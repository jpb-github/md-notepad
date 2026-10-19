"""Main window: menus, mode switching, file operations, status bar."""

import html
from pathlib import Path

from PySide6.QtCore import QEvent, QRect, QTimer
from PySide6.QtGui import QActionGroup, QFont, QGuiApplication, QKeySequence
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QStackedWidget,
)

from mdviewer.core import encoding

APP_NAME = "MD Viewer"
ZOOM_MIN = 0.25
ZOOM_MAX = 3.0
ZOOM_STEP = 1.25
DEFAULT_SIZE = (900, 700)
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
    PREVIEW = "preview"
    EDIT = "edit"

    def __init__(self, data: dict):
        super().__init__()
        self.mode = self.PREVIEW
        self.dirty = False
        self.loaded_path: Path | None = None
        self.encoding = "utf-8"
        self.newline = "\n"
        self._size = 0
        self._zoom = float(data.get("preview_zoom") or 1.0)
        self._theme_choice = data.get("theme") or "system"

        self.editor = QPlainTextEdit()
        font = QFont("Consolas", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.editor.setFont(font)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)

        self.preview = QWebEngineView()
        # Dropped files must reach MainWindow, not navigate the page.
        self.preview.setAcceptDrops(False)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.preview)  # index 0
        self.stack.addWidget(self.editor)  # index 1
        self.setCentralWidget(self.stack)

        self._left_label = QLabel()
        self._right_label = QLabel()
        self.statusBar().addWidget(self._left_label)
        self.statusBar().addPermanentWidget(self._right_label)

        self._build_menus()

        self.editor.modificationChanged.connect(self._on_modification)
        self.editor.cursorPositionChanged.connect(self._update_chrome)
        self.editor.viewport().installEventFilter(self)
        # setHtml can reset the page zoom; re-apply ours after every load.
        self.preview.loadFinished.connect(self._apply_zoom)
        self._apply_zoom()

        self.setAcceptDrops(True)
        self._restore_geometry(data.get("window"))
        self._update_chrome()

    # --- Buffer ------------------------------------------------------------

    @property
    def buffer(self) -> str:
        """Editor text with \\n breaks. toPlainText() would turn NBSP into spaces."""
        return self.editor.document().toRawText().replace("\u2029", "\n")

    def _load(self, path: Path | None, raw: bytes) -> None:
        """Decode raw file bytes into the buffer; remember encoding and newline style."""
        text, self.encoding = encoding.detect(raw)
        self.newline = "\r\n" if "\r\n" in text else "\n"
        self.loaded_path = path
        self._size = len(raw)
        self.editor.setPlainText(text.replace("\r\n", "\n"))
        self.editor.document().setModified(False)
        self.dirty = False

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
        # Find/Replace stay disabled and unconnected until Task 12 wires them.
        self.act_find = self._action(m, "&Find...", "Ctrl+F")
        self.act_replace = self._action(m, "&Replace...", "Ctrl+H")
        self.act_find.setEnabled(False)
        self.act_replace.setEnabled(False)
        self.act_select_all = self._action(m, "Select &All", "Ctrl+A", self.editor.selectAll)

        m = self.menu_view = bar.addMenu("&View")
        modes = QActionGroup(self)
        self.act_preview = self._action(
            m, "&Preview Mode", "Ctrl+P", lambda: self.set_mode(self.PREVIEW), checkable=True
        )
        self.act_edit = self._action(
            m, "&Edit Mode", "Ctrl+E", lambda: self.set_mode(self.EDIT), checkable=True
        )
        modes.addAction(self.act_preview)
        modes.addAction(self.act_edit)
        m.addSeparator()
        self.act_wrap = self._action(m, "&Word Wrap", checkable=True)
        self.act_wrap.setChecked(True)
        self.act_wrap.toggled.connect(self._toggle_wrap)
        m.addSeparator()
        self.act_zoom_in = self._action(m, "Zoom &In", "Ctrl+=", self._zoom_in)
        self.act_zoom_out = self._action(m, "Zoom &Out", "Ctrl+-", self._zoom_out)
        self.act_zoom_reset = self._action(m, "&Restore Default Zoom", "Ctrl+0", self._zoom_reset)

        m = self.menu_help = bar.addMenu("&Help")
        self._action(m, "&About MD Viewer", slot=self._show_about)

        self._edit_only_actions = [
            self.act_undo, self.act_redo, self.act_cut, self.act_paste, self.act_select_all,
        ]
        self._preview_only_actions = [self.act_zoom_in, self.act_zoom_out, self.act_zoom_reset]

    # --- File operations ---------------------------------------------------

    def open_file(self, path) -> bool:
        target = Path(path)
        try:
            raw = target.read_bytes()
        except OSError as exc:
            show_error(self, _open_error_text(target, exc))
            return False
        self._load(target, raw)
        self._show_mode(self.PREVIEW)
        return True

    def on_new(self) -> None:
        if not self._ok_to_replace():
            return
        self._load(None, b"")
        self._show_mode(self.EDIT)  # a preview of an empty file is meaningless

    def on_open(self) -> None:
        if not self._ok_to_replace():
            return
        path = pick_open_path(self)
        if path:
            self.open_file(path)

    def on_save(self) -> bool:
        if self.loaded_path is None:
            return self.on_save_as()
        return self._save_to(self.loaded_path)

    def on_save_as(self) -> bool:
        start = str(self.loaded_path) if self.loaded_path else "Untitled.md"
        path = pick_save_path(self, start)
        if not path:
            return False
        target = Path(path)
        if not target.suffix:
            target = target.with_suffix(".md")
        return self._save_to(target)

    def on_close(self) -> None:
        if not self._ok_to_replace():
            return
        self._load(None, b"")
        self._show_mode(self.PREVIEW)

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
        self.dirty = False
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

    def _prompt_save(self) -> str:
        """Ask 'Save changes to <name>?'. Returns 'save' (saved OK), 'discard' or 'cancel'."""
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
            return "save" if self.on_save() else "cancel"
        if answer == buttons.Discard:
            return "discard"
        return "cancel"

    def _ok_to_replace(self) -> bool:
        """True when the buffer may be replaced: it is clean, was saved, or was discarded."""
        return not self.dirty or self._prompt_save() != "cancel"

    def _reload_or_clear(self) -> None:
        """Don't Save: put the disk content back (empty for Untitled or unreadable files)."""
        if self.loaded_path is not None:
            try:
                raw = self.loaded_path.read_bytes()
            except OSError:
                raw = None
            if raw is not None:
                self._load(self.loaded_path, raw)
                return
        self.editor.setPlainText("")
        self.editor.document().setModified(False)
        self.dirty = False

    # --- Modes -------------------------------------------------------------

    def set_mode(self, mode: str) -> None:
        if mode == self.mode:
            self._update_chrome()
            return
        if mode == self.PREVIEW and self.dirty:
            answer = self._prompt_save()
            if answer == "cancel":
                self._update_chrome()  # the action group already moved the radio check
                return
            if answer == "discard":
                self._reload_or_clear()
        self._show_mode(mode)

    def _show_mode(self, mode: str) -> None:
        self.mode = mode
        self.stack.setCurrentIndex(0 if mode == self.PREVIEW else 1)
        if mode == self.PREVIEW:
            self._render_preview()
        else:
            self.editor.setFocus()
        self._update_chrome()

    def _render_preview(self) -> None:
        """Placeholder until Task 9: the escaped buffer in a <pre>."""
        self.preview.setHtml(
            "<!DOCTYPE html><html><head><meta charset='utf-8'></head><body>"
            "<pre style='white-space:pre-wrap;font:14px Consolas,monospace'>"
            f"{html.escape(self.buffer)}</pre></body></html>"
        )

    # --- View --------------------------------------------------------------

    def _toggle_wrap(self, checked: bool) -> None:
        self.editor.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth if checked else QPlainTextEdit.LineWrapMode.NoWrap
        )

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
        self.preview.setZoomFactor(self._zoom)

    def _copy(self) -> None:
        if self.mode == self.PREVIEW:
            self.preview.page().triggerAction(QWebEnginePage.WebAction.Copy)
        else:
            self.editor.copy()

    def _show_about(self) -> None:
        QMessageBox.about(
            self, f"About {APP_NAME}", f"{APP_NAME} 0.1.0\n\nA Notepad-like Markdown viewer for Windows."
        )

    # --- Chrome: title, status bar, action state ---------------------------

    def _update_chrome(self) -> None:
        editing = self.mode == self.EDIT
        (self.act_edit if editing else self.act_preview).setChecked(True)
        for act in self._edit_only_actions:
            act.setEnabled(editing)
        for act in self._preview_only_actions:
            act.setEnabled(not editing)

        pct = round(self._zoom * 100)
        if editing:
            cursor = self.editor.textCursor()
            left = f"Ln {cursor.blockNumber() + 1}, Col {cursor.positionInBlock() + 1}"
        else:
            left = "Preview" if pct == 100 else f"Preview {pct}%"
        self._left_label.setText(left)
        label = ENCODING_LABELS.get(self.encoding, self.encoding)
        self._right_label.setText(f"{pct}% | {label} | {_fmt_size(self._size)}")

        name = self.loaded_path.name if self.loaded_path else "Untitled"
        self.setWindowTitle(f"{'*' if self.dirty else ''}{name} - {APP_NAME}")

    def _on_modification(self, modified: bool) -> None:
        self.dirty = modified
        self._update_chrome()

    # --- Drag and drop -----------------------------------------------------

    def _open_dropped(self, paths: list[str]) -> None:
        if paths and self._ok_to_replace():
            self.open_file(paths[0])

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

    def eventFilter(self, obj, event) -> bool:
        """Open files dropped on the editor instead of inserting their path as text."""
        if event.type() in _DROP_EVENTS and event.mimeData().hasUrls():
            if event.type() == QEvent.Type.Drop:
                self._defer_drop(event)
            else:
                event.acceptProposedAction()
            return True
        return super().eventFilter(obj, event)

    # --- Window lifecycle and settings -------------------------------------

    def closeEvent(self, event) -> None:
        if self._ok_to_replace():
            event.accept()
        else:
            event.ignore()

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
        }
