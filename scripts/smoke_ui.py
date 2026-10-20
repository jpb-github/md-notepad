"""Headless UI smoke test for MD Viewer.

Run: .venv\\Scripts\\python scripts\\smoke_ui.py  ->  prints SMOKE OK or the failed checks.
Lives outside tests/ because tests/ must never import Qt.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
TMP = Path(tempfile.mkdtemp(prefix="mdviewer-smoke-"))
os.environ["APPDATA"] = str(TMP / "appdata")  # never touch the real settings.json
# The offscreen platform ships an empty font database; point it at the Windows fonts
# so the Preferences font list (fixed-pitch filter) has something to filter.
os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts"))

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
check(window.mode == "preview", "starts in preview mode")
check(window.stack.currentIndex() == 0, "preview page shown at startup")
check(window.windowTitle() == "Untitled - MD Viewer", "Untitled title at startup")

# --- Menus and shortcuts (spec section 3) ----------------------------------
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
    (window.act_preview, "Ctrl+P"), (window.act_edit, "Ctrl+E"),
    (window.act_zoom_in, "Ctrl+="), (window.act_zoom_out, "Ctrl+-"),
    (window.act_zoom_reset, "Ctrl+0"),
]:
    check(act.shortcut().toString() == keys, f"{act.text()} shortcut is {keys}")
check(window.act_copy.isEnabled(), "Copy enabled in preview mode")
check(not window.act_paste.isEnabled(), "Paste disabled in preview mode")
check(window.act_zoom_in.isEnabled(), "Zoom enabled in preview mode")
check(window.act_wrap.isChecked(), "Word Wrap on by default")

# --- Open: encoding, CRLF, NBSP, title, status bar --------------------------
check(window.open_file(sample), "open_file returns True")
check(window.buffer == SAMPLE_TEXT, "buffer uses \\n breaks and keeps NBSP")
check(window.newline == "\r\n", "CRLF newline style detected")
check(window.encoding == "utf-8", "UTF-8 detected")
check(window.windowTitle() == "sample.md - MD Viewer", "title shows file name")
check(window._left_label.text() == "Preview", "status left shows Preview")
size = len(sample.read_bytes())
check(window._right_label.text() == f"100% | UTF-8 | {size} B", "status right shows zoom, encoding, size")

# --- Open failure keeps the current document --------------------------------
ERRORS.clear()
check(not window.open_file(TMP / "missing.md"), "missing file returns False")
check(len(ERRORS) == 1 and "File not found." in ERRORS[0], "missing-file error uses Notepad wording")
check(window.loaded_path == sample, "failed open keeps the current document")

# --- Edit mode chrome -------------------------------------------------------
window.act_edit.trigger()
check(window.mode == "edit" and window.stack.currentIndex() == 1, "Edit Mode shows the editor page")
check(window.act_undo.isEnabled() and window.act_paste.isEnabled(), "edit actions enabled in edit mode")
check(window.act_copy.isEnabled(), "Copy enabled in edit mode")
check(not window.act_zoom_in.isEnabled(), "Zoom disabled in edit mode")
check(window.act_find.isEnabled() and window.act_replace.isEnabled(), "Find/Replace enabled in edit mode")
window.editor.moveCursor(START)
check(window._left_label.text() == "Ln 1, Col 1", "status shows Ln 1, Col 1 at start")
window.editor.moveCursor(END)
check(window._left_label.text() == "Ln 4, Col 1", "status follows the cursor")

# --- Dirty buffer, Edit -> Preview prompt: Cancel ---------------------------
window.editor.insertPlainText("edited\n")
check(window.dirty, "typing marks the buffer dirty")
check(window.windowTitle() == "*sample.md - MD Viewer", "dirty title has * prefix")
FAKE["answer"] = S.Cancel
ASKED.clear()
window.act_preview.trigger()
check(ASKED == ["Save changes to sample.md?"], "Edit -> Preview asks to save")
check(window.mode == "edit" and window.dirty, "Cancel stays in edit mode with edits")
check(window.act_edit.isChecked() and not window.act_preview.isChecked(), "Cancel restores the Edit Mode radio")

# --- Don't Save restores disk content ---------------------------------------
FAKE["answer"] = S.Discard
window.act_preview.trigger()
check(window.mode == "preview" and window.stack.currentIndex() == 0, "Don't Save switches to preview")
check(not window.dirty and window.buffer == SAMPLE_TEXT, "Don't Save restores the disk content")

# --- Save keeps CRLF and NBSP -----------------------------------------------
window.act_edit.trigger()
window.editor.moveCursor(END)
window.editor.insertPlainText("more\n")
FAKE["answer"] = S.Save
window.act_preview.trigger()
check(
    sample.read_bytes() == "# Café\r\n\r\nline\u00a0two\r\nmore\r\n".encode("utf-8"),
    "save writes CRLF and NBSP exactly",
)
check(window.mode == "preview" and not window.dirty, "Save switches to preview and clears dirty")
check(window.windowTitle() == "sample.md - MD Viewer", "title clean after save")

# --- Unencodable text in a Windows-1252 file --------------------------------
legacy = TMP / "legacy.md"
legacy.write_bytes(b"caf\xe9\n")
window.open_file(legacy)
check(window.encoding == "windows-1252", "Windows-1252 detected")
check("Windows-1252" in window._right_label.text(), "status shows Windows-1252")
window.act_edit.trigger()
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
check(window.mode == "edit" and window.stack.currentIndex() == 1, "New opens in edit mode")
check(window.loaded_path is None and window.buffer == "", "New gives an empty Untitled buffer")
check(window.windowTitle() == "Untitled - MD Viewer", "New shows Untitled title")
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

# --- Open from edit mode lands in preview -----------------------------------
FAKE["answer"] = S.Discard
FAKE["open_path"] = str(sample)
window.on_open()
check(window.loaded_path == sample, "File > Open loads the picked file")
check(window.mode == "preview" and window.stack.currentIndex() == 0, "open from edit mode shows preview")
check(window.act_preview.isChecked(), "open from edit mode checks Preview Mode")

# --- Drag-and-drop with a dirty buffer --------------------------------------
window.act_edit.trigger()
window.editor.insertPlainText("x")
FAKE["answer"] = S.Cancel
window._open_dropped([str(legacy)])
check(window.loaded_path == sample and window.dirty, "cancelled drop keeps the document")
FAKE["answer"] = S.Discard
window._open_dropped([str(legacy)])
check(window.loaded_path == legacy and window.mode == "preview", "drop opens the file in preview")

# --- Window close with unsaved changes --------------------------------------
window.act_edit.trigger()
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
check(window.mode == "preview" and not window.dirty, "Close returns to clean preview")
check(window.windowTitle() == "Untitled - MD Viewer", "Close shows Untitled title")

# --- Zoom -------------------------------------------------------------------
window._zoom_in()
check(window._zoom == 1.25, "Zoom In multiplies by 1.25")
check(window._left_label.text() == "Preview 125%", "status left shows zoom when not 100%")
check(window._right_label.text().startswith("125% | "), "status right shows zoom")
for _ in range(20):
    window._zoom_in()
check(window._zoom == 3.0, "zoom clamps at 300%")
for _ in range(40):
    window._zoom_out()
check(window._zoom == 0.25, "zoom clamps at 25%")
window._zoom_reset()
check(window._zoom == 1.0 and window.preview.zoomFactor() == 1.0, "Zoom Reset returns to 100%")

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

# --- Task 9: preview rendering ------------------------------------------------
from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings  # noqa: E402

from mdviewer import preview as preview_module  # noqa: E402
from mdviewer.core import render  # noqa: E402

check(isinstance(window.preview, preview_module.MarkdownPreview), "preview is a MarkdownPreview")
check(
    not window.preview.settings().testAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled),
    "JavaScript is disabled in the preview",
)
doc = TMP / "doc.md"
doc.write_text("# Title\n\n![pic](pic.png)\n\n[web](https://example.com)\n", encoding="utf-8")
FAKE["answer"] = S.Discard
check(window.open_file(doc), "open doc.md")
rendered = window.preview.last_html
check("<h1>Title</h1>" in rendered, "preview renders Markdown headings")
check((TMP / "pic.png").as_uri() in rendered, "relative image resolved against the file's folder")
check(window.preview.page_file.read_text(encoding="utf-8") == rendered, "page file holds the rendered HTML")
check("#1f2328" in rendered, "light CSS by default")
window._effective_theme = "dark"
window._render_preview()
check("#0d1117" in window.preview.last_html, "dark CSS when the effective theme is dark")
window._effective_theme = "light"


def boom(text, base_dir=None):
    raise RuntimeError("renderer bug")


original_render_body = render.render_body
render.render_body = boom
window.statusBar().clearMessage()
window._render_preview()
render.render_body = original_render_body
check('<pre class="fallback">' in window.preview.last_html, "render failure falls back to <pre>")
check("plain text" in window.statusBar().currentMessage(), "render failure shows a status warning")

OPENED: list = []
preview_module.open_external = OPENED.append
LINK = QWebEnginePage.NavigationType.NavigationTypeLinkClicked
page = window.preview.page()
check(not page.acceptNavigationRequest(QUrl("https://example.com"), LINK, True), "web link does not navigate the preview")
check(OPENED == [QUrl("https://example.com")], "web link opens externally")
anchor = QUrl.fromLocalFile(str(window.preview.page_file))
anchor.setFragment("fn-1")
check(page.acceptNavigationRequest(anchor, LINK, True), "in-page anchor stays in the preview")
check(len(OPENED) == 1, "in-page anchor does not open externally")

big = TMP / "big.md"
big.write_text("".join(f"Line {i} with some **bold** text.\n\n" for i in range(60000)), encoding="utf-8")
check(window.open_file(big), "open a large document")
check(window.preview.page_file.stat().st_size > 2 * 1024 * 1024, "pages over 2 MB are rendered")

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
watched = TMP / "watched.md"
watched.write_bytes(b"one\n")
FAKE["answer"] = S.Discard
window.open_file(watched)
ASKED.clear()
window._poll_disk()
check(window.buffer == "one\n" and not ASKED, "unchanged file: nothing happens")

# preview mode: silent re-render
watched.write_bytes(b"two two\n")
window._poll_disk()
check(window.buffer == "two two\n" and "two two" in window.preview.last_html, "preview re-renders silently")
check(not ASKED and not window.dirty, "silent re-render asks nothing")

# own save is not an external change
window.act_edit.trigger()
window.editor.moveCursor(END)
window.editor.insertPlainText("mine\n")
check(window.on_save(), "save in edit mode")
window._poll_disk()
check(not ASKED, "own save does not trigger the dialog")

# edit mode: dialog first, then Reload
watched.write_bytes(b"external 1\n")
FAKE["answer"] = S.Yes
window._poll_disk()
check(len(ASKED) == 1 and '"watched.md" was modified externally at' in ASKED[0], "edit mode asks before replacing")
check(window.buffer == "external 1\n" and not window.dirty, "Reload loads the disk content")
check(window.mode == "edit", "Reload stays in edit mode")

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
window.act_preview.trigger()
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
check(window.buffer == "back again\n", "reappearing file re-renders")

# Save recreates a deleted file without a false alarm
window.act_edit.trigger()
watched.unlink()
window._poll_disk()
window.editor.insertPlainText("x")
check(window.on_save() and watched.exists(), "Save recreates a deleted file")
window._poll_disk()
check(not ASKED, "recreating save raises no change dialog")

# preview read failure is retried on the next tick
window.act_preview.trigger()
window._read_disk = lambda: None
watched.write_bytes(b"locked content!\n")
window.statusBar().clearMessage()
window._poll_disk()
check("Could not read" in window.statusBar().currentMessage(), "read failure warns")
check("locked content" not in window.preview.last_html, "read failure keeps the last render")
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

# Untitled: nothing to watch
window.on_close()
window._poll_disk()
check(window._watcher is None, "no watcher for Untitled")

# --- Task 12: find / replace ------------------------------------------------------
bar = window.find_bar
FAKE["answer"] = S.Discard
window.on_close()
check(not window.act_find.isEnabled() and not window.act_replace.isEnabled(), "Find/Replace disabled in preview")
window.on_new()
check(window.act_find.isEnabled() and window.act_replace.isEnabled(), "Find/Replace enabled in edit mode")
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
FAKE["system_theme"] = "dark"
window._poll_theme()
check(window._effective_theme == "dark", "System mode follows Windows switching to dark")
check(qt_app.style().name().lower() == "fusion" and window_color() == DARK_WINDOW, "dark palette on the Fusion style")
check("#0d1117" in window.preview.last_html, "preview re-rendered with dark CSS")
check("on disk only" not in window.preview.last_html, "theme switch re-renders the buffer, not the disk")
check(window.mode == "preview" and not window.dirty, "theme switch keeps mode and dirty state")
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
check("#3a3d41" in window.preview.last_html, "preview re-rendered with gray CSS")
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
check("#0d1117" in restarted.preview.last_html, "startup preview is already dark")
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
rw.act_edit.trigger()
rw.editor.insertPlainText("dirty")
FAKE["answer"] = S.Cancel
ASKED.clear()
recent_entries(rw)[1].trigger()
check(len(ASKED) == 1 and rw.loaded_path == sample, "a dirty buffer is asked about before opening a recent file")
FAKE["answer"] = S.Discard
recent_entries(rw)[1].trigger()
check(rw.loaded_path == rdoc and rw.mode == "preview", "clicking an entry opens it in preview")
check(recent_paths(rw)[0] == abs_(rdoc), "the opened entry moves to the front")

# a vanished file reports the error and drops its entry
ERRORS.clear()
entry = [a for a in recent_entries(rw) if a.data() == abs_(gone)][0]
entry.trigger()
check(len(ERRORS) == 1 and "File not found." in ERRORS[0], "a missing recent file shows the Notepad-style error")
check(abs_(gone) not in recent_paths(rw), "a missing recent file is removed from the list")

# Save As records the new path
rw.on_new()
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
check(window.act_preferences.isEnabled(), "Preferences enabled in preview mode")
window.act_edit.trigger()
check(window.act_preferences.isEnabled(), "Preferences enabled in edit mode")
window.act_preview.trigger()

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
check(window._theme_choice == "system" and window.mode == "preview" and not window.dirty, "font change keeps theme, mode and dirty state")

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

# --- Later tasks insert their checks directly above this line. ---

shutil.rmtree(TMP, ignore_errors=True)
if FAILURES:
    print("SMOKE FAILED:")
    for label in FAILURES:
        print(f"  - {label}")
    sys.exit(1)
print("SMOKE OK")
