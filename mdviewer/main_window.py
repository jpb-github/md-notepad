"""Main window: menus, mode switching, file operations, status bar."""

import os
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QRect, QTimer
from PySide6.QtGui import QActionGroup, QColor, QFont, QGuiApplication, QKeySequence, QPalette, QTextCursor
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from mdviewer.core import docmodel, encoding, frontmatter, serialize, settings, themeservice
from mdviewer.core.filewatch import Watcher, WatchEvent
from mdviewer.editor import MarkdownEditor
from mdviewer.findbar import FindBar
from mdviewer.preferences import PreferencesDialog
from mdviewer.richview import RichView
from mdviewer.toolbar import FormatToolbar

APP_NAME = "MD Viewer"
ZOOM_MIN = 0.25
ZOOM_MAX = 3.0
ZOOM_STEP = 1.25
DEFAULT_SIZE = (900, 700)
WARNING_MS = 10000
POLL_MS = 1000
THEME_POLL_MS = 2000
LARGE_FILE_BYTES = 5 * 1024 * 1024  # spec: larger files open in Source mode
LARGE_FILE_NOTE = "Large file: opened in Source mode"
OPEN_FAILED_NOTE = "Opened in Source mode: the rendered editor could not load this file."
SWITCH_FAILED_NOTE = "Staying in Source mode: the rendered editor could not load this document."
EDITOR_FAILED_NOTE = "Rendered mode is unavailable: the rendered editor did not start."
STOPPED_TEXT = "The rendered editor stopped responding."  # spec section 7
HUNG_DETAIL = (
    "Retry waits for it again. Switch to Source continues with the document as it was last "
    "opened, saved or switched between modes: Rendered edits made since then are lost."
)
CRASHED_DETAIL = (
    "Rendered edits made since the document was last opened, saved or switched between modes "
    "are lost. Retry reloads the rendered editor; Switch to Source continues in Source mode."
)
DARK_PALETTE_COLORS = {
    "window": "#202020",
    "window_text": "#f0f0f0",
    "base": "#191919",
    "alternate_base": "#262626",
    "text": "#f0f0f0",
    "button": "#2b2b2b",
    "button_text": "#f0f0f0",
    "highlight": "#2f6fd6",
    "highlighted_text": "#ffffff",
    "link": "#4493f8",
    "tooltip_base": "#2b2b2b",
    "tooltip_text": "#f0f0f0",
    "placeholder": "#9a9a9a",
    "disabled_text": "#7a7a7a",
}
GRAY_PALETTE_COLORS = {
    "window": "#3a3d41",
    "window_text": "#e6e8eb",
    "base": "#2f3236",
    "alternate_base": "#35383c",
    "text": "#e6e8eb",
    "button": "#4a4e53",
    "button_text": "#e6e8eb",
    "highlight": "#2f6fd6",
    "highlighted_text": "#ffffff",
    "link": "#6cb2ff",
    "tooltip_base": "#4a4e53",
    "tooltip_text": "#e6e8eb",
    "placeholder": "#a0a6ad",
    "disabled_text": "#85898e",
}
# Themes drawn on Fusion with a custom palette (and a dark Windows title bar).
CUSTOM_PALETTES = {"dark": DARK_PALETTE_COLORS, "gray": GRAY_PALETTE_COLORS}
OPEN_FILTER = "Markdown (*.md *.markdown *.mdown *.txt);;All files (*)"
SAVE_FILTER = "Markdown (*.md);;Text (*.txt);;All files (*)"
ENCODING_LABELS = {
    "utf-8": "UTF-8",
    "utf-8-sig": "UTF-8 with BOM",
    "utf-16": "UTF-16",
    "windows-1252": "Windows-1252",
}
_DROP_EVENTS = (QEvent.Type.DragEnter, QEvent.Type.DragMove, QEvent.Type.Drop)


# --- Dialog seams: every modal goes through these (scripts/smoke_ui.py fakes them).


def ask(box: QMessageBox) -> QMessageBox.StandardButton:
    """Run a modal message box; return the standard button the user chose."""
    box.exec()
    return box.standardButton(box.clickedButton())


def show_error(parent, text: str) -> None:
    QMessageBox.critical(parent, APP_NAME, text)


def pick_open_path(parent) -> str:
    path, _ = QFileDialog.getOpenFileName(parent, "Open", "", OPEN_FILTER)
    return path


def pick_save_path(parent, start: str) -> str:
    path, _ = QFileDialog.getSaveFileName(parent, "Save As", start, SAVE_FILTER)
    return path


def run_preferences(dialog) -> bool:
    """Run the modal Preferences dialog; True when the user pressed OK."""
    return dialog.exec() == QDialog.DialogCode.Accepted


def read_system_theme() -> str:
    """Seam: the Windows app theme; 'light' on any failure or off Windows."""
    try:
        reader = themeservice.system_theme_reader()
    except ImportError:
        return "light"
    return themeservice.read_system_theme(reader)


def _custom_palette(theme: str) -> QPalette:
    c = {key: QColor(value) for key, value in CUSTOM_PALETTES[theme].items()}
    role = QPalette.ColorRole
    palette = QPalette()
    for r, key in (
        (role.Window, "window"), (role.WindowText, "window_text"), (role.Base, "base"),
        (role.AlternateBase, "alternate_base"), (role.Text, "text"), (role.Button, "button"),
        (role.ButtonText, "button_text"), (role.Highlight, "highlight"),
        (role.HighlightedText, "highlighted_text"), (role.Link, "link"),
        (role.ToolTipBase, "tooltip_base"), (role.ToolTipText, "tooltip_text"),
        (role.PlaceholderText, "placeholder"),
    ):
        palette.setColor(r, c[key])
    for r in (role.WindowText, role.Text, role.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, r, c["disabled_text"])
    return palette


def _set_dark_title_bar(window, dark: bool) -> None:
    """Best effort: match the Windows title bar (DWMWA_USE_IMMERSIVE_DARK_MODE = 20)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        value = ctypes.c_int(1 if dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(int(window.winId())), 20, ctypes.byref(value), ctypes.sizeof(value)
        )
    except (AttributeError, OSError):
        pass


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def _open_error_text(path: Path, exc: OSError) -> str:
    """Notepad-style wording for a failed open."""
    if isinstance(exc, FileNotFoundError):
        return f"{path}\nFile not found.\nCheck the file name and try again."
    if isinstance(exc, PermissionError):
        return f"{path}\nAccess is denied."
    return f"{path}\n{exc.strerror or exc}"


def _local_paths(mime) -> list[str]:
    return [url.toLocalFile() for url in mime.urls() if url.isLocalFile()]


class MainWindow(QMainWindow):
    RENDERED = "rendered"
    SOURCE = "source"

    def __init__(self, data: dict):
        super().__init__()
        self.mode = self.RENDERED
        self.dirty = False
        self.loaded_path: Path | None = None
        self.encoding = "utf-8"
        self.newline = "\n"
        self._size = 0
        self._watcher: Watcher | None = None
        self._pending_reload = False  # a Rendered re-read failed; retry on the next tick
        self._busy = False  # a "File changed on disk" dialog is open
        self._zoom = float(data.get("preview_zoom") or 1.0)
        self._theme_choice = data.get("theme") or "system"
        self._recent: list[str] = list(data.get("recent_files") or [])
        self._editor_font = {**settings.DEFAULT_FONT, **(data.get("editor_font") or {})}
        self._show_toolbar = data.get("show_toolbar", True) is not False
        self._effective_theme = "light"  # Task 13 makes this follow System/Light/Dark
        # Rendered mode: the buffer is the text last loaded into the editor page or pulled
        # from it; _block_lines are its top-level blocks' source lines (None: not parsed yet).
        self._rendered_text = ""
        self._block_lines: list[int] | None = []
        self._caret_block = 0  # top-level block of the Rendered caret (RichView.caretBlock)
        self._pending_pull = False  # a with_buffer pull is in flight; re-triggers are dropped
        self._doc_number = 0  # counts loads; a pull started before the latest one is discarded

        self.editor = MarkdownEditor()
        self._apply_editor_font()
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)

        # Start the page in the saved theme: no light flash before the first set_theme.
        self.rich = RichView(read_system_theme() if self._theme_choice == "system" else self._theme_choice)
        self.rich.changed.connect(self._on_rendered_changed)
        self.rich.caretBlock.connect(self._on_caret_block)
        self.rich.load_failed.connect(self._on_editor_failed)
        self.rich.crashed.connect(self._on_editor_crashed)
        self.rich.ready.connect(self._watch_rich_drops)
        self._watch_rich_drops()

        self.find_bar = FindBar(self.editor)
        self.find_bar.hide()
        editor_page = QWidget()
        page_layout = QVBoxLayout(editor_page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)
        page_layout.addWidget(self.editor)
        page_layout.addWidget(self.find_bar)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.rich)  # index 0
        self.stack.addWidget(editor_page)  # index 1: editor + find bar
        self.setCentralWidget(self.stack)

        self.toolbar = FormatToolbar(self)
        self.addToolBar(self.toolbar)
        self.toolbar.commandRequested.connect(self._run_format_command)
        self.rich.selectionState.connect(self.toolbar.update_state)

        self._left_label = QLabel()
        self._right_label = QLabel()
        self.statusBar().addWidget(self._left_label)
        self.statusBar().addPermanentWidget(self._right_label)

        self._build_menus()

        self.editor.modificationChanged.connect(self._on_modification)
        self.editor.cursorPositionChanged.connect(self._update_chrome)
        self.editor.viewport().installEventFilter(self)
        # A page load (restart) resets the zoom; re-apply ours after every load.
        self.rich.loadFinished.connect(self._apply_zoom)
        self._apply_zoom()

        self.setAcceptDrops(True)
        self._restore_geometry(data.get("window"))
        self._update_chrome()

        self._watch_timer = QTimer(self)
        self._watch_timer.setInterval(POLL_MS)
        self._watch_timer.timeout.connect(self._poll_disk)
        self._watch_timer.start()

        self._theme_timer = QTimer(self)
        self._theme_timer.setInterval(THEME_POLL_MS)
        self._theme_timer.timeout.connect(self._poll_theme)
        self._set_theme_choice(self._theme_choice)  # before the first paint: no light flash

    # --- Buffer ------------------------------------------------------------

    @property
    def buffer(self) -> str:
        """Source mode: editor text with \\n breaks (toPlainText() would turn NBSP into spaces).
        Rendered mode: the text last loaded into the editor page or pulled from it."""
        if self.mode == self.RENDERED:
            return self._rendered_text
        return self.editor.document().toRawText().replace("\u2029", "\n")

    def _load(self, path: Path | None, raw: bytes) -> None:
        """Decode raw file bytes into the buffer; remember encoding and newline style."""
        text, self.encoding = encoding.detect(raw)
        self.newline = "\r\n" if "\r\n" in text else "\n"
        self.loaded_path = path
        self._size = len(raw)
        self._doc_number += 1
        self._pending_pull = False  # the pull in flight is discarded; it must not block this document
        self._rendered_text = text.replace("\r\n", "\n")
        self._block_lines = None
        self.editor.setPlainText(self._rendered_text)
        self.editor.document().setModified(False)
        self.dirty = False
        self._watch(path)

    # --- Menus -------------------------------------------------------------

    def _action(self, menu, text, shortcut=None, slot=None, checkable=False):
        act = menu.addAction(text)
        if shortcut:
            act.setShortcut(QKeySequence(shortcut))
        act.setCheckable(checkable)
        if slot is not None:
            act.triggered.connect(slot)
        return act

    def _build_menus(self) -> None:
        bar = self.menuBar()

        m = self.menu_file = bar.addMenu("&File")
        self.act_new = self._action(m, "&New", "Ctrl+N", self.on_new)
        self.act_open = self._action(m, "&Open...", "Ctrl+O", self.on_open)
        self.menu_recent = m.addMenu("Open &Recent")
        self.menu_recent.setToolTipsVisible(True)  # entries show the full path
        self.act_save = self._action(m, "&Save", "Ctrl+S", self.on_save)
        self.act_save_as = self._action(m, "Save &As...", "Ctrl+Shift+S", self.on_save_as)
        self.act_close = self._action(m, "&Close", "Ctrl+W", self.on_close)
        m.addSeparator()
        self.act_exit = self._action(m, "E&xit", "Alt+F4", self.close)

        m = self.menu_edit = bar.addMenu("&Edit")
        self.act_undo = self._action(m, "&Undo", "Ctrl+Z", self.editor.undo)
        self.act_redo = self._action(m, "&Redo", "Ctrl+Y", self.editor.redo)
        m.addSeparator()
        self.act_cut = self._action(m, "Cu&t", "Ctrl+X", self.editor.cut)
        self.act_copy = self._action(m, "&Copy", "Ctrl+C", self._copy)
        self.act_paste = self._action(m, "&Paste", "Ctrl+V", self.editor.paste)
        m.addSeparator()
        self.act_find = self._action(m, "&Find...", "Ctrl+F", self.find_bar.open_find)
        self.act_replace = self._action(m, "&Replace...", "Ctrl+H", self.find_bar.open_replace)
        self.act_select_all = self._action(m, "Select &All", "Ctrl+A", self.editor.selectAll)

        m = self.menu_view = bar.addMenu("&View")
        modes = QActionGroup(self)
        self.act_rendered = self._action(
            m, "&Rendered", "Ctrl+P", lambda: self.set_mode(self.RENDERED), checkable=True
        )
        self.act_source = self._action(
            m, "&Source", "Ctrl+E", lambda: self.set_mode(self.SOURCE), checkable=True
        )
        modes.addAction(self.act_rendered)
        modes.addAction(self.act_source)
        m.addSeparator()
        self.act_toolbar = self._action(m, "&Toolbar", checkable=True)
        self.act_toolbar.setChecked(self._show_toolbar)
        self.act_toolbar.toggled.connect(self._toggle_toolbar)
        self.act_wrap = self._action(m, "&Word Wrap", checkable=True)
        self.act_wrap.setChecked(True)
        self.act_wrap.toggled.connect(self._toggle_wrap)
        m.addSeparator()
        self.act_zoom_in = self._action(m, "Zoom &In", "Ctrl+=", self._zoom_in)
        self.act_zoom_out = self._action(m, "Zoom &Out", "Ctrl+-", self._zoom_out)
        self.act_zoom_reset = self._action(m, "&Restore Default Zoom", "Ctrl+0", self._zoom_reset)
        m.addSeparator()
        self.act_preferences = self._action(m, "Pre&ferences...", "Ctrl+,", self.on_preferences)

        m = self.menu_help = bar.addMenu("&Help")
        self._action(m, "&About MD Viewer", slot=self._show_about)

        self._refresh_recent_menu()

        # Task 17 routes the Edit menu to the Rendered editor; until then its keys go to the page.
        self._source_only_actions = [
            self.act_undo, self.act_redo, self.act_cut, self.act_paste, self.act_select_all,
            self.act_find, self.act_replace,
        ]
        self._rendered_only_actions = [self.act_zoom_in, self.act_zoom_out, self.act_zoom_reset]

    # --- File operations ---------------------------------------------------

    def open_file(self, path) -> bool:
        target = Path(path)
        try:
            raw = target.read_bytes()
        except OSError as exc:
            show_error(self, _open_error_text(target, exc))
            return False
        self._load(target, raw)
        self._remember_recent(target)
        if len(raw) > LARGE_FILE_BYTES:
            self._show_mode(self.SOURCE)
            self._warn(LARGE_FILE_NOTE)
        elif not self._show_mode(self.RENDERED) and not self.rich.failed:
            self._warn(OPEN_FAILED_NOTE)
        return True

    def on_new(self) -> None:
        self._confirm_replace(self._new_document)

    def _new_document(self) -> None:
        self._load(None, b"")
        self._show_mode(self.RENDERED)

    def on_open(self) -> None:
        self._confirm_replace(self._pick_and_open)

    def _pick_and_open(self) -> None:
        path = pick_open_path(self)
        if path:
            self.open_file(path)

    def on_save(self, *, then: Callable[[], None] | None = None) -> bool:
        """True when the file was written before returning. In Rendered mode with edits not
        yet pulled, the save finishes after the pull and this returns False. then() runs once
        the file is written, now or after the pull; never when the save fails."""
        if self.loaded_path is None:
            return self.on_save_as(then=then)
        return self._save_when_ready(self.loaded_path, then)

    def on_save_as(self, *, then: Callable[[], None] | None = None) -> bool:
        start = str(self.loaded_path) if self.loaded_path else "Untitled.md"
        path = pick_save_path(self, start)
        if not path:
            return False
        target = Path(path)
        if not target.suffix:
            target = target.with_suffix(".md")
        return self._save_when_ready(target, then)

    def on_close(self) -> None:
        self._confirm_replace(self._new_document)

    def _save_when_ready(self, path: Path, then: Callable[[], None] | None = None) -> bool:
        saved: list[bool] = []

        def save(_text: str) -> None:
            saved.append(self._save_to(path))
            if saved[0] and then is not None:
                then()

        self.with_buffer(save)
        return saved == [True]

    def _save_to(self, path: Path) -> bool:
        """Write the buffer with the file's own newline style and encoding."""
        text = self.buffer.replace("\n", self.newline)
        try:
            raw = encoding.encode(text, self.encoding)
        except UnicodeEncodeError:
            if not self._offer_utf8(path):
                return False
            self.encoding = "utf-8"
            raw = encoding.encode(text, self.encoding)
        try:
            path.write_bytes(raw)
        except OSError as exc:
            show_error(self, f"{path}\n{exc.strerror or exc}")
            return False
        self.loaded_path = path
        self._size = len(raw)
        self.editor.document().setModified(False)
        self.dirty = self.mode == self.RENDERED and self.rich.modified  # an edit made since the pull
        self._note_own_write(path)
        self._remember_recent(path)
        self._update_chrome()
        return True

    def _offer_utf8(self, path: Path) -> bool:
        label = ENCODING_LABELS.get(self.encoding, self.encoding)
        box = QMessageBox(
            QMessageBox.Icon.Warning,
            APP_NAME,
            f"{path.name} contains characters that cannot be saved in {label}.\n"
            "Save it as UTF-8 instead?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            self,
        )
        box.setDefaultButton(QMessageBox.StandardButton.Yes)
        return ask(box) == QMessageBox.StandardButton.Yes

    def _prompt_save(self, then: Callable[[], None]) -> None:
        """Ask 'Save changes to <name>?'. Don't Save: then() at once. Save: then() once the file
        is written (after a Rendered pull), asking again if an edit came in meanwhile."""
        name = self.loaded_path.name if self.loaded_path else "Untitled"
        buttons = QMessageBox.StandardButton
        box = QMessageBox(
            QMessageBox.Icon.Warning,
            APP_NAME,
            f"Save changes to {name}?",
            buttons.Save | buttons.Discard | buttons.Cancel,
            self,
        )
        box.setDefaultButton(buttons.Save)
        box.button(buttons.Discard).setText("Don't Save")
        answer = ask(box)
        if answer == buttons.Save:
            self.on_save(then=lambda: self._confirm_replace(then))
        elif answer == buttons.Discard:
            then()

    def _confirm_replace(self, then: Callable[[], None]) -> None:
        """then() once the buffer may be replaced: it is clean, was saved or was discarded.
        Nothing on Cancel or a failed save; dropped while a pull is in flight (spec 6.4)."""
        if self._pending_pull:
            return
        if self.dirty:
            self._prompt_save(then)
        else:
            then()

    # --- Modes -------------------------------------------------------------

    def set_mode(self, mode: str) -> None:
        """Switch without a prompt; the dirty flag carries over, each mode starts a new undo history."""
        self._update_chrome()  # the action group already moved the radio; it follows self.mode
        if mode == self.mode:
            return
        if mode == self.SOURCE:
            self.with_buffer(self._enter_source)
            return
        line = self.editor.textCursor().blockNumber() + 1
        if self._show_mode(self.RENDERED):
            self.rich.focus_block(self._block_at_line(line))
        else:
            self._warn(SWITCH_FAILED_NOTE)

    def with_buffer(self, fn: Callable[[str], None]) -> None:
        """fn(text) with the current buffer: at once in Source mode or when the Rendered document
        is unchanged since it was loaded or last pulled; otherwise after pulling it. Dropped
        while another pull is in flight (spec 6.4)."""
        if self._pending_pull:
            return
        if self.mode != self.RENDERED or not self.rich.modified:
            fn(self.buffer)
            return
        self._pending_pull = True
        number = self._doc_number
        self.rich.request_document(lambda doc: self._pulled(doc, fn, number))

    def _pulled(self, doc: dict | None, fn: Callable[[str], None], number: int) -> None:
        if number != self._doc_number:
            return  # another document was loaded meanwhile: this one is gone
        self._pending_pull = False
        if doc is None:
            # A crash answers pulls before rich.crashed, with the page no longer ready:
            # _on_editor_crashed asks then. Otherwise the page hangs (spec section 7).
            if self.rich.is_ready:
                if self._ask_stopped(HUNG_DETAIL):
                    self.with_buffer(fn)
                else:
                    self._abandon_rendered()
            return
        try:
            text = serialize.to_text(doc)
        except Exception as exc:  # a serializer bug must not lose the edits
            self.rich.modified = True
            show_error(self, f"The document could not be converted to Markdown, so nothing was saved.\n{exc}")
            return
        if text != self._rendered_text:
            self._rendered_text = text
            self._block_lines = None
        fn(text)

    def _enter_source(self, text: str) -> None:
        """Rendered -> Source with `text`, the Rendered buffer (unchanged text keeps the editor's)."""
        if self.mode == self.RENDERED and self.rich.modified:
            self.with_buffer(self._enter_source)  # typed since the pull's snapshot: pull again
            return
        line = self._line_of_block(self._caret_block)
        self._show_mode(self.SOURCE)  # puts `text` (== _rendered_text) into the editor
        self.editor.setTextCursor(QTextCursor(self.editor.document().findBlockByNumber(line - 1)))
        self.editor.ensureCursorVisible()

    def _show_mode(self, mode: str, keep_scroll: bool = False) -> bool:
        """Show `mode`; Rendered first loads the buffer into the editor page. False (and Source
        shown) when the page is unavailable or the buffer cannot be parsed."""
        shown = True
        if mode == self.RENDERED:
            shown = not self.rich.failed and self._render(self.buffer, keep_scroll)
            if not shown:
                mode = self.SOURCE
        if mode == self.SOURCE and self.mode == self.RENDERED:
            self._sync_editor()  # a pull or save moved the Rendered buffer past the editor's text
        self.mode = mode
        self.stack.setCurrentIndex(0 if mode == self.RENDERED else 1)
        (self.rich if mode == self.RENDERED else self.editor).setFocus()
        self._update_chrome()
        return shown

    def _sync_editor(self) -> None:
        """Rendered -> Source: the editor takes the Rendered buffer (an unchanged text keeps the
        editor's own), with a new undo history and the dirty flag."""
        if self.editor.document().toRawText().replace("\u2029", "\n") != self._rendered_text:
            self.editor.setPlainText(self._rendered_text)
        self.editor.document().clearUndoRedoStacks()
        self.editor.document().setModified(self.dirty)

    def _render(self, text: str, keep_scroll: bool = False) -> bool:
        """Load `text` into the editor page (new undo history); False when docmodel fails."""
        try:
            doc = self._parse(text)
        except Exception:  # an unmappable construct must not block the file: Source still works
            return False
        self._doc_number += 1
        self._pending_pull = False
        self._rendered_text = text
        self._block_lines = [block["attrs"].get("line") for block in doc.get("content", [])]
        self.rich.set_document(doc, keep_scroll)
        return True

    def _parse(self, text: str) -> dict:
        front, body = frontmatter.split(text)
        return docmodel.from_markdown(body, front, self.loaded_path.parent if self.loaded_path else None)

    def _line_of_block(self, index: int) -> int:
        """First source line (1-based) of top-level block `index` of the Rendered buffer."""
        if self._block_lines is None:
            try:
                doc = self._parse(self._rendered_text)
            except Exception:
                return 1
            self._block_lines = [block["attrs"].get("line") for block in doc.get("content", [])]
        lines = [line for line in self._block_lines[: index + 1] if line is not None]
        return lines[-1] if lines else 1

    def _block_at_line(self, line: int) -> int:
        """Top-level block containing source line `line`: the one starting last at or before it."""
        best, start = 0, 0
        for index, block_line in enumerate(self._block_lines or []):
            if block_line is not None and start < block_line <= line:
                best, start = index, block_line
        return best

    def _ask_stopped(self, detail: str) -> bool:
        """Spec section 7: the editor stopped responding. True for Retry, False for Switch to Source."""
        buttons = QMessageBox.StandardButton
        box = QMessageBox(
            QMessageBox.Icon.Warning, APP_NAME, f"{STOPPED_TEXT}\n\n{detail}",
            buttons.Discard | buttons.Retry, self,
        )
        box.button(buttons.Discard).setText("Switch to Source")
        box.setDefaultButton(buttons.Retry)
        return ask(box) == buttons.Retry

    def _abandon_rendered(self) -> None:
        """Switch to Source with the text last loaded into the page or pulled from it. The page
        is restarted: its later edits are dropped, and a hung page may never answer again."""
        self.rich.restart()  # also clears rich.modified, so _enter_source does not pull
        self._enter_source(self._rendered_text)

    def _warn(self, text: str) -> None:
        """Transient status-bar warning (render fallback, missing file, read failure)."""
        self.statusBar().showMessage(text, WARNING_MS)

    # --- View --------------------------------------------------------------

    def _toggle_wrap(self, checked: bool) -> None:
        self.editor.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth if checked else QPlainTextEdit.LineWrapMode.NoWrap
        )

    def _toggle_toolbar(self, checked: bool) -> None:
        self._show_toolbar = checked
        self._update_chrome()

    def _run_format_command(self, name: str, args) -> None:
        """A toolbar button or the block combo: run it in the page, which keeps the focus."""
        self.rich.command(name, args)
        self.rich.setFocus()

    def _zoom_in(self) -> None:
        self._set_zoom(self._zoom * ZOOM_STEP)

    def _zoom_out(self) -> None:
        self._set_zoom(self._zoom / ZOOM_STEP)

    def _zoom_reset(self) -> None:
        self._set_zoom(1.0)

    def _set_zoom(self, factor: float) -> None:
        self._zoom = round(min(max(factor, ZOOM_MIN), ZOOM_MAX), 4)
        self._apply_zoom()
        self._update_chrome()

    def _apply_zoom(self, _ok: bool = True) -> None:
        self.rich.setZoomFactor(self._zoom)

    def _copy(self) -> None:
        if self.mode == self.RENDERED:
            self.rich.page().triggerAction(QWebEnginePage.WebAction.Copy)
        else:
            self.editor.copy()

    def _show_about(self) -> None:
        QMessageBox.about(
            self, f"About {APP_NAME}", f"{APP_NAME} 0.1.0\n\nA Notepad-like Markdown viewer for Windows."
        )

    # --- Chrome: title, status bar, action state ---------------------------

    def _update_chrome(self) -> None:
        source = self.mode == self.SOURCE
        (self.act_source if source else self.act_rendered).setChecked(True)
        self.act_rendered.setEnabled(not self.rich.failed)
        for act in self._source_only_actions:
            act.setEnabled(source)
        for act in self._rendered_only_actions:
            act.setEnabled(not source)
        self.toolbar.setVisible(not source and self._show_toolbar)

        pct = round(self._zoom * 100)
        if source:
            cursor = self.editor.textCursor()
            left = f"Ln {cursor.blockNumber() + 1}, Col {cursor.positionInBlock() + 1}"
        else:
            left = "Rendered" if pct == 100 else f"Rendered {pct}%"
        self._left_label.setText(left)
        label = ENCODING_LABELS.get(self.encoding, self.encoding)
        self._right_label.setText(f"{pct}% | {label} | {_fmt_size(self._size)}")

        name = self.loaded_path.name if self.loaded_path else "Untitled"
        self.setWindowTitle(f"{'*' if self.dirty else ''}{name} - {APP_NAME}")

    def _on_modification(self, modified: bool) -> None:
        if self.mode == self.SOURCE:  # Rendered mode: the editor only holds text between switches
            self.dirty = modified
            self._update_chrome()

    def _on_rendered_changed(self) -> None:
        if self.mode == self.RENDERED:
            self.dirty = True
            self._update_chrome()

    def _on_caret_block(self, index: int) -> None:
        self._caret_block = index

    def _on_editor_crashed(self) -> None:
        """The page's process died with its unpulled edits. Source mode restarts it quietly;
        Rendered mode asks, then reloads the buffer (Retry) or switches to Source (spec 7)."""
        if self.mode == self.RENDERED and not self._ask_stopped(CRASHED_DETAIL):
            self._abandon_rendered()
            return
        self.rich.restart()
        if self.mode == self.RENDERED and not self._show_mode(self.RENDERED):
            self._warn(OPEN_FAILED_NOTE)

    def _on_editor_failed(self) -> None:
        """No ready() in time: Source only for this session. Nothing was edited in the page."""
        if self.mode == self.RENDERED:
            self._show_mode(self.SOURCE)
        self._update_chrome()  # greys Rendered, also when Source was already shown (a restart after a hang)
        self._warn(EDITOR_FAILED_NOTE)

    # --- Drag and drop -----------------------------------------------------

    def _open_dropped(self, paths: list[str]) -> None:
        if paths:
            self._confirm_replace(lambda: self.open_file(paths[0]))

    def _defer_drop(self, event) -> None:
        # Defer so a save prompt does not block Explorer's drag-and-drop loop.
        paths = _local_paths(event.mimeData())
        event.acceptProposedAction()
        QTimer.singleShot(0, lambda: self._open_dropped(paths))

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        self._defer_drop(event)

    def _watch_rich_drops(self) -> None:
        """Files dropped on the editor page open; its own drags (text, images) stay in the page.
        Drops go to the view's focus proxy; a restart after a renderer crash replaces it, and
        the new one exists by ready() (before loadFinished)."""
        proxy = self.rich.focusProxy()
        if proxy is not None:
            proxy.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:
        """Open files dropped on the editors instead of inserting their path as text."""
        if event.type() in _DROP_EVENTS and event.mimeData().hasUrls():
            if obj is not self.editor.viewport() and (
                event.source() is not None or not _local_paths(event.mimeData())
            ):
                return super().eventFilter(obj, event)  # a drag inside the page, or a web link
            if event.type() == QEvent.Type.Drop:
                self._defer_drop(event)
            else:
                event.acceptProposedAction()
            return True
        return super().eventFilter(obj, event)

    # --- Window lifecycle and settings -------------------------------------

    def closeEvent(self, event) -> None:
        """Asks about unsaved changes. When Save needs a Rendered pull, this close is refused and
        close() is called again once the file is written (spec 6.4): the buffer is clean then."""
        inside = True
        allowed: list[bool] = []

        def allow() -> None:
            if inside:
                allowed.append(True)
            else:
                self.close()  # Qt ignores a close() made from inside closeEvent; this one is not

        self._confirm_replace(allow)
        inside = False
        event.setAccepted(bool(allowed))

    def _restore_geometry(self, rect: dict | None) -> None:
        if not rect:
            self.resize(*DEFAULT_SIZE)
            return
        geo = QRect(rect["x"], rect["y"], rect["width"], rect["height"])
        self.resize(geo.size())
        # Skip the position if it lies on a monitor that is no longer connected.
        if any(screen.availableGeometry().intersects(geo) for screen in QGuiApplication.screens()):
            self.move(geo.topLeft())

    def settings_snapshot(self) -> dict:
        """Same shape as settings.load(); pos()/size() pair with move()/resize()."""
        pos, size = self.pos(), self.size()
        return {
            "theme": self._theme_choice,
            "window": {"x": pos.x(), "y": pos.y(), "width": size.width(), "height": size.height()},
            "preview_zoom": self._zoom,
            "recent_files": list(self._recent),
            "editor_font": dict(self._editor_font),
            "show_toolbar": self._show_toolbar,
        }

    # --- Recent files --------------------------------------------------------

    def _remember_recent(self, path) -> None:
        self._recent = settings.add_recent(self._recent, os.path.abspath(str(path)))
        self._refresh_recent_menu()

    def _forget_recent(self, path: str) -> None:
        key = os.path.normcase(path)
        self._recent = [p for p in self._recent if os.path.normcase(p) != key]
        self._refresh_recent_menu()

    def _clear_recent(self) -> None:
        self._recent = []
        self._refresh_recent_menu()

    def _refresh_recent_menu(self) -> None:
        menu = self.menu_recent
        menu.clear()
        for number, path in enumerate(self._recent, start=1):
            name = Path(path).name.replace("&", "&&")  # a lone & would become a mnemonic
            prefix = f"&{number}" if number < 10 else f"{number // 10}&{number % 10}"
            act = menu.addAction(f"{prefix} {name}")
            act.setData(path)
            act.setToolTip(path)
            act.triggered.connect(lambda _checked=False, p=path: self._open_recent(p))
        if self._recent:
            menu.addSeparator()
        menu.addAction("&Clear Recent Files", self._clear_recent)
        menu.setEnabled(bool(self._recent))

    def _open_recent(self, path: str) -> None:
        self._confirm_replace(lambda: self._open_recent_now(path))

    def _open_recent_now(self, path: str) -> None:
        if not self.open_file(path) and not Path(path).exists():
            self._forget_recent(path)  # the file is gone; don't keep offering it

    # --- File watching -------------------------------------------------------

    def _watch(self, path: Path | None) -> None:
        self._pending_reload = False
        self._watcher = Watcher(path, os.stat) if path is not None else None
        if self._watcher is not None:
            self._watcher.poll()  # baseline: the content we just loaded

    def _note_own_write(self, path: Path) -> None:
        """Expect the disk state our save produced so the next poll stays quiet."""
        self._pending_reload = False
        self._watcher = Watcher(path, os.stat)  # fresh: no stale "missing" state
        try:
            st = os.stat(path)
        except OSError:
            return  # first poll will baseline instead
        self._watcher.note_write(st.st_mtime_ns, st.st_size)

    def _read_disk(self) -> bytes | None:
        try:
            return self.loaded_path.read_bytes()
        except OSError:
            return None

    def _poll_disk(self) -> None:
        if self._watcher is None or self._busy or QApplication.activeModalWidget() is not None:
            return  # unpolled changes are picked up on a later tick
        event = self._watcher.poll()
        if event == WatchEvent.MISSING:
            self._warn(f'"{self.loaded_path.name}" was not found on disk.')
        elif event == WatchEvent.CHANGED:
            if self.mode == self.SOURCE or self.dirty:
                self._busy = True
                try:
                    self._ask_reload()
                finally:
                    self._busy = False
            else:
                self._reload_rendered(warn=True)
        elif self._pending_reload and self.mode == self.RENDERED and not self.dirty:
            self._reload_rendered(warn=False)

    def _reload_rendered(self, warn: bool) -> None:
        """Rendered and clean: reload silently, keeping the scroll position (spec section 2)."""
        raw = self._read_disk()
        if raw is None:
            self._pending_reload = True
            if warn:
                self._warn(f'Could not read "{self.loaded_path.name}"; showing the last version.')
            return
        self._load(self.loaded_path, raw)
        if not self._show_mode(self.RENDERED, keep_scroll=True):
            self._warn(OPEN_FAILED_NOTE)

    def _ask_reload(self) -> None:
        name = self.loaded_path.name
        try:
            stamp = datetime.fromtimestamp(os.stat(self.loaded_path).st_mtime)
        except OSError:
            stamp = datetime.now()
        buttons = QMessageBox.StandardButton
        box = QMessageBox(
            QMessageBox.Icon.Warning,
            "File changed on disk",
            f'"{name}" was modified externally at {stamp:%H:%M:%S}. '
            "Reload it now? Your unsaved changes will be lost.",
            buttons.Yes | buttons.No,
            self,
        )
        box.button(buttons.Yes).setText("Reload")
        box.button(buttons.No).setText("Keep my version")
        box.setDefaultButton(buttons.Yes)
        if ask(box) != buttons.Yes:
            if self.mode == self.SOURCE:
                self.editor.document().setModified(True)  # buffer now differs from disk
            else:
                self.dirty = True
                self._update_chrome()
            return
        raw = self._read_disk()
        if raw is None:
            self._warn(f'Could not read "{name}"; your version is kept.')
            return
        if self.mode == self.RENDERED:
            self._load(self.loaded_path, raw)
            if not self._show_mode(self.RENDERED, keep_scroll=True):
                self._warn(OPEN_FAILED_NOTE)
            return
        position = self.editor.textCursor().position()
        self._load(self.loaded_path, raw)
        cursor = self.editor.textCursor()
        cursor.setPosition(min(position, len(self.buffer)))
        self.editor.setTextCursor(cursor)
        self._update_chrome()

    # --- Preferences -----------------------------------------------------------

    def on_preferences(self) -> None:
        dialog = PreferencesDialog(
            self._theme_choice, self._editor_font["family"], self._editor_font["size"], self
        )
        if not run_preferences(dialog):
            return
        if dialog.theme_choice() != self._theme_choice:
            self._set_theme_choice(dialog.theme_choice())
        font = {"family": dialog.font_family(), "size": dialog.font_size()}
        if font != self._editor_font:
            self._editor_font = font
            self._apply_editor_font()

    def _apply_editor_font(self) -> None:
        font = QFont(self._editor_font["family"], self._editor_font["size"])
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.editor.setFont(font)

    # --- Theme -----------------------------------------------------------------

    def _set_theme_choice(self, choice: str) -> None:
        self._theme_choice = choice
        if choice == "system":
            self._theme_timer.start()
        else:
            self._theme_timer.stop()  # forced Light/Dark/Gray ignore the system theme
        self._apply_theme(force=True)

    def _poll_theme(self) -> None:
        if self._theme_choice == "system":
            self._apply_theme()

    def _apply_theme(self, force: bool = False) -> None:
        theme = read_system_theme() if self._theme_choice == "system" else self._theme_choice
        if theme == self._effective_theme and not force:
            return
        self._effective_theme = theme
        if theme in CUSTOM_PALETTES:
            # windowsvista paints native light controls whatever the palette says.
            QApplication.setStyle("Fusion")
            QApplication.setPalette(_custom_palette(theme))
        else:
            QApplication.setStyle("windowsvista")
            QApplication.setPalette(QApplication.style().standardPalette())
        _set_dark_title_bar(self, theme in CUSTOM_PALETTES)
        self.editor.set_theme(theme)
        self.rich.set_theme(theme)  # no reload: same document, undo history and scroll
