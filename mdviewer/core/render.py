"""Markdown -> themed HTML page for the preview (pure, Qt-free).

GitHub-like styling: one shared stylesheet driven by CSS variables; light,
dark and gray differ only in the variable set and the Pygments style, so the same body
HTML is reused for both themes.
"""

import html
from pathlib import Path

import mistune
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

from mdviewer.core import urls

THEMES = ("light", "dark", "gray")
PLUGINS = ["table", "strikethrough", "footnotes", "task_lists", "url"]
# file: is needed for resolved relative URLs; javascript:/vbscript: stay blocked.
_ALLOWED_PROTOCOLS = ("file:", "data:image/")

_VARIABLES = {
    "light": {
        "--bg": "#ffffff",
        "--fg": "#1f2328",
        "--muted": "#59636e",
        "--border": "#d1d9e0",
        "--link": "#0969da",
        "--code-bg": "#f6f8fa",
        "--row-alt": "#f6f8fa",
    },
    "dark": {
        "--bg": "#0d1117",
        "--fg": "#f0f6fc",
        "--muted": "#9198a1",
        "--border": "#3d444d",
        "--link": "#4493f8",
        "--code-bg": "#151b23",
        "--row-alt": "#151b23",
    },
    "gray": {
        "--bg": "#3a3d41",
        "--fg": "#e6e8eb",
        "--muted": "#a6adb5",
        "--border": "#565b61",
        "--link": "#6cb2ff",
        "--code-bg": "#2f3236",
        "--row-alt": "#2f3236",
    },
}
PAGE_BACKGROUND = {theme: values["--bg"] for theme, values in _VARIABLES.items()}
_PYGMENTS_STYLES = {"light": "default", "dark": "native", "gray": "native"}

_SHARED_CSS = """
html, body { margin: 0; background: var(--bg); color: var(--fg); }
body {
  font: 16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans",
        Helvetica, Arial, sans-serif;
}
.markdown-body { box-sizing: border-box; max-width: 835px; margin: 0 auto;
  padding: 32px; word-wrap: break-word; }
.markdown-body > *:first-child { margin-top: 0; }
a { color: var(--link); text-decoration: none; }
a:hover { text-decoration: underline; }
h1, h2, h3, h4, h5, h6 { margin: 24px 0 16px; font-weight: 600; line-height: 1.25; }
h1 { font-size: 2em; padding-bottom: .3em; border-bottom: 1px solid var(--border); }
h2 { font-size: 1.5em; padding-bottom: .3em; border-bottom: 1px solid var(--border); }
h3 { font-size: 1.25em; }
h4 { font-size: 1em; }
h5 { font-size: .875em; }
h6 { font-size: .85em; color: var(--muted); }
p, blockquote, ul, ol, table, pre, .highlight { margin: 0 0 16px; }
ul, ol { padding-left: 2em; }
li + li { margin-top: .25em; }
.task-list-item { list-style: none; }
.task-list-item-checkbox { margin: 0 .2em .25em -1.4em; vertical-align: middle; }
blockquote { padding: 0 1em; color: var(--muted); border-left: .25em solid var(--border); }
hr { height: .25em; padding: 0; margin: 24px 0; background: var(--border); border: 0; }
img { max-width: 100%; }
table { border-collapse: collapse; display: block; width: max-content; max-width: 100%; overflow: auto; }
th, td { padding: 6px 13px; border: 1px solid var(--border); }
th { font-weight: 600; }
tr:nth-child(2n) { background: var(--row-alt); }
code, pre { font-family: Consolas, Menlo, "Liberation Mono", monospace; font-size: 85%; }
code { padding: .2em .4em; background: var(--code-bg); border-radius: 6px; }
pre, .highlight pre { padding: 16px; overflow: auto; line-height: 1.45;
  background: var(--code-bg); border-radius: 6px; }
pre code { padding: 0; background: transparent; font-size: 100%; }
.highlight { background: var(--code-bg); border-radius: 6px; }
pre.fallback { white-space: pre-wrap; }
.footnotes { font-size: 85%; color: var(--muted); border-top: 1px solid var(--border); }
"""


class _Renderer(mistune.HTMLRenderer):
    """HTML renderer with Pygments code blocks and base-dir URL resolution."""

    def __init__(self, base_dir: Path | None):
        super().__init__(escape=False, allow_harmful_protocols=_ALLOWED_PROTOCOLS)
        self._base_dir = base_dir

    def block_code(self, code: str, info: str | None = None) -> str:
        lang = info.split(None, 1)[0] if info and info.strip() else ""
        if lang:
            try:
                lexer = get_lexer_by_name(lang)
            except ClassNotFound:
                lexer = None
            if lexer is not None:
                return highlight(code, lexer, HtmlFormatter(cssclass="highlight"))
        return super().block_code(code, info)

    def link(self, text: str, url: str, title: str | None = None) -> str:
        return super().link(text, self._resolve(url), title)

    def image(self, text: str, url: str, title: str | None = None) -> str:
        return super().image(text, self._resolve(url), title)

    def _resolve(self, url: str) -> str:
        """Turn a document-relative URL into an absolute file: URI."""
        return urls.resolve(url, self._base_dir)


def page_css(theme: str) -> str:
    variables = "".join(f"{name}: {value}; " for name, value in _VARIABLES[theme].items())
    pygments_css = HtmlFormatter(style=_PYGMENTS_STYLES[theme]).get_style_defs(".highlight")
    return f":root {{ {variables}}}\n{_SHARED_CSS}\n{pygments_css}\n"


def render_body(text: str, base_dir: Path | None = None) -> str:
    markdown = mistune.create_markdown(renderer=_Renderer(base_dir), plugins=PLUGINS)
    return markdown(text)


def highlight_code(code: str, language: str) -> str:
    """Pygments markup for a code block in the Rendered editor; "" when the language is unknown.

    Class-based <span>s only (no wrapper, no inline colors): the editor puts them in
    a <pre class="highlight"> and page_css(theme) supplies the colors. The text is
    kept exactly, leading and trailing newlines included."""
    if not language.strip():
        return ""
    try:
        lexer = get_lexer_by_name(language, stripnl=False, ensurenl=False)
    except ClassNotFound:
        return ""
    return highlight(code, lexer, HtmlFormatter(nowrap=True))


def build_page(text: str, theme: str, base_dir: Path | None = None) -> tuple[str, bool]:
    """Full HTML page; falls back to the escaped raw text if rendering fails."""
    try:
        body, ok = render_body(text, base_dir), True
    except Exception:  # any renderer/lexer bug must not blank the preview
        body, ok = f'<pre class="fallback">{html.escape(text)}</pre>', False
    return (
        '<!DOCTYPE html>\n<html><head><meta charset="utf-8">'
        f"<style>{page_css(theme)}</style></head>"
        f'<body><article class="markdown-body">{body}</article></body></html>\n'
    ), ok
