"""Rendered editor host: the ProseMirror page (mdviewer/web) in a QWebEngineView.

Python calls the page through window.mdEditor (runJavaScript); the page calls Python
through the one QWebChannel object, Bridge, whose slots re-emit as RichView signals.
"""

import json
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

from mdviewer.core import render

# Files the page loads from its own folder (CSP script-src 'self').
RUNTIME_FILES = ("editor.js", "editor.css", "qwebchannel.js")
READY_TIMEOUT_MS = 5000  # spec: page ready() within 5 s
# Spec: a pull answers within 3 s. Big documents take longer to serialize in the page
# (~2 s for 28 MB of document JSON), so each MB of the last document JSON adds this much.
PULL_TIMEOUT_MS = 3000
PULL_MS_PER_MB = 100
# Backstop counted from the request: a page that hangs inside set_document never lets the
# pull's own timer start (it waits for the load), and no crash signal fires for a hang.
PULL_HARD_TIMEOUT_MS = 60000
_MAIN_WORLD = 0  # QWebEngineScript.ScriptWorldId.MainWorld: where window.mdEditor lives
# PySide6 types adjusted()'s parameter as ComponentFormattingOption, so the bare
# UrlFormattingOption.RemoveFragment is rejected; OR-ing in PrettyDecoded is accepted.
_NO_FRAGMENT = QUrl.ComponentFormattingOption.PrettyDecoded | QUrl.UrlFormattingOption.RemoveFragment
# A pull reads the document and marks the page clean in one step: no edit falls in between.
_PULL_JS = "(() => {{ const json = JSON.stringify(window.mdEditor.getDocument()); window.mdEditor.markClean({}); return json; }})()"
# Edited code blocks the caret has left, as [{pos, language, code}] (nodeviews.js staleCodeBlocks).
_STALE_CODE_JS = "JSON.stringify(window.mdEditor.staleCodeBlocks())"
# The selection's toolbar and menu state, unthrottled (editor.js selectionState).
_SELECTION_JS = "JSON.stringify(window.mdEditor.selectionState())"
# Each top-level block's heading text, null for other blocks (in-page #anchor links).
_HEADINGS_JS = (
    "(() => { const out = []; window.mdEditor.view.state.doc.forEach("
    "(node) => out.push(node.type.name === 'heading' ? node.textContent : null)); return JSON.stringify(out); })()"
)


class Bridge(QObject):
    """The only object the page sees: one slot per call in web-src/src/bridge.js CALLS."""

    def __init__(self, view: "RichView"):
        super().__init__(view)
        self._view = view

    @Slot()
    def ready(self) -> None:
        self._view._on_ready()

    @Slot(int)
    def changed(self, epoch: int) -> None:
        self._view._on_changed(epoch)

    @Slot("QVariantMap")
    def selectionState(self, state: dict) -> None:
        self._view.selectionState.emit(state)

    @Slot(str, str)
    def requestLinkDialog(self, text: str, href: str) -> None:
        self._view.requestLinkDialog.emit(text, href)

    @Slot()
    def requestImageDialog(self) -> None:
        self._view.requestImageDialog.emit()

    @Slot(str)
    def openLink(self, href: str) -> None:
        self._view.openLink.emit(href)

    @Slot(str)
    def hoverLink(self, href: str) -> None:
        self._view.hoverLink.emit(href)

    @Slot(int)
    def editProtected(self, index: int) -> None:
        self._view.editProtected.emit(index)

    @Slot(int)
    def caretBlock(self, index: int) -> None:
        self._view.caretBlock.emit(index)


class _Page(QWebEnginePage):
    """Stays on the editor page: links leave only through Bridge.openLink (Ctrl+click)."""

    def __init__(self, page_url: QUrl, parent=None):
        super().__init__(parent)
        self.page_url = page_url

    def acceptNavigationRequest(self, url, nav_type, is_main_frame) -> bool:
        if is_main_frame:
            return url.adjusted(_NO_FRAGMENT) == self.page_url  # our loads and in-page anchors
        return url.scheme() == "about"  # raw HTML frames (about:srcdoc)


class RichView(QWebEngineView):
    """The Rendered editor. Calls made before ready() are queued and run once it arrives."""

    ready = Signal()
    changed = Signal()  # first edit since the last set_document or request_document
    selectionState = Signal(dict)
    requestLinkDialog = Signal(str, str)
    requestImageDialog = Signal()
    openLink = Signal(str)
    hoverLink = Signal(str)
    editProtected = Signal(int)
    caretBlock = Signal(int)
    load_failed = Signal()  # no ready() within READY_TIMEOUT_MS, or the page files are missing
    crashed = Signal()  # the render process died; restart() loads a fresh page

    def __init__(self, theme: str = "light", parent=None):
        super().__init__(parent)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="mdviewer-", ignore_cleanup_errors=True)
        self.page_file = Path(self._tmpdir.name) / "editor.html"
        self.setPage(_Page(QUrl.fromLocalFile(str(self.page_file)), self))
        # v1's preview disabled JavaScript; the editor needs it. Raw HTML stays script-free
        # (sandboxed frames, CSP script-src 'self').
        self.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        # Chromium's menu offers Reload and View Source; MainWindow shows its own (edit and table
        # items) from customContextMenuRequested.
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._channel = QWebChannel(self.page())
        self._bridge = Bridge(self)
        self._channel.registerObject("bridge", self._bridge)
        self.page().setWebChannel(self._channel)
        self.page().renderProcessTerminated.connect(self._on_crash)
        self.caretBlock.connect(lambda _index: self._refresh_highlights())
        self._ready_timer = QTimer(self)
        self._ready_timer.setSingleShot(True)
        self._ready_timer.timeout.connect(self._fail)
        self._theme = theme
        self._doc_mb = 0.0  # size of the last document JSON, for the pull timeout
        self._sent = 0  # set_document calls made
        self._applied = 0  # set_document calls the page has finished
        # Every set_document and pull starts a new epoch; the page's changed(epoch) names the
        # one it follows, so a change from before a load or pull is never taken for a new one.
        self._epoch = 0
        self.modified = False  # the page has changed since the last set_document or pull
        self._load_epoch = 0  # the epoch of the latest set_document or restart
        self._pulls: dict[int, tuple[Callable[[dict | None], None], bool, int]] = {}
        self._waiting: list[int] = []  # pulls whose timeout starts when the page is idle
        self._next_pull = 0
        self._finding = False  # the find bar is open over the page (set_finding)
        self.restart()

    # --- lifecycle -------------------------------------------------------------

    def restart(self) -> None:
        """Load a fresh editor page (start, or after `crashed`); the document is empty."""
        self._forget_page()
        self.failed = False
        self._crashed = False
        self._epoch += 1
        self._load_epoch = self._epoch
        self.modified = False
        self._queue.append((f"window.mdEditor.markClean({self._epoch}), 0", None))
        if self._finding:
            self._queue.append(("window.mdEditor.setFinding(true), 0", None))
        self.page().setBackgroundColor(QColor(render.PAGE_BACKGROUND[self._theme]))
        try:
            folder = self.page_file.parent
            folder.mkdir(parents=True, exist_ok=True)
            for name in RUNTIME_FILES:
                shutil.copyfile(render.WEB_DIR / name, folder / name)
            self.page_file.write_text(render.editor_page(self._theme), encoding="utf-8")
        except OSError:
            QTimer.singleShot(0, self, self._fail)  # after the caller has connected load_failed
            return
        self._ready_timer.start(READY_TIMEOUT_MS)
        self.load(QUrl.fromLocalFile(str(self.page_file)))

    def _on_ready(self) -> None:
        if self.is_ready or self.failed:
            return
        self._ready_timer.stop()
        self.is_ready = True
        queue, self._queue = self._queue, []
        for script, callback in queue:
            self._js(script, callback)
        self._arm_waiting()
        self.ready.emit()

    def _fail(self) -> None:
        if self.failed:
            return
        self._forget_page()
        self.failed = True
        self.load_failed.emit()

    def _on_crash(self, _status, _code) -> None:
        self._crashed = True  # until restart(): calls are no-ops, pulls answer None (as when failed)
        self._forget_page()
        self.crashed.emit()

    def _forget_page(self) -> None:
        """Drop everything tied to the current page: its JavaScript callbacks never arrive."""
        self._ready_timer.stop()
        self.is_ready = False
        self._queue: list[tuple[str, Callable | None]] = []
        self._applied = self._sent
        self._fail_pulls()

    # --- Python -> page --------------------------------------------------------

    def _js(self, script: str, callback: Callable | None = None) -> None:
        if callback is None:
            self.page().runJavaScript(script, _MAIN_WORLD)
        else:
            self.page().runJavaScript(script, _MAIN_WORLD, callback)

    def _call(self, script: str, callback: Callable | None = None) -> bool:
        """Runs `script` now, or queues it until ready(); False once loading has failed or the
        render process has crashed (until restart())."""
        if self.failed or self._crashed:
            return False
        if self.is_ready:
            self._js(script, callback)
        else:
            self._queue.append((script, callback))
        return True

    def set_document(self, doc: dict, keep_scroll: bool = False) -> None:
        """Replace the document (new undo history). keep_scroll: external reload."""
        payload = json.dumps(doc)
        self._epoch += 1
        self._load_epoch = self._epoch
        self.modified = False
        self._sent += 1
        number = self._sent
        if self._call(f"window.mdEditor.setDocument({payload}, {json.dumps(keep_scroll)}, {self._epoch}), 0",
                      lambda _result: self._on_applied(number)):
            self._doc_mb = len(payload) / 1e6
        else:
            self._applied = self._sent

    def _on_applied(self, number: int) -> None:
        self._applied = max(self._applied, number)
        self._arm_waiting()

    def _on_changed(self, epoch: int) -> None:
        if epoch == self._epoch and not self.modified:
            self.modified = True
            self.changed.emit()

    def request_document(self, callback: Callable[[dict | None], None]) -> None:
        """callback(doc) with the page's document, or callback(None) on timeout, crash or
        load failure. Called exactly once, never synchronously from a working page.
        The page counts as clean from then on (`modified` False): the caller keeps the
        document's text. A failed pull leaves `modified` as it was."""
        if self.failed or self._crashed:
            callback(None)
            return
        self._next_pull += 1
        number = self._next_pull
        self._pulls[number] = (callback, self.modified, self._load_epoch)
        self._epoch += 1
        self.modified = False
        self._call(_PULL_JS.format(self._epoch), lambda value: self._on_pulled(number, value))
        self._waiting.append(number)
        self._arm_waiting()
        QTimer.singleShot(PULL_HARD_TIMEOUT_MS, self, lambda n=number: self._finish_pull(n, None))

    def _arm_waiting(self) -> None:
        """Start the timeouts of waiting pulls once the page has run every earlier load."""
        if not self.is_ready or self._applied != self._sent:
            return
        timeout = PULL_TIMEOUT_MS + int(PULL_MS_PER_MB * self._doc_mb)
        for number in self._waiting:
            QTimer.singleShot(timeout, self, lambda n=number: self._finish_pull(n, None))
        self._waiting.clear()

    def _on_pulled(self, number: int, value) -> None:
        try:
            doc = json.loads(value) if isinstance(value, str) else None
        except ValueError:
            doc = None
        if isinstance(value, str):
            self._doc_mb = len(value) / 1e6
        self._finish_pull(number, doc if isinstance(doc, dict) else None)

    def _finish_pull(self, number: int, doc: dict | None) -> None:
        pull = self._pulls.pop(number, None)
        if number in self._waiting:
            self._waiting.remove(number)
        if pull is not None:
            callback, was_modified, load_epoch = pull
            if doc is None and load_epoch == self._load_epoch:  # not across a load: that page is clean
                self.modified = self.modified or was_modified
            callback(doc)

    def _fail_pulls(self) -> None:
        pulls, self._pulls = self._pulls, {}
        self._waiting.clear()
        for callback, was_modified, load_epoch in pulls.values():
            if load_epoch == self._load_epoch:
                self.modified = self.modified or was_modified
            callback(None)

    def command(self, name: str, args=None) -> None:
        """Run a toolbar or menu command (web-src/src/commands.js, tables.js)."""
        self._call(f"window.mdEditor.command({json.dumps(name)}, {json.dumps(args)}), 0")

    def set_theme(self, theme: str) -> None:
        """Swap the theme stylesheet in place: no reload, same document and undo history."""
        self._theme = theme
        self.page().setBackgroundColor(QColor(render.PAGE_BACKGROUND[theme]))
        self._call(f"window.mdEditor.setTheme({json.dumps(render.page_css(theme))}), 0")

    def focus_block(self, index: int) -> None:
        """Caret at the start of top-level block `index` (mode-switch caret mapping)."""
        self._call(f"window.mdEditor.focusBlock({int(index)}), 0")

    def heading_texts(self, callback: Callable[[list], None]) -> None:
        """callback(each top-level block's heading text, None for other blocks). Never called when
        the page fails, crashes or restarts first."""
        def done(value):
            if isinstance(value, str):
                callback(json.loads(value))
        self._call(_HEADINGS_JS, done)

    def selection_state(self, callback: Callable[[dict], None]) -> None:
        """callback(the selection's {marks, block, can}), read now rather than throttled (the
        context menu). Never called when the page fails, crashes or restarts first."""
        def done(value):
            if isinstance(value, str):
                callback(json.loads(value))
        self._call(_SELECTION_JS, done)

    def set_finding(self, on: bool) -> None:
        """While the find bar is open, code blocks show plain text only, so find-in-page counts
        each match once; kept across restart()."""
        self._finding = on
        self._call(f"window.mdEditor.setFinding({json.dumps(on)}), 0")

    def _refresh_highlights(self) -> None:
        """The caret moved to another top-level block: edited code blocks it left get their
        highlight back, computed here with Pygments and applied by the page. The answer is
        neither a change nor an undo step, and the page skips a block edited meanwhile."""
        def done(value):
            if not isinstance(value, str):
                return
            updates = [{**block, "markup": render.highlight_code(block["code"], block["language"])}
                       for block in json.loads(value)]
            updates = [update for update in updates if update["markup"]]
            if updates:
                self._call(f"window.mdEditor.applyHighlights({json.dumps(updates)}), 0")
        self._call(_STALE_CODE_JS, done)
