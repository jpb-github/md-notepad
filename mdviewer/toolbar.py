"""The format toolbar of the Rendered editor (spec section 3).

Its buttons run page commands through `commandRequested`. The page's
`selectionState` drives their checked and enabled state. The shortcuts belong
to the page's keymap (web-src/src/input.js): the actions carry none, and the
tooltips name them.
"""

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPalette, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QComboBox, QToolBar

ICON_SIZE = 16
_ICON_SCALES = (1, 1.5, 2, 3)  # pixmaps for 100% to 300% display scaling
# Block combo: (text, setBlock args, shortcut); the page reports the block in the same shape.
BLOCKS = (
    ("Normal", {"type": "paragraph"}, "Ctrl+Alt+0"),
    *((f"Heading {level}", {"type": "heading", "level": level}, f"Ctrl+Alt+{level}") for level in range(1, 7)),
    ("Code block", {"type": "code_block"}, None),
)
# Buttons in toolbar order, None between groups: (key, text, shortcut, command, args).
# The command's name is also its key in selectionState.can.
BUTTONS = (
    ("bold", "Bold", "Ctrl+B", "toggleMark", "strong"),
    ("italic", "Italic", "Ctrl+I", "toggleMark", "em"),
    ("strike", "Strikethrough", "Ctrl+Shift+X", "toggleMark", "strike"),
    ("code", "Inline code", "Ctrl+`", "toggleMark", "code"),
    ("link", "Link", "Ctrl+K", "linkDialog", None),
    None,
    ("bullets", "Bulleted list", "Ctrl+Shift+8", "toggleList", "bullet"),
    ("numbers", "Numbered list", "Ctrl+Shift+7", "toggleList", "ordered"),
    ("tasks", "Task list", "Ctrl+Shift+9", "toggleList", "task"),
    None,
    ("quote", "Quote", "Ctrl+Shift+.", "toggleQuote", None),
    ("code_block", "Code block", None, "insertCodeBlock", None),
    ("table", "Table", None, "insertTable", {"rows": 3, "cols": 3}),
    ("image", "Image", None, "imageDialog", None),
    ("rule", "Horizontal rule", None, "insertRule", None),
    None,
    ("clear", "Clear formatting", "Ctrl+Space", "clearFormatting", None),
)
# Buttons checked while their mark is active at the selection.
MARKS = {"bold": "strong", "italic": "em", "strike": "strike", "code": "code", "link": "link"}


def tooltip(text: str, shortcut: str | None) -> str:
    return f"{text} ({shortcut})" if shortcut else text


def _letter(p: QPainter, text: str, pixel_size: int, *, bold=False, italic=False, family=None, rect=None) -> None:
    font = QFont(family) if family else QFont()
    font.setPixelSize(pixel_size)
    font.setBold(bold)
    font.setItalic(italic)
    p.setFont(font)
    p.drawText(rect or QRectF(0, 0, 16, 16), Qt.AlignmentFlag.AlignCenter, text)


def _rows(p: QPainter, mark) -> None:
    """Three rows: a marker drawn by mark(p, y), then a line."""
    for y in (3.5, 8, 12.5):
        mark(p, y)
        p.drawLine(QPointF(7, y), QPointF(14, y))


def _draw_glyph(p: QPainter, key: str, color: QColor) -> None:
    fill = QColor(color)
    p.setPen(QPen(color, 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    if key == "bold":
        _letter(p, "B", 14, bold=True)
    elif key == "italic":
        _letter(p, "I", 14, italic=True, family="Georgia")
    elif key == "strike":
        _letter(p, "S", 13)
        p.drawLine(QPointF(2.5, 8), QPointF(13.5, 8))
    elif key == "code":
        p.drawPolyline(QPolygonF([QPointF(6, 4), QPointF(2, 8), QPointF(6, 12)]))
        p.drawPolyline(QPolygonF([QPointF(10, 4), QPointF(14, 8), QPointF(10, 12)]))
    elif key == "link":
        p.translate(8, 8)
        p.rotate(-45)
        p.drawRoundedRect(QRectF(-6.5, -2.5, 8, 5), 2.5, 2.5)
        p.drawRoundedRect(QRectF(-1.5, -2.5, 8, 5), 2.5, 2.5)
    elif key == "bullets":
        def dot(painter, y):
            painter.setBrush(fill)
            painter.drawEllipse(QPointF(3.5, y), 1.2, 1.2)
            painter.setBrush(Qt.BrushStyle.NoBrush)

        _rows(p, dot)
    elif key == "numbers":
        def number(painter, y):
            _letter(painter, str(int(y // 4.5) + 1), 6, bold=True, rect=QRectF(0, y - 3, 6, 6))

        _rows(p, number)
    elif key == "tasks":
        _rows(p, lambda painter, y: painter.drawRect(QRectF(2, y - 1.5, 3, 3)))
    elif key == "quote":
        p.drawLine(QPointF(3, 2.5), QPointF(3, 13.5))
        for y in (4, 8, 12):
            p.drawLine(QPointF(6.5, y), QPointF(14, y))
    elif key == "code_block":
        _letter(p, "{}", 12, bold=True)
    elif key == "table":
        p.drawRect(QRectF(2, 2.5, 12, 11))
        for x in (6, 10):
            p.drawLine(QPointF(x, 2.5), QPointF(x, 13.5))
        for y in (6.2, 9.8):
            p.drawLine(QPointF(2, y), QPointF(14, y))
    elif key == "image":
        p.drawRect(QRectF(2, 2.5, 12, 11))
        p.drawPolyline(QPolygonF([QPointF(2.5, 12), QPointF(6, 8), QPointF(8.5, 10.5), QPointF(10.5, 8.5), QPointF(13.5, 12)]))
        p.setBrush(fill)
        p.drawEllipse(QPointF(10.5, 5.5), 1.2, 1.2)
    elif key == "rule":
        p.setPen(QPen(color, 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(2, 8), QPointF(14, 8))
    elif key == "clear":
        _letter(p, "T", 13, rect=QRectF(0, 0, 12, 16))
        p.drawLine(QPointF(10.5, 9.5), QPointF(14, 13))
        p.drawLine(QPointF(14, 9.5), QPointF(10.5, 13))


def glyph_icon(key: str, palette: QPalette) -> QIcon:
    """A flat glyph in the palette's button-text color, sharp at every display scale."""
    icon = QIcon()
    for mode, group in ((QIcon.Mode.Normal, QPalette.ColorGroup.Active), (QIcon.Mode.Disabled, QPalette.ColorGroup.Disabled)):
        color = palette.color(group, QPalette.ColorRole.ButtonText)
        for scale in _ICON_SCALES:
            side = round(ICON_SIZE * scale)
            pixmap = QPixmap(side, side)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            painter.scale(side / 16, side / 16)
            _draw_glyph(painter, key, color)
            painter.end()
            icon.addPixmap(pixmap, mode)
    return icon


def _same_block(item_args: dict, block) -> bool:
    if not isinstance(block, dict) or block.get("type") != item_args["type"]:
        return False
    return item_args["type"] != "heading" or block.get("level") == item_args["level"]


class FormatToolbar(QToolBar):
    commandRequested = Signal(str, object)

    def __init__(self, parent=None) -> None:
        super().__init__("Format", parent)
        self.setObjectName("format_toolbar")
        self.setMovable(False)
        self.setFloatable(False)
        self.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        # View > Toolbar is the one switch.
        self.toggleViewAction().setVisible(False)
        self._state: dict = {}
        self._commands: dict[str, tuple[str, object]] = {}

        self.block_box = QComboBox()
        self.block_box.setToolTip("Block type")
        self.block_box.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        for text, args, shortcut in BLOCKS:
            self.block_box.addItem(text, args)
            self.block_box.setItemData(self.block_box.count() - 1, tooltip(text, shortcut), Qt.ItemDataRole.ToolTipRole)
        # Only `activated`: currentIndexChanged also fires on update_state's own setCurrentIndex.
        self.block_box.activated.connect(self._block_picked)
        self.addWidget(self.block_box)
        self.addSeparator()

        self.buttons: dict[str, QAction] = {}
        for entry in BUTTONS:
            if entry is None:
                self.addSeparator()
                continue
            key, text, shortcut, command, args = entry
            action = self.addAction(text)
            action.setToolTip(tooltip(text, shortcut))
            action.setCheckable(key in MARKS)
            action.triggered.connect(lambda _checked=False, k=key: self._button_clicked(k))
            self.buttons[key] = action
            self._commands[key] = (command, args)
        self._redraw_icons()
        self.update_state({})

    def _redraw_icons(self) -> None:
        for key, action in self.buttons.items():
            action.setIcon(glyph_icon(key, self.palette()))

    def update_state(self, state: dict) -> None:
        self._state = state if isinstance(state, dict) else {}
        can = self._state.get("can")
        can = can if isinstance(can, dict) else {}
        marks = self._state.get("marks")
        marks = marks if isinstance(marks, list) else []
        for key, action in self.buttons.items():
            action.setEnabled(can.get(self._commands[key][0]) is True)
            if key in MARKS:
                action.setChecked(MARKS[key] in marks)
        self.block_box.setEnabled(can.get("setBlock") is True)
        block = self._state.get("block")
        index = -1
        for number, (_text, args, _shortcut) in enumerate(BLOCKS):
            if _same_block(args, block):
                index = number
                break
        self.block_box.setCurrentIndex(index)

    def _button_clicked(self, key: str) -> None:
        # Qt flipped the check already; show the page's last report until it answers.
        self.update_state(self._state)
        command, args = self._commands[key]
        self.commandRequested.emit(command, args)

    def _block_picked(self, number: int) -> None:
        self.update_state(self._state)
        self.commandRequested.emit("setBlock", self.block_box.itemData(number))

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.PaletteChange:
            self._redraw_icons()
        super().changeEvent(event)
