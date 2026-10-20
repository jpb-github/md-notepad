"""Offscreen check of the committed web editor: page shell, bundle, QWebChannel, CSP.

Run: .venv\\Scripts\\python scripts\\check_web.py  ->  prints WEB OK or the failed checks.
Loads mdviewer/web/editor.html from a temp folder (as RichView will), with an inline
<script> probe added: the CSP must block the probe while the external scripts run.
Run it after every scripts/build_web.py.
"""

import base64
import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")  # the view is shown: no GPU log noise

from PySide6.QtCore import QEventLoop, QMimeData, QObject, QPoint, Qt, QUrl, Slot  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWebChannel import QWebChannel  # noqa: E402
from PySide6.QtWebEngineCore import QWebEnginePage  # noqa: E402
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from mdviewer.core import docmodel, docschema, render, serialize  # noqa: E402
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
    """Stands in for richview.Bridge: records every call from the page as [name, *args]."""

    def __init__(self):
        super().__init__()
        self.calls: list[list] = []

    def args(self, name: str, start: int = 0) -> list:
        """Argument lists of the calls to `name` from index `start` of `calls` on."""
        return [call[1:] for call in self.calls[start:] if call[0] == name]

    @Slot()
    def ready(self) -> None:
        self.calls.append(["ready"])

    @Slot()
    def changed(self) -> None:
        self.calls.append(["changed"])

    @Slot("QVariantMap")
    def selectionState(self, state: dict) -> None:
        self.calls.append(["selectionState", state])

    @Slot(str, str)
    def requestLinkDialog(self, text: str, href: str) -> None:
        self.calls.append(["requestLinkDialog", text, href])

    @Slot()
    def requestImageDialog(self) -> None:
        self.calls.append(["requestImageDialog"])

    @Slot(str)
    def openLink(self, href: str) -> None:
        self.calls.append(["openLink", href])

    @Slot(str)
    def hoverLink(self, href: str) -> None:
        self.calls.append(["hoverLink", href])

    @Slot(int)
    def editProtected(self, index: int) -> None:
        self.calls.append(["editProtected", index])

    @Slot(int)
    def caretBlock(self, index: int) -> None:
        self.calls.append(["caretBlock", index])


class Page(QWebEnginePage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.console: list[str] = []
        self.page_url = QUrl()
        self.navigations: list[str] = []  # main-frame navigations away from the page, all refused

    def javaScriptConsoleMessage(self, level, message, line, source) -> None:
        self.console.append(message)

    def acceptNavigationRequest(self, url, nav_type, is_main_frame) -> bool:
        if is_main_frame and url != self.page_url:
            self.navigations.append(url.toString())
            return False
        return True


def pump(app: QApplication, predicate, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while not predicate() and time.monotonic() < deadline:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
    return bool(predicate())


def run_js(app: QApplication, view: QWebEngineView, script: str):
    """Evaluates `script` in the page's main world; the value must be JSON-serializable (undefined -> None)."""
    box: list = []
    view.page().runJavaScript(f"JSON.stringify(({script}) ?? null)", 0, box.append)
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
            # Columns aligned like Markdown can write them: each cell like its column's header.
            {"type": "table_row", "content": [cell("table_header", "left", text("h")), cell("table_header", "center")]},
            {"type": "table_row", "content": [cell("table_cell", "left", text("c", {"type": "em"})),
                                              cell("table_cell", "center")]},
        ]},
        {"type": "html_block", "attrs": {"source": HTML_SOURCE, "line": 27}},
        para(line=31),
        {"type": "footnote_def", "attrs": {"label": "1", "source": "[^1]: note", "line": 33}},
    ]}


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
    return run_js(app, view, "window.mdEditor.getDocument()")


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


def check_editor(app: QApplication, view: QWebEngineView, folder: Path, bridge: Bridge) -> None:
    if not run_js(app, view, "Boolean(window.mdEditor && window.mdEditor.schema && window.mdEditor.setDocument)"):
        check(False, "window.mdEditor exposes schema and setDocument")
        return
    (folder / "pixel.png").write_bytes(base64.b64decode(PNG_1PX.split(",", 1)[1]))
    check(run_js(app, view, SCHEMA_SHAPE_JS) == expected_schema_shape(),
          "JS schema: names, attrs, content rules and mark ranks match core/docschema.py")

    run_js(app, view, "(window.frameMessages = [], addEventListener('message', (e) => frameMessages.push(e.data)), 0)")
    doc = every_node_doc()
    check(docschema.validate(doc) == [], "the every-node document is valid in Python")
    mark = len(bridge.calls)
    set_doc(app, view, doc)
    check(get_doc(app, view) == doc, "every node type comes back unchanged from setDocument/getDocument")
    pump(app, lambda: False, 0.3)  # a change report would arrive by now
    check(bridge.args("changed", mark) == [], "loading a document does not report a change")

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
    mark = len(bridge.calls)
    run_js(app, view, """(() => {
      const hit = (selector) => document.querySelector('#editor ' + selector)
        .dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true }));
      ['.md-front-matter', '.md-html-inline', '.md-html-block .md-shield', '.md-footnote-def'].forEach(hit);
      return 0;
    })()""")
    pump(app, lambda: len(bridge.args("editProtected", mark)) >= 4, 3)
    events = bridge.args("editProtected", mark)
    check(events == [[0], [2], [10], [12]], f"double-click on protected nodes calls bridge.editProtected ({events})")

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


# --- Task 9: bridge and document lifecycle ---------------------------------------------------

LINK_HREF = "https://example.com/a?b=1"
# Positions in bridge_doc(): inside "plain ", inside "bold", inside "link", inside the code.
PLAIN, BOLD, LINK, CODE = 9, 16, 21, 26
TABLE_INDEX, RULE_INDEX = 3, 4
NO_UNDO = {"undo": False, "redo": False}
# Defines select(from, to = from); needs window.TextSelection (set by check_bridge).
SELECT_JS = """(window.select = (from, to = from) => {
  const view = window.mdEditor.view;
  view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, from, to)));
  return 0;
}, 0)"""


def bridge_doc() -> dict:
    """Heading, marked text and a link, code, a table, a rule and raw HTML."""
    def text(value, *marks):
        node = {"type": "text", "text": value}
        if marks:
            node["marks"] = list(marks)
        return node

    link = {"type": "link", "attrs": {"href": LINK_HREF, "title": None}}
    return {"type": "doc", "content": [
        {"type": "heading", "attrs": {"level": 2, "line": 1}, "content": [text("Title")]},
        {"type": "paragraph", "attrs": {"line": 3}, "content": [
            text("plain "), text("bold", {"type": "strong"}, {"type": "em"}), text(" "), text("link", link),
        ]},
        {"type": "code_block", "attrs": {"language": "", "highlight": "", "line": 5}, "content": [text("x = 1")]},
        {"type": "table", "attrs": {"line": 9}, "content": [{"type": "table_row", "content": [
            {"type": "table_header", "attrs": {"align": None}, "content": [text("h")]},
        ]}]},
        {"type": "horizontal_rule", "attrs": {"line": 12}},
        {"type": "html_block", "attrs": {"source": "<p>raw</p>", "line": 14}},
    ]}


def history_view(state: dict | None) -> dict | None:
    """`state` with only undo and redo in `can`: the Task 9 checks predate the formatting commands."""
    if state is None:
        return None
    return {**state, "can": {name: state["can"].get(name) for name in ("undo", "redo")}}


def latest_state(app: QApplication, bridge: Bridge) -> dict | None:
    """The last selectionState sent, once the throttle has flushed."""
    pump(app, lambda: False, 0.2)
    states = bridge.args("selectionState")
    return states[-1][0] if states else None


def mouse(selector: str, kind: str, ctrl: bool = False) -> str:
    return (f"(document.querySelector({json.dumps(selector)}).dispatchEvent(new MouseEvent({json.dumps(kind)}, "
            f"{{ bubbles: true, cancelable: true, button: 0, ctrlKey: {json.dumps(ctrl)} }})), 0)")


def js_calls() -> list[str]:
    """The CALLS list of web-src/src/bridge.js: every call the page makes on the Bridge."""
    source = (WEB.parent.parent / "web-src" / "src" / "bridge.js").read_text(encoding="utf-8")
    match = re.search(r"^export const CALLS = (\[.*?^\]);$", source, flags=re.S | re.M)
    return json.loads(match.group(1)) if match else []


def check_bridge(app: QApplication, view: QWebEngineView, page: Page, bridge: Bridge) -> None:
    if not run_js(app, view, "typeof window.mdEditor?.command === 'function'"):
        check(False, "window.mdEditor exposes command and setTheme")
        return
    meta = Bridge.staticMetaObject
    slots = {bytes(meta.method(i).name()).decode() for i in range(meta.methodOffset(), meta.methodCount())}
    check(js_calls() and set(js_calls()) <= slots, f"the Bridge has a slot for every call in bridge.js ({slots})")
    doc = bridge_doc()
    check(docschema.validate(doc) == [], "the bridge document is valid in Python")
    mark = len(bridge.calls)
    set_doc(app, view, doc)
    pump(app, lambda: False, 0.2)
    calls = [[name, *(history_view(arg) if name == "selectionState" else arg for arg in args)]
             for name, *args in bridge.calls[mark:]]
    check(calls == [["caretBlock", 0],
                    ["selectionState", {"marks": [], "block": {"type": "heading", "level": 2}, "can": NO_UNDO}]],
          f"setDocument reports the caret block and the selection state, nothing else ({calls})")
    get_doc(app, view)
    check(run_js(app, view, "window.mdEditor.view.state.doc.child(3).child(0).child(0).attrs.colspan") == 1,
          "getDocument leaves the live table cell attrs alone")

    # Selection state: at most one report per 50 ms, with the latest state; caretBlock at once.
    run_js(app, view, "(window.mdEditor.focusBlock(0), "
                      "window.TextSelection = window.mdEditor.view.state.selection.constructor, 0)")
    run_js(app, view, SELECT_JS)
    pump(app, lambda: False, 0.2)
    mark = len(bridge.calls)
    run_js(app, view, f"(select({PLAIN}), select({CODE}), select(3), select({BOLD}), 0)")
    pump(app, lambda: False, 0.2)
    states = [[history_view(state)] for state, in bridge.args("selectionState", mark)]
    check(bridge.args("caretBlock", mark) == [[1], [2], [0], [1]], "caretBlock follows every block change at once")
    check(states == [[{"marks": ["strong", "em"], "block": {"type": "paragraph"}, "can": NO_UNDO}]],
          f"four quick selection changes send one selectionState with the last one ({states})")
    expected = {
        f"select({PLAIN})": ([], {"type": "paragraph"}),
        f"select({LINK})": (["link"], {"type": "paragraph"}),
        f"select({PLAIN}, {LINK})": (["strong", "em", "link"], {"type": "paragraph"}),
        f"select({CODE})": ([], {"type": "code_block"}),
        f"window.mdEditor.focusBlock({TABLE_INDEX})": ([], {"type": "table_header"}),
        f"window.mdEditor.focusBlock({RULE_INDEX})": ([], None),
    }
    for script, (marks, block) in expected.items():
        run_js(app, view, f"({script}, 0)")
        state = history_view(latest_state(app, bridge))
        check(state == {"marks": marks, "block": block, "can": NO_UNDO}, f"selectionState after {script} ({state})")
    check(bridge.args("changed", mark) == [], "selection changes do not report a change")

    # changed: once per load. Undo history: per load, through command().
    mark = len(bridge.calls)
    run_js(app, view, f"""(window.mdEditor.view.dispatch(window.mdEditor.view.state.tr.insertText('A', {PLAIN})),
        window.mdEditor.view.dispatch(window.mdEditor.view.state.tr.insertText('B', {PLAIN})), 0)""")
    state = history_view(latest_state(app, bridge))
    check(bridge.args("changed", mark) == [[]], "two edits after a load report changed once")
    check(state and state["can"] == {"undo": True, "redo": False}, f"an edit can be undone ({state})")
    check(run_js(app, view, "window.mdEditor.command('undo')") is True and get_doc(app, view) == doc,
          "command('undo') restores the loaded document")
    state = history_view(latest_state(app, bridge))
    check(state and state["can"] == {"undo": False, "redo": True}, f"an undone edit can be redone ({state})")
    check(run_js(app, view, "window.mdEditor.command('redo')") is True
          and get_doc(app, view)["content"][1]["content"][0]["text"] == "pBAlain ",
          "command('redo') reapplies the edit")
    check(run_js(app, view, "window.mdEditor.command('noSuchCommand')") is False, "an unknown command returns false")
    check(any("unknown command noSuchCommand" in message for message in page.console),
          "an unknown command logs a warning")
    set_doc(app, view, doc)
    check(run_js(app, view, "window.mdEditor.command('undo')") is False, "setDocument starts a new undo history")
    state = history_view(latest_state(app, bridge))
    check(state and state["can"] == NO_UNDO, f"after setDocument nothing can be undone ({state})")
    mark = len(bridge.calls)
    run_js(app, view, f"(window.mdEditor.view.dispatch(window.mdEditor.view.state.tr.insertText('C', {PLAIN})), 0)")
    pump(app, lambda: bridge.args("changed", mark), 3)
    check(bridge.args("changed", mark) == [[]], "the first edit after another load reports changed again")

    # setTheme: swaps the theme stylesheet and the raw HTML frame colors, without a reload.
    set_doc(app, view, doc)
    frame_fg = """(() => {
      const fg = getComputedStyle(document.documentElement).getPropertyValue('--fg').trim();
      return document.querySelector('#editor .md-html-block iframe').srcdoc.includes('color:' + fg);
    })()"""
    light_fg = run_js(app, view, "getComputedStyle(document.documentElement).getPropertyValue('--fg').trim()")
    check(run_js(app, view, frame_fg) is True, "the raw HTML frame uses the page's text color")
    run_js(app, view, "(window.notReloaded = true, 0)")
    pump(app, lambda: False, 0.2)
    mark = len(bridge.calls)
    run_js(app, view, f"(window.mdEditor.setTheme({json.dumps(render.page_css('dark'))}), 0)")
    pump(app, lambda: False, 0.2)
    background = run_js(app, view, "getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()")
    dark_fg = run_js(app, view, "getComputedStyle(document.documentElement).getPropertyValue('--fg').trim()")
    check((background or "").lower() == render.PAGE_BACKGROUND["dark"].lower()
          and run_js(app, view, "window.notReloaded") is True,
          f"setTheme swaps the theme CSS without reloading (--bg = {background!r})")
    check(dark_fg != light_fg and run_js(app, view, frame_fg) is True, "setTheme refreshes the raw HTML frames")
    check(bridge.calls[mark:] == [] and get_doc(app, view) == doc, "setTheme leaves the document alone")
    run_js(app, view, f"(window.mdEditor.setTheme({json.dumps(render.page_css('light'))}), 0)")

    # Links: hover shows the href; Ctrl+click opens it; a plain click never navigates.
    mark = len(bridge.calls)
    for script in (mouse("#editor a", "mouseover"), mouse("#editor a", "mouseover"),
                   mouse("#editor h2", "mouseover"), mouse("#editor a", "mouseover")):
        run_js(app, view, script)
    run_js(app, view, "(document.querySelector('#editor .ProseMirror').dispatchEvent(new MouseEvent('mouseleave')), 0)")
    pump(app, lambda: len(bridge.args("hoverLink", mark)) >= 4, 3)
    hovers = bridge.args("hoverLink", mark)
    check(hovers == [[LINK_HREF], [""], [LINK_HREF], [""]], f"hovering links reports their href ({hovers})")
    for script in (mouse("#editor a", "mousedown"), mouse("#editor a", "click"),
                   mouse("#editor a", "mousedown", ctrl=True), mouse("#editor a", "click", ctrl=True)):
        run_js(app, view, script)
    pump(app, lambda: bridge.args("openLink", mark), 3)
    pump(app, lambda: False, 0.3)  # a navigation would be requested by now
    check(bridge.args("openLink", mark) == [[LINK_HREF]], f"only Ctrl+click opens a link ({bridge.calls[mark:]})")
    check(page.navigations == [], f"clicking a link never navigates the page ({page.navigations})")
    run_js(app, view, mouse("#editor a", "mouseover"))
    mark = len(bridge.calls)
    set_doc(app, view, doc)
    pump(app, lambda: bridge.args("hoverLink", mark), 3)
    check(bridge.args("hoverLink", mark) == [[""]], "setDocument clears the hovered link")

    # keepScroll: an external reload keeps the scroll offset; other loads scroll to the top.
    long_doc = {"type": "doc", "content": [
        {"type": "paragraph", "attrs": {"line": None}, "content": [{"type": "text", "text": f"paragraph {i}"}]}
        for i in range(200)
    ]}
    set_doc(app, view, long_doc)
    scroll_top = "document.scrollingElement.scrollTop"
    run_js(app, view, f"({scroll_top} = 600, 0)")
    check(run_js(app, view, scroll_top) == 600, "the long document scrolls")
    run_js(app, view, f"(window.mdEditor.setDocument({json.dumps(long_doc)}, true), 0)")
    check(run_js(app, view, scroll_top) == 600, "setDocument(doc, true) keeps the scroll offset")
    run_js(app, view, f"(window.mdEditor.setDocument({json.dumps(long_doc)}, false), 0)")
    check(run_js(app, view, scroll_top) == 0, "setDocument(doc, false) scrolls to the top")


# --- Task 10: formatting commands, keymaps and input rules ------------------------------------

CTRL = Qt.KeyboardModifier.ControlModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier
ALT = Qt.KeyboardModifier.AltModifier
K = Qt.Key
# place(needle, start, end) selects from `start` to `end` characters into the first text that
# contains `needle`; span(a, b) selects from the start of `a` to the end of `b`. Both focus the
# editor. They need select() and window.TextSelection (set by check_bridge).
PLACE_JS = """(window.findText = (needle) => {
  let found = null;
  window.mdEditor.view.state.doc.descendants((node, pos) => {
    if (found === null && node.isText && node.text.includes(needle)) found = pos + node.text.indexOf(needle);
    return found === null;
  });
  if (found === null) throw new Error('text not found: ' + needle);
  return found;
}, window.place = (needle, start = 0, end = start) => {
  select(findText(needle) + start, findText(needle) + end);
  window.mdEditor.view.focus();
}, window.span = (first, last) => {
  select(findText(first), findText(last) + last.length);
  window.mdEditor.view.focus();
}, 0)"""

# (markdown, selection, command name, args, Markdown after the command)
COMMAND_CASES = [
    ("a word b\n", "place('word', 0, 4)", "toggleMark", "strong", "a **word** b\n"),
    ("a **word** b\n", "place('word', 0, 4)", "toggleMark", "strong", "a word b\n"),
    ("a word\n", "place('word', 0, 4)", "toggleMark", "strike", "a ~~word~~\n"),
    ("Title\n", "place('Title')", "setBlock", {"type": "heading", "level": 2}, "## Title\n"),
    ("## Title\n", "place('Title')", "setBlock", {"type": "paragraph"}, "Title\n"),
    ("a\\\nb\n", "place('a')", "setBlock", {"type": "code_block", "language": "py"}, "```py\na\nb\n```\n"),
    ("```\na\nb\n```\n", "place('a')", "setBlock", {"type": "paragraph"}, "a\\\nb\n"),
    ("a\n", "place('a')", "toggleList", "bullet", "- a\n"),
    ("- a\n", "place('a')", "toggleList", "bullet", "a\n"),
    ("a\n", "place('a')", "toggleList", "ordered", "1. a\n"),
    ("a\n", "place('a')", "toggleList", "task", "- [ ] a\n"),
    ("- [x] a\n- [ ] b\n", "place('a')", "toggleList", "bullet", "- a\n- b\n"),
    ("3. a\n4. b\n", "place('b')", "toggleList", "task", "- [ ] a\n- [ ] b\n"),
    ("a\n", "place('a')", "toggleQuote", None, "> a\n"),
    ("> - a\n", "place('a')", "toggleQuote", None, "- a\n"),
    ("a\n", "place('a', 1)", "insertCodeBlock", {"language": "py thon"}, "a\n\n```py\n```\n"),
    ("a\n", "place('a', 1)", "insertTable", {"rows": 2, "cols": 2}, "a\n\n|  |  |\n| --- | --- |\n|  |  |\n"),
    ("a\n", "place('a', 1)", "insertRule", None, "a\n\n---\n"),
    ("- a\n", "place('a', 1)", "insertRule", None, "- a\n  ___\n"),
    # Tables go at document level: the parser reads a table in a list item or quote back as text.
    ("- a\n", "place('a', 1)", "insertTable", {"rows": 2, "cols": 1}, "- a\n\n|  |\n| --- |\n|  |\n"),
    ("> a\n", "place('a', 1)", "insertTable", {"rows": 2, "cols": 1}, "> a\n\n|  |\n| --- |\n|  |\n"),
    # An image-only selection gets the link (the dialog sends no text for it); the image stays.
    ("a ![X](x.png) b\n", "select(findText('a ') + 2, findText('a ') + 3)", "setLink",
     {"text": "", "href": "https://e.com/"}, "a [![X](x.png)](https://e.com/) b\n"),
    ("a b\n", "place('a', 1)", "insertImage",
     {"src": "pics/x.png", "display_src": "file:///C:/pics/x.png", "alt": "X"}, "a![X](pics/x.png) b\n"),
    ("a word\n", "place('word', 0, 4)", "setLink", {"text": "word", "href": "https://e.com/"},
     "a [word](https://e.com/)\n"),
    ("a **wo**rd\n", "span('wo', 'rd')", "setLink", {"text": "word", "href": "https://e.com/"},
     "a [**wo**rd](https://e.com/)\n"),
    ("ab\n", "place('ab', 1)", "setLink", {"text": "site", "href": "https://e.com/"}, "a[site](https://e.com/)b\n"),
    ("ab\n", "place('ab', 1)", "setLink", {"text": "", "href": "https://e.com/"},
     "a<https://e.com/>b\n"),
    ("x [old](https://o.com/ \"T\")\n", "place('old', 1)", "setLink", {"text": "new", "href": "https://n.com/"},
     "x [new](https://n.com/ \"T\")\n"),
    ("[old](https://o.com/) x\n", "place('old', 1)", "removeLink", None, "old x\n"),
    ("## **a** *b* [l](https://l.com/)\n", "span('a', 'l')", "clearFormatting", None, "a b [l](https://l.com/)\n"),
    ("```py\nx\n```\n", "place('x')", "setCodeLanguage", "rust extra", "```rust\nx\n```\n"),
]
# (markdown, selection, command name, args): the command refuses and changes nothing.
REFUSED_CASES = [
    ("```\nx\n```\n", "place('x', 0, 1)", "toggleMark", "strong"),
    ("a\n", "place('a', 0, 1)", "toggleMark", "link"),
    ("a\n", "place('a')", "setBlock", {"type": "heading", "level": 9}),
    ("a\n", "place('a')", "toggleList", "numbered"),
    ("a\n", "place('a')", "insertTable", {"rows": 0, "cols": 3}),
    ("a\n", "place('a')", "insertTable", {"rows": 51, "cols": 3}),
    ("a\n", "place('a')", "insertImage", {"src": "javascript:alert(1)", "alt": "x"}),
    ("a\n", "place('a')", "insertImage", {"src": "x.png", "display_src": "data:text/html,x"}),
    ("```\nx\n```\n", "place('x')", "insertImage", {"src": "x.png"}),
    ("a\n", "place('a', 0, 1)", "setLink", {"text": "a", "href": "java\tscript:alert(1)"}),
    ("```\nx\n```\n", "place('x', 0, 1)", "setLink", {"text": "x", "href": "https://e.com/"}),
    ("a\n", "place('a')", "removeLink", None),
    ("a\n", "place('a')", "setCodeLanguage", "py"),
]
# (markdown, selection, keys, Markdown after them); a str is typed, a tuple is (key, modifiers).
KEY_CASES = [
    ("a word\n", "place('word', 0, 4)", [(K.Key_B, CTRL)], "a **word**\n"),
    ("a word\n", "place('word', 0, 4)", [(K.Key_I, CTRL)], "a *word*\n"),
    ("a word\n", "place('word', 0, 4)", [(K.Key_X, CTRL | SHIFT)], "a ~~word~~\n"),
    ("a word\n", "place('word', 0, 4)", [(K.Key_QuoteLeft, CTRL)], "a `word`\n"),
    ("word\n", "place('word')", [(K.Key_2, CTRL | ALT)], "## word\n"),
    ("## word\n", "place('word')", [(K.Key_0, CTRL | ALT)], "word\n"),
    ("word\n", "place('word')", [(K.Key_Asterisk, CTRL | SHIFT)], "- word\n"),
    ("word\n", "place('word')", [(K.Key_8, CTRL | SHIFT)], "- word\n"),
    ("word\n", "place('word')", [(K.Key_Ampersand, CTRL | SHIFT)], "1. word\n"),
    ("word\n", "place('word')", [(K.Key_ParenLeft, CTRL | SHIFT)], "- [ ] word\n"),
    ("word\n", "place('word')", [(K.Key_Greater, CTRL | SHIFT)], "> word\n"),
    ("**a** *b*\n", "span('a', 'b')", [(K.Key_Space, CTRL)], "a b\n"),
    ("a word\n", "place('word', 0, 4)", [(K.Key_B, CTRL), (K.Key_Z, CTRL)], "a word\n"),
    ("a word\n", "place('word', 0, 4)", [(K.Key_B, CTRL), (K.Key_Z, CTRL), (K.Key_Y, CTRL)], "a **word**\n"),
    # Input rules, typed over a selected placeholder paragraph.
    ("x\n", "place('x', 0, 1)", ["# Title"], "# Title\n"),
    ("x\n", "place('x', 0, 1)", ["###### T"], "###### T\n"),
    ("x\n", "place('x', 0, 1)", ["- a"], "- a\n"),
    ("x\n", "place('x', 0, 1)", ["* a"], "- a\n"),
    ("x\n", "place('x', 0, 1)", ["3. a"], "3. a\n"),
    ("x\n", "place('x', 0, 1)", ["> a"], "> a\n"),
    ("x\n", "place('x', 0, 1)", ["- [ ] a"], "- [ ] a\n"),
    ("x\n", "place('x', 0, 1)", ["- [x] a"], "- [x] a\n"),
    ("x\n", "place('x', 0, 1)", ["a **b** c"], "a **b** c\n"),
    ("x\n", "place('x', 0, 1)", ["a *i* c"], "a *i* c\n"),
    ("x\n", "place('x', 0, 1)", ["a `c` d"], "a `c` d\n"),
    ("x\n", "place('x', 0, 1)", ["a ~~s~~ d"], "a ~~s~~ d\n"),
    ("x\n", "place('x', 0, 1)", ["2*3*4"], "2\\*3\\*4\n"),
    # A mark rule leaves a range alone that holds an image or other marks (it would flatten them).
    ("*see ![X](p.png) here\n", "place('here', 4)", ["*"], "\\*see ![X](p.png) here\\*\n"),
    ("*it **bd** x\n", "place('x', 1)", ["*"], "\\*it **bd** x\\*\n"),
    ("x\n", "place('x', 0, 1)", ["```py", (K.Key_Return, None), "x"], "```py\nx\n```\n"),
    ("x\n", "place('x', 0, 1)", ["---", (K.Key_Return, None), "x"], "---\n\nx\n"),
    ("x\n", "place('x', 0, 1)", ["# ", (K.Key_Backspace, None)], "\\#\n"),
    ("```\nx\n```\n", "place('x', 0, 1)", ["**b**"], "```\n**b**\n```\n"),
    # Lists.
    ("- a\n", "place('a', 1)", [(K.Key_Return, None), (K.Key_Tab, None), "b"], "- a\n  - b\n"),
    ("- a\n  - b\n", "place('b', 1)", [(K.Key_Tab, SHIFT)], "- a\n- b\n"),
    ("- a\n", "place('a', 1)", [(K.Key_Return, None), (K.Key_Return, None), "b"], "- a\n\nb\n"),
    ("- [x] a\n", "place('a', 1)", [(K.Key_Return, None), "b"], "- [x] a\n- [ ] b\n"),
    # Code blocks.
    ("```\nx\n```\n", "place('x')", [(K.Key_Tab, None)], "```\n    x\n```\n"),
    ("```\nx\n```\n", "place('x')", [(K.Key_Tab, SHIFT), "y"], "```\nyx\n```\n"),
    ("```\nx\n```\n", "place('x', 1)", [(K.Key_Return, None), "y"], "```\nx\ny\n```\n"),
    ("```\nx\n```\n", "place('x', 1)", [(K.Key_Return, CTRL), "y"], "```\nx\n```\n\ny\n"),
    ("```\nx\n```\n", "place('x', 1)", [(K.Key_Down, None), "y"], "```\nx\n```\n\ny\n"),
    ("```\nx\n```\n", "place('x')", [(K.Key_Up, None), "y"], "y\n\n```\nx\n```\n"),
    # With a block after it, ArrowDown just moves there (to the end of "b": the code's padding).
    ("a\n\n```\nx\n```\n\nb\n", "place('x')", [(K.Key_Down, None), "y"], "a\n\n```\nx\n```\n\nby\n"),
    # Tab outside lists and code keeps the focus in the editor; the gap cursor passes a final rule.
    ("a\n", "place('a', 1)", [(K.Key_Tab, None), "b"], "ab\n"),
    ("a\n", "place('a', 1)", [(K.Key_Tab, SHIFT), "b"], "ab\n"),
    ("a\n\n---\n", "place('a', 1)", [(K.Key_Right, None), (K.Key_Right, None), "z"], "a\n\n---\n\nz\n"),
]


def load_md(app: QApplication, view: QWebEngineView, markdown: str) -> None:
    set_doc(app, view, docmodel.from_markdown(markdown))


def as_markdown(app: QApplication, view: QWebEngineView) -> str:
    return serialize.to_markdown(get_doc(app, view))


def command(app: QApplication, view: QWebEngineView, name: str, args=None):
    """mdEditor.command's result, or the text of the exception it threw."""
    return run_js(app, view, f"""(() => {{
      try {{ return window.mdEditor.command({json.dumps(name)}, {json.dumps(args)}); }}
      catch (error) {{ return String(error); }}
    }})()""")


def press(app: QApplication, view: QWebEngineView, strokes: list) -> None:
    for stroke in strokes:
        if isinstance(stroke, str):
            QTest.keyClicks(view.focusProxy(), stroke)
        else:
            key, modifiers, *text = stroke
            modifiers = modifiers or Qt.KeyboardModifier.NoModifier
            if text:  # the text a real keyboard sends, e.g. "\x16" with Ctrl+Shift+V
                QTest.sendKeyEvent(QTest.KeyAction.Click, view.focusProxy(), key, text[0], modifiers)
            else:
                QTest.keyClick(view.focusProxy(), key, modifiers)
    pump(app, lambda: False, 0.2)


def check_editing(app: QApplication, view: QWebEngineView, bridge: Bridge) -> None:
    run_js(app, view, PLACE_JS)
    for markdown, selection, name, args, expected in COMMAND_CASES:
        load_md(app, view, markdown)
        run_js(app, view, f"({selection}, 0)")
        done = command(app, view, name, args)
        result = as_markdown(app, view)
        check(done is True and result == expected,
              f"command {name}({args!r}) on {markdown!r}: {result!r} (returned {done!r})")
    for markdown, selection, name, args in REFUSED_CASES:
        load_md(app, view, markdown)
        run_js(app, view, f"({selection}, 0)")
        before = get_doc(app, view)
        done = command(app, view, name, args)
        check(done is False and get_doc(app, view) == before, f"command {name}({args!r}) refused on {markdown!r}")

    # The caret goes into an inserted code block or table.
    load_md(app, view, "a\n")
    run_js(app, view, "(place('a', 1), 0)")
    command(app, view, "insertTable", {"rows": 3, "cols": 3})
    check((latest_state(app, bridge) or {}).get("block") == {"type": "table_header"},
          "insertTable puts the caret in the first header cell")
    command(app, view, "insertCodeBlock", None)
    check((latest_state(app, bridge) or {}).get("block") == {"type": "code_block"},
          "insertCodeBlock puts the caret in the new code block")
    load_md(app, view, "a\n")
    run_js(app, view, "(place('a', 1), 0)")
    command(app, view, "insertRule")
    pump(app, lambda: False, 0.2)
    types = [node["type"] for node in get_doc(app, view)["content"]]
    check(types == ["paragraph", "horizontal_rule", "paragraph"] and bridge.args("caretBlock")[-1] == [2],
          f"a rule inserted at the end gets a paragraph after it for the caret ({types})")

    # selectionState.can follows the selection.
    load_md(app, view, "a\n\n```\nx\n```\n\n| h |\n| --- |\n| c |\n")
    expected_can = {
        "place('a')": {"toggleMark": True, "setBlock": True, "setLink": True, "insertImage": True,
                       "setCodeLanguage": False, "removeLink": False, "insertTable": True},
        "place('x')": {"toggleMark": False, "setBlock": True, "setLink": False, "insertImage": False,
                       "setCodeLanguage": True, "linkDialog": False, "imageDialog": False},
        "place('h')": {"toggleMark": True, "setBlock": False, "setLink": True, "insertImage": True,
                       "setCodeLanguage": False, "toggleList": False, "toggleQuote": False},
    }
    for selection, wanted in expected_can.items():
        run_js(app, view, f"({selection}, 0)")
        can = (latest_state(app, bridge) or {}).get("can", {})
        check({name: can.get(name) for name in wanted} == wanted, f"selectionState.can after {selection} ({can})")

    # Link and image dialogs are requested from Python; refused where they do not apply.
    load_md(app, view, "[old](https://o.com/) a word\n\n```\nx\n```\n")
    mark = len(bridge.calls)
    for selection in ("place('old', 1)", "place('word', 0, 4)"):
        run_js(app, view, f"({selection}, 0)")
        check(command(app, view, "linkDialog") is True, f"linkDialog applies after {selection}")
    run_js(app, view, "(place('x'), 0)")
    check(command(app, view, "linkDialog") is False and command(app, view, "imageDialog") is False,
          "no link or image dialog inside a code block")
    run_js(app, view, "(place('a', 0), 0)")
    check(command(app, view, "imageDialog") is True, "imageDialog applies in a paragraph")
    run_js(app, view, "(place('old', 1), 0)")
    press(app, view, [(K.Key_K, CTRL)])
    pump(app, lambda: len(bridge.args("requestLinkDialog", mark)) >= 3, 3)
    dialogs = [call for call in bridge.calls[mark:] if call[0] in ("requestLinkDialog", "requestImageDialog")]
    check(dialogs == [["requestLinkDialog", "old", "https://o.com/"], ["requestLinkDialog", "word", ""],
                      ["requestImageDialog"], ["requestLinkDialog", "old", "https://o.com/"]],
          f"dialog requests carry the link text and href ({dialogs})")

    # Keys and input rules, typed for real.
    for markdown, selection, strokes, expected in KEY_CASES:
        load_md(app, view, markdown)
        run_js(app, view, f"({selection}, 0)")
        press(app, view, strokes)
        result = as_markdown(app, view)
        check(result == expected, f"keys {strokes!r} on {markdown!r}: {result!r}")

    # Task checkboxes: a real mouse click toggles the item, leaves the caret, reports a change.
    load_md(app, view, "- [ ] a\n")
    run_js(app, view, "(place('a', 1), 0)")
    mark = len(bridge.calls)
    box = run_js(app, view, """(() => {
      const box = document.querySelector('#editor input.task-list-item-checkbox').getBoundingClientRect();
      return [Math.round(box.left + box.width / 2), Math.round(box.top + box.height / 2)];
    })()""")
    caret = "window.mdEditor.view.state.selection.from"
    before = run_js(app, view, caret)
    for expected in ("- [x] a\n", "- [ ] a\n"):
        QTest.mouseClick(view.focusProxy(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(*box))
        pump(app, lambda: False, 0.3)
        result = as_markdown(app, view)
        check(result == expected and run_js(app, view, caret) == before,
              f"clicking a task checkbox toggles the item and leaves the caret ({result!r})")
    pump(app, lambda: bridge.args("changed", mark), 3)
    check(bridge.args("changed", mark) == [[]], "toggling a task checkbox reports a change")


# --- Task 11: tables, paste and protected blocks --------------------------------------------

TABLE_MD = "| h | i |\n| --- | --- |\n| c | d |\n"
# (markdown, selection, command name, args, Markdown after the command)
TABLE_CASES = [
    (TABLE_MD, "place('c')", "addRowBefore", None, "| h | i |\n| --- | --- |\n|  |  |\n| c | d |\n"),
    (TABLE_MD, "place('c')", "addRowAfter", None, "| h | i |\n| --- | --- |\n| c | d |\n|  |  |\n"),
    (TABLE_MD, "place('d')", "addColumnBefore", None, "| h |  | i |\n| --- | --- | --- |\n| c |  | d |\n"),
    (TABLE_MD, "place('d')", "addColumnAfter", None, "| h | i |  |\n| --- | --- | --- |\n| c | d |  |\n"),
    (TABLE_MD, "place('c')", "deleteRow", None, "| h | i |\n| --- | --- |\n"),
    (TABLE_MD, "place('c')", "deleteColumn", None, "| i |\n| --- |\n| d |\n"),
    ("a\n\n" + TABLE_MD, "place('c')", "deleteTable", None, "a\n"),
    (TABLE_MD, "place('d')", "setColumnAlign", "center", "| h | i |\n| --- | :---: |\n| c | d |\n"),
    (TABLE_MD, "place('h')", "setColumnAlign", "right", "| h | i |\n| --- | --- |\n| c | d |\n".replace(
        "| --- | --- |", "| ---: | --- |")),
    # Markdown's header is the first row: deleting it promotes the next row, a row above it replaces it.
    (TABLE_MD, "place('h')", "deleteRow", None, "| c | d |\n| --- | --- |\n"),
    (TABLE_MD, "place('h')", "addRowBefore", None, "|  |  |\n| --- | --- |\n| h | i |\n| c | d |\n"),
    # Tables are top-level only (mistune reads nested ones as paragraphs): inserted after the list or quote.
    ("- a\n", "place('a', 1)", "insertTable", {"rows": 2, "cols": 1}, "- a\n\n|  |\n| --- |\n|  |\n"),
    ("> a\n", "place('a', 1)", "insertTable", {"rows": 2, "cols": 1}, "> a\n\n|  |\n| --- |\n|  |\n"),
]
TABLE_REFUSED = [
    ("| h |\n| --- |\n", "place('h')", "deleteRow", None),
    ("| h |\n| --- |\n| c |\n", "place('c')", "deleteColumn", None),
    (TABLE_MD, "place('c')", "setColumnAlign", "justify"),
    ("a\n", "place('a')", "addRowAfter", None),
    ("a\n", "place('a')", "deleteTable", None),
    ("a\n", "place('a')", "setColumnAlign", "left"),
]
# (markdown, selection, keys, Markdown after them)
TABLE_KEYS = [
    (TABLE_MD, "place('h', 1)", [(K.Key_Tab, None), "x"], "| h | x |\n| --- | --- |\n| c | d |\n"),
    (TABLE_MD, "place('i', 1)", [(K.Key_Tab, None), "x"], "| h | i |\n| --- | --- |\n| x | d |\n"),
    (TABLE_MD, "place('d', 1)", [(K.Key_Tab, None), "e"], "| h | i |\n| --- | --- |\n| c | d |\n| e |  |\n"),
    (TABLE_MD, "place('d')", [(K.Key_Tab, SHIFT), "x"], "| h | i |\n| --- | --- |\n| x | d |\n"),
    (TABLE_MD, "place('h')", [(K.Key_Tab, SHIFT), "y"], "| yh | i |\n| --- | --- |\n| c | d |\n"),
]
# HTML as a browser puts it on the Windows clipboard (CF_HTML keeps the fragment markers).
PASTE_HTML = (
    '<html><body><!--StartFragment--><p><b>bold</b> <a href="javascript:alert(1)">bad</a> '
    '<a href="https://ok.example/">ok</a></p>'
    '<table><tr><th colspan="2">h</th></tr><tr><td>1</td><td>2</td><td>3</td></tr></table>'
    '<table><tr><th rowspan="2">a</th><th>b</th></tr><tr><td>c</td></tr></table>'
    "<!--EndFragment--></body></html>"
)
PASTED_MD = (
    "**bold** bad [ok](https://ok.example/)\n\n"
    "| h |  |  |\n| --- | --- | --- |\n| 1 | 2 | 3 |\n\n"
    "| a | b |\n| --- | --- |\n|  | c |\n"
)
NESTED_PASTE_HTML = (
    "<html><body><!--StartFragment--><table><tr><th>h</th></tr><tr><td>c</td></tr></table>"
    "<!--EndFragment--></body></html>"
)
NESTED_PASTE_MD = "- x\n\n| h |\n| --- |\n| c |\n"
# Word, Confluence and Docs wrap cell text in <p>, <ul> or <div>: the cell keeps one line of text.
CELL_PASTE_HTML = (
    "<html><body><!--StartFragment--><table><tr><th><p>Name</p></th><th><p>Age</p></th></tr>"
    "<tr><td><p>Ann</p></td><td><ul><li>3</li><li>0</li></ul></td></tr></table><!--EndFragment--></body></html>"
)
CELL_PASTE_MD = "| Name | Age |\n| --- | --- |\n| Ann | 3 0 |\n"
LINES_PASTE_HTML = "<html><body><!--StartFragment--><p>one</p><p>two</p><!--EndFragment--></body></html>"
LINES_PASTED_MD = "| h | i |\n| --- | --- |\n| cone two | d |\n"


def to_clipboard(html: str | None, text: str) -> None:
    mime = QMimeData()
    if html is not None:
        mime.setData("text/html", html.encode("utf-8"))
    mime.setText(text)
    QApplication.clipboard().setMimeData(mime)


def click(app: QApplication, view: QWebEngineView, selector: str, button=Qt.MouseButton.LeftButton) -> None:
    """A real mouse click in the middle of the first element matching `selector`."""
    point = run_js(app, view, f"""(() => {{
      const box = document.querySelector({json.dumps(selector)}).getBoundingClientRect();
      return [Math.round(box.left + box.width / 2), Math.round(box.top + box.height / 2)];
    }})()""")
    QTest.mouseClick(view.focusProxy(), button, Qt.KeyboardModifier.NoModifier, QPoint(*point))
    pump(app, lambda: False, 0.3)


def check_tables(app: QApplication, view: QWebEngineView, page: Page, bridge: Bridge) -> None:
    for markdown, selection, name, args, expected in TABLE_CASES:
        load_md(app, view, markdown)
        run_js(app, view, f"({selection}, 0)")
        done = command(app, view, name, args)
        result = as_markdown(app, view)
        check(done is True and result == expected,
              f"table command {name}({args!r}) after {selection}: {result!r} (returned {done!r})")
    for markdown, selection, name, args in TABLE_REFUSED:
        load_md(app, view, markdown)
        run_js(app, view, f"({selection}, 0)")
        before = get_doc(app, view)
        check(command(app, view, name, args) is False and get_doc(app, view) == before,
              f"table command {name}({args!r}) refused on {markdown!r}")
    for markdown, selection, strokes, expected in TABLE_KEYS:
        load_md(app, view, markdown)
        run_js(app, view, f"({selection}, 0)")
        press(app, view, strokes)
        result = as_markdown(app, view)
        check(result == expected, f"table keys {strokes!r} after {selection}: {result!r}")

    # Deleting the header row keeps the caret in the table (the cells change type in place).
    load_md(app, view, TABLE_MD)
    run_js(app, view, "(place('h'), 0)")
    command(app, view, "deleteRow")
    check((latest_state(app, bridge) or {}).get("block") == {"type": "table_header"},
          "after deleting the header row the caret is in the new header row")

    # Paste: unsafe links dropped, merged cells split, short rows padded; Ctrl+Shift+V pastes plain text.
    load_md(app, view, "x\n")
    run_js(app, view, "(place('x', 0, 1), 0)")
    to_clipboard(PASTE_HTML, "bold bad ok")
    press(app, view, [(K.Key_V, CTRL)])
    result = as_markdown(app, view)
    check(result == PASTED_MD, f"Ctrl+V pastes formatting, drops unsafe links, splits merged cells ({result!r})")
    check(docschema.validate(get_doc(app, view)) == [], "the pasted document is valid in Python")
    load_md(app, view, "- x\n")
    run_js(app, view, "(place('x', 1), 0)")
    to_clipboard(NESTED_PASTE_HTML, "h c")
    press(app, view, [(K.Key_V, CTRL)])
    result = as_markdown(app, view)
    check(result == NESTED_PASTE_MD and docschema.validate(get_doc(app, view)) == [],
          f"a table pasted into a list item lands after the list ({result!r})")
    load_md(app, view, "x\n")
    run_js(app, view, "(place('x', 0, 1), 0)")
    to_clipboard(PASTE_HTML, "bold bad ok")
    press(app, view, [(K.Key_V, CTRL | SHIFT, "\x16")])
    result = as_markdown(app, view)
    check(result == "bold bad ok\n", f"Ctrl+Shift+V pastes plain text ({result!r})")
    load_md(app, view, "x\n")
    run_js(app, view, "(place('x', 0, 1), 0)")
    to_clipboard(CELL_PASTE_HTML, "Name Age Ann 3 0")
    press(app, view, [(K.Key_V, CTRL)])
    result = as_markdown(app, view)
    check(result == CELL_PASTE_MD, f"a pasted table with <p> and <ul> in its cells keeps its shape ({result!r})")
    # Several lines pasted into a cell join into that cell, as text, HTML paragraphs or plain text.
    for html in (None, LINES_PASTE_HTML):
        for stroke in ((K.Key_V, CTRL), (K.Key_V, CTRL | SHIFT, "\x16")):
            load_md(app, view, TABLE_MD)
            run_js(app, view, "(place('c', 1), 0)")
            to_clipboard(html, "one\ntwo")
            press(app, view, [stroke])
            result = as_markdown(app, view)
            check(result == LINES_PASTED_MD,
                  f"several lines pasted into a cell stay in it ({'html' if html else 'text'}, {stroke[1]!r}): {result!r}")
    QApplication.clipboard().clear()  # a clipboard still owning our data crashes Qt at exit

    # Right-click: the caret moves to the clicked cell before Qt's context menu request, so
    # the menu built from selectionState() offers the table items.
    states: list = []

    def menu_requested(_point) -> None:
        page.runJavaScript("JSON.stringify(window.mdEditor.selectionState?.() ?? null)", 0, states.append)

    view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    view.customContextMenuRequested.connect(menu_requested)
    load_md(app, view, "a\n\n" + TABLE_MD)
    for selection, target, in_table in (("place('a')", "#editor td:last-child", True),
                                        ("place('d')", "#editor p", False)):
        run_js(app, view, f"({selection}, 0)")
        states.clear()
        click(app, view, target, Qt.MouseButton.RightButton)
        pump(app, lambda: states, 3)
        state = (json.loads(states[0]) if states else None) or {}
        can = state.get("can", {})
        check(bool(state) and can.get("addRowAfter") is in_table and can.get("deleteTable") is in_table
              and can.get("setColumnAlign") is in_table,
              f"right-click on {target} moves the caret there before the menu request ({state})")
    view.customContextMenuRequested.disconnect(menu_requested)
    view.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)

    # Protected blocks and chips are selected and deleted as a unit.
    load_md(app, view, "a\n\n<div>raw</div>\n\nb<kbd>c\n")
    click(app, view, "#editor .md-html-block")
    press(app, view, [(K.Key_Backspace, None)])
    result = as_markdown(app, view)
    check(result == "a\n\nb<kbd>c\n", f"a clicked raw HTML block is deleted with Backspace ({result!r})")
    run_js(app, view, "(place('c'), 0)")
    press(app, view, [(K.Key_Backspace, None)])
    result = as_markdown(app, view)
    check(result == "a\n\nbc\n", f"Backspace after an HTML chip deletes the whole chip ({result!r})")
    load_md(app, view, "a[^1]\n\n[^1]: note\n")
    click(app, view, "#editor .md-footnote-def")
    press(app, view, [(K.Key_Delete, None)])
    result = as_markdown(app, view)
    check(result == "a[^1]\n", f"a clicked footnote definition is deleted with Delete ({result!r})")


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

    # Shown like the app's view: Chromium throttles the timers of hidden pages to one per second.
    view.resize(900, 700)
    view.show()
    page.page_url = QUrl.fromLocalFile(str(build_page(folder)))
    view.load(page.page_url)
    check(pump(app, lambda: bridge.args("ready"), READY_TIMEOUT_S), "bridge.ready() received within 5 s")
    pump(app, lambda: False, 0.3)  # a duplicate ready() would arrive by now
    check(bridge.calls == [["ready"]], f"ready() is the first and only call after loading ({bridge.calls})")

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
    check_editor(app, view, folder, bridge)
    check_bridge(app, view, page, bridge)
    check_editing(app, view, bridge)
    check_tables(app, view, page, bridge)

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
