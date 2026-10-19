"""Application bootstrap: QApplication, settings load/save, window lifecycle."""

import sys

from PySide6.QtWidgets import QApplication

from mdviewer.core import settings
from mdviewer.main_window import APP_NAME, MainWindow


def build(argv: list[str]) -> tuple[QApplication, MainWindow]:
    """Create (or reuse) the QApplication and a MainWindow from saved settings."""
    app = QApplication.instance() or QApplication([sys.argv[0], *argv])
    app.setStyle("windowsvista")
    app.setApplicationName(APP_NAME)
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
