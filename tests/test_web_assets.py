"""Static checks on the shipped web editor files.

No Qt here (tests/ must stay Qt-free); scripts/check_web.py loads the page for real.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "mdviewer" / "web"
CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src file: data: https: http:; frame-src 'self' about:; child-src 'self'"
)
THEME_SLOT = "/*@THEME_CSS@*/"


def shell() -> str:
    return (WEB / "editor.html").read_text(encoding="utf-8")


def test_shell_sets_the_spec_csp():
    metas = re.findall(r'<meta http-equiv="Content-Security-Policy" content="([^"]*)">', shell())
    assert metas == [CSP]


def test_shell_loads_only_external_scripts_in_order():
    scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", shell(), flags=re.S)
    assert [attrs.strip() for attrs, _ in scripts] == ['src="qwebchannel.js"', 'src="editor.js"']
    assert all(body == "" for _, body in scripts)


def test_shell_has_no_event_handler_attributes():
    assert not re.search(r"\son[a-z]+\s*=", shell())


def test_shell_has_one_theme_slot_inside_the_theme_style():
    page = shell()
    assert page.count(THEME_SLOT) == 1
    assert f'<style id="theme">{THEME_SLOT}</style>' in page


def test_shell_links_the_bundle_stylesheet_and_mount_point():
    page = shell()
    assert '<link rel="stylesheet" href="editor.css">' in page
    assert '<article class="markdown-body" id="editor"></article>' in page


def test_committed_build_outputs_exist():
    for name in ("editor.js", "editor.css", "qwebchannel.js", "THIRD_PARTY.txt"):
        assert (WEB / name).stat().st_size > 0, name


def test_qwebchannel_is_qt_original_with_its_license_header():
    head = (WEB / "qwebchannel.js").read_text(encoding="utf-8")[:400]
    assert "The Qt Company" in head
    assert "SPDX-License-Identifier" in head


def test_third_party_notices_cover_the_bundled_packages():
    notices = (WEB / "THIRD_PARTY.txt").read_text(encoding="utf-8")
    for name in ("prosemirror-model", "prosemirror-state", "prosemirror-view"):
        assert f"==== {name} " in notices, name


def test_node_modules_is_git_ignored():
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "web-src/node_modules/" in lines


def test_code_block_languages_match_the_source_editor():
    from mdviewer.core.completion import FENCE_LANGUAGES

    source = (ROOT / "web-src" / "src" / "nodeviews.js").read_text(encoding="utf-8")
    match = re.search(r"^export const FENCE_LANGUAGES = (\[.*?^\]);$", source, flags=re.S | re.M)
    assert match, "nodeviews.js has no 'export const FENCE_LANGUAGES = [...];' block"
    assert json.loads(match.group(1)) == list(FENCE_LANGUAGES)
