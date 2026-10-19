"""Generate assets/mdviewer.ico (and a 256px preview PNG) by drawing the logo with QPainter.

Run:  .venv\\Scripts\\python scripts\\make_icon.py
The logo is vector-drawn per size (not downscaled), so small sizes stay crisp.
"""

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "assets"
SIZES = (16, 24, 32, 48, 64, 128, 256)

# Everything below is in a 256x256 design space.
TILE = QRectF(10, 10, 236, 236)
TILE_RADIUS = 54
M_POINTS = [(46, 176), (46, 80), (86, 128), (126, 80), (126, 176)]
ARROW_STEM = [(190, 80), (190, 172)]
ARROW_HEAD = [(164, 146), (190, 174), (216, 146)]


def polyline(points) -> QPainterPath:
    path = QPainterPath(QPointF(*points[0]))
    for x, y in points[1:]:
        path.lineTo(x, y)
    return path


def render(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
    p.scale(size / 256, size / 256)

    # Soft drop shadow (skipped at tiny sizes where it only muddies the edge).
    if size >= 48:
        for i, alpha in enumerate((14, 10, 6)):
            grow = 3 + i * 3
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(15, 23, 42, alpha))
            p.drawRoundedRect(TILE.adjusted(-grow + 2, -grow + 6, grow - 2, grow + 6), TILE_RADIUS + grow, TILE_RADIUS + grow)

    gradient = QLinearGradient(TILE.topLeft(), TILE.bottomRight())
    gradient.setColorAt(0.0, QColor("#5B8CFF"))
    gradient.setColorAt(1.0, QColor("#3730A3"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(gradient)
    p.drawRoundedRect(TILE, TILE_RADIUS, TILE_RADIUS)

    # Subtle top sheen.
    sheen = QLinearGradient(TILE.topLeft(), QPointF(TILE.left(), TILE.center().y()))
    sheen.setColorAt(0.0, QColor(255, 255, 255, 60))
    sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(sheen)
    p.drawRoundedRect(TILE, TILE_RADIUS, TILE_RADIUS)

    # The "M" and down-arrow, nudged so the pair is optically centered.
    p.translate(-1, 0)
    pen = QPen(QColor("white"), 24, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(polyline(M_POINTS))
    p.drawPath(polyline(ARROW_STEM))
    p.drawPath(polyline(ARROW_HEAD))
    p.end()
    return image


def png_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, "PNG")
    return bytes(data)


def write_ico(path: Path, pngs: list[tuple[int, bytes]]) -> None:
    header = struct.pack("<HHH", 0, 1, len(pngs))
    offset = 6 + 16 * len(pngs)
    entries, blobs = b"", b""
    for size, data in pngs:
        dim = 0 if size >= 256 else size  # 0 means 256 in the ICO format
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset + len(blobs))
        blobs += data
    path.write_bytes(header + entries + blobs)


def main() -> int:
    _app = QGuiApplication(sys.argv)
    OUT_DIR.mkdir(exist_ok=True)
    pngs = [(size, png_bytes(render(size))) for size in SIZES]
    write_ico(OUT_DIR / "mdviewer.ico", pngs)
    (OUT_DIR / "mdviewer.png").write_bytes(pngs[-1][1])
    print(f"Wrote {OUT_DIR / 'mdviewer.ico'} ({', '.join(str(s) for s in SIZES)} px)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
