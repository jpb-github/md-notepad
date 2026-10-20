// ProseMirror schema of the Rendered editor, mirroring mdviewer/core/docschema.py.
// CONTRACT holds docschema's names and required attrs as strict JSON:
// tests/test_docschema.py parses it and compares it with the Python tables. The specs
// below get their attrs from CONTRACT and must list the same names in the same order
// (checked when this module loads). Change both files together and rebuild the bundle.
import { Schema } from "prosemirror-model";
import { tableNodes } from "prosemirror-tables";

export const CONTRACT = {
  "blockNodes": {
    "doc": [],
    "paragraph": [],
    "heading": ["level"],
    "blockquote": [],
    "bullet_list": ["tight"],
    "ordered_list": ["start", "tight"],
    "list_item": ["checked"],
    "code_block": ["language", "highlight"],
    "horizontal_rule": [],
    "table": [],
    "table_row": [],
    "table_header": ["align"],
    "table_cell": ["align"],
    "front_matter": ["source"],
    "html_block": ["source"],
    "footnote_def": ["label", "source"]
  },
  "inlineNodes": {
    "text": [],
    "hard_break": [],
    "image": ["src", "display_src", "alt", "title"],
    "footnote_ref": ["label"],
    "html_inline": ["source"]
  },
  "marks": {
    "strong": [],
    "em": [],
    "strike": [],
    "code": [],
    "link": ["href", "title"]
  },
  "protectedNodes": ["footnote_def", "footnote_ref", "front_matter", "html_block", "html_inline"],
  "topLevelNodes": [
    "blockquote", "bullet_list", "code_block", "footnote_def", "front_matter", "heading",
    "horizontal_rule", "html_block", "ordered_list", "paragraph", "table"
  ]
};

// Defaults let ProseMirror create nodes on its own (createAndFill, paste). label and
// href have none: a footnote or link without them is never created implicitly.
const ATTR_DEFAULTS = {
  level: 1, tight: true, start: 1, checked: null, language: "", highlight: "",
  align: null, source: "", src: "", display_src: "", alt: "", title: null,
};
const TOP_LEVEL = new Set(CONTRACT.topLevelNodes);
const ALIGNMENTS = ["left", "center", "right"];

// Same policy as core/urls.is_safe: no script URLs, no data: URLs except images.
// Browsers ignore ASCII whitespace and control characters inside a scheme.
export function isSafeUrl(url) {
  const compact = [...String(url)].filter((ch) => ch.codePointAt(0) > 0x20).join("").toLowerCase();
  return compact.startsWith("data:image/") || !/^(javascript|vbscript|data):/.test(compact);
}

// A fence info word: no whitespace, no backticks (they would end a backtick fence).
export function cleanLanguage(value) {
  return (String(value).trim().split(/\s+/)[0] || "").replace(/`/g, "");
}

function tightFromDOM(dom) {
  const tight = dom.getAttribute("data-tight");
  return tight === null ? !dom.querySelector(":scope > li > p") : tight === "true";
}

function startFromDOM(dom) {
  const start = parseInt(dom.getAttribute("start") ?? "1", 10);
  return Number.isInteger(start) && start >= 0 ? start : 1;
}

// GitHub task items: <li class="task-list-item"><input type="checkbox" checked> text</li>,
// or with the box inside the first <p> of a loose list.
function checkedFromDOM(dom) {
  const box = dom.querySelector(
    ":scope > input[type=checkbox], :scope > p:first-child > input[type=checkbox]",
  );
  return box ? box.hasAttribute("checked") : null;
}

function languageFromDOM(dom) {
  const code = dom.querySelector("code");
  const fromClass = /(?:^|\s)language-(\S+)/.exec(code ? code.className : "");
  return cleanLanguage(dom.getAttribute("data-language") || (fromClass ? fromClass[1] : ""));
}

function alignFromDOM(dom) {
  const align = (dom.style.textAlign || dom.getAttribute("align") || "").toLowerCase();
  return ALIGNMENTS.includes(align) ? align : null;
}

function imageFromDOM(dom) {
  const src = dom.getAttribute("data-src") ?? dom.getAttribute("src");
  const displaySrc = dom.getAttribute("src");
  if (!isSafeUrl(src) || !isSafeUrl(displaySrc)) return false;
  return { src, display_src: displaySrc, alt: dom.getAttribute("alt") ?? "", title: dom.getAttribute("title") };
}

const tables = tableNodes({
  tableGroup: "block",
  cellContent: "inline*",
  cellAttributes: {
    align: {
      default: null,
      getFromDOM: alignFromDOM,
      setDOMAttr: (value, attrs) => {
        if (value) attrs.style = `${attrs.style || ""}text-align: ${value};`;
      },
    },
  },
});

// Node specs in CONTRACT order. Group "block" must start with paragraph and group
// "inline" with text: ProseMirror fills required content with a group's first type.
// toDOM is what ProseMirror renders without a node view and what it puts on the
// clipboard; parseDOM reads pasted HTML, including our own clipboard output.
const nodes = {
  doc: { content: "front_matter? (block | footnote_def)+" },
  paragraph: {
    content: "inline*",
    group: "block",
    parseDOM: [{ tag: "p" }],
    toDOM: () => ["p", 0],
  },
  heading: {
    content: "inline*",
    group: "block",
    defining: true,
    parseDOM: [1, 2, 3, 4, 5, 6].map((level) => ({ tag: `h${level}`, attrs: { level } })),
    toDOM: (node) => [`h${node.attrs.level}`, 0],
  },
  blockquote: {
    content: "block+",
    group: "block",
    defining: true,
    parseDOM: [{ tag: "blockquote" }],
    toDOM: () => ["blockquote", 0],
  },
  bullet_list: {
    content: "list_item+",
    group: "block",
    parseDOM: [{ tag: "ul", getAttrs: (dom) => ({ tight: tightFromDOM(dom) }) }],
    toDOM: (node) => ["ul", { "data-tight": String(node.attrs.tight) }, 0],
  },
  ordered_list: {
    content: "list_item+",
    group: "block",
    parseDOM: [{ tag: "ol", getAttrs: (dom) => ({ start: startFromDOM(dom), tight: tightFromDOM(dom) }) }],
    toDOM: (node) => [
      "ol",
      { start: node.attrs.start === 1 ? null : node.attrs.start, "data-tight": String(node.attrs.tight) },
      0,
    ],
  },
  list_item: {
    content: "block+",
    defining: true,
    parseDOM: [{ tag: "li", getAttrs: (dom) => ({ checked: checkedFromDOM(dom) }) }],
    toDOM: (node) => {
      if (node.attrs.checked === null) return ["li", 0];
      const box = { type: "checkbox", class: "task-list-item-checkbox", contenteditable: "false" };
      if (node.attrs.checked) box.checked = "";
      return ["li", { class: "task-list-item" }, ["input", box], ["div", 0]];
    },
  },
  code_block: {
    content: "text*",
    marks: "",
    group: "block",
    code: true,
    defining: true,
    parseDOM: [{ tag: "pre", preserveWhitespace: "full", getAttrs: (dom) => ({ language: languageFromDOM(dom) }) }],
    toDOM: (node) => ["pre", { "data-language": node.attrs.language || null }, ["code", 0]],
  },
  horizontal_rule: {
    group: "block",
    parseDOM: [{ tag: "hr" }],
    toDOM: () => ["hr"],
  },
  table: tables.table,
  // prosemirror-tables allows empty rows ("*"); docschema requires a cell.
  table_row: { ...tables.table_row, content: "(table_cell | table_header)+" },
  table_header: tables.table_header,
  table_cell: tables.table_cell,
  // No parseDOM: front matter is only valid as the first node, so a pasted copy
  // arrives as a code block instead.
  front_matter: {
    atom: true,
    toDOM: (node) => ["pre", { class: "md-protected md-front-matter" }, node.attrs.source],
  },
  html_block: {
    group: "block",
    atom: true,
    parseDOM: [{ tag: "div.md-html-block", getAttrs: (dom) => ({ source: dom.getAttribute("data-source") ?? "" }) }],
    toDOM: (node) => [
      "div",
      { class: "md-protected md-html-block", "data-source": node.attrs.source },
      ["pre", node.attrs.source],
    ],
  },
  footnote_def: {
    atom: true,
    parseDOM: [{
      tag: "div.md-footnote-def[data-label]",
      getAttrs: (dom) => dom.getAttribute("data-label")
        ? { label: dom.getAttribute("data-label"), source: dom.getAttribute("data-source") ?? "" }
        : false,
    }],
    toDOM: (node) => [
      "div",
      { class: "md-protected md-footnote-def", "data-label": node.attrs.label, "data-source": node.attrs.source },
      ["pre", node.attrs.source],
    ],
  },
  text: { group: "inline" },
  hard_break: {
    inline: true,
    group: "inline",
    selectable: false,
    // Turning a paragraph into a code block makes its hard breaks newlines, and back.
    linebreakReplacement: true,
    parseDOM: [{ tag: "br" }],
    toDOM: () => ["br"],
  },
  image: {
    inline: true,
    group: "inline",
    draggable: true,
    parseDOM: [{ tag: "img[src]", getAttrs: imageFromDOM }],
    toDOM: (node) => [
      "img",
      { src: node.attrs.display_src, "data-src": node.attrs.src, alt: node.attrs.alt, title: node.attrs.title },
    ],
  },
  footnote_ref: {
    inline: true,
    group: "inline",
    atom: true,
    parseDOM: [{
      tag: "sup.md-footnote-ref[data-label]",
      getAttrs: (dom) => (dom.getAttribute("data-label") ? { label: dom.getAttribute("data-label") } : false),
    }],
    toDOM: (node) => ["sup", { class: "md-chip md-footnote-ref", "data-label": node.attrs.label }, node.attrs.label],
  },
  html_inline: {
    inline: true,
    group: "inline",
    atom: true,
    // Above the code mark's <code> rule, which would otherwise win.
    parseDOM: [{ tag: "code.md-html-inline", priority: 60, getAttrs: (dom) => ({ source: dom.textContent }) }],
    toDOM: (node) => ["code", { class: "md-chip md-html-inline" }, node.attrs.source],
  },
};

// Mark specs in CONTRACT order: ProseMirror sorts a node's marks by this rank, and
// docmodel emits them in docschema.MARKS order.
const marks = {
  strong: {
    parseDOM: [
      { tag: "strong" },
      // Google Docs wraps whole pastes in <b style="font-weight: normal">.
      { tag: "b", getAttrs: (dom) => dom.style.fontWeight !== "normal" && null },
      { style: "font-weight", getAttrs: (value) => /^(bold(er)?|[5-9]\d{2,})$/.test(value) && null },
    ],
    toDOM: () => ["strong", 0],
  },
  em: {
    parseDOM: [{ tag: "em" }, { tag: "i" }, { style: "font-style=italic" }],
    toDOM: () => ["em", 0],
  },
  strike: {
    parseDOM: [{ tag: "del" }, { tag: "s" }, { tag: "strike" }, { style: "text-decoration=line-through" }],
    toDOM: () => ["del", 0],
  },
  code: {
    parseDOM: [{ tag: "code" }],
    toDOM: () => ["code", 0],
  },
  link: {
    inclusive: false,
    parseDOM: [{
      tag: "a[href]",
      getAttrs: (dom) => (isSafeUrl(dom.getAttribute("href"))
        ? { href: dom.getAttribute("href"), title: dom.getAttribute("title") }
        : false),
    }],
    toDOM: (mark) => ["a", { href: isSafeUrl(mark.attrs.href) ? mark.attrs.href : null, title: mark.attrs.title }, 0],
  },
};

function withContractAttrs(specs, contract, what) {
  if (Object.keys(specs).join() !== Object.keys(contract).join()) {
    throw new Error(`schema.js: ${what} differ from CONTRACT`);
  }
  for (const [name, spec] of Object.entries(specs)) {
    const attrs = {};
    for (const attr of contract[name]) attrs[attr] = attr in ATTR_DEFAULTS ? { default: ATTR_DEFAULTS[attr] } : {};
    if (what === "nodes" && TOP_LEVEL.has(name)) attrs.line = { default: null };
    // Table cells keep the extra attrs prosemirror-tables declares (colspan, rowspan, colwidth).
    specs[name] = { ...spec, attrs: { ...attrs, ...spec.attrs } };
  }
  return specs;
}

export const schema = new Schema({
  nodes: withContractAttrs(nodes, { ...CONTRACT.blockNodes, ...CONTRACT.inlineNodes }, "nodes"),
  marks: withContractAttrs(marks, CONTRACT.marks, "marks"),
});
