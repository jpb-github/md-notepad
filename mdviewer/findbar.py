"""Find/Replace bar under the editors, in two modes.

Source: plain-text Find/Replace via QTextDocument.find. QTextDocument positions count
UTF-16 units, so all matching stays in Qt; Python string offsets would drift after any
emoji.

Rendered (web mode): find only, in the page via QWebEnginePage.findText; its
findTextFinished reports the match count.
"""

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

RECOUNT_MS = 200


class FindBar(QWidget):
    def __init__(self, editor, view=None, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.view = view  # the RichView searched in web mode
        self.web_mode = False

        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText("Find")
        self.case_box = QCheckBox("Match case")
        self.count_label = QLabel()
        self.count_label.setMinimumWidth(90)
        self.prev_button = QPushButton("Previous")
        self.next_button = QPushButton("Next")
        close_button = QToolButton()
        close_button.setText("✕")
        close_button.setAutoRaise(True)
        close_button.setToolTip("Close (Esc)")
        self.replace_edit = QLineEdit()
        self.replace_edit.setPlaceholderText("Replace with")
        self.replace_button = QPushButton("Replace")
        self.replace_all_button = QPushButton("Replace All")

        find_row = QHBoxLayout()
        find_row.addWidget(QLabel("Find:"))
        find_row.addWidget(self.find_edit, 1)
        for widget in (self.case_box, self.count_label, self.prev_button, self.next_button, close_button):
            find_row.addWidget(widget)
        self.replace_row = QWidget()
        replace_layout = QHBoxLayout(self.replace_row)
        replace_layout.setContentsMargins(0, 0, 0, 0)
        replace_layout.addWidget(QLabel("Replace:"))
        replace_layout.addWidget(self.replace_edit, 1)
        replace_layout.addWidget(self.replace_button)
        replace_layout.addWidget(self.replace_all_button)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 4, 6, 4)
        outer.addLayout(find_row)
        outer.addWidget(self.replace_row)

        self._recount = QTimer(self)
        self._recount.setSingleShot(True)
        self._recount.setInterval(RECOUNT_MS)
        self._recount.timeout.connect(self._update_count)

        self.find_edit.textChanged.connect(self._search_as_typed)
        self.case_box.toggled.connect(self._search_as_typed)
        self.find_edit.returnPressed.connect(self.find_next)
        self.replace_edit.returnPressed.connect(self.replace_one)
        self.prev_button.clicked.connect(self.find_previous)
        self.next_button.clicked.connect(self.find_next)
        self.replace_button.clicked.connect(self.replace_one)
        self.replace_all_button.clicked.connect(self.replace_all)
        close_button.clicked.connect(self.close_bar)
        self.editor.document().contentsChanged.connect(self._on_text_edited)
        if view is not None:
            view.page().findTextFinished.connect(self._on_page_result)
        for edit in (self.find_edit, self.replace_edit):
            edit.installEventFilter(self)

    # --- open / close ----------------------------------------------------------

    def open_find(self) -> None:
        self._open(replace=False)

    def open_replace(self) -> None:
        self._open(replace=True)

    def set_web_mode(self, on: bool) -> None:
        """Rendered mode (True) searches the page and has no Replace row; a change closes the bar."""
        if on == self.web_mode:
            return
        if self.isVisible():
            self._hide()
        self.web_mode = on

    def _open(self, replace: bool) -> None:
        was_open = self.isVisible()
        before = self.find_edit.text()
        selected = self.view.selectedText() if self.web_mode else self.editor.textCursor().selectedText()
        if selected and "\u2029" not in selected and "\n" not in selected:  # single-line selections only
            self.find_edit.blockSignals(True)  # it is already selected in the editor
            self.find_edit.setText(selected)
            self.find_edit.blockSignals(False)
        self.replace_row.setVisible(replace)
        self.show()
        self.find_edit.setFocus()
        self.find_edit.selectAll()
        if self.web_mode:
            self.view.set_finding(True)
            if not was_open or self.find_edit.text() != before:  # Ctrl+F on the open bar keeps the match
                self._find(backward=False)
        else:
            self._update_count()

    def close_bar(self) -> None:
        self._hide()
        (self.view if self.web_mode else self.editor).setFocus()

    def _hide(self) -> None:
        if self.web_mode:
            self.view.page().findText("")  # clears the highlights; the active match stays selected
            self.view.set_finding(False)
        self.hide()

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self.close_bar()
                return True
            if (obj is self.find_edit and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                    and event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                self.find_previous()
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:  # focus on a button or the checkbox
            self.close_bar()
        else:
            super().keyPressEvent(event)

    # --- searching -------------------------------------------------------------

    def find_next(self) -> bool:
        return self._find(backward=False)

    def find_previous(self) -> bool:
        return self._find(backward=True)

    def _flags(self, backward: bool = False):
        flags = QTextDocument.FindFlag(0)
        if self.case_box.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if backward:
            flags |= QTextDocument.FindFlag.FindBackward
        return flags

    def _find(self, backward: bool) -> bool:
        """Source: moves the editor's selection. Web mode: asks the page, True at once; the count
        arrives in _on_page_result."""
        needle = self.find_edit.text()
        if not needle:
            self.count_label.setText("")
            if self.web_mode:
                self.view.page().findText("")
            return False
        if self.web_mode:
            flags = QWebEnginePage.FindFlag(0)
            if self.case_box.isChecked():
                flags |= QWebEnginePage.FindFlag.FindCaseSensitively
            if backward:
                flags |= QWebEnginePage.FindFlag.FindBackward
            self.view.page().findText(needle, flags)
            return True
        doc = self.editor.document()
        flags = self._flags(backward)
        found = doc.find(needle, self.editor.textCursor(), flags)
        if found.isNull():  # wrap around
            start = QTextCursor(doc)
            if backward:
                start.movePosition(QTextCursor.MoveOperation.End)
            found = doc.find(needle, start, flags)
        if not found.isNull():
            self.editor.setTextCursor(found)
        self._update_count()
        return not found.isNull()

    def _search_as_typed(self, *_args) -> None:
        """Re-search from the start of the current selection so typing extends the match."""
        if self.web_mode:  # a new text or case flag starts a new search in the page
            self._find(backward=False)
            return
        cursor = self.editor.textCursor()
        cursor.setPosition(cursor.selectionStart())
        self.editor.setTextCursor(cursor)
        self._find(backward=False)

    def _matches(self) -> list[tuple[int, int]]:
        needle = self.find_edit.text()
        doc = self.editor.document()
        flags = self._flags()
        spans = []
        found = QTextCursor(doc)
        while needle:
            found = doc.find(needle, found, flags)
            if found.isNull():
                break
            spans.append((found.selectionStart(), found.selectionEnd()))
        return spans

    def _update_count(self) -> None:
        if not self.find_edit.text():
            self.count_label.setText("")
            return
        spans = self._matches()
        cursor = self.editor.textCursor()
        current = (cursor.selectionStart(), cursor.selectionEnd())
        if not spans:
            text = "No results"
        elif current in spans:
            text = f"{spans.index(current) + 1} of {len(spans)}"
        else:
            text = "1 match" if len(spans) == 1 else f"{len(spans)} matches"
        self.count_label.setText(text)

    def _on_text_edited(self) -> None:
        if self.isVisible() and not self.web_mode:
            self._recount.start()

    def _on_page_result(self, result) -> None:
        # findText("") answers too; only a search the field asks for counts
        if not (self.web_mode and self.isVisible() and self.find_edit.text()):
            return
        count = result.numberOfMatches()
        self.count_label.setText(f"{result.activeMatch()} of {count}" if count else "No results")

    # --- replacing -------------------------------------------------------------

    def replace_one(self) -> None:
        cursor = self.editor.textCursor()
        if cursor.hasSelection() and (cursor.selectionStart(), cursor.selectionEnd()) in self._matches():
            cursor.insertText(self.replace_edit.text())
            self.editor.setTextCursor(cursor)
        self._find(backward=False)

    def replace_all(self) -> int:
        needle = self.find_edit.text()
        if not needle:
            return 0
        doc = self.editor.document()
        flags = self._flags()
        replacement = self.replace_edit.text()
        count = 0
        found = QTextCursor(doc)
        block = QTextCursor(doc)
        block.beginEditBlock()  # the whole Replace All is one undo step
        try:
            while True:
                found = doc.find(needle, found, flags)
                if found.isNull():
                    break
                found.insertText(replacement)  # search resumes after the inserted text
                count += 1
        finally:
            block.endEditBlock()
        self._recount.stop()  # keep the "replaced" message instead of a recount
        self.count_label.setText(f"{count} replaced" if count else "No results")
        return count
