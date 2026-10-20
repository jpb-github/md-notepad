from pathlib import Path

import pytest

from mdviewer.core.urls import anchor_block, image_src, is_safe, resolve, slug

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


# --- image_src ---------------------------------------------------------------------


@pytest.mark.parametrize("typed", ["https://e.com/a.png", "file:///C:/x.png", "data:image/png;base64,AA",
                                   "img/a.png", "../a.png", "a b.png"])
def test_image_src_keeps_urls_and_relative_paths(typed, tmp_path):
    assert image_src(typed, tmp_path) == typed


def test_image_src_relative_path_uses_slashes(tmp_path):
    assert image_src(r"img\a.png", tmp_path) == "img/a.png"


def test_image_src_strips_spaces_and_explorer_quotes(tmp_path):
    assert image_src(f'  "{tmp_path / "a.png"}"  ', tmp_path) == "a.png"


def test_image_src_absolute_path_in_the_folder_becomes_relative(tmp_path):
    assert image_src(str(tmp_path / "pics" / "a.png"), tmp_path) == "pics/a.png"
    assert image_src((tmp_path / "pics" / "a.png").as_posix(), tmp_path) == "pics/a.png"


def test_image_src_absolute_path_elsewhere_on_the_drive_goes_up(tmp_path):
    assert image_src(str(tmp_path.parent / "a.png"), tmp_path) == "../a.png"


def test_image_src_other_drive_is_a_file_uri(tmp_path):
    other = r"Q:\pics\a b.png" if not str(tmp_path).upper().startswith("Q:") else r"R:\pics\a b.png"
    assert image_src(other, tmp_path) == Path(other).as_uri()


def test_image_src_untitled_is_a_file_uri():
    assert image_src(r"C:\pics\a b.png", None) == "file:///C:/pics/a%20b.png"


@pytest.mark.parametrize("name", ["a b.png", "100%.png", "a#1.png", "café (1).png", "%20.png"])
def test_image_src_resolves_back_to_the_file(name, tmp_path):
    target = tmp_path / "pics" / name
    assert resolve(image_src(str(target), tmp_path), tmp_path) == target.as_uri()


# --- slug and anchor_block ------------------------------------------------------------


@pytest.mark.parametrize("text, expected", [
    ("Intro", "intro"), ("Section Two", "section-two"), ("What's new?", "whats-new"),
    ("C++ & C#", "c--c"), ("snake_case and-dash", "snake_case-and-dash"), ("Café 2", "café-2"),
    ("  padded  ", "padded"), ("", ""),
])
def test_slug(text, expected):
    assert slug(text) == expected


def test_anchor_block_finds_the_heading():
    assert anchor_block([None, "Intro", None, "Section Two"], "section-two") == 3


def test_anchor_block_counts_repeated_headings():
    headings = ["Notes", None, "Notes", "Notes"]
    assert [anchor_block(headings, f) for f in ("notes", "notes-1", "notes-2")] == [0, 2, 3]


def test_anchor_block_ignores_case_and_decodes_escapes():
    assert anchor_block(["Café Menu"], "Caf%C3%A9-Menu") == 0


@pytest.mark.parametrize("fragment", ["missing", "", "intro-1"])
def test_anchor_block_without_a_match(fragment):
    assert anchor_block([None, "Intro"], fragment) is None
