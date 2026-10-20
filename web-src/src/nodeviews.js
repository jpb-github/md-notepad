// Node views and display plugins of the Rendered editor: code blocks (Pygments
// highlight from Python, language field), images (broken-image placeholder), raw HTML
// blocks (sandboxed iframe) and double-click on protected nodes.
import { Plugin } from "prosemirror-state";
import { Decoration, DecorationSet } from "prosemirror-view";
import { cleanLanguage, isSafeUrl } from "./schema.js";

// Must equal mdviewer/core/completion.py FENCE_LANGUAGES (tests/test_web_assets.py).
export const FENCE_LANGUAGES = [
  "python", "bash", "powershell", "javascript", "typescript", "json",
  "yaml", "xml", "html", "css", "c", "cpp", "csharp", "go", "rust",
  "java", "sql", "toml", "text"
];
const LANGUAGE_LIST_ID = "md-fence-languages";

function element(tag, className) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  return node;
}

// The page has one <datalist> of fence languages, shared by every code block's field.
function languageList() {
  let list = document.getElementById(LANGUAGE_LIST_ID);
  if (!list) {
    list = element("datalist");
    list.id = LANGUAGE_LIST_ID;
    for (const language of FENCE_LANGUAGES) list.append(new Option(language));
    document.body.append(list);
  }
  return list.id;
}

// The highlight attr comes from Python (render.highlight_code): <span class> markup
// only. Anything else is not shown, so a malformed attr cannot inject elements.
function highlightFragment(markup) {
  if (!markup) return null;
  const template = element("template");
  template.innerHTML = markup;
  for (const node of template.content.querySelectorAll("*")) {
    if (node.tagName !== "SPAN" || [...node.attributes].some((attr) => attr.name !== "class")) return null;
  }
  return template.content;
}

// Index of the top-level block that contains document position `pos`.
function topLevelIndex(state, pos) {
  return state.doc.resolve(pos).index(0);
}

class CodeBlockView {
  constructor(node, view, getPos) {
    this.node = node;
    this.view = view;
    this.getPos = getPos;
    this.dom = element("div", "md-code-block");
    this.tools = element("div", "md-code-tools");
    this.tools.contentEditable = "false";
    this.language = element("input", "md-code-language");
    this.language.type = "text";
    this.language.placeholder = "language";
    this.language.spellcheck = false;
    this.language.setAttribute("list", languageList());
    this.language.addEventListener("change", () => this.commitLanguage());
    this.language.addEventListener("keydown", (event) => this.languageKey(event));
    this.tools.append(this.language);
    const source = element("pre", "md-code-source");
    this.contentDOM = element("code");
    source.append(this.contentDOM);
    // Highlighted copy of the text, laid over the source while the caret is elsewhere.
    // Clicks go through it to the source text (pointer-events: none in editor.css).
    this.overlay = element("pre", "highlight md-code-highlight");
    this.overlay.setAttribute("aria-hidden", "true");
    this.overlayCode = element("code");
    this.overlay.append(this.overlayCode);
    this.dom.append(this.tools, source, this.overlay);
    this.shownHighlight = null;
    this.render();
  }

  render() {
    const { language, highlight } = this.node.attrs;
    if (document.activeElement !== this.language) this.language.value = language;
    if (highlight !== this.shownHighlight) {
      this.shownHighlight = highlight;
      const fragment = highlightFragment(highlight);
      this.overlayCode.replaceChildren(...(fragment ? [fragment] : []));
      this.dom.classList.toggle("md-has-highlight", fragment !== null);
    }
  }

  update(node) {
    if (node.type !== this.node.type) return false;
    this.node = node;
    this.render();
    return true;
  }

  commitLanguage() {
    const language = cleanLanguage(this.language.value);
    this.language.value = language;
    const pos = this.getPos();
    if (pos === undefined || language === this.node.attrs.language) return;
    // The highlight belongs to the old language: drop it (Python recomputes it on the next load).
    this.view.dispatch(this.view.state.tr.setNodeMarkup(pos, null, { ...this.node.attrs, language, highlight: "" }));
  }

  languageKey(event) {
    if (event.key === "Enter") {
      event.preventDefault();
      this.commitLanguage();
      this.view.focus();
    } else if (event.key === "Escape") {
      event.preventDefault();
      this.language.value = this.node.attrs.language;
      this.view.focus();
    }
  }

  // Keys and clicks in the language field belong to the field, not to ProseMirror.
  stopEvent(event) {
    return this.tools.contains(event.target);
  }

  ignoreMutation(mutation) {
    if (this.tools.contains(mutation.target) || this.overlay.contains(mutation.target)) return true;
    return mutation.type !== "selection" && !this.contentDOM.contains(mutation.target);
  }
}

class ImageView {
  constructor(node) {
    this.node = node;
    this.dom = element("span", "md-image");
    this.render();
  }

  render() {
    const { src, display_src: displaySrc, alt, title } = this.node.attrs;
    if (!isSafeUrl(displaySrc)) {
      this.showBroken();
      return;
    }
    const img = element("img");
    img.alt = alt;
    if (title !== null) img.title = title;
    img.addEventListener("error", () => this.showBroken(), { once: true });
    img.src = displaySrc;
    img.setAttribute("data-src", src);
    this.dom.replaceChildren(img);
  }

  // `src` is never rewritten: the placeholder only shows the alt text (or the path).
  showBroken() {
    const box = element("span", "md-image-broken");
    box.textContent = this.node.attrs.alt || this.node.attrs.src || "image";
    box.title = this.node.attrs.src;
    this.dom.replaceChildren(box);
  }

  update(node) {
    if (node.type !== this.node.type) return false;
    const changed = ["src", "display_src", "alt", "title"].some((name) => node.attrs[name] !== this.node.attrs[name]);
    this.node = node;
    if (changed) this.render();
    return true;
  }

  ignoreMutation() {
    return true;
  }
}

// Raw HTML is shown in an iframe built from srcdoc whose sandbox allows same-origin
// access but no scripts: nothing in it runs, and the editor can read the frame's
// content height to fit it. A transparent shield on top takes the clicks, so the
// block is selected and double-clicked like the other protected blocks and links
// inside it are not followed.
const frames = new Set();

// Theme colors for the frame document; refreshFrames() re-applies them after a theme change.
function frameDocument(source) {
  const css = getComputedStyle(document.documentElement);
  const color = (name) => css.getPropertyValue(name).trim();
  return '<!DOCTYPE html><html><head><meta charset="utf-8"><style>'
    + `html,body{margin:0;background:transparent;color:${color("--fg")}}`
    + 'body{font:16px/1.5 "Segoe UI","Noto Sans",Helvetica,Arial,sans-serif;padding:8px 12px}'
    + `a{color:${color("--link")}}img{max-width:100%}`
    + `</style></head><body>${source}</body></html>`;
}

class HtmlBlockView {
  constructor(node) {
    this.node = node;
    this.dom = element("div", "md-protected md-html-block");
    this.dom.title = "Raw HTML. Double-click to edit it in Source mode.";
    this.frame = element("iframe");
    this.frame.setAttribute("sandbox", "allow-same-origin");
    this.frame.setAttribute("tabindex", "-1");
    // "load" fires after the frame's images; the observer refits when the width changes.
    this.frame.addEventListener("load", () => this.fit());
    this.resizer = new ResizeObserver(() => this.fit());
    this.resizer.observe(this.dom);
    this.dom.append(this.frame, element("div", "md-shield"));
    frames.add(this);
    this.render();
  }

  render() {
    this.frame.srcdoc = frameDocument(this.node.attrs.source);
  }

  fit() {
    const root = this.frame.contentDocument?.documentElement;
    if (root) this.frame.style.height = `${Math.ceil(root.getBoundingClientRect().height)}px`;
  }

  update(node) {
    if (node.type !== this.node.type) return false;
    const changed = node.attrs.source !== this.node.attrs.source;
    this.node = node;
    if (changed) this.render();
    return true;
  }

  ignoreMutation() {
    return true;
  }

  destroy() {
    frames.delete(this);
    this.resizer.disconnect();
  }
}

// Task 9's setTheme calls this after swapping the theme stylesheet.
export function refreshFrames() {
  for (const view of frames) view.render();
}

export function createNodeViews() {
  return {
    code_block: (node, view, getPos) => new CodeBlockView(node, view, getPos),
    image: (node) => new ImageView(node),
    html_block: (node) => new HtmlBlockView(node),
  };
}

// Marks the code block that holds the selection: CSS then shows its plain text
// instead of the highlight overlay.
const activeCodePlugin = new Plugin({
  props: {
    decorations(state) {
      const { $from, $to } = state.selection;
      const found = [];
      for (const $pos of [$from, $to]) {
        for (let depth = $pos.depth; depth > 0; depth--) {
          if ($pos.node(depth).type.name === "code_block") {
            const start = $pos.before(depth);
            if (!found.some((d) => d.from === start)) {
              found.push(Decoration.node(start, start + $pos.node(depth).nodeSize, { class: "md-code-active" }));
            }
          }
        }
      }
      return found.length ? DecorationSet.create(state.doc, found) : null;
    },
  },
});

// Clears `highlight` on every code block inside the changed range: the markup no
// longer matches the text (or language) and Python recomputes it on the next load.
const staleHighlightPlugin = new Plugin({
  appendTransaction(transactions, oldState, newState) {
    if (!transactions.some((tr) => tr.docChanged)) return null;
    const start = oldState.doc.content.findDiffStart(newState.doc.content);
    if (start === null) return null;
    const end = Math.max(start, oldState.doc.content.findDiffEnd(newState.doc.content).b);
    const tr = newState.tr;
    newState.doc.nodesBetween(start, end, (node, pos) => {
      if (node.type.name === "code_block" && node.attrs.highlight) {
        tr.setNodeMarkup(pos, null, { ...node.attrs, highlight: "" });
      }
    });
    return tr.docChanged ? tr : null;
  },
});

// Double-click on a protected block or chip asks Python to show it in Source mode.
// callbacks.editProtected(index) receives the index of the enclosing top-level block.
function protectedPlugin(callbacks) {
  return new Plugin({
    props: {
      handleDOMEvents: {
        dblclick(view, event) {
          const target = event.target instanceof Element ? event.target.closest(".md-protected, .md-chip") : null;
          if (!target || !view.dom.contains(target)) return false;
          event.preventDefault();
          callbacks.editProtected(topLevelIndex(view.state, view.posAtDOM(target, 0)));
          return true;
        },
      },
    },
  });
}

export function displayPlugins(callbacks) {
  return [activeCodePlugin, staleHighlightPlugin, protectedPlugin(callbacks)];
}
