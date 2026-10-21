"""Editor page: QPlainTextEdit with Markdown highlighting, underlines, and completion."""

import re

from PySide6.QtCore import QEvent, QStringListModel, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QCompleter, QPlainTextEdit, QToolTip

from mdviewer.core import mdcheck
from mdviewer.core.completion import (
    AUTOCLOSE_PAIRS,
    apply_suggestion,
    autoclose_action,
    deletes_pair,
    should_continue_on_enter,
    suggestions_for,
    token_prefix,
)

TRIGGER_CHARS = "#|`>-*_["
REFRESH_MS = 250

COLORS = {
    "light": {
        "heading": "#0550ae", "code": "#953800", "link": "#0969da", "marker": "#cf222e",
        "quote": "#59636e", "table": "#8250df", "fence": "#116329", "comment": "#6e7781",
        "error": "#d1242f", "warning": "#e36209",
    },
    "dark": {
        "heading": "#79c0ff", "code": "#ffa657", "link": "#58a6ff", "marker": "#ff7b72",
        "quote": "#9198a1", "table": "#d2a8ff", "fence": "#7ee787", "comment": "#8b949e",
        "error": "#f85149", "warning": "#f0883e",
    },
    "darkgray": {
        "heading": "#79c0ff", "code": "#ffa657", "link": "#6cb2ff", "marker": "#ff8f87",
        "quote": "#a6adb5", "table": "#d2a8ff", "fence": "#7ee787", "comment": "#9aa1a9",
        "error": "#ff6b63", "warning": "#f0883e",
    },
}
COLORS["lightgray"] = COLORS["light"]  # the light colors read fine on the light gray base

# Block states: 0 normal, 1 inside an HTML comment, >= 1000 inside a fence
# (1000 + length for backtick fences, 2000 + length for tilde fences).
NORMAL, COMMENT, FENCE_BACKTICK, FENCE_TILDE = 0, 1, 1000, 2000

_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_HEADING_RE = re.compile(r"^ {0,3}#{1,6}(?:\s|$)")
_QUOTE_RE = re.compile(r"^\s*>")
_LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])(?=\s|$)")
_BOLD_RE = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
_ITALIC_RE = re.compile(r"(?<![*_\w])([*_])(?=[^\s*_])(.+?)(?<=[^\s*_])\1(?![*_\w])")
_LINK_RE = re.compile(r"!?\[[^\]\n]*\]\([^)\n]*\)|<https?://[^>\s]+>|https?://\S+")
_CODE_RE = re.compile(r"(`+)(.+?)\1")
_COMMENT_RE = re.compile(r"<!--.*?-->")
_FENCE_LINE_RE = re.compile(r"^\s*```")
_POPUP_KEYS = (
    Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape, Qt.Key.Key_Tab, Qt.Key.Key_Backtab,
)
_COMMAND_MODS = (
    Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.MetaModifier
)


def _fence_state(text: str) -> int | None:
    """Block state for a line that opens a fence, else None (mirrors mdcheck)."""
    m = _FENCE_RE.match(text)
    if m is None:
        return None
    marker, rest = m.group(1), m.group(2)
    if marker[0] == "`":
        return None if "`" in rest else FENCE_BACKTICK + min(len(marker), 999)
    return FENCE_TILDE + min(len(marker), 999)


def _closes_fence(text: str, state: int) -> bool:
    m = _FENCE_RE.match(text)
    if m is None or m.group(2).strip():
        return False
    char = "`" if state < FENCE_TILDE else "~"
    return m.group(1)[0] == char and len(m.group(1)) >= state % 1000


def _is_table_separator(text: str) -> bool:
    s = text.strip()
    return "|" in s and "-" in s and set(s) <= set("|-: \t")


def _char_format(color=None, bold=False, italic=False, underline=False) -> QTextCharFormat:
    fmt = QTextCharFormat()
    if color:
        fmt.setForeground(QColor(color))
    if bold:
        fmt.setFontWeight(QFont.Weight.Bold)
    if italic:
        fmt.setFontItalic(True)
    if underline:
        fmt.setFontUnderline(True)
    return fmt


class MarkdownHighlighter(QSyntaxHighlighter):
    """Structural colors per block, plus mdcheck wavy underlines refreshed after edits."""

    def __init__(self, document):
        super().__init__(document)
        self._issues: dict[int, list[mdcheck.Issue]] = {}
        self._refreshing = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(REFRESH_MS)
        self._timer.timeout.connect(self.refresh_issues)
        document.contentsChange.connect(self._schedule_refresh)
        self._build_formats("light")

    # --- public API --------------------------------------------------------

    def set_theme(self, theme: str) -> None:
        self._build_formats(theme)
        self._refreshing = True
        try:
            self.rehighlight()
        finally:
            self._refreshing = False

    def refresh_issues(self) -> None:
        """Re-run mdcheck; re-highlight only the lines whose issues changed."""
        issues: dict[int, list[mdcheck.Issue]] = {}
        for issue in mdcheck.check(self.document().toPlainText()):
            issues.setdefault(issue.line, []).append(issue)
        changed = [
            line for line in set(issues) | set(self._issues)
            if issues.get(line) != self._issues.get(line)
        ]
        self._issues = issues
        self._refreshing = True
        try:
            for line in changed:
                block = self.document().findBlockByNumber(line - 1)
                if block.isValid():
                    self.rehighlightBlock(block)
        finally:
            self._refreshing = False

    def starts_in_fence(self, block) -> bool:
        """True when the block is fenced-code content (or the closing fence)."""
        previous = block.previous()
        return previous.isValid() and previous.userState() >= FENCE_BACKTICK

    def message_at(self, line: int, col: int) -> str:
        return "\n".join(
            issue.message for issue in self._issues.get(line, [])
            if issue.start <= col < max(issue.end, issue.start + 1)
        )

    # --- QSyntaxHighlighter --------------------------------------------------

    def highlightBlock(self, text: str) -> None:
        state = max(self.previousBlockState(), NORMAL)
        if state >= FENCE_BACKTICK:
            self.setFormat(0, len(text), self._formats["fence"])
            if _closes_fence(text, state):
                state = NORMAL
        else:
            state = self._highlight_markdown(text, state)
        self.setCurrentBlockState(state)
        self._apply_issues(text)

    # --- internals -----------------------------------------------------------

    def _schedule_refresh(self, *_args) -> None:
        if not self._refreshing:  # our own re-highlighting also emits contentsChange
            self._timer.start()

    def _build_formats(self, theme: str) -> None:
        c = COLORS[theme]
        self._formats = {
            "heading": _char_format(c["heading"], bold=True),
            "bold": _char_format(bold=True),
            "italic": _char_format(italic=True),
            "code": _char_format(c["code"]),
            "link": _char_format(c["link"], underline=True),
            "marker": _char_format(c["marker"], bold=True),
            "quote": _char_format(c["quote"], italic=True),
            "table": _char_format(c["table"]),
            "fence": _char_format(c["fence"]),
            "comment": _char_format(c["comment"], italic=True),
        }
        self._underlines = {}
        for severity in ("error", "warning"):
            fmt = QTextCharFormat()
            fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
            fmt.setUnderlineColor(QColor(c[severity]))
            self._underlines[severity] = fmt

    def _merge(self, start: int, length: int, fmt: QTextCharFormat) -> None:
        for pos in range(start, start + length):
            merged = self.format(pos)
            merged.merge(fmt)
            self.setFormat(pos, 1, merged)

    def _highlight_markdown(self, text: str, state: int) -> int:
        f = self._formats
        start = 0
        if state == COMMENT:
            end = text.find("-->")
            if end < 0:
                self.setFormat(0, len(text), f["comment"])
                return COMMENT
            start = end + 3
        else:
            fence = _fence_state(text)
            if fence is not None:
                self.setFormat(0, len(text), f["fence"])
                return fence
            self._line_rules(text)
        for m in _BOLD_RE.finditer(text, start):
            self._merge(m.start(), m.end() - m.start(), f["bold"])
        for m in _ITALIC_RE.finditer(text, start):
            self._merge(m.start(), m.end() - m.start(), f["italic"])
        for regex, key in ((_LINK_RE, "link"), (_CODE_RE, "code"), (_COMMENT_RE, "comment")):
            for m in regex.finditer(text, start):
                self.setFormat(m.start(), m.end() - m.start(), f[key])
        if start:
            self.setFormat(0, start, f["comment"])
        opening = text.rfind("<!--")
        if opening >= start and text.find("-->", opening + 4) < 0:
            self.setFormat(opening, len(text) - opening, f["comment"])
            return COMMENT
        return NORMAL

    def _line_rules(self, text: str) -> None:
        f = self._formats
        if _HEADING_RE.match(text):
            self.setFormat(0, len(text), f["heading"])
        elif _QUOTE_RE.match(text):
            self.setFormat(0, len(text), f["quote"])
        elif _is_table_separator(text):
            self.setFormat(0, len(text), f["table"])
        marker = _LIST_RE.match(text)
        if marker is not None:
            self.setFormat(marker.start(2), len(marker.group(2)), f["marker"])

    def _apply_issues(self, text: str) -> None:
        line = self.currentBlock().blockNumber() + 1
        # Warnings first so an error on the same characters wins.
        for issue in sorted(self._issues.get(line, []), key=lambda i: i.severity == "error"):
            start, end = min(issue.start, len(text)), min(issue.end, len(text))
            self._merge(start, end - start, self._underlines[issue.severity])


class MarkdownEditor(QPlainTextEdit):
    """Notepad-style editor plus auto-close pairs, Enter continuation, and a completer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlighter = MarkdownHighlighter(self.document())
        self._model = QStringListModel(self)
        self.completer = QCompleter(self._model, self)
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.activated[str].connect(self._insert_completion)
        self._suggestions = {}

    def set_theme(self, theme: str) -> None:
        self.highlighter.set_theme(theme)

    # --- keys ----------------------------------------------------------------

    def keyPressEvent(self, event) -> None:
        key, mods = event.key(), event.modifiers()
        if self.completer.popup().isVisible() and key in _POPUP_KEYS:
            event.ignore()  # the completer accepts or dismisses
            return
        if key == Qt.Key.Key_Space and mods == Qt.KeyboardModifier.ControlModifier:
            self._show_completions()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (mods & _COMMAND_MODS):
            if not self._continue_on_enter():
                cursor = self.textCursor()
                cursor.insertText("\n")  # never Shift+Enter's U+2028 soft break
                self.setTextCursor(cursor)
            self.ensureCursorVisible()
            return
        if key == Qt.Key.Key_Backspace and not mods and self._delete_pair():
            self._after_typing("\b")
            return
        typed = event.text()
        # No modifier test here: AltGr ([ on many layouts) reports Ctrl+Alt.
        if not (len(typed) == 1 and typed.isprintable() and self._auto_close(typed)):
            super().keyPressEvent(event)
        self._after_typing(typed)

    def _auto_close(self, ch: str) -> bool:
        cursor = self.textCursor()
        if cursor.hasSelection() or self.highlighter.starts_in_fence(cursor.block()):
            return False
        action = autoclose_action(cursor.block().text(), cursor.positionInBlock(), ch)
        if action == "over":
            cursor.movePosition(QTextCursor.MoveOperation.Right)
        elif action == "pair":
            cursor.insertText(ch + AUTOCLOSE_PAIRS[ch])
            cursor.movePosition(QTextCursor.MoveOperation.Left)
        else:
            return False
        self.setTextCursor(cursor)
        return True

    def _delete_pair(self) -> bool:
        cursor = self.textCursor()
        if cursor.hasSelection() or not deletes_pair(cursor.block().text(), cursor.positionInBlock()):
            return False
        cursor.movePosition(QTextCursor.MoveOperation.Left)
        cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 2)
        cursor.removeSelectedText()
        return True

    def _continue_on_enter(self) -> bool:
        cursor = self.textCursor()
        if cursor.hasSelection():
            return False
        block = cursor.block()
        prefix = should_continue_on_enter(
            block.text(), cursor.positionInBlock(), self.highlighter.starts_in_fence(block)
        )
        if prefix is None:
            return False
        cursor.beginEditBlock()  # one undo step
        if prefix == "":
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText("\n")
        else:
            cursor.insertText("\n" + prefix)
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        return True

    # --- completion ----------------------------------------------------------

    def _after_typing(self, typed: str) -> None:
        popup = self.completer.popup()
        if typed and typed in TRIGGER_CHARS:
            self._show_completions()
        elif popup.isVisible() and typed != " " and _FENCE_LINE_RE.match(self.textCursor().block().text()):
            self._show_completions()  # narrow fence languages as the user types
        else:
            popup.hide()  # a space or ordinary text ends the token

    def _show_completions(self) -> None:
        popup = self.completer.popup()
        cursor = self.textCursor()
        block = cursor.block()
        suggestions = [] if self.highlighter.starts_in_fence(block) else suggestions_for(
            block.text(), cursor.positionInBlock()
        )
        if not suggestions:
            popup.hide()
            return
        self._suggestions = {s.text: s for s in suggestions}
        self._model.setStringList(list(self._suggestions))
        self.completer.setCompletionPrefix(token_prefix(block.text(), cursor.positionInBlock()))
        if self.completer.completionCount() == 0:
            popup.hide()
            return
        popup.setCurrentIndex(self.completer.completionModel().index(0, 0))
        rect = self.cursorRect()
        rect.setWidth(popup.sizeHintForColumn(0) + popup.verticalScrollBar().sizeHint().width())
        self.completer.complete(rect)

    def _insert_completion(self, text: str) -> None:
        suggestion = self._suggestions.get(text)
        if suggestion is None:
            return
        cursor = self.textCursor()
        block = cursor.block()
        new_line, offset = apply_suggestion(block.text(), cursor.positionInBlock(), suggestion)
        start = block.position()
        cursor.beginEditBlock()
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(new_line)
        cursor.endEditBlock()
        cursor.setPosition(start + offset)
        self.setTextCursor(cursor)
        self.completer.popup().hide()

    # --- tooltips for underlined issues ---------------------------------------

    def viewportEvent(self, event) -> bool:
        if event.type() == QEvent.Type.ToolTip:
            cursor = self.cursorForPosition(event.pos())
            message = self.highlighter.message_at(cursor.blockNumber() + 1, cursor.positionInBlock())
            if message:
                QToolTip.showText(event.globalPos(), message, self)
            else:
                QToolTip.hideText()
            return True
        return super().viewportEvent(event)
