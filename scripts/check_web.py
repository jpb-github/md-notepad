"""Offscreen check of the committed web editor: page shell, bundle, QWebChannel, CSP.

Run: .venv\\Scripts\\python scripts\\check_web.py  ->  prints WEB OK or the failed checks.
Loads mdviewer/web/editor.html from a temp folder (as RichView will), with an inline
<script> probe added: the CSP must block the probe while the external scripts run.
Run it after every scripts/build_web.py.
"""

import base64
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QEventLoop, QObject, QUrl, Slot  # noqa: E402
from PySide6.QtWebChannel import QWebChannel  # noqa: E402
from PySide6.QtWebEngineCore import QWebEnginePage  # noqa: E402
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from mdviewer.core import docschema, render  # noqa: E402
from mdviewer.core.completion import FENCE_LANGUAGES  # noqa: E402

WEB = Path(__file__).resolve().parent.parent / "mdviewer" / "web"
RUNTIME_FILES = ("editor.js", "editor.css", "qwebchannel.js")
THEME_SLOT = "/*@THEME_CSS@*/"
FIRST_SCRIPT = '<script src="qwebchannel.js"></script>'
INLINE_PROBE = "<script>window.inlineScriptRan = true;</script>"
READY_TIMEOUT_S = 5  # spec: page ready() timeout
FAILURES: list[str] = []


def check(condition, label: str) -> None:
    if not condition:
        FAILURES.append(label)


class Bridge(QObject):
    def __init__(self):
        super().__init__()
        self.ready_calls = 0

    @Slot()
    def ready(self) -> None:
        self.ready_calls += 1


class Page(QWebEnginePage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.console: list[str] = []

    def javaScriptConsoleMessage(self, level, message, line, source) -> None:
        self.console.append(message)


def pump(app: QApplication, predicate, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while not predicate() and time.monotonic() < deadline:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
    return bool(predicate())


def run_js(app: QApplication, view: QWebEngineView, script: str):
    """Evaluates `script` in the page's main world; the value must be JSON-serializable."""
    box: list = []
    view.page().runJavaScript(f"JSON.stringify({script})", 0, box.append)
    pump(app, lambda: box, 3)
    return json.loads(box[0]) if box and box[0] is not None else None


def build_page(folder: Path) -> Path:
    for name in RUNTIME_FILES:
        shutil.copy2(WEB / name, folder / name)
    shell = (WEB / "editor.html").read_text(encoding="utf-8")
    check(shell.count(THEME_SLOT) == 1 and shell.count(FIRST_SCRIPT) == 1, "editor.html has the expected slots")
    shell = shell.replace(THEME_SLOT, render.page_css("light"))
    shell = shell.replace(FIRST_SCRIPT, INLINE_PROBE + FIRST_SCRIPT)
    page_file = folder / "editor.html"
    page_file.write_text(shell, encoding="utf-8")
    return page_file


# --- Task 8: schema and node views ----------------------------------------------------------

# Attrs the JS schema declares beyond docschema: prosemirror-tables needs them on cells.
CELL_EXTRAS = ("colspan", "rowspan", "colwidth")
PNG_1PX = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGD4DwAB"
    "BAEAwS2OUAAAAABJRU5ErkJggg=="
)
# Raw HTML: pixel.png (written next to the page by check_editor) must load in the frame;
# the script and the error handler would post a message if they ever ran.
HTML_SOURCE = (
    '<div id="raw">raw <b>html</b></div>\n<img src="pixel.png" height="120">\n'
    "<script>parent.postMessage('script ran', '*')</script>\n"
    "<img src=\"missing.png\" onerror=\"parent.postMessage('handler ran', '*')\">"
)
HIGHLIGHT = '<span class="k">pass</span>'
CODE_INDEX = 6  # top-level index of the highlighted code block in every_node_doc()

# Per node type: [attr names, child types its content can hold, content may be empty];
# per inline-content type: the marks it allows; and the marks in rank order.
SCHEMA_SHAPE_JS = """(() => {
  const schema = window.mdEditor.schema;
  const nodes = {};
  for (const type of Object.values(schema.nodes)) {
    const children = new Set(), seen = new Set(), todo = [type.contentMatch];
    while (todo.length) {
      const match = todo.pop();
      if (seen.has(match)) continue;
      seen.add(match);
      for (let i = 0; i < match.edgeCount; i++) {
        children.add(match.edge(i).type.name);
        todo.push(match.edge(i).next);
      }
    }
    nodes[type.name] = [Object.keys(type.spec.attrs || {}).sort(), [...children].sort(), type.contentMatch.validEnd];
  }
  const marks = Object.keys(schema.marks);
  const marked = Object.values(schema.nodes).filter((type) => type.inlineContent)
    .map((type) => [type.name, marks.filter((mark) => type.allowsMarkType(schema.marks[mark]))]);
  return { nodes, marks, marked: Object.fromEntries(marked) };
})()"""


def every_node_doc() -> dict:
    """Every node and mark, written exactly as ProseMirror's toJSON() returns it."""
    def text(value, *marks):
        node = {"type": "text", "text": value}
        if marks:
            node["marks"] = list(marks)
        return node

    def para(*inline, line=None):
        node = {"type": "paragraph", "attrs": {"line": line}}
        if inline:
            node["content"] = list(inline)
        return node

    def item(*blocks, checked=None):
        return {"type": "list_item", "attrs": {"checked": checked}, "content": list(blocks)}

    def cell(kind, align, *inline):
        node = {"type": kind, "attrs": {"align": align}}
        if inline:
            node["content"] = list(inline)
        return node

    link = {"type": "link", "attrs": {"href": "https://example.com", "title": "Example"}}
    return {"type": "doc", "content": [
        {"type": "front_matter", "attrs": {"source": "---\ntitle: x\n---\n", "line": 1}},
        {"type": "heading", "attrs": {"level": 2, "line": 5}, "content": [text("Title")]},
        para(
            text("all", {"type": "strong"}, {"type": "em"}, {"type": "strike"}, {"type": "code"}, link),
            text(" plain "),
            {"type": "hard_break"},
            {"type": "image", "attrs": {"src": "pixel.png", "display_src": PNG_1PX, "alt": "pixel", "title": None},
             "marks": [link]},
            {"type": "image",
             "attrs": {"src": "gone.png", "display_src": "file:///nowhere/gone.png", "alt": "Gone", "title": "t"}},
            {"type": "footnote_ref", "attrs": {"label": "1"}},
            {"type": "html_inline", "attrs": {"source": "<kbd>"}},
            line=7,
        ),
        {"type": "blockquote", "attrs": {"line": 9}, "content": [para(text("quoted"))]},
        {"type": "bullet_list", "attrs": {"tight": True, "line": 11}, "content": [
            item(para(text("one"))),
            item(para(text("done")), {"type": "ordered_list", "attrs": {"start": 0, "tight": False, "line": None},
                                      "content": [item(para(), checked=False)]}, checked=True),
        ]},
        {"type": "ordered_list", "attrs": {"start": 3, "tight": True, "line": 14}, "content": [
            item({"type": "code_block", "attrs": {"language": "", "highlight": "", "line": None},
                  "content": [text("first block is code")]}),
        ]},
        {"type": "code_block", "attrs": {"language": "python", "highlight": HIGHLIGHT, "line": 16},
         "content": [text("pass")]},
        {"type": "code_block", "attrs": {"language": "", "highlight": "", "line": 19}},
        {"type": "horizontal_rule", "attrs": {"line": 21}},
        {"type": "table", "attrs": {"line": 23}, "content": [
            {"type": "table_row", "content": [cell("table_header", "left", text("h")), cell("table_header", None)]},
            {"type": "table_row", "content": [cell("table_cell", "right", text("c", {"type": "em"})),
                                              cell("table_cell", "center")]},
        ]},
        {"type": "html_block", "attrs": {"source": HTML_SOURCE, "line": 27}},
        para(line=31),
        {"type": "footnote_def", "attrs": {"label": "1", "source": "[^1]: note", "line": 33}},
    ]}


def without_cell_extras(node):
    """`node` without prosemirror-tables' cell attrs (Task 9's getDocument removes them itself)."""
    if isinstance(node, list):
        return [without_cell_extras(child) for child in node]
    if not isinstance(node, dict):
        return node
    copy = {key: without_cell_extras(value) for key, value in node.items()}
    if copy.get("type") in ("table_header", "table_cell"):
        copy["attrs"] = {key: value for key, value in copy["attrs"].items() if key not in CELL_EXTRAS}
    return copy


def without_lines_and_highlight(node):
    """`node` as a paste rebuilds it: no source lines, no precomputed highlight."""
    if isinstance(node, list):
        return [without_lines_and_highlight(child) for child in node]
    if not isinstance(node, dict):
        return node
    copy = {key: without_lines_and_highlight(value) for key, value in node.items()}
    attrs = copy.get("attrs")
    if isinstance(attrs, dict):
        copy["attrs"] = {**attrs}
        if docschema.LINE_ATTR in attrs:
            copy["attrs"][docschema.LINE_ATTR] = None
        if "highlight" in attrs:
            copy["attrs"]["highlight"] = ""
    return copy


def expected_schema_shape() -> dict:
    nodes = {}
    for name, attrs in {**docschema.BLOCK_NODES, **docschema.INLINE_NODES}.items():
        names = set(attrs)
        if name in docschema.TOP_LEVEL_NODES:
            names.add(docschema.LINE_ATTR)
        if name in ("table_header", "table_cell"):
            names.update(CELL_EXTRAS)
        allowed, minimum = docschema.CONTENT.get(name, (frozenset(), 0))
        nodes[name] = [sorted(names), sorted(allowed), minimum == 0]
    marked = {
        name: [] if name == "code_block" else list(docschema.MARKS)
        for name, (allowed, _) in docschema.CONTENT.items()
        if allowed <= set(docschema.INLINE_NODES)
    }
    return {"nodes": nodes, "marks": list(docschema.MARKS), "marked": marked}


def set_doc(app: QApplication, view: QWebEngineView, doc: dict) -> None:
    run_js(app, view, f"(window.mdEditor.setDocument({json.dumps(doc)}), 0)")


def get_doc(app: QApplication, view: QWebEngineView):
    return without_cell_extras(run_js(app, view, "window.mdEditor.getDocument()"))


def code_block_state(app: QApplication, view: QWebEngineView) -> dict:
    """DOM state of the second code block, the highlighted one at CODE_INDEX."""
    return run_js(app, view, f"""(() => {{
      const block = document.querySelectorAll('#editor .md-code-block')[1];
      return {{
        classes: [...block.classList].sort(),
        overlay: getComputedStyle(block.querySelector('.md-code-highlight')).display,
        keyword: block.querySelector('.md-code-highlight span.k')?.textContent ?? null,
        language: block.querySelector('input.md-code-language').value,
        highlight: window.mdEditor.getDocument().content[{CODE_INDEX}].attrs.highlight,
      }};
    }})()""")


def check_editor(app: QApplication, view: QWebEngineView, folder: Path) -> None:
    if not run_js(app, view, "Boolean(window.mdEditor && window.mdEditor.schema && window.mdEditor.setDocument)"):
        check(False, "window.mdEditor exposes schema and setDocument")
        return
    (folder / "pixel.png").write_bytes(base64.b64decode(PNG_1PX.split(",", 1)[1]))
    check(run_js(app, view, SCHEMA_SHAPE_JS) == expected_schema_shape(),
          "JS schema: names, attrs, content rules and mark ranks match core/docschema.py")

    run_js(app, view, "(window.frameMessages = [], addEventListener('message', (e) => frameMessages.push(e.data)), 0)")
    doc = every_node_doc()
    check(docschema.validate(without_cell_extras(doc)) == [], "the every-node document is valid in Python")
    set_doc(app, view, doc)
    check(get_doc(app, view) == doc, "every node type comes back unchanged from setDocument/getDocument")
    check(run_js(app, view, "window.mdEditor.events.length") == 0, "loading a document sends no events")

    # Code block: highlight overlay while the caret is elsewhere, plain text inside, cleared on edit.
    state = code_block_state(app, view)
    check("md-has-highlight" in state["classes"] and "md-code-active" not in state["classes"]
          and state["overlay"] == "block" and state["keyword"] == "pass" and state["language"] == "python",
          f"code block shows the Python highlight while the caret is outside ({state})")
    run_js(app, view, f"(window.mdEditor.focusBlock({CODE_INDEX}), 0)")
    state = code_block_state(app, view)
    check("md-code-active" in state["classes"] and state["overlay"] == "none",
          f"code block shows plain text while the caret is inside ({state})")
    run_js(app, view, "(window.mdEditor.focusBlock(1), 0)")
    check(code_block_state(app, view)["overlay"] == "block", "the highlight comes back when the caret leaves")
    run_js(app, view, "(window.mdEditor.view.dispatch(window.mdEditor.view.state.tr.insertText('y', 2)), 0)")
    check(get_doc(app, view)["content"][1]["content"][0]["text"] == "yTitle"
          and code_block_state(app, view)["highlight"] == HIGHLIGHT,
          "typing outside a code block keeps its highlight")
    run_js(app, view, f"""(window.mdEditor.focusBlock({CODE_INDEX}),
        window.mdEditor.view.dispatch(window.mdEditor.view.state.tr.insertText('x')), 0)""")
    state = code_block_state(app, view)
    check(state["highlight"] == "" and "md-has-highlight" not in state["classes"],
          f"typing in a code block clears its highlight ({state})")

    set_doc(app, view, doc)
    run_js(app, view, """(() => {
      const field = document.querySelectorAll('#editor .md-code-block')[1].querySelector('input');
      field.value = '  rust extra`';
      field.dispatchEvent(new Event('change'));
      return 0;
    })()""")
    block = get_doc(app, view)["content"][CODE_INDEX]["attrs"]
    check(block["language"] == "rust" and block["highlight"] == "",
          f"the language field sets a cleaned language and clears the highlight ({block})")
    check(run_js(app, view, "document.querySelectorAll('datalist#md-fence-languages option').length")
          == len(FENCE_LANGUAGES), "the language field offers the fence languages")

    set_doc(app, view, {"type": "doc", "content": [
        {"type": "code_block", "attrs": {"language": "x", "highlight": '<img src="x">', "line": None},
         "content": [{"type": "text", "text": "x"}]}]})
    check(run_js(app, view, "document.querySelector('#editor .md-code-block.md-has-highlight') === null"),
          "highlight markup other than <span class> is not shown")

    # Images: a loaded image shows display_src; a missing one shows its alt text.
    set_doc(app, view, doc)
    pump(app, lambda: run_js(app, view, "document.querySelector('#editor .md-image-broken') !== null"), 3)
    images = run_js(app, view, """[...document.querySelectorAll('#editor .md-image')].map((span) => {
      const img = span.querySelector('img');
      return img ? ['img', img.naturalWidth, img.dataset.src] : ['broken', span.textContent, span.firstChild.title];
    })""")
    check(images == [["img", 1, "pixel.png"], ["broken", "Gone", "gone.png"]], f"image node views ({images})")

    # Raw HTML: same-origin sandbox without scripts, fitted to its content, nothing in it runs.
    fitted = """(() => {
      const frame = document.querySelector('#editor .md-html-block iframe');
      const root = frame.contentDocument?.documentElement;
      return root ? [frame.offsetHeight, Math.ceil(root.getBoundingClientRect().height),
                     frame.contentDocument.images[0]?.naturalWidth ?? 0] : null;
    })()"""
    pump(app, lambda: (run_js(app, view, fitted) or [0, 1, 0])[2] == 1, 3)
    pump(app, lambda: False, 0.3)  # the error handler and the fit after "load" would have run by now
    frame = run_js(app, view, """(() => {
      const frame = document.querySelector('#editor .md-html-block iframe');
      return [frame.getAttribute('sandbox'), frame.srcdoc.includes('<div id="raw">'),
              document.querySelector('#editor .md-html-block .md-shield') !== null];
    })()""")
    check(frame == ["allow-same-origin", True, True],
          f"html_block renders in a script-less sandboxed iframe behind a shield ({frame})")
    size = run_js(app, view, fitted)
    check(size is not None and size[0] == size[1] and size[0] >= 120 and size[2] == 1,
          f"the raw HTML frame loads local images and fits its content ([height, content, image] = {size})")
    check(run_js(app, view, "window.frameMessages") == [], "scripts and handlers in raw HTML never run")
    check(run_js(app, view, "document.querySelector('#editor #raw, #editor script') === null"),
          "raw HTML never enters the editor DOM")

    # Double-click on protected nodes reports the top-level block index.
    run_js(app, view, """(() => {
      const hit = (selector) => document.querySelector('#editor ' + selector)
        .dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true }));
      ['.md-front-matter', '.md-html-inline', '.md-html-block .md-shield', '.md-footnote-def'].forEach(hit);
      return 0;
    })()""")
    events = run_js(app, view, "window.mdEditor.events")
    check(events == [["editProtected", 0], ["editProtected", 2], ["editProtected", 10], ["editProtected", 12]],
          f"double-click on protected nodes ({events})")

    # Copy and paste inside the editor keeps every node (front matter aside: it is only valid first).
    body = {"type": "doc", "content": doc["content"][1:]}
    set_doc(app, view, body)
    run_js(app, view, """(() => {
      const view = window.mdEditor.view;
      const html = view.serializeForClipboard(view.state.doc.slice(0, view.state.doc.content.size)).dom.innerHTML;
      window.mdEditor.setDocument({ type: 'doc', content: [{ type: 'paragraph' }] });
      view.pasteHTML(html);
      return 0;
    })()""")
    check(get_doc(app, view) == without_lines_and_highlight(body),
          "copy and paste inside the editor keeps every node (line and highlight reset)")

    # Pasted HTML from elsewhere: unsafe URLs are dropped, GitHub markup is read.
    set_doc(app, view, {"type": "doc", "content": [{"type": "paragraph"}]})
    run_js(app, view, """(window.mdEditor.view.pasteHTML(
      '<p><a href="java\tscript:alert(1)">bad</a> <a href="https://ok.example/">ok</a>' +
      '<img src="javascript:x" alt="no"><img src="data:text/html,x" alt="no2"></p>' +
      '<ul><li class="task-list-item"><input type="checkbox" class="task-list-item-checkbox" checked> t</li></ul>' +
      '<pre><code class="language-go">x</code></pre><table><tr><th align="center">h</th></tr></table>'), 0)""")
    pasted = get_doc(app, view)["content"]
    para = {"type": "paragraph", "attrs": {"line": None}}
    check(pasted == [
        {**para, "content": [
            {"type": "text", "text": "bad "},
            {"type": "text", "text": "ok",
             "marks": [{"type": "link", "attrs": {"href": "https://ok.example/", "title": None}}]},
        ]},
        {"type": "bullet_list", "attrs": {"tight": True, "line": None}, "content": [
            {"type": "list_item", "attrs": {"checked": True},
             "content": [{**para, "content": [{"type": "text", "text": "t"}]}]},
        ]},
        {"type": "code_block", "attrs": {"language": "go", "highlight": "", "line": None},
         "content": [{"type": "text", "text": "x"}]},
        {"type": "table", "attrs": {"line": None}, "content": [{"type": "table_row", "content": [
            {"type": "table_header", "attrs": {"align": "center"}, "content": [{"type": "text", "text": "h"}]},
        ]}]},
    ], f"pasted HTML: unsafe URLs dropped, task box, code language and cell align kept ({pasted})")


def main() -> int:
    app = QApplication([])
    folder = Path(tempfile.mkdtemp(prefix="mdviewer-webcheck-"))
    view = QWebEngineView()
    page = Page(view)
    view.setPage(page)
    channel = QWebChannel(page)
    bridge = Bridge()
    channel.registerObject("bridge", bridge)
    page.setWebChannel(channel)

    view.load(QUrl.fromLocalFile(str(build_page(folder))))
    check(pump(app, lambda: bridge.ready_calls > 0, READY_TIMEOUT_S), "bridge.ready() received within 5 s")
    pump(app, lambda: False, 0.3)  # a duplicate ready() would arrive by now
    check(bridge.ready_calls == 1, f"ready() called exactly once (got {bridge.ready_calls})")

    check(run_js(app, view, "window.inlineScriptRan === true") is False, "CSP blocks the inline <script>")
    check(
        any("Content Security Policy" in message for message in page.console),
        "the inline <script> was refused by the CSP (console message)",
    )
    check(
        run_js(app, view, "document.querySelector('#editor .ProseMirror').contentEditable") == "true",
        "ProseMirror is mounted and editable",
    )
    check(
        run_js(app, view, "getComputedStyle(document.querySelector('.ProseMirror')).whiteSpace")
        in ("pre-wrap", "break-spaces"),
        "editor.css is loaded",
    )
    background = run_js(app, view, "getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()")
    check(
        (background or "").lower() == render.PAGE_BACKGROUND["light"].lower(),
        f"theme CSS filled into the slot (--bg = {background!r})",
    )
    doc = run_js(app, view, "window.mdEditor.getDocument()")
    check(isinstance(doc, dict) and doc.get("type") == "doc", f"mdEditor.getDocument() returns a doc ({doc!r})")
    check_editor(app, view, folder)

    console = list(page.console)
    del page, view  # the page is the view's child; release both before removing the folder
    shutil.rmtree(folder, ignore_errors=True)
    if FAILURES:
        print("WEB CHECK FAILED:")
        for label in FAILURES:
            print("  -", label)
        for message in console:
            print("  console:", message)
        return 1
    print("WEB OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
