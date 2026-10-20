"""Link and image dialogs of the Rendered editor (spec section 3).

main_window's seams run_link_dialog / run_image_dialog show them; the Browse... file dialog goes
through pick_image_path, which the smoke fakes."""

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
)

from mdviewer.core import urls

IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.gif *.svg *.webp *.bmp);;All files (*)"
_MIN_WIDTH = 420


def pick_image_path(parent, start: str) -> str:
    """Ask for an image file, starting in `start`; "" when cancelled."""
    path, _filter = QFileDialog.getOpenFileName(parent, "Choose Image", start, IMAGE_FILTER)
    return path


def _ok_cancel_box(dialog: QDialog) -> QDialogButtonBox:
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)
    return box


class LinkDialog(QDialog):
    """Insert Link, or Edit Link when it gets a URL (which also offers Remove link)."""

    REMOVE = 2  # the result of Remove link (Rejected is 0, Accepted 1)

    def __init__(self, text: str, url: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Link" if url else "Insert Link")
        self.setMinimumWidth(_MIN_WIDTH)
        self.text_edit = QLineEdit(text)
        self.url_edit = QLineEdit(url)
        form = QFormLayout(self)
        form.addRow("&Text:", self.text_edit)
        form.addRow("&URL:", self.url_edit)
        box = _ok_cancel_box(self)
        self.ok_button = box.button(QDialogButtonBox.StandardButton.Ok)
        self.remove_button: QPushButton | None = None
        if url:
            self.remove_button = box.addButton("&Remove link", QDialogButtonBox.ButtonRole.ActionRole)
            self.remove_button.clicked.connect(lambda: self.done(self.REMOVE))
        form.addRow(box)
        self.url_edit.textChanged.connect(self._update_ok)
        self._update_ok()
        self.url_edit.setFocus()
        self.url_edit.selectAll()

    def _update_ok(self) -> None:
        url = self.url_edit.text().strip()
        self.ok_button.setEnabled(bool(url) and urls.is_safe(url))

    def values(self) -> tuple[str, str]:
        """(text as typed, trimmed URL); an empty text keeps the link's current text."""
        return self.text_edit.text(), self.url_edit.text().strip()


class ImageDialog(QDialog):
    """Insert Image: a path or URL (with Browse...) and its alt text."""

    def __init__(self, base_dir: Path | None, parent=None):
        super().__init__(parent)
        self.base_dir = base_dir
        self.setWindowTitle("Insert Image")
        self.setMinimumWidth(_MIN_WIDTH)
        self.path_edit = QLineEdit()
        self.browse_button = QPushButton("&Browse...")
        self.browse_button.setAutoDefault(False)
        self.browse_button.clicked.connect(self._browse)
        path_row = QHBoxLayout()
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(self.browse_button)
        self.alt_edit = QLineEdit()
        form = QFormLayout(self)
        form.addRow("&Path or URL:", path_row)
        form.addRow("&Alt text:", self.alt_edit)
        box = _ok_cancel_box(self)
        self.ok_button = box.button(QDialogButtonBox.StandardButton.Ok)
        form.addRow(box)
        self.path_edit.textChanged.connect(self._update_ok)
        self._update_ok()
        self.path_edit.setFocus()

    def _browse(self) -> None:
        picked = pick_image_path(self, str(self.base_dir) if self.base_dir else "")
        if picked:
            self.path_edit.setText(str(Path(picked)))  # native separators

    def _src(self) -> str:
        return urls.image_src(self.path_edit.text(), self.base_dir)

    def _update_ok(self) -> None:
        src = self._src()
        self.ok_button.setEnabled(bool(src) and urls.is_safe(src))

    def values(self) -> tuple[str, str]:
        """(the Markdown src, the alt text)."""
        return self._src(), self.alt_edit.text()
