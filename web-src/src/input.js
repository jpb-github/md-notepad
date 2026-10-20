// Keyboard and mouse input of the Rendered editor: shortcuts (spec section 3), Markdown
// input rules, lists, code blocks and task checkboxes (section 4).
import { baseKeymap, chainCommands } from "prosemirror-commands";
import { dropCursor } from "prosemirror-dropcursor";
import { gapCursor } from "prosemirror-gapcursor";
import { redo, undo } from "prosemirror-history";
import { InputRule, inputRules, textblockTypeInputRule, undoInputRule, wrappingInputRule } from "prosemirror-inputrules";
import { keymap } from "prosemirror-keymap";
import { liftListItem, sinkListItem, splitListItem } from "prosemirror-schema-list";
import { Plugin, TextSelection } from "prosemirror-state";
import { FORMATTING_COMMANDS } from "./commands.js";
import { cleanLanguage, schema } from "./schema.js";

const { nodes, marks } = schema;
const CODE_INDENT = "    ";

const bind = (name, args) => (state, dispatch, view) => FORMATTING_COMMANDS[name].run(state, dispatch, view, args);
const inCode = (state) => Boolean(state.selection.$from.parent.type.spec.code);

// `**text**`, `*text*`, `~~text~~`, `` `text` `` typed inline: the markers become the mark.
function markRule(regexp, type) {
  return new InputRule(regexp, (state, match, start, end) => {
    const $start = state.doc.resolve(start);
    if (!$start.parent.type.allowsMarkType(type)) return null;
    return state.tr
      .replaceWith(start, end, schema.text(match[1], type.create().addToSet($start.marks())))
      .removeStoredMark(type);
  }, { inCodeMark: false });
}

// `[ ] ` or `[x] ` at the start of a list item's first paragraph makes it a task item.
const taskRule = new InputRule(/^\[([ xX])\]\s$/, (state, match, start, end) => {
  const $start = state.doc.resolve(start);
  const item = $start.node(-1);
  if (item?.type !== nodes.list_item || $start.index(-1) !== 0 || item.attrs.checked !== null) return null;
  return state.tr.delete(start, end).setNodeMarkup($start.before(-1), null, { ...item.attrs, checked: match[1] !== " " });
});

const rules = inputRules({
  rules: [
    textblockTypeInputRule(/^(#{1,6})\s$/, nodes.heading, (match) => ({ level: match[1].length })),
    wrappingInputRule(/^\s*[-*]\s$/, nodes.bullet_list),
    wrappingInputRule(
      /^(\d{1,9})\.\s$/, nodes.ordered_list, (match) => ({ start: Number(match[1]) }),
      (match, node) => node.childCount + node.attrs.start === Number(match[1]),
    ),
    wrappingInputRule(/^\s*>\s$/, nodes.blockquote),
    taskRule,
    markRule(/(?<![*\w])\*\*([^*\s](?:[^*]*[^*\s])?)\*\*$/, marks.strong),
    markRule(/(?<![*\w])\*([^*\s](?:[^*]*[^*\s])?)\*$/, marks.em),
    markRule(/(?<!~)~~([^~\s](?:[^~]*[^~\s])?)~~$/, marks.strike),
    markRule(/(?<!`)`([^`]+)`$/, marks.code),
  ],
});

// Enter at the end of a paragraph holding only ``` + optional language makes a code block;
// one holding only --- makes a horizontal rule followed by a new paragraph.
function fenceOrRule(state, dispatch) {
  const { $from, empty } = state.selection;
  const block = $from.parent;
  if (!empty || block.type !== nodes.paragraph || block.childCount !== 1 || !block.firstChild.isText
      || $from.parentOffset !== block.content.size) return false;
  const fence = /^```([^\s`]*)$/.exec(block.textContent);
  const replacement = fence
    ? [nodes.code_block.create({ language: cleanLanguage(fence[1]) })]
    : block.textContent === "---" ? [nodes.horizontal_rule.create(), nodes.paragraph.create()] : null;
  if (!replacement) return false;
  const index = $from.index(-1);
  if (!replacement.every((node) => $from.node(-1).canReplaceWith(index, index + 1, node.type))) return false;
  if (dispatch) {
    const start = $from.before();
    const tr = state.tr.replaceWith(start, $from.after(), replacement);
    const caret = start + (fence ? 1 : replacement[0].nodeSize + 1);
    dispatch(tr.setSelection(TextSelection.create(tr.doc, caret)).scrollIntoView());
  }
  return true;
}

// A new item after a task item is an unchecked task item.
function splitItem(state, dispatch) {
  const { $from } = state.selection;
  const item = $from.depth >= 2 ? $from.node(-1) : null;
  const attrs = item?.type === nodes.list_item && item.attrs.checked !== null ? { checked: false } : undefined;
  return splitListItem(nodes.list_item, attrs)(state, dispatch);
}

function codeTab(state, dispatch) {
  if (!inCode(state)) return false;
  if (dispatch) dispatch(state.tr.insertText(CODE_INDENT).scrollIntoView());
  return true;
}

// Arrow keys leave a code block that has no block after (or before) it in its parent:
// a new paragraph is added there.
function leaveCode(dir) {
  const after = dir === "down" || dir === "right";
  return (state, dispatch, view) => {
    const { $head, empty } = state.selection;
    if (!empty || !$head.parent.type.spec.code || !view?.endOfTextblock(dir)) return false;
    const parent = $head.node(-1);
    const index = $head.index(-1);
    if (after ? index < parent.childCount - 1 : index > 0) return false;
    const at = after ? index + 1 : index;
    if (!parent.canReplaceWith(at, at, nodes.paragraph)) return false;
    if (dispatch) {
      const pos = after ? $head.after() : $head.before();
      const tr = state.tr.insert(pos, nodes.paragraph.create());
      dispatch(tr.setSelection(TextSelection.create(tr.doc, pos + 1)).scrollIntoView());
    }
    return true;
  };
}

const consume = () => true; // Tab never moves the focus out of the editor

const keys = {
  "Mod-z": undo,
  "Mod-y": redo,
  "Mod-Shift-z": redo,
  "Backspace": undoInputRule,
  "Mod-b": bind("toggleMark", "strong"),
  "Mod-i": bind("toggleMark", "em"),
  "Mod-Shift-x": bind("toggleMark", "strike"),
  "Mod-`": bind("toggleMark", "code"),
  "Mod-k": bind("linkDialog"),
  "Mod-Shift-8": bind("toggleList", "bullet"),
  "Mod-Shift-7": bind("toggleList", "ordered"),
  "Mod-Shift-9": bind("toggleList", "task"),
  "Mod-Shift-.": bind("toggleQuote"),
  "Mod-Space": bind("clearFormatting"),
  "Mod-Alt-0": bind("setBlock", { type: "paragraph" }),
  "Enter": chainCommands(fenceOrRule, splitItem),
  "Tab": chainCommands(codeTab, sinkListItem(nodes.list_item), consume),
  "Shift-Tab": chainCommands((state) => inCode(state), liftListItem(nodes.list_item), consume),
  "ArrowDown": leaveCode("down"),
  "ArrowRight": leaveCode("right"),
  "ArrowUp": leaveCode("up"),
  "ArrowLeft": leaveCode("left"),
};
for (let level = 1; level <= 6; level++) keys[`Mod-Alt-${level}`] = bind("setBlock", { type: "heading", level });

function isTaskBox(view, target) {
  return target instanceof HTMLInputElement && target.classList.contains("task-list-item-checkbox")
    && view.dom.contains(target);
}

// Clicking a task checkbox toggles the item (an edit: undoable, marks the document dirty).
const taskBoxPlugin = new Plugin({
  props: {
    handleDOMEvents: {
      click(view, event) {
        if (!isTaskBox(view, event.target)) return false;
        const $pos = view.state.doc.resolve(view.posAtDOM(event.target.nextElementSibling, 0));
        for (let depth = $pos.depth; depth > 0; depth--) {
          const item = $pos.node(depth);
          if (item.type !== nodes.list_item) continue;
          if (item.attrs.checked !== null) {
            view.dispatch(view.state.tr.setNodeMarkup($pos.before(depth), null, { ...item.attrs, checked: !item.attrs.checked }));
          }
          break;
        }
        return true;
      },
    },
  },
});

// Order matters: our keys run before ProseMirror's base keymap (Enter, Backspace, ...).
export function inputPlugins() {
  return [rules, keymap(keys), keymap(baseKeymap), taskBoxPlugin, gapCursor(), dropCursor({ color: "var(--fg)" })];
}
