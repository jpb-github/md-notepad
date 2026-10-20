// Rendered editor bundle: EditorView, document lifecycle and window.mdEditor, the API
// Python calls through runJavaScript. Calls to Python go through bridge.js; commands.js
// and input.js hold the formatting commands, shortcuts and input rules; tables.js the
// table editing.
import "prosemirror-view/style/prosemirror.css";
import "prosemirror-gapcursor/style/gapcursor.css";
import "prosemirror-tables/style/tables.css";
import "./editor.css";
import { selectAll } from "prosemirror-commands";
import { history, redo, redoDepth, undo, undoDepth } from "prosemirror-history";
import { EditorState, NodeSelection, Plugin, Selection } from "prosemirror-state";
import { EditorView } from "prosemirror-view";
import { connectBridge, send } from "./bridge.js";
import { FORMATTING_COMMANDS } from "./commands.js";
import { inputPlugins } from "./input.js";
import {
  HIGHLIGHT_META, applyHighlights, createNodeViews, displayPlugins, flushLanguageFields, refreshFrames, resetStaleCode,
  staleCodeBlocks,
} from "./nodeviews.js";
import { schema } from "./schema.js";
import { TABLE_COMMANDS, tablePlugins } from "./tables.js";

const SELECTION_THROTTLE_MS = 50;
// prosemirror-tables' cell attrs; docschema does not know them (merged cells are a non-goal).
const CELL_EXTRAS = ["colspan", "rowspan", "colwidth"];

// Commands run by mdEditor.command(name, args): { run(state, dispatch, view, args) -> boolean,
// can?(state) -> boolean }. Each `can` is reported in selectionState.can.
const COMMANDS = {
  undo: { run: (state, dispatch) => undo(state, dispatch), can: (state) => undoDepth(state) > 0 },
  redo: { run: (state, dispatch) => redo(state, dispatch), can: (state) => redoDepth(state) > 0 },
  // Edit > Select All: what Ctrl+A does (baseKeymap). Chromium's own select-all reaches the
  // editor state only after a selectionchange, too late for a Paste right after it.
  selectAll: { run: (state, dispatch) => selectAll(state, dispatch) },
  ...FORMATTING_COMMANDS,
  ...TABLE_COMMANDS,
};

// What has been reported to Python since the last setDocument or, for changed, markClean.
const sent = { changed: false, caretBlock: null, selectionState: null, hoverLink: "" };
// Python numbers every setDocument and markClean; changed(epoch) names the latest one, so
// Python can tell an edit made after a save's pull from one made before it.
let epoch = 0;
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

// A right-click outside the selection first moves the caret there, so the context menu
// Python then shows (edit and table items, built from selectionState()) acts on that place.
const contextMenuPlugin = new Plugin({
  props: {
    handleDOMEvents: {
      contextmenu(view, event) {
        const hit = view.posAtCoords({ left: event.clientX, top: event.clientY });
        const { from, to } = view.state.selection;
        if (hit && (hit.pos < from || hit.pos > to)) {
          view.dispatch(view.state.tr.setSelection(Selection.near(view.state.doc.resolve(hit.pos))));
        }
        return false;
      },
    },
  },
});

// The first change since the last setDocument or markClean goes to Python once.
function reportChange() {
  if (sent.changed) return;
  sent.changed = true;
  send("changed", epoch);
}

const callbacks = { editProtected: (index) => send("editProtected", index), pendingEdit: reportChange };
// Table keys first: Tab moves between cells before input.js consumes it.
const plugins = [
  history(), ...tablePlugins(), ...inputPlugins(), linkPlugin, contextMenuPlugin, ...displayPlugins(callbacks),
];

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
  nodeViews: createNodeViews(callbacks),
  dispatchTransaction(tr) {
    const before = view.state.doc;
    view.updateState(view.state.apply(tr));
    if (view.state.doc !== before && !tr.getMeta(HIGHLIGHT_META)) reportChange();
    report(view.state);
  },
});

// New EditorState: empty undo history, caret at the start. With keepScroll the page
// keeps its scroll offset (external reload), otherwise it scrolls to the top.
// The epoch is adopted first: Python has moved to it already, so if the document is
// rejected (it throws and the old one stays) edits must still be reported as changed(epoch).
function setDocument(json, keepScroll = false, docEpoch = epoch) {
  epoch = docEpoch;
  sent.changed = false;
  const state = createState(json);
  resetStaleCode();
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
  getDocument() {
    flushLanguageFields(); // a language typed but not yet committed is part of the document
    return withoutCellExtras(view.state.doc.toJSON());
  },
  // Python has the current document (a pull): the next edit reports changed(cleanEpoch).
  markClean(cleanEpoch = epoch) {
    epoch = cleanEpoch;
    sent.changed = false;
  },
  // The selectionState payload for the current selection, at once (context menu).
  selectionState: () => selectionState(view.state),
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
  // Edited code blocks the caret has left, for Python to highlight; applyHighlights answers.
  staleCodeBlocks: () => staleCodeBlocks(view.state),
  applyHighlights: (updates) => applyHighlights(view, updates),
  // `css` is render.page_css(theme); the frames re-read the theme colors.
  setTheme(css) {
    document.getElementById("theme").textContent = css;
    refreshFrames();
  },
  // Find bar open: code blocks show their plain text only, so find-in-page counts and
  // highlights each match once, in the editable copy (editor.css).
  setFinding(on) {
    document.body.classList.toggle("md-finding", on);
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
