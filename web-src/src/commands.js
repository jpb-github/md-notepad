// Formatting commands of the Rendered editor, run by toolbar buttons, menus and keys.
// Each entry is { run(state, dispatch, view, args) -> boolean, can(state) -> boolean };
// editor.js merges them into COMMANDS (mdEditor.command), and `can` is reported in
// selectionState.can. run(state) without dispatch only answers "would it apply".
import { setBlockType, toggleMark, wrapIn } from "prosemirror-commands";
import { liftListItem, wrapInList } from "prosemirror-schema-list";
import { Selection, TextSelection } from "prosemirror-state";
import { liftTarget } from "prosemirror-transform";
import { send } from "./bridge.js";
import { cleanLanguage, isSafeUrl, schema } from "./schema.js";

const { nodes, marks } = schema;
// Marks the toolbar toggles; links have their own commands.
const TOGGLED_MARKS = ["strong", "em", "strike", "code"];
const LIST_TYPES = { bullet: nodes.bullet_list, ordered: nodes.ordered_list, task: nodes.bullet_list };
const MAX_TABLE_SIZE = 50;

const isList = (node) => node.type === nodes.bullet_list || node.type === nodes.ordered_list;

// `attrs` limited to the attrs `type` declares (the others default): a node refuses unknown attrs.
function ownAttrs(type, attrs) {
  return Object.fromEntries(Object.entries(type.spec.attrs).map(([name, spec]) => [name, name in attrs ? attrs[name] : spec.default]));
}

// "bullet", "ordered" or "task": task items carry a checkbox in either list type.
function listKind(list, item) {
  if (item.attrs.checked !== null) return "task";
  return list.type === nodes.ordered_list ? "ordered" : "bullet";
}

// True when both ends of the selection sit in inline content that allows `type`.
function marksAllowed(state, type) {
  const { $from, $to } = state.selection;
  return [$from, $to].every(($pos) => $pos.parent.inlineContent && $pos.parent.type.allowsMarkType(type));
}

// The code block holding the selection start: { node, pos } or null.
function codeBlockAt(state) {
  const { $from } = state.selection;
  for (let depth = $from.depth; depth > 0; depth--) {
    if ($from.node(depth).type === nodes.code_block) return { node: $from.node(depth), pos: $from.before(depth) };
  }
  return null;
}

// The whole link next to `$pos` (the text after it first, then the text before it):
// { from, to, mark } or null.
function linkAround($pos) {
  const parent = $pos.parent;
  const candidates = $pos.textOffset ? [$pos.index()] : [$pos.index(), $pos.index() - 1];
  for (const index of candidates) {
    const child = index >= 0 && index < parent.childCount ? parent.child(index) : null;
    const mark = child ? marks.link.isInSet(child.marks) : null;
    if (!mark) continue;
    let first = index;
    let last = index;
    while (first > 0 && mark.isInSet(parent.child(first - 1).marks)) first--;
    while (last + 1 < parent.childCount && mark.isInSet(parent.child(last + 1).marks)) last++;
    let from = $pos.start();
    for (let i = 0; i < first; i++) from += parent.child(i).nodeSize;
    let to = from;
    for (let i = first; i <= last; i++) to += parent.child(i).nodeSize;
    return { from, to, mark };
  }
  return null;
}

// What a link command acts on: the selection, else the link around the caret, else the caret.
function linkTarget(state) {
  const { from, to, empty, $from } = state.selection;
  if (!empty) {
    const around = linkAround($from);
    const mark = around && around.from <= from && around.to >= to ? around.mark : null;
    return { from, to, mark };
  }
  return linkAround($from) ?? { from, to, mark: null };
}

// Inserts block `node` after the textblock (or selected block) at the selection, at the
// first level up that allows it; an empty paragraph is replaced instead. The caret goes
// into the new block (its first cell for a table) or, for an atom, to the next textblock:
// `trailingParagraph` adds an empty paragraph when nothing follows the new block;
// `topLevel` only allows the document level (the parser reads tables nowhere else).
function insertBlock(state, dispatch, node, trailingParagraph = false, topLevel = false) {
  const { $from, $to, empty } = state.selection;
  const tr = state.tr;
  let pos = null;
  if (empty && $from.parent.type === nodes.paragraph && $from.parent.content.size === 0
      && (!topLevel || $from.depth === 1)
      && $from.node(-1).canReplaceWith($from.index(-1), $from.index(-1) + 1, node.type)) {
    pos = $from.before();
    tr.replaceWith(pos, $from.after(), node);
  } else {
    for (let depth = $to.depth; depth >= 0 && pos === null; depth--) {
      if (topLevel && depth > 0) continue;
      const index = $to.indexAfter(depth);
      if ($to.node(depth).canReplaceWith(index, index, node.type)) {
        pos = depth === $to.depth ? $to.pos : $to.after(depth + 1);
      }
    }
    if (pos === null) return false;
    tr.insert(pos, node);
  }
  if (!dispatch) return true;
  const end = pos + node.nodeSize;
  if (trailingParagraph && !tr.doc.resolve(end).nodeAfter) tr.insert(end, nodes.paragraph.create());
  tr.setSelection(Selection.near(tr.doc.resolve(pos + 1)));
  dispatch(tr.scrollIntoView());
  return true;
}

function blockType(args) {
  const type = args?.type;
  if (type === "paragraph") return [nodes.paragraph, null];
  if (type === "code_block") return [nodes.code_block, { language: cleanLanguage(args.language ?? "") }];
  if (type === "heading" && Number.isInteger(args.level) && args.level >= 1 && args.level <= 6) {
    return [nodes.heading, { level: args.level }];
  }
  return null;
}

function toggleList(state, dispatch, kind) {
  const type = LIST_TYPES[kind];
  if (!type) return false;
  const { $from, $to } = state.selection;
  const range = $from.blockRange($to, isList);
  if (range) {
    const list = range.parent;
    if (listKind(list, list.child(range.startIndex)) === kind) return liftListItem(nodes.list_item)(state, dispatch);
    // Another kind of list: change the list in place (type, then every item's checkbox).
    if (dispatch) {
      const listPos = range.$from.before(range.depth);
      const tr = state.tr.setNodeMarkup(listPos, type, ownAttrs(type, list.attrs));
      let pos = listPos + 1;
      list.forEach((item) => {
        const checked = kind === "task" ? item.attrs.checked ?? false : null;
        tr.setNodeMarkup(pos, null, { ...item.attrs, checked });
        pos += item.nodeSize;
      });
      dispatch(tr.scrollIntoView());
    }
    return true;
  }
  return wrapInList(type)(state, dispatch && ((tr) => {
    if (kind === "task") {
      const wrapped = tr.selection.$from.blockRange(tr.selection.$to, isList);
      if (wrapped) {
        for (let i = wrapped.startIndex; i < wrapped.endIndex; i++) {
          const pos = tr.doc.resolve(wrapped.start).posAtIndex(i);
          tr.setNodeMarkup(pos, null, { ...tr.doc.nodeAt(pos).attrs, checked: false });
        }
      }
    }
    dispatch(tr);
  }));
}

function toggleQuote(state, dispatch) {
  const { $from, $to } = state.selection;
  const range = $from.blockRange($to, (node) => node.type === nodes.blockquote);
  if (!range) return wrapIn(nodes.blockquote)(state, dispatch);
  // Lift the selected blocks out of the blockquote that holds them.
  const target = liftTarget(range);
  if (target === null) return false;
  if (dispatch) dispatch(state.tr.lift(range, target).scrollIntoView());
  return true;
}

function setLink(state, dispatch, args) {
  const href = String(args?.href ?? "").trim();
  if (!href || !isSafeUrl(href) || !marksAllowed(state, marks.link)) return false;
  if (!dispatch) return true;
  const target = linkTarget(state);
  const link = marks.link.create({ href, title: args.title ?? target.mark?.attrs.title ?? null });
  const current = state.doc.textBetween(target.from, target.to);
  const wanted = String(args.text ?? "");
  const text = wanted || current || href;
  const tr = state.tr;
  const $start = state.doc.resolve(target.from);
  // Unchanged or empty text keeps the selection (an image has no text): only the mark is added.
  if (text === current || (!wanted && target.from < target.to) || !$start.sameParent(state.doc.resolve(target.to))) {
    tr.addMark(target.from, target.to, link);
  } else {
    // New text: it takes the marks of the text it replaces, plus the link.
    const old = target.from < target.to ? state.doc.nodeAt(target.from)?.marks ?? [] : $start.marks();
    tr.replaceWith(target.from, target.to, schema.text(text, link.addToSet(marks.link.removeFromSet(old))));
    tr.setSelection(TextSelection.create(tr.doc, target.from + text.length));
  }
  dispatch(tr.scrollIntoView());
  return true;
}

function removeLink(state, dispatch) {
  const { empty, from, to, $from } = state.selection;
  const target = empty ? linkAround($from) : { from, to };
  if (!target || !state.doc.rangeHasMark(target.from, target.to, marks.link)) return false;
  if (dispatch) dispatch(state.tr.removeMark(target.from, target.to, marks.link).scrollIntoView());
  return true;
}

// Removes bold, italic, strikethrough and code (links stay: they are content) and turns
// the textblocks in the selection into paragraphs.
function clearFormatting(state, dispatch) {
  const { from, to, empty, $from } = state.selection;
  if (empty && !$from.parent.isTextblock) return false;
  if (dispatch) {
    const tr = state.tr;
    if (empty) tr.setStoredMarks([]);
    else for (const name of TOGGLED_MARKS) tr.removeMark(from, to, marks[name]);
    tr.setBlockType(from, to, nodes.paragraph);
    dispatch(tr.scrollIntoView());
  }
  return true;
}

function command(run) {
  return { run, can: (state) => run(state, null, null, undefined) };
}

export const FORMATTING_COMMANDS = {
  // args: "strong" | "em" | "strike" | "code"; can: any of them applies here.
  toggleMark: {
    run: (state, dispatch, view, name) => TOGGLED_MARKS.includes(name) && toggleMark(marks[name])(state, dispatch),
    can: (state) => marksAllowed(state, marks.strong),
  },
  // args: {type: "paragraph"} | {type: "heading", level: 1-6} | {type: "code_block", language?}
  setBlock: {
    run: (state, dispatch, view, args) => {
      const target = blockType(args);
      return Boolean(target) && setBlockType(...target)(state, dispatch);
    },
    can: (state) => [nodes.paragraph, nodes.heading, nodes.code_block]
      .some((type) => setBlockType(type, type === nodes.heading ? { level: 1 } : null)(state)),
  },
  // args: "bullet" | "ordered" | "task"
  toggleList: {
    run: (state, dispatch, view, kind) => toggleList(state, dispatch, kind),
    can: (state) => ["bullet", "ordered"].some((kind) => toggleList(state, null, kind)),
  },
  toggleQuote: command((state, dispatch) => toggleQuote(state, dispatch)),
  // args: {language?}
  insertCodeBlock: command((state, dispatch, view, args) => insertBlock(
    state, dispatch, nodes.code_block.create({ language: cleanLanguage(args?.language ?? "") }),
  )),
  // args: {rows, cols}: rows includes the header row
  insertTable: {
    run: (state, dispatch, view, args) => {
      const { rows, cols } = args ?? {};
      const ok = (n) => Number.isInteger(n) && n >= 1 && n <= MAX_TABLE_SIZE;
      if (!ok(rows) || !ok(cols)) return false;
      const row = (cell) => nodes.table_row.create(null, Array.from({ length: cols }, () => cell.create()));
      const table = nodes.table.create(null, [
        row(nodes.table_header), ...Array.from({ length: rows - 1 }, () => row(nodes.table_cell)),
      ]);
      return insertBlock(state, dispatch, table, false, true);
    },
    can: (state) => insertBlock(state, null, nodes.table.createAndFill(), false, true),
  },
  // args: {src, display_src?, alt?, title?}: src as written in Markdown, display_src resolved by Python
  insertImage: {
    run: (state, dispatch, view, args) => {
      const src = String(args?.src ?? "");
      const displaySrc = String(args?.display_src ?? src);
      if (!src || !isSafeUrl(src) || !isSafeUrl(displaySrc) || !canInsertImage(state)) return false;
      const image = nodes.image.create({ src, display_src: displaySrc, alt: args.alt ?? "", title: args.title ?? null });
      if (dispatch) dispatch(state.tr.replaceSelectionWith(image).scrollIntoView());
      return true;
    },
    can: (state) => canInsertImage(state),
  },
  insertRule: command((state, dispatch) => insertBlock(state, dispatch, nodes.horizontal_rule.create(), true)),
  // args: {href, text?, title?}: text "" keeps the current text
  setLink: {
    run: (state, dispatch, view, args) => setLink(state, dispatch, args),
    can: (state) => marksAllowed(state, marks.link),
  },
  removeLink: command((state, dispatch) => removeLink(state, dispatch)),
  // Asks Python for the link dialog (Ctrl+K, toolbar); Python answers with setLink or removeLink.
  linkDialog: command((state, dispatch) => {
    if (!marksAllowed(state, marks.link)) return false;
    if (dispatch) {
      const target = linkTarget(state);
      send("requestLinkDialog", state.doc.textBetween(target.from, target.to, " "), target.mark?.attrs.href ?? "");
    }
    return true;
  }),
  // Asks Python for the image dialog; Python answers with insertImage.
  imageDialog: command((state, dispatch) => {
    if (!canInsertImage(state)) return false;
    if (dispatch) send("requestImageDialog");
    return true;
  }),
  clearFormatting: command((state, dispatch) => clearFormatting(state, dispatch)),
  // args: language string; the highlight belongs to the old language and is dropped
  setCodeLanguage: {
    run: (state, dispatch, view, language) => {
      const block = codeBlockAt(state);
      if (!block) return false;
      const attrs = { ...block.node.attrs, language: cleanLanguage(language ?? ""), highlight: "" };
      if (dispatch) dispatch(state.tr.setNodeMarkup(block.pos, null, attrs));
      return true;
    },
    can: (state) => codeBlockAt(state) !== null,
  },
};

function canInsertImage(state) {
  const { $from } = state.selection;
  return $from.parent.inlineContent && $from.parent.canReplaceWith($from.index(), $from.index(), nodes.image);
}
