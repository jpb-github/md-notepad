from pathlib import Path

import pytest

from mdviewer.core.urls import is_safe, resolve

# --- resolve ---------------------------------------------------------------------


@pytest.mark.parametrize("url", ["", "#top", "/abs/x.png", "\\\\server\\share\\x.png",
                                 "https://example.com/a.png", "mailto:a@b.co", "file:///C:/x.png",
                                 "data:image/png;base64,AA", "//cdn.example/x.png"])
def test_resolve_leaves_non_relative_urls(url, tmp_path):
    assert resolve(url, tmp_path) == url


def test_resolve_without_base_dir_leaves_relative_urls():
    assert resolve("img/a.png", None) == "img/a.png"


def test_resolve_relative_path(tmp_path):
    assert resolve("img/a.png", tmp_path) == (tmp_path / "img" / "a.png").as_uri()


def test_resolve_decodes_percent_escapes(tmp_path):
    assert resolve("my%20pic.png", tmp_path) == (tmp_path / "my pic.png").as_uri()


def test_resolve_normalizes_parent_segments(tmp_path):
    expected = Path(tmp_path.parent / "x.png").as_uri()
    assert resolve("../x.png", tmp_path) == expected


def test_resolve_keeps_query_and_fragment(tmp_path):
    assert resolve("doc.md?x=1#part", tmp_path) == (tmp_path / "doc.md").as_uri() + "?x=1#part"


def test_resolve_windows_drive_path(tmp_path):
    assert resolve("C:/pics/a%20b.png", tmp_path) == Path("C:/pics/a b.png").as_uri()


# --- is_safe -----------------------------------------------------------------------


@pytest.mark.parametrize("url", [
    "", "#a", "page.md", "../x.png", "https://example.com", "http://x", "mailto:a@b.co",
    "file:///C:/a.md", "data:image/png;base64,AA", "DATA:IMAGE/gif;base64,AA",
])
def test_safe_urls(url):
    assert is_safe(url)


@pytest.mark.parametrize("url", [
    "javascript:alert(1)", "JavaScript:alert(1)", " javascript:x", "java\tscript:x",
    "\x01javascript:x", "java\nscript:x", "vbscript:msgbox", "VBScript:x",
    "data:text/html,<script>x</script>", "data:,x",
])
def test_unsafe_urls(url):
    assert not is_safe(url)
