import html
import re

import pytest
from pygments.formatters import HtmlFormatter

from mdviewer.core import render
from mdviewer.core.render import build_page, page_css, render_body


def test_heading():
    assert "<h1>Title</h1>" in render_body("# Title")


def test_table():
    body = render_body("| a | b |\n| --- | --- |\n| 1 | 2 |\n")
    assert "<table>" in body and "<td>1</td>" in body


def test_strikethrough():
    assert "<del>gone</del>" in render_body("~~gone~~")


def test_footnotes():
    assert 'class="footnotes"' in render_body("Text[^1]\n\n[^1]: The note.\n")


def test_task_list():
    assert "task-list-item-checkbox" in render_body("- [ ] todo\n- [x] done\n")


def test_fenced_python_is_highlighted():
    body = render_body("```python\ndef f():\n    return 1\n```\n")
    assert '<div class="highlight">' in body
    assert '<span class="k">def</span>' in body


def test_unknown_language_falls_back_to_escaped_code():
    body = render_body("```nosuchlang\n<b>x</b>\n```\n")
    assert "&lt;b&gt;x&lt;/b&gt;" in body
    assert "highlight" not in body


def test_fence_without_language_is_escaped():
    assert "<pre><code>&lt;i&gt;" in render_body("```\n<i>\n```\n")


def test_raw_html_comment_is_kept_so_it_stays_hidden():
    assert "<!-- secret -->" in render_body("<!-- secret -->\n\ntext\n")


def test_relative_image_resolves_against_base_dir(tmp_path):
    body = render_body("![logo](img/a%20b.png)", tmp_path)
    assert (tmp_path / "img" / "a b.png").as_uri() in body


def test_relative_link_keeps_fragment(tmp_path):
    body = render_body("[next](other.md#part)", tmp_path)
    assert 'href="' + (tmp_path / "other.md").as_uri() + '#part"' in body


def test_absolute_and_anchor_urls_untouched(tmp_path):
    body = render_body("[w](https://example.com/x) [f](#notes)", tmp_path)
    assert 'href="https://example.com/x"' in body
    assert 'href="#notes"' in body


def test_no_base_dir_leaves_relative_urls():
    assert 'src="img.png"' in render_body("![x](img.png)")


def test_javascript_link_is_neutralized():
    assert "javascript:" not in render_body("[x](javascript:alert(1))")


def test_light_and_dark_share_the_same_body():
    light, ok_light = build_page("# Hi\n\n*there*", "light")
    dark, ok_dark = build_page("# Hi\n\n*there*", "dark")
    assert ok_light and ok_dark
    assert light.split("<body>", 1)[1] == dark.split("<body>", 1)[1]
    assert "#1f2328" in light
    assert "#0d1117" in dark


def test_page_basics():
    page, _ = build_page("text", "light")
    assert page.startswith("<!DOCTYPE html>")
    assert '<meta charset="utf-8">' in page
    assert "835px" in page


def test_pygments_css_follows_theme():
    assert HtmlFormatter(style="default").get_style_defs(".highlight") in page_css("light")
    assert HtmlFormatter(style="native").get_style_defs(".highlight") in page_css("dark")


def test_page_background_per_theme():
    assert render.PAGE_BACKGROUND == {
        "light": "#ffffff", "dark": "#0d1117", "darkgray": "#3a3d41", "lightgray": "#ececec",
    }


@pytest.mark.parametrize("theme, background", [("darkgray", "#3a3d41"), ("lightgray", "#ececec")])
def test_gray_themes_render_with_their_own_variables(theme, background):
    page, ok = build_page("# Hi\n\n*there*", theme)
    light, _ = build_page("# Hi\n\n*there*", "light")
    assert ok
    assert f"--bg: {background};" in page
    assert page.split("<body>", 1)[1] == light.split("<body>", 1)[1]
    assert set(render.THEMES) == {"light", "dark", "darkgray", "lightgray"}


def test_light_gray_is_black_text_on_a_very_light_gray():
    css = page_css("lightgray")
    assert "--fg: #000000;" in css
    assert HtmlFormatter(style="default").get_style_defs(".highlight") in css


def test_render_failure_falls_back_to_escaped_pre(monkeypatch):
    def boom(text, base_dir=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(render, "render_body", boom)
    page, ok = render.build_page("<x> & y", "dark")
    assert not ok
    assert '<pre class="fallback">&lt;x&gt; &amp; y</pre>' in page
    assert "#0d1117" in page


def test_empty_document():
    page, ok = build_page("", "light")
    assert ok
    assert '<article class="markdown-body"></article>' in page


# --- highlight_code (Rendered editor code blocks) ------------------------------------------


def test_highlight_code_is_class_based_spans_only():
    markup = render.highlight_code("print(1)", "python")
    assert '<span class="nb">print</span>' in markup
    assert "<pre" not in markup and "<div" not in markup and "style=" not in markup


def test_highlight_code_keeps_the_text_exactly():
    code = "\n\nx = '<b>' & 1\n\n"
    markup = render.highlight_code(code, "python")
    assert html.unescape(re.sub(r"<[^>]+>", "", markup)) == code


def test_highlight_code_language_lookup_ignores_case():
    assert render.highlight_code("x = 1", "Python") == render.highlight_code("x = 1", "python") != ""


@pytest.mark.parametrize("language", ["", "  ", "nosuchlang", "py thon"])
def test_highlight_code_unknown_language_is_empty(language):
    assert render.highlight_code("x = 1", language) == ""


@pytest.mark.parametrize("theme", render.THEMES)
def test_editor_page_fills_the_theme_slot(theme):
    shell = (render.WEB_DIR / "editor.html").read_text(encoding="utf-8")
    page = render.editor_page(theme)
    assert render.THEME_SLOT not in page
    assert f'<style id="theme">{render.page_css(theme)}</style>' in page
    assert page.replace(render.page_css(theme), render.THEME_SLOT) == shell  # nothing else changes
    assert (render.WEB_DIR / "editor.js").is_file()
