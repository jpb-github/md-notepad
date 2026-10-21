"""Headless UI smoke test for MD Viewer.

Run: .venv\\Scripts\\python scripts\\smoke_ui.py  ->  prints SMOKE OK or the failed checks.
Lives outside tests/ because tests/ must never import Qt.
"""

import json
import os
import re
import shutil
import signal
import sys
import tempfile
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")  # shown web views: no GPU log noise
TMP = Path(tempfile.mkdtemp(prefix="mdviewer-smoke-"))
os.environ["APPDATA"] = str(TMP / "appdata")  # never touch the real settings.json
# The offscreen platform ships an empty font database; point it at the Windows fonts
# so the Preferences font list (fixed-pitch filter) has something to filter.
os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts"))

from PySide6.QtCore import QEventLoop  # noqa: E402
from PySide6.QtGui import QCloseEvent, QTextCursor  # noqa: E402
from PySide6.QtWidgets import QMessageBox, QPlainTextEdit  # noqa: E402

from mdviewer import app as app_module  # noqa: E402
from mdviewer import main_window  # noqa: E402
from mdviewer.core import settings  # noqa: E402

S = QMessageBox.StandardButton
FAILURES: list[str] = []
ERRORS: list[str] = []
ASKED: list[str] = []
FAKE = {"answer": S.Cancel, "open_path": "", "save_path": ""}


def check(condition, label: str) -> None:
    if not condition:
        FAILURES.append(label)


def pump(predicate, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while not predicate() and time.monotonic() < deadline:
        qt_app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
    return bool(predicate())


def page_js(view, script: str):
    """Evaluates `script` in the page's main world; JSON-serializable result (undefined -> None)."""
    box: list = []
    view.page().runJavaScript(f"JSON.stringify(({script}) ?? null)", 0, box.append)
    pump(lambda: box, 3)
    return json.loads(box[0]) if box and box[0] else None  # "" when JavaScript is off


def pull(view, timeout_s: float = 10) -> list:
    """request_document's callback arguments, after waiting for the first one."""
    got: list = []
    view.request_document(got.append)
    pump(lambda: got, timeout_s)
    return got


def record(view) -> list:
    """Every RichView signal as [name, *args], in arrival order."""
    seen: list = []
    for name in ("ready", "changed", "selectionState", "requestLinkDialog", "requestImageDialog", "openLink",
                 "hoverLink", "editProtected", "caretBlock", "load_failed", "crashed"):
        getattr(view, name).connect(lambda *args, name=name: seen.append([name, *args]))
    return seen


def names(seen: list) -> list[str]:
    return [entry[0] for entry in seen]


def fake_ask(box):
    ASKED.append(box.text())
    hook = FAKE.pop("during_ask", None)  # runs "while the dialog is open" (Task 11)
    if hook:
        hook()
    return FAKE["answer"]


main_window.ask = fake_ask
main_window.show_error = lambda parent, text: ERRORS.append(text)
main_window.pick_open_path = lambda parent: FAKE["open_path"]
main_window.pick_save_path = lambda parent, start: FAKE["save_path"]
PREFS_DIALOGS: list = []


def fake_prefs(dialog):
    """Stand-in for the modal Preferences dialog. FAKE["prefs"] edits it, then 'OK'.

    The hook may return False to cancel; no hook at all also cancels."""
    PREFS_DIALOGS.append(dialog)
    hook = FAKE.pop("prefs", None)
    if hook is None:
        return False
    return hook(dialog) is not False


main_window.run_preferences = fake_prefs
FAKE["system_theme"] = "light"
main_window.read_system_theme = lambda: FAKE["system_theme"]  # never read the real registry

qt_app, window = app_module.build([])
check(app_module.icon_path().is_file() and not qt_app.windowIcon().isNull(), "application window icon is set")
END = QTextCursor.MoveOperation.End
START = QTextCursor.MoveOperation.Start

sample = TMP / "sample.md"
sample.write_bytes("# Café\r\n\r\nline\u00a0two\r\n".encode("utf-8"))
SAMPLE_TEXT = "# Café\n\nline\u00a0two\n"

# --- Startup state ---------------------------------------------------------
window.show()  # shown like the app: Chromium throttles the timers of hidden pages
check(window.mode == "rendered", "starts in Rendered mode")
check(window.stack.currentWidget() is window.rich, "the Rendered editor is shown at startup")
check(window.windowTitle() == "Untitled - MD Viewer", "Untitled title at startup")
check(pump(lambda: window.rich.is_ready, 5), "the Rendered editor page is ready")

# --- Menus and shortcuts (spec section 3; v2 spec section 2) ----------------
check(
    [a.text() for a in window.menuBar().actions()] == ["&File", "&Edit", "&View", "&Help"],
    "menu bar is File / Edit / View / Help",
)
for act, keys in [
    (window.act_new, "Ctrl+N"), (window.act_open, "Ctrl+O"),
    (window.act_save, "Ctrl+S"), (window.act_save_as, "Ctrl+Shift+S"),
    (window.act_close, "Ctrl+W"), (window.act_exit, "Alt+F4"),
    (window.act_undo, "Ctrl+Z"), (window.act_redo, "Ctrl+Y"),
    (window.act_cut, "Ctrl+X"), (window.act_copy, "Ctrl+C"),
    (window.act_paste, "Ctrl+V"), (window.act_find, "Ctrl+F"),
    (window.act_replace, "Ctrl+H"), (window.act_select_all, "Ctrl+A"),
    (window.act_rendered, "Ctrl+P"), (window.act_source, "Ctrl+E"),
    (window.act_zoom_in, "Ctrl+="), (window.act_zoom_out, "Ctrl+-"),
    (window.act_zoom_reset, "Ctrl+0"),
]:
    check(act.shortcut().toString() == keys, f"{act.text()} shortcut is {keys}")
check([a.text() for a in window.menu_view.actions()[:2]] == ["&Rendered", "&Source"], "View menu starts with Rendered / Source")
check(window.act_rendered.isChecked() and window.act_rendered.actionGroup().isExclusive(), "the two modes are a radio pair")
check(window.act_copy.isEnabled(), "Copy enabled in Rendered mode")
check(window.act_cut.isEnabled() and window.act_paste.isEnabled() and window.act_select_all.isEnabled(),
      "Cut, Paste and Select All enabled in Rendered mode")
check(window.act_zoom_in.isEnabled(), "Zoom enabled in Rendered mode")
check(window.act_wrap.isChecked(), "Word Wrap on by default")

# --- Open: Rendered mode, encoding, CRLF, NBSP, title, status bar ------------
check(window.open_file(sample), "open_file returns True")
check(window.mode == "rendered" and window.stack.currentWidget() is window.rich, "a file opens in Rendered mode")
check(window.buffer == SAMPLE_TEXT, "buffer uses \\n breaks and keeps NBSP")
check(window.newline == "\r\n", "CRLF newline style detected")
check(window.encoding == "utf-8", "UTF-8 detected")
check(window.windowTitle() == "sample.md - MD Viewer", "title shows file name")
check(window._left_label.text() == "Rendered", "status left shows Rendered")
size = len(sample.read_bytes())
check(window._right_label.text() == f"100% | UTF-8 | {size} B", "status right shows zoom, encoding, size")
check(page_js(window.rich, "document.querySelector('#editor h1')?.textContent") == "Café", "the editor page shows the file")

# --- Open failure keeps the current document --------------------------------
ERRORS.clear()
check(not window.open_file(TMP / "missing.md"), "missing file returns False")
check(len(ERRORS) == 1 and "File not found." in ERRORS[0], "missing-file error uses Notepad wording")
check(window.loaded_path == sample, "failed open keeps the current document")

# --- Switching without edits never touches the buffer (v2 spec section 2) ----
window.act_source.trigger()
check(window.mode == "source" and window.stack.currentIndex() == 1, "Source shows the plain-text editor")
check(window.buffer == SAMPLE_TEXT and not window.dirty, "Rendered -> Source without edits keeps the buffer")
check(window.act_undo.isEnabled() and window.act_paste.isEnabled(), "edit actions enabled in Source mode")
check(window.act_copy.isEnabled(), "Copy enabled in Source mode")
check(not window.act_zoom_in.isEnabled(), "Zoom disabled in Source mode")
check(window.act_find.isEnabled() and window.act_replace.isEnabled(), "Find/Replace enabled in Source mode")
window.editor.moveCursor(START)
check(window._left_label.text() == "Ln 1, Col 1", "status shows Ln 1, Col 1 at start")
window.editor.moveCursor(END)
check(window._left_label.text() == "Ln 4, Col 1", "status follows the cursor")
window.act_rendered.trigger()
check(window.mode == "rendered" and window.buffer == SAMPLE_TEXT and not window.dirty, "Source -> Rendered keeps the buffer")
window.act_source.trigger()
check(window.buffer == SAMPLE_TEXT, "and back: still byte-identical")

# --- The caret maps across a switch by top-level block -----------------------
window.editor.setTextCursor(QTextCursor(window.editor.document().findBlockByNumber(2)))  # "line\u00a0two"
window.act_rendered.trigger()
check(pump(lambda: window._caret_block == 1, 3), "Source -> Rendered puts the caret in the block of the source line")
window.rich.focus_block(0)
check(pump(lambda: window._caret_block == 0, 3), "the Rendered caret moves")
window.rich.focus_block(1)
pump(lambda: window._caret_block == 1, 3)
window.act_source.trigger()
check(window.editor.textCursor().blockNumber() == 2, "Rendered -> Source puts the caret on the block's first line")

# --- Dirty carries across switches, with no prompt ---------------------------
window.editor.moveCursor(END)
window.editor.insertPlainText("edited\n")
check(window.dirty, "typing marks the buffer dirty")
check(window.windowTitle() == "*sample.md - MD Viewer", "dirty title has * prefix")
ASKED.clear()
window.act_rendered.trigger()
check(not ASKED and window.mode == "rendered" and window.dirty, "switching asks nothing and keeps the buffer dirty")
check(window.windowTitle() == "*sample.md - MD Viewer", "the * stays in Rendered mode")
window.act_source.trigger()
check(window.buffer == SAMPLE_TEXT + "edited\n" and window.dirty, "unedited Rendered mode hands the same text back")
check(not window.editor.document().isUndoAvailable(), "each switch starts a new undo history")

# --- Save keeps CRLF and NBSP ------------------------------------------------
check(window.on_save(), "Save in Source mode")
check(
    sample.read_bytes() == "# Café\r\n\r\nline\u00a0two\r\nedited\r\n".encode("utf-8"),
    "save writes CRLF and NBSP exactly",
)
check(not window.dirty and window.windowTitle() == "sample.md - MD Viewer", "title clean after save")

# --- Rendered edits: Save pulls and serializes, editing goes on (v2 spec 6.4) -
window.act_rendered.trigger()
window.rich.focus_block(0)
window.rich.command("setBlock", {"type": "heading", "level": 2})
check(pump(lambda: window.dirty, 3), "an edit in Rendered mode marks the buffer dirty")
check(window.windowTitle() == "*sample.md - MD Viewer", "and shows the * prefix")
check(not window.on_save(), "Save with unpulled edits returns before the pull")
check(pump(lambda: not window.dirty, 5), "the pulled document is saved")
RENDERED_SAVED = "## Café\n\nline\u00a0two edited\n"  # normalized: the soft break becomes a space
check(sample.read_bytes() == RENDERED_SAVED.replace("\n", "\r\n").encode("utf-8"),
      "Save writes normalized Markdown with the file's CRLF and NBSP")
check(window.buffer == RENDERED_SAVED and window.mode == "rendered", "the buffer holds the saved text")
check(page_js(window.rich, "window.mdEditor.command('undo')") is True, "Save keeps the Rendered undo history")
check(pump(lambda: window.dirty, 3), "the first edit after a save marks the buffer dirty again")
window.act_source.trigger()
check(pump(lambda: window.mode == "source", 5), "Rendered -> Source with edits switches once the pull is done")
check(window.buffer == "# Café\n\nline\u00a0two edited\n" and window.dirty, "the Source text has the edits, still unsaved")
check(window.editor.document().isModified() and not window.editor.document().isUndoAvailable(),
      "the editor marks it unsaved, with a new undo history")
check(window.editor.textCursor().blockNumber() == 0, "the caret lands on the edited block's line")

# --- Unencodable text in a Windows-1252 file --------------------------------
legacy = TMP / "legacy.md"
legacy.write_bytes(b"caf\xe9\n")
window.open_file(legacy)
check(window.encoding == "windows-1252", "Windows-1252 detected")
check("Windows-1252" in window._right_label.text(), "status shows Windows-1252")
window.act_source.trigger()
window.editor.moveCursor(START)
window.editor.insertPlainText("日本")
FAKE["answer"] = S.Cancel
check(not window.on_save(), "declined unencodable save returns False")
check(legacy.read_bytes() == b"caf\xe9\n", "declined unencodable save leaves the file untouched")
check(window.dirty, "declined unencodable save keeps the buffer dirty")
FAKE["answer"] = S.Yes
check(window.on_save(), "accepting the UTF-8 offer saves")
check(legacy.read_bytes() == "日本café\n".encode("utf-8"), "file rewritten as UTF-8")
check(window.encoding == "utf-8", "encoding switches to UTF-8 after the offer")

# --- New / Save As on Untitled ----------------------------------------------
window.on_new()
check(window.mode == "rendered" and window.stack.currentWidget() is window.rich, "New opens in Rendered mode")
check(window.loaded_path is None and window.buffer == "", "New gives an empty Untitled buffer")
check(window.windowTitle() == "Untitled - MD Viewer", "New shows Untitled title")
window.act_source.trigger()
window.editor.insertPlainText("hello")
FAKE["save_path"] = ""
check(not window.on_save(), "cancelled Save As returns False")
check(window.dirty, "cancelled Save As keeps dirty")
FAKE["save_path"] = str(TMP / "fresh")
check(window.on_save(), "Save on Untitled acts as Save As")
check((TMP / "fresh.md").read_bytes() == b"hello", "Save As appends .md and writes the buffer")
check(window.windowTitle() == "fresh.md - MD Viewer", "title follows Save As path")

# --- New while dirty: Cancel keeps the buffer -------------------------------
window.editor.insertPlainText("!")
FAKE["answer"] = S.Cancel
window.on_new()
check(window.loaded_path == TMP / "fresh.md" and window.dirty, "cancelled New keeps the buffer")

# --- Open from Source mode lands in Rendered mode ---------------------------
FAKE["answer"] = S.Discard
FAKE["open_path"] = str(sample)
window.on_open()
check(window.loaded_path == sample, "File > Open loads the picked file")
check(window.mode == "rendered" and window.stack.currentWidget() is window.rich, "open from Source mode shows Rendered")
check(window.act_rendered.isChecked(), "open from Source mode checks Rendered")

# --- Drag-and-drop with a dirty buffer --------------------------------------
window.act_source.trigger()
window.editor.insertPlainText("x")
FAKE["answer"] = S.Cancel
window._open_dropped([str(legacy)])
check(window.loaded_path == sample and window.dirty, "cancelled drop keeps the document")
FAKE["answer"] = S.Discard
window._open_dropped([str(legacy)])
check(window.loaded_path == legacy and window.mode == "rendered", "drop opens the file in Rendered mode")

# --- Files dropped on the editor page open; web links stay in the page --------
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDragEnterEvent, QDropEvent  # noqa: E402


def drop_on_page(url: QUrl) -> None:
    """A drag from Explorer: DragEnter then Drop on the page's focus proxy (Qt needs both)."""
    mime = QMimeData()
    mime.setUrls([url])
    for kind in (QDragEnterEvent, QDropEvent):
        qt_app.sendEvent(window.rich.focusProxy(), kind(QPointF(40, 40), Qt.DropAction.CopyAction, mime,
                                                        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    pump(lambda: False, 0.3)  # the open is deferred to the next event-loop turn


drop_on_page(QUrl.fromLocalFile(str(sample)))
check(window.loaded_path == sample and window.mode == "rendered", "a file dropped on the Rendered page opens")
drop_on_page(QUrl("https://example.com/page.md"))
check(window.loaded_path == sample, "a web link dropped on the page opens nothing")
ASKED.clear()
FAKE["answer"] = S.Retry  # the crash dialog (Task 14): reload the page
os.kill(window.rich.page().renderProcessPid(), signal.SIGTERM)  # a crash replaces the focus proxy
check(pump(lambda: ASKED, 5), "a crash asks")
check(pump(lambda: window.rich.is_ready and window.rich.focusProxy() is not None, 5), "the restarted page is ready")
drop_on_page(QUrl.fromLocalFile(str(legacy)))
check(window.loaded_path == legacy, "files dropped on a restarted page still open")

# --- Window close with unsaved changes --------------------------------------
window.act_source.trigger()
window.editor.insertPlainText("unsaved")
FAKE["answer"] = S.Cancel
event = QCloseEvent()
window.closeEvent(event)
check(not event.isAccepted(), "Cancel on close keeps the window open")
FAKE["answer"] = S.Discard
event = QCloseEvent()
window.closeEvent(event)
check(event.isAccepted(), "Don't Save on close lets the window close")

# --- File > Close resets to a fresh state -----------------------------------
window.on_close()  # still dirty: FAKE answer is Discard
check(window.loaded_path is None and window.buffer == "", "Close empties the buffer")
check(window.mode == "rendered" and not window.dirty, "Close returns to a clean Rendered page")
check(window.windowTitle() == "Untitled - MD Viewer", "Close shows Untitled title")

# --- Zoom -------------------------------------------------------------------
window._zoom_in()
check(window._zoom == 1.25, "Zoom In multiplies by 1.25")
check(window._left_label.text() == "Rendered 125%", "status left shows zoom when not 100%")
check(window._right_label.text().startswith("125% | "), "status right shows zoom")
for _ in range(20):
    window._zoom_in()
check(window._zoom == 3.0, "zoom clamps at 300%")
for _ in range(40):
    window._zoom_out()
check(window._zoom == 0.25, "zoom clamps at 25%")
window._zoom_reset()
check(window._zoom == 1.0 and window.rich.zoomFactor() == 1.0, "Zoom Reset returns to 100%")

# --- Word Wrap --------------------------------------------------------------
window.act_wrap.setChecked(False)
check(window.editor.lineWrapMode() == QPlainTextEdit.LineWrapMode.NoWrap, "Word Wrap off")
window.act_wrap.setChecked(True)
check(window.editor.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth, "Word Wrap on")

# --- Settings: geometry, zoom, theme ----------------------------------------
data = {
    "theme": "dark",
    "window": {"x": 100, "y": 120, "width": 640, "height": 480},
    "preview_zoom": 1.5,
    "recent_files": [str(TMP / "r1.md"), str(TMP / "r2.md")],
    "editor_font": {"family": "Courier New", "size": 14},
    "show_toolbar": False,
}
restored = main_window.MainWindow(data)
check(restored.settings_snapshot() == data, "settings snapshot round-trips constructor data")
lost = main_window.MainWindow(
    {"theme": "system", "window": {"x": -50000, "y": -50000, "width": 640, "height": 480}, "preview_zoom": 1.0}
)
check(lost.pos().x() > -50000, "off-screen geometry is not restored")
app_module.save_settings(restored)
check(settings.load() == data, "save_settings writes settings.json")
original_save = settings.save


def broken_save(path, data):
    raise PermissionError("read-only")


settings.save = broken_save
try:
    app_module.save_settings(restored)
    survived = True
except OSError:
    survived = False
settings.save = original_save
check(survived, "save_settings swallows write errors on exit")

# --- WYSIWYG Task 13: the Rendered editor in the window -----------------------
from mdviewer import richview  # noqa: E402
from mdviewer.core import docmodel, render, serialize  # noqa: E402

check(isinstance(window.rich, richview.RichView), "the Rendered view is a RichView")
doc_md = TMP / "doc.md"
doc_md.write_text("# Title\n\n![pic](pic.png)\n\n[web](https://example.com)\n", encoding="utf-8")
FAKE["answer"] = S.Discard
check(window.open_file(doc_md), "open doc.md")
check(page_js(window.rich, "window.mdEditor.getDocument().content[1].content[0].attrs.display_src")
      == (TMP / "pic.png").as_uri(), "relative image resolved against the file's folder")
check(page_js(window.rich, "getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()")
      == render.PAGE_BACKGROUND["light"], "light theme by default")

# a file docmodel cannot load opens in Source mode; a switch to Rendered then stays in Source
def boom(*args, **kwargs):
    raise RuntimeError("docmodel bug")


original_from_markdown = docmodel.from_markdown
docmodel.from_markdown = boom
window.statusBar().clearMessage()
check(window.open_file(doc_md), "a file docmodel cannot load still opens")
check(window.mode == "source" and window.buffer == doc_md.read_text(encoding="utf-8"), "it opens in Source mode")
check(window.statusBar().currentMessage() == main_window.OPEN_FAILED_NOTE, "with the Source-mode warning")
window.act_rendered.trigger()
check(window.mode == "source" and window.act_source.isChecked(), "a switch to Rendered that cannot load stays in Source")
check(window.statusBar().currentMessage() == main_window.SWITCH_FAILED_NOTE, "and says so")
docmodel.from_markdown = original_from_markdown

# files larger than 5 MB open in Source mode, smaller ones in Rendered mode
saved_limit = main_window.LARGE_FILE_BYTES
main_window.LARGE_FILE_BYTES = 10
small, large = TMP / "ten.md", TMP / "eleven.md"
small.write_bytes(b"0123456789")
large.write_bytes(b"0123456789\n")
window.statusBar().clearMessage()
check(window.open_file(small) and window.mode == "rendered", "a file at the limit opens in Rendered mode")
check(window.open_file(large) and window.mode == "source", "a file over the limit opens in Source mode")
check(window.statusBar().currentMessage() == "Large file: opened in Source mode", "with the large-file note")
window.act_rendered.trigger()
check(window.mode == "rendered", "a large file can still be switched to Rendered mode")
main_window.LARGE_FILE_BYTES = saved_limit
check(saved_limit == 5 * 1024 * 1024, "the limit is 5 MB")

# a Rendered edit, not yet saved (pulls that get no answer: Task 14 section)
window.open_file(doc_md)
window.rich.focus_block(0)
window.rich.command("setBlock", {"type": "heading", "level": 3})
pump(lambda: window.dirty, 3)
saved_timeout = richview.PULL_TIMEOUT_MS

# a serializer failure saves nothing and keeps the edits for the next try
def bad_to_text(doc):
    raise ValueError("serializer bug")


ERRORS.clear()
original_to_text = serialize.to_text
serialize.to_text = bad_to_text
window.on_save()
check(pump(lambda: ERRORS, 3) and "could not be converted to Markdown" in ERRORS[0], "a serializer failure is reported")
serialize.to_text = original_to_text
check(doc_md.read_text(encoding="utf-8").startswith("# Title") and window.dirty, "nothing was saved")
window.on_save()
check(pump(lambda: not window.dirty, 5) and doc_md.read_text(encoding="utf-8").startswith("### Title"),
      "the next Save writes the edits")

# a pull in flight: other pulls are dropped; a pull of a replaced document is discarded
window.rich.focus_block(0)
window.rich.command("setBlock", {"type": "heading", "level": 1})
pump(lambda: window.dirty, 3)
window.rich.page().runJavaScript("(() => { const t = Date.now(); while (Date.now() - t < 600); })()", 0)
window.on_save()
window.act_source.trigger()
check(window.mode == "rendered" and window.act_rendered.isChecked(), "a switch while a pull is in flight is dropped")
check(pump(lambda: not window.dirty, 5) and doc_md.read_text(encoding="utf-8").startswith("# Title"), "the first pull saves")
window.rich.command("setBlock", {"type": "heading", "level": 2})
pump(lambda: window.dirty, 3)
window.rich.page().runJavaScript("(() => { const t = Date.now(); while (Date.now() - t < 600); })()", 0)
window.on_save()
window.open_file(sample)
pump(lambda: False, 1)
check(window.buffer == RENDERED_SAVED and doc_md.read_text(encoding="utf-8").startswith("# Title"),
      "a pull from a document replaced meanwhile is discarded")

# a load drops the pull in flight: the new document saves at once, and the dropped pull's late
# timeout does not mark it modified (an unedited file must never be rewritten)
window.rich.focus_block(0)
window.rich.command("setBlock", {"type": "heading", "level": 1})
pump(lambda: window.dirty, 3)
richview.PULL_TIMEOUT_MS = 300
window.rich.page().runJavaScript("(() => { const t = Date.now(); while (Date.now() - t < 1200); })()", 0)
window.on_save()
check(window._pending_pull, "a pull is in flight")
window.open_file(sample)
check(not window._pending_pull, "a load clears the pull in flight")
pump(lambda: False, 1.8)
richview.PULL_TIMEOUT_MS = saved_timeout
check(not window.rich.modified and not window.dirty, "a late timeout of a dropped pull leaves the new document clean")

# an edit that lands between a pull's snapshot and its callback is not lost
PULLS: list = []
_request_document = richview.RichView.request_document


def _counted_request_document(self, callback):
    PULLS.append(1)
    _request_document(self, callback)


richview.RichView.request_document = _counted_request_document


def edit_after_next_snapshot() -> None:
    """The next pull's snapshot is followed by a keystroke before Python's callback runs."""
    real = window.rich.request_document  # the counted class method, bound

    def request(callback):
        del window.rich.request_document

        def late(doc):
            window.rich.modified = True  # changed() arrives after the snapshot
            window._on_rendered_changed()
            callback(doc)
        real(late)
    window.rich.request_document = request


window.rich.focus_block(0)
window.rich.command("setBlock", {"type": "heading", "level": 2})
pump(lambda: window.dirty, 3)
edit_after_next_snapshot()
window.on_save()
check(pump(lambda: not window._pending_pull, 5) and sample.read_bytes().startswith(b"## "), "the snapshot is saved")
check(window.dirty and window.windowTitle().startswith("*"), "an edit made after the snapshot keeps the buffer dirty")
window.open_file(sample)
window.rich.focus_block(0)
window.rich.command("setBlock", {"type": "heading", "level": 3})
pump(lambda: window.dirty, 3)
PULLS.clear()
edit_after_next_snapshot()
window.act_source.trigger()
check(pump(lambda: window.mode == "source", 5), "the switch to Source completes")
check(len(PULLS) == 2 and not window.rich.modified, "a switch pulls again when an edit landed after the snapshot")

# a page that never loads: Source mode only, with a warning
saved_web = render.WEB_DIR
render.WEB_DIR = TMP / "no-web"
broken = main_window.MainWindow({"theme": "light", "window": None, "preview_zoom": 1.0})
render.WEB_DIR = saved_web
check(pump(lambda: broken.rich.failed, 2) and broken.mode == "source", "a page that never loads leaves Source mode")
check(not broken.act_rendered.isEnabled(), "Rendered is greyed for the session")
check(broken.statusBar().currentMessage() == main_window.EDITOR_FAILED_NOTE, "with a warning")
check(broken.open_file(doc_md) and broken.mode == "source", "files then open in Source mode")


# --- Task 10: editor intelligence ---------------------------------------------
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QTextCharFormat  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from mdviewer import editor as editor_module  # noqa: E402

ed = window.editor
check(isinstance(ed, editor_module.MarkdownEditor), "editor is a MarkdownEditor")
window.show()  # the completer popup only opens for a visible editor
FAKE["answer"] = S.Discard
window.on_new()
window.act_source.trigger()
qt_app.processEvents()
LIGHT = editor_module.COLORS["light"]
WAVE = QTextCharFormat.UnderlineStyle.WaveUnderline


def reset(text: str = "") -> None:
    ed.completer.popup().hide()
    ed.setPlainText(text)
    ed.moveCursor(END)
    ed.highlighter.refresh_issues()


def cur_line() -> str:
    return ed.textCursor().block().text()


def cur_col() -> int:
    return ed.textCursor().positionInBlock()


def block_formats(number: int):
    # Copy each format: r.format dangles once the temporary FormatRange list is freed.
    return [QTextCharFormat(r.format) for r in ed.document().findBlockByNumber(number).layout().formats()]


def has_wave(number: int, color: str) -> bool:
    return any(f.underlineStyle() == WAVE and f.underlineColor().name() == color for f in block_formats(number))


# auto-close
reset()
QTest.keyClicks(ed, "(")
check(ed.toPlainText() == "()" and cur_col() == 1, "( inserts a pair")
QTest.keyClicks(ed, ")")
check(ed.toPlainText() == "()" and cur_col() == 2, ") types over the closer")
reset()
QTest.keyClicks(ed, "[")
QTest.keyClick(ed, Qt.Key.Key_Backspace)
check(ed.toPlainText() == "", "Backspace removes an empty pair")
reset()
QTest.keyClicks(ed, "my_var")
check(ed.toPlainText() == "my_var", "_ inside a word is not paired")
reset()
QTest.keyClicks(ed, "* item")
check(ed.toPlainText() == "* item", "* bullet at line start is not paired")
reset()
QTest.keyClicks(ed, "a `")
check(ed.toPlainText() == "a ``", "backtick after a space is paired")

# completion popup
reset()
QTest.keyClicks(ed, "```")
check(ed.toPlainText() == "```", "typing ``` gives exactly three backticks")
check(ed.completer.popup().isVisible(), "``` opens the fence-language popup")
QTest.keyClicks(ed, "py")
check(ed.completer.completionCount() == 1, "typing narrows fence languages")
ed._insert_completion("python")
check(cur_line() == "```python" and cur_col() == 9, "fence language completes in place")
reset()
QTest.keyClicks(ed, "#")
check(ed.completer.popup().isVisible() and ed.completer.completionCount() == 6, "# offers six heading levels")
ed._insert_completion("## ")
check(cur_line() == "## " and cur_col() == 3, "heading completion replaces the # run")
reset()
QTest.keyClicks(ed, "- ")
check(not ed.completer.popup().isVisible(), "typing a space closes the popup")
reset("| a | b |")
QTest.keyClick(ed, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
check(ed.completer.popup().isVisible(), "Ctrl+Space opens the popup")
ed._insert_completion("| --- | --- |")
check(ed.toPlainText() == "| a | b |\n| --- | --- |", "table separator row goes on a new line")
reset("```python\n")
QTest.keyClicks(ed, "#")
check(not ed.completer.popup().isVisible(), "no heading popup inside a fenced block")

# Enter continuation
reset("- item")
QTest.keyClick(ed, Qt.Key.Key_Return)
check(ed.toPlainText() == "- item\n- ", "Enter continues a bullet list")
QTest.keyClick(ed, Qt.Key.Key_Return)
check(ed.toPlainText() == "- item\n\n", "Enter on an empty item exits the list")
reset("1. one")
QTest.keyClick(ed, Qt.Key.Key_Return)
check(ed.toPlainText() == "1. one\n2. ", "Enter increments ordered lists")
reset("> q")
QTest.keyClick(ed, Qt.Key.Key_Return)
check(ed.toPlainText() == "> q\n> ", "Enter continues a quote")
reset("```\n- item")
QTest.keyClick(ed, Qt.Key.Key_Return)
check(ed.toPlainText() == "```\n- item\n", "no list continuation inside a fence")
reset("- item")
QTest.keyClick(ed, Qt.Key.Key_Return)
ed.undo()
check(ed.toPlainText() == "- item", "one undo reverts an Enter continuation")
reset("a")
QTest.keyClick(ed, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
check(window.buffer == "a\n", "Shift+Enter inserts a plain line break")

# highlighting and underlines
reset("# Title\n\ntext")
check(any(f.foreground().color().name() == LIGHT["heading"] for f in block_formats(0)), "headings are colored")
check(not any(f.underlineStyle() == WAVE for n in range(3) for f in block_formats(n)), "clean text has no underlines")
reset("```python\nx = 1\n")
check(has_wave(0, LIGHT["error"]), "unclosed fence gets a red wavy underline")
check(ed.highlighter.message_at(1, 0) == "Unclosed fenced code block", "issue message available for the tooltip")
reset("#Title")
check(has_wave(0, LIGHT["warning"]), "heading without space gets an orange wavy underline")
cursor = ed.textCursor()
cursor.setPosition(1)
cursor.insertText(" ")
ed.highlighter.refresh_issues()
check(not has_wave(0, LIGHT["warning"]), "fixing the line removes its underline")
ed.set_theme("dark")
reset("# T")
check(
    any(f.foreground().color().name() == editor_module.COLORS["dark"]["heading"] for f in block_formats(0)),
    "dark theme recolors the editor",
)
ed.set_theme("light")
FAKE["answer"] = S.Discard
window.on_close()

# --- Task 11: file watching -----------------------------------------------------
check(window._watch_timer.interval() == 1000 and window._watch_timer.isActive(), "watcher polls every 1000 ms")
window._watch_timer.stop()  # the checks below poll by hand; pump() would let the timer poll too
watched = TMP / "watched.md"
watched.write_bytes(b"one\n")
FAKE["answer"] = S.Discard
window.open_file(watched)
ASKED.clear()
window._poll_disk()
check(window.buffer == "one\n" and not ASKED, "unchanged file: nothing happens")

# Rendered mode, no edits: silent reload
watched.write_bytes(b"two two\n")
window._poll_disk()
check(window.buffer == "two two\n" and window.mode == "rendered", "Rendered mode reloads silently")
check(page_js(window.rich, "document.querySelector('#editor p')?.textContent") == "two two", "the page shows the new text")
check(not ASKED and not window.dirty, "silent reload asks nothing")

# own save is not an external change
window.act_source.trigger()
window.editor.moveCursor(END)
window.editor.insertPlainText("mine\n")
check(window.on_save(), "save in edit mode")
window._poll_disk()
check(not ASKED, "own save does not trigger the dialog")

# edit mode: dialog first, then Reload
watched.write_bytes(b"external 1\n")
FAKE["answer"] = S.Yes
window._poll_disk()
check(len(ASKED) == 1 and '"watched.md" was modified externally at' in ASKED[0], "Source mode asks before replacing")
check(window.buffer == "external 1\n" and not window.dirty, "Reload loads the disk content")
check(window.mode == "source", "Reload stays in Source mode")

# Keep my version
ASKED.clear()
watched.write_bytes(b"external 22\n")
FAKE["answer"] = S.No
window._poll_disk()
check(len(ASKED) == 1 and window.buffer == "external 1\n", "Keep my version leaves the buffer")
check(window.dirty and window.windowTitle().startswith("*"), "Keep my version marks the buffer unsaved")
window._poll_disk()
check(len(ASKED) == 1, "no repeat dialog without a new change")
watched.write_bytes(b"external 333\n")
window._poll_disk()
check(len(ASKED) == 2, "the next external change asks again")

# dialogs never stack
ASKED.clear()


def change_during_dialog():
    watched.write_bytes(b"during the dialog\n")
    window._poll_disk()


FAKE["during_ask"] = change_during_dialog
watched.write_bytes(b"external 4444\n")
FAKE["answer"] = S.No
window._poll_disk()
check(len(ASKED) == 1, "polls while the dialog is open do not stack dialogs")
FAKE["answer"] = S.Yes
window._poll_disk()
check(len(ASKED) == 2 and window.buffer == "during the dialog\n", "a change made during the dialog is picked up next")

# missing file: one warning, then recovery
window.act_rendered.trigger()
ASKED.clear()
watched.unlink()
window.statusBar().clearMessage()
window._poll_disk()
check("not found on disk" in window.statusBar().currentMessage(), "missing file warns")
window.statusBar().clearMessage()
window._poll_disk()
check(window.statusBar().currentMessage() == "", "missing-file warning is shown once")
watched.write_bytes(b"back again\n")
window._poll_disk()
check(window.buffer == "back again\n", "reappearing file reloads")

# Save recreates a deleted file without a false alarm
window.act_source.trigger()
watched.unlink()
window._poll_disk()
window.editor.insertPlainText("x")
check(window.on_save() and watched.exists(), "Save recreates a deleted file")
window._poll_disk()
check(not ASKED, "recreating save raises no change dialog")

# a Rendered-mode read failure is retried on the next tick
window.act_rendered.trigger()
before_lock = window.buffer
window._read_disk = lambda: None
watched.write_bytes(b"locked content!\n")
window.statusBar().clearMessage()
window._poll_disk()
check("Could not read" in window.statusBar().currentMessage(), "read failure warns")
check(window.buffer == before_lock, "read failure keeps the last version")
del window._read_disk
window._poll_disk()
check(window.buffer == "locked content!\n", "the failed read is retried on the next tick")

# Save As: the watcher follows the new path
moved = TMP / "moved.md"
FAKE["save_path"] = str(moved)
check(window.on_save_as(), "Save As to a new path")
watched.write_bytes(b"old path changed\n")
window._poll_disk()
check(window.loaded_path == moved and window.buffer == "locked content!\n", "old path is no longer watched")
moved.write_bytes(b"new path changed\n")
window._poll_disk()
check(window.buffer == "new path changed\n", "watcher follows the Save As path")

# Rendered mode with edits: the dialog, as in Source mode (v2 spec section 2)
window.rich.focus_block(0)
window.rich.command("setBlock", {"type": "heading", "level": 1})
check(pump(lambda: window.dirty, 3), "a Rendered edit marks the buffer dirty")
ASKED.clear()
moved.write_bytes(b"changed under an edit\n")
FAKE["answer"] = S.No
window._poll_disk()
check(len(ASKED) == 1 and window.mode == "rendered" and window.dirty, "Rendered mode with edits asks first")
check(page_js(window.rich, "document.querySelector('#editor h1')?.textContent") == "new path changed",
      "Keep my version keeps the edited page")
moved.write_bytes(b"changed again\n")
FAKE["answer"] = S.Yes
window._poll_disk()
check(len(ASKED) == 2 and window.buffer == "changed again\n" and not window.dirty, "Reload replaces the edits")
check(window.mode == "rendered" and page_js(window.rich, "document.querySelector('#editor p')?.textContent")
      == "changed again", "the page shows the reloaded file")

# Untitled: nothing to watch
window.on_close()
window._poll_disk()
check(window._watcher is None, "no watcher for Untitled")

# --- Task 12: find / replace ------------------------------------------------------
bar = window.find_bar
FAKE["answer"] = S.Discard
window.on_close()
check(window.act_find.isEnabled() and window.act_replace.isEnabled(), "Find and Replace enabled in Rendered mode")
window.on_new()
window.act_source.trigger()
check(window.act_find.isEnabled() and window.act_replace.isEnabled(), "Find/Replace enabled in Source mode")
check(not bar.isVisible(), "find bar hidden by default")


def selected() -> str:
    return window.editor.textCursor().selectedText()


window.editor.setPlainText("\U0001F600 alpha beta Alpha\nalpha")
window.editor.moveCursor(START)
window.act_find.trigger()
check(bar.isVisible() and not bar.replace_row.isVisible(), "Ctrl+F shows the find row only")
bar.find_edit.setText("alpha")
check(selected() == "alpha" and bar.count_label.text() == "1 of 3", "typing selects the first match after an emoji")
bar.find_next()
check(selected() == "Alpha" and bar.count_label.text() == "2 of 3", "Next is case-insensitive by default")
bar.find_next()
check(bar.count_label.text() == "3 of 3", "Next reaches the last match")
bar.find_next()
check(bar.count_label.text() == "1 of 3", "Next wraps to the first match")
bar.find_previous()
check(bar.count_label.text() == "3 of 3", "Previous wraps to the last match")
bar.case_box.setChecked(True)
check(bar.count_label.text() == "2 of 2", "Match case narrows the matches")
bar.case_box.setChecked(False)
bar.find_edit.setText("zzz")
check(bar.count_label.text() == "No results", "no hits shows No results")
check(window.buffer == "\U0001F600 alpha beta Alpha\nalpha", "a failed search leaves the text alone")
bar.find_edit.setText("")
check(bar.count_label.text() == "", "empty search clears the count")
check(not bar.find_next(), "Next with an empty field does nothing")

window.editor.moveCursor(START)
window.act_replace.trigger()
check(bar.isVisible() and bar.replace_row.isVisible(), "Ctrl+H shows the replace row")
bar.find_edit.setText("beta")
bar.replace_edit.setText("BETA")
bar.replace_one()
check(window.buffer == "\U0001F600 alpha BETA Alpha\nalpha", "Replace swaps the selected match")
bar.find_edit.setText("a")
bar.replace_edit.setText("aa")
check(bar.replace_all() == 7, "Replace All counts every match once")
check(window.buffer == "\U0001F600 aalphaa BETaa aalphaa\naalphaa", "Replace All terminates when the replacement contains the needle")
check(bar.count_label.text() == "7 replaced", "Replace All reports the count")
window.editor.undo()
check(window.buffer == "\U0001F600 alpha BETA Alpha\nalpha", "one undo reverts Replace All")

window.editor.setPlainText("one two")
window.editor.moveCursor(START)
cursor = window.editor.textCursor()
cursor.movePosition(QTextCursor.MoveOperation.NextWord, QTextCursor.MoveMode.KeepAnchor)
window.editor.setTextCursor(cursor)
bar.close_bar()
window.act_find.trigger()
check(bar.find_edit.text().strip() == "one", "the editor selection seeds the find field")
QTest.keyClick(bar.find_edit, Qt.Key.Key_Escape)
check(not bar.isVisible(), "Esc closes the bar")
FAKE["answer"] = S.Discard
window.on_close()

# --- Task 13: theme system ----------------------------------------------------------
from PySide6.QtGui import QPalette  # noqa: E402


def window_color() -> str:
    return qt_app.palette().color(QPalette.ColorRole.Window).name()


def heading_color(win) -> str:
    return win.editor.highlighter._formats["heading"].foreground().color().name()


def choose_theme(choice: str) -> None:
    """Pick a theme the way a user does: through the Preferences dialog, then OK."""
    FAKE["prefs"] = lambda dialog: dialog.set_theme_choice(choice)
    window.act_preferences.trigger()


DARK_WINDOW = main_window.DARK_PALETTE_COLORS["window"]
check(window._theme_choice == "system", "System (auto) is the default")
check(window._theme_timer.isActive() and window._theme_timer.interval() == 2000, "System mode polls every 2000 ms")

FAKE["answer"] = S.Discard
window.open_file(sample)
sample_before = sample.read_bytes()
sample.write_bytes(sample_before + b"on disk only\r\n")  # not polled: a theme switch must not reload
theme_loads: list = []
window.rich.loadStarted.connect(lambda: theme_loads.append(1))
FAKE["system_theme"] = "dark"
window._poll_theme()
check(window._effective_theme == "dark", "System mode follows Windows switching to dark")
check(qt_app.style().name().lower() == "fusion" and window_color() == DARK_WINDOW, "dark palette on the Fusion style")
check(pump(lambda: page_js(window.rich, "getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()")
           == "#0d1117", 3), "the editor page switches to the dark CSS")
check(page_js(window.rich, "document.body.innerText.includes('on disk only')") is False,
      "theme switch keeps the document, not the disk")
check(window.mode == "rendered" and not window.dirty, "theme switch keeps mode and dirty state")
check(heading_color(window) == editor_module.COLORS["dark"]["heading"], "editor recolored for dark")
sample.write_bytes(sample_before)

choose_theme("light")
check(window._effective_theme == "light" and window_color() != DARK_WINDOW, "forced Light applies the light palette")
check(not window._theme_timer.isActive(), "forced Light stops the system poll")
FAKE["system_theme"] = "dark"
window._poll_theme()
check(window._effective_theme == "light", "forced Light ignores the system theme")
check(window.settings_snapshot()["theme"] == "light", "forced Light is saved")

choose_theme("dark")
check(window._effective_theme == "dark" and not window._theme_timer.isActive(), "forced Dark applies without polling")
FAKE["system_theme"] = "light"
window._poll_theme()
check(window._effective_theme == "dark", "forced Dark ignores the system theme")

GRAY_WINDOW = main_window.GRAY_PALETTE_COLORS["window"]
choose_theme("gray")
check(window._effective_theme == "gray" and not window._theme_timer.isActive(), "forced Gray applies without polling")
check(qt_app.style().name().lower() == "fusion" and window_color() == GRAY_WINDOW, "gray palette on the Fusion style")
check(pump(lambda: page_js(window.rich, "getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()")
           == "#3a3d41", 3), "the editor page switches to the gray CSS")
check(theme_loads == [], "theme changes never reload the editor page")
check(heading_color(window) == editor_module.COLORS["gray"]["heading"], "editor recolored for gray")
FAKE["system_theme"] = "dark"
window._poll_theme()
check(window._effective_theme == "gray", "forced Gray ignores the system theme")
check(window.settings_snapshot()["theme"] == "gray", "forced Gray is saved")
FAKE["system_theme"] = "light"

choose_theme("system")
check(window._effective_theme == "light", "System (auto) applies the current system theme immediately")
check(window._theme_timer.isActive(), "System (auto) restarts the poll")
check(window.settings_snapshot()["theme"] == "system", "System (auto) is saved")

restarted = main_window.MainWindow({"theme": "dark", "window": None, "preview_zoom": 1.0})
check(restarted._theme_choice == "dark" and restarted._effective_theme == "dark", "saved Dark is restored")
check("#0d1117" in restarted.rich.page_file.read_text(encoding="utf-8"), "the startup editor page is already dark")
check(heading_color(restarted) == editor_module.COLORS["dark"]["heading"], "startup editor is already dark")
choose_theme("system")  # back to light for any later checks

# --- Open Recent (user-requested, between Tasks 13 and 14) -------------------------
def recent_entries(win):
    return [a for a in win.menu_recent.actions() if a.data()]


def recent_paths(win) -> list[str]:
    return [a.data() for a in recent_entries(win)]


def abs_(path) -> str:
    return os.path.abspath(str(path))


gone = TMP / "gone.md"
rw = main_window.MainWindow(
    {"theme": "light", "window": None, "preview_zoom": 1.0, "recent_files": [abs_(gone), abs_(sample)]}
)
check(rw.menu_file.actions()[rw.menu_file.actions().index(rw.act_open) + 1].menu() is rw.menu_recent, "Open Recent sits right below Open")
check(rw.menu_recent.title() == "Open &Recent", "submenu is titled Open Recent")
check([a.text() for a in recent_entries(rw)] == ["&1 gone.md", "&2 sample.md"], "entries are numbered, newest first")
check(recent_entries(rw)[1].toolTip() == abs_(sample), "tooltip shows the full path")
check(rw.menu_recent.isEnabled(), "Open Recent enabled when there are entries")
empty = main_window.MainWindow({"theme": "light", "window": None, "preview_zoom": 1.0})
check(not empty.menu_recent.isEnabled(), "Open Recent disabled when empty")

# opening records the file, de-duplicated, newest first
rdoc = TMP / "a&b.md"
rdoc.write_text("# R\n", encoding="utf-8")
check(rw.open_file(str(rdoc)), "open a file with & in its name")
check(recent_paths(rw) == [abs_(rdoc), abs_(gone), abs_(sample)], "opening a file puts it first")
check(recent_entries(rw)[0].text() == "&1 a&&b.md", "& in a file name is escaped in the menu")
check(rw.open_file(sample), "re-open sample")
check(recent_paths(rw) == [abs_(sample), abs_(rdoc), abs_(gone)], "re-opening moves the entry to the front")
check(rw.settings_snapshot()["recent_files"] == recent_paths(rw), "snapshot carries the recent list")

# a failed open is not recorded
ERRORS.clear()
check(not rw.open_file(TMP / "never-existed.md"), "failed open returns False")
check(abs_(TMP / "never-existed.md") not in recent_paths(rw), "failed open is not remembered")

# clicking an entry opens it (through the unsaved-changes prompt)
rw.act_source.trigger()
rw.editor.insertPlainText("dirty")
FAKE["answer"] = S.Cancel
ASKED.clear()
recent_entries(rw)[1].trigger()
check(len(ASKED) == 1 and rw.loaded_path == sample, "a dirty buffer is asked about before opening a recent file")
FAKE["answer"] = S.Discard
recent_entries(rw)[1].trigger()
check(rw.loaded_path == rdoc and rw.mode == "rendered", "clicking an entry opens it in Rendered mode")
check(recent_paths(rw)[0] == abs_(rdoc), "the opened entry moves to the front")

# a vanished file reports the error and drops its entry
ERRORS.clear()
entry = [a for a in recent_entries(rw) if a.data() == abs_(gone)][0]
entry.trigger()
check(len(ERRORS) == 1 and "File not found." in ERRORS[0], "a missing recent file shows the Notepad-style error")
check(abs_(gone) not in recent_paths(rw), "a missing recent file is removed from the list")

# Save As records the new path
rw.on_new()
rw.act_source.trigger()
rw.editor.insertPlainText("fresh")
saved_as = TMP / "recent-saved.md"
FAKE["save_path"] = str(saved_as)
check(rw.on_save(), "Save As from Untitled")
check(recent_paths(rw)[0] == abs_(saved_as), "a saved file is remembered")

# capped at ten
for i in range(12):
    extra = TMP / f"extra{i}.md"
    extra.write_text("x\n", encoding="utf-8")
    FAKE["answer"] = S.Discard
    rw.open_file(extra)
check(len(recent_paths(rw)) == 10 and recent_paths(rw)[0] == abs_(TMP / "extra11.md"), "the list holds the ten newest files")

# persisted and restored
app_module.save_settings(rw)
reloaded = main_window.MainWindow(settings.load())
check(recent_paths(reloaded) == recent_paths(rw), "the recent list survives a restart")

# Clear Recent Files
clear_act = rw.menu_recent.actions()[-1]
check(clear_act.text() == "&Clear Recent Files", "last item clears the list")
clear_act.trigger()
check(recent_paths(rw) == [] and not rw.menu_recent.isEnabled(), "Clear empties the list and disables the menu")
check(rw.settings_snapshot()["recent_files"] == [], "the cleared list is what gets saved")

# --- Preferences dialog (user-requested, between Tasks 13 and 14) ----------------------
from PySide6.QtGui import QFont, QFontDatabase  # noqa: E402

check(not any(a.menu() for a in window.menu_view.actions()), "View no longer has a Theme submenu")
check(window.act_preferences in window.menu_view.actions(), "Preferences is in the View menu")
check(window.act_preferences.text() == "Pre&ferences...", "Preferences action text")
check(window.act_preferences.shortcut().toString() == "Ctrl+,", "Preferences shortcut is Ctrl+,")
check(window.act_preferences.isEnabled(), "Preferences enabled in Rendered mode")
window.act_source.trigger()
check(window.act_preferences.isEnabled(), "Preferences enabled in Source mode")
window.act_rendered.trigger()

seen: dict = {}


def inspect(dialog):
    seen["theme"] = dialog.theme_choice()
    seen["family"] = dialog.font_family()
    seen["size"] = dialog.font_size()
    seen["entries"] = [dialog.font_box.itemText(i) for i in range(dialog.font_box.count())]
    seen["labels"] = [b.text() for b in dialog.theme_buttons.values()]
    return False  # Cancel


FAKE["prefs"] = inspect
before_font = window.editor.font()
window.act_preferences.trigger()
check(seen["theme"] == "system" and window._theme_choice == "system", "dialog opens on the current theme")
check(seen["labels"] == ["&System (auto)", "&Light", "&Dark", "&Gray"], "dialog offers System (auto) / Light / Dark / Gray")
check(seen["family"] == "Consolas" and seen["size"] == 11, "dialog opens on the current editor font")
proportional = [f for f in QFontDatabase.families() if not QFontDatabase.isFixedPitch(f)]
check(seen["entries"] and all(QFontDatabase.isFixedPitch(f) for f in seen["entries"]), "font list has only fixed-pitch fonts")
check(proportional and not set(proportional) & set(seen["entries"]), "proportional fonts are not offered")
check("Consolas" in seen["entries"] and "Courier New" in seen["entries"], "common fixed-pitch fonts are offered")
check(window.editor.font() == before_font, "Cancel leaves the editor font alone")

# OK applies and persists the font
FAKE["prefs"] = lambda d: (d.font_box.setCurrentFont(QFont("Courier New")), d.size_box.setValue(15))
window.act_preferences.trigger()
check(window.editor.font().family() == "Courier New" and window.editor.font().pointSize() == 15, "OK applies the editor font")
check(window.settings_snapshot()["editor_font"] == {"family": "Courier New", "size": 15}, "the font is saved")

# changing the font in a dialog that is then cancelled changes nothing
FAKE["prefs"] = lambda d: (d.size_box.setValue(30), False)[1]
window.act_preferences.trigger()
check(window.editor.font().pointSize() == 15, "a cancelled font change is discarded")

# a font change does not disturb theme, mode, text or dirty state
check(window._theme_choice == "system" and window.mode == "rendered" and not window.dirty, "font change keeps theme, mode and dirty state")

# restored at startup, and written by save_settings
app_module.save_settings(window)
font_restart = main_window.MainWindow(settings.load())
check(font_restart.editor.font().family() == "Courier New" and font_restart.editor.font().pointSize() == 15, "the editor font survives a restart")

# a saved proportional font is still applied at startup, and the dialog falls back to a listed one
odd = main_window.MainWindow(
    {"theme": "light", "window": None, "preview_zoom": 1.0, "editor_font": {"family": proportional[0], "size": 10}}
)
check(odd.editor.font().family() == proportional[0], "a hand-edited proportional font is still applied")
FAKE["prefs"] = inspect
odd.act_preferences.trigger()
check(seen["family"] in seen["entries"], "the dialog never shows a font outside its fixed-pitch list")

# size limits
FAKE["prefs"] = inspect
window.act_preferences.trigger()
sizes = PREFS_DIALOGS[-1].size_box
check((sizes.minimum(), sizes.maximum()) == (settings.FONT_SIZE_MIN, settings.FONT_SIZE_MAX), "size spin box uses the settings limits")
choose_theme("system")
check(window._theme_choice == "system", "theme choice still works after font changes")

# --- WYSIWYG Task 12: RichView and Bridge ---------------------------------------
from PySide6.QtCore import QPoint, Qt, QUrl  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings  # noqa: E402

from mdviewer import richview  # noqa: E402
from mdviewer.core import docmodel, frontmatter, render  # noqa: E402

# The Bridge has exactly one slot per call bridge.js makes, and nothing else of its own.
bridge_js = (Path(__file__).resolve().parent.parent / "web-src" / "src" / "bridge.js").read_text(encoding="utf-8")
CALLS = json.loads(re.search(r"^export const CALLS = (\[.*?^\]);$", bridge_js, flags=re.S | re.M).group(1))
meta = richview.Bridge.staticMetaObject
own = [meta.method(i) for i in range(meta.methodOffset(), meta.methodCount())]
check([bytes(m.name()).decode() for m in own] == CALLS, "Bridge declares one slot per bridge.js call, in order")
check(all(m.methodType() == m.MethodType.Slot for m in own), "Bridge declares only slots (no signals for the page)")
check(meta.propertyCount() == meta.propertyOffset(), "Bridge declares no properties")

# Load: ready() arrives, the page sits in a temp folder with its runtime files and theme CSS.
rich = richview.RichView("light")
seen = record(rich)
rich.resize(800, 600)
rich.show()  # hidden pages throttle timers: selectionState would arrive late (plan Task 9)
check(rich.settings().testAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled), "JavaScript is enabled in the editor")
check(rich.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu, "our own context menu replaces Chromium's (Reload, View Source)")
before_ready = docmodel.from_markdown("# Early\n")
rich.set_document(before_ready)
early = []
rich.request_document(early.append)
check(pump(lambda: rich.is_ready, richview.READY_TIMEOUT_MS / 1000), "RichView becomes ready within 5 s")
check(names(seen)[:1] == ["ready"], f"ready is the first signal ({names(seen)})")
check(pump(lambda: early, 5) and early == [before_ready], "calls made before ready() run after it, in order")
folder = rich.page_file.parent
check(sorted(p.name for p in folder.iterdir()) == sorted(["editor.html", *richview.RUNTIME_FILES]),
      "temp folder holds the page and its runtime files")
check(rich.page_file.read_text(encoding="utf-8") == render.editor_page("light"), "page file is editor_page(theme)")
check(rich.url() == QUrl.fromLocalFile(str(rich.page_file)), "the view shows the page file")

# Round trip: what set_document puts in comes back from request_document.
WYSIWYG_MD = (
    "---\ntitle: x\n---\n\n# Café 😀\n\nText with **bold**, *em*, `code`, ~~gone~~ and\u00a0NBSP.\n\n"
    "- [x] done\n- [ ] todo\n\n1. one\n2. two\n\n> quote\n\n```python\nprint('hi')\n```\n\n"
    "| a | b |\n| :-- | --: |\n| 1 | 2 |\n\n![pic](pic.png) [bad](javascript:alert(1)) [web](https://example.com)\n\n"
    "<div>raw <script>parent.scriptRan = true</script><img src=\"nope.png\" onerror=\"parent.handlerRan = true\"></div>\n\n"
    "Note[^1].\n\n[^1]: The note.\n"
)
front, body = frontmatter.split(WYSIWYG_MD)
doc = docmodel.from_markdown(body, front, TMP)
rich.set_document(doc)
check(pull(rich) == [doc], "request_document returns the document set_document loaded")
pump(lambda: False, 0.5)  # frames load; a script would have run by now
check(page_js(rich, "window.scriptRan === undefined && window.handlerRan === undefined") is True,
      "raw HTML <script> and event handlers never run")
hrefs = page_js(rich, "[...document.querySelectorAll('#editor a[href]')].map((a) => a.getAttribute('href'))")
check(hrefs == ["https://example.com"], f"javascript: link stripped, web link kept ({hrefs})")
check("changed" not in names(seen), "loading documents does not report a change")

# Bridge slots re-emit as RichView signals with their arguments.
seen.clear()
bridge = rich._bridge
bridge.selectionState({"marks": ["strong"], "block": {"type": "paragraph"}, "can": {"undo": True}})
bridge.requestLinkDialog("text", "https://x.test")
bridge.requestImageDialog()
bridge.openLink("https://x.test")
bridge.hoverLink("")
bridge.editProtected(3)
bridge.caretBlock(2)
check(seen == [
    ["selectionState", {"marks": ["strong"], "block": {"type": "paragraph"}, "can": {"undo": True}}],
    ["requestLinkDialog", "text", "https://x.test"], ["requestImageDialog"], ["openLink", "https://x.test"],
    ["hoverLink", ""], ["editProtected", 3], ["caretBlock", 2],
], f"Bridge slots re-emit as RichView signals ({seen})")

# Commands and focus go through the channel both ways: one changed() per load, state follows.
seen.clear()
rich.set_document(docmodel.from_markdown("plain words\n\nsecond\n"))
pump(lambda: "caretBlock" in names(seen), 3)
rich.focus_block(1)
check(pump(lambda: ["caretBlock", 1] in seen, 3), "focus_block moves the caret (caretBlock 1)")
seen.clear()
rich.focus_block(0)
pump(lambda: ["caretBlock", 0] in seen, 3)
rich.activateWindow()  # the main window is shown too; keys go to the active window
QTest.keyClick(rich.focusProxy(), Qt.Key.Key_End, Qt.KeyboardModifier.ShiftModifier)
check(pump(lambda: page_js(rich, "window.mdEditor.view.state.selection.empty") is False, 3), "Shift+End selects the line")
rich.command("toggleMark", "strong")
rich.command("toggleMark", "em")
check(pump(lambda: names(seen).count("changed") == 1 and any(
    e[0] == "selectionState" and e[1]["marks"] == ["strong", "em"] for e in seen), 3),
    f"command edits report changed once and the new marks ({seen[-3:]})")
check(pull(rich)[0]["content"][0]["content"][0]["marks"] == [{"type": "strong"}, {"type": "em"}],
      "commands change the pulled document")

# changed(epoch): a change from before the latest load or pull is not a new edit.
seen.clear()
rich.set_document(docmodel.from_markdown("fresh\n"))
check(not rich.modified, "set_document leaves the view unmodified")
bridge.changed(rich._epoch - 1)  # in flight from the document this load replaced
pump(lambda: False, 0.3)
check("changed" not in names(seen) and not rich.modified, "a changed() from the replaced document is dropped")
rich.command("insertRule")
rich.command("insertRule")
check(pump(lambda: "changed" in names(seen), 3) and rich.modified, "an edit after set_document reports changed")
pump(lambda: False, 0.3)
check(names(seen).count("changed") == 1, "and only once per load")
bridge.changed(rich._epoch)  # a repeated message for the same load
check(names(seen).count("changed") == 1, "a repeated changed() is emitted once")
# A pull marks the page clean and re-arms changed: the next edit is reported again.
check(pull(rich)[0] is not None and not rich.modified, "a pull leaves the view unmodified")
bridge.changed(rich._epoch - 1)  # an edit the pull already read
pump(lambda: False, 0.3)
check(names(seen).count("changed") == 1, "a changed() from before the pull is dropped")
rich.command("insertRule")
check(pump(lambda: names(seen).count("changed") == 2, 3) and rich.modified, "the first edit after a pull reports changed")
check(page_js(rich, "window.mdEditor.command('undo')") is True, "a pull keeps the undo history")

# Theme and zoom: no reload, document and history kept.
loads: list = []
rich.loadStarted.connect(lambda: loads.append(1))
rich.set_document(docmodel.from_markdown("theme\n"))
rich.setZoomFactor(1.5)
rich.set_theme("dark")
pump(lambda: False, 0.3)
background = page_js(rich, "getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()")
check(background == render.PAGE_BACKGROUND["dark"], f"set_theme swaps the theme CSS ({background})")
check(rich.page().backgroundColor().name() == render.PAGE_BACKGROUND["dark"], "set_theme sets the page background")
check(loads == [] and rich.zoomFactor() == 1.5, "theme change and set_document keep the page and the zoom")
check(pull(rich)[0] == docmodel.from_markdown("theme\n"), "theme change keeps the document")
rich.setZoomFactor(1.0)  # the click below uses page coordinates

# Navigation guard: only the page itself; links leave through openLink (Ctrl+click).
LINK = QWebEnginePage.NavigationType.NavigationTypeLinkClicked
TYPED = QWebEnginePage.NavigationType.NavigationTypeTyped
OTHER = QWebEnginePage.NavigationType.NavigationTypeOther
own_url = QUrl.fromLocalFile(str(rich.page_file))
anchor = QUrl(own_url)
anchor.setFragment("fn-1")
guard = rich.page().acceptNavigationRequest
check(guard(own_url, TYPED, True) and guard(anchor, LINK, True), "own page and in-page anchors are allowed")
check(not guard(QUrl("https://example.com"), LINK, True), "a clicked web link does not navigate the page")
check(not guard(QUrl.fromLocalFile(str(TMP / "dropped.md")), TYPED, True), "a dropped file does not replace the page")
check(guard(QUrl("about:srcdoc"), OTHER, False) and not guard(QUrl("https://example.com"), LINK, False),
      "raw HTML frames load their srcdoc and nothing else")
seen.clear()
rich.set_document(docmodel.from_markdown("[web](https://example.com/page)\n"))
pump(lambda: False, 0.3)
point = page_js(rich, "(() => { const b = document.querySelector('#editor a').getBoundingClientRect();"
                      " return [Math.round(b.left + b.width / 2), Math.round(b.top + b.height / 2)]; })()")
QTest.mouseClick(rich.focusProxy(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier, QPoint(*point))
check(pump(lambda: ["openLink", "https://example.com/page"] in seen, 3), "Ctrl+click on a link emits openLink(href)")
pump(lambda: False, 0.3)
check(rich.url() == own_url, "Ctrl+click does not navigate the page")

# Pull timeout: a busy page answers None once; the late answer is ignored.
rich.command("insertRule")
pump(lambda: rich.modified, 3)
saved_timeout = richview.PULL_TIMEOUT_MS
richview.PULL_TIMEOUT_MS = 300
rich.page().runJavaScript("(() => { const t = Date.now(); while (Date.now() - t < 1200); })()", 0)
started = time.monotonic()
busy = pull(rich, 3)
waited = time.monotonic() - started
check(busy == [None] and waited < 1.1, f"a pull with no answer in time gives None ({busy}, {waited:.2f} s)")
check(rich.modified, "a failed pull leaves the view modified")
pump(lambda: False, 1.5)
check(busy == [None], "the late answer does not call back again")
richview.PULL_TIMEOUT_MS = saved_timeout
check(pull(rich)[0]["content"][0] == docmodel.from_markdown("[web](https://example.com/page)\n")["content"][0],
      "pulls work again afterwards")

# A page that hangs inside set_document: the pull's own timer starts only after loads finish, so a
# hard limit from the request time answers it (and restores `modified`).
saved_hard = richview.PULL_HARD_TIMEOUT_MS
richview.PULL_HARD_TIMEOUT_MS = 800
rich.command("insertRule")
pump(lambda: rich.modified, 3)
rich.page().runJavaScript("(() => { const t = Date.now(); while (Date.now() - t < 3000); })()", 0)
rich.set_document(docmodel.from_markdown("hung\n"))
started = time.monotonic()
hung = pull(rich, 2.5)
check(hung == [None] and time.monotonic() - started < 2.5, f"a pull behind a hung set_document is answered anyway ({hung})")
richview.PULL_HARD_TIMEOUT_MS = saved_hard
pump(lambda: False, 3)  # the page recovers; the stale answers are dropped
rich.set_document(docmodel.from_markdown("recovered\n"))
check(pull(rich)[0] == docmodel.from_markdown("recovered\n"), "pulls work again after the hang")

# Renderer crash: crashed(), the pending pull gets None, restart() brings a working page back.
rich.command("insertRule")  # this document's change is reported before the crash
check(pump(lambda: "changed" in names(seen), 3), "an edit reports changed")
seen.clear()
rich.page().runJavaScript("(() => { const t = Date.now(); while (Date.now() - t < 3000); })()", 0)
crash_pull: list = []
rich.request_document(crash_pull.append)
os.kill(rich.page().renderProcessPid(), signal.SIGTERM)
check(pump(lambda: "crashed" in names(seen), 5), "a killed renderer emits crashed")
check(crash_pull == [None] and not rich.is_ready, "the pull in flight gets None and the view is not ready")
dead_pull: list = []
rich.request_document(dead_pull.append)  # Save pressed while a crash dialog is up
check(dead_pull == [None], "a pull between the crash and restart() is answered at once")
rich.set_document(docmodel.from_markdown("lost\n"))
rich.command("insertRule")
rich.restart()
check(pump(lambda: rich.is_ready, 5), "restart() loads a fresh page")
rich.command("insertRule")
check(pump(lambda: "changed" in names(seen), 3), "the first edit on the restarted page reports changed")
again = docmodel.from_markdown("# Back\n")
rich.set_document(again)
check(pull(rich) == [again], "set_document and request_document work after a restart")
check(page_js(rich, "getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()")
      == render.PAGE_BACKGROUND["dark"], "the restarted page keeps the current theme")
rich.close()

# Load failures: missing page files, or no ready() in time -> load_failed; then calls are no-ops.
saved_web, saved_ready = render.WEB_DIR, richview.READY_TIMEOUT_MS
render.WEB_DIR = TMP / "no-web"
missing = richview.RichView()
missing_seen = record(missing)
check(pump(lambda: "load_failed" in names(missing_seen), 1) and missing.failed, "missing page files -> load_failed")
render.WEB_DIR = saved_web
richview.READY_TIMEOUT_MS = 50  # the real page needs ~0.5 s: its ready() comes too late
late = richview.RichView()
late_seen = record(late)
check(pump(lambda: "load_failed" in names(late_seen), 3), "no ready() in time -> load_failed")
pump(lambda: False, 1.5)  # the page's own ready() arrives meanwhile
check(names(late_seen) == ["load_failed"] and not late.is_ready, f"a late ready() is ignored ({names(late_seen)})")
nothing: list = []
late.request_document(nothing.append)
late.set_document(docmodel.from_markdown("x\n"))
late.command("toggleMark", "strong")
check(nothing == [None], "after load_failed, request_document answers None at once")
richview.READY_TIMEOUT_MS = saved_ready

# --- WYSIWYG Task 14: save prompts, stopped and crashed editors ------------------
import stat  # noqa: E402

BOXES: list = []
ANSWERS: list = []  # answers for the next asks, in order; then FAKE["answer"]


def ask_in_turn(box):
    BOXES.append(box)
    answer = fake_ask(box)
    if ANSWERS:
        answer = ANSWERS.pop(0)
    return answer() if callable(answer) else answer  # a callable acts "while the dialog is open"


main_window.ask = ask_in_turn
richview.PULL_TIMEOUT_MS = saved_timeout
STOPPED_HUNG = main_window.STOPPED_TEXT + "\n\n" + main_window.HUNG_DETAIL
STOPPED_CRASHED = main_window.STOPPED_TEXT + "\n\n" + main_window.CRASHED_DETAIL
check(main_window.STOPPED_TEXT == "The rendered editor stopped responding.", "the stopped-responding text is the spec's")


def edit_rendered(win, level: int) -> None:
    """A Rendered edit not yet pulled: the first block becomes a heading of `level`."""
    win.rich.focus_block(0)
    win.rich.command("setBlock", {"type": "heading", "level": level})
    check(pump(lambda: win.rich.modified and win.dirty, 3), f"a Rendered edit (H{level}) is pending")


def type_rendered(win, text: str) -> None:
    page_js(win.rich, f"(window.mdEditor.view.dispatch(window.mdEditor.view.state.tr.insertText({json.dumps(text)})), 0)")
    check(pump(lambda: win.rich.modified and win.dirty, 3), f"typing {text!r} in Rendered mode is pending")


def busy_page(win, ms: int) -> None:
    win.rich.page().runJavaScript(f"(() => {{ const t = Date.now(); while (Date.now() - t < {ms}); }})()", 0)


# "Save changes?" answered Save: each action goes on once the pulled document is saved
flow, other = TMP / "flow.md", TMP / "other.md"
other.write_bytes(b"# Other\n")


def save_prompt_flow(label: str, trigger, done) -> None:
    flow.write_bytes(b"# Flow\n")
    window.open_file(flow)
    edit_rendered(window, 2)
    ASKED.clear()
    FAKE["answer"] = S.Save
    trigger()
    check(ASKED == ["Save changes to flow.md?"], f"{label}: asks to save the Rendered edits ({ASKED})")
    check(pump(done, 5), f"{label}: goes on once the pulled document is saved")
    check(flow.read_bytes() == b"## Flow\n", f"{label}: the Rendered edit is saved ({flow.read_bytes()!r})")


FAKE["open_path"] = str(other)
save_prompt_flow("New", window.on_new, lambda: window.loaded_path is None and window.mode == "rendered")
save_prompt_flow("Open", window.on_open, lambda: window.loaded_path == other)
save_prompt_flow("Drop", lambda: window._open_dropped([str(other)]), lambda: window.loaded_path == other)
save_prompt_flow("Open Recent", lambda: window._open_recent(os.path.abspath(other)), lambda: window.loaded_path == other)
save_prompt_flow("Close", window.on_close, lambda: window.loaded_path is None and window.buffer == "")

# Untitled: Save goes through Save As (cancelling it stops the action), then the action goes on
FAKE["answer"] = S.Discard
window.on_new()
type_rendered(window, "untitled words")
FAKE["save_path"] = ""
FAKE["answer"] = S.Save
window.on_open()
pump(lambda: False, 0.3)
check(window.loaded_path is None and window.dirty and window.rich.modified, "Untitled: cancelling Save As stops Open")
FAKE["save_path"] = str(TMP / "named")
window.on_open()
check(pump(lambda: window.loaded_path == other, 5), "Untitled: Open goes on after Save As")
check((TMP / "named.md").read_bytes() == b"untitled words\n", "Untitled: the Rendered text is saved as named.md")

# Cancel, or a save that fails, stops the action and keeps the edits
edit_rendered(window, 3)
FAKE["answer"] = S.Cancel
window.on_new()
pump(lambda: False, 0.3)
check(window.loaded_path == other and window.dirty and window.rich.modified, "Cancel keeps the Rendered edits")
os.chmod(other, stat.S_IREAD)
ERRORS.clear()
ASKED.clear()
FAKE["answer"] = S.Save
window.on_new()
check(pump(lambda: ERRORS, 5) and window.loaded_path == other and window.dirty, "a save that fails stops the action")
check(len(ASKED) == 1 and len(ERRORS) == 1, f"and asks once ({len(ASKED)} asks)")
os.chmod(other, stat.S_IREAD | stat.S_IWRITE)
check(other.read_bytes() == b"# Other\n", "and wrote nothing")

# an edit that lands after the save's snapshot is asked about again
edit_rendered(window, 2)
ASKED.clear()
edit_after_next_snapshot()
window.on_new()
check(pump(lambda: window.loaded_path is None, 5) and len(ASKED) == 2, f"an edit made during the save asks again ({ASKED})")
check(other.read_bytes() == b"## Other\n", "the snapshot was saved")

# while a pull is in flight, a prompt is not even shown
window.open_file(other)
edit_rendered(window, 1)
busy_page(window, 600)
window.on_save()
ASKED.clear()
window.on_new()
window.close()
check(not ASKED and window.loaded_path == other and window.isVisible(), "New and close are dropped while a pull is in flight")
check(pump(lambda: not window._pending_pull and not window.dirty, 5) and other.read_bytes() == b"# Other\n", "the save completes")

# a pull with no answer asks; Retry waits again and the action goes on
edit_rendered(window, 2)
richview.PULL_TIMEOUT_MS = 300
busy_page(window, 1200)
ASKED.clear()
BOXES.clear()
ANSWERS[:] = [S.Save, lambda: (setattr(richview, "PULL_TIMEOUT_MS", saved_timeout), S.Retry)[1]]
window.on_new()
check(pump(lambda: len(ASKED) >= 2, 3) and ASKED[1] == STOPPED_HUNG, f"a pull with no answer asks ({ASKED[1:]})")
box = BOXES[1]
check(sorted(b.text() for b in box.buttons()) == ["Retry", "Switch to Source"], "the box offers Switch to Source and Retry")
check(box.defaultButton() is box.button(S.Retry), "Retry is the default")
check(pump(lambda: window.loaded_path is None, 5), "Retry: New goes on once the page answers")
check(other.read_bytes() == b"## Other\n" and len(ASKED) == 2, f"the edit is saved ({len(ASKED)} asks)")

# Switch to Source: the last pulled text, still dirty; the page restarts
window.open_file(other)
edit_rendered(window, 3)
richview.PULL_TIMEOUT_MS = 300
busy_page(window, 1200)
ASKED.clear()
ANSWERS[:] = [S.Discard]
page_loads: list = []
window.rich.loadStarted.connect(lambda: page_loads.append(1))
window.act_source.trigger()
check(pump(lambda: window.mode == "source", 3) and ASKED == [STOPPED_HUNG], "Switch to Source shows Source mode")
richview.PULL_TIMEOUT_MS = saved_timeout
check(window.buffer == "## Other\n" and window.editor.document().isModified() and window.dirty,
      "with the last loaded text, marked unsaved")
check(other.read_bytes() == b"## Other\n", "nothing was saved")
check(page_loads and pump(lambda: window.rich.is_ready, 6) and not window.rich.modified, "the abandoned page restarts")
window.act_rendered.trigger()
check(window.mode == "rendered" and pump(lambda: page_js(window.rich, "document.querySelector('#editor h2')?.textContent") == "Other", 3),
      "switching back shows the Source text")

# a crash in Rendered mode asks; Retry reloads the last loaded text into a fresh page
CRASHES: list = []
window.rich.crashed.connect(lambda: CRASHES.append(1))
FAKE["answer"] = S.Discard
window.open_file(other)
edit_rendered(window, 1)
ASKED.clear()
ANSWERS[:] = [S.Retry]
os.kill(window.rich.page().renderProcessPid(), signal.SIGTERM)
check(pump(lambda: ASKED, 5) and ASKED == [STOPPED_CRASHED], f"a crash in Rendered mode asks ({ASKED})")
check(pump(lambda: window.rich.is_ready, 5) and window.mode == "rendered", "Retry restarts the page in Rendered mode")
check(pump(lambda: page_js(window.rich, "document.querySelector('#editor h2')?.textContent") == "Other", 3),
      "the restarted page shows the last loaded text")
check(window.dirty and not window.rich.modified, "the lost edit leaves the buffer marked unsaved")
edit_rendered(window, 3)
window.on_save()
check(pump(lambda: not window.dirty, 5) and other.read_bytes() == b"### Other\n", "the restarted page edits and saves")

# a crash during a pull asks once; Switch to Source keeps the last pulled text
edit_rendered(window, 1)
busy_page(window, 3000)
ASKED.clear()
ANSWERS[:] = [S.Discard]
window.on_save()
os.kill(window.rich.page().renderProcessPid(), signal.SIGTERM)
check(pump(lambda: window.mode == "source", 5) and ASKED == [STOPPED_CRASHED], f"a crash during a pull asks once ({ASKED})")
check(window.buffer == "### Other\n" and other.read_bytes() == b"### Other\n", "Switch to Source: the last pulled text, nothing saved")
check(pump(lambda: window.rich.is_ready, 5), "the page restarts")

# a crash in Source mode restarts the page without asking
CRASHES.clear()
ASKED.clear()
os.kill(window.rich.page().renderProcessPid(), signal.SIGTERM)
check(pump(lambda: CRASHES and window.rich.is_ready, 5) and not ASKED and window.mode == "source",
      "a crash in Source mode restarts the page quietly")
window.act_rendered.trigger()
check(pump(lambda: page_js(window.rich, "document.querySelector('#editor h3')?.textContent") == "Other", 3),
      "switching to Rendered after it shows the document")

# window close and Exit: the save finishes after the pull, then the window closes
cw = main_window.MainWindow({"theme": "light", "window": None, "preview_zoom": 1.0})
cw.show()
check(pump(lambda: cw.rich.is_ready, 5), "a second window's page is ready")
exit_md = TMP / "exit.md"
for label, close, level in [("closing the window", cw.close, 2), ("File > Exit", cw.act_exit.trigger, 3)]:
    exit_md.write_bytes(b"# Exit\n")
    cw.show()
    cw.open_file(exit_md)
    edit_rendered(cw, level)
    ASKED.clear()
    ANSWERS[:] = [S.Save]
    close()
    check(cw.isVisible() and ASKED == ["Save changes to exit.md?"], f"{label}: asks, and waits for the pull")
    check(pump(lambda: not cw.isVisible(), 5), f"{label}: closes once the document is saved")
    check(exit_md.read_bytes() == b"#" * level + b" Exit\n", f"{label}: the Rendered edit is saved")
cw.show()
cw.open_file(exit_md)
edit_rendered(cw, 1)
ANSWERS[:] = [S.Discard]
check(cw.close() and not cw.isVisible(), "Don't Save closes at once")
check(exit_md.read_bytes() == b"### Exit\n", "and saves nothing")

# a page that stays hung: Switch to Source works, and Rendered is greyed once the restart times out
cw.show()
cw.open_file(exit_md)
edit_rendered(cw, 2)
saved_ready = richview.READY_TIMEOUT_MS
richview.PULL_TIMEOUT_MS, richview.READY_TIMEOUT_MS = 300, 300
busy_page(cw, 2000)
ANSWERS[:] = [S.Discard]
cw.on_save()
check(pump(lambda: cw.rich.failed, 3) and cw.mode == "source" and cw.buffer == "### Exit\n",
      "a page that stays hung: Source mode with the last loaded text")
check(not cw.act_rendered.isEnabled() and cw.statusBar().currentMessage() == main_window.EDITOR_FAILED_NOTE,
      "Rendered is greyed with a warning")
richview.PULL_TIMEOUT_MS, richview.READY_TIMEOUT_MS = saved_timeout, saved_ready
cw.hide()

# table edits and unsafe paste reach the saved file through the window
FAKE["answer"] = S.Discard
table_md = TMP / "table.md"
table_md.write_bytes(b"intro\n")
window.open_file(table_md)
page_js(window.rich, "(window.mdEditor.view.dispatch(window.mdEditor.view.state.tr.setSelection("
                     "window.mdEditor.view.state.selection.constructor.atEnd(window.mdEditor.view.state.doc))), 0)")
window.rich.command("insertTable", {"rows": 2, "cols": 2})
pump(lambda: window.dirty, 3)
page_js(window.rich, "(window.mdEditor.view.dispatch(window.mdEditor.view.state.tr.insertText('h ')), 0)")
window.rich.command("addRowAfter")
page_js(window.rich, """(window.mdEditor.view.pasteHTML('<p><b>bold</b> <a href="javascript:alert(1)">bad</a> '
  + '<a href="https://ok.example/">ok</a><script>parent.pasted = 1</script></p>'), 0)""")
window.on_save()
check(pump(lambda: not window.dirty, 5), "Save after table edits and a paste")
saved_table = table_md.read_bytes().decode("utf-8")
check(saved_table == "intro\n\n| h **bold** bad [ok](https://ok.example/) |  |\n| --- | --- |\n|  |  |\n|  |  |\n",
      f"the saved file has the table, and the paste without its javascript: link or script ({saved_table!r})")
check(page_js(window.rich, "window.pasted === undefined") is True, "the pasted script never ran")

# --- Task 14 review fixes ------------------------------------------------------------
# The page fails after a Rendered save: Source shows the saved text, not the older editor text
fw = main_window.MainWindow({"theme": "light", "window": None, "preview_zoom": 1.0})
fw.show()
check(pump(lambda: fw.rich.is_ready, 5), "a third window's page is ready")
fail_md = TMP / "fail.md"
fail_md.write_bytes(b"# One\n")
fw.open_file(fail_md)
edit_rendered(fw, 2)
fw.on_save()
check(pump(lambda: not fw.dirty, 5) and fail_md.read_bytes() == b"## One\n", "a Rendered edit is saved")
fw.rich.load_failed.emit()
check(fw.mode == "source" and fw.buffer == "## One\n" and not fw.dirty,
      f"a page failure after a save shows the saved text in Source ({fw.buffer!r})")
check(fw.on_save() and fail_md.read_bytes() == b"## One\n", "and saving from there keeps the edit")
fw.hide()

# a language typed into a code block's field and not committed is saved by Ctrl+S
lang_md = TMP / "lang.md"
lang_md.write_bytes(b"```\nx\n```\n")
window.open_file(lang_md)
page_js(window.rich, """(() => { const field = document.querySelector('#editor .md-code-language');
  field.focus(); field.value = 'go'; field.dispatchEvent(new Event('input')); return 0; })()""")
check(pump(lambda: window.dirty, 3), "typing a language in a code block marks the document dirty")
window.on_save()
check(pump(lambda: not window.dirty, 5) and lang_md.read_bytes() == b"```go\nx\n```\n",
      f"Save takes a language that was typed but not committed ({lang_md.read_bytes()!r})")

# --- WYSIWYG Task 15: format toolbar ----------------------------------------------
from PySide6.QtWidgets import QToolBar  # noqa: E402

tb = window.toolbar
FAKE["answer"] = S.Discard
window.on_new()
check(isinstance(tb, QToolBar) and tb.isVisible(), "the format toolbar shows in Rendered mode")
check(window.toolBarArea(tb) == Qt.ToolBarArea.TopToolBarArea and not tb.isMovable() and not tb.isFloatable(),
      "one fixed toolbar row under the menu bar")
layout = ["combo" if tb.widgetForAction(a) is tb.block_box else "|" if a.isSeparator() else a.text() for a in tb.actions()]
check(layout == ["combo", "|", "Bold", "Italic", "Strikethrough", "Inline code", "Link", "|",
                 "Bulleted list", "Numbered list", "Task list", "|",
                 "Quote", "Code block", "Table", "Image", "Horizontal rule", "|", "Clear formatting"],
      f"the toolbar layout is the spec's ({layout})")
check([a.toolTip() for a in tb.buttons.values()] == [
    "Bold (Ctrl+B)", "Italic (Ctrl+I)", "Strikethrough (Ctrl+Shift+X)", "Inline code (Ctrl+`)", "Link (Ctrl+K)",
    "Bulleted list (Ctrl+Shift+8)", "Numbered list (Ctrl+Shift+7)", "Task list (Ctrl+Shift+9)",
    "Quote (Ctrl+Shift+.)", "Code block", "Table", "Image", "Horizontal rule", "Clear formatting (Ctrl+Space)",
], "button tooltips name their shortcuts")
check(all(a.shortcut().isEmpty() for a in tb.buttons.values()), "the shortcuts stay with the page's keymap")
box = tb.block_box


def pick_block(number: int) -> None:
    """What a user's pick in the block combo does: the combo moves, then activated(number)."""
    box.setCurrentIndex(number)
    box.activated.emit(number)


check([box.itemText(i) for i in range(box.count())] == ["Normal", *(f"Heading {n}" for n in range(1, 7)), "Code block"],
      "the block combo offers Normal, Heading 1-6 and Code block")
check([box.itemData(i, Qt.ItemDataRole.ToolTipRole) for i in range(box.count())]
      == ["Normal (Ctrl+Alt+0)", *(f"Heading {n} (Ctrl+Alt+{n})" for n in range(1, 7)), "Code block"],
      "block combo tooltips name their shortcuts")
check(all(not a.icon().isNull() for a in tb.buttons.values()), "every button has a glyph icon")
check([a.isCheckable() for a in tb.buttons.values()] == [True] * 5 + [False] * 9, "mark and link buttons are checkable")
popup = window.createPopupMenu()
check(popup is None or popup.isEmpty(), "no context menu hides the toolbar behind View > Toolbar's back")

# View > Toolbar, Source mode and the saved choice
window.act_source.trigger()
check(window.mode == "source" and not tb.isVisible(), "the toolbar hides in Source mode")
window.act_rendered.trigger()
check(tb.isVisible(), "and comes back in Rendered mode")
check(window.act_toolbar in window.menu_view.actions() and window.act_toolbar.isChecked(), "View > Toolbar is on by default")
window.act_toolbar.trigger()
check(not tb.isVisible() and window.settings_snapshot()["show_toolbar"] is False, "View > Toolbar hides it; the choice is saved")
window.act_source.trigger()
window.act_rendered.trigger()
check(not tb.isVisible(), "a hidden toolbar stays hidden across mode switches")
window.act_toolbar.trigger()
check(tb.isVisible() and window.settings_snapshot()["show_toolbar"] is True, "View > Toolbar shows it again")
check(not fw.toolbar.isVisibleTo(fw) and fw.mode == "source", "a page that failed leaves the toolbar hidden")
check(not restored.act_toolbar.isChecked() and not restored.toolbar.isVisibleTo(restored),
      "a saved hidden toolbar starts hidden")

# every control sends its command; nothing runs while the page reports nothing
SENT: list = []
window.rich.command = lambda name, args=None: SENT.append((name, args))
tb.update_state({})
check(not box.isEnabled() and not any(a.isEnabled() for a in tb.buttons.values()), "with no selection state every control is disabled")
tb.buttons["bold"].trigger()
check(SENT == [], "a disabled button sends nothing")
CAN_ALL = {name: True for name in ("toggleMark", "linkDialog", "toggleList", "toggleQuote", "insertCodeBlock",
                                   "insertTable", "imageDialog", "insertRule", "clearFormatting", "setBlock")}
tb.update_state({"marks": [], "block": {"type": "paragraph"}, "can": CAN_ALL})
for act in tb.buttons.values():
    act.trigger()
check(not any(a.isChecked() for a in tb.buttons.values()), "a click alone checks nothing: the page's report does")
for number in range(box.count()):
    pick_block(number)
del window.rich.command
check(SENT == [
    ("toggleMark", "strong"), ("toggleMark", "em"), ("toggleMark", "strike"), ("toggleMark", "code"), ("linkDialog", None),
    ("toggleList", "bullet"), ("toggleList", "ordered"), ("toggleList", "task"),
    ("toggleQuote", None), ("insertCodeBlock", None), ("insertTable", {"rows": 3, "cols": 3}), ("imageDialog", None),
    ("insertRule", None), ("clearFormatting", None),
    ("setBlock", {"type": "paragraph"}), *(("setBlock", {"type": "heading", "level": n}) for n in range(1, 7)),
    ("setBlock", {"type": "code_block"}),
], f"each control sends its command ({SENT})")
check(box.currentText() == "Normal", "picking a block type leaves the combo to the page's report")

# the real page: commands apply, the controls follow the selection, Save writes them
tool_md = TMP / "toolbar.md"
tool_md.write_bytes(b"alpha\n\nbeta\n\n---\n")
window.open_file(tool_md)
check(pump(lambda: box.isEnabled() and tb.buttons["bold"].isEnabled() and box.currentText() == "Normal", 3),
      "the page's selection state enables the toolbar")
window.rich.focus_block(0)
pick_block(2)
check(pump(lambda: box.currentText() == "Heading 2", 3), "Heading 2 from the combo; the combo follows")
window.rich.focus_block(1)
page_js(window.rich, "(() => { const v = window.mdEditor.view; const s = v.state.selection;"
                     " v.dispatch(v.state.tr.setSelection(s.constructor.create(v.state.doc, s.from, s.from + 4))); return 0; })()")
check(pump(lambda: box.currentText() == "Normal" and not tb.buttons["bold"].isChecked(), 3), "a plain selection")
tb.buttons["bold"].trigger()
check(pump(lambda: tb.buttons["bold"].isChecked(), 3), "Bold applies and is checked")
tb.buttons["bullets"].trigger()
check(pump(lambda: window.dirty, 3), "the toolbar edit marks the document dirty")
window.rich.focus_block(2)
check(pump(lambda: box.currentIndex() == -1 and box.currentText() == "", 3), "a selected rule shows no block type")
window.rich.focus_block(1)
check(pump(lambda: tb.buttons["table"].isEnabled(), 3), "Table applies in a list")
tb.buttons["table"].trigger()
pump(lambda: False, 0.2)
window.on_save()
check(pump(lambda: not window.dirty, 5), "Save after toolbar edits")
saved_tool = tool_md.read_bytes().decode("utf-8")
check(saved_tool == "## alpha\n\n- **beta**\n\n|  |  |  |\n| --- | --- | --- |\n|  |  |  |\n|  |  |  |\n\n---\n",
      f"the saved file has the toolbar's heading, bold, list and table ({saved_tool!r})")
tb.buttons["code_block"].trigger()
check(pump(lambda: box.currentText() == "Code block", 3), "{} inserts a code block; the combo shows it")
check(not tb.buttons["bold"].isEnabled() and not tb.buttons["link"].isEnabled() and box.isEnabled(),
      "marks and Link are disabled in a code block")

# the shortcuts work with the toolbar hidden (the page's keymap)
window.act_toolbar.trigger()
window.rich.focus_block(0)
pump(lambda: False, 0.2)
QTest.keyClick(window.rich.focusProxy(), Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
check(pump(lambda: "strong" in (page_js(window.rich, "window.mdEditor.selectionState().marks") or []), 3),
      "Ctrl+B works with the toolbar hidden")
window.act_toolbar.trigger()


# a page that is restarting leaves no live controls: a click would queue behind setDocument
RESTART_STATE: list = []
window.rich.crashed.connect(lambda: RESTART_STATE.append((window.rich.is_ready, tb.buttons["table"].isEnabled(), box.isEnabled())))
check(pump(lambda: tb.buttons["table"].isEnabled() and box.isEnabled(), 3), "the controls are live before the crash")
ASKED.clear()
ANSWERS[:] = [S.Retry]
os.kill(window.rich.page().renderProcessPid(), signal.SIGTERM)
check(pump(lambda: RESTART_STATE, 5), "a crash with the toolbar shown")
check(RESTART_STATE == [(False, False, False)], f"a restarting page leaves every control disabled ({RESTART_STATE})")
check(pump(lambda: window.rich.is_ready and tb.buttons["table"].isEnabled() and box.isEnabled(), 8),
      "the restarted page's first report enables them again")


# glyphs follow the theme's text color
def glyph_lightness(act) -> int:
    image = act.icon().pixmap(16, 16).toImage()
    pixels = [image.pixelColor(x, y) for x in range(16) for y in range(16)]
    return max(pixels, key=lambda c: c.alpha()).lightness()


check(glyph_lightness(tb.buttons["bold"]) < 100, "light theme: dark glyphs")
choose_theme("dark")
check(pump(lambda: glyph_lightness(tb.buttons["bold"]) > 150, 2), "dark theme: light glyphs")
choose_theme("system")
check(pump(lambda: glyph_lightness(tb.buttons["bold"]) < 100, 2), "back to light glyphs")
FAKE["answer"] = S.Discard
window.on_new()

# --- WYSIWYG Task 16: link and image dialogs, link navigation, protected blocks -----
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialogButtonBox  # noqa: E402

from mdviewer import dialogs  # noqa: E402

DIALOGS: list = []
OPENED: list = []
real_run_link_dialog = main_window.run_link_dialog
real_run_image_dialog = main_window.run_image_dialog


def fake_dialog(*call):
    """Stand-in for a page-requested dialog: records the call, runs FAKE["during_dialog"]
    "while it is open", then answers FAKE[kind]."""
    DIALOGS.append(call)
    hook = FAKE.pop("during_dialog", None)
    if hook:
        hook()
    return FAKE[call[0]]


main_window.run_link_dialog = lambda parent, text, url: fake_dialog("link", text, url)
main_window.run_image_dialog = lambda parent, base_dir: fake_dialog("image", base_dir)
main_window.open_external = OPENED.append
dialogs.pick_image_path = lambda parent, start: (DIALOGS.append(("browse", start)), FAKE["image_path"])[-1]
FAKE.update(link=None, image=None, image_path="")

# the dialogs themselves
link_box = dialogs.LinkDialog("word", "")
check(link_box.windowTitle() == "Insert Link" and link_box.remove_button is None and link_box.text_edit.text() == "word",
      "a new link: Insert Link with the selected text, no Remove link")
check(not link_box.ok_button.isEnabled(), "OK waits for a URL")
link_box.url_edit.setText("java\tscript:alert(1)")
check(not link_box.ok_button.isEnabled(), "a javascript: URL cannot be accepted")
link_box.url_edit.setText("  https://example.com/  ")
check(link_box.ok_button.isEnabled() and link_box.values() == ("word", "https://example.com/"), "OK gives (text, trimmed URL)")
edit_box = dialogs.LinkDialog("old", "https://o.test/")
check(edit_box.windowTitle() == "Edit Link" and edit_box.remove_button.text() == "&Remove link"
      and edit_box.ok_button.isEnabled(), "editing a link offers Remove link")
image_box = dialogs.ImageDialog(TMP)
check(image_box.windowTitle() == "Insert Image" and not image_box.ok_button.isEnabled(), "OK waits for a path")
picked = TMP / "pics" / "a b.png"
FAKE["image_path"] = picked.as_posix()
image_box.browse_button.click()
check(DIALOGS[-1] == ("browse", str(TMP)) and image_box.path_edit.text() == str(picked),
      "Browse... starts in the document's folder and fills the path")
image_box.alt_edit.setText("Alt")
check(image_box.ok_button.isEnabled() and image_box.values() == ("pics/a b.png", "Alt"),
      "a picked file is stored relative to the document's folder")
untitled_box = dialogs.ImageDialog(None)
untitled_box.path_edit.setText(str(picked))
check(untitled_box.values()[0] == picked.as_uri(), "Untitled: the image is an absolute file: URI")
image_box.path_edit.setText("javascript:alert(1)")
check(not image_box.ok_button.isEnabled(), "a javascript: image cannot be accepted")


# the real seams map the buttons to their answers (a timer presses them)
def press_when_open(button_of, tries: int = 100) -> None:
    """Clicks button_of(dialog) once a modal dialog is open (polled every 20 ms, up to 2 s)."""
    dialog = QApplication.activeModalWidget()
    if dialog is not None:
        button_of(dialog).click()
    elif tries:
        QTimer.singleShot(20, lambda: press_when_open(button_of, tries - 1))


def page_doc() -> str:
    """The page's document as JSON text, read without a pull (a pull marks the page clean)."""
    return json.dumps(page_js(window.rich, "window.mdEditor.view.state.doc.toJSON()"))


CANCEL = QDialogButtonBox.StandardButton.Cancel
press_when_open(lambda d: d.remove_button)
check(real_run_link_dialog(window, "old", "https://o.test/") == "remove", "Remove link answers 'remove'")
press_when_open(lambda d: d.ok_button)
check(real_run_link_dialog(window, "old", "https://o.test/") == ("old", "https://o.test/"), "OK answers (text, url)")
press_when_open(lambda d: d.findChild(QDialogButtonBox).button(CANCEL))
check(real_run_link_dialog(window, "", "") is None, "Cancel answers None")
press_when_open(lambda d: (d.path_edit.setText("https://e.test/a.png"), d.ok_button)[1])
check(real_run_image_dialog(window, TMP) == ("https://e.test/a.png", ""), "the image dialog answers (src, alt)")

# Link and Image through the page: the saved Markdown
picked.parent.mkdir()
QImage(4, 4, QImage.Format.Format_ARGB32).save(str(picked))
links_md = TMP / "links.md"
links_md.write_bytes(b"word here\n\n# Intro\n\nend\n")
window.open_file(links_md)
check(pump(lambda: tb.buttons["link"].isEnabled(), 3), "the page enables Link")
SELECT_JS = ("(() => {{ const v = window.mdEditor.view; const s = v.state.selection;"
             " v.dispatch(v.state.tr.setSelection(s.constructor.create(v.state.doc, s.from + {}, s.from + {}))); return 0; }})()")
window.rich.focus_block(0)
page_js(window.rich, SELECT_JS.format(0, 4))
FAKE["link"] = ("word", "https://example.com/")
tb.buttons["link"].trigger()
check(pump(lambda: window.dirty, 3) and DIALOGS[-1] == ("link", "word", ""), "Link opens the dialog with the selected text")
window.rich.focus_block(2)
pump(lambda: window._caret_block == 2, 3)
FAKE["image"] = ("pics/a b.png", "Alt")
check(pump(lambda: tb.buttons["image"].isEnabled(), 3), "the page enables Image")
tb.buttons["image"].trigger()
check(pump(lambda: DIALOGS[-1] == ("image", TMP), 3), "Image opens the dialog with the document's folder")
check(pump(lambda: page_js(window.rich, "document.querySelector('#editor .md-image img')?.naturalWidth") == 4, 3),
      "the inserted image displays: display_src is its resolved file: URI")
window.on_save()
check(pump(lambda: not window.dirty, 5), "Save after the dialogs")
saved_links = links_md.read_bytes().decode("utf-8")
check(saved_links == "[word](https://example.com/) here\n\n# Intro\n\n![Alt](<pics/a b.png>)end\n",
      f"the saved file has the dialogs' link and image ({saved_links!r})")
window.rich.focus_block(0)
page_js(window.rich, SELECT_JS.format(1, 1))
FAKE["link"] = "remove"
tb.buttons["link"].trigger()
check(pump(lambda: window.dirty, 3) and DIALOGS[-1] == ("link", "word", "https://example.com/"),
      "on a link, the dialog gets its text and URL")
FAKE["link"] = None
count = len(DIALOGS)
FAKE["during_dialog"] = lambda: window.rich.requestLinkDialog.emit("again", "")
tb.buttons["link"].trigger()
check(pump(lambda: len(DIALOGS) > count, 3) and len(DIALOGS) == count + 1, "a request made while a dialog is open is dropped")
window.on_save()
check(pump(lambda: not window.dirty, 5) and links_md.read_bytes().startswith(b"word here\n"),
      "Remove link; Cancel changes nothing")
FAKE["link"] = ("zzz", "https://z.test/")
FAKE["during_dialog"] = lambda: window.open_file(links_md)
tb.buttons["link"].trigger()
pump(lambda: False, 0.5)
check(not window.dirty and "z.test" not in page_doc(), "an answer for a document replaced meanwhile is dropped")
FAKE["link"] = None

# the real dialog, run from inside the page's bridge call
main_window.run_link_dialog = real_run_link_dialog
check(pump(lambda: tb.buttons["link"].isEnabled(), 3), "Link is enabled again")
window.rich.focus_block(0)
page_js(window.rich, SELECT_JS.format(0, 4))
press_when_open(lambda d: (d.url_edit.setText("https://real.test/"), d.ok_button)[1])
tb.buttons["link"].trigger()
check(pump(lambda: "https://real.test/" in page_doc(), 3), "a real dialog opened from the page's request applies its answer")
main_window.run_link_dialog = lambda parent, text, url: fake_dialog("link", text, url)

# Ctrl+click: external links, relative files, #anchors; unsafe, runnable and handler-scheme ones are ignored
OPENED.clear()
for href in ("https://example.com/a", "javascript:alert(1)", " java\tscript:x", "other.md#part", "setup.exe",
             "ms-msdt:/id", "file:///C:/x/tool.bat", "mailto:me@example.com"):
    window.rich.openLink.emit(href)
check(OPENED == [QUrl("https://example.com/a"), QUrl((TMP / "other.md").as_uri() + "#part"), QUrl("mailto:me@example.com")],
      f"safe links open outside the app, relative ones next to the file ({OPENED})")
anchors_md = TMP / "anchors.md"
anchors_md.write_bytes(b"[go](#section-two) [nowhere](#missing)\n\n# Intro\n\ntext\n\n## Section Two\n\nend\n")
window.open_file(anchors_md)
pump(lambda: window._caret_block == 0 and window.rich.is_ready, 3)
OPENED.clear()
point = page_js(window.rich, "(() => { const b = document.querySelector('#editor a').getBoundingClientRect();"
                             " return [Math.round(b.left + b.width / 2), Math.round(b.top + b.height / 2)]; })()")
QTest.mouseClick(window.rich.focusProxy(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier, QPoint(*point))
check(pump(lambda: window._caret_block == 3, 3) and OPENED == [], "Ctrl+click on #section-two moves to that heading")
window.rich.openLink.emit("#missing")
pump(lambda: False, 0.3)
check(window._caret_block == 3 and OPENED == [], "an anchor with no heading does nothing")
window.on_new()
window.rich.openLink.emit("other.md")
window.rich.openLink.emit("https://example.com/b")
check(OPENED == [QUrl("https://example.com/b")], "Untitled: a relative link has nowhere to open")

# hovering a link shows its URL; leaving clears only that message
bar = window.statusBar()
window.rich.hoverLink.emit("https://example.com/h")
check(bar.currentMessage() == "https://example.com/h", "a hovered link shows its URL in the status bar")
window.rich.hoverLink.emit("")
check(bar.currentMessage() == "", "leaving the link clears it")
window.rich.hoverLink.emit("https://example.com/h")
bar.showMessage("a warning", 10000)
window.rich.hoverLink.emit("")
check(bar.currentMessage() == "a warning", "leaving a link keeps a warning shown meanwhile")
bar.showMessage("a warning", 10000)
window.rich.hoverLink.emit("https://example.com/h")
check(bar.currentMessage() == "a warning", "hovering a link keeps a warning already shown")
window.rich.hoverLink.emit("")
check(bar.currentMessage() == "a warning", "leaving that link keeps the warning too")
bar.clearMessage()
window.rich.hoverLink.emit("https://example.com/h")
window.act_source.trigger()
check(window.mode == "source" and bar.currentMessage() == "", "Source mode drops the hovered URL")
count = len(DIALOGS)
window.rich.requestLinkDialog.emit("late", "")
window.rich.requestImageDialog.emit()
check(len(DIALOGS) == count, "a dialog request that arrives in Source mode is dropped")
window.act_rendered.trigger()

# double-click on a protected block: Source mode, caret on its first line
protected_md = TMP / "protected.md"
protected_md.write_bytes(b"intro\n\n<div>\nraw\n</div>\n\nafter\n")
window.open_file(protected_md)
pump(lambda: window.rich.is_ready and page_js(window.rich, "document.querySelector('#editor .md-shield') !== null"), 3)
page_js(window.rich, "(() => { const v = window.mdEditor.view; v.dispatch(v.state.tr.insertText('X', v.state.doc.content.size - 1)); return 0; })()")
check(pump(lambda: window.dirty, 3), "an edit after the raw HTML block")
# QTest cannot double-click in the page (see Task 16): dispatch the DOM event the page handles.
page_js(window.rich, "document.querySelector('#editor .md-shield')"
                     ".dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true }))")
check(pump(lambda: window.mode == "source", 3) and window.act_source.isChecked(), "double-clicking raw HTML switches to Source")
check(window.editor.textCursor().blockNumber() + 1 == 3, f"the caret is on the block's first line ({window.editor.textCursor().blockNumber() + 1})")
check(window.dirty and window.buffer == "intro\n\n<div>\nraw\n</div>\n\nafterX\n", f"the edit came along ({window.buffer!r})")
FAKE["answer"] = S.Discard
window.on_new()

# --- Code block highlight comes back after editing ---------------------------------
hl_md = TMP / "highlight.md"
hl_md.write_bytes(b"intro\n\n```python\nx = 1\n```\n\nafter\n")
window.open_file(hl_md)
HAS_HL = "document.querySelector('#editor .md-code-block').classList.contains('md-has-highlight')"
check(window.mode == "rendered" and pump(lambda: window.rich.is_ready and page_js(window.rich, HAS_HL), 3),
      "a code block shows its highlight after loading")
window.rich.focus_block(1)
page_js(window.rich, "(() => { const v = window.mdEditor.view; v.dispatch(v.state.tr.insertText('y', v.state.selection.from)); return 0; })()")
check(pump(lambda: window.dirty, 3) and page_js(window.rich, HAS_HL) is False, "typing in a code block drops its highlight")
window.rich.focus_block(2)
check(pump(lambda: page_js(window.rich, HAS_HL), 3), "leaving the edited code block restores its highlight")
check(page_js(window.rich, "document.querySelector('#editor .md-code-highlight').textContent").strip() == "yx = 1",
      "the restored highlight is for the edited text")
check(window.dirty, "restoring the highlight leaves the edit pending")
FAKE["answer"] = S.Discard
window.on_new()

# --- WYSIWYG Task 17: Edit menu, context menu and Find in Rendered mode -------------
from PySide6.QtCore import QMimeData  # noqa: E402
from PySide6.QtGui import QAction  # noqa: E402
from PySide6.QtWidgets import QMenu  # noqa: E402

CTRL = Qt.KeyboardModifier.ControlModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier
SELECTED_JS = "(() => { const s = window.mdEditor.view.state.selection; return window.mdEditor.view.state.doc.textBetween(s.from, s.to); })()"
FINDING_JS = "document.body.classList.contains('md-finding')"


def page_text() -> str:
    return page_js(window.rich, "window.mdEditor.view.state.doc.textContent")


def page_key(key, modifiers, text: str) -> None:
    """A key as a real keyboard sends it (Ctrl+Z carries the text "\\x1a"), into the page."""
    window.rich.setFocus()
    QTest.sendKeyEvent(QTest.KeyAction.Click, window.rich.focusProxy(), key, text, modifiers)


def select_all_in_page() -> None:
    """Edit > Select All, then wait for it: a web action sent at once may run before it."""
    window.act_select_all.trigger()
    check(pump(lambda: page_js(window.rich, "window.mdEditor.view.state.selection.from === 0 && window.mdEditor.view.state"
                                            ".selection.to === window.mdEditor.view.state.doc.content.size"), 3),
          "Edit > Select All selects the whole page document")


def to_clipboard(html: str, text: str) -> None:
    """A browser copy: the page reads the HTML only with CF_HTML's fragment markers (Task 11)."""
    mime = QMimeData()
    mime.setData("text/html", f"<html><body><!--StartFragment-->{html}<!--EndFragment--></body></html>".encode())
    mime.setText(text)
    QApplication.clipboard().setMimeData(mime)


# the Edit menu: Paste as Plain Text after Paste; the page's formatting keys stay the page's
check([a.text() for a in window.menu_edit.actions() if not a.isSeparator()]
      == ["&Undo", "&Redo", "Cu&t", "&Copy", "&Paste", "Paste as P&lain Text", "&Find...", "&Replace...", "Select &All"],
      "the Edit menu adds Paste as Plain Text after Paste")
check(window.act_paste_plain.shortcut().toString() == "Ctrl+Shift+V", "Paste as Plain Text is Ctrl+Shift+V")
PAGE_KEYS = {"Ctrl+B", "Ctrl+I", "Ctrl+K", "Ctrl+Shift+X", "Ctrl+`", "Ctrl+Space", "Ctrl+Shift+7", "Ctrl+Shift+8",
             "Ctrl+Shift+9", "Ctrl+Shift+.", *(f"Ctrl+Alt+{n}" for n in range(7))}
taken = {a.shortcut().toString() for a in window.findChildren(QAction)} & PAGE_KEYS
check(not taken, f"no menu shortcut takes the page's formatting keys ({taken})")

# Undo and Redo follow the page's history; their keys undo one step, as the menu does
edit_md = TMP / "edit.md"
edit_md.write_bytes(b"one\n")
window.open_file(edit_md)
check(pump(lambda: "undo" in window._page_can, 3) and not window.act_undo.isEnabled() and not window.act_redo.isEnabled(),
      "Rendered: Undo and Redo are greyed with nothing to undo")
window.rich.focus_block(0)
type_rendered(window, "X")
pump(lambda: False, 0.6)  # past prosemirror-history's 500 ms grouping: the next edit is its own step
type_rendered(window, "Y")
check(pump(lambda: window.act_undo.isEnabled(), 3) and not window.act_redo.isEnabled(), "an edit enables Undo")
page_key(Qt.Key.Key_Z, CTRL, "\x1a")
check(pump(lambda: page_text() == "Xone", 3), f"Ctrl+Z undoes one step ({page_text()!r})")
check(pump(lambda: window.act_redo.isEnabled(), 3), "an undo enables Redo")
page_key(Qt.Key.Key_Y, CTRL, "\x19")
check(pump(lambda: page_text() == "XYone", 3), f"Ctrl+Y redoes it ({page_text()!r})")
window.act_undo.trigger()
check(pump(lambda: page_text() == "Xone", 3), "Edit > Undo undoes one step")
window.act_redo.trigger()
check(pump(lambda: page_text() == "XYone", 3), "Edit > Redo redoes it")
window.act_undo.trigger()
window.act_undo.trigger()
check(pump(lambda: page_text() == "one" and not window.act_undo.isEnabled(), 3), "Undo greys out at the start of the history")

# the clipboard: Paste keeps formatting (schema rules), Paste as Plain Text and Ctrl+Shift+V do not
to_clipboard('<b>bold</b> <a href="javascript:alert(1)">bad</a>', "bold bad")
select_all_in_page()
window.act_paste.trigger()
check(pump(lambda: page_text() == "bold bad", 3) and '"strong"' in page_doc() and "javascript" not in page_doc(),
      f"Edit > Paste keeps bold and drops the unsafe link ({page_doc()})")
select_all_in_page()
window.act_paste_plain.trigger()
check(pump(lambda: '"strong"' not in page_doc(), 3) and page_text() == "bold bad", "Paste as Plain Text drops the formatting")
select_all_in_page()
window.act_paste.trigger()
pump(lambda: '"strong"' in page_doc(), 3)
select_all_in_page()
page_key(Qt.Key.Key_V, CTRL | SHIFT, "\x16")
check(pump(lambda: '"strong"' not in page_doc(), 3) and page_text() == "bold bad",
      f"Ctrl+Shift+V pastes plain text once ({page_text()!r})")
select_all_in_page()
window.act_copy.trigger()
check(pump(lambda: QApplication.clipboard().text() == "bold bad", 3), "Edit > Copy copies the page selection")
QApplication.clipboard().clear()
select_all_in_page()
window.act_cut.trigger()
check(pump(lambda: page_text() == "" and QApplication.clipboard().text() == "bold bad", 3), "Edit > Cut cuts it")
window.act_source.trigger()
check(pump(lambda: window.mode == "source", 5) and window.act_undo.isEnabled() and window.act_redo.isEnabled(),
      "Source: Undo and Redo stay enabled (v1)")
window.editor.setPlainText("plain text")
window.act_select_all.trigger()
window.act_cut.trigger()
check(window.buffer == "", "Source: Edit > Cut acts on the text editor")
window.act_paste_plain.trigger()
check(window.buffer == "plain text", "Source: Paste as Plain Text pastes the text")
QApplication.clipboard().clear()  # a clipboard still owning our data crashes Qt at exit (Task 11)
FAKE["answer"] = S.Discard
window.on_new()

# Find in Rendered mode: the page's find-in-page, find only
bar = window.find_bar
find_md = TMP / "find.md"
find_md.write_bytes(b"alpha beta Alpha\n\n```python\nalpha = 1\n```\n\nalpha end\n")
window.open_file(find_md)
check(pump(lambda: window.rich.is_ready and page_js(window.rich, HAS_HL), 3), "a highlighted code block to search")
window.act_find.trigger()
check(bar.isVisible() and bar.web_mode and not bar.replace_row.isVisible(), "Ctrl+F in Rendered mode shows the find row only")
check(pump(lambda: page_js(window.rich, FINDING_JS), 3), "code blocks show plain text while the bar is open")
bar.find_edit.setText("alpha")
check(pump(lambda: bar.count_label.text() == "1 of 4", 3), f"the match count counts the code block once ({bar.count_label.text()})")
bar.find_next()
check(pump(lambda: bar.count_label.text() == "2 of 4", 3), "Next moves to the second match")
window.act_find.trigger()
pump(lambda: False, 0.3)
check(bar.count_label.text() == "2 of 4", "Ctrl+F on the open bar keeps the current match")
bar.find_previous()
check(pump(lambda: bar.count_label.text() == "1 of 4", 3), "Previous moves back")
bar.find_previous()
check(pump(lambda: bar.count_label.text() == "4 of 4", 3), "Previous wraps to the last match")
bar.case_box.setChecked(True)
check(pump(lambda: bar.count_label.text().endswith(" of 3"), 3), f"Match case narrows the matches ({bar.count_label.text()})")
bar.case_box.setChecked(False)
bar.find_edit.setText("zzz")
check(pump(lambda: bar.count_label.text() == "No results", 3), "no hits shows No results")
bar.find_edit.setText("")
check(bar.count_label.text() == "", "an empty search clears the count")
bar.find_edit.setText("beta")
check(pump(lambda: bar.count_label.text() == "1 of 1", 3), "a new search")
QTest.keyClick(bar.find_edit, Qt.Key.Key_Escape)
check(not bar.isVisible() and pump(lambda: not page_js(window.rich, FINDING_JS), 3), "Esc closes the bar; the highlights come back")
check(pump(lambda: page_js(window.rich, SELECTED_JS) == "beta", 3), "the found text stays selected in the editor")
check(not window.dirty, "finding changes nothing")
window.act_find.trigger()
check(bar.find_edit.text() == "beta", "the page selection seeds the find field")
window.act_source.trigger()
check(window.mode == "source" and not bar.isVisible() and not bar.web_mode, "a mode switch closes the find bar")
check(page_js(window.rich, FINDING_JS) is False, "and the page's code highlights come back")
window.act_find.trigger()
bar.find_edit.setText("alpha")
check(bar.count_label.text() == "1 of 4" and selected() == "alpha", "Source mode searches the text editor again")
QTest.keyClick(bar.find_edit, Qt.Key.Key_Escape)
window.act_rendered.trigger()
finder = richview.RichView("light")
finder.show()
pump(lambda: finder.is_ready, 5)
finder.set_finding(True)
finder.restart()
check(pump(lambda: finder.is_ready, 5) and page_js(finder, FINDING_JS) is True, "a restarted page keeps the find bar's state")
finder.close()
finder.deleteLater()

# Replace from Rendered mode: Source with the Rendered edits, Replace bar open
window.rich.focus_block(2)
type_rendered(window, "Z")
window.act_replace.trigger()
check(pump(lambda: window.mode == "source", 5) and bar.isVisible() and bar.replace_row.isVisible() and not bar.web_mode,
      "Ctrl+H in Rendered mode switches to Source and opens Replace")
check(window.dirty and "Zalpha end" in window.buffer, f"the Rendered edit came along ({window.buffer!r})")
bar.find_edit.setText("alpha")
bar.replace_edit.setText("omega")
check(bar.replace_all() == 4, "Replace works on the switched text")
bar.close_bar()
FAKE["answer"] = S.Discard
window.on_new()

# the cell context menu: a native menu built from the page's state at the right-clicked place
table_md = TMP / "table.md"
table_md.write_bytes(b"intro\n\n| a | b |\n| --- | --- |\n")
window.open_file(table_md)
pump(lambda: window.rich.is_ready, 3)
window.rich.focus_block(0)


def right_click(selector: str) -> QMenu | None:
    """A real right-click in the middle of `selector`; the menu it shows, if any."""
    window.context_menu = None
    point = page_js(window.rich, f"(() => {{ const b = document.querySelector({json.dumps(selector)}).getBoundingClientRect();"
                                 " return [Math.round(b.left + b.width / 2), Math.round(b.top + b.height / 2)]; })()")
    QTest.mouseClick(window.rich.focusProxy(), Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, QPoint(*point))
    pump(lambda: window.context_menu is not None and window.context_menu.isVisible(), 3)
    return window.context_menu


def pick(menu: QMenu | None, text: str) -> None:
    """Chooses the item `text` of a shown menu, if it has one, and closes the menu."""
    for act in menu.actions() if menu else []:
        if act.text() == text:
            act.trigger()
    if menu:
        menu.close()


EDIT_ITEMS = [window.act_undo, window.act_redo, None, window.act_cut, window.act_copy, window.act_paste,
              window.act_paste_plain, None, window.act_select_all]
window.rich.selectionState.disconnect(window._on_selection_state)  # only a fresh read sees the moved caret
menu = right_click("#editor th:last-child")
window.rich.selectionState.connect(window._on_selection_state)
check(menu is not None, "a right-click in the page shows the context menu")
items = [None if a.isSeparator() else a for a in menu.actions()] if menu else []
check(items[:9] == EDIT_ITEMS, "it starts with the Edit menu's own items")
TABLE_TEXTS = [None, "Insert row above", "Insert row below", None, "Insert column left", "Insert column right",
               None, "Delete row", "Delete column", "Delete table",
               None, "Align column left", "Align column center", "Align column right"]
table_items = [None if a.isSeparator() else a.text() for a in menu.actions()[9:]] if menu else []
check(table_items == TABLE_TEXTS and all(a.isEnabled() for a in menu.actions()[9:]),
      f"right-clicking a cell (the caret was outside the table) adds the table items ({table_items})")
crafted = window._build_context_menu({"can": {"addRowAfter": True, "deleteRow": False, "setColumnAlign": True}})
check([None if a.isSeparator() else a.text() for a in crafted.actions()[9:]] == TABLE_TEXTS
      and [a.text() for a in crafted.actions()[9:] if a.isEnabled() and not a.isSeparator()]
      == ["Insert row below", "Align column left", "Align column center", "Align column right"],
      "each table item is enabled from selectionState.can")
crafted.deleteLater()
pick(menu, "Align column right")
pick(right_click("#editor th:last-child"), "Insert row below")
check(pump(lambda: window.dirty, 3), "a table item edits the document")
window.on_save()
check(pump(lambda: not window.dirty, 5) and table_md.read_bytes() == b"intro\n\n| a | b |\n| --- | ---: |\n|  |  |\n",
      f"the table items reach the saved file ({table_md.read_bytes()!r})")
menu = right_click("#editor p")
check(menu is not None and [None if a.isSeparator() else a for a in menu.actions()] == EDIT_ITEMS,
      "outside a table: the edit items only")
if menu:
    menu.close()
window.context_menu = None
window.rich.customContextMenuRequested.emit(QPoint(5, 5))
window.act_source.trigger()
pump(lambda: False, 0.5)
check(window.context_menu is None, "no menu once the window has left Rendered mode")
FAKE["answer"] = S.Discard
window.on_new()

# Ctrl+Shift+V with the focus in a find field pastes into the field, not the document (review fix)
field_md = TMP / "field.md"
field_md.write_bytes(b"keep\n")
window.open_file(field_md)
pump(lambda: window.rich.is_ready, 3)
QApplication.clipboard().setText("PASTED")
window.activateWindow()  # shortcuts only fire in the active window
pump(lambda: window.isActiveWindow(), 3)
for mode_action, mode_name in ((window.act_rendered, "Rendered"), (window.act_source, "Source")):
    mode_action.trigger()
    pump(lambda: window.mode == mode_name.lower() and (mode_name == "Source" or window.rich.is_ready), 5)
    window.find_bar.open_find()
    window.find_bar.find_edit.clear()
    window.find_bar.find_edit.setFocus()
    QTest.sendKeyEvent(QTest.KeyAction.Click, window.find_bar.find_edit, Qt.Key.Key_V, "\x16", CTRL | SHIFT)
    pump(lambda: False, 0.3)
    check(window.find_bar.find_edit.text() == "PASTED" and not window.dirty and window.buffer == "keep\n",
          f"{mode_name}: Ctrl+Shift+V in the find field pastes into the field ({window.find_bar.find_edit.text()!r}, {window.buffer!r})")
    window.find_bar.close_bar()
QApplication.clipboard().clear()
FAKE["answer"] = S.Discard
window.on_new()

# --- Later tasks insert their checks directly above this line. ---

shutil.rmtree(TMP, ignore_errors=True)
if FAILURES:
    print("SMOKE FAILED:")
    for label in FAILURES:
        print(f"  - {label}")
    sys.exit(1)
print("SMOKE OK")
