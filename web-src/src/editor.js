// Rendered editor bundle: EditorView, document lifecycle and window.mdEditor, the API
// Python calls through runJavaScript. Calls to Python go through bridge.js; commands.js
// and input.js hold the formatting commands, shortcuts and input rules.
import "prosemirror-view/style/prosemirror.css";
import "prosemirror-gapcursor/style/gapcursor.css";
import "./editor.css";
import { history, redo, redoDepth, undo, undoDepth } from "prosemirror-history";
import { EditorState, NodeSelection, Plugin, Selection } from "prosemirror-state";
import { EditorView } from "prosemirror-view";
import { connectBridge, send } from "./bridge.js";
import { FORMATTING_COMMANDS } from "./commands.js";
import { inputPlugins } from "./input.js";
import { createNodeViews, displayPlugins, refreshFrames } from "./nodeviews.js";
import { schema } from "./schema.js";

const SELECTION_THROTTLE_MS = 50;
// prosemirror-tables' cell attrs; docschema does not know them (merged cells are a non-goal).
const CELL_EXTRAS = ["colspan", "rowspan", "colwidth"];

// Commands run by mdEditor.command(name, args): { run(state, dispatch, view, args) -> boolean,
// can?(state) -> boolean }. Each `can` is reported in selectionState.can.
const COMMANDS = {
  undo: { run: (state, dispatch) => undo(state, dispatch), can: (state) => undoDepth(state) > 0 },
  redo: { run: (state, dispatch) => redo(state, dispatch), can: (state) => redoDepth(state) > 0 },
  ...FORMATTING_COMMANDS,
};

// What has been reported to Python since the last setDocument.
const sent = { changed: false, caretBlock: null, selectionState: null, hoverLink: "" };
let selectionTimer = null;

function linkAt(view, target) {
  const link = target instanceof Element ? target.closest("a[href]") : null;
  return link && view.dom.contains(link) ? link : null;
}

function hover(href) {
  if (href === sent.hoverLink) return;
  sent.hoverLink = href;
  send("hoverLink", href);
}

// Hovering a link shows its URL in the status bar; Ctrl+click opens it (Python checks
// the scheme). A plain click only places the caret: Chromium follows no links in
// editable content.
const linkPlugin = new Plugin({
  props: {
    handleDOMEvents: {
      mouseover(view, event) {
        hover(linkAt(view, event.target)?.getAttribute("href") ?? "");
        return false;
      },
      mouseleave() {
        hover("");
        return false;
      },
      mousedown(view, event) {
        const link = event.ctrlKey && event.button === 0 ? linkAt(view, event.target) : null;
        if (!link) return false;
        event.preventDefault();
        send("openLink", link.getAttribute("href"));
        return true;
      },
    },
  },
});

const callbacks = { editProtected: (index) => send("editProtected", index) };
const plugins = [history(), ...inputPlugins(), linkPlugin, ...displayPlugins(callbacks)];

function createState(json) {
  if (!json) return EditorState.create({ schema, plugins });
  const doc = schema.nodeFromJSON(json);
  doc.check(); // throws on content the schema does not allow
  return EditorState.create({ schema, plugins, doc });
}

// Top-level block of the selection start (a gap cursor after the last block counts as it).
function caretBlock(state) {
  return Math.min(state.selection.$from.index(0), state.doc.childCount - 1);
}

// Toolbar state: marks active at the caret (or anywhere in the selection, as toggling
// then removes them), the textblock type at the selection start, command availability.
function selectionState(state) {
  const { empty, from, to, $from } = state.selection;
  const stored = empty ? state.storedMarks || $from.marks() : null;
  const marks = Object.values(schema.marks)
    .filter((type) => (stored ? type.isInSet(stored) : state.doc.rangeHasMark(from, to, type)))
    .map((type) => type.name);
  const parent = $from.parent;
  let block = null;
  if (parent.isTextblock) {
    block = parent.type.name === "heading" ? { type: "heading", level: parent.attrs.level } : { type: parent.type.name };
  }
  const can = {};
  for (const [name, command] of Object.entries(COMMANDS)) {
    if (command.can) can[name] = command.can(state);
  }
  return { marks, block, can };
}

function flushSelectionState() {
  selectionTimer = null;
  const state = selectionState(view.state);
  const key = JSON.stringify(state);
  if (key === sent.selectionState) return;
  sent.selectionState = key;
  send("selectionState", state);
}

// caretBlock goes out at once (it changes rarely and a mode switch reads it);
// selectionState at most every SELECTION_THROTTLE_MS, always with the latest state.
function report(state) {
  const index = caretBlock(state);
  if (index !== sent.caretBlock) {
    sent.caretBlock = index;
    send("caretBlock", index);
  }
  if (selectionTimer === null) selectionTimer = setTimeout(flushSelectionState, SELECTION_THROTTLE_MS);
}

const view = new EditorView(document.getElementById("editor"), {
  state: createState(null),
  nodeViews: createNodeViews(),
  dispatchTransaction(tr) {
    const before = view.state.doc;
    view.updateState(view.state.apply(tr));
    if (view.state.doc !== before && !sent.changed) {
      sent.changed = true;
      send("changed");
    }
    report(view.state);
  },
});

// New EditorState: empty undo history, caret at the start. With keepScroll the page
// keeps its scroll offset (external reload), otherwise it scrolls to the top.
function setDocument(json, keepScroll = false) {
  const state = createState(json);
  const scroller = document.scrollingElement;
  const top = scroller.scrollTop;
  view.updateState(state);
  scroller.scrollTop = keepScroll ? top : 0;
  clearTimeout(selectionTimer);
  selectionTimer = null;
  Object.assign(sent, { changed: false, caretBlock: null, selectionState: null });
  hover("");
  report(state);
}

// toJSON() shares each node's attrs object: copy the cells' attrs, never edit them.
function withoutCellExtras(json) {
  if (json.type === "table_header" || json.type === "table_cell") {
    json.attrs = Object.fromEntries(Object.entries(json.attrs).filter(([name]) => !CELL_EXTRAS.includes(name)));
  }
  json.content?.forEach(withoutCellExtras);
  return json;
}

window.mdEditor = {
  schema,
  view,
  setDocument,
  getDocument: () => withoutCellExtras(view.state.doc.toJSON()),
  // Runs a toolbar or menu command; false when it does not apply here (or is unknown).
  command(name, args) {
    const command = Object.hasOwn(COMMANDS, name) ? COMMANDS[name] : null;
    if (!command) {
      console.warn(`mdEditor.command: unknown command ${name}`);
      return false;
    }
    const done = command.run(view.state, view.dispatch, view, args);
    if (done) view.focus();
    return done;
  },
  // `css` is render.page_css(theme); the frames re-read the theme colors.
  setTheme(css) {
    document.getElementById("theme").textContent = css;
    refreshFrames();
  },
  // Caret at the start of top-level block `index`; atoms (protected blocks, rules) are selected.
  focusBlock(index) {
    const { doc } = view.state;
    if (!Number.isInteger(index) || index < 0 || index >= doc.childCount) return;
    let pos = 0;
    for (let i = 0; i < index; i++) pos += doc.child(i).nodeSize;
    const block = doc.child(index);
    const selection = block.isLeaf ? NodeSelection.create(doc, pos) : Selection.near(doc.resolve(pos + 1));
    view.dispatch(view.state.tr.setSelection(selection).scrollIntoView());
    view.focus();
  },
};

connectBridge();
