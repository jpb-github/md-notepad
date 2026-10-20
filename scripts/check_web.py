"""Offscreen check of the committed web editor: page shell, bundle, QWebChannel, CSP.

Run: .venv\\Scripts\\python scripts\\check_web.py  ->  prints WEB OK or the failed checks.
Loads mdviewer/web/editor.html from a temp folder (as RichView will), with an inline
<script> probe added: the CSP must block the probe while the external scripts run.
Run it after every scripts/build_web.py.
"""

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

from mdviewer.core import render  # noqa: E402

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
