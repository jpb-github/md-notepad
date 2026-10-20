"""Preferences dialog: app theme and editor font (fixed-pitch fonts only)."""

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFontComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)

from mdviewer.core import settings

THEME_LABELS = (("system", "&System (auto)"), ("light", "&Light"), ("dark", "&Dark"), ("gray", "&Gray"))
SAMPLE_TEXT = "AaBbCc 0123456789 {}[]()<> # * `"


class PreferencesDialog(QDialog):
    """Edits a copy of the preferences; MainWindow applies them only on OK."""

    def __init__(self, theme: str, font_family: str, font_size: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")

        theme_box = QGroupBox("Theme")
        theme_layout = QVBoxLayout(theme_box)
        self.theme_buttons: dict[str, QRadioButton] = {}
        for choice, label in THEME_LABELS:
            button = QRadioButton(label)
            theme_layout.addWidget(button)
            self.theme_buttons[choice] = button
        self.set_theme_choice(theme)

        font_group = QGroupBox("Editor font")
        font_layout = QFormLayout(font_group)
        self.font_box = QFontComboBox()
        self.font_box.setFontFilters(QFontComboBox.FontFilter.MonospacedFonts)
        self.font_box.setEditable(False)  # only the listed (fixed-pitch) fonts can be chosen
        self.font_box.setCurrentFont(QFont(font_family))
        self.size_box = QSpinBox()
        self.size_box.setRange(settings.FONT_SIZE_MIN, settings.FONT_SIZE_MAX)
        self.size_box.setSuffix(" pt")
        self.size_box.setValue(font_size)
        self.sample = QLabel(SAMPLE_TEXT)
        self.sample.setMinimumHeight(48)
        font_layout.addRow("&Font:", self.font_box)
        font_layout.addRow("&Size:", self.size_box)
        font_layout.addRow("Sample:", self.sample)
        self.font_box.currentFontChanged.connect(self._update_sample)
        self.size_box.valueChanged.connect(self._update_sample)
        self._update_sample()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(theme_box)
        row.addWidget(font_group, 1)
        layout.addLayout(row)
        layout.addWidget(buttons)

    def theme_choice(self) -> str:
        return next(choice for choice, button in self.theme_buttons.items() if button.isChecked())

    def set_theme_choice(self, choice: str) -> None:
        self.theme_buttons.get(choice, self.theme_buttons["system"]).setChecked(True)

    def font_family(self) -> str:
        return self.font_box.currentFont().family()

    def font_size(self) -> int:
        return self.size_box.value()

    def _update_sample(self, *_args) -> None:
        self.sample.setFont(QFont(self.font_family(), self.font_size()))
