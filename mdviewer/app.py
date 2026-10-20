"""Application bootstrap: QApplication, settings load/save, window lifecycle."""

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from mdviewer.core import settings
from mdviewer.main_window import APP_NAME, MainWindow


def icon_path() -> Path:
    """assets/mdviewer.ico: bundled next to the code in a PyInstaller build, else in the repo."""
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return root / "assets" / "mdviewer.ico"


def build(argv: list[str]) -> tuple[QApplication, MainWindow]:
    """Create (or reuse) the QApplication and a MainWindow from saved settings."""
    app = QApplication.instance() or QApplication([sys.argv[0], *argv])
    app.setStyle("windowsvista")
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(str(icon_path())))  # title bar, dialogs; the exe icon alone is not used by Qt
    return app, MainWindow(settings.load())


def save_settings(window: MainWindow) -> None:
    """Persist theme, geometry and zoom; a failed write must not crash on exit."""
    try:
        settings.save(None, window.settings_snapshot())
    except OSError:
        pass


def main(argv: list[str]) -> int:
    app, window = build(argv)
    window.show()  # shown first so an open-error box has a visible parent
    if argv:
        window.open_file(argv[0])
    code = app.exec()
    save_settings(window)
    return code
