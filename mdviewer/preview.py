"""Preview page: a QWebEngineView showing Markdown rendered by core/render.py."""

import tempfile
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineScript, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

from mdviewer.core import render

# PySide6 types adjusted()'s parameter as ComponentFormattingOption, so the bare
# UrlFormattingOption.RemoveFragment is rejected; OR-ing in PrettyDecoded is accepted.
_NO_FRAGMENT = QUrl.ComponentFormattingOption.PrettyDecoded | QUrl.UrlFormattingOption.RemoveFragment


def open_external(url: QUrl) -> None:
    """Hand a clicked link to Windows (browser, mail client, default app)."""
    QDesktopServices.openUrl(url)


class _Page(QWebEnginePage):
    """Keeps the preview on the document: clicked links open outside the app."""

    def __init__(self, document_url: QUrl, parent=None):
        super().__init__(parent)
        self.document_url = document_url

    def acceptNavigationRequest(self, url, nav_type, is_main_frame) -> bool:
        if nav_type != QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            return True  # our own loads
        if url.adjusted(_NO_FRAGMENT) == self.document_url.adjusted(_NO_FRAGMENT):
            return True  # in-page anchor: footnotes, table-of-contents links
        open_external(url)
        return False


class MarkdownPreview(QWebEngineView):
    """Loads each render from a temp file: no 2 MB setHtml limit, anchors keep working."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="mdviewer-", ignore_cleanup_errors=True)
        self.page_file = Path(self._tmpdir.name) / "preview.html"
        self.setPage(_Page(QUrl.fromLocalFile(str(self.page_file)), self))
        # Raw HTML is allowed in Markdown; scripts in it must never run.
        self.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, False)
        self.last_html = ""
        self._scroll = None
        self.loadFinished.connect(self._restore_scroll)

    def show_markdown(
        self, text: str, theme: str, base_dir: Path | None = None, keep_scroll: bool = False
    ) -> bool:
        """Render and load; returns False when the <pre> fallback was used."""
        page_html, ok = render.build_page(text, theme, base_dir)
        self._scroll = self.page().scrollPosition() if keep_scroll else None
        self.page().setBackgroundColor(QColor(render.PAGE_BACKGROUND[theme]))
        self.last_html = page_html
        self.page_file.write_text(page_html, encoding="utf-8")
        self.load(QUrl.fromLocalFile(str(self.page_file)))
        return ok

    def _restore_scroll(self, _ok: bool) -> None:
        if self._scroll is None:
            return
        x, y = self._scroll.x(), self._scroll.y()
        self._scroll = None
        # ApplicationWorld scripts still run with page JavaScript disabled.
        self.page().runJavaScript(
            f"window.scrollTo({x}, {y});", QWebEngineScript.ScriptWorldId.ApplicationWorld.value
        )
