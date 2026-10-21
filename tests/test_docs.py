"""The README and CLAUDE.md are contracts: pin them to the code they describe (text reads only)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
CLAUDE = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
V1_SPEC = ROOT / "docs" / "superpowers" / "specs" / "2026-10-16-md-viewer-design.md"
main_window_text = (ROOT / "mdviewer" / "main_window.py").read_text(encoding="utf-8")
toolbar_text = (ROOT / "mdviewer" / "toolbar.py").read_text(encoding="utf-8")


def code_shortcuts() -> set[str]:
    found = set()
    for text in (main_window_text, toolbar_text):
        found.update(re.findall(r'"((?:Ctrl|Alt)\+[^"\s{]+)"', text))
    # The heading shortcuts are built with an f-string, which the pattern skips.
    return found | {"Ctrl+Alt+1", "Ctrl+Alt+6"}


def test_readme_lists_every_shortcut_in_the_code():
    assert sorted(s for s in code_shortcuts() if s not in README) == []


def test_readme_states_the_normalization_rule():
    flat = " ".join(README.split())
    assert "## Markdown normalization" in README
    assert "A file you only view, or switch between modes without editing, is never rewritten." in flat


def test_readme_names_the_lossy_normalizations():
    flat = " ".join(README.split())
    for needle in ("Soft line breaks", "link reference definitions", "empty paragraphs"):
        assert needle in flat, needle


def test_readme_quotes_the_large_file_note():
    note = re.search(r'LARGE_FILE_NOTE = "([^"]+)"', main_window_text).group(1)
    assert note in README and "5 MB" in README


def test_docs_name_no_removed_v1_wording():
    for text in (README, CLAUDE):
        for stale in ("Preview Mode", "Edit Mode", "preview.py", "Edit commands work in Edit Mode only"):
            assert stale not in text


def test_every_script_named_in_the_docs_exists():
    names = set(re.findall(r"scripts[\\/](\w+\.py)", README + CLAUDE))
    assert {"build_web.py", "check_web.py"} <= names
    assert [n for n in sorted(names) if not (ROOT / "scripts" / n).is_file()] == []


def test_claude_md_keeps_the_schema_bundle_and_seam_rules():
    for needle in ("core/docschema.py", "web-src/src/schema.js", "scripts/build_web.py",
                   "scripts/check_web.py", "WEB OK", "run_link_dialog", "run_image_dialog"):
        assert needle in CLAUDE, needle
    bullet = re.search(r"^- Non-goals \(do not add\):.*?(?=^- |\Z)", CLAUDE, re.S | re.M)
    assert bullet and "merged table cells" in bullet.group(0)
    assert "WYSIWYG" not in bullet.group(0) and "installers" not in bullet.group(0)


def test_v1_spec_points_to_the_v2_spec():
    assert "2026-10-20-wysiwyg-editing-design.md" in V1_SPEC.read_text(encoding="utf-8")
