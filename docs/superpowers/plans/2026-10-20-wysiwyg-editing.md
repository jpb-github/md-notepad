# MD Viewer v2 - WYSIWYG Editing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Status: high-level outline.** Phases and tasks are fixed; each task's
> bite-sized steps (tests, code, commands) are written out on request, task
> by task, below its heading. Do not execute a task whose steps are not yet
> detailed. Detailed so far: Tasks 1-8.

**Goal:** Make the rendered view an editable WYSIWYG Markdown editor with a
format toolbar, keeping the plain-text editor as Source mode.

**Architecture:** A ProseMirror editor (committed esbuild bundle) runs in the
existing `QWebEngineView` and talks to Python over `QWebChannel`. Python owns
Markdown in both directions: `core/docmodel.py` turns the mistune AST into
ProseMirror document JSON, `core/serialize.py` turns that JSON back into
normalized Markdown. `MainWindow` keeps one buffer; in Rendered mode it is
refreshed by an asynchronous pull before every save, mode switch or close.

**Tech Stack:** Python 3.12+, PySide6 >= 6.5 (QtWebEngine, QtWebChannel),
mistune 3 (AST renderer), Pygments, pytest; ProseMirror packages + esbuild
(Node only to rebuild the bundle).

**Spec:** `docs/superpowers/specs/2026-10-20-wysiwyg-editing-design.md`
(builds on `docs/superpowers/specs/2026-10-16-md-viewer-design.md`).

## Global Constraints

- `mdviewer/core/` and `tests/` never import Qt (`rg -n "import (PySide|Qt)|from PySide" mdviewer/core tests` prints nothing).
- Modes: **Rendered** (View > Rendered, Ctrl+P, default on open) and **Source** (View > Source, Ctrl+E).
- A file only viewed or switched between modes without editing is never rewritten: the buffer stays byte-identical.
- Save keeps the detected encoding and newline style (`MainWindow.newline`); the serializer emits `\n` only.
- Never use `QPlainTextEdit.toPlainText()` for the buffer; use `MainWindow.buffer`.
- Every modal goes through a seam in `mdviewer/main_window.py` (`ask`, `show_error`, `pick_open_path`, `pick_save_path`, `run_preferences`, `read_system_theme`, new: `run_link_dialog`, `run_image_dialog`).
- Themes are `light`, `dark`, `gray`; code highlight markup is class-based and theme-independent.
- Raw HTML never runs scripts: `html_block` in `<iframe sandbox="allow-same-origin" srcdoc>`, never `allow-scripts` (Task 8 decision); `html_inline` shown escaped; page CSP `script-src 'self'`.
- `javascript:` and `vbscript:` URLs are stripped in `docmodel` and in JS paste/link paths.
- Schema names live in `core/docschema.py` and `web-src/src/schema.js`; a pytest check keeps them equal.
- `mdviewer/web/editor.js`, `editor.css`, `qwebchannel.js` and `THIRD_PARTY.txt` are committed build output (`scripts/build_web.py`); `web-src/node_modules/` is git-ignored; Node is not needed for tests or packaging. After every bundle rebuild, `scripts/check_web.py` must print `WEB OK`.
- The page loads its scripts from its own `file:` folder under CSP `script-src 'self'` (R1 retired in Task 1); there is no custom URL scheme.
- Files larger than 5 MB open in Source mode with status note `Large file: opened in Source mode`.
- Timeouts: page `ready()` 5 s, document pull 3 s.
- UI checks go in `scripts/smoke_ui.py` above `# --- Later tasks insert their checks directly above this line. ---`, using `check()` and `FAKE`.
- Commits: small, one per task, conventional prefixes (`feat:`, `fix:`, `docs:`, `chore:`).

## File Map

| File | Status | Responsibility | Task |
|---|---|---|---|
| `web-src/package.json`, `package-lock.json`, `build.mjs` | new | pinned ProseMirror deps, esbuild config | 1 |
| `scripts/build_web.py` | new | `npm ci` + esbuild, copies Qt's `qwebchannel.js` next to the bundle | 1 |
| `scripts/check_web.py` | new | offscreen load of the shell: `ready()`, CSP blocks inline scripts, prints `WEB OK` | 1, extended in 8-11 if useful |
| `tests/test_web_assets.py` | new | Qt-free static checks: CSP string, no inline scripts, outputs present | 1 |
| `mdviewer/web/editor.html` | new | page shell: CSP, `editor.css` link, theme slot `/*@THEME_CSS@*/`, `qwebchannel.js` + `editor.js` `<script src>` | 1 |
| `mdviewer/web/editor.js`, `editor.css`, `qwebchannel.js`, `THIRD_PARTY.txt` | new | committed bundle, ProseMirror CSS, unmodified Qt client, license notices | 1, rebuilt in 8-11 |
| `mdviewer/core/docschema.py` | new | node/mark names and attrs, `validate(doc)` | 2 |
| `mdviewer/core/frontmatter.py` | new | `split(text)` / `join(front, body)` | 3 |
| `mdviewer/core/urls.py` | new | URL resolution + scheme stripping (extracted from `render.py`) | 4 |
| `mdviewer/core/docmodel.py` | new | Markdown -> document JSON | 4, 5 |
| `mdviewer/core/render.py` | changed | adds `highlight_code(code, lang)`, `editor_page(theme)`; uses `core/urls.py` | 4, 5, 12 |
| `mdviewer/core/serialize.py` | new | document JSON -> normalized Markdown | 6, 7 |
| `web-src/src/schema.js` | new | ProseMirror schema mirroring `docschema` | 8 |
| `web-src/src/nodeviews.js` | new | code block, image, raw HTML frame, double-click on protected nodes | 8 |
| `web-src/src/editor.css` | new | editor styles: lists, code overlay, protected blocks, chips | 8 |
| `web-src/src/bridge.js` | new | QWebChannel glue, Python-facing API | 9 |
| `web-src/src/editor.js` | new | EditorView, commands, keymaps, input rules, tables, paste | 9, 10, 11 |
| `mdviewer/richview.py` | new | `RichView` (QWebEngineView) + `Bridge` (QObject) | 12 |
| `mdviewer/preview.py` | deleted | replaced by `richview.py` | 13 |
| `mdviewer/main_window.py` | changed | modes, `with_buffer`, async lifecycle, seams, Edit routing | 13-17 |
| `mdviewer/toolbar.py` | new | `FormatToolbar`, QPainter glyphs, selection sync | 15 |
| `mdviewer/dialogs.py` | new | `LinkDialog`, `ImageDialog` | 16 |
| `mdviewer/findbar.py` | changed | find-only mode over the web view | 17 |
| `mdviewer/core/settings.py` | changed | `show_toolbar` key | 15 |
| `scripts/smoke_ui.py` | changed | Rendered-mode checks | 12-17 |
| `scripts/build_exe.py` | changed | bundles `mdviewer/web/*` and WebChannel | 18 |
| `README.md`, `CLAUDE.md` | changed | normalization note, shortcuts, manual checklist, rules | 19 |

## Key Interfaces (shared across tasks)

```python
# core/docschema.py
BLOCK_NODES: dict[str, tuple[str, ...]]     # node name -> required attr names
INLINE_NODES: dict[str, tuple[str, ...]]
PROTECTED_NODES: frozenset[str]
MARKS: dict[str, tuple[str, ...]]
LINE_ATTR = "line"                          # optional on TOP_LEVEL_NODES; non-None only under doc
BLOCK_CONTENT: frozenset[str]               # blocks allowed in doc, blockquote, list_item
TOP_LEVEL_NODES: frozenset[str]             # BLOCK_CONTENT | {front_matter, footnote_def}
CONTENT: dict[str, tuple[frozenset[str], int]]   # container -> (allowed children, min count)
def validate(doc: dict) -> list[str]        # "<json path>: <problem>" strings; [] when valid

# core/frontmatter.py
def split(text: str) -> tuple[str | None, str]
def join(front: str | None, body: str) -> str

# core/urls.py
def resolve(url: str, base_dir: Path | None) -> str   # moved from render._Renderer._resolve
def is_safe(url: str) -> bool                          # False for javascript:, vbscript:, non-image data:

# core/render.py (additions)
def highlight_code(code: str, language: str) -> str    # "" when the language is unknown
def editor_page(theme: str) -> str                     # editor.html with theme CSS filled in

# core/docmodel.py
def from_markdown(body: str, front: str | None = None, base_dir: Path | None = None) -> dict

# core/serialize.py
def to_markdown(doc: dict) -> str                      # body only; "" when empty
def front_matter(doc: dict) -> str | None             # the front_matter node's source, verbatim
def to_text(doc: dict) -> str                         # frontmatter.join(front, body): the pulled buffer

# mdviewer/richview.py
class Bridge(QObject):   # JS -> Python signals
    ready, changed, selectionState(dict), openLink(str), hoverLink(str),
    requestLinkDialog(str, str), requestImageDialog(), editProtected(int), caretBlock(int)
class RichView(QWebEngineView):
    def set_document(self, doc: dict, keep_scroll: bool = False) -> None
    def request_document(self, callback: Callable[[dict | None], None]) -> None  # None on timeout
    def command(self, name: str, args=None) -> None
    def set_theme(self, theme: str) -> None
    def focus_block(self, index: int) -> None

# mdviewer/main_window.py (additions)
MainWindow.RENDERED = "rendered"; MainWindow.SOURCE = "source"
def with_buffer(self, fn: Callable[[str], None]) -> None
def run_link_dialog(parent, text: str, url: str) -> tuple[str, str] | str | None   # "remove"
def run_image_dialog(parent, base_dir: Path | None) -> tuple[str, str] | None
```

```js
// JS editor API (window.mdEditor), called from Python via runJavaScript
setDocument(json, keepScroll); getDocument() -> json; command(name, args);
setTheme(css); focusBlock(index)
```

---

## Phase 0 - Foundation

### Task 1: Web toolchain and page-shell spike

Retire risk R1 before anything depends on it. **Status: steps detailed.**

**R1 pre-check (done while writing this plan, 2026-10-20, PySide6 6.12.0,
offscreen):** a `file:` page with the spec CSP ran a `<script src>` from its
own folder, refused an inline `<script>` (console: `Refused to execute inline
script because it violates the following Content Security Policy directive:
"script-src 'self'"`), refused `eval`, and a `QWebChannel` `ready()` call
reached Python. So `'self'` matches the sibling `file:` bundle and **no
`mdviewer:` scheme handler is needed**. This task builds the real pipeline and
a permanent check (`scripts/check_web.py`) that re-proves this on every bundle
rebuild.

**Design decisions (deviations from the outline above, all in this task):**

- `qwebchannel.js` ships as its own **unmodified** file,
  `mdviewer/web/qwebchannel.js`, loaded by a second `<script src>` before
  `editor.js`, rather than concatenated into the bundle. `'self'` covers it
  just the same, and keeping Qt's LGPL file separate and unmodified is the
  simplest way to comply with its license. `build_web.py` copies it from Qt's
  resource `:/qtwebchannel/qwebchannel.js` (readable after
  `from PySide6 import QtWebChannel`; no QApplication needed).
- ProseMirror's required stylesheet (`prosemirror-view/style/prosemirror.css`)
  is imported by `web-src/src/editor.js`; esbuild emits it as
  `mdviewer/web/editor.css`, loaded by `<link rel="stylesheet">`.
- `THIRD_PARTY.txt` is generated by `build.mjs` from esbuild's metafile: every
  npm package that actually ends up in the bundle (including transitive ones
  such as `orderedmap`, `rope-sequence`, `w3c-keyname`) gets its license text.
  The build fails if a bundled package has no license file.
- The offscreen check is permanent, not throwaway: `scripts/check_web.py`
  prints `WEB OK`. Tasks 8-11 run it after every bundle rebuild (before the
  Qt integration in Task 12 exists).
- All twelve ProseMirror packages from spec 6.1 are pinned now, so the lockfile
  is created once; later tasks only add imports and rebuild.

**Files:**
- Create: `tests/test_web_assets.py` (Qt-free static checks on the shipped files)
- Create: `web-src/package.json`, `web-src/package-lock.json` (generated by npm), `web-src/build.mjs`, `web-src/src/editor.js`
- Create: `scripts/build_web.py`, `scripts/check_web.py`
- Create: `mdviewer/web/editor.html` (hand-written template)
- Generate and commit: `mdviewer/web/editor.js`, `mdviewer/web/editor.css`, `mdviewer/web/qwebchannel.js`, `mdviewer/web/THIRD_PARTY.txt`
- Modify: `.gitignore` (add `web-src/node_modules/`)
- Modify: `docs/superpowers/specs/2026-10-20-wysiwyg-editing-design.md` (sections 5, 6.1, 10: record the R1 verdict and the extra files)

**Interfaces:**
- Consumes: `mdviewer.core.render.page_css(theme: str) -> str` and
  `render.PAGE_BACKGROUND: dict[str, str]` (existing v1 code, used only by
  `check_web.py` to fill the theme slot).
- Produces (later tasks rely on these exact names):
  - `mdviewer/web/editor.html`: page template. Its only placeholder is the
    literal token `/*@THEME_CSS@*/` inside `<style id="theme">`; Task 12's
    `render.editor_page(theme)` replaces it with `render.page_css(theme)`.
    The editor mounts into `<article class="markdown-body" id="editor">`.
  - Runtime files that must sit next to the filled-in page (Task 12's
    `RichView` copies them into its temp dir; Task 18 bundles them):
    `editor.js`, `editor.css`, `qwebchannel.js`.
  - QWebChannel contract: Python registers one object under the name
    **`"bridge"`**; the bundle calls `bridge.ready()` exactly once after the
    channel connects.
  - `window.mdEditor.getDocument()` returns the ProseMirror document JSON
    (minimal one-paragraph schema in this task; Task 9 replaces the API).
  - `scripts/build_web.py` (rebuild everything in `mdviewer/web/` except
    `editor.html`) and `scripts/check_web.py` (prints `WEB OK`).

- [x] **Step 1: Write the failing static test**

Create `tests/test_web_assets.py`:

```python
"""Static checks on the shipped web editor files.

No Qt here (tests/ must stay Qt-free); scripts/check_web.py loads the page for real.
"""

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
```

- [x] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_web_assets.py -v`
Expected: every test FAILs (`FileNotFoundError` for `mdviewer/web/...`;
`test_node_modules_is_git_ignored` fails on the assert).

- [x] **Step 3: Ignore `node_modules` and create `web-src/package.json`**

Append to `.gitignore`:

```
web-src/node_modules/
```

Create `web-src/package.json`:

```json
{
  "name": "mdviewer-web",
  "version": "0.0.0",
  "private": true,
  "description": "Sources of mdviewer/web/editor.js. Rebuild with: python scripts/build_web.py",
  "engines": {
    "node": ">=20"
  },
  "scripts": {
    "build": "node build.mjs"
  }
}
```

- [x] **Step 4: Pin the dependencies (creates `package-lock.json`)**

Needs Node.js >= 20 with npm on PATH, and network access. Run in Git Bash:

```bash
cd web-src && npm install --save-exact prosemirror-model prosemirror-state prosemirror-view prosemirror-transform prosemirror-commands prosemirror-keymap prosemirror-history prosemirror-schema-list prosemirror-tables prosemirror-inputrules prosemirror-dropcursor prosemirror-gapcursor && npm install --save-exact --save-dev esbuild; cd ..
```

Expected: `web-src/package.json` gains `dependencies` (twelve exact
versions, no `^`) and `devDependencies.esbuild`; `web-src/package-lock.json`
exists; `git status --short` does **not** list `web-src/node_modules/`.

- [x] **Step 5: Write the minimal editor source**

Create `web-src/src/editor.js`:

```js
// Minimal Phase 0 editor: proves the bundle loads under the page CSP and talks
// to Python over QWebChannel. Task 8 replaces the schema; Task 9 the API.
/* global QWebChannel, qt */
import "prosemirror-view/style/prosemirror.css";
import { Schema } from "prosemirror-model";
import { EditorState } from "prosemirror-state";
import { EditorView } from "prosemirror-view";

const schema = new Schema({
  nodes: {
    doc: { content: "paragraph+" },
    paragraph: { content: "text*", toDOM: () => ["p", 0], parseDOM: [{ tag: "p" }] },
    text: {},
  },
});

const view = new EditorView(document.getElementById("editor"), {
  state: EditorState.create({ schema }),
});

window.mdEditor = {
  getDocument: () => view.state.doc.toJSON(),
};

// qwebchannel.js is loaded by its own <script> before this bundle.
new QWebChannel(qt.webChannelTransport, (channel) => {
  channel.objects.bridge.ready();
});
```

- [x] **Step 6: Write the esbuild config**

Create `web-src/build.mjs`:

```js
// Bundles src/editor.js into ../mdviewer/web/editor.js (+ editor.css) and writes
// THIRD_PARTY.txt for every npm package that ends up in the bundle.
// Run through scripts/build_web.py, which also runs `npm ci` and copies qwebchannel.js.
import { build } from "esbuild";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const out = join(here, "..", "mdviewer", "web");

const result = await build({
  absWorkingDir: here,
  entryPoints: ["src/editor.js"],
  bundle: true,
  format: "iife",
  target: "chrome108", // Chromium of Qt 6.5, the oldest supported Qt
  minify: true,
  legalComments: "none", // notices go to THIRD_PARTY.txt instead
  charset: "utf8",
  outfile: join(out, "editor.js"),
  metafile: true,
  logLevel: "info",
});

const LICENSE_FILES = ["LICENSE", "LICENSE.md", "LICENSE.txt", "license", "license.md"];
const packages = new Set();
for (const input of Object.keys(result.metafile.inputs)) {
  const match = input.replace(/\\/g, "/").match(/node_modules\/((?:@[^/]+\/)?[^/]+)\//);
  if (match) packages.add(match[1]);
}
const sections = [...packages].sort().map((name) => {
  const dir = join(here, "node_modules", name);
  const meta = JSON.parse(readFileSync(join(dir, "package.json"), "utf8"));
  const file = LICENSE_FILES.map((f) => join(dir, f)).find((p) => existsSync(p));
  if (!file) throw new Error(`${name}: no license file found; add its notice by hand`);
  const text = readFileSync(file, "utf8").replace(/\r\n/g, "\n").trim();
  return `==== ${name} ${meta.version} (${meta.license}) ====\n\n${text}\n`;
});
const header =
  "Third-party software in mdviewer/web/editor.js and editor.css.\n" +
  "Generated by web-src/build.mjs; do not edit by hand.\n\n" +
  "qwebchannel.js is Qt WebChannel's client script, copied unmodified from PySide6\n" +
  "by scripts/build_web.py; its copyright and license header are kept in the file.\n";
writeFileSync(join(out, "THIRD_PARTY.txt"), [header, ...sections].join("\n"), "utf8");
console.log(`THIRD_PARTY.txt: ${packages.size} packages`);
```

- [x] **Step 7: Write the page shell template**

Create `mdviewer/web/editor.html` (exact content; the CSP is spec section 5
verbatim):

```html
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src file: data: https: http:; frame-src 'self' about:; child-src 'self'">
<link rel="stylesheet" href="editor.css">
<style id="theme">/*@THEME_CSS@*/</style>
</head>
<body>
<article class="markdown-body" id="editor"></article>
<script src="qwebchannel.js"></script>
<script src="editor.js"></script>
</body>
</html>
```

- [x] **Step 8: Write the rebuild script**

Create `scripts/build_web.py`:

```python
"""Rebuild the web editor runtime files in mdviewer/web/ from web-src/.

Run from anywhere:  .venv\\Scripts\\python scripts\\build_web.py
Needs Node.js >= 20 with npm on PATH. Outputs (all committed): editor.js, editor.css,
THIRD_PARTY.txt (esbuild, web-src/build.mjs) and qwebchannel.js (copied from PySide6).
Normal development, tests and packaging use the committed files; run this only after
changing web-src/, then run scripts/check_web.py.
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB_SRC = ROOT / "web-src"
WEB_OUT = ROOT / "mdviewer" / "web"
OUTPUTS = ("editor.js", "editor.css", "qwebchannel.js", "THIRD_PARTY.txt")
QWEBCHANNEL_RESOURCE = ":/qtwebchannel/qwebchannel.js"


def copy_qwebchannel() -> None:
    """Ship Qt's client unmodified next to the bundle, so CSP script-src 'self' covers it."""
    from PySide6 import QtWebChannel  # noqa: F401  registers the :/qtwebchannel resources
    from PySide6.QtCore import QFile, QIODevice

    resource = QFile(QWEBCHANNEL_RESOURCE)
    if not resource.open(QIODevice.OpenModeFlag.ReadOnly):
        raise RuntimeError(f"cannot read {QWEBCHANNEL_RESOURCE} from PySide6")
    try:
        (WEB_OUT / "qwebchannel.js").write_bytes(bytes(resource.readAll()))
    finally:
        resource.close()


def main() -> int:
    npm = shutil.which("npm")
    if npm is None:
        print("npm not found. Install Node.js 20 or later and retry.", file=sys.stderr)
        return 1
    for args in (["ci"], ["run", "build"]):
        print("Running: npm", " ".join(args))
        result = subprocess.run([npm, *args], cwd=WEB_SRC)
        if result.returncode != 0:
            return result.returncode
    copy_qwebchannel()
    missing = [name for name in OUTPUTS if not (WEB_OUT / name).is_file()]
    if missing:
        print(f"Build finished but did not produce: {', '.join(missing)}", file=sys.stderr)
        return 1
    print(f"\nBuilt {WEB_OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [x] **Step 9: Build the bundle**

Run: `.venv/Scripts/python scripts/build_web.py`
Expected: npm ci output, esbuild's size report for `editor.js` and
`editor.css`, `THIRD_PARTY.txt: N packages` (N >= 5: at least
`orderedmap`, `prosemirror-model`, `prosemirror-state`,
`prosemirror-transform`, `prosemirror-view`), and
`Built ...\mdviewer\web`. Exit code 0.

- [x] **Step 10: Run the static tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_web_assets.py -v`
Expected: 9 passed.

- [x] **Step 11: Write the offscreen page check**

Create `scripts/check_web.py`:

```python
"""Offscreen check of the committed web editor: page shell, bundle, QWebChannel, CSP.

Run: .venv\\Scripts\\python scripts\\check_web.py  ->  prints WEB OK or the failed checks.
Loads mdviewer/web/editor.html from a temp folder (as RichView will), with an inline
<script> probe added: the CSP must block the probe while the external scripts run.
Run it after every scripts/build_web.py.
"""

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QEventLoop, QObject, QUrl, Slot  # noqa: E402
from PySide6.QtWebChannel import QWebChannel  # noqa: E402
from PySide6.QtWebEngineCore import QWebEnginePage  # noqa: E402
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from mdviewer.core import render  # noqa: E402

WEB = Path(__file__).resolve().parent.parent / "mdviewer" / "web"
RUNTIME_FILES = ("editor.js", "editor.css", "qwebchannel.js")
THEME_SLOT = "/*@THEME_CSS@*/"
FIRST_SCRIPT = '<script src="qwebchannel.js"></script>'
INLINE_PROBE = "<script>window.inlineScriptRan = true;</script>"
READY_TIMEOUT_S = 5  # spec: page ready() timeout
FAILURES: list[str] = []


def check(condition, label: str) -> None:
    if not condition:
        FAILURES.append(label)


class Bridge(QObject):
    def __init__(self):
        super().__init__()
        self.ready_calls = 0

    @Slot()
    def ready(self) -> None:
        self.ready_calls += 1


class Page(QWebEnginePage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.console: list[str] = []

    def javaScriptConsoleMessage(self, level, message, line, source) -> None:
        self.console.append(message)


def pump(app: QApplication, predicate, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while not predicate() and time.monotonic() < deadline:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
    return bool(predicate())


def run_js(app: QApplication, view: QWebEngineView, script: str):
    """Evaluates `script` in the page's main world; the value must be JSON-serializable."""
    box: list = []
    view.page().runJavaScript(f"JSON.stringify({script})", 0, box.append)
    pump(app, lambda: box, 3)
    return json.loads(box[0]) if box and box[0] is not None else None


def build_page(folder: Path) -> Path:
    for name in RUNTIME_FILES:
        shutil.copy2(WEB / name, folder / name)
    shell = (WEB / "editor.html").read_text(encoding="utf-8")
    check(shell.count(THEME_SLOT) == 1 and shell.count(FIRST_SCRIPT) == 1, "editor.html has the expected slots")
    shell = shell.replace(THEME_SLOT, render.page_css("light"))
    shell = shell.replace(FIRST_SCRIPT, INLINE_PROBE + FIRST_SCRIPT)
    page_file = folder / "editor.html"
    page_file.write_text(shell, encoding="utf-8")
    return page_file


def main() -> int:
    app = QApplication([])
    folder = Path(tempfile.mkdtemp(prefix="mdviewer-webcheck-"))
    view = QWebEngineView()
    page = Page(view)
    view.setPage(page)
    channel = QWebChannel(page)
    bridge = Bridge()
    channel.registerObject("bridge", bridge)
    page.setWebChannel(channel)

    view.load(QUrl.fromLocalFile(str(build_page(folder))))
    check(pump(app, lambda: bridge.ready_calls > 0, READY_TIMEOUT_S), "bridge.ready() received within 5 s")
    pump(app, lambda: False, 0.3)  # a duplicate ready() would arrive by now
    check(bridge.ready_calls == 1, f"ready() called exactly once (got {bridge.ready_calls})")

    check(run_js(app, view, "window.inlineScriptRan === true") is False, "CSP blocks the inline <script>")
    check(
        any("Content Security Policy" in message for message in page.console),
        "the inline <script> was refused by the CSP (console message)",
    )
    check(
        run_js(app, view, "document.querySelector('#editor .ProseMirror').contentEditable") == "true",
        "ProseMirror is mounted and editable",
    )
    check(
        run_js(app, view, "getComputedStyle(document.querySelector('.ProseMirror')).whiteSpace")
        in ("pre-wrap", "break-spaces"),
        "editor.css is loaded",
    )
    background = run_js(app, view, "getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()")
    check(
        (background or "").lower() == render.PAGE_BACKGROUND["light"].lower(),
        f"theme CSS filled into the slot (--bg = {background!r})",
    )
    doc = run_js(app, view, "window.mdEditor.getDocument()")
    check(isinstance(doc, dict) and doc.get("type") == "doc", f"mdEditor.getDocument() returns a doc ({doc!r})")

    console = list(page.console)
    del page, view  # the page is the view's child; release both before removing the folder
    shutil.rmtree(folder, ignore_errors=True)
    if FAILURES:
        print("WEB CHECK FAILED:")
        for label in FAILURES:
            print("  -", label)
        for message in console:
            print("  console:", message)
        return 1
    print("WEB OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [x] **Step 12: Run the page check**

Run: `.venv/Scripts/python scripts/check_web.py`
Expected: `WEB OK`, exit code 0.

If it fails **only** on the two CSP checks or the `ready()` check, R1 has
regressed relative to the pre-check above (for example a different Qt
version). Stop and report the full output; do not add a scheme handler
without a decision from the user.

- [x] **Step 13: Confirm the build is reproducible**

Hash the outputs, rebuild, and compare:

```bash
sha256sum mdviewer/web/* > /tmp/web1.txt && .venv/Scripts/python scripts/build_web.py > /dev/null && sha256sum mdviewer/web/* | diff /tmp/web1.txt - && echo REPRODUCIBLE
```

Expected: `REPRODUCIBLE`.

- [x] **Step 14: Record the R1 verdict in the spec**

In `docs/superpowers/specs/2026-10-20-wysiwyg-editing-design.md`:

Section 5, item 2, replace

```
   No inline scripts, no `eval`. (Risk R1: verify `'self'` matches the
   bundle's `file:` URL; fallback is serving page and bundle from a custom
   `mdviewer:` scheme via `QWebEngineUrlSchemeHandler`.)
```

with

```
   No inline scripts, no `eval`. `'self'` matches the bundle and
   `qwebchannel.js` loaded from the page's own `file:` folder (R1, retired;
   re-checked by `scripts/check_web.py`).
```

Section 6.1, replace

```
    editor.js            esbuild bundle: ProseMirror + our code (~200 KB)
    editor.html          page shell template (CSP, CSS slot, bundle reference)
    THIRD_PARTY.txt      ProseMirror MIT license notices
```

with

```
    editor.js            esbuild bundle: ProseMirror + our code (~200 KB)
    editor.css           ProseMirror's required stylesheet (esbuild output)
    qwebchannel.js       Qt WebChannel client, copied unmodified from PySide6
    editor.html          page shell template (CSP, CSS slot, script references)
    THIRD_PARTY.txt      license notices of the bundled npm packages
```

and replace

```
scripts/build_web.py NEW  npm ci + esbuild -> mdviewer/web/editor.js
```

with

```
scripts/build_web.py NEW  npm ci + esbuild -> mdviewer/web/*, copies qwebchannel.js
scripts/check_web.py NEW  offscreen load of the shell: ready(), CSP blocks inline scripts
```

Section 10, replace

```
1. **CSP `'self'` on `file:` pages** - day-1 spike; fallback custom
   `mdviewer:` scheme handler.
```

with

```
1. **CSP `'self'` on `file:` pages** - retired 2026-10-20 (PySide6 6.12.0,
   offscreen): scripts loaded from the page's own folder run, inline scripts
   and `eval` are refused, QWebChannel connects. No custom scheme is needed;
   `scripts/check_web.py` re-verifies this after every bundle rebuild.
```

- [x] **Step 15: Run the full verification**

Run:

```bash
.venv/Scripts/python -m pytest -v
.venv/Scripts/python scripts/smoke_ui.py
.venv/Scripts/python scripts/check_web.py
rg -n "import (PySide|Qt)|from PySide" mdviewer/core tests
```

Expected: all tests pass; `SMOKE OK` (v1 behavior untouched: nothing imports
`mdviewer/web` yet); `WEB OK`; the `rg` line prints nothing.

- [x] **Step 16: Commit**

```bash
git add .gitignore web-src/package.json web-src/package-lock.json web-src/build.mjs web-src/src/editor.js scripts/build_web.py scripts/check_web.py mdviewer/web tests/test_web_assets.py docs/superpowers/specs/2026-10-20-wysiwyg-editing-design.md
git status --short   # must not list web-src/node_modules
git commit -m "chore: add web editor toolchain and CSP-checked page shell"
```

**Review Focus:**

- `editor.html` contains no inline script and no `on*=` attribute; the CSP
  string equals spec section 5 character for character.
- `qwebchannel.js` is byte-identical to Qt's resource (no reformatting, header
  kept); `THIRD_PARTY.txt` lists every package esbuild bundled, including
  transitive ones.
- `package.json` versions are exact (no `^`/`~`); `node_modules` is not
  committed; a second build changes no bytes.
- Nothing in `mdviewer/` imports `mdviewer/web` yet, so v1 behavior and the
  smoke test are unchanged; `tests/test_web_assets.py` imports no Qt.
- `check_web.py` fails loudly (non-zero exit, console dump) when `ready()`
  never arrives instead of hanging.

## Phase 1 - Python document model (pure, TDD)

### Task 2: Document schema contract

**Status: steps detailed.** The module and tests below were run before being
written into this plan (56 passed).

**Design decisions (pinned here; Tasks 4-8 rely on them):**

- **Attr tuples list required attrs.** A node must carry every listed attr
  and nothing else, except the transient `line`.
- **`line`** (1-based source start line, or `None`) is an optional attr of
  the node types that may sit directly in `doc` (`TOP_LEVEL_NODES`). It may be
  non-`None` only on direct children of `doc`. Nested nodes of those types may
  carry `line: None`, because ProseMirror's `toJSON()` writes every declared
  attr. Task 8 declares `line` (default `null`) on exactly these node types.
- **Content rules** (`CONTENT`) mirror what the JS schema enforces:
  - `doc`: blocks plus `front_matter` (first child only) and `footnote_def`
  - `blockquote` and `list_item`: one or more blocks. A list item may start
    with a code block, so there is no `paragraph block*` rule.
  - lists: `list_item+`
  - `table` > `table_row+` > (`table_header` | `table_cell`)+
  - cells, `paragraph` and `heading`: inline content
  - `code_block`: unmarked text only
  - everything else is a leaf
- **Marks are allowed on any inline node**, not only text. This differs from
  the outline's "mark on a non-text node" test: linked images such as README
  badges (`[![ci](badge.svg)](url)`) need a `link` mark on `image`. Marks are
  rejected on block nodes and inside `code_block`, and a mark type may appear
  only once per node.
- **Attr value checks:**
  - `level`: 1-6
  - `start`: integer >= 0
  - `tight`: bool
  - `checked`: `None` or bool
  - `align`: `None`, `left`, `center` or `right`
  - `title`: `None` or str
  - `label`: non-empty str
  - all other attrs (`language`, `highlight`, `src`, `display_src`, `alt`,
    `href`, `source`): str. `language` is `""` when absent, never `None`.
- **Problems** are strings `"<JSON path>: <message>"` (paths like
  `$.content[2].marks[0]`), listed in document order. All problems are
  collected; validation does not stop at the first one.

**Files:**
- Create: `mdviewer/core/docschema.py`
- Test: `tests/test_docschema.py`

**Interfaces:**
- Consumes: nothing (pure module, no Qt, no other `mdviewer` imports).
- Produces:
  - `BLOCK_NODES: dict[str, tuple[str, ...]]`: block node name -> required attrs
  - `INLINE_NODES: dict[str, tuple[str, ...]]`: inline node name -> required attrs
  - `MARKS: dict[str, tuple[str, ...]]`: mark name -> required attrs
  - `PROTECTED_NODES: frozenset[str]`
  - `LINE_ATTR = "line"`
  - `BLOCK_CONTENT: frozenset[str]`: blocks allowed in `doc`, `blockquote`
    and `list_item`
  - `TOP_LEVEL_NODES: frozenset[str]`: `BLOCK_CONTENT` plus `front_matter`
    and `footnote_def`; these accept `line`
  - `CONTENT: dict[str, tuple[frozenset[str], int]]`: container -> (allowed
    child types, minimum children). Nodes missing from it are leaves.
  - `validate(doc: dict) -> list[str]`: `[]` when valid
  - Tasks 4-5 assert `validate(from_markdown(...)) == []`. Task 7 validates
    every corpus document. Task 8 parses `web-src/src/schema.js` and compares
    its names and attrs with these tables (`line` excluded).

- [x] **Step 1: Write the failing tests**

Create `tests/test_docschema.py`:

```python
import pytest

from mdviewer.core.docschema import (
    BLOCK_CONTENT,
    BLOCK_NODES,
    CONTENT,
    INLINE_NODES,
    LINE_ATTR,
    MARKS,
    PROTECTED_NODES,
    TOP_LEVEL_NODES,
    validate,
)


def t(text, *marks):
    node = {"type": "text", "text": text}
    if marks:
        node["marks"] = list(marks)
    return node


def p(*inline):
    node = {"type": "paragraph"}
    if inline:
        node["content"] = list(inline)
    return node


def item(*blocks, checked=None):
    return {"type": "list_item", "attrs": {"checked": checked}, "content": list(blocks) or [p(t("x"))]}


def doc(*blocks):
    return {"type": "doc", "content": list(blocks)}


def link(href="https://example.com", title=None):
    return {"type": "link", "attrs": {"href": href, "title": title}}


def every_node_doc():
    """One document using every node type and mark, shaped like ProseMirror's toJSON()."""
    return doc(
        {"type": "front_matter", "attrs": {"source": "---\ntitle: x\n---\n", "line": 1}},
        {"type": "heading", "attrs": {"level": 1, "line": 5}, "content": [t("Title")]},
        {"type": "paragraph", "attrs": {"line": 7}, "content": [
            t("bold", {"type": "strong"}),
            t("it", {"type": "em"}),
            t("gone", {"type": "strike"}),
            t("x()", {"type": "code"}),
            t("link", link()),
            {"type": "hard_break"},
            {"type": "image",
             "attrs": {"src": "a.png", "display_src": "file:///C:/d/a.png", "alt": "A", "title": None},
             "marks": [link("https://ci.example/badge", "Build")]},
            {"type": "footnote_ref", "attrs": {"label": "1"}},
            {"type": "html_inline", "attrs": {"source": "<kbd>"}},
        ]},
        {"type": "blockquote", "attrs": {"line": 9}, "content": [
            {"type": "paragraph", "attrs": {"line": None}, "content": [t("quoted")]},
        ]},
        {"type": "bullet_list", "attrs": {"tight": True, "line": 11}, "content": [
            item(p(t("one"))),
            item(p(t("done")), {"type": "ordered_list", "attrs": {"start": 3, "tight": False},
                                "content": [item(p(t("nested")), checked=False)]}, checked=True),
        ]},
        {"type": "code_block",
         "attrs": {"language": "python", "highlight": '<span class="k">pass</span>', "line": 15},
         "content": [t("pass")]},
        {"type": "horizontal_rule", "attrs": {"line": 18}},
        {"type": "table", "attrs": {"line": 20}, "content": [
            {"type": "table_row", "content": [
                {"type": "table_header", "attrs": {"align": "left"}, "content": [t("h")]},
                {"type": "table_header", "attrs": {"align": None}},
            ]},
            {"type": "table_row", "content": [
                {"type": "table_cell", "attrs": {"align": "right"}, "content": [t("c")]},
                {"type": "table_cell", "attrs": {"align": "center"}},
            ]},
        ]},
        {"type": "html_block", "attrs": {"source": "<div>x</div>\n", "line": 24}},
        {"type": "footnote_def", "attrs": {"label": "1", "source": "[^1]: note\n", "line": 26}},
    )


def collect_types(node, nodes, marks):
    nodes.add(node["type"])
    for mark in node.get("marks", []):
        marks.add(mark["type"])
    for child in node.get("content", []):
        collect_types(child, nodes, marks)


# --- name tables -------------------------------------------------------------

def test_block_node_names_and_attrs_match_spec():
    assert BLOCK_NODES == {
        "doc": (),
        "paragraph": (),
        "heading": ("level",),
        "blockquote": (),
        "bullet_list": ("tight",),
        "ordered_list": ("start", "tight"),
        "list_item": ("checked",),
        "code_block": ("language", "highlight"),
        "horizontal_rule": (),
        "table": (),
        "table_row": (),
        "table_header": ("align",),
        "table_cell": ("align",),
        "front_matter": ("source",),
        "html_block": ("source",),
        "footnote_def": ("label", "source"),
    }


def test_inline_node_names_and_attrs_match_spec():
    assert INLINE_NODES == {
        "text": (),
        "hard_break": (),
        "image": ("src", "display_src", "alt", "title"),
        "footnote_ref": ("label",),
        "html_inline": ("source",),
    }


def test_marks_match_spec():
    assert MARKS == {"strong": (), "em": (), "strike": (), "code": (), "link": ("href", "title")}


def test_protected_nodes_match_spec():
    assert PROTECTED_NODES == {"front_matter", "html_block", "footnote_def", "footnote_ref", "html_inline"}
    assert PROTECTED_NODES <= set(BLOCK_NODES) | set(INLINE_NODES)


def test_name_tables_do_not_overlap():
    assert not set(BLOCK_NODES) & set(INLINE_NODES)
    assert not (set(BLOCK_NODES) | set(INLINE_NODES)) & set(MARKS)


def test_content_rules_only_name_known_nodes():
    known = set(BLOCK_NODES) | set(INLINE_NODES)
    assert set(CONTENT) <= set(BLOCK_NODES)
    for allowed, minimum in CONTENT.values():
        assert allowed <= known
        assert minimum in (0, 1)
    assert BLOCK_CONTENT < TOP_LEVEL_NODES <= set(BLOCK_NODES)
    assert LINE_ATTR == "line"


# --- valid documents ----------------------------------------------------------

def test_every_node_doc_uses_every_name():
    nodes, marks = set(), set()
    collect_types(every_node_doc(), nodes, marks)
    assert nodes == set(BLOCK_NODES) | set(INLINE_NODES)
    assert marks == set(MARKS)


def test_every_node_doc_is_valid():
    assert validate(every_node_doc()) == []


def test_empty_paragraph_doc_is_valid():
    assert validate(doc(p())) == []


def test_marks_on_inline_non_text_nodes_are_valid():
    image = {"type": "image", "attrs": {"src": "b.svg", "display_src": "b.svg", "alt": "", "title": None},
             "marks": [link()]}
    assert validate(doc(p(image, {"type": "hard_break", "marks": [{"type": "em"}]}))) == []


def test_line_may_be_none_on_nested_blocks():
    assert validate(doc({"type": "blockquote", "content": [
        {"type": "paragraph", "attrs": {"line": None}, "content": [t("x")]},
    ]})) == []


# --- rejected documents -------------------------------------------------------

@pytest.mark.parametrize("root", [None, [], {}, {"type": "paragraph"}, {"type": 3}])
def test_root_must_be_doc(root):
    assert validate(root) == ["$: root must be a doc node"]


def test_unknown_node_type():
    assert validate(doc(p(t("a")), {"type": "callout"})) == ["$.content[1]: unknown node type 'callout'"]


def test_non_object_child():
    assert validate(doc("text")) == ["$.content[0]: not a node object"]


def test_unknown_mark_type():
    assert validate(doc(p(t("a", {"type": "bold"})))) == [
        "$.content[0].content[0].marks[0]: unknown mark type 'bold'"
    ]


def test_duplicate_mark():
    assert validate(doc(p(t("a", {"type": "em"}, {"type": "em"})))) == [
        "$.content[0].content[0].marks[1]: duplicate mark 'em'"
    ]


def test_missing_node_attr():
    assert validate(doc({"type": "heading", "content": [t("x")]})) == [
        "$.content[0]: heading is missing attr 'level'"
    ]


def test_missing_mark_attr():
    assert validate(doc(p(t("a", {"type": "link", "attrs": {"href": "x"}})))) == [
        "$.content[0].content[0].marks[0]: mark link is missing attr 'title'"
    ]


def test_unknown_attr():
    assert validate(doc({"type": "paragraph", "attrs": {"align": "left"}})) == [
        "$.content[0]: paragraph has unknown attr 'align'"
    ]


def test_line_is_unknown_on_nodes_that_are_never_top_level():
    assert validate(doc({"type": "bullet_list", "attrs": {"tight": True}, "content": [
        {"type": "list_item", "attrs": {"checked": None, "line": None}, "content": [p()]},
    ]})) == ["$.content[0].content[0]: list_item has unknown attr 'line'"]


def test_attrs_must_be_an_object():
    assert validate(doc({"type": "paragraph", "attrs": []})) == ["$.content[0]: attrs must be an object"]


@pytest.mark.parametrize("block, message", [
    ({"type": "heading", "attrs": {"level": 7}}, "heading.level has invalid value 7"),
    ({"type": "heading", "attrs": {"level": True}}, "heading.level has invalid value True"),
    ({"type": "bullet_list", "attrs": {"tight": "yes"}, "content": [item()]},
     "bullet_list.tight has invalid value 'yes'"),
    ({"type": "ordered_list", "attrs": {"start": -1, "tight": True}, "content": [item()]},
     "ordered_list.start has invalid value -1"),
    ({"type": "code_block", "attrs": {"language": None, "highlight": ""}},
     "code_block.language has invalid value None"),
    ({"type": "html_block", "attrs": {"source": "<br>", "line": 0}}, "html_block.line has invalid value 0"),
    ({"type": "footnote_def", "attrs": {"label": "", "source": "[^]: x"}},
     "footnote_def.label has invalid value ''"),
])
def test_invalid_top_level_attr_values(block, message):
    assert validate(doc(block)) == [f"$.content[0]: {message}"]


def test_invalid_nested_attr_values():
    cell = {"type": "table_cell", "attrs": {"align": "justify"}}
    image = {"type": "image", "attrs": {"src": "a", "display_src": "a", "alt": "", "title": 5}}
    assert validate(doc(
        {"type": "table", "content": [{"type": "table_row", "content": [cell]}]},
        {"type": "bullet_list", "attrs": {"tight": True}, "content": [item(checked="x")]},
        p(image, t("a", link(href=None))),
    )) == [
        "$.content[0].content[0].content[0]: table_cell.align has invalid value 'justify'",
        "$.content[1].content[0]: list_item.checked has invalid value 'x'",
        "$.content[2].content[0]: image.title has invalid value 5",
        "$.content[2].content[1].marks[0]: mark link.href has invalid value None",
    ]


def test_line_only_on_top_level_blocks():
    assert validate(doc({"type": "blockquote", "content": [
        {"type": "paragraph", "attrs": {"line": 3}, "content": [t("x")]},
    ]})) == ["$.content[0].content[0]: line is only allowed on top-level blocks"]


@pytest.mark.parametrize("node", [{"type": "text"}, {"type": "text", "text": ""}, {"type": "text", "text": 5}])
def test_text_node_needs_text(node):
    assert validate(doc(p(node))) == ["$.content[0].content[0]: text node needs a non-empty 'text' string"]


def test_only_text_nodes_have_text():
    assert validate(doc({"type": "paragraph", "text": "a"})) == ["$.content[0]: only text nodes have 'text'"]


def test_block_nodes_cannot_have_marks():
    assert validate(doc({"type": "paragraph", "marks": [{"type": "strong"}], "content": [t("a")]})) == [
        "$.content[0]: paragraph cannot have marks"
    ]


def test_marks_must_be_a_list():
    assert validate(doc(p({"type": "text", "text": "a", "marks": {"type": "em"}}))) == [
        "$.content[0].content[0]: marks must be a list"
    ]


def test_no_marks_inside_code_block():
    code = {"type": "code_block", "attrs": {"language": "", "highlight": ""},
            "content": [t("x", {"type": "strong"})]}
    assert validate(doc(code)) == ["$.content[0].content[0]: marks are not allowed inside code_block"]


@pytest.mark.parametrize("block, message", [
    (p(p(t("a"))), "$.content[0].content[0]: paragraph is not allowed in paragraph"),
    ({"type": "heading", "attrs": {"level": 2}, "content": [{"type": "horizontal_rule"}]},
     "$.content[0].content[0]: horizontal_rule is not allowed in heading"),
    ({"type": "bullet_list", "attrs": {"tight": True}, "content": [p(t("a"))]},
     "$.content[0].content[0]: paragraph is not allowed in bullet_list"),
    ({"type": "code_block", "attrs": {"language": "", "highlight": ""}, "content": [{"type": "hard_break"}]},
     "$.content[0].content[0]: hard_break is not allowed in code_block"),
    ({"type": "blockquote", "content": [{"type": "footnote_def", "attrs": {"label": "1", "source": "x"}}]},
     "$.content[0].content[0]: footnote_def is not allowed in blockquote"),
    ({"type": "table", "content": [{"type": "table_cell", "attrs": {"align": None}}]},
     "$.content[0].content[0]: table_cell is not allowed in table"),
])
def test_child_not_allowed_in_parent(block, message):
    assert validate(doc(block)) == [message]


def test_inline_node_at_top_level():
    assert validate(doc(t("a"))) == ["$.content[0]: text is not allowed in doc"]


@pytest.mark.parametrize("block", [
    {"type": "blockquote"},
    {"type": "bullet_list", "attrs": {"tight": True}, "content": []},
    {"type": "table", "content": [{"type": "table_row"}]},
])
def test_containers_need_children(block):
    problems = validate(doc(block))
    assert len(problems) == 1 and problems[0].endswith("needs at least one child")


def test_doc_needs_a_child():
    assert validate({"type": "doc"}) == ["$: doc needs at least one child"]


def test_leaves_cannot_have_content():
    image = {"type": "image", "attrs": {"src": "a", "display_src": "a", "alt": "", "title": None},
             "content": [t("x")]}
    assert validate(doc({"type": "horizontal_rule", "content": []}, p(image))) == [
        "$.content[0]: horizontal_rule is a leaf and cannot have content",
        "$.content[1].content[0]: image is a leaf and cannot have content",
    ]


def test_content_must_be_a_list():
    assert validate(doc({"type": "paragraph", "content": "a"})) == ["$.content[0]: content must be a list"]


def test_front_matter_only_first_in_doc():
    front = {"type": "front_matter", "attrs": {"source": "---\na: 1\n---\n"}}
    assert validate(doc(p(t("a")), front)) == ["$.content[1]: front_matter must be the first child of doc"]
    assert validate(doc({"type": "blockquote", "content": [front]})) == [
        "$.content[0].content[0]: front_matter is not allowed in blockquote"
    ]


def test_reports_every_problem_in_document_order():
    bad = doc({"type": "heading", "attrs": {"level": 9}, "content": [t("x", {"type": "bold"})]}, {"type": "x"})
    assert validate(bad) == [
        "$.content[0]: heading.level has invalid value 9",
        "$.content[0].content[0].marks[0]: unknown mark type 'bold'",
        "$.content[1]: unknown node type 'x'",
    ]
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_docschema.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'mdviewer.core.docschema'`.

- [x] **Step 3: Write the implementation**

Create `mdviewer/core/docschema.py`:

```python
"""Document contract for the Rendered editor (spec 6.3).

ProseMirror JSON nodes look like {"type", "attrs", "content", "marks", "text"}.
core/docmodel.py produces documents, core/serialize.py consumes them, and
web-src/src/schema.js declares the same names, attrs and content rules: change
both files together and rebuild the bundle (scripts/build_web.py).

The attr tuples list required attrs. Top-level blocks (TOP_LEVEL_NODES) also
accept the transient LINE_ATTR (1-based source start line, or None); it is
non-None only on direct children of doc and the serializer ignores it.
"""

from collections.abc import Callable

BLOCK_NODES: dict[str, tuple[str, ...]] = {
    "doc": (),
    "paragraph": (),
    "heading": ("level",),
    "blockquote": (),
    "bullet_list": ("tight",),
    "ordered_list": ("start", "tight"),
    "list_item": ("checked",),
    "code_block": ("language", "highlight"),
    "horizontal_rule": (),
    "table": (),
    "table_row": (),
    "table_header": ("align",),
    "table_cell": ("align",),
    "front_matter": ("source",),
    "html_block": ("source",),
    "footnote_def": ("label", "source"),
}
INLINE_NODES: dict[str, tuple[str, ...]] = {
    "text": (),
    "hard_break": (),
    "image": ("src", "display_src", "alt", "title"),
    "footnote_ref": ("label",),
    "html_inline": ("source",),
}
PROTECTED_NODES = frozenset({"front_matter", "html_block", "footnote_def", "footnote_ref", "html_inline"})
MARKS: dict[str, tuple[str, ...]] = {
    "strong": (),
    "em": (),
    "strike": (),
    "code": (),
    "link": ("href", "title"),
}
LINE_ATTR = "line"

# Blocks allowed wherever block content goes: doc, blockquote, list_item.
BLOCK_CONTENT = frozenset({
    "paragraph", "heading", "blockquote", "bullet_list", "ordered_list",
    "code_block", "horizontal_rule", "table", "html_block",
})
# Blocks allowed directly in doc; front_matter only as its first child.
TOP_LEVEL_NODES = BLOCK_CONTENT | {"front_matter", "footnote_def"}
_INLINE_CONTENT = frozenset(INLINE_NODES)

# Container -> (allowed child types, minimum number of children). Other nodes are leaves.
CONTENT: dict[str, tuple[frozenset[str], int]] = {
    "doc": (TOP_LEVEL_NODES, 1),
    "paragraph": (_INLINE_CONTENT, 0),
    "heading": (_INLINE_CONTENT, 0),
    "blockquote": (BLOCK_CONTENT, 1),
    "bullet_list": (frozenset({"list_item"}), 1),
    "ordered_list": (frozenset({"list_item"}), 1),
    "list_item": (BLOCK_CONTENT, 1),
    "code_block": (frozenset({"text"}), 0),
    "table": (frozenset({"table_row"}), 1),
    "table_row": (frozenset({"table_header", "table_cell"}), 1),
    "table_header": (_INLINE_CONTENT, 0),
    "table_cell": (_INLINE_CONTENT, 0),
}


def _is_str(value: object) -> bool:
    return isinstance(value, str)


def _is_optional_str(value: object) -> bool:
    return value is None or isinstance(value, str)


def _is_int(value: object, low: int, high: int | None = None) -> bool:
    if not isinstance(value, int) or isinstance(value, bool):
        return False
    return value >= low and (high is None or value <= high)


_ATTR_CHECKS: dict[str, Callable[[object], bool]] = {
    "level": lambda v: _is_int(v, 1, 6),
    "tight": lambda v: isinstance(v, bool),
    "start": lambda v: _is_int(v, 0),
    "checked": lambda v: v is None or isinstance(v, bool),
    "language": _is_str,
    "highlight": _is_str,
    "align": lambda v: v in (None, "left", "center", "right"),
    "source": _is_str,
    "label": lambda v: isinstance(v, str) and v != "",
    "src": _is_str,
    "display_src": _is_str,
    "alt": _is_str,
    "title": _is_optional_str,
    "href": _is_str,
    LINE_ATTR: lambda v: v is None or _is_int(v, 1),
}


def validate(doc: dict) -> list[str]:
    """Problems found in `doc`, each prefixed with its JSON path ("$.content[2]"); [] when valid."""
    if not isinstance(doc, dict) or doc.get("type") != "doc":
        return ["$: root must be a doc node"]
    problems: list[str] = []
    _check_node(doc, "$", None, problems)
    return problems


def _check_node(node: object, path: str, parent: str | None, problems: list[str]) -> None:
    if not isinstance(node, dict) or not isinstance(node.get("type"), str):
        problems.append(f"{path}: not a node object")
        return
    name = node["type"]
    if name in BLOCK_NODES:
        required = BLOCK_NODES[name]
    elif name in INLINE_NODES:
        required = INLINE_NODES[name]
    else:
        problems.append(f"{path}: unknown node type {name!r}")
        return
    optional = (LINE_ATTR,) if name in TOP_LEVEL_NODES else ()
    attrs = _check_attrs(node, name, required, optional, path, problems)
    if attrs.get(LINE_ATTR) is not None and parent != "doc":
        problems.append(f"{path}: {LINE_ATTR} is only allowed on top-level blocks")
    _check_text(node, name, path, problems)
    _check_marks(node, name, path, parent, problems)
    _check_content(node, name, path, problems)


def _check_attrs(
    obj: dict, label: str, required: tuple[str, ...], optional: tuple[str, ...], path: str, problems: list[str]
) -> dict:
    attrs = obj.get("attrs", {})
    if not isinstance(attrs, dict):
        problems.append(f"{path}: attrs must be an object")
        return {}
    for attr in required:
        if attr not in attrs:
            problems.append(f"{path}: {label} is missing attr {attr!r}")
    for attr, value in attrs.items():
        if attr not in required and attr not in optional:
            problems.append(f"{path}: {label} has unknown attr {attr!r}")
        elif not _ATTR_CHECKS[attr](value):
            problems.append(f"{path}: {label}.{attr} has invalid value {value!r}")
    return attrs


def _check_text(node: dict, name: str, path: str, problems: list[str]) -> None:
    if name == "text":
        if not isinstance(node.get("text"), str) or node["text"] == "":
            problems.append(f"{path}: text node needs a non-empty 'text' string")
    elif "text" in node:
        problems.append(f"{path}: only text nodes have 'text'")


def _check_marks(node: dict, name: str, path: str, parent: str | None, problems: list[str]) -> None:
    if "marks" not in node:
        return
    marks = node["marks"]
    if name in BLOCK_NODES:
        problems.append(f"{path}: {name} cannot have marks")
        return
    if not isinstance(marks, list):
        problems.append(f"{path}: marks must be a list")
        return
    if marks and parent == "code_block":
        problems.append(f"{path}: marks are not allowed inside code_block")
    seen: set[str] = set()
    for index, mark in enumerate(marks):
        mark_path = f"{path}.marks[{index}]"
        mark_type = mark.get("type") if isinstance(mark, dict) else None
        if not isinstance(mark_type, str) or mark_type not in MARKS:
            problems.append(f"{mark_path}: unknown mark type {mark_type!r}")
            continue
        if mark_type in seen:
            problems.append(f"{mark_path}: duplicate mark {mark_type!r}")
        seen.add(mark_type)
        _check_attrs(mark, f"mark {mark_type}", MARKS[mark_type], (), mark_path, problems)


def _check_content(node: dict, name: str, path: str, problems: list[str]) -> None:
    if name not in CONTENT:
        if "content" in node:
            problems.append(f"{path}: {name} is a leaf and cannot have content")
        return
    content = node.get("content", [])
    if not isinstance(content, list):
        problems.append(f"{path}: content must be a list")
        return
    allowed, minimum = CONTENT[name]
    if len(content) < minimum:
        problems.append(f"{path}: {name} needs at least one child")
    for index, child in enumerate(content):
        child_path = f"{path}.content[{index}]"
        child_type = child.get("type") if isinstance(child, dict) else None
        if isinstance(child_type, str) and (child_type in BLOCK_NODES or child_type in INLINE_NODES):
            if child_type not in allowed:
                problems.append(f"{child_path}: {child_type} is not allowed in {name}")
            elif child_type == "front_matter" and index != 0:
                problems.append(f"{child_path}: front_matter must be the first child of doc")
        _check_node(child, child_path, name, problems)
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_docschema.py -v`
Expected: 56 passed.

- [x] **Step 5: Run the full suite and the Qt-import check**

Run:

```bash
.venv/Scripts/python -m pytest -v
rg -n "import (PySide|Qt)|from PySide" mdviewer/core tests
```

Expected: all tests pass; the `rg` line prints nothing.

- [x] **Step 6: Commit**

```bash
git add mdviewer/core/docschema.py tests/test_docschema.py
git commit -m "feat: add WYSIWYG document schema contract (core/docschema)"
```

**Review Focus:**

- Names and attrs equal spec 6.3 exactly (the first four tests pin them).
  Any change there must also be made in `web-src/src/schema.js` from Task 8.
- `bool` is never accepted as an int (`level: True`, `start: False`).
- `line` is accepted only on `TOP_LEVEL_NODES`, and is non-`None` only
  directly under `doc`.
- Malformed input never raises: non-dict children, non-list
  `content`/`marks`, non-dict `attrs` and unhashable `type` values all
  become problem strings.
- The module imports nothing from Qt or other `mdviewer` modules.

### Task 3: Front matter

**Status: steps detailed.** The module and tests below were run before being
written into this plan (33 passed).

**Input contract.** `split` receives the editor buffer.
`MainWindow._load` (`mdviewer/main_window.py:253-259`) has already stripped
any BOM (`encoding.detect`) and replaced `\r\n` with `\n`. So lines are
separated by `\n` only, and a CRLF block is deliberately not recognized
(test included). Lines are found with `str.find("\n")`, never
`str.splitlines()`: `splitlines` also breaks on `\r`, `\x0c`, `\u2028` and
others, which would disagree with how the Markdown parser sees lines.

**Rules (spec 6.6, made exact):**

- The text must start with `---\n` at offset 0, with no BOM, no indent and no
  trailing spaces.
- The block ends at the **first** following line that is exactly `---` or
  `...`, with no surrounding whitespace.
- If no line between the opener and that first closer is non-blank
  (`line.strip() != ""`), there is no front matter. The search does not move
  on to a later closer: `---\n\n---\n...` is a horizontal rule followed by
  normal text.
- If no closer exists, there is no front matter.
- `front` runs from offset 0 through the closing line **including its `\n`**,
  or to the end of the text when the closer is the last line without a
  newline.
- `body` is the rest, unchanged (leading blank lines included).
- `join(front, body) == (front or "") + body`, so
  `join(*split(text)) == text` for every input.

**Files:**
- Create: `mdviewer/core/frontmatter.py`
- Test: `tests/test_frontmatter.py`

**Interfaces:**
- Consumes: nothing (pure module, no Qt, no other `mdviewer` imports).
- Produces:
  - `split(text: str) -> tuple[str | None, str]`: `(front, body)`, or
    `(None, text)` when there is no front matter.
  - `join(front: str | None, body: str) -> str`
  - For Task 4 (`docmodel.from_markdown`):
    - the `front_matter` node's `source` is `front` exactly, and its `line`
      is `1`
    - body line numbers become file line numbers by adding
      `front.count("\n")` (0 when `front is None`). When `front` does not end
      with `\n`, the body is `""`, so the offset never matters.
  - For Task 6/7 (serializer): the save path is
    `join(front, serialize.to_markdown(doc))`. `front` is taken from the
    `front_matter` node's `source` and emitted verbatim.

- [x] **Step 1: Write the failing tests**

Create `tests/test_frontmatter.py`:

```python
import pytest

from mdviewer.core.frontmatter import join, split

# --- recognized blocks ---------------------------------------------------------


@pytest.mark.parametrize("text, front, body", [
    ("---\ntitle: x\n---\n# Hi\n", "---\ntitle: x\n---\n", "# Hi\n"),
    ("---\ntitle: x\n...\n# Hi\n", "---\ntitle: x\n...\n", "# Hi\n"),
    ("---\na: 1\n---\n", "---\na: 1\n---\n", ""),
    ("---\na: 1\n---", "---\na: 1\n---", ""),
    ("---\na: 1\n---\n\n\nText", "---\na: 1\n---\n", "\n\nText"),
    ("---\n\na: 1\n\n---\nx", "---\n\na: 1\n\n---\n", "x"),
    ("---\ntitle: Café ✓\n---\nbody", "---\ntitle: Café ✓\n---\n", "body"),
])
def test_split_recognizes_front_matter(text, front, body):
    assert split(text) == (front, body)


def test_block_ends_at_the_first_closing_line():
    assert split("---\na: 1\n---\nb\n---\n") == ("---\na: 1\n---\n", "b\n---\n")


def test_closer_must_be_exact():
    text = "---\na: |\n  ---\n--- \n....\n...\nrest\n"
    assert split(text) == ("---\na: |\n  ---\n--- \n....\n...\n", "rest\n")


# --- near misses: no front matter, text parsed normally -----------------------------


@pytest.mark.parametrize("text", [
    "",
    "---",
    "---\n",
    "---\na: 1\n",                 # no closing line
    "\n---\na: 1\n---\n",          # not at offset 0
    " ---\na: 1\n---\n",           # indented opener
    "--- \na: 1\n---\n",           # trailing space on the opener
    "----\na: 1\n----\n",          # four dashes
    "...\na: 1\n...\n",            # dots only close a block
    "---\n---\nText\n",            # empty block: a horizontal rule, then text
    "---\n  \n\t\n---\nText\n",    # blank-only block
    "---\n\n---\na: 1\n---\n",     # the first closer ends the (blank) block
    "---\nText\n--- \n",           # closer with a trailing space
    "# Title\n---\na\n---\n",
    "---\r\na: 1\r\n---\r\n",      # CRLF never reaches core/: the buffer is "\n" only
])
def test_split_near_misses(text):
    assert split(text) == (None, text)


# --- join ------------------------------------------------------------------------


def test_join_without_front_matter_is_the_body():
    assert join(None, "# Hi\n") == "# Hi\n"


def test_join_puts_the_block_back_unchanged():
    assert join("---\na: 1\n...\n", "\nbody") == "---\na: 1\n...\n\nbody"


@pytest.mark.parametrize("text", [
    "---\ntitle: x\n---\n# Hi\n",
    "---\na: 1\n---",
    "---\n\na: 1\n\n---\n\n\nx",
    "---\n---\nText\n",
    "---\na: 1\n",
    "",
    "plain\n",
])
def test_join_split_round_trip_is_byte_exact(text):
    assert join(*split(text)) == text
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_frontmatter.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'mdviewer.core.frontmatter'`.

- [x] **Step 3: Write the implementation**

Create `mdviewer/core/frontmatter.py`:

```python
"""Leading YAML front matter (spec 6.6): split it off byte-exact, join it back unchanged.

Input is the editor buffer: BOM already stripped, newlines already "\\n".
"""

_OPENER = "---\n"
_CLOSERS = ("---", "...")


def split(text: str) -> tuple[str | None, str]:
    """(front, body) when text starts with a front-matter block, else (None, text).

    The block opens with a "---" line at offset 0 and ends at the next line that is
    exactly "---" or "..."; at least one line in between must be non-blank. `front`
    runs through the closing line and its newline, so join(*split(text)) == text.
    """
    if not text.startswith(_OPENER):
        return None, text
    has_content = False
    pos = len(_OPENER)
    while pos < len(text):
        newline = text.find("\n", pos)
        end = len(text) if newline == -1 else newline
        line = text[pos:end]
        if line in _CLOSERS:
            if not has_content:
                return None, text
            cut = len(text) if newline == -1 else newline + 1
            return text[:cut], text[cut:]
        has_content = has_content or line.strip() != ""
        pos = end + 1
    return None, text


def join(front: str | None, body: str) -> str:
    """Inverse of split: the front-matter block (if any) followed by the body."""
    return (front or "") + body
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_frontmatter.py -v`
Expected: 33 passed.

- [x] **Step 5: Run the full suite and the Qt-import check**

Run:

```bash
.venv/Scripts/python -m pytest -v
rg -n "import (PySide|Qt)|from PySide" mdviewer/core tests
```

Expected: all tests pass; the `rg` line prints nothing.

- [x] **Step 6: Commit**

```bash
git add mdviewer/core/frontmatter.py tests/test_frontmatter.py
git commit -m "feat: add YAML front-matter split/join (core/frontmatter)"
```

**Review Focus:**

- `join(*split(text)) == text` for every input, including a closer at end of
  text without a newline and a body with leading blank lines.
- Only the **first** closing line counts; a blank-only block is rejected
  rather than extended to a later closer.
- Lines come from `"\n"` only (no `splitlines`), and the opener and closers
  match exactly: no `strip()` on them, only on the non-blank test.
- No YAML parsing and no YAML dependency: the block is opaque text.

### Task 4: Markdown -> document, text and structure

**Status: steps detailed.** All code and tests below were run before being
written into this plan, against mistune 3.4.0 and with the Task 2 module
taken from this plan. Results: 51 + 35 new tests pass, the 21 existing
`tests/test_render.py` tests stay green, and four deliberate breaks (no start
stack, no entity decoding, no text merging, no URL check) each make tests
fail. Speed: 1 MB of Markdown converts in about 0.5 s, the same as
`render_body`.

**Findings about mistune 3.4.0 that shape this task:**

- **The AST has no source positions.** Line numbers come from small
  `BlockState`/`BlockParser` subclasses that tag each top-level token with
  `_pos`, its start offset:
  - Rule matches start at a line start (`m.start()`), and paragraphs and
    indented code are added while `state.cursor` is still at their start.
  - The list parser may call `parse_method` again on the **root** state for a
    block that interrupts the list, then `insert`s the list token, and an
    interrupted block quote is added with `prepend_token`. So the starts are a
    **stack**, and both `append` and `insert` are tagged.
  - Setext headings convert the previous paragraph token in place, so its tag
    survives.
- **Inline details:**
  - Text `raw` and link titles keep HTML entities (`&amp;`, `&copy;`), so
    docmodel decodes them strictly (`;` required, per CommonMark) and
    **per token before merging**, so that `\&amp;` stays a literal `&amp;`.
  - Backslash escapes arrive already applied (`\*` gives text `*`).
  - URLs arrive entity-decoded (`javascript&#58;x` gives `javascript:x`) and
    percent-encoded (`<b c>` gives `b%20c`).
  - Empty text tokens (`raw: ""`) occur and are skipped. An empty
    blockquote holds only `blank_line` children.
- **Reference definitions** (`[r]: url`) produce no token; their lines fall
  into the next token's gap.
- **mistune deviates from CommonMark** in one place: `> quote\n# Head` keeps
  the heading *inside* the quote. docmodel follows mistune, which keeps the
  Task 7 property `render_body(md2) == render_body(md)` consistent.

**Design decisions (later tasks rely on them):**

- **Exact ProseMirror shape.** Output equals what ProseMirror's `toJSON()`
  returns for the same document, so Task 12 can assert
  `request_document() == set_document()` input:
  - every declared attr is present, including `line: None` on nested nodes
    of `TOP_LEVEL_NODES` types
  - empty `content` and `marks` are omitted
  - adjacent text nodes with equal marks are merged
  - marks are sorted in `docschema.MARKS` order (strong, em, strike, code,
    link). **Task 8 must declare the marks in that order**, because
    ProseMirror sorts marks by schema rank.
- **Fallback.** A top-level block containing any token without a handler
  (block or inline, at any depth) becomes
  `html_block{source: <the block's source slice>}`:
  - the slice runs from the token's `_pos` to the next token's `_pos`
  - trailing `\n` are stripped (**protected `source` attrs never end with
    `\n`**, except `front_matter`, which is byte-exact)
  - slices that are blank are dropped
  - the slice includes reference definitions that follow the block, so they
    survive verbatim.

  Until Task 5 lands, lists, code blocks, tables, raw HTML, images and
  footnote references therefore become `html_block`. Footnote definitions
  are lost in that interim; Task 5 must handle the `footnotes` token. The
  fallback tests remove a handler with `monkeypatch`, so they stay valid
  after Task 5.
- **The `footnotes` token has no `_pos`.** The footnotes plugin adds it in an
  after-render hook, outside the block parser. So `from_markdown` reads
  positions with `.get("_pos", len(body))`: that token's slice is empty and
  it is dropped. (Revision: the first draft of this task indexed
  `token["_pos"]` and raised `KeyError` on any document with a footnote.
  `test_documents_with_footnotes_convert` guards against that.)
- **Soft line breaks** become a space; **hard breaks** become `hard_break`
  carrying the active marks.
- **Code spans** keep their raw text (no entity decoding) and add the `code`
  mark to the active marks.
- **Links:** `href` is kept exactly as mistune gives it. A link that fails
  `urls.is_safe` loses its link mark and keeps its text. A title is decoded,
  or `None`.
- **Autolinks** (`<http://a>`, bare `https://...`, `<a@b.co>` with href
  `mailto:a@b.co`) are ordinary `link` marks. The serializer (Task 6) decides
  when to write them back bare.
- **Line attrs:**
  - the top-level `line` is the file line: the body line plus
    `front.count("\n")`
  - `front_matter` is line 1
  - a document with no body blocks gets one empty paragraph at line
    `offset + 1`
- **`urls.is_safe`** blocks `javascript:`, `vbscript:` and non-image `data:`
  (the same policy as `render.py`'s mistune setup: `data:image/` allowed,
  `file:` allowed). ASCII whitespace and control characters are removed
  before comparing, as browsers do. `urls.resolve` is `render.py`'s
  `_resolve` moved verbatim; `render.py` delegates to it, and its existing
  tests keep covering it.

**Files:**
- Create: `mdviewer/core/urls.py`
- Create: `mdviewer/core/docmodel.py`
- Modify: `mdviewer/core/render.py` (imports at lines 8-17; `_Renderer._resolve` at lines 121-136)
- Test: `tests/test_urls.py`, `tests/test_docmodel.py` (new); `tests/test_render.py` (unchanged, must stay green)

**Interfaces:**
- Consumes:
  - `docschema.MARKS`, `docschema.TOP_LEVEL_NODES`, `docschema.LINE_ATTR`
    and `docschema.validate` (Task 2)
  - `frontmatter.split` (Task 3), indirectly: callers pass its `front`
  - `render.PLUGINS`
- Produces:
  - `urls.resolve(url: str, base_dir: Path | None) -> str`
  - `urls.is_safe(url: str) -> bool`
  - `docmodel.from_markdown(body: str, front: str | None = None, base_dir: Path | None = None) -> dict`
    (`base_dir` is unused until Task 5's images)
  - For Task 5, which replaces `docmodel.py` as a whole (handlers gain a
    context argument): the Task 4 tests patch `docmodel._BLOCKS` (mistune
    block token type -> node builder) and `docmodel._SIMPLE_MARKS`, so both
    names must survive.
  - For Task 6 (serializer):
    - text is **decoded**, so the escaping rules must also escape `&` where
      it would start an entity reference (`&copy;` in text must not come back
      as ©)
    - a body that is a single empty paragraph serializes to `""`
    - autolink round trip: text equal to href, or `mailto:` + text, can be
      written bare.

- [x] **Step 1: Write the failing URL tests**

Create `tests/test_urls.py`:

```python
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
```

- [x] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_urls.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'mdviewer.core.urls'`.

- [x] **Step 3: Create `mdviewer/core/urls.py`**

```python
"""URL helpers shared by the preview renderer and the document model (pure, Qt-free)."""

import os
from pathlib import Path
from urllib.parse import unquote, urlsplit

# Same policy as render.py's mistune setup: script URLs and non-image data: URLs are unsafe.
_BLOCKED_PREFIXES = ("javascript:", "vbscript:", "data:")
_ALLOWED_DATA_PREFIX = "data:image/"


def resolve(url: str, base_dir: Path | None) -> str:
    """Turn a document-relative URL into an absolute file: URI; leave anything else as is."""
    if base_dir is None or not url or url.startswith(("#", "/", "\\")):
        return url
    parts = urlsplit(url)
    if len(parts.scheme) == 1:  # C:/pics/a.png - a Windows drive path
        return Path(unquote(url)).as_uri()
    if parts.scheme or parts.netloc:  # http:, mailto:, file:, ...
        return url
    target = Path(os.path.normpath(Path(base_dir).absolute() / unquote(parts.path)))
    uri = target.as_uri()
    if parts.query:
        uri += "?" + parts.query
    if parts.fragment:
        uri += "#" + parts.fragment
    return uri


def is_safe(url: str) -> bool:
    """False for javascript:, vbscript: and non-image data: URLs.

    Browsers ignore ASCII whitespace and control characters inside a scheme
    ("java\\tscript:"), so those are dropped before comparing."""
    compact = "".join(ch for ch in url if ord(ch) > 0x20).lower()
    return compact.startswith(_ALLOWED_DATA_PREFIX) or not compact.startswith(_BLOCKED_PREFIXES)
```

- [x] **Step 4: Make `render.py` use `urls.resolve`**

In `mdviewer/core/render.py`, replace the imports

```python
import html
import os
from pathlib import Path
from urllib.parse import unquote, urlsplit

import mistune
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound
```

with

```python
import html
from pathlib import Path

import mistune
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

from mdviewer.core import urls
```

and replace the body of `_Renderer._resolve`

```python
    def _resolve(self, url: str) -> str:
        """Turn a document-relative URL into an absolute file: URI."""
        if self._base_dir is None or not url or url.startswith(("#", "/", "\\")):
            return url
        parts = urlsplit(url)
        if len(parts.scheme) == 1:  # C:/pics/a.png - a Windows drive path
            return Path(unquote(url)).as_uri()
        if parts.scheme or parts.netloc:  # http:, mailto:, file:, ...
            return url
        target = Path(os.path.normpath(Path(self._base_dir).absolute() / unquote(parts.path)))
        uri = target.as_uri()
        if parts.query:
            uri += "?" + parts.query
        if parts.fragment:
            uri += "#" + parts.fragment
        return uri
```

with

```python
    def _resolve(self, url: str) -> str:
        """Turn a document-relative URL into an absolute file: URI."""
        return urls.resolve(url, self._base_dir)
```

- [x] **Step 5: Run the URL and render tests**

Run: `.venv/Scripts/python -m pytest tests/test_urls.py tests/test_render.py -v`
Expected: 56 passed (35 + 21).

- [x] **Step 6: Write the failing document-model tests**

Create `tests/test_docmodel.py`:

```python
import pytest

from mdviewer.core import docmodel
from mdviewer.core.docschema import validate


def convert(markdown, front=None):
    """from_markdown, plus the contract every output must meet."""
    doc = docmodel.from_markdown(markdown, front)
    assert validate(doc) == []
    return doc


def doc(*blocks):
    return {"type": "doc", "content": list(blocks)}


def para(*inline, line=None):
    node = {"type": "paragraph", "attrs": {"line": line}}
    if inline:
        node["content"] = list(inline)
    return node


def heading(level, *inline, line=None):
    node = {"type": "heading", "attrs": {"level": level, "line": line}}
    if inline:
        node["content"] = list(inline)
    return node


def quote(*blocks, line=None):
    return {"type": "blockquote", "attrs": {"line": line}, "content": list(blocks)}


def rule(line=None):
    return {"type": "horizontal_rule", "attrs": {"line": line}}


def text(value, *marks):
    node = {"type": "text", "text": value}
    if marks:
        node["marks"] = list(marks)
    return node


def hard_break(*marks):
    node = {"type": "hard_break"}
    if marks:
        node["marks"] = list(marks)
    return node


STRONG, EM, STRIKE, CODE = ({"type": name} for name in ("strong", "em", "strike", "code"))


def link(href, title=None):
    return {"type": "link", "attrs": {"href": href, "title": title}}


def only_inline(markdown):
    """Inline content of a one-paragraph document."""
    [block] = convert(markdown)["content"]
    assert block["type"] == "paragraph"
    return block.get("content", [])


# --- documents and paragraphs ---------------------------------------------------------


@pytest.mark.parametrize("markdown", ["", "\n", "\n\n  \n"])
def test_empty_body_is_one_empty_paragraph(markdown):
    assert convert(markdown) == doc(para(line=1))


def test_paragraphs_with_lines():
    assert convert("Hello\n\nWorld\n") == doc(para(text("Hello"), line=1), para(text("World"), line=3))


def test_soft_break_becomes_a_space():
    assert only_inline("line one\nline two") == [text("line one line two")]


def test_hard_breaks():
    assert only_inline("a  \nb\\\nc") == [text("a"), hard_break(), text("b"), hard_break(), text("c")]


def test_hard_break_keeps_active_marks():
    assert only_inline("**a  \nb**") == [text("a", STRONG), hard_break(STRONG), text("b", STRONG)]


# --- headings ------------------------------------------------------------------------


@pytest.mark.parametrize("level", [1, 2, 3, 4, 5, 6])
def test_atx_headings(level):
    assert convert("#" * level + " Title") == doc(heading(level, text("Title"), line=1))


def test_atx_closing_hashes_are_dropped():
    assert convert("#   Title   #\n") == doc(heading(1, text("Title"), line=1))


def test_setext_headings():
    assert convert("One\n===\n\nTwo\n---\n") == doc(
        heading(1, text("One"), line=1), heading(2, text("Two"), line=4)
    )


def test_empty_heading_has_no_content():
    assert convert("#\n") == doc(heading(1, line=1))


# --- block quotes and rules -------------------------------------------------------------


def test_blockquote_nested_blocks_have_line_none():
    assert convert("> a\n>\n> b\n") == doc(quote(para(text("a")), para(text("b")), line=1))


def test_blockquote_lazy_continuation():
    assert convert("> quote\nlazy\n") == doc(quote(para(text("quote lazy")), line=1))


def test_empty_blockquote_gets_an_empty_paragraph():
    assert convert(">\n") == doc(quote(para(), line=1))


def test_nested_blockquote():
    assert convert("> > deep\n") == doc(quote(quote(para(text("deep"))), line=1))


@pytest.mark.parametrize("markdown", ["***", "---", "___", " - - -"])
def test_horizontal_rules(markdown):
    assert convert(f"text\n\n{markdown}\n") == doc(para(text("text"), line=1), rule(line=3))


# --- marks ---------------------------------------------------------------------------


def test_simple_marks():
    assert only_inline("**b** *i* ~~s~~ `c`") == [
        text("b", STRONG), text(" "), text("i", EM), text(" "), text("s", STRIKE), text(" "), text("c", CODE),
    ]


def test_marks_are_sorted_in_schema_order():
    assert only_inline("***both***") == [text("both", STRONG, EM)]
    assert only_inline("~~**x**~~") == [text("x", STRONG, STRIKE)]


def test_nested_marks_split_text():
    assert only_inline("**a *b* c**") == [text("a ", STRONG), text("b", STRONG, EM), text(" c", STRONG)]


def test_code_span_keeps_outer_marks_and_raw_text():
    assert only_inline("**`a &amp; *b*`**") == [text("a &amp; *b*", STRONG, CODE)]


def test_code_span_line_ending_becomes_space():
    assert only_inline("`a\nb`") == [text("a b", CODE)]


# --- links ---------------------------------------------------------------------------


def test_inline_link_with_and_without_title():
    assert only_inline('[a](http://x "T") [b](y)') == [
        text("a", link("http://x", "T")), text(" "), text("b", link("y")),
    ]


def test_link_title_entities_are_decoded():
    assert only_inline('[a](u "x &amp; y")') == [text("a", link("u", "x & y"))]


def test_marks_inside_and_around_links():
    assert only_inline("[**b** l](u) **[in](v)**") == [
        text("b", STRONG, link("u")), text(" l", link("u")), text(" "), text("in", STRONG, link("v")),
    ]


def test_autolinks():
    assert only_inline("<http://a.b> <a@b.co> https://x.y/z.") == [
        text("http://a.b", link("http://a.b")), text(" "),
        text("a@b.co", link("mailto:a@b.co")), text(" "),
        text("https://x.y/z", link("https://x.y/z")), text("."),
    ]


def test_reference_links_become_inline_links():
    assert convert('[t][r] and [r]\n\n[r]: http://r "RT"\n') == doc(
        para(text("t", link("http://r", "RT")), text(" and "), text("r", link("http://r", "RT")), line=1)
    )


@pytest.mark.parametrize("markdown", [
    "[a](javascript:alert(1))",
    "[a](JAVASCRIPT:alert(1))",
    "[a](javascript&#58;alert(1))",
    "[a](vbscript:msgbox)",
    "[a](data:text/html,x)",
    "<javascript:alert(1)>",
])
def test_unsafe_links_keep_text_without_link(markdown):
    [node] = only_inline(markdown)
    assert "marks" not in node


def test_image_data_url_link_is_kept():
    assert only_inline("[a](data:image/png;base64,AA)") == [text("a", link("data:image/png;base64,AA"))]


# --- text decoding -------------------------------------------------------------------


def test_entities_are_decoded_strictly():
    assert only_inline("a &amp; b &copy; &#35; &#x41; &nosuch; AT&T &copy") == [
        text("a & b © # A &nosuch; AT&T &copy")
    ]


def test_backslash_escapes():
    assert only_inline("\\*not em\\* \\&amp;") == [text("*not em* &amp;")]


# --- front matter and line numbers ---------------------------------------------------------


def test_front_matter_node_and_line_offset():
    front = "---\na: 1\n---\n"
    assert convert("# T\n", front) == doc(
        {"type": "front_matter", "attrs": {"source": front, "line": 1}},
        heading(1, text("T"), line=4),
    )


def test_front_matter_only_adds_an_empty_paragraph():
    front = "---\na: 1\n---\n"
    assert convert("", front) == doc(
        {"type": "front_matter", "attrs": {"source": front, "line": 1}}, para(line=4)
    )


def test_top_level_lines_follow_the_source():
    markdown = "Title\n=====\n\n\n> quote\nlazy\n\n[r]: http://x\npara\n\n***\n"
    assert [block["attrs"]["line"] for block in convert(markdown)["content"]] == [1, 5, 9, 11]


# --- fallback: unmappable blocks are kept as source -------------------------------------------


def test_unmappable_top_level_block_keeps_its_source(monkeypatch):
    monkeypatch.delitem(docmodel._BLOCKS, "block_quote")
    assert convert("> a\n> b\n\nafter\n") == doc(
        {"type": "html_block", "attrs": {"source": "> a\n> b", "line": 1}},
        para(text("after"), line=4),
    )


def test_unmappable_nested_block_protects_the_whole_top_level_block(monkeypatch):
    monkeypatch.delitem(docmodel._BLOCKS, "thematic_break")
    assert convert("> a\n>\n> ***\n\nz\n") == doc(
        {"type": "html_block", "attrs": {"source": "> a\n>\n> ***", "line": 1}},
        para(text("z"), line=5),
    )


def test_unmappable_inline_protects_its_block(monkeypatch):
    monkeypatch.delitem(docmodel._SIMPLE_MARKS, "strikethrough")
    assert convert("# H\n\na ~~b~~ c\n") == doc(
        heading(1, text("H"), line=1),
        {"type": "html_block", "attrs": {"source": "a ~~b~~ c", "line": 3}},
    )


def test_unmappable_block_absorbs_a_following_reference_definition(monkeypatch):
    monkeypatch.delitem(docmodel._BLOCKS, "block_quote")
    assert convert("> [a][r]\n[r]: http://x\n\nz\n")["content"][0] == {
        "type": "html_block", "attrs": {"source": "> [a][r]\n[r]: http://x", "line": 1},
    }


def test_documents_with_footnotes_convert():
    assert convert("A[^1]\n\n[^1]: note\n")["content"][0]["attrs"]["line"] == 1
```

- [x] **Step 7: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_docmodel.py -v`
Expected: collection error, `ImportError: cannot import name 'docmodel' from 'mdviewer.core'`.

- [x] **Step 8: Create `mdviewer/core/docmodel.py`**

```python
"""Markdown -> ProseMirror document JSON for the Rendered editor (spec 6.3, 6.4).

Parses with mistune's AST and render.py's plugin list, and returns exactly what
ProseMirror's toJSON() gives for the same document: every declared attr present
(LINE_ATTR is None below the top level), empty content and marks omitted,
adjacent text nodes with equal marks merged, marks in docschema.MARKS order.
A top-level block containing anything this module cannot map becomes a protected
html_block holding its source text, so nothing is lost.
"""

import html
import re
from bisect import bisect_left
from pathlib import Path

import mistune
from mistune.plugins import import_plugin

from mdviewer.core import docschema, urls
from mdviewer.core.render import PLUGINS

# CommonMark entity references (the ';' is required); html.unescape decodes each match.
_ENTITY = re.compile(r"&(?:#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});")
_MARK_RANK = {name: rank for rank, name in enumerate(docschema.MARKS)}
# mistune inline token -> mark without attrs.
_SIMPLE_MARKS = {"strong": "strong", "emphasis": "em", "strikethrough": "strike"}


class _Unmappable(Exception):
    """A token with no document node; its top-level block is kept as source."""


# --- mistune with block start offsets -------------------------------------------
# mistune's AST has no positions. These subclasses tag each top-level token with
# "_pos", the offset where its block starts. Rules record m.start() while they run
# (a stack: the list rule may parse an interrupting block on the same state), and
# paragraphs and indented code are added while state.cursor is still at their start.


class _Tokens(list):
    def __init__(self, state: "_State"):
        super().__init__()
        self._state = state

    def _tag(self, token: dict) -> None:
        starts = self._state.block_starts
        token.setdefault("_pos", starts[-1] if starts else self._state.cursor)

    def append(self, token: dict) -> None:
        self._tag(token)
        super().append(token)

    def insert(self, index: int, token: dict) -> None:
        self._tag(token)
        super().insert(index, token)


class _State(mistune.BlockState):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.block_starts: list[int] = []
        if parent is None:
            self.tokens = _Tokens(self)


class _BlockParser(mistune.BlockParser):
    state_cls = _State

    def parse_method(self, m, state):
        if state.parent is not None:
            return super().parse_method(m, state)
        state.block_starts.append(m.start())
        try:
            return super().parse_method(m, state)
        finally:
            state.block_starts.pop()


def _parse(body: str) -> list[dict]:
    markdown = mistune.Markdown(
        renderer=None,
        block=_BlockParser(),
        inline=mistune.InlineParser(),
        plugins=[import_plugin(name) for name in PLUGINS],
    )
    return markdown(body)


# --- public API -----------------------------------------------------------------


def from_markdown(body: str, front: str | None = None, base_dir: Path | None = None) -> dict:
    """Document JSON for `body`; `front` (from frontmatter.split) becomes a front_matter node.

    base_dir is the folder image paths resolve against (display_src); None for Untitled."""
    offset = front.count("\n") if front is not None else 0
    newlines = [m.start() for m in re.finditer("\n", body)]
    blocks: list[dict] = []
    if front is not None:
        blocks.append(_node("front_matter", {"source": front, docschema.LINE_ATTR: 1}))
    tokens = _parse(body)
    for index, token in enumerate(tokens):
        if token["type"] == "blank_line":
            continue
        start = token.get("_pos", len(body))  # the footnotes token is added after parsing
        end = tokens[index + 1].get("_pos", len(body)) if index + 1 < len(tokens) else len(body)
        try:
            node = _block(token)
        except _Unmappable:
            source = body[start:end].rstrip("\n")
            if not source.strip():
                continue
            node = _node("html_block", {"source": source})
        node["attrs"][docschema.LINE_ATTR] = offset + bisect_left(newlines, start) + 1
        blocks.append(node)
    if not any(block["type"] != "front_matter" for block in blocks):
        blocks.append(_node("paragraph", {docschema.LINE_ATTR: offset + 1}))
    return {"type": "doc", "content": blocks}


# --- blocks ---------------------------------------------------------------------


def _node(kind: str, attrs: dict | None = None, content: list | None = None) -> dict:
    """A node shaped like ProseMirror's toJSON(): all attrs, no empty content."""
    full = dict(attrs or {})
    if kind in docschema.TOP_LEVEL_NODES:
        full.setdefault(docschema.LINE_ATTR, None)
    node: dict = {"type": kind}
    if full:
        node["attrs"] = full
    if content:
        node["content"] = content
    return node


def _block(token: dict) -> dict:
    handler = _BLOCKS.get(token["type"])
    if handler is None:
        raise _Unmappable(token["type"])
    return handler(token)


def _blocks(tokens: list[dict]) -> list[dict]:
    """Child blocks without blank lines; an empty container gets one empty paragraph."""
    nodes = [_block(token) for token in tokens if token["type"] != "blank_line"]
    return nodes or [_node("paragraph")]


def _paragraph(token: dict) -> dict:
    return _node("paragraph", content=_inline(token["children"]))


def _heading(token: dict) -> dict:
    return _node("heading", {"level": token["attrs"]["level"]}, _inline(token["children"]))


def _block_quote(token: dict) -> dict:
    return _node("blockquote", content=_blocks(token["children"]))


def _thematic_break(token: dict) -> dict:
    return _node("horizontal_rule")


_BLOCKS = {
    "paragraph": _paragraph,
    "heading": _heading,
    "block_quote": _block_quote,
    "thematic_break": _thematic_break,
}


# --- inline ---------------------------------------------------------------------


def _inline(children: list[dict]) -> list[dict]:
    nodes: list[dict] = []
    _walk_inline(children, {}, nodes)
    merged: list[dict] = []
    for node in nodes:
        previous = merged[-1] if merged else None
        if (
            previous is not None
            and previous["type"] == node["type"] == "text"
            and previous.get("marks") == node.get("marks")
        ):
            previous["text"] += node["text"]
        else:
            merged.append(node)
    return merged


def _walk_inline(children: list[dict], marks: dict[str, dict | None], out: list[dict]) -> None:
    """Append inline nodes to `out`; `marks` maps each active mark name to its attrs (or None)."""
    for child in children:
        kind = child["type"]
        if kind == "text":
            _text(_decode(child["raw"]), marks, out)
        elif kind == "softbreak":
            _text(" ", marks, out)
        elif kind == "linebreak":
            out.append(_marked({"type": "hard_break"}, marks))
        elif kind == "codespan":
            _text(child["raw"], {**marks, "code": None}, out)
        elif kind in _SIMPLE_MARKS:
            _walk_inline(child["children"], {**marks, _SIMPLE_MARKS[kind]: None}, out)
        elif kind == "link":
            _walk_inline(child["children"], _with_link(child["attrs"], marks), out)
        else:
            raise _Unmappable(kind)


def _with_link(attrs: dict, marks: dict[str, dict | None]) -> dict[str, dict | None]:
    href = attrs["url"]
    if not urls.is_safe(href):
        return marks  # keep the text, drop the link
    title = attrs.get("title")
    return {**marks, "link": {"href": href, "title": None if title is None else _decode(title)}}


def _text(text: str, marks: dict[str, dict | None], out: list[dict]) -> None:
    if text:
        out.append(_marked({"type": "text", "text": text}, marks))


def _marked(node: dict, marks: dict[str, dict | None]) -> dict:
    if marks:
        node["marks"] = [
            {"type": name} if attrs is None else {"type": name, "attrs": dict(attrs)}
            for name, attrs in sorted(marks.items(), key=lambda item: _MARK_RANK[item[0]])
        ]
    return node


def _decode(raw: str) -> str:
    return _ENTITY.sub(lambda m: html.unescape(m.group()), raw)
```

- [x] **Step 9: Run the document-model tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_docmodel.py -v`
Expected: 51 passed.

- [x] **Step 10: Run the full suite, the Qt-import check and the UI smoke**

Run:

```bash
.venv/Scripts/python -m pytest -v
rg -n "import (PySide|Qt)|from PySide" mdviewer/core tests
.venv/Scripts/python scripts/smoke_ui.py
```

Expected: all tests pass; the `rg` line prints nothing; `SMOKE OK`. The
preview still resolves relative images and links through `urls.resolve`.

- [x] **Step 11: Commit**

```bash
git add mdviewer/core/urls.py mdviewer/core/render.py mdviewer/core/docmodel.py tests/test_urls.py tests/test_docmodel.py
git commit -m "feat: convert Markdown text blocks and marks to document JSON"
```

**Review Focus:**

- `render.py` behaves exactly as before. `_resolve` delegates to
  `urls.resolve`, and `os`, `unquote` and `urlsplit` are no longer imported
  there; `render.py` must not import `docmodel` (no import cycle).
- The position hook tags only **root** tokens. Nested states (block quote,
  list children) are untouched, and `_pos` never leaks into the output.
- Output is ProseMirror-shaped:
  - `line: None` on nested top-level-type nodes
  - no empty `content` or `marks` keys
  - merged text runs
  - marks in `MARKS` order
  - mark dicts are fresh copies (no shared `attrs` dicts between nodes)
- Entities are decoded per token before merging, strictly (`&copy` without
  `;` stays literal); code spans are never decoded.
- Unsafe links lose only the mark, never the text. The fallback keeps the
  block's full source, including reference definitions that follow it.

### Task 5: Markdown -> document, rich blocks and protected nodes

**Status: steps detailed.** All code and tests below were run before being
written into this plan, against mistune 3.4.0 with the Task 2-4 modules taken
from this plan. Results:
- `tests/test_docmodel.py` (51 Task 4 + 35 Task 5 tests) and the 7 new
  `highlight_code` tests pass.
- The new Task 5 tests run against the Task 4 code give 32 failed, 54 passed.
- Six deliberate breaks each make tests fail: footnote capture, fence
  newline, pipe unescaping in table code, unsafe-image check, fallback cut,
  footnote label lookup.

**Findings about mistune 3.4.0 that shape this task:**

- **Lists:**
  - The `list` token has `tight`, `attrs.ordered` and `attrs.start`
    (present only when it isn't 1).
  - Items are `list_item` or `task_list_item` (`attrs.checked`; `[X]`
    counts as checked).
  - Tight items hold `block_text` instead of `paragraph`.
  - An empty item (`-`) has no children.
- **Code:**
  - Fenced `raw` keeps the newline before the closing fence
    (`print(1)\n\n` for a block ending in a blank line). Indented `raw` has
    no trailing newline.
  - `attrs.info` holds the full info string (`python title=x`) and is absent
    when the fence has none.
- **Tables:**
  - `table` holds `table_head` (cells directly) and `table_body` (rows).
  - Cells carry `attrs.align` (`left`/`center`/`right`/None).
  - mistune ends the table at the first row whose cell count differs, so
    rows always match the header width.
  - Inside a table, a code span keeps `\|` raw. GFM shows `|`.
- **Images:**
  - `attrs.url` is percent-encoded; `attrs.title` is optional.
  - The alt text comes as inline children.
  - Reference images arrive resolved.
- **Raw HTML:** `block_html.raw` ends with `\n`; `inline_html.raw` is the
  tag or comment text.
- **Footnotes:**
  - A definition (`[^label]: text`, block rule `ref_footnote`, top level
    only) produces **no token**.
  - The `footnotes` token holds only *referenced* notes, in reference order,
    and is added by an after-render hook (so it has no `_pos`).
  - `footnote_ref.raw` is mistune's *normalized* key (`[^note]` arrives as
    `NOTE`).
  - A `[^a]: x` inside a quote or list item is consumed as a link reference
    definition. So footnote definitions exist only at the root.

**Cross-task finding (recorded for Tasks 8, 9 and 11).** `prosemirror-tables`
1.8.5 reads `colspan`, `rowspan` and `colwidth` on every cell (its table map
breaks without them). The JS schema must declare them (defaults `1`, `1`,
`null`). They are **not** part of the Python document contract: spec 6.3's
`table_header{align}` and `table_cell{align}` stay as they are.
- Task 9's `getDocument` deletes the three attrs from every cell before
  returning the JSON. On `setDocument`, ProseMirror fills in the defaults.
- Task 11's paste must split merged cells (`colspan`/`rowspan` > 1), since
  merged cells are a v2 non-goal.

**Design decisions:**

- **`docmodel.py` is replaced as a whole.** Handlers now take a context
  (`_Context(base_dir, labels)`), because images need `base_dir` and
  footnote references need the definitions' labels, deep inside inline
  conversion. Names the Task 4 tests patch stay the same: `_BLOCKS`,
  `_SIMPLE_MARKS`. New: the `_INLINE` table, `_table_row`.
- **Lists:**
  - `ordered_list{start, tight}` and `bullet_list{tight}`
  - `list_item{checked}`: `None` for normal items, a bool for task items
  - `block_text` maps to `paragraph`
  - an empty item gets one empty paragraph
  - the bullet character and the `.`/`)` delimiter are normalized away
    (accepted)
- **Code blocks:**
  - the text is `raw` minus one trailing `\n`
  - `language` is the first word of the info string (the rest is dropped:
    normalization, accepted), `""` when there is none
  - `highlight = render.highlight_code(code, language)`
  - an empty block has no content
  - code text is never entity-decoded
- **`render.highlight_code(code, language)`:**
  - returns Pygments `<span class=...>` markup only, using
    `HtmlFormatter(nowrap=True)`: no wrapper and no inline colors, so it is
    theme-independent and `page_css` colors it under `.highlight`
  - the lexer is created with `stripnl=False, ensurenl=False`, so the text is
    kept exactly
  - returns `""` for an empty or unknown language
  - **Task 8's code-block node view must wrap it in an element with class
    `highlight`** (for example `<pre class="highlight">`)
  - the existing v1 `_Renderer.block_code` stays as is
- **Tables:**
  - the head row's cells become `table_header`, body cells become
    `table_cell`, each with `align`
  - `\|` inside code text in a cell becomes `|` (the Task 7 serializer escapes
    `|` in cells, so this round-trips)
  - a ragged table (never produced by mistune) raises `_Unmappable`, so its
    source is kept
- **Images:**
  - `src` is kept as mistune gives it
  - `display_src = urls.resolve(src, base_dir)`, which equals `src` when
    `base_dir` is None (Untitled)
  - `alt` is the plain text of the children
  - `title` is decoded or `None`
  - an image is inline, so it carries active marks (a linked badge has a
    `link` mark)
  - an image whose `src` fails `urls.is_safe` is replaced by its alt text
- **Raw HTML:**
  - `html_block{source: raw without trailing newlines}`
  - `html_inline{source}`, carrying active marks
- **Footnotes:**
  - The `_BlockParser` hook records, for each `ref_footnote` match at the
    root, `(label as written, source slice without trailing newlines,
    offset)`, keeping the first definition per key as mistune does.
  - **All** definitions become `footnote_def{label, source, line}` at the
    end of the document in source order, including unreferenced ones, so
    saving never drops them.
  - A `footnote_ref` gets its definition's label as written, so `[^Note]`
    referring to `[^note]: ...` becomes `note` (normalization, accepted).
  - Undefined references stay text, as in mistune.
  - The `footnotes` token itself is skipped.
  - When a block falls back to `html_block`, its slice is cut at the first
    footnote definition inside it, so the definition is not duplicated.
- **Empty documents:** a document whose only blocks would be front matter
  and/or footnote definitions gets one empty paragraph (line `offset + 1`)
  after the front matter.
- **Known limit of the fallback** (unchanged from Task 4): reference link
  definitions used *only* inside an `html_block` fallback are lost on save if
  they follow a mappable block. With every mistune token now mapped, the
  fallback is a safety net only. `test_repo_documents_map_without_fallback`
  checks that the project's own Markdown files never hit it.

**Files:**
- Modify: `mdviewer/core/render.py` (add `highlight_code` after `render_body`)
- Replace: `mdviewer/core/docmodel.py` (whole file)
- Modify: `tests/test_render.py` (imports + 7 tests), `tests/test_docmodel.py` (append 35 tests)

**Interfaces:**
- Consumes:
  - `docschema` (Task 2), `frontmatter.split` (Task 3, used in a test)
  - `urls.resolve`, `urls.is_safe` and the Task 4 test helpers in
    `tests/test_docmodel.py` (`convert`, `doc`, `para`, `text`, `link`,
    `only_inline`, `STRONG`, `CODE`)
  - `render.PLUGINS`
- Produces:
  - `render.highlight_code(code: str, language: str) -> str`
  - `docmodel.from_markdown(body, front=None, base_dir=None) -> dict`,
    covering every node in spec 6.3
  - Footnote definitions are the last top-level nodes, in source order.
  - Every protected `source` except `front_matter` lacks trailing newlines.
  - For Task 7: the serializer can emit the `footnote_def` `source` attrs
    verbatim at the end, and must escape `|` in table cells, including inside
    code spans.
  - For Task 8: wrap the `highlight` markup in a `.highlight` element; declare
    `colspan`/`rowspan`/`colwidth` on cell types.
  - For Task 9: `getDocument` strips those three cell attrs.

- [x] **Step 1: Write the failing `highlight_code` tests**

At the top of `tests/test_render.py`, replace

```python
from pygments.formatters import HtmlFormatter
```

with

```python
import html
import re

import pytest
from pygments.formatters import HtmlFormatter
```

and append to the end of `tests/test_render.py`:

```python
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
```

- [x] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_render.py -v`
Expected: the 7 new tests FAIL with
`AttributeError: module 'mdviewer.core.render' has no attribute 'highlight_code'`;
the 21 existing tests pass.

- [x] **Step 3: Add `highlight_code` to `render.py`**

In `mdviewer/core/render.py`, directly after the `render_body` function, add:

```python
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
```

(`highlight`, `HtmlFormatter`, `get_lexer_by_name` and `ClassNotFound` are
already imported by `render.py`.)

- [x] **Step 4: Run the render tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_render.py -v`
Expected: 28 passed.

- [x] **Step 5: Append the failing document-model tests**

Append to the end of `tests/test_docmodel.py` (the block uses a four-backtick
fence because the tests contain triple-backtick Markdown):

````python
# === Task 5: lists, code, tables, images, raw HTML, footnotes ===============================

from pathlib import Path  # noqa: E402

from mdviewer.core import frontmatter  # noqa: E402
from mdviewer.core.render import highlight_code  # noqa: E402


def convert_in(markdown, base_dir):
    doc = docmodel.from_markdown(markdown, None, base_dir)
    assert validate(doc) == []
    return doc


def bullets(*items, tight=True, line=None):
    return {"type": "bullet_list", "attrs": {"tight": tight, "line": line}, "content": list(items)}


def numbers(*items, start=1, tight=True, line=None):
    return {"type": "ordered_list", "attrs": {"start": start, "tight": tight, "line": line}, "content": list(items)}


def item(*blocks, checked=None):
    return {"type": "list_item", "attrs": {"checked": checked}, "content": list(blocks)}


def code(value, language="", line=None):
    node = {"type": "code_block",
            "attrs": {"language": language, "highlight": highlight_code(value, language), "line": line}}
    if value:
        node["content"] = [text(value)]
    return node


def cell(kind, *inline, align=None):
    node = {"type": kind, "attrs": {"align": align}}
    if inline:
        node["content"] = list(inline)
    return node


def row(*cells):
    return {"type": "table_row", "content": list(cells)}


def table(*rows, line=None):
    return {"type": "table", "attrs": {"line": line}, "content": list(rows)}


def image(src, display_src=None, alt="", title=None, marks=()):
    attrs = {"src": src, "display_src": src if display_src is None else display_src, "alt": alt, "title": title}
    node = {"type": "image", "attrs": attrs}
    if marks:
        node["marks"] = list(marks)
    return node


def html_block(source, line=None):
    return {"type": "html_block", "attrs": {"source": source, "line": line}}


def html_inline(source, *marks):
    node = {"type": "html_inline", "attrs": {"source": source}}
    if marks:
        node["marks"] = list(marks)
    return node


def footnote_ref(label):
    return {"type": "footnote_ref", "attrs": {"label": label}}


def footnote_def(label, source, line):
    return {"type": "footnote_def", "attrs": {"label": label, "source": source, "line": line}}


# --- lists -------------------------------------------------------------------------------


def test_tight_bullet_list_with_nested_list():
    assert convert("- a\n- b\n  - c\n") == doc(bullets(
        item(para(text("a"))),
        item(para(text("b")), bullets(item(para(text("c"))))),
        line=1,
    ))


def test_loose_ordered_list():
    assert convert("1. a\n\n2. b\n") == doc(
        numbers(item(para(text("a"))), item(para(text("b"))), tight=False, line=1)
    )


def test_ordered_list_start():
    assert convert("3) x\n4) y\n") == doc(numbers(item(para(text("x"))), item(para(text("y"))), start=3, line=1))


def test_task_items():
    assert convert("- [ ] todo\n- [x] done\n- [X] caps\n- plain\n") == doc(bullets(
        item(para(text("todo")), checked=False),
        item(para(text("done")), checked=True),
        item(para(text("caps")), checked=True),
        item(para(text("plain"))),
        line=1,
    ))


def test_empty_list_item_gets_an_empty_paragraph():
    assert convert("-\n- b\n") == doc(bullets(item(para()), item(para(text("b"))), line=1))


def test_list_item_with_several_blocks():
    assert convert("- a\n\n  para\n\n      code\n") == doc(bullets(
        item(para(text("a")), para(text("para")), code("code")), tight=False, line=1,
    ))


def test_list_lines_with_an_interrupting_heading():
    assert [block["attrs"]["line"] for block in convert("- a\n- b\n# H\n")["content"]] == [1, 3]


# --- code blocks ---------------------------------------------------------------------------


def test_fenced_code_keeps_text_and_first_info_word():
    assert convert("```python title=x\nprint(1)\n\n```\n") == doc(code("print(1)\n", "python", line=1))


def test_fenced_code_highlight_is_precomputed():
    [block] = convert("```python\nprint(1)\n```\n")["content"]
    assert '<span class="nb">print</span>' in block["attrs"]["highlight"]


def test_empty_fence():
    assert convert("```\n```\n") == doc(code("", line=1))


def test_tilde_fence():
    assert convert("~~~js\nx\n~~~\n") == doc(code("x", "js", line=1))


def test_indented_code():
    assert convert("    a\n      b\n") == doc(code("a\n  b", line=1))


def test_unknown_language_has_no_highlight():
    assert convert("```nosuchlang\nx\n```\n")["content"][0]["attrs"]["highlight"] == ""


def test_code_text_is_not_decoded():
    assert convert("```\n&amp; <b>\n```\n") == doc(code("&amp; <b>", line=1))


# --- tables --------------------------------------------------------------------------------


def test_table_with_alignment():
    markdown = "| a | b | c | d |\n|:--|:-:|--:|---|\n| 1 | 2 | 3 | 4 |\n"
    aligns = ["left", "center", "right", None]
    assert convert(markdown) == doc(table(
        row(*(cell("table_header", text(name), align=a) for name, a in zip("abcd", aligns))),
        row(*(cell("table_cell", text(value), align=a) for value, a in zip("1234", aligns))),
        line=1,
    ))


def test_table_with_header_only():
    assert convert("| a |\n|---|\n") == doc(table(row(cell("table_header", text("a"))), line=1))


def test_table_cells_keep_marks_and_unescape_pipes_in_code():
    assert convert("| `a\\|b` | **x** |\n|---|---|\n| c | |\n") == doc(table(
        row(cell("table_header", text("a|b", CODE)), cell("table_header", text("x", STRONG))),
        row(cell("table_cell", text("c")), cell("table_cell")),
        line=1,
    ))


def test_ragged_table_is_kept_as_source(monkeypatch):
    original = docmodel._table_row

    def drop_last_body_cell(ctx, cells, kind):
        node = original(ctx, cells, kind)
        if kind == "table_cell":
            node["content"].pop()
        return node

    monkeypatch.setattr(docmodel, "_table_row", drop_last_body_cell)
    assert convert("a | b\n--|--\n1 | 2\n") == doc(html_block("a | b\n--|--\n1 | 2", line=1))


# --- images ---------------------------------------------------------------------------------


def test_image_resolves_display_src_and_flattens_alt(tmp_path):
    [node] = convert_in('![alt *em* `c`](<a b.png> "T")', tmp_path)["content"][0]["content"]
    assert node == image("a%20b.png", (tmp_path / "a b.png").as_uri(), "alt em c", "T")


def test_image_without_base_dir_keeps_src():
    assert only_inline("![x](img/a.png)") == [image("img/a.png", alt="x")]


def test_web_and_drive_letter_images(tmp_path):
    inline = convert_in("![w](https://x.y/a.png) ![d](C:/pics/b.png)", tmp_path)["content"][0]["content"]
    assert inline[0] == image("https://x.y/a.png", alt="w")
    assert inline[2] == image("C:/pics/b.png", Path("C:/pics/b.png").as_uri(), "d")


def test_linked_badge_image():
    assert only_inline("[![ci](b.svg)](http://x)") == [image("b.svg", alt="ci", marks=[link("http://x")])]


def test_reference_image():
    assert only_inline("![r][i]\n\n[i]: c.png 'T'") == [image("c.png", alt="r", title="T")]


def test_unsafe_image_keeps_its_alt_text():
    assert only_inline("a ![x](javascript:y) b") == [text("a x b")]
    assert convert("![](javascript:y)") == doc(para(line=1))


# --- raw HTML --------------------------------------------------------------------------------


def test_html_blocks_keep_source_without_trailing_newline():
    assert convert("<div>\n*x*\n</div>\n\n<!-- c -->\n") == doc(
        html_block("<div>\n*x*\n</div>", line=1), html_block("<!-- c -->", line=5)
    )


def test_inline_html_keeps_marks():
    assert only_inline("**a <b>x</b>** <!-- y -->") == [
        text("a ", STRONG), html_inline("<b>", STRONG), text("x", STRONG), html_inline("</b>", STRONG),
        text(" "), html_inline("<!-- y -->"),
    ]


# --- footnotes -------------------------------------------------------------------------------


def test_footnote_refs_and_definitions():
    markdown = "A[^1] B[^note] C[^1]\n\n[^1]: first\n    more\n\n[^note]: second *em*\n\n[^unused]: never\n"
    assert convert(markdown) == doc(
        para(text("A"), footnote_ref("1"), text(" B"), footnote_ref("note"), text(" C"), footnote_ref("1"), line=1),
        footnote_def("1", "[^1]: first\n    more", 3),
        footnote_def("note", "[^note]: second *em*", 6),
        footnote_def("unused", "[^unused]: never", 8),
    )


def test_footnote_ref_uses_the_label_of_its_definition():
    assert convert("X[^Note]\n\n[^note]: y\n")["content"][0]["content"] == [text("X"), footnote_ref("note")]


def test_undefined_footnote_ref_stays_text():
    assert only_inline("X[^nope]") == [text("X[^nope]")]


def test_footnote_definitions_follow_source_order():
    content = convert("[^b]: B\n\n[^a]: A\n\nx[^a][^b]\n")["content"]
    assert [block["type"] for block in content] == ["paragraph", "footnote_def", "footnote_def"]
    assert content[0]["attrs"]["line"] == 5
    assert [block["attrs"]["label"] for block in content[1:]] == ["b", "a"]


def test_first_footnote_definition_wins():
    assert convert("x[^a]\n\n[^a]: one\n\n[^a]: two\n")["content"][1:] == [footnote_def("a", "[^a]: one", 3)]


def test_footnote_only_document_gets_an_empty_paragraph():
    assert convert("[^a]: x\n") == doc(para(line=1), footnote_def("a", "[^a]: x", 1))


def test_front_matter_shifts_footnote_lines():
    content = convert("x[^a]\n\n[^a]: n\n", "---\na: 1\n---\n")["content"]
    assert [block["attrs"]["line"] for block in content] == [1, 4, 6]


def test_fallback_source_stops_at_a_footnote_definition(monkeypatch):
    monkeypatch.delitem(docmodel._BLOCKS, "block_code")
    assert convert("```\nx\n```\n[^a]: n\n\ny[^a]\n")["content"] == [
        html_block("```\nx\n```", line=1),
        para(text("y"), footnote_ref("a"), line=6),
        footnote_def("a", "[^a]: n", 4),
    ]


# --- whole documents -------------------------------------------------------------------------


def test_repo_documents_map_without_fallback():
    """Every construct in the project's own docs has a node; html_block only holds real HTML."""
    root = Path(__file__).resolve().parent.parent
    paths = [root / "README.md", *sorted((root / "docs").rglob("*.md"))]
    assert len(paths) >= 5
    for path in paths:
        front, body = frontmatter.split(path.read_text(encoding="utf-8").replace("\r\n", "\n"))
        for block in convert(body, front)["content"]:
            if block["type"] == "html_block":
                assert block["attrs"]["source"].lstrip().startswith("<"), (path, block["attrs"]["line"])
````

- [x] **Step 6: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_docmodel.py -v`
Expected: 32 failed, 54 passed. Lists, code, tables, images, raw HTML and
footnote references still come out as `html_block`, and no `footnote_def` is
produced.

- [x] **Step 7: Replace `mdviewer/core/docmodel.py`**

Replace the whole file with:

```python
"""Markdown -> ProseMirror document JSON for the Rendered editor (spec 6.3, 6.4).

Parses with mistune's AST and render.py's plugin list, and returns exactly what
ProseMirror's toJSON() gives for the same document: every declared attr present
(LINE_ATTR is None below the top level), empty content and marks omitted,
adjacent text nodes with equal marks merged, marks in docschema.MARKS order.
A top-level block containing anything this module cannot map becomes a protected
html_block holding its source text, so nothing is lost. Footnote definitions
become footnote_def nodes at the end of the document, in source order.
"""

import html
import re
from bisect import bisect_left
from dataclasses import dataclass
from pathlib import Path

import mistune
from mistune.plugins import import_plugin
from mistune.util import unikey

from mdviewer.core import docschema, urls
from mdviewer.core.render import PLUGINS, highlight_code

# CommonMark entity references (the ';' is required); html.unescape decodes each match.
_ENTITY = re.compile(r"&(?:#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});")
_MARK_RANK = {name: rank for rank, name in enumerate(docschema.MARKS)}
# mistune inline token -> mark without attrs.
_SIMPLE_MARKS = {"strong": "strong", "emphasis": "em", "strikethrough": "strike"}
# mistune's block rule for "[^label]: text" (footnotes plugin) and where we keep what it matched.
_FOOTNOTE_RULE = "ref_footnote"
_FOOTNOTE_ENV = "mdviewer_footnote_defs"


class _Unmappable(Exception):
    """A token with no document node; its top-level block is kept as source."""


@dataclass
class _Footnote:
    label: str  # as written in the definition
    source: str  # the definition's text, without trailing newlines
    pos: int  # offset of the definition in the body


@dataclass
class _Context:
    base_dir: Path | None
    labels: dict[str, str]  # mistune footnote key -> label as written in its definition


# --- mistune with block start offsets -------------------------------------------
# mistune's AST has no positions. These subclasses tag each top-level token with
# "_pos", the offset where its block starts. Rules record m.start() while they run
# (a stack: the list rule may parse an interrupting block on the same state), and
# paragraphs and indented code are added while state.cursor is still at their start.
# Footnote definitions produce no token; their source is recorded in state.env.
# (mistune only recognizes them at the top level; nested ones are link definitions.)


class _Tokens(list):
    def __init__(self, state: "_State"):
        super().__init__()
        self._state = state

    def _tag(self, token: dict) -> None:
        starts = self._state.block_starts
        token.setdefault("_pos", starts[-1] if starts else self._state.cursor)

    def append(self, token: dict) -> None:
        self._tag(token)
        super().append(token)

    def insert(self, index: int, token: dict) -> None:
        self._tag(token)
        super().insert(index, token)


class _State(mistune.BlockState):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.block_starts: list[int] = []
        if parent is None:
            self.tokens = _Tokens(self)


class _BlockParser(mistune.BlockParser):
    state_cls = _State

    def parse_method(self, m, state):
        if state.parent is not None:
            return super().parse_method(m, state)
        state.block_starts.append(m.start())
        try:
            end = super().parse_method(m, state)
        finally:
            state.block_starts.pop()
        if m.lastgroup == _FOOTNOTE_RULE:
            defs = state.env.setdefault(_FOOTNOTE_ENV, {})
            key = unikey(m.group("footnote_key"))
            if key not in defs:  # mistune also keeps the first definition
                source = state.src[m.start() : end].rstrip("\n")
                defs[key] = _Footnote(m.group("footnote_key"), source, m.start())
        return end


def _parse(body: str) -> tuple[list[dict], dict[str, _Footnote]]:
    markdown = mistune.Markdown(
        renderer=None,
        block=_BlockParser(),
        inline=mistune.InlineParser(),
        plugins=[import_plugin(name) for name in PLUGINS],
    )
    tokens, state = markdown.parse(body)
    return tokens, state.env.get(_FOOTNOTE_ENV, {})


# --- public API -----------------------------------------------------------------


def from_markdown(body: str, front: str | None = None, base_dir: Path | None = None) -> dict:
    """Document JSON for `body`; `front` (from frontmatter.split) becomes a front_matter node.

    base_dir is the folder image paths resolve against (display_src); None for Untitled."""
    offset = front.count("\n") if front is not None else 0
    newlines = [m.start() for m in re.finditer("\n", body)]

    def line(pos: int) -> int:
        return offset + bisect_left(newlines, pos) + 1

    tokens, footnotes = _parse(body)
    ctx = _Context(base_dir, {key: note.label for key, note in footnotes.items()})
    note_starts = sorted(note.pos for note in footnotes.values())
    blocks: list[dict] = []
    for index, token in enumerate(tokens):
        if token["type"] in ("blank_line", "footnotes"):  # footnotes: rebuilt from the definitions
            continue
        start = token["_pos"]
        end = tokens[index + 1].get("_pos", len(body)) if index + 1 < len(tokens) else len(body)
        try:
            node = _block(ctx, token)
        except _Unmappable:
            # The slice may run into footnote definitions; those become their own nodes.
            end = next((pos for pos in note_starts if start < pos < end), end)
            source = body[start:end].rstrip("\n")
            if not source.strip():
                continue
            node = _node("html_block", {"source": source})
        node["attrs"][docschema.LINE_ATTR] = line(start)
        blocks.append(node)
    if not blocks:
        blocks.append(_node("paragraph", {docschema.LINE_ATTR: offset + 1}))
    if front is not None:
        blocks.insert(0, _node("front_matter", {"source": front, docschema.LINE_ATTR: 1}))
    for note in sorted(footnotes.values(), key=lambda note: note.pos):
        attrs = {"label": note.label, "source": note.source, docschema.LINE_ATTR: line(note.pos)}
        blocks.append(_node("footnote_def", attrs))
    return {"type": "doc", "content": blocks}


# --- blocks ---------------------------------------------------------------------


def _node(kind: str, attrs: dict | None = None, content: list | None = None) -> dict:
    """A node shaped like ProseMirror's toJSON(): all attrs, no empty content."""
    full = dict(attrs or {})
    if kind in docschema.TOP_LEVEL_NODES:
        full.setdefault(docschema.LINE_ATTR, None)
    node: dict = {"type": kind}
    if full:
        node["attrs"] = full
    if content:
        node["content"] = content
    return node


def _block(ctx: _Context, token: dict) -> dict:
    handler = _BLOCKS.get(token["type"])
    if handler is None:
        raise _Unmappable(token["type"])
    return handler(ctx, token)


def _blocks(ctx: _Context, tokens: list[dict]) -> list[dict]:
    """Child blocks without blank lines; an empty container gets one empty paragraph."""
    nodes = [_block(ctx, token) for token in tokens if token["type"] != "blank_line"]
    return nodes or [_node("paragraph")]


def _paragraph(ctx: _Context, token: dict) -> dict:
    return _node("paragraph", content=_inline(ctx, token["children"]))


def _heading(ctx: _Context, token: dict) -> dict:
    return _node("heading", {"level": token["attrs"]["level"]}, _inline(ctx, token["children"]))


def _block_quote(ctx: _Context, token: dict) -> dict:
    return _node("blockquote", content=_blocks(ctx, token["children"]))


def _thematic_break(ctx: _Context, token: dict) -> dict:
    return _node("horizontal_rule")


def _list(ctx: _Context, token: dict) -> dict:
    items = [_list_item(ctx, child) for child in token["children"]]
    if token["attrs"]["ordered"]:
        return _node("ordered_list", {"start": token["attrs"].get("start", 1), "tight": token["tight"]}, items)
    return _node("bullet_list", {"tight": token["tight"]}, items)


def _list_item(ctx: _Context, token: dict) -> dict:
    if token["type"] == "task_list_item":
        checked = token["attrs"]["checked"]
    elif token["type"] == "list_item":
        checked = None
    else:
        raise _Unmappable(token["type"])
    return _node("list_item", {"checked": checked}, _blocks(ctx, token["children"]))


def _code_block(ctx: _Context, token: dict) -> dict:
    raw = token["raw"]
    code = raw[:-1] if raw.endswith("\n") else raw  # the newline before the closing fence
    info = (token.get("attrs") or {}).get("info") or ""
    language = info.split(None, 1)[0] if info.strip() else ""
    content = [{"type": "text", "text": code}] if code else None
    return _node("code_block", {"language": language, "highlight": highlight_code(code, language)}, content)


def _table(ctx: _Context, token: dict) -> dict:
    rows: list[dict] = []
    for part in token["children"]:
        if part["type"] == "table_head":
            rows.append(_table_row(ctx, part["children"], "table_header"))
        elif part["type"] == "table_body":
            rows.extend(_table_row(ctx, row["children"], "table_cell") for row in part["children"])
        else:
            raise _Unmappable(part["type"])
    if any(len(row["content"]) != len(rows[0]["content"]) for row in rows):
        raise _Unmappable("ragged table")  # mistune never produces one; keep the source if it does
    return _node("table", content=rows)


def _table_row(ctx: _Context, cells: list[dict], kind: str) -> dict:
    content = []
    for cell in cells:
        inline = _inline(ctx, cell["children"])
        for node in inline:  # GFM: "\|" inside a code span in a table is a literal pipe
            if node["type"] == "text" and {"type": "code"} in node.get("marks", []):
                node["text"] = node["text"].replace("\\|", "|")
        content.append(_node(kind, {"align": cell["attrs"]["align"]}, inline))
    return _node("table_row", content=content)


def _html_block(ctx: _Context, token: dict) -> dict:
    return _node("html_block", {"source": token["raw"].rstrip("\n")})


_BLOCKS = {
    "paragraph": _paragraph,
    "block_text": _paragraph,  # tight list items
    "heading": _heading,
    "block_quote": _block_quote,
    "thematic_break": _thematic_break,
    "list": _list,
    "block_code": _code_block,
    "table": _table,
    "block_html": _html_block,
}


# --- inline ---------------------------------------------------------------------


def _inline(ctx: _Context, children: list[dict]) -> list[dict]:
    nodes: list[dict] = []
    _walk_inline(ctx, children, {}, nodes)
    merged: list[dict] = []
    for node in nodes:
        previous = merged[-1] if merged else None
        if (
            previous is not None
            and previous["type"] == node["type"] == "text"
            and previous.get("marks") == node.get("marks")
        ):
            previous["text"] += node["text"]
        else:
            merged.append(node)
    return merged


def _walk_inline(ctx: _Context, children: list[dict], marks: dict[str, dict | None], out: list[dict]) -> None:
    """Append inline nodes to `out`; `marks` maps each active mark name to its attrs (or None)."""
    for child in children:
        kind = child["type"]
        if kind == "text":
            _text(_decode(child["raw"]), marks, out)
        elif kind == "softbreak":
            _text(" ", marks, out)
        elif kind == "linebreak":
            out.append(_marked({"type": "hard_break"}, marks))
        elif kind == "codespan":
            _text(child["raw"], {**marks, "code": None}, out)
        elif kind in _SIMPLE_MARKS:
            _walk_inline(ctx, child["children"], {**marks, _SIMPLE_MARKS[kind]: None}, out)
        elif kind == "link":
            _walk_inline(ctx, child["children"], _with_link(child["attrs"], marks), out)
        elif kind in _INLINE:
            _INLINE[kind](ctx, child, marks, out)
        else:
            raise _Unmappable(kind)


def _with_link(attrs: dict, marks: dict[str, dict | None]) -> dict[str, dict | None]:
    href = attrs["url"]
    if not urls.is_safe(href):
        return marks  # keep the text, drop the link
    title = attrs.get("title")
    return {**marks, "link": {"href": href, "title": None if title is None else _decode(title)}}


def _image(ctx: _Context, token: dict, marks: dict[str, dict | None], out: list[dict]) -> None:
    src = token["attrs"]["url"]
    alt = _plain_text(token["children"])
    if not urls.is_safe(src):
        _text(alt, marks, out)  # keep what a reader would see, drop the image
        return
    title = token["attrs"].get("title")
    attrs = {
        "src": src,
        "display_src": urls.resolve(src, ctx.base_dir),
        "alt": alt,
        "title": None if title is None else _decode(title),
    }
    out.append(_marked({"type": "image", "attrs": attrs}, marks))


def _html_inline(ctx: _Context, token: dict, marks: dict[str, dict | None], out: list[dict]) -> None:
    out.append(_marked({"type": "html_inline", "attrs": {"source": token["raw"]}}, marks))


def _footnote_ref(ctx: _Context, token: dict, marks: dict[str, dict | None], out: list[dict]) -> None:
    label = ctx.labels.get(token["raw"], token["raw"])
    out.append(_marked({"type": "footnote_ref", "attrs": {"label": label}}, marks))


# mistune inline token -> handler(ctx, token, marks, out) for tokens that become inline nodes.
_INLINE = {
    "image": _image,
    "inline_html": _html_inline,
    "footnote_ref": _footnote_ref,
}


def _plain_text(children: list[dict]) -> str:
    """Image alt text: the visible text of the inline tokens, without formatting."""
    parts = []
    for child in children:
        if child["type"] == "text":
            parts.append(_decode(child["raw"]))
        elif child["type"] in ("softbreak", "linebreak"):
            parts.append(" ")
        elif "children" in child:
            parts.append(_plain_text(child["children"]))
        else:  # codespan, inline_html, footnote_ref
            parts.append(child.get("raw", ""))
    return "".join(parts)


def _text(text: str, marks: dict[str, dict | None], out: list[dict]) -> None:
    if text:
        out.append(_marked({"type": "text", "text": text}, marks))


def _marked(node: dict, marks: dict[str, dict | None]) -> dict:
    if marks:
        node["marks"] = [
            {"type": name} if attrs is None else {"type": name, "attrs": dict(attrs)}
            for name, attrs in sorted(marks.items(), key=lambda item: _MARK_RANK[item[0]])
        ]
    return node


def _decode(raw: str) -> str:
    return _ENTITY.sub(lambda m: html.unescape(m.group()), raw)
```

- [x] **Step 8: Run the document-model tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_docmodel.py -v`
Expected: 86 passed.

- [x] **Step 9: Run the full suite, the Qt-import check and the UI smoke**

Run:

```bash
.venv/Scripts/python -m pytest -v
rg -n "import (PySide|Qt)|from PySide" mdviewer/core tests
.venv/Scripts/python scripts/smoke_ui.py
```

Expected: all tests pass; the `rg` line prints nothing; `SMOKE OK` (the
preview's `_Renderer` is unchanged).

- [x] **Step 10: Commit**

```bash
git add mdviewer/core/render.py mdviewer/core/docmodel.py tests/test_render.py tests/test_docmodel.py
git commit -m "feat: convert lists, code, tables, images and protected blocks to document JSON"
```

**Review Focus:**

- Every mistune token type the v1 plugin list can emit has a handler:
  - block: `paragraph`, `block_text`, `heading`, `block_quote`,
    `thematic_break`, `list`, `list_item`, `task_list_item`, `block_code`,
    `table`, `block_html`
  - inline: `text`, `softbreak`, `linebreak`, `codespan`, `strong`,
    `emphasis`, `strikethrough`, `link`, `image`, `inline_html`,
    `footnote_ref`
  - plus `blank_line` and `footnotes`, which are skipped
- Footnote definitions:
  - captured only on the root state, first definition per key
  - all emitted (including unreferenced ones) at the end in source order
  - never duplicated inside an `html_block` fallback
- `highlight_code` never wraps or inlines colors, and keeps the text
  byte-exact. The highlight markup goes into the document only as data;
  Pygments escapes the code text.
- Unsafe image sources never reach `display_src`: the image is replaced by
  its alt text.
- The Task 4 tests still pass unchanged (`_BLOCKS` and `_SIMPLE_MARKS` keep
  their names).

### Task 6: Document -> Markdown, text and structure

**Status: steps detailed.** All code and tests below were run before being
written into this plan, against mistune 3.4.0 with the Task 2-5 modules taken
from this plan. Results:
- `tests/test_serialize.py`: 185 passed; the full suite: 540 passed (355 from
  Tasks 2-5 and v1, plus these 185).
- Twelve deliberate breaks each make tests fail: no `!` escape, no split at
  link edges, no line-start escapes, no `https\:` escape, no entity after a
  hard break, bare URL before a hard break, no whitespace expelling, strike
  not outermost, no `-=` underline escape, no `&` escape, no line-edge
  stripping, no backslash escape.
- A seeded random round trip (3000 paragraphs of tricky text under random
  marks) is part of the tests. Wider exploratory runs (24,000 paragraphs with
  strong or em, plus runs mixing both) found only the known limits listed
  below.

**Findings about mistune 3.4.0 that shape this task:**

- **Backslashes** only escape ASCII punctuation: `a\b` and `C:\Users` stay
  literal, and a `\` at the very end of a paragraph is literal too. A `\`
  before a hard break's `\` must be doubled, or the break is lost.
- **Bare URLs.** The `url` plugin links `https?://...` anywhere, even mid-word
  (`ahttps://x.y`), and **inside link text** it swallows the markup up to the
  next `]` (`[**https://x.y**](u)` loses the bold). So `https://` in text is
  always written `https\://`. A bare URL followed directly by a hard break
  takes the break's `\` into the URL.
- **Line edges.** Spaces and tabs at the start and end of a paragraph line are
  stripped; after a hard break **every** Unicode whitespace character is
  stripped (NBSP included), while NBSP at the start of a paragraph is kept.
  Spaces before a `\` hard break are kept.
- **Lines inside a paragraph** (after a hard break) can still turn into
  blocks: `===` or `---` makes the paragraph a setext heading (mistune also
  accepts mixed `-=`), and `a|b\` followed by `-|-` becomes a table.
- **`!` before a link** makes an image: `x![a](u)`.
- **Strikethrough** (`~~`) has no flanking rules, unlike `*`: a delimiter next
  to punctuation or other markup still works. Strong/em delimiters next to
  other markup count as punctuation (`~~a~~***c` does not close).
- **Link destinations** decode entities even after a backslash
  (`u\&amp;v` gives `u&v`); `&amp;amp;` keeps a literal `&amp;`. Destinations
  come back percent-encoded (`<a b>` gives `a%20b`), so a link typed with a
  space is normalized on its first save and stable after that.
- `**a***b*`, `*a***b**`, `***a***` and nested runs parse correctly; runs of
  four or more `*` from strong/em runs that touch or cross do not.

**Design decisions:**

- **API.** `to_markdown(doc)` is the body only (spec Key Interfaces).
  `front_matter(doc)` returns the `front_matter` node's `source` verbatim, or
  `None`. `to_text(doc)` is the whole buffer, `frontmatter.join(front, body)`,
  and is what Tasks 13-14 call on a pull. When the front-matter block ended the
  file without a newline (`"---\na: 1\n---"`) and the body is not empty,
  `to_text` adds the `\n`; otherwise the first body line would join the
  closing `---`.
- **Unknown node types raise `ValueError`** naming the type. Spec section 7:
  a serializer exception aborts the pending action. Task 7 adds lists, code,
  tables, images and the protected nodes to the same tables.
- **Blocks:** one blank line between blocks, output ends with exactly one
  `\n`, `""` when nothing is left. Empty paragraphs are dropped (Markdown
  cannot hold them), so `doc(para())` gives `""`. ATX headings only; an empty
  heading is `#`. Block quotes prefix every line with `> ` (`>` on blank
  lines); an empty quote is `>`. The rule is `---`.
- **Inline normalization** (all invisible in the rendered output):
  - `\n` inside text becomes a space; a hard break in a heading becomes a
    space.
  - Spaces and tabs at line edges are dropped; trailing hard breaks are
    dropped (a block cannot end with one).
  - Leading/trailing whitespace of a strong/em/strike run moves outside the
    run, so delimiters always touch text.
  - Whitespace other than space/tab right after a hard break is written as an
    entity: `&nbsp;` for NBSP, numeric (`&#8195;`) for others.
- **Marks:**
  - `**strong**`, `*em*`, `~~strike~~`, `` `code` ``. Code is innermost; its
    span uses a backtick run longer than any inside, padded with spaces when
    the code starts or ends with a backtick or with a space on both sides.
  - Links open outermost, then strike, then longer strong/em runs outside
    shorter ones (strong first on ties). Strong/em runs are closed and
    reopened at every edge of a link or strike run (`**x**[**y**](u)` rather
    than `**x[y](u)**`). This never changes the document, because adjacent
    text with equal marks merges back, and it keeps `*` delimiters next to
    text.
- **Links:**
  - `[text](href "title")`. The destination goes in `<...>` when it holds
    whitespace, control characters, `<` or `>`; otherwise backslashes before
    punctuation are doubled and unbalanced parentheses escaped. A `&` that
    starts an entity is written `&amp;` in destinations and titles.
  - Autolinks, only for an untitled link that is its node's only mark and
    covers just that node: an http(s) URL whose text equals its href stays
    bare when what follows is the line end, or closing punctuation then
    whitespace (the case docmodel produces from bare URLs); otherwise it
    becomes `<href>`. Other text-equals-href URIs become `<href>`; a mailto:
    link whose text is the address becomes `<address>`.
- **Escaping** (minimal and context-sensitive; spec 6.5). Text is escaped
  after the markup is laid out, knowing the output character on each side:
  - always: `*`, `` ` ``, `[`, and the `:` of `http://` / `https://`
  - `]` inside link text only
  - `\` before ASCII punctuation (including the next piece's markup)
  - `_` unless between two alphanumerics (`snake_case` stays)
  - `~` next to another `~`
  - `!` before `[`
  - `<` before a letter, `/`, `!` or `?`
  - `&` that starts an entity reference (docmodel decodes them)
  - at a line start (paragraph start or after a hard break): `#`-headings,
    `-`/`+` bullets, `1.`/`1)` items (the delimiter: `1\.`), `>`; and a whole
    line that would be a setext underline, thematic break or table delimiter
    row (its first `-` or `=`)
  - in headings: only a trailing `#` run that would close the heading
  - `|` is left alone outside tables (Task 7 escapes it in cells).
- **Known limits** (CommonMark/mistune cannot express these with `*`; the
  random test's generator avoids them, and docmodel never produces them, so
  they only arise from editing in Rendered mode):
  - a strong/em run that starts or ends with punctuation or a code span
    directly next to a letter or digit outside it (`**(a)**b`)
  - strong and em runs that touch or cross so that four or more `*` meet
    (bold `a`, bold-italic `b`, italic `c` with no spaces between)
  - a link at the very start of a paragraph whose text holds a code span
    containing `]:` (read as a link reference definition).

**Files:**
- Create: `mdviewer/core/serialize.py`
- Test: `tests/test_serialize.py`

**Interfaces:**
- Consumes:
  - `frontmatter.join` and `frontmatter.split` (Task 3; `split` in tests)
  - `docmodel.from_markdown` (Tasks 4-5), in tests only
  - the document shape of Task 2 (`docschema`); marks may come in any order
- Produces:
  - `serialize.to_markdown(doc: dict) -> str`: body Markdown, `"\n"`
    newlines, ends with one `\n`, or `""`
  - `serialize.front_matter(doc: dict) -> str | None`
  - `serialize.to_text(doc: dict) -> str`: the buffer text for a pull
    (Tasks 13-14)
  - `ValueError` for node types not handled yet
  - For Task 7, which extends this file:
    - `_BLOCKS` maps a block type to `fn(node) -> str` (the block's lines
      without a trailing newline; `""` means "nothing"); `_blocks(nodes)`
      joins blocks with one blank line. List items reuse `_blocks` for their
      content and indent its lines.
    - `_content(node, in_link)` returns the piece for an inline node:
      `(text, in_link)` for text to escape, `(markup, None)` for literal
      markup. Task 7 adds `image`, `footnote_ref` and `html_inline` there as
      markup pieces. A marked image is wrapped by `_pieces` like text.
    - `_inline(nodes, heading=False)` is where table cells add `|` escaping
      (including `\|` inside code spans).
    - `_task6_only` in `tests/test_serialize.py` limits the repo round trip
      to the node types handled so far; Task 7 widens it to all types.

- [x] **Step 1: Write the failing tests**

Create `tests/test_serialize.py` (the block uses a four-backtick fence because
a test string contains triple backticks):

````python
import random
from pathlib import Path

import pytest

from mdviewer.core import frontmatter
from mdviewer.core.docmodel import from_markdown
from mdviewer.core.serialize import front_matter, to_markdown, to_text


def doc(*blocks):
    return {"type": "doc", "content": list(blocks)}


def para(*inline, line=None):
    node = {"type": "paragraph", "attrs": {"line": line}}
    if inline:
        node["content"] = list(inline)
    return node


def heading(level, *inline):
    node = {"type": "heading", "attrs": {"level": level, "line": None}}
    if inline:
        node["content"] = list(inline)
    return node


def quote(*blocks):
    return {"type": "blockquote", "attrs": {"line": None}, "content": list(blocks)}


def rule():
    return {"type": "horizontal_rule", "attrs": {"line": None}}


def text(value, *marks):
    node = {"type": "text", "text": value}
    if marks:
        node["marks"] = list(marks)
    return node


def hard_break(*marks):
    node = {"type": "hard_break"}
    if marks:
        node["marks"] = list(marks)
    return node


STRONG, EM, STRIKE, CODE = ({"type": name} for name in ("strong", "em", "strike", "code"))


def link(href, title=None):
    return {"type": "link", "attrs": {"href": href, "title": title}}


def inline_md(*inline):
    """Markdown for a one-paragraph document, without the final newline."""
    out = to_markdown(doc(para(*inline)))
    assert out.endswith("\n") and not out.endswith("\n\n")
    return out[:-1]


def round_trip(markdown):
    return to_markdown(from_markdown(markdown))


def without_lines(node):
    """The node with every line attr set to None (line numbers move when text is normalized)."""
    copy = dict(node)
    if "attrs" in copy and "line" in copy["attrs"]:
        copy["attrs"] = {**copy["attrs"], "line": None}
    if "content" in copy:
        copy["content"] = [without_lines(child) for child in copy["content"]]
    return copy


# --- documents and blocks ---------------------------------------------------------------


@pytest.mark.parametrize("body", [doc(para()), doc(para(), para()), from_markdown(""), from_markdown("\n\n")])
def test_empty_body_is_the_empty_string(body):
    assert to_markdown(body) == ""


def test_blocks_are_separated_by_one_blank_line_and_end_with_one_newline():
    assert to_markdown(doc(para(text("a"), line=1), heading(2, text("b")), rule(), para(text("c")))) == (
        "a\n\n## b\n\n---\n\nc\n"
    )


def test_empty_paragraphs_are_dropped():
    assert to_markdown(doc(para(text("a")), para(), para(hard_break()), para(text("b")))) == "a\n\nb\n"


@pytest.mark.parametrize("level", [1, 2, 3, 4, 5, 6])
def test_atx_headings(level):
    assert to_markdown(doc(heading(level, text("Title")))) == "#" * level + " Title\n"


def test_empty_heading():
    assert to_markdown(doc(heading(3))) == "###\n"


def test_setext_heading_becomes_atx():
    assert round_trip("Title\n=====\n\nSub\n---\n") == "# Title\n\n## Sub\n"


def test_hard_break_in_heading_becomes_a_space():
    assert to_markdown(doc(heading(1, text("a"), hard_break(), text("b")))) == "# a b\n"


@pytest.mark.parametrize("content, expected", [
    ("C#", "# C#"),
    ("a #", "# a \\#"),
    ("#", "# \\#"),
    ("a ##  ", "# a \\##"),
    ("# b", "# # b"),
    ("- not a list", "# - not a list"),
])
def test_heading_text_escapes_only_a_closing_sequence(content, expected):
    assert to_markdown(doc(heading(1, text(content)))) == expected + "\n"


def test_blockquote_with_several_paragraphs():
    assert to_markdown(doc(quote(para(text("a")), para(text("b"))))) == "> a\n>\n> b\n"


def test_nested_blockquote_and_hard_break_inside():
    assert to_markdown(doc(quote(quote(para(text("a"), hard_break(), text("b")))))) == "> > a\\\n> > b\n"


def test_empty_blockquote():
    assert to_markdown(doc(quote(para()))) == ">\n"


def test_horizontal_rule_and_line_attrs_are_ignored():
    assert to_markdown(doc({"type": "horizontal_rule", "attrs": {"line": 7}})) == "---\n"


def test_unknown_block_raises():
    with pytest.raises(ValueError, match="'callout'"):
        to_markdown(doc({"type": "callout"}))


def test_unknown_inline_node_raises():
    with pytest.raises(ValueError, match="'widget'"):
        to_markdown(doc(para(text("a"), {"type": "widget"})))


# --- front matter ---------------------------------------------------------------------------

FRONT = {"type": "front_matter", "attrs": {"source": "---\ntitle: x\n---\n", "line": 1}}


def test_body_excludes_front_matter():
    assert to_markdown(doc(FRONT, para(text("a")))) == "a\n"


def test_front_matter_source_is_returned_verbatim():
    assert front_matter(doc(FRONT, para())) == "---\ntitle: x\n---\n"
    assert front_matter(doc(para(text("a")))) is None


def test_to_text_joins_front_matter_and_body():
    assert to_text(doc(FRONT, heading(1, text("Hi")))) == "---\ntitle: x\n---\n# Hi\n"
    assert to_text(doc(FRONT, para())) == "---\ntitle: x\n---\n"
    assert to_text(doc(para(text("a")))) == "a\n"


def test_to_text_adds_a_newline_after_front_matter_that_ended_the_file():
    front = {"type": "front_matter", "attrs": {"source": "---\na: 1\n---", "line": 1}}
    assert to_text(doc(front, para())) == "---\na: 1\n---"
    assert to_text(doc(front, para(text("x")))) == "---\na: 1\n---\nx\n"


def test_to_text_round_trips_a_file_with_front_matter():
    source = "---\ntitle: x\n---\n# Hi\n\nText\n"
    front, body = frontmatter.split(source)
    assert to_text(from_markdown(body, front)) == source


# --- marks ---------------------------------------------------------------------------------


def test_simple_marks():
    assert inline_md(text("b", STRONG), text(" "), text("i", EM), text(" "), text("s", STRIKE), text(" "),
                     text("c", CODE)) == "**b** *i* ~~s~~ `c`"


@pytest.mark.parametrize("markdown", [
    "***both***",
    "**a *b* c**",
    "*a **b** c*",
    "~~**x**~~ ~~a *b*~~",
    "**a**b and a**b**c",
    "*a***b**",
    "**a***b*",
    "**`x`** and [`y`](u)",
])
def test_nested_and_adjacent_marks_keep_their_markdown(markdown):
    assert round_trip(markdown) == markdown + "\n"


def test_whitespace_moves_outside_delimiters():
    assert inline_md(text("a"), text(" bold ", STRONG), text("b")) == "a **bold** b"
    assert inline_md(text("x "), text("y ", EM), text("z", EM, STRONG)) == "x *y **z***"


def test_spaces_and_tabs_at_line_edges_are_dropped():
    assert inline_md(text(" \t a  "), hard_break(), text("  b \t")) == "a\\\nb"


def test_newlines_in_text_become_spaces():
    assert inline_md(text("a\nb"), text("c\nd", CODE)) == "a b`c d`"


def test_hard_breaks():
    assert inline_md(text("a"), hard_break(), text("b"), hard_break(), hard_break(), text("c")) == "a\\\nb\\\n\\\nc"


def test_leading_hard_break_is_kept_and_trailing_ones_are_dropped():
    assert inline_md(hard_break(), text("a"), hard_break(), hard_break()) == "\\\na"


def test_hard_break_inside_marks():
    assert inline_md(text("a", STRONG), hard_break(STRONG), text("b", STRONG)) == "**a\\\nb**"


def test_whitespace_after_a_hard_break_is_written_as_an_entity():
    assert inline_md(text("a"), hard_break(), text("\xa0b")) == "a\\\n&nbsp;b"
    assert inline_md(text("a"), hard_break(), text("\u2003b")) == "a\\\n&#8195;b"


@pytest.mark.parametrize("code, expected", [
    ("a", "`a`"),
    ("a`b", "``a`b``"),
    ("a``b`", "``` a``b` ```"),
    ("`a", "`` `a ``"),
    (" a ", "`  a  `"),
    (" a", "` a`"),
    ("  ", "`  `"),
    ("*not em* &amp; \\", "`*not em* &amp; \\`"),
])
def test_code_spans(code, expected):
    assert inline_md(text(code, CODE)) == expected


# --- links ---------------------------------------------------------------------------------


def test_inline_links():
    assert inline_md(text("a", link("http://x", "T")), text(" "), text("b", link("y"))) == '[a](http://x "T") [b](y)'


def test_link_title_escapes_quotes_backslashes_and_entities():
    assert inline_md(text("a", link("u", 'say "hi" \\* &copy;'))) == '[a](u "say \\"hi\\" \\\\* &amp;copy;")'


@pytest.mark.parametrize("href, expected", [
    ("", "[a]()"),
    ("page.md#top", "[a](page.md#top)"),
    ("a b", "[a](<a b>)"),
    ("x<y>", "[a](<x\\<y\\>>)"),
    ("wiki/A_(b)", "[a](wiki/A_(b))"),
    ("a(b", "[a](a\\(b)"),
    ("a\\b", "[a](a\\b)"),
    ("a\\*b", "[a](a\\\\*b)"),
    ("q?x=1&copy;", "[a](q?x=1&amp;copy;)"),
])
def test_link_destinations(href, expected):
    assert inline_md(text("a", link(href))) == expected


def test_link_text_escapes_brackets():
    assert inline_md(text("a]b [c]", link("u")), text(" ]")) == "[a\\]b \\[c\\]](u) ]"


def test_link_is_outermost_and_splits_other_marks():
    assert inline_md(text("x", STRONG), text("y", STRONG, link("u")), text("z", STRONG)) == "**x**[**y**](u)**z**"
    assert inline_md(text("a", STRONG, EM, link("u"))) == "[***a***](u)"


def test_strike_is_outside_strong_and_em():
    assert inline_md(text("a", STRONG, STRIKE), text("b", STRONG)) == "~~**a**~~**b**"


@pytest.mark.parametrize("inline, expected", [
    ([text("see "), text("https://x.y/z", link("https://x.y/z")), text(".")], "see https://x.y/z."),
    ([text("https://x.y", link("https://x.y")), text("), next")], "https://x.y), next"),
    ([text("https://x.y", link("https://x.y")), text("abc")], "<https://x.y>abc"),
    ([text("https://x.y", link("https://x.y")), text(".x")], "<https://x.y>.x"),
    ([text("https://x.y", link("https://x.y")), hard_break(), text("b")], "<https://x.y>\\\nb"),
    ([text("https://x.y", link("https://x.y")), text("b", STRONG)], "<https://x.y>**b**"),
    ([text("https://x.y/a.", link("https://x.y/a."))], "<https://x.y/a.>"),
    ([text("mailto:a@b.co", link("mailto:a@b.co"))], "<mailto:a@b.co>"),
    ([text("a@b.co", link("mailto:a@b.co"))], "<a@b.co>"),
    ([text("https://x.y", link("https://x.y", "T"))], '[https\\://x.y](https://x.y "T")'),
    ([text("https://x.y", STRONG, link("https://x.y"))], "[**https\\://x.y**](https://x.y)"),
    ([text("x.y", link("https://x.y"))], "[x.y](https://x.y)"),
])
def test_autolinks(inline, expected):
    assert inline_md(*inline) == expected


def test_autolinks_round_trip():
    markdown = "Bare https://x.y/z. Angle <http://a.b> and <a@b.co>.\n"
    assert round_trip(markdown) == "Bare https://x.y/z. Angle http://a.b and <a@b.co>.\n"


# --- escaping ------------------------------------------------------------------------------


@pytest.mark.parametrize("value, expected", [
    ("2 * 3 = 6", "2 \\* 3 = 6"),
    ("snake_case_name", "snake_case_name"),
    ("_x_ and x_", "\\_x\\_ and x\\_"),
    ("a ~ b", "a ~ b"),
    ("~~x~~", "\\~\\~x\\~\\~"),
    ("`x`", "\\`x\\`"),
    ("[x] and a]b", "\\[x] and a]b"),
    ("C:\\Users\\me", "C:\\Users\\me"),
    ("a\\*b", "a\\\\\\*b"),
    ("ends with \\", "ends with \\"),
    ("&copy; &amp; &#35; AT&T &nosemi", "\\&copy; \\&amp; \\&#35; AT&T &nosemi"),
    ("a < b <c> </d> <!x <?y", "a < b \\<c> \\</d> \\<!x \\<?y"),
    ("Wow! [", "Wow! \\["),
    ("see https://x.y or http://a", "see https\\://x.y or http\\://a"),
    ("100% | 1.5 kg", "100% | 1.5 kg"),
    ("# not a heading", "\\# not a heading"),
    ("###### six", "\\###### six"),
    ("####### seven", "####### seven"),
    ("#hashtag", "#hashtag"),
    ("- item", "\\- item"),
    ("+ item", "\\+ item"),
    ("-5 degrees", "-5 degrees"),
    ("1. one", "1\\. one"),
    ("2) two", "2\\) two"),
    ("2024.", "2024\\."),
    ("1.5", "1.5"),
    ("> quote", "\\> quote"),
    ("a > b", "a > b"),
    ("---", "\\---"),
    ("- - -", "\\- - -"),
    ("===", "\\==="),
])
def test_text_escaping(value, expected):
    assert inline_md(text(value)) == expected


@pytest.mark.parametrize("inline, expected", [
    ([text("x!"), text("a", link("u"))], "x\\![a](u)"),
    ([text("C:\\"), text("b", STRONG)], "C:\\\\**b**"),
    ([text("a\\"), hard_break(), text("b")], "a\\\\\\\nb"),
    ([text("x_"), text("b", EM)], "x\\_*b*"),
    ([text("a~"), text("b", STRIKE)], "a\\~~~b~~"),
    ([text("a<"), text("b", EM)], "a<*b*"),
    ([text("1."), text("x", EM)], "1.*x*"),
    ([text("-"), text("x", STRONG)], "-**x**"),
    ([text("-")], "\\-"),
    ([text("a"), hard_break(), text("# b")], "a\\\n\\# b"),
    ([text("a"), hard_break(), text("1) b")], "a\\\n1\\) b"),
    ([text("a"), hard_break(), text("===")], "a\\\n\\==="),
    ([text("a"), hard_break(), text("-=")], "a\\\n\\-="),
    ([text("a|b"), hard_break(), text("-|-")], "a|b\\\n\\-|-"),
    ([text("a|b"), hard_break(), text(":-:|-")], "a|b\\\n:\\-:|-"),
])
def test_context_sensitive_escaping(inline, expected):
    assert inline_md(*inline) == expected


@pytest.mark.parametrize("value", [
    "2 * 3", "_x_", "~~x~~", "`x`", "[x](y)", "![x](y)", "&copy; &amp;", "<b>x</b>", "<http://x>",
    "https://x.y", "# h", "- i", "+ i", "1. i", "1) i", "> q", "---", "***", "___", "===", "\\", "a\\b",
    "\\*", "[^1]", "x | y", "~a~", "a  b", "C:\\Users\\", "<!-- c -->", "1.", "#", "*", "_", "]", "!",
])
def test_escaped_text_parses_back_to_the_same_text(value):
    assert from_markdown(to_markdown(doc(para(text(value)))))["content"][0]["content"] == [text(value)]


# --- round trips ----------------------------------------------------------------------------


@pytest.mark.parametrize("markdown, expected", [
    ("Title\n===\n", "# Title\n"),
    ("#   Spaced   #\n", "# Spaced\n"),
    ("a  \nb\n", "a\\\nb\n"),
    ("line one\nline two\n", "line one line two\n"),
    ("* * *\n", "---\n"),
    ("> a\nlazy\n", "> a lazy\n"),
    ("[t][r]\n\n[r]: http://r 'T'\n", '[t](http://r "T")\n'),
    ("&copy; &#35; \\&copy;\n", "© # \\&copy;\n"),
    ("__strong__ _em_\n", "**strong** *em*\n"),
    ("\\# \\- \\> \\[x\\]\n", "\\# - > \\[x]\n"),
])
def test_normalizing_round_trips(markdown, expected):
    assert round_trip(markdown) == expected


SNIPPETS = [
    "Hello *world* and **bold** and ~~gone~~ and `code`.",
    "# Title\n\n## Sub *em*\n\nText.",
    "> quote\n>\n> > nested\n\n---\n\nafter",
    "Line one\\\nline two  \nline three",
    "A [link](http://x \"T\") and [another](<a b>) and https://bare.example/x.",
    "Escapes: \\* \\_ \\` \\[ \\] \\# \\\\ &amp; &lt;b&gt;",
    "**[bold link](u)** then *[em link](v)*",
    "C:\\Users\\me\\file.md and snake_case_word",
]


@pytest.mark.parametrize("markdown", SNIPPETS)
def test_serialized_documents_parse_back_unchanged(markdown):
    original = from_markdown(markdown)
    once = to_markdown(original)
    assert without_lines(from_markdown(once)) == without_lines(original)
    assert round_trip(once) == once


def _task6_only(node):
    """True when the node uses only the node types this serializer handles so far."""
    if node["type"] not in {"paragraph", "heading", "blockquote", "horizontal_rule", "text", "hard_break"}:
        return False
    return all(_task6_only(child) for child in node.get("content", []))


def test_repo_text_blocks_round_trip():
    """Every paragraph, heading, quote and rule in the project's docs survives serialization."""
    root = Path(__file__).resolve().parent.parent
    paths = [root / "README.md", *sorted((root / "docs").rglob("*.md"))]
    checked = 0
    for path in paths:
        front, body = frontmatter.split(path.read_text(encoding="utf-8").replace("\r\n", "\n"))
        for block in from_markdown(body, front)["content"]:
            if not _task6_only(block):
                continue
            markdown = to_markdown(doc(block))
            assert without_lines(from_markdown(markdown))["content"] == [without_lines(block)], (path, markdown)
            checked += 1
    assert checked > 100


# --- random inline content ------------------------------------------------------------------
# Random paragraphs of tricky text under random marks must parse back to the same text and
# marks. Known limits, kept out of the generator (see the plan's Task 6 Review Focus):
# strong/em runs that start or end with punctuation or a code span next to a letter, and
# strong and em runs that touch or cross each other.

_TRICKY = list("ab ") * 4 + list("*_~`[]!<>&#\\-+=|:.()/1;\"' \t\xa0") + ["https://x.y", "&copy;", "<b>", "1. "]
_ALNUM = list("abcxyz019")
_LINKS = [link("https://x.y"), link("u%20v(", 'a "q" \\*'), link("a&amp;b*")]


def _random_inline(rng, flanked):
    nodes = []
    for _ in range(rng.randint(1, 6)):
        if rng.random() < 0.1:
            nodes.append(hard_break())
            continue
        marks = [mark for mark in (flanked, STRIKE) if rng.random() < 0.3]
        if rng.random() < 0.15:
            marks = [CODE]
        if rng.random() < 0.2:
            marks.append(rng.choice(_LINKS))
        body = "".join(rng.choice(_TRICKY) for _ in range(rng.randint(0, 5)))
        if CODE in marks or not ({flanked["type"], "strike"} & {mark["type"] for mark in marks}):
            value = body or rng.choice(_ALNUM)
        else:
            value = rng.choice(_ALNUM) + body + rng.choice(_ALNUM)
        if marks and marks[-1]["type"] == "link" and len(marks) == 1 and rng.random() < 0.3:
            value = marks[-1]["attrs"]["href"]
        nodes.append(text(value, *marks))
    return nodes


def _visible(inline):
    """Lines of (character, marks): what a reader sees. Edge spaces and tabs are dropped and
    whitespace never counts as strong/em/strike, the serializer's two normalizations."""
    lines = [[]]
    for node in inline:
        if node["type"] == "hard_break":
            lines.append([])
            continue
        marks = node.get("marks", [])
        for ch in node["text"].replace("\n", " "):
            kept = marks if CODE in marks or not ch.isspace() else [m for m in marks if m["type"] == "link"]
            lines[-1].append((ch, sorted(repr(mark) for mark in kept)))
    for line in lines:
        while line and line[0][0] in " \t" and repr(CODE) not in line[0][1]:
            line.pop(0)
        while line and line[-1][0] in " \t" and repr(CODE) not in line[-1][1]:
            line.pop()
    while lines and not lines[-1]:
        lines.pop()
    return lines


@pytest.mark.parametrize("flanked", [STRONG, EM], ids=["strong", "em"])
def test_random_inline_content_round_trips(flanked):
    rng = random.Random(6)
    for _ in range(1500):
        inline = _random_inline(rng, flanked)
        markdown = to_markdown(doc(para(*inline)))
        blocks = from_markdown(markdown)["content"]
        assert [block["type"] for block in blocks] == ["paragraph"], markdown
        assert _visible(blocks[0].get("content", [])) == _visible(inline), markdown
        assert round_trip(markdown) == (markdown or ""), markdown
````

- [x] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_serialize.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'mdviewer.core.serialize'`.

- [x] **Step 3: Write the implementation**

Create `mdviewer/core/serialize.py`:

```python
"""ProseMirror document JSON -> normalized Markdown for the Rendered editor (spec 6.5).

The inverse of core/docmodel.py: from_markdown(to_markdown(doc)) gives the same
document back, up to the normalizations of spec 6.5. Output uses "\\n" only and
ends with exactly one "\\n" ("" for an empty body); MainWindow applies the file's
newline style on save. LINE_ATTR and code_block.highlight are display-only and
ignored here.
"""

import re
import string

from mdviewer.core import frontmatter

# CommonMark entity references, as docmodel decodes them; a "&" that starts one is escaped.
_ENTITY = re.compile(r"&(?:#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});")
_ASCII_PUNCT = frozenset(string.punctuation)
# Marks whose delimiters must touch non-whitespace (CommonMark flanking rules).
_FLANKED = frozenset({"strong", "em", "strike"})
_DELIMITERS = {"strong": "**", "em": "*", "strike": "~~"}
# Links, then strike, always open outermost: their syntax has no flanking rules. Strong
# and em runs are split at every edge of a link or strike run, which never changes the
# document (equal-marked text merges back) but keeps their delimiters next to text.
_OUTER_RANK = {"link": 0, "strike": 1}

# Line starts that would begin a block: ATX heading, bullet item, ordered item.
_HEADING_START = re.compile(r"#{1,6}(?=[ \t]|$)")
_BULLET_START = re.compile(r"[-+](?=[ \t]|$)")
_ORDERED_START = re.compile(r"[0-9]{1,9}([.)])(?=[ \t]|$)")
# Whole lines that would be a setext underline, a thematic break or a table delimiter row.
_UNDERLINE = re.compile(r"[-=]+[ \t]*|[-:| \t]*-[-:| \t]*")  # mistune also takes "-=" as an underline
# Trailing "#"s of a heading's text would be read as its closing sequence.
_HEADING_CLOSE = re.compile(r"(?:^|[ \t])(#+)[ \t]*$")
# mistune's url plugin links bare http(s) URLs; it never ends one on these characters.
_BARE_URL = re.compile(r"""https?://[^\s<]+[^<.,:;"')\]\s]""")
_BARE_URL_SCHEME = re.compile(r"https?(?=://)")
_URL_TRAILING = ".,:;\"')]"
# CommonMark autolinks: <scheme:...> and <address>.
_URI_AUTOLINK = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]{1,31}:[^\s<>&\\]*")
_EMAIL_AUTOLINK = re.compile(
    r"[a-zA-Z0-9.!#$%'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*"
)


# --- public API -----------------------------------------------------------------


def to_markdown(doc: dict) -> str:
    """Normalized Markdown for the document body; "" when the body has no content.

    The front_matter node is not part of the body: see front_matter() and to_text()."""
    body = _blocks([node for node in doc.get("content", []) if node["type"] != "front_matter"])
    return body + "\n" if body else ""


def front_matter(doc: dict) -> str | None:
    """The front_matter node's source, verbatim; None when the document has none."""
    content = doc.get("content", [])
    if content and content[0]["type"] == "front_matter":
        return content[0]["attrs"]["source"]
    return None


def to_text(doc: dict) -> str:
    """The whole buffer (spec 6.4 pull): front matter verbatim, then the body.

    A front-matter block that ended the file without a newline gets one when a body follows."""
    front, body = front_matter(doc), to_markdown(doc)
    if front is not None and body and not front.endswith("\n"):
        front += "\n"
    return frontmatter.join(front, body)


# --- blocks ---------------------------------------------------------------------


def _blocks(nodes: list[dict]) -> str:
    """Blocks separated by one blank line; blocks that serialize to "" are left out."""
    return "\n\n".join(text for text in (_block(node) for node in nodes) if text)


def _block(node: dict) -> str:
    handler = _BLOCKS.get(node["type"])
    if handler is None:
        raise ValueError(f"cannot serialize a {node['type']!r} node")
    return handler(node)


def _paragraph(node: dict) -> str:
    return _inline(node.get("content", []))


def _heading(node: dict) -> str:
    text = _inline(node.get("content", []), heading=True)
    marker = "#" * node["attrs"]["level"]
    return f"{marker} {text}" if text else marker


def _blockquote(node: dict) -> str:
    inner = _blocks(node.get("content", []))
    if not inner:
        return ">"
    return "\n".join(f"> {line}" if line else ">" for line in inner.split("\n"))


def _horizontal_rule(node: dict) -> str:
    return "---"


# Node type -> serializer returning the block's lines without a trailing newline ("" = nothing).
_BLOCKS = {
    "paragraph": _paragraph,
    "heading": _heading,
    "blockquote": _blockquote,
    "horizontal_rule": _horizontal_rule,
}


# --- inline: normalization ------------------------------------------------------


def _inline(nodes: list[dict], heading: bool = False) -> str:
    """Markdown for the inline content of a paragraph or heading."""
    return _escape_pieces(_pieces(_normalize(nodes, heading)), heading)


def _marks(node: dict) -> list[dict]:
    return node.get("marks", [])


def _has_mark(node: dict, name: str) -> bool:
    return any(mark["type"] == name for mark in _marks(node))


def _text_node(text: str, marks: list[dict]) -> dict:
    node: dict = {"type": "text", "text": text}
    if marks:
        node["marks"] = marks
    return node


def _normalize(nodes: list[dict], heading: bool) -> list[dict]:
    """The inline nodes as Markdown can express them.

    Newlines in text and hard breaks in headings become spaces; spaces and tabs at
    line edges are dropped (Markdown strips them); trailing hard breaks are dropped
    (a block cannot end with one); whitespace moves out of strong/em/strike runs
    (their delimiters must touch non-whitespace); equal-marked text is merged."""
    flat: list[dict] = []
    for node in nodes:
        if node["type"] == "text":
            flat.append(_text_node(node["text"].replace("\n", " "), _marks(node)))
        elif node["type"] == "hard_break" and heading:
            flat.append(_text_node(" ", _marks(node)))
        else:
            flat.append(node)
    lines: list[list[dict]] = [[]]
    for node in flat:
        if node["type"] == "hard_break":
            lines.append([])
        lines[-1].append(node)
    out: list[dict] = []
    for line in lines:
        out.extend(_strip_line(line))
    while out and out[-1]["type"] == "hard_break":
        out.pop()
    return _merge(_expel_whitespace(out))


def _strip_line(line: list[dict]) -> list[dict]:
    """Drop spaces and tabs at both edges of one line (which may start with its hard_break)."""
    nodes = list(line)
    _strip_edge(nodes, range(len(nodes)), str.lstrip)
    _strip_edge(nodes, range(len(nodes) - 1, -1, -1), str.rstrip)
    return [node for node in nodes if node["type"] != "text" or node["text"]]


def _strip_edge(nodes: list[dict], order: range, strip) -> None:
    for i in order:
        node = nodes[i]
        if node["type"] == "hard_break":
            continue
        if node["type"] != "text" or _has_mark(node, "code"):
            return
        nodes[i] = _text_node(strip(node["text"], " \t"), _marks(node))
        if nodes[i]["text"]:
            return


def _shared(marks: list[dict], *neighbors: list[dict]) -> list[dict]:
    """`marks` without the strong/em/strike marks that some neighbor lacks."""
    return [mark for mark in marks if mark["type"] not in _FLANKED or all(mark in other for other in neighbors)]


def _expel_whitespace(nodes: list[dict]) -> list[dict]:
    """Move leading/trailing whitespace of strong/em/strike runs outside the run.

    Runs also end at the edges of links and strike runs, where _pieces closes them."""
    out: list[dict] = []
    for i, node in enumerate(nodes):
        before = _marks(nodes[i - 1]) if i > 0 and not _edge(nodes[i - 1], node) else []
        after = _marks(nodes[i + 1]) if i + 1 < len(nodes) and not _edge(node, nodes[i + 1]) else []
        if node["type"] == "hard_break":  # whitespace too: inside a run only between its parts
            marks = _shared(_marks(node), before, after)
            out.append({"type": "hard_break", "marks": marks} if marks else {"type": "hard_break"})
            continue
        if node["type"] != "text" or _has_mark(node, "code"):
            out.append(node)
            continue
        text, marks = node["text"], _marks(node)
        core = text.strip()
        if not core:
            out.append(_text_node(text, _shared(marks, before, after)))
            continue
        start, end = len(text) - len(text.lstrip()), len(text.rstrip())
        out.append(_text_node(text[:start], _shared(marks, before)))
        out.append(_text_node(core, marks))
        out.append(_text_node(text[end:], _shared(marks, after)))
    return [node for node in out if node["type"] != "text" or node["text"]]


def _merge(nodes: list[dict]) -> list[dict]:
    merged: list[dict] = []
    for node in nodes:
        previous = merged[-1] if merged else None
        if previous and previous["type"] == node["type"] == "text" and _marks(previous) == _marks(node):
            merged[-1] = _text_node(previous["text"] + node["text"], _marks(node))
        else:
            merged.append(node)
    return merged


# --- inline: marks and pieces ---------------------------------------------------
# Inline content becomes a list of pieces: (document text, inside-link flag) or
# (markup, None) for delimiters, code spans, link syntax and hard breaks. Text is
# escaped afterwards, when the output characters around each text piece are known.


def _pieces(nodes: list[dict]) -> list[tuple[str, bool | None]]:
    pieces: list[tuple[str, bool | None]] = []
    stack: list[dict] = []  # open marks, outermost first
    for i, node in enumerate(nodes):
        wanted = [mark for mark in _marks(node) if mark["type"] != "code"]
        keep = 0
        if i == 0 or not _edge(nodes[i - 1], node):  # at a link or strike edge all marks close
            while keep < len(stack) and stack[keep] in wanted:
                keep += 1
        for mark in reversed(stack[keep:]):
            pieces.append((_close(mark), None))
        del stack[keep:]
        if autolink := _autolink(nodes, i):
            pieces.append((autolink, None))
            continue
        # Link, then strike; then longer strong/em runs outside shorter ones, strong first on ties.
        opening = [mark for mark in wanted if mark not in stack]
        opening.sort(key=lambda m: (_OUTER_RANK.get(m["type"], 2), -_extent(nodes, i, m), m["type"] != "strong"))
        for mark in opening:
            pieces.append((_DELIMITERS.get(mark["type"], "["), None))
            stack.append(mark)
        pieces.append(_content(node, in_link=_link(node) is not None))
    for mark in reversed(stack):
        pieces.append((_close(mark), None))
    return pieces


def _link(node: dict) -> dict | None:
    return next((mark for mark in _marks(node) if mark["type"] == "link"), None)


def _edge(left: dict, right: dict) -> bool:
    """A link or strike run starts or ends between two adjacent nodes."""
    return _link(left) != _link(right) or _has_mark(left, "strike") != _has_mark(right, "strike")


def _extent(nodes: list[dict], index: int, mark: dict) -> int:
    """How many nodes from `index` on carry `mark`; strong/em runs stop at link and strike edges."""
    count = 1
    while index + count < len(nodes) and mark in _marks(nodes[index + count]):
        if mark["type"] not in _OUTER_RANK and _edge(nodes[index + count - 1], nodes[index + count]):
            break
        count += 1
    return count


def _content(node: dict, in_link: bool) -> tuple[str, bool | None]:
    if node["type"] == "text":
        if _has_mark(node, "code"):
            return _code_span(node["text"]), None
        return node["text"], in_link
    if node["type"] == "hard_break":
        return "\\\n", None
    raise ValueError(f"cannot serialize a {node['type']!r} node")


def _close(mark: dict) -> str:
    if mark["type"] == "link":
        return "](" + _link_target(mark["attrs"]["href"], mark["attrs"]["title"]) + ")"
    return _DELIMITERS[mark["type"]]


def _autolink(nodes: list[dict], index: int) -> str | None:
    """The node written as an autolink (spec 6.5), or None for a [text](href) link.

    Only an untitled link that is the node's only mark and covers just this node
    qualifies. An http(s) URL whose text is its href stays bare when nothing that
    follows could be read as part of the URL; otherwise it becomes <href>. A mailto:
    link whose text is the address becomes <address>."""
    node = nodes[index]
    link = _link(node)
    if node["type"] != "text" or _marks(node) != [link] or link["attrs"]["title"] is not None:
        return None
    if _extent(nodes, index, link) != 1 or (index > 0 and link in _marks(nodes[index - 1])):
        return None
    text, href = node["text"], link["attrs"]["href"]
    if text == href and _BARE_URL.fullmatch(text) and _bare_url_ends(nodes, index) and not set("&\\") & set(text):
        return text
    if text == href and _URI_AUTOLINK.fullmatch(href):
        return f"<{href}>"
    if href == "mailto:" + text and _EMAIL_AUTOLINK.fullmatch(text):
        return f"<{text}>"
    return None


def _bare_url_ends(nodes: list[dict], index: int) -> bool:
    """Nothing after nodes[index] extends a bare URL: a line end, or (closing punctuation and) whitespace."""
    following = nodes[index + 1] if index + 1 < len(nodes) else None
    if following is None:
        return True
    if following["type"] != "text" or _marks(following):  # also a hard break: the URL would take its "\"
        return False
    rest = following["text"].lstrip(_URL_TRAILING)
    if rest:
        return rest[0].isspace()
    return index + 2 == len(nodes)


def _code_span(code: str) -> str:
    """A backtick run longer than any inside; padded where CommonMark would strip or merge."""
    fence = "`" * (max((len(run) for run in re.findall("`+", code)), default=0) + 1)
    pad = code[0] == "`" or code[-1] == "`" or (code[0] == code[-1] == " " and code.strip(" ") != "")
    return f"{fence} {code} {fence}" if pad else f"{fence}{code}{fence}"


def _link_target(href: str, title: str | None) -> str:
    """The inside of a link's parentheses: destination, then an optional "title"."""
    href = _escape_entities(href)
    if any(ch.isspace() or ord(ch) < 0x20 or ch in "<>" for ch in href):
        target = "<" + re.sub(r"([<>\\])", r"\\\1", href) + ">"
    else:
        target = _escape_backslashes(href)
        if not _parens_balanced(target):
            target = re.sub(r"(?<!\\)([()])", r"\\\1", target)
    if title is None:
        return target
    return target + ' "' + _escape_backslashes(_escape_entities(title)).replace('"', '\\"') + '"'


def _escape_entities(value: str) -> str:
    """Keep a literal "&name;" from being decoded by writing its "&" as "&amp;"."""
    return _ENTITY.sub(lambda m: "&amp;" + m.group()[1:], value)


def _escape_backslashes(value: str) -> str:
    """Double each backslash that would otherwise escape the character after it."""
    return re.sub(r"\\(?=[" + re.escape(string.punctuation) + r"]|$)", r"\\\\", value)


def _parens_balanced(value: str) -> bool:
    depth = 0
    for i, ch in enumerate(value):
        if ch in "()" and i > 0 and value[i - 1] == "\\":
            continue
        depth += {"(": 1, ")": -1}.get(ch, 0)
        if depth < 0:
            return False
    return depth == 0


# --- inline: escaping -----------------------------------------------------------


def _escape_pieces(pieces: list[tuple[str, bool | None]], heading: bool) -> str:
    out: list[str] = []
    for i, (value, in_link) in enumerate(pieces):
        if in_link is None:
            out.append(value)
            continue
        before = out[-1][-1:] if out else ""
        after = pieces[i + 1][0][:1] if i + 1 < len(pieces) else ""
        line_start = before in ("", "\n")
        line_end = i + 1 == len(pieces) or pieces[i + 1][0] == "\\\n"
        out.append(_escape(value, before, after, in_link, line_start, line_end, heading))
    return "".join(out)


def _escape(
    text: str, before: str, after: str, in_link: bool, line_start: bool, line_end: bool, heading: bool
) -> str:
    """Backslash-escape what Markdown would read as syntax in `text`, and nothing else.

    `before`/`after` are the output characters around the text ("" at a block edge,
    "\\n" after a hard break); line_start/line_end say whether the text starts/ends a line."""
    escaped: set[int] = set()
    # mistune links bare http(s) URLs anywhere; inside link text one swallows the markup up to "]".
    escaped |= {match.end() for match in _BARE_URL_SCHEME.finditer(text)}
    if line_start and not heading:
        escaped |= _line_start_escapes(text, line_end)
    if heading and after == "" and (match := _HEADING_CLOSE.search(text)):
        escaped.add(match.start(1))
    for i, ch in enumerate(text):
        prev = text[i - 1] if i > 0 else before
        nxt = text[i + 1] if i + 1 < len(text) else after
        if (
            ch in "*`["
            or (ch == "]" and in_link)
            or (ch == "\\" and nxt in _ASCII_PUNCT)  # a hard break's "\" counts: it follows
            or (ch == "_" and not (prev.isalnum() and nxt.isalnum()))
            or (ch == "~" and "~" in (prev, nxt))
            or (ch == "!" and nxt == "[")
            or (ch == "<" and ((nxt.isascii() and nxt.isalpha()) or nxt in ("/", "!", "?")))
            or (ch == "&" and _ENTITY.match(text, i))
        ):
            escaped.add(i)
    out = ["\\" + ch if i in escaped else ch for i, ch in enumerate(text)]
    if before == "\n" and text[0].isspace():  # mistune drops any whitespace after a hard break
        out[0] = "&nbsp;" if text[0] == "\xa0" else f"&#{ord(text[0])};"
    return "".join(out)


def _line_start_escapes(text: str, line_end: bool) -> set[int]:
    """Positions to escape so that a line starting with `text` stays paragraph text."""
    if line_end and _UNDERLINE.fullmatch(text):
        return {min(i for i, ch in enumerate(text) if ch in "-=")}
    probe = text if line_end else text + "x"  # markup (non-blank) follows the text
    if text[:1] == ">" or _HEADING_START.match(probe) or _BULLET_START.match(probe):
        return {0}
    if match := _ORDERED_START.match(probe):
        return {match.start(1)}
    return set()
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_serialize.py -v`
Expected: 185 passed.

- [x] **Step 5: Run the full suite and the Qt-import check**

Run:

```bash
.venv/Scripts/python -m pytest -v
rg -n "import (PySide|Qt)|from PySide" mdviewer/core tests
```

Expected: all tests pass; the `rg` line prints nothing.

- [x] **Step 6: Commit**

```bash
git add mdviewer/core/serialize.py tests/test_serialize.py
git commit -m "feat: serialize text blocks and marks to normalized Markdown"
```

**Review Focus:**

- Every escape is justified by a test in `test_text_escaping` or
  `test_context_sensitive_escaping`, and nothing else is escaped: `snake_case`,
  `C:\Users`, `a ~ b`, `100% | 1.5 kg`, `#hashtag` and `-5 degrees` come out
  unchanged.
- `test_escaped_text_parses_back_to_the_same_text`,
  `test_repo_text_blocks_round_trip` and
  `test_random_inline_content_round_trips` check the output against the real
  parser (`docmodel.from_markdown`). An escaping change must keep them green
  without loosening their generators or the `_visible` projection.
- Splitting strong/em runs at link and strike edges and expelling whitespace
  never changes what a reader sees; the normalizations are exactly those
  listed in the design decisions.
- `line` and `highlight` attrs are ignored; mark order in the input does not
  matter.
- Unknown node types raise `ValueError` rather than being skipped, so a pull
  never silently drops content.
- The module imports nothing from Qt and only `frontmatter` from `mdviewer`.

### Task 7: Document -> Markdown, rich blocks and round-trip properties

**Status: steps detailed.** All code and tests below were run before being
written into this plan, against mistune 3.4.0 with the Task 2-6 modules taken
from this plan. Results:
- `tests/test_serialize.py`: 312 passed (Task 6's 185, one of them widened,
  plus 127 new); `tests/test_roundtrip.py`: 44 passed; the full suite: 711
  passed.
- Against the Task 6 serializer the new and widened tests give 160 failed, 196
  passed.
- Sixteen deliberate breaks each make tests fail: no list marker switch, no
  `___` opening an item, no `___` under a joined line, two paragraphs kept
  tight, every loose list written loose, any block joined under a quote, no
  bare-marker rule check, no backslash escape in the language, no tilde fence,
  fixed fence length, no pipe escaping, hard breaks kept in cells, autolinks
  with `|` in cells, footnote definitions left in place, no colon escape after
  a footnote reference, no character reference at a cell's end.
- Exploratory runs found only the known limits listed below: 9,000 random
  block trees (three seeds), 3,000 random tables of tricky inline content, and
  3,000 random paragraphs holding images, footnote references or inline HTML.

**Findings about mistune 3.4.0 that shape this task:**

- **Tight and loose lists.** A list is loose when a blank line separates two
  items, when an item's own tokens include a blank line, or when an item holds
  two paragraphs anywhere (not just next to each other); a task box line
  (`- [x]` with nothing after it) counts as a paragraph. A blank line right
  after a nested list is taken in by that list's last item, so it makes nothing
  loose, unless that item is empty: then the nested list becomes loose
  (`- a\n-\n\nb` reads as a loose list).
- **What may start right under a line of text** (interrupt a paragraph): an
  ATX heading, a fence, `>`, a thematic break, and a list item with text
  (`-`, or an ordered item numbered 1). An empty item cannot, and `-` alone
  under text is a setext underline; `2. b` under text is a lazy continuation.
- **After a block quote:** a paragraph line continues the quote (lazy), and
  mistune also keeps a following heading or HTML block *inside* the quote
  (Task 4 found the heading case); two quotes on adjacent lines merge. A list
  directly under a quote is moved *in front of* the quote once a later block
  interrupts the list (`> a\n- y\n___` gives list, quote, rule; `render_body`
  shows the same order, docmodel follows it). With a blank line in between the
  order is kept.
- **Thematic breaks:** `- ---`, `- - -` and `* * *` are rules, not list items;
  `- ___` is an item holding a rule.
- **Fenced code:** the info string takes backslash escapes (`c\+\+` gives
  `c++`) but keeps entities raw; a backtick fence's info string cannot contain
  a backtick (a tilde fence's can). Leading tabs in code lines inside a list
  item are expanded to spaces.
- **Tables:**
  - The v1 plugin list has `table` only (not `table_in_quote` or
    `table_in_list`), so tables are read at the top level only.
  - Cells are split at each `|` that follows an even number of backslashes
    (`_is_escaped_pipe`); a cell's text is `str.strip()`ped, which removes every
    Unicode whitespace character, NBSP included.
  - A pipe table with one row of a different width is read as a paragraph.
  - Link destinations and image sources come back percent-encoded (`|` gives
    `%7C`, as a space gives `%20`).
- **Footnotes and link references:** `[^1]: x` at a paragraph start (at any
  depth) is a definition, or a link reference definition below the root; it
  cannot interrupt a paragraph. `[^1](x)` stays a reference followed by text.
- **Inline HTML** that opens an HTML block (`<div>`, `<!--`) at the start of a
  line, also right after a hard break, starts an HTML block.

**Cross-task findings (recorded for Tasks 10, 11 and 19):**
- A table inside a block quote or a list item cannot be read back as a table.
  The serializer writes it anyway (it comes back as paragraph text, nothing is
  lost), but Task 10 should report `insertTable` as unavailable (`can`) inside
  `blockquote` and `list_item`, and Task 11's paste should lift pasted tables
  out of them.
- Task 10's "Enter on an empty item exits the list" also avoids the empty
  last item limit below.
- The README normalization note (Task 19) can name what changes on the first
  save: bullets become `-` (`*` for a list right after another bullet list),
  ordered markers `1.` (or `1)`), numbering restarts from `start`, task boxes
  `[x]`, indented code becomes fenced and info strings keep only the language,
  reference links and setext headings disappear, footnote definitions move to
  the end, tables get outer pipes and `---` delimiters.

**Design decisions:**

- **`serialize.py` is replaced as a whole**, as Task 5 did for docmodel. The
  Task 6 code stays, with these changes:
  - `_blocks` is split into `_parts` (serialize, switch list markers) and
    `_join` (blank line, or one line in a tight item)
  - `_inline` gains `cell`; `_normalize`'s `heading` flag becomes `one_line`
    (headings and cells); `_pieces` and `_autolink` gain `cell`
  - `_content` handles `image`, `footnote_ref` and `html_inline`
  - `_escape_pieces` escapes a colon after a leading footnote reference;
    `_escape` decides character references before escaping, so a backslash
    next to one is doubled
  - `to_markdown` moves footnote definitions to the end.
- **Lists:**
  - Bullets `-`, ordered `N.` counting from `start`. A list right after a list
    of the same kind (in the same container) switches to `*` or `)`, or the two
    would merge; the switch alternates for a run of lists.
  - Every line of an item is indented to its content column, the marker width
    plus one (`10. ` indents by 4). Blank lines stay empty.
  - Task items write `[ ] ` or `[x] ` before the first paragraph's text. An
    item whose first block is not a paragraph gets the box alone on its first
    line; docmodel reads that back as an empty first paragraph, which is what
    it gives for `- [ ]` followed by a block.
  - An empty item is the bare marker.
  - **Tightness is written as mistune reads it back**, so the first save is
    already a fixed point:
    - a tight item writes its blocks line by line; `_joins` allows that after a
      heading, code block or rule; after a paragraph, quote or list only for a
      heading, fence, quote, rule or a list item with text (bullet, or ordered
      from 1); after a quote only for a fence or rule; never after a table or
      HTML block
    - a tight list is written loose when some item has two paragraphs or a
      pair of blocks `_joins` refuses (that is how it would be read anyway)
    - a loose list with one item whose blank lines mistune would not see (one
      paragraph, or blank lines only after nested lists) is written tight
  - A rule written right under a line (joined in a tight item) or opening an
    item is `___`; elsewhere it stays `---` (Task 6).
  - Items whose first line would be only markers forming a rule (`- - -`) put
    their content on the next line (`-\n  - -`).
- **Code blocks:** fenced with backticks, or tildes when the language holds a
  backtick; the fence is one longer than the longest run of its character in
  the code (at least 3). Only the language's first word is written
  (backslashes before punctuation doubled), as docmodel keeps only that word.
  The code text is written exactly, blank lines and a trailing newline
  included. `highlight` is ignored.
- **Tables:**
  - The first row is the header, whatever its cell types; the delimiter row
    comes from the first row's `align` attrs (`---`, `:---`, `:---:`, `---:`).
  - Rows are padded with empty cells to the widest row.
  - Cells are one line: hard breaks and newlines in inline HTML become spaces,
    no line-start escapes apply, and whitespace other than space or tab at a
    cell's edges is written as a character reference (`&nbsp;`).
  - Every `|` after an even number of backslashes is escaped as `\|`, in text,
    code spans, link and image targets, alt text and inline HTML alike. Text
    escaping already doubles a backslash before `|`, so the count works out;
    docmodel turns `\|` in a code span back into `|`.
  - An autolink whose text or URL holds `|` is written `[text](href)`, where the
    escape works.
- **Images:** `![alt](src "title")`, using the link target rules for `src` and
  `title`; the alt text is escaped like link text, newlines become spaces.
  `display_src` is ignored. Marks wrap an image like text (`[![ci](b.svg)](u)`).
- **Protected nodes:**
  - `html_block` and `footnote_def` write their `source` verbatim (indented or
    quoted like any block when nested); `html_inline` writes its `source`;
    `footnote_ref` writes `[^label]`.
  - All `footnote_def` nodes are written after the body, in document order.
  - A colon right after a footnote reference that opens a paragraph is
    escaped (`[^1]\: x`), or the paragraph would become a definition.
- **Known limits** (editing-only: docmodel never produces these from
  Markdown, so the round-trip properties over Markdown input hold; the random
  generators avoid them):
  - an empty last list item followed by another block reads back loose
  - a table inside a quote or list item comes back as paragraph text (see the
    cross-task finding)
  - leading tabs in code lines inside a list item become spaces
  - a code span in a table cell cannot hold a literal `\|` (GFM cannot either);
    it comes back as `|`
  - an inline HTML chip that opens a line and looks like an HTML block start
    (`<div>`, `<!--`) becomes an `html_block`
  - link destinations and image sources with characters mistune
    percent-encodes (space, `|`) change on the first save, then stay stable
  - Task 6's inline limits apply to images, footnote references and inline
    HTML too: they count as punctuation for strong/em flanking.

**Files:**
- Replace: `mdviewer/core/serialize.py` (whole file)
- Modify: `tests/test_serialize.py` (replace the Task 6 repo test, append 46
  test functions, 127 cases)
- Create: `tests/test_roundtrip.py`, `tests/corpus/lists.md`,
  `tests/corpus/code.md`, `tests/corpus/tables.md`, `tests/corpus/inline.md`,
  `tests/corpus/blocks.md`

**Interfaces:**
- Consumes:
  - `frontmatter.split` / `frontmatter.join` (Task 3), `docschema` (Task 2)
  - `docmodel.from_markdown` (Tasks 4-5) and `render.render_body` (v1), in tests
  - the Task 6 test helpers in `tests/test_serialize.py` (`doc`, `para`,
    `heading`, `quote`, `rule`, `text`, `hard_break`, `STRONG`, `EM`, `CODE`,
    `link`, `inline_md`, `round_trip`, `without_lines`, `_random_inline`)
- Produces:
  - `serialize.to_markdown`, `serialize.front_matter`, `serialize.to_text` for
    every node type in `docschema` (signatures unchanged from Task 6)
  - `ValueError` only for node types `docschema` does not know
  - `tests/corpus/*.md`: Markdown samples that cover every node type and mark;
    later tasks may add files (the round-trip tests pick them up)

- [x] **Step 1: Create the corpus**

Create `tests/corpus/lists.md`:

````markdown
# Lists

- tight one
- tight two
  - nested *em*
    - deeper
- three

* a second bullet list, right after the first

## Ordered

1. one
2. two
   1. nested ordered
   2. again
3. three

Starting at seven:

7. seven
8. eight

1) a parenthesis delimiter

## Loose

- loose item

  with a second paragraph

- another loose item

## Tasks

- [ ] open task
- [x] done task
- [X] done in capitals
  - [ ] nested task

## Empty and wide items

-
- empty first item above

10. wide markers
11. need four columns
    - nested under eleven

## Blocks in items

- item with code:
  ```python
  print("in a list")
  ```
- > a quote in a list
- # a heading in a list
- ***
- text that looks like markup: \[ ] and 1\. and \- dash
````

Create `tests/corpus/code.md`:

`````markdown
# Code

```python
def double(x):
    return x * 2
```

```
no language
```

~~~js
const fence = "```";
~~~

````markdown
```
a nested fence
```
````

    indented code
    second line

```text title="ignored"
the info string after the language is dropped
```

```

blank lines around

```

Inline `code`, ``a`b``, ` `` `, `` `tick` `` and `*not em*`.
`````

Create `tests/corpus/tables.md`:

```markdown
# Tables

| Left | Center | Right | None |
| :--- | :----: | ----: | ---- |
| a | **b** | `c` | [d](https://example.com) |
| pipe \| text | `code \| pipe` | ![img](pic.png) | |

| One column |
| --- |
| single |

Name | Value
--- | ---
no outer pipes | 1
```

Create `tests/corpus/inline.md` (line 14 ends with two spaces, a hard break;
keep them):

```markdown
# Inline

Plain *em*, **strong**, ***both***, ~~strike~~, `code`, and **nested *em* inside**.

Links: [inline](https://example.com "Title"), [relative](docs/page.md#part), <https://auto.example>,
a bare https://bare.example/path, a mail <someone@example.com>, and [a reference][r].

[r]: https://ref.example 'Ref title'

Images: ![alt text](pic.png), ![titled](img/a%20b.png "Pic"), and a badge
[![build](https://ci.example/badge.svg)](https://ci.example).

Hard break with a backslash\
and with two spaces  
done.

Escapes: \* \_ \# \[x\] \\ &amp; &copy; &#35; 2 * 3 snake_case C:\Users\me

Raw <kbd>Ctrl</kbd>+<kbd>C</kbd> and an <!-- inline comment -->.

A footnote[^1] and another[^note].

[^1]: The first note.
[^note]: The second note,
    continued.

Setext heading
==============

Second level
------------
```

Create `tests/corpus/blocks.md`:

```markdown
---
title: Corpus
tags: [a, b]
---
# Blocks

> A quote
> over two lines
>
> > nested
>
> - a list in a quote

---

<div align="center">
  <b>HTML block</b>
</div>

<!--
a comment
-->

A paragraph after HTML.

***

The last paragraph.
```

- [x] **Step 2: Write the failing tests**

In `tests/test_serialize.py`, replace

```python
def _task6_only(node):
    """True when the node uses only the node types this serializer handles so far."""
    if node["type"] not in {"paragraph", "heading", "blockquote", "horizontal_rule", "text", "hard_break"}:
        return False
    return all(_task6_only(child) for child in node.get("content", []))


def test_repo_text_blocks_round_trip():
    """Every paragraph, heading, quote and rule in the project's docs survives serialization."""
    root = Path(__file__).resolve().parent.parent
    paths = [root / "README.md", *sorted((root / "docs").rglob("*.md"))]
    checked = 0
    for path in paths:
        front, body = frontmatter.split(path.read_text(encoding="utf-8").replace("\r\n", "\n"))
        for block in from_markdown(body, front)["content"]:
            if not _task6_only(block):
                continue
            markdown = to_markdown(doc(block))
            assert without_lines(from_markdown(markdown))["content"] == [without_lines(block)], (path, markdown)
            checked += 1
    assert checked > 100
```

with

```python
def test_repo_blocks_round_trip():
    """Every top-level block in the project's docs survives serialization on its own.

    The document's footnote definitions come along, so that its references stay references."""
    root = Path(__file__).resolve().parent.parent
    paths = [root / "README.md", *sorted((root / "docs").rglob("*.md"))]
    checked = 0
    for path in paths:
        front, body = frontmatter.split(path.read_text(encoding="utf-8").replace("\r\n", "\n"))
        blocks = from_markdown(body, front)["content"]
        notes = [block for block in blocks if block["type"] == "footnote_def"]
        for block in blocks:
            if block["type"] in ("front_matter", "footnote_def"):
                continue
            markdown = to_markdown(doc(block, *notes))
            expected = [without_lines(node) for node in (block, *notes)]
            assert without_lines(from_markdown(markdown))["content"] == expected, (path, markdown)
            checked += 1
    assert checked > 500
```

Append to the end of `tests/test_serialize.py` (the block uses a four-backtick
fence because the tests contain triple-backtick Markdown):

``````python
# === Task 7: lists, code, tables, images, raw HTML, footnotes ===============================

from mdviewer.core.docschema import validate  # noqa: E402


def bullets(*items, tight=True):
    return {"type": "bullet_list", "attrs": {"tight": tight, "line": None}, "content": list(items)}


def ordered(*items, start=1, tight=True):
    return {"type": "ordered_list", "attrs": {"start": start, "tight": tight, "line": None}, "content": list(items)}


def item(*blocks, checked=None):
    return {"type": "list_item", "attrs": {"checked": checked}, "content": list(blocks) or [para()]}


def code_block(code, language="", highlight=""):
    node = {"type": "code_block", "attrs": {"language": language, "highlight": highlight, "line": None}}
    if code:
        node["content"] = [text(code)]
    return node


def table(*rows):
    return {"type": "table", "attrs": {"line": None}, "content": list(rows)}


def row(*cells):
    return {"type": "table_row", "content": list(cells)}


def header(*inline, align=None):
    node = {"type": "table_header", "attrs": {"align": align}}
    if inline:
        node["content"] = list(inline)
    return node


def cell(*inline, align=None):
    node = {"type": "table_cell", "attrs": {"align": align}}
    if inline:
        node["content"] = list(inline)
    return node


def image(src, alt="", title=None, *marks):
    node = {"type": "image", "attrs": {"src": src, "display_src": "file:///ignored", "alt": alt, "title": title}}
    if marks:
        node["marks"] = list(marks)
    return node


def footnote_ref(label):
    return {"type": "footnote_ref", "attrs": {"label": label}}


def footnote_def(label, source):
    return {"type": "footnote_def", "attrs": {"label": label, "source": source, "line": None}}


def html_inline(source, *marks):
    node = {"type": "html_inline", "attrs": {"source": source}}
    if marks:
        node["marks"] = list(marks)
    return node


def html_block(source):
    return {"type": "html_block", "attrs": {"source": source, "line": None}}


def cell_md(*inline):
    """Markdown for a one-cell table's header cell, without the "| " and " |" around it."""
    out = to_markdown(doc(table(row(header(*inline)))))
    first = out.split("\n")[0]
    assert first.startswith("| ") and first.endswith(" |"), out
    return first[2:-2]


# --- lists ---------------------------------------------------------------------------------


def test_tight_bullet_list_with_nested_list():
    assert to_markdown(doc(bullets(item(para(text("a"))), item(para(text("b")), bullets(item(para(text("c")))))))) == (
        "- a\n- b\n  - c\n"
    )


def test_loose_list():
    assert to_markdown(doc(bullets(item(para(text("a"))), item(para(text("b"))), tight=False))) == "- a\n\n- b\n"


def test_loose_item_with_two_paragraphs():
    assert to_markdown(doc(bullets(item(para(text("a")), para(text("b"))), tight=False))) == "- a\n\n  b\n"


@pytest.mark.parametrize("start, expected", [(1, "1. a\n2. b\n"), (3, "3. a\n4. b\n"), (0, "0. a\n1. b\n")])
def test_ordered_list_counts_from_start(start, expected):
    assert to_markdown(doc(ordered(item(para(text("a"))), item(para(text("b"))), start=start))) == expected


def test_nested_lines_indent_to_each_items_content_column():
    nested = bullets(item(para(text("c"), hard_break(), text("d"))))
    assert to_markdown(doc(ordered(item(para(text("a"))), item(para(text("b")), nested), start=9))) == (
        "9. a\n10. b\n    - c\\\n      d\n"
    )


def test_task_items():
    assert to_markdown(doc(bullets(item(para(text("a")), checked=False), item(para(text("b")), checked=True)))) == (
        "- [ ] a\n- [x] b\n"
    )


def test_task_item_without_text_has_the_box_on_its_own_line():
    assert to_markdown(doc(bullets(item(para(), checked=False)))) == "- [ ]\n"
    assert to_markdown(doc(bullets(item(code_block("x"), checked=True)))) == "- [x]\n  ```\n  x\n  ```\n"


def test_empty_items():
    assert to_markdown(doc(bullets(item(para()), item(para(text("b")))))) == "-\n- b\n"
    assert to_markdown(doc(ordered(item(para())))) == "1.\n"


def test_list_item_text_that_looks_like_markup_is_escaped():
    assert to_markdown(doc(bullets(item(para(text("- x"))), item(para(text("[ ] y")))))) == "- \\- x\n- \\[ ] y\n"


def test_adjacent_lists_of_the_same_kind_alternate_markers():
    three = doc(bullets(item(para(text("a")))), bullets(item(para(text("b")))), bullets(item(para(text("c")))))
    assert to_markdown(three) == "- a\n\n* b\n\n- c\n"
    assert to_markdown(doc(ordered(item(para(text("a")))), ordered(item(para(text("b"))), start=5))) == (
        "1. a\n\n5) b\n"
    )
    assert to_markdown(doc(bullets(item(para(text("a")))), para(), ordered(item(para(text("b")))))) == (
        "- a\n\n1. b\n"
    )


def test_adjacent_lists_in_a_quote_and_in_an_item():
    assert to_markdown(doc(quote(bullets(item(para(text("a")))), bullets(item(para(text("b"))))))) == (
        "> - a\n>\n> * b\n"
    )
    inner = item(para(text("x")), bullets(item(para(text("a")))), bullets(item(para(text("b")))))
    assert to_markdown(doc(bullets(inner))) == "- x\n  - a\n  * b\n"


def test_rule_that_opens_an_item():
    assert to_markdown(doc(bullets(item(rule())))) == "- ___\n"


def test_nested_items_without_text_do_not_form_a_rule():
    assert to_markdown(doc(bullets(item(bullets(item(bullets(item(para())))))))) == "-\n  - -\n"


@pytest.mark.parametrize("blocks, expected", [
    ([para(text("a")), code_block("x")], "- a\n  ```\n  x\n  ```\n"),
    ([para(text("a")), rule()], "- a\n  ___\n"),
    ([para(text("a")), quote(para(text("q")))], "- a\n  > q\n"),
    ([para(text("a")), heading(2, text("h"))], "- a\n  ## h\n"),
    ([para(text("a")), bullets(item(para(text("b"))))], "- a\n  - b\n"),
    ([para(text("a")), ordered(item(para(text("b"))))], "- a\n  1. b\n"),
    ([heading(1, text("h")), para(text("a"))], "- # h\n  a\n"),
    ([code_block("x"), para(text("a"))], "- ```\n  x\n  ```\n  a\n"),
    ([quote(para(text("q"))), code_block("x")], "- > q\n  ```\n  x\n  ```\n"),
])
def test_tight_item_blocks_follow_line_by_line(blocks, expected):
    assert to_markdown(doc(bullets(item(*blocks)))) == expected


@pytest.mark.parametrize("blocks, expected", [
    ([para(text("a")), para(text("b"))], "- a\n\n  b\n"),
    ([para(text("a")), rule(), para(text("b"))], "- a\n\n  ---\n\n  b\n"),
    ([para(text("a")), html_block("<div>x</div>")], "- a\n\n  <div>x</div>\n"),
    ([para(text("a")), ordered(item(para(text("b"))), start=3)], "- a\n\n  3. b\n"),
    ([para(text("a")), bullets(item(para()), item(para(text("b"))))], "- a\n\n  -\n  - b\n"),
    ([quote(para(text("q"))), para(text("a"))], "- > q\n\n  a\n"),
    ([quote(para(text("q"))), heading(1, text("h"))], "- > q\n\n  # h\n"),
    ([quote(para(text("q"))), bullets(item(para(text("b"))))], "- > q\n\n  - b\n"),
    ([quote(para(text("a"))), quote(para(text("b")))], "- > a\n\n  > b\n"),
    ([para(text("a")), bullets(item(para(text("b")))), para(text("c"))], "- a\n\n  - b\n\n  c\n"),
])
def test_tight_list_is_written_loose_when_an_item_cannot_be_tight(blocks, expected):
    markdown = to_markdown(doc(bullets(item(*blocks))))
    assert markdown == expected
    assert from_markdown(markdown)["content"][0]["attrs"]["tight"] is False


def test_task_box_line_follows_the_same_rules():
    assert to_markdown(doc(bullets(item(rule(), checked=True)))) == "- [x]\n  ___\n"
    assert to_markdown(doc(bullets(item(html_block("<br>"), checked=True)))) == "- [x]\n\n  <br>\n"
    assert to_markdown(doc(bullets(item(code_block("x"), para(text("a")), checked=True)))) == (
        "- [x]\n\n  ```\n  x\n  ```\n\n  a\n"
    )


@pytest.mark.parametrize("blocks", [
    [para(text("a"))],
    [bullets(item(para(text("a")))), heading(1, text("h"))],
])
def test_loose_list_is_written_tight_when_mistune_would_read_it_tight(blocks):
    markdown = to_markdown(doc(bullets(item(*blocks), tight=False)))
    assert "\n\n" not in markdown
    assert from_markdown(markdown)["content"][0]["attrs"]["tight"] is True


@pytest.mark.parametrize("markdown", [
    "- a\n- b\n  - c\n    - d\n",
    "- a\n\n- b\n",
    "1. a\n\n   b\n\n2. c\n",
    "3. a\n4. b\n",
    "- [ ] a\n- [x] b\n  - [ ] c\n",
    "- [x]\n  ```\n  x\n  ```\n",
    "-\n- b\n",
    "- a\n  - b\n\n  - c\n- d\n",
    "10. a\n11. b\n    - c\n",
    "- a\n\n* b\n",
    "1. a\n\n1) b\n",
    "> - a\n> - b\n>\n> 1. c\n",
    "- ___\n- a\n  ___\n",
    "- # h\n  text\n- > q\n  ```py\n  x\n  ```\n",
    "- <div>x</div>\n- b\n",
])
def test_lists_keep_their_markdown(markdown):
    assert round_trip(markdown) == markdown


@pytest.mark.parametrize("markdown, expected", [
    ("* a\n* b\n", "- a\n- b\n"),
    ("+ a\n\n* b\n", "- a\n\n* b\n"),
    ("1) a\n2) b\n", "1. a\n2. b\n"),
    ("- [X] done\n", "- [x] done\n"),
    ("- ***\n", "- ___\n"),
    ("-   wide\n    marker\n", "- wide marker\n"),
    ("2. a\n2. b\n2. c\n", "2. a\n3. b\n4. c\n"),
])
def test_normalizing_list_round_trips(markdown, expected):
    assert round_trip(markdown) == expected


# --- code blocks ---------------------------------------------------------------------------


def test_fenced_code_block_with_language():
    assert to_markdown(doc(code_block("x = 1\nprint(x)", "python", '<span class="n">x</span>'))) == (
        "```python\nx = 1\nprint(x)\n```\n"
    )


def test_empty_code_block():
    assert to_markdown(doc(code_block(""))) == "```\n```\n"
    assert to_markdown(doc(code_block("", "js"))) == "```js\n```\n"


def test_code_keeps_blank_lines_and_a_trailing_newline():
    assert to_markdown(doc(code_block("\na\n\nb\n"))) == "```\n\na\n\nb\n\n```\n"


@pytest.mark.parametrize("code, fence", [
    ("x = `y`", "```"),
    ("```", "````"),
    ("a\n````\nb", "`````"),
    ("~~~", "```"),
])
def test_fence_is_longer_than_any_backtick_run(code, fence):
    assert to_markdown(doc(code_block(code))) == f"{fence}\n{code}\n{fence}\n"


@pytest.mark.parametrize("language, expected", [
    ("py thon", "```py\nx\n```\n"),
    ("  rust  ", "```rust\nx\n```\n"),
    ("c\\+\\+", "```c\\\\+\\\\+\nx\n```\n"),
    ("a`b", "~~~a`b\nx\n~~~\n"),
    ("a&amp;b", "```a&amp;b\nx\n```\n"),
])
def test_code_language(language, expected):
    assert to_markdown(doc(code_block("x", language))) == expected


def test_code_in_a_list_item_and_a_quote_indents_every_line():
    assert to_markdown(doc(bullets(item(code_block("a\n\n  b"))))) == "- ```\n  a\n\n    b\n  ```\n"
    assert to_markdown(doc(quote(code_block("a\n\nb")))) == "> ```\n> a\n>\n> b\n> ```\n"


@pytest.mark.parametrize("markdown, expected", [
    ("    indented\n    code\n", "```\nindented\ncode\n```\n"),
    ("~~~\nx\n~~~\n", "```\nx\n```\n"),
    ("```python title=x\nx\n```\n", "```python\nx\n```\n"),
    ("```\nx\n", "```\nx\n```\n"),
    ("~~~ a`b\nx\n~~~\n", "~~~a`b\nx\n~~~\n"),
    ("````\n```\n````\n", "````\n```\n````\n"),
])
def test_code_block_round_trips(markdown, expected):
    assert round_trip(markdown) == expected


# --- tables --------------------------------------------------------------------------------


def test_table_with_alignment():
    markdown = to_markdown(doc(table(
        row(header(text("L"), align="left"), header(text("C"), align="center"), header(text("R"), align="right"),
            header(text("N"))),
        row(cell(text("1"), align="left"), cell(text("2", STRONG), align="center"), cell(align="right"), cell()),
    )))
    assert markdown == "| L | C | R | N |\n| :--- | :---: | ---: | --- |\n| 1 | **2** |  |  |\n"


def test_short_rows_are_padded_and_the_first_row_is_the_header():
    assert to_markdown(doc(table(row(cell(text("a"))), row(cell(text("b")), cell(text("c")))))) == (
        "| a |  |\n| --- | --- |\n| b | c |\n"
    )


@pytest.mark.parametrize("inline, expected", [
    ([text("a|b")], "a\\|b"),
    ([text("a\\|b")], "a\\\\\\|b"),
    ([text("x|y", CODE)], "`x\\|y`"),
    ([text("l", link("u|v", "t|"))], '[l](u\\|v "t\\|")'),
    ([text("https://x.y/a|b", link("https://x.y/a|b"))], "[https\\://x.y/a\\|b](https://x.y/a\\|b)"),
    ([text("https://x.y", link("https://x.y"))], "https://x.y"),
    ([image("a|b.png", "x|y")], "![x\\|y](a\\|b.png)"),
    ([html_inline('<a title="\\|">'), text("x"), html_inline("</a>")], '<a title="\\|">x</a>'),
])
def test_pipes_in_cells_are_escaped(inline, expected):
    assert cell_md(*inline) == expected


@pytest.mark.parametrize("inline, expected", [
    ([text("# x - y 1. z > q")], "# x - y 1. z > q"),
    ([text("---")], "---"),
    ([text("a"), hard_break(), text("b")], "a b"),
    ([html_inline("<a\nhref='x'>"), text("y")], "<a href='x'>y"),
    ([text("\xa0a\xa0")], "&nbsp;a&nbsp;"),
    ([text("a\\\xa0")], "a\\\\&nbsp;"),
    ([text("  a\t")], "a"),
])
def test_cell_text_is_one_line(inline, expected):
    assert cell_md(*inline) == expected


def test_empty_cells():
    assert to_markdown(doc(table(row(header(), header()), row(cell(), cell(text("x")))))) == (
        "|  |  |\n| --- | --- |\n|  | x |\n"
    )


@pytest.mark.parametrize("markdown, expected", [
    ("| a | b |\n|:-|-:|\n| 1 | 2 |\n", "| a | b |\n| :--- | ---: |\n| 1 | 2 |\n"),
    ("a | b\n--- | ---\n1 | 2\n", "| a | b |\n| --- | --- |\n| 1 | 2 |\n"),
    ("| a \\| b | `c \\| d` |\n| --- | --- |\n", "| a \\| b | `c \\| d` |\n| --- | --- |\n"),
    ("| x |\n| --- |\n| &nbsp;y |\n", "| x |\n| --- |\n| &nbsp;y |\n"),
])
def test_table_round_trips(markdown, expected):
    assert round_trip(markdown) == expected


# --- images ----------------------------------------------------------------------------------


@pytest.mark.parametrize("node, expected", [
    (image("a.png", "alt"), "![alt](a.png)"),
    (image("a.png"), "![](a.png)"),
    (image("img/a%20b.png", "x", 'say "hi"'), '![x](img/a%20b.png "say \\"hi\\"")'),
    (image("a b.png", "x"), "![x](<a b.png>)"),
    (image("a.png", "a]b *c* https://x.y"), "![a\\]b \\*c\\* https\\://x.y](a.png)"),
    (image("a.png", "line\nbreak"), "![line break](a.png)"),
])
def test_images(node, expected):
    assert inline_md(node) == expected


def test_display_src_is_ignored():
    assert inline_md(image("a.png", "x")) == inline_md({**image("a.png", "x"), "attrs": {
        "src": "a.png", "display_src": "file:///C:/elsewhere/a.png", "alt": "x", "title": None}})


def test_marked_images():
    assert inline_md(image("b.svg", "ci", None, link("https://ci"))) == "[![ci](b.svg)](https://ci)"
    assert inline_md(text("see "), image("a.png", "A", None, STRONG)) == "see **![A](a.png)**"


@pytest.mark.parametrize("inline, expected", [
    ([text("wow!"), image("a.png")], "wow!![](a.png)"),
    ([image("a.png"), text("(not a link)")], "![](a.png)(not a link)"),
    ([text("https://x.y", link("https://x.y")), image("a.png")], "<https://x.y>![](a.png)"),
])
def test_text_next_to_images(inline, expected):
    assert inline_md(*inline) == expected


# --- raw HTML and footnotes ------------------------------------------------------------------


def test_html_block_is_verbatim_and_indented_in_containers():
    source = "<div>\n  <b>x</b>\n</div>"
    assert to_markdown(doc(html_block(source))) == source + "\n"
    assert to_markdown(doc(quote(html_block("<!--\n\nc\n-->")))) == "> <!--\n>\n> c\n> -->\n"
    assert to_markdown(doc(bullets(item(html_block("<div>\nx\n</div>"))))) == "- <div>\n  x\n  </div>\n"


def test_html_inline_is_verbatim():
    assert inline_md(text("a "), html_inline("<kbd>"), text("Ctrl"), html_inline("</kbd>")) == "a <kbd>Ctrl</kbd>"
    assert inline_md(text("x", STRONG), html_inline("<br>", STRONG)) == "**x<br>**"


def test_newlines_in_html_inline_are_kept_in_paragraphs_and_dropped_in_headings():
    assert inline_md(text("a "), html_inline("<a\nhref='x'>")) == "a <a\nhref='x'>"
    assert to_markdown(doc(heading(1, html_inline("<a\nhref='x'>")))) == "# <a href='x'>\n"


def test_footnote_definitions_go_last_in_document_order():
    body = doc(footnote_def("b", "[^b]: B"), para(text("x"), footnote_ref("a")), footnote_def("a", "[^a]: A\n    more"),
               para(text("y"), footnote_ref("b")))
    assert to_markdown(body) == "x[^a]\n\ny[^b]\n\n[^b]: B\n\n[^a]: A\n    more\n"


def test_colon_after_a_footnote_reference_at_a_paragraph_start_is_escaped():
    note = footnote_def("1", "[^1]: note")
    assert to_markdown(doc(para(footnote_ref("1"), text(": not a definition")), note)) == (
        "[^1]\\: not a definition\n\n[^1]: note\n"
    )
    assert to_markdown(doc(para(text("a "), footnote_ref("1"), text(": fine")), note)) == "a [^1]: fine\n\n[^1]: note\n"
    assert to_markdown(doc(quote(para(footnote_ref("1"), text(": q"))), note)) == "> [^1]\\: q\n\n[^1]: note\n"


@pytest.mark.parametrize("markdown, expected", [
    ("[^1]: first\n\nPara[^1].\n", "Para[^1].\n\n[^1]: first\n"),
    ("A[^n] b[^m].\n\n[^m]: M\n[^n]: N\n    more\n", "A[^n] b[^m].\n\n[^m]: M\n\n[^n]: N\n    more\n"),
    ("[^1]\\: x\n\n[^1]: n\n", "[^1]\\: x\n\n[^1]: n\n"),
    ("<div>\nblock\n</div>\n\nafter\n", "<div>\nblock\n</div>\n\nafter\n"),
    ("<!-- c -->\n\ntext\n", "<!-- c -->\n\ntext\n"),
])
def test_protected_round_trips(markdown, expected):
    assert round_trip(markdown) == expected


# --- whole documents -------------------------------------------------------------------------


def test_unknown_node_inside_a_list_raises():
    with pytest.raises(ValueError, match="'callout'"):
        to_markdown(doc(bullets(item({"type": "callout"}))))


def test_every_node_type_serializes_and_parses_back_valid():
    body = doc(
        {"type": "front_matter", "attrs": {"source": "---\nt: 1\n---\n", "line": 1}},
        heading(1, text("T")),
        para(text("b", STRONG), text(" "), image("a.png", "A"), footnote_ref("1"), html_inline("<br>")),
        quote(para(text("q"))),
        bullets(item(para(text("t")), checked=True)),
        ordered(item(para(text("o"))), start=2),
        code_block("x", "py"),
        rule(),
        table(row(header(text("h"))), row(cell(text("c")))),
        html_block("<div>x</div>"),
        footnote_def("1", "[^1]: n"),
    )
    text_out = to_text(body)
    front, rest = frontmatter.split(text_out)
    back = from_markdown(rest, front)
    assert validate(back) == []
    assert [node["type"] for node in back["content"]] == [node["type"] for node in body["content"]]
    assert to_text(back) == text_out


# --- random table cells and inline chips -----------------------------------------------------
# Known limits kept out of the generators (see the plan's Task 7 Review Focus): "\|" inside a
# code span in a table cell, and an inline HTML chip at the start of a line.


def _units(inline, one_line=False):
    """What a reader sees, as lines of (unit, marks), like _visible; images, footnote references
    and inline HTML are one unit each. In a table cell (one_line) hard breaks are spaces."""
    lines = [[]]
    for node in inline:
        marks = node.get("marks", [])
        if node["type"] == "hard_break":
            if not one_line:
                lines.append([])
                continue
            node = text(" ", *marks)
        if node["type"] != "text":
            attrs = {key: value for key, value in node["attrs"].items() if key != "display_src"}
            lines[-1].append((repr(sorted(attrs.items())), sorted(repr(mark) for mark in marks)))
            continue
        for ch in node["text"].replace("\n", " "):
            kept = marks if CODE in marks or not ch.isspace() else [m for m in marks if m["type"] == "link"]
            lines[-1].append((ch, sorted(repr(mark) for mark in kept)))
    for line in lines:
        while line and line[0][0] in " \t" and repr(CODE) not in line[0][1]:
            line.pop(0)
        while line and line[-1][0] in " \t" and repr(CODE) not in line[-1][1]:
            line.pop()
    while lines and not lines[-1]:
        lines.pop()
    return lines


def _random_cell(rng, flanked):
    inline = _random_inline(rng, flanked)
    for node in inline:
        if node["type"] != "text" or rng.random() >= 0.3:
            continue
        coded = CODE in node.get("marks", [])
        cut = rng.randint(1, len(node["text"]) - 1) if len(node["text"]) > 1 else 0
        node["text"] = node["text"][:cut] + rng.choice(["|", "a|b"] if coded else ["|", "\\|", "a|b"]) + node["text"][cut:]
        if cut == 0 and not coded:
            node.pop("marks", None)  # a "|" at the edge of a strong/em run: the Task 6 limit
    for node in inline:
        if node["type"] == "text" and CODE in node.get("marks", []):
            while "\\|" in node["text"]:
                node["text"] = node["text"].replace("\\|", "|")
    if rng.random() < 0.2:
        inline.append(image(rng.choice(["p.png", "a%7Cb.png"]), rng.choice(["", "x|y", "a]"])))
    if rng.random() < 0.1:
        inline.insert(0, html_inline("<kbd>"))
    return inline


@pytest.mark.parametrize("flanked", [STRONG, EM], ids=["strong", "em"])
def test_random_cell_content_round_trips(flanked):
    rng = random.Random(7)
    for _ in range(800):
        cells = [_random_cell(rng, flanked) for _ in range(rng.randint(1, 3))]
        markdown = to_markdown(doc(table(row(*(header(*inline) for inline in cells)))))
        blocks = from_markdown(markdown)["content"]
        assert [block["type"] for block in blocks] == ["table"], markdown
        back = [node.get("content", []) for node in blocks[0]["content"][0]["content"]]
        assert [_units(inline, True) for inline in back] == [_units(inline, True) for inline in cells], markdown
        assert round_trip(markdown) == markdown


def _random_chip(rng):
    kind = rng.choice(["image", "footnote_ref", "html_inline"])
    if kind == "image":
        node = image(rng.choice(["p.png", "a%20b.png", "x(y"]), rng.choice(["", "alt", "a]b", "*x*", "https://x.y"]),
                     rng.choice([None, "T"]))
    elif kind == "footnote_ref":
        node = footnote_ref("n")
    else:
        node = html_inline(rng.choice(["<kbd>", "</kbd>", "<!-- c -->"]))
    if rng.random() < 0.3:
        node["marks"] = [rng.choice([STRONG, EM, link("u")])]
    return node


@pytest.mark.parametrize("flanked", [STRONG, EM], ids=["strong", "em"])
def test_random_inline_chips_round_trip(flanked):
    rng = random.Random(5)
    note = footnote_def("n", "[^n]: note")
    for _ in range(800):
        inline = _random_inline(rng, flanked)
        position = rng.randint(0, len(inline))
        inline[position:position] = [text("x "), _random_chip(rng), text(" ")]
        markdown = to_markdown(doc(para(*inline), note))
        blocks = from_markdown(markdown)["content"]
        assert [block["type"] for block in blocks] == ["paragraph", "footnote_def"], markdown
        assert _units(blocks[0].get("content", [])) == _units(inline), markdown
        assert round_trip(markdown) == markdown
``````

Create `tests/test_roundtrip.py`:

````python
"""Round-trip properties of docmodel + serialize (spec 8) over tests/corpus, README.md and docs/."""

import html
import random
import re
from pathlib import Path

import pytest

from mdviewer.core import docschema, frontmatter
from mdviewer.core.docmodel import from_markdown
from mdviewer.core.render import render_body
from mdviewer.core.serialize import to_text

ROOT = Path(__file__).resolve().parent.parent
CORPUS = sorted((ROOT / "tests" / "corpus").glob("*.md"))
SOURCES = CORPUS + [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]


def load(text: str) -> dict:
    front, body = frontmatter.split(text)
    return from_markdown(body, front)


def without_lines(node: dict) -> dict:
    copy = dict(node)
    if "attrs" in copy and docschema.LINE_ATTR in copy["attrs"]:
        copy["attrs"] = {**copy["attrs"], docschema.LINE_ATTR: None}
    if "content" in copy:
        copy["content"] = [without_lines(child) for child in copy["content"]]
    return copy


def rendered(text: str) -> str:
    """render_body of the text's body, whitespace-normalized and entity-decoded.

    Fenced code keeps the newline before its closing fence, indented code does not; the
    serializer writes all code fenced, so that newline is dropped before comparing."""
    body = frontmatter.split(text)[1]
    markup = render_body(body).replace("\n</code></pre>", "</code></pre>")
    return re.sub(r"\s+", " ", html.unescape(markup)).strip()


@pytest.fixture(params=SOURCES, ids=lambda path: path.relative_to(ROOT).as_posix())
def source(request) -> str:
    return request.param.read_text(encoding="utf-8").replace("\r\n", "\n")


def test_corpus_exists():
    assert len(CORPUS) >= 5


def test_corpus_uses_every_node_type_and_mark():
    nodes, marks = set(), set()

    def collect(node):
        nodes.add(node["type"])
        marks.update(mark["type"] for mark in node.get("marks", []))
        for child in node.get("content", []):
            collect(child)

    for path in CORPUS:
        collect(load(path.read_text(encoding="utf-8")))
    assert nodes == set(docschema.BLOCK_NODES) | set(docschema.INLINE_NODES)
    assert marks == set(docschema.MARKS)


def test_documents_are_valid(source):
    assert docschema.validate(load(source)) == []


def test_serialization_is_a_fixed_point_after_one_pass(source):
    once = to_text(load(source))
    assert to_text(load(once)) == once


def test_serialized_text_loads_as_the_same_document(source):
    document = load(source)
    assert without_lines(load(to_text(document))) == without_lines(document)


def test_serialized_text_renders_the_same_html(source):
    assert rendered(to_text(load(source))) == rendered(source)


def test_corpus_is_not_already_in_normal_form():
    """Every corpus file exercises normalization, so the fixed-point test is not vacuous.

    (Spec 1: a file that is only viewed is never rewritten; MainWindow ensures that by not
    serializing an unchanged document, not by the serializer reproducing the source.)"""
    for path in CORPUS:
        source = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        assert to_text(load(source)) != source, path


# --- random block structure ---------------------------------------------------------------
# Random trees of paragraphs, headings, code, rules, HTML, quotes, lists and tables must come
# back with the same structure (tight flags and empty paragraphs aside) and be a fixed point.
# Known limit kept out of the generator (see the plan's Task 7 Review Focus): a list whose
# last item is empty.

_WORDS = ["a", "b", "word", "x_y", "1.", "-", "#", ">", "*", "`", "|", "[x]", "---", "===", "<b>", "&amp;", "\\"]


def _text(value):
    return {"type": "text", "text": value}


def _paragraph(rng):
    value = " ".join(rng.choice(_WORDS) for _ in range(rng.randint(0, 4)))
    node = {"type": "paragraph", "attrs": {"line": None}}
    if value:
        node["content"] = [_text(value)]
    return node


def _random_block(rng, depth, top):
    kinds = ["paragraph", "paragraph", "paragraph", "heading", "code", "rule", "html"]
    if depth < 3:
        kinds += ["quote", "bullets", "ordered", "bullets", "ordered"]
    if top:  # mistune reads tables at the top level only (no table_in_quote / table_in_list)
        kinds.append("table")
    kind = rng.choice(kinds)
    if kind == "paragraph":
        return _paragraph(rng)
    if kind == "heading":
        return {**_paragraph(rng), "type": "heading", "attrs": {"level": rng.randint(1, 6), "line": None}}
    if kind == "code":
        node = {"type": "code_block", "attrs": {"language": rng.choice(["", "py"]), "highlight": "", "line": None}}
        code = rng.choice(["", "x", "a\n\nb", "```\ny", "  indented", "x\n"])
        if code:
            node["content"] = [_text(code)]
        return node
    if kind == "rule":
        return {"type": "horizontal_rule", "attrs": {"line": None}}
    if kind == "html":
        return {"type": "html_block", "attrs": {"source": rng.choice(["<div>x</div>", "<!-- c\n\nd -->"]),
                                                "line": None}}
    if kind == "quote":
        return {"type": "blockquote", "attrs": {"line": None}, "content": _random_blocks(rng, depth + 1)}
    if kind == "table":
        return _random_table(rng)
    items = [{"type": "list_item", "attrs": {"checked": rng.choice([None, None, True, False])},
              "content": _random_blocks(rng, depth + 1)} for _ in range(rng.randint(1, 3))]
    last = items[-1]
    if last["attrs"]["checked"] is None and not any(_skeleton(block) != {"type": "paragraph"}
                                                    for block in last["content"]):
        last["content"] = [{"type": "paragraph", "attrs": {"line": None}, "content": [_text("z")]}]
    attrs = {"tight": rng.random() < 0.6, "line": None}
    if kind == "ordered":
        return {"type": "ordered_list", "attrs": {"start": rng.choice([1, 1, 0, 3, 9]), **attrs}, "content": items}
    return {"type": "bullet_list", "attrs": attrs, "content": items}


def _random_table(rng):
    width = rng.randint(1, 3)
    aligns = [rng.choice([None, "left", "center", "right"]) for _ in range(width)]
    rows = []
    for index in range(rng.randint(1, 3)):
        cells = []
        for align in aligns:
            cell = {"type": "table_header" if index == 0 else "table_cell", "attrs": {"align": align}}
            if "content" in (paragraph := _paragraph(rng)):
                cell["content"] = paragraph["content"]
            cells.append(cell)
        rows.append({"type": "table_row", "content": cells})
    return {"type": "table", "attrs": {"line": None}, "content": rows}


def _random_blocks(rng, depth, top=False):
    return [_random_block(rng, depth, top) for _ in range(rng.randint(1, 3))]


def _skeleton(node):
    """The node without what serialization may change: line, tight, highlight, empty paragraphs."""
    out = {"type": node["type"]}
    attrs = {key: value for key, value in node.get("attrs", {}).items() if key not in ("line", "tight", "highlight")}
    if attrs:
        out["attrs"] = attrs
    if "text" in node:
        out["text"] = node["text"]
    children = [_skeleton(child) for child in node.get("content", [])
                if child["type"] != "paragraph" or child.get("content")]
    if children:
        out["content"] = children
    return out


def test_random_block_trees_round_trip():
    rng = random.Random(7)
    for _ in range(600):
        document = {"type": "doc", "content": _random_blocks(rng, 0, top=True)}
        markdown = to_text(document)
        back = load(markdown)
        assert docschema.validate(back) == [], markdown
        assert _skeleton(back) == _skeleton(document), markdown
        assert to_text(back) == markdown, markdown
````

- [x] **Step 3: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_serialize.py tests/test_roundtrip.py -q`
Expected: 160 failed, 196 passed. The failures are `ValueError: cannot
serialize a 'bullet_list' node` (and the other new node types) plus wrong
output for the table, list and footnote rules. The counts assume the current
`docs/` tree (two specs, two plans); each Markdown file there adds four
round-trip tests.

- [x] **Step 4: Replace `mdviewer/core/serialize.py`**

Replace the whole file with:

```python
"""ProseMirror document JSON -> normalized Markdown for the Rendered editor (spec 6.5).

The inverse of core/docmodel.py: from_markdown(to_markdown(doc)) gives the same
document back, up to the normalizations of spec 6.5. Output uses "\\n" only and
ends with exactly one "\\n" ("" for an empty body); MainWindow applies the file's
newline style on save. LINE_ATTR, code_block.highlight and image.display_src are
display-only and ignored here.
"""

import re
import string

from mdviewer.core import frontmatter

# CommonMark entity references, as docmodel decodes them; a "&" that starts one is escaped.
_ENTITY = re.compile(r"&(?:#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});")
_ASCII_PUNCT = frozenset(string.punctuation)
# Marks whose delimiters must touch non-whitespace (CommonMark flanking rules).
_FLANKED = frozenset({"strong", "em", "strike"})
_DELIMITERS = {"strong": "**", "em": "*", "strike": "~~"}
# Links, then strike, always open outermost: their syntax has no flanking rules. Strong
# and em runs are split at every edge of a link or strike run, which never changes the
# document (equal-marked text merges back) but keeps their delimiters next to text.
_OUTER_RANK = {"link": 0, "strike": 1}

# Line starts that would begin a block: ATX heading, bullet item, ordered item.
_HEADING_START = re.compile(r"#{1,6}(?=[ \t]|$)")
_BULLET_START = re.compile(r"[-+](?=[ \t]|$)")
_ORDERED_START = re.compile(r"[0-9]{1,9}([.)])(?=[ \t]|$)")
# Whole lines that would be a setext underline, a thematic break or a table delimiter row.
_UNDERLINE = re.compile(r"[-=]+[ \t]*|[-:| \t]*-[-:| \t]*")  # mistune also takes "-=" as an underline
# Trailing "#"s of a heading's text would be read as its closing sequence.
_HEADING_CLOSE = re.compile(r"(?:^|[ \t])(#+)[ \t]*$")
# mistune's url plugin links bare http(s) URLs; it never ends one on these characters.
_BARE_URL = re.compile(r"""https?://[^\s<]+[^<.,:;"')\]\s]""")
_BARE_URL_SCHEME = re.compile(r"https?(?=://)")
_URL_TRAILING = ".,:;\"')]"
# CommonMark autolinks: <scheme:...> and <address>.
_URI_AUTOLINK = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]{1,31}:[^\s<>&\\]*")
_EMAIL_AUTOLINK = re.compile(
    r"[a-zA-Z0-9.!#$%'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*"
)

_LISTS = frozenset({"bullet_list", "ordered_list"})
# A list directly after a list of the same kind uses the second marker, or the two would merge.
_BULLETS = ("-", "*")
_ORDERED_DELIMITERS = (".", ")")
# Blocks that end on their own line: anything may follow on the next line.
_CLOSED_BLOCKS = frozenset({"heading", "code_block", "horizontal_rule"})
# Blocks whose last line could take the next line in as a lazy paragraph continuation.
_OPEN_BLOCKS = frozenset({"paragraph", "blockquote", "bullet_list", "ordered_list"})
# Item markers with no text after them can add up to a thematic break: "- - -", "* * *".
_THEMATIC_BREAK = re.compile(r"(?:-[ \t]*){3,}|(?:\*[ \t]*){3,}")
_ALIGN_ROW = {None: "---", "left": ":---", "center": ":---:", "right": "---:"}
# A "|" after an even number of backslashes (none included) splits a table cell.
_UNESCAPED_PIPE = re.compile(r"(?<!\\)((?:\\\\)*)\|")


# --- public API -----------------------------------------------------------------


def to_markdown(doc: dict) -> str:
    """Normalized Markdown for the document body; "" when the body has no content.

    The front_matter node is not part of the body: see front_matter() and to_text().
    Footnote definitions are written last, in document order."""
    content = [node for node in doc.get("content", []) if node["type"] != "front_matter"]
    notes = [node for node in content if node["type"] == "footnote_def"]
    body = _blocks([node for node in content if node["type"] != "footnote_def"] + notes)
    return body + "\n" if body else ""


def front_matter(doc: dict) -> str | None:
    """The front_matter node's source, verbatim; None when the document has none."""
    content = doc.get("content", [])
    if content and content[0]["type"] == "front_matter":
        return content[0]["attrs"]["source"]
    return None


def to_text(doc: dict) -> str:
    """The whole buffer (spec 6.4 pull): front matter verbatim, then the body.

    A front-matter block that ended the file without a newline gets one when a body follows."""
    front, body = front_matter(doc), to_markdown(doc)
    if front is not None and body and not front.endswith("\n"):
        front += "\n"
    return frontmatter.join(front, body)


# --- blocks ---------------------------------------------------------------------


def _blocks(nodes: list[dict]) -> str:
    """Blocks separated by one blank line; blocks that serialize to "" are left out."""
    return _join(_parts(nodes), tight=False)


def _parts(nodes: list[dict]) -> list[tuple[dict, str]]:
    """(node, Markdown) for each block that serializes to something.

    A list right after a list of the same kind switches markers, or the two would merge."""
    parts: list[tuple[dict, str]] = []
    alternate = False
    for node in nodes:
        if node["type"] in _LISTS:
            previous = parts[-1][0] if parts else None
            alternate = previous is not None and previous["type"] == node["type"] and not alternate
            text = _list(node, alternate)
        else:
            text = _block(node)
        if text:
            parts.append((node, text))
    return parts


def _join(parts: list[tuple[dict, str]], tight: bool) -> str:
    """The blocks one blank line apart, or one line apart in a tight list item (see _joins)."""
    out: list[str] = []
    for index, (node, text) in enumerate(parts):
        if index:
            out.append("\n" if tight else "\n\n")
            if tight and text == "---":  # right under a line of text, "---" would underline it
                text = "___"
        out.append(text)
    return "".join(out)


def _tight_item(parts: list[tuple[dict, str]]) -> bool:
    """The item's blocks can be written line by line and mistune reads them back as tight.

    mistune reads an item with two paragraphs as loose, wherever they are."""
    if sum(node["type"] == "paragraph" for node, _ in parts) > 1:
        return False
    return all(_joins(parts[index - 1][0], node, text) for index, (node, text) in enumerate(parts) if index)


def _reads_loose(items: list[list[tuple[dict, str]]]) -> bool:
    """mistune reads the list back as loose when its items and blocks are a blank line apart.

    It sees a blank line between items, and one between an item's blocks unless the
    blank line follows a nested list (which takes it in without becoming loose)."""
    if len(items) > 1:
        return True
    return any(
        sum(node["type"] == "paragraph" for node, _ in parts) > 1
        or any(parts[index - 1][0]["type"] not in _LISTS for index in range(1, len(parts)))
        for parts in items
    )


def _joins(previous: dict, node: dict, text: str) -> bool:
    """True when `node`, written as `text`, may start on the line right after `previous`."""
    if previous["type"] in _CLOSED_BLOCKS:
        return True
    if previous["type"] not in _OPEN_BLOCKS:  # tables and HTML blocks run on to a blank line
        return False
    if previous["type"] == "blockquote":
        # mistune keeps a heading or HTML block in the quote, merges two quotes, and moves a
        # list that follows a quote in front of it once a later block interrupts the list.
        return node["type"] in ("code_block", "horizontal_rule")
    # The next line must interrupt a paragraph, or it would continue the previous block.
    if node["type"] in ("heading", "code_block", "blockquote", "horizontal_rule"):
        return True
    if node["type"] == "bullet_list" or (node["type"] == "ordered_list" and node["attrs"]["start"] == 1):
        return " " in text.split("\n", 1)[0]  # an empty first item cannot interrupt ("-" underlines)
    return False


def _block(node: dict) -> str:
    handler = _BLOCKS.get(node["type"])
    if handler is None:
        raise ValueError(f"cannot serialize a {node['type']!r} node")
    return handler(node)


def _paragraph(node: dict) -> str:
    return _inline(node.get("content", []))


def _heading(node: dict) -> str:
    text = _inline(node.get("content", []), heading=True)
    marker = "#" * node["attrs"]["level"]
    return f"{marker} {text}" if text else marker


def _blockquote(node: dict) -> str:
    inner = _blocks(node.get("content", []))
    if not inner:
        return ">"
    return "\n".join(f"> {line}" if line else ">" for line in inner.split("\n"))


def _horizontal_rule(node: dict) -> str:
    return "---"


def _list(node: dict, alternate: bool = False) -> str:
    """Items with `-` or `1.`, `2.`, ... from `start`; one line apart when tight, a blank line when loose.

    The list is written tight or loose as mistune will read it back: a tight list is
    written loose when some item cannot be tight (_tight_item), and a loose list is
    written tight when mistune would not see its blank lines (_reads_loose)."""
    items = [_item_parts(item) for item in node["content"]]
    tight = all(_tight_item(parts) for parts in items) and (node["attrs"]["tight"] or not _reads_loose(items))
    lines = []
    for index, parts in enumerate(items):
        if node["type"] == "ordered_list":
            marker = f"{node['attrs']['start'] + index}{_ORDERED_DELIMITERS[alternate]}"
        else:
            marker = _BULLETS[alternate]
        lines.append(_list_item(_join(parts, tight), marker))
    return ("\n" if tight else "\n\n").join(lines)


# A task box with no text reads back as an empty first paragraph (docmodel: "- [ ]" + a block).
_BOX_LINE = {"type": "paragraph"}


def _item_parts(node: dict) -> list[tuple[dict, str]]:
    """The item's blocks; a task item's box opens its first paragraph, or stands on its own line."""
    parts = _parts(node.get("content", []))
    checked = node["attrs"]["checked"]
    if checked is None:
        return parts
    box = "[x]" if checked else "[ ]"
    if parts and parts[0][0]["type"] == "paragraph":
        return [(parts[0][0], f"{box} {parts[0][1]}"), *parts[1:]]
    return [(_BOX_LINE, box), *parts]


def _list_item(inner: str, marker: str) -> str:
    """The marker, then the item's Markdown indented to its content column."""
    if not inner:
        return marker
    lines = inner.split("\n")
    if lines[0] == "---":  # "- ---" would be one thematic break, not an item holding a rule
        lines[0] = "___"
    indent = " " * (len(marker) + 1)
    if _THEMATIC_BREAK.fullmatch(f"{marker} {lines[0]}"):  # "- - -": nested items with no text
        return "\n".join([marker] + [indent + line if line else "" for line in lines])
    return "\n".join([f"{marker} {lines[0]}"] + [indent + line if line else "" for line in lines[1:]])


def _code_block(node: dict) -> str:
    """A fence longer than any run of its character in the code; only the language's first word."""
    code = "".join(child["text"] for child in node.get("content", []))
    words = node["attrs"]["language"].split()
    language = _escape_backslashes(words[0]) if words else ""  # the info string takes backslash escapes
    char = "~" if "`" in language else "`"  # a backtick fence's info string cannot hold a backtick
    longest = max((len(run) for run in re.findall(re.escape(char) + "+", code)), default=0)
    fence = char * max(3, longest + 1)
    return f"{fence}{language}\n{code}\n{fence}" if code else f"{fence}{language}\n{fence}"


def _table(node: dict) -> str:
    """A pipe table: the first row is the header, its cells' align attrs give the delimiter row.

    Short rows are padded with empty cells: mistune reads a table whose rows differ in width
    as a paragraph."""
    rows = [[_cell(cell) for cell in row.get("content", [])] for row in node["content"]]
    width = max(len(row) for row in rows)
    aligns = [cell["attrs"]["align"] for cell in node["content"][0].get("content", [])]
    aligns += [None] * (width - len(aligns))
    lines = [rows[0], [_ALIGN_ROW[align] for align in aligns], *rows[1:]]
    return "\n".join("| " + " | ".join(cells + [""] * (width - len(cells))) + " |" for cells in lines)


def _cell(node: dict) -> str:
    """One line of inline Markdown with every unescaped "|" escaped, code spans included.

    docmodel turns "\\|" inside a code span in a cell back into "|" (GFM)."""
    return _UNESCAPED_PIPE.sub(r"\1\\|", _inline(node.get("content", []), cell=True))


def _source(node: dict) -> str:
    return node["attrs"]["source"]


# Node type -> serializer returning the block's lines without a trailing newline ("" = nothing).
_BLOCKS = {
    "paragraph": _paragraph,
    "heading": _heading,
    "blockquote": _blockquote,
    "horizontal_rule": _horizontal_rule,
    "bullet_list": _list,
    "ordered_list": _list,
    "code_block": _code_block,
    "table": _table,
    "html_block": _source,
    "footnote_def": _source,
}


# --- inline: normalization ------------------------------------------------------


def _inline(nodes: list[dict], heading: bool = False, cell: bool = False) -> str:
    """Markdown for the inline content of a paragraph, heading or table cell."""
    return _escape_pieces(_pieces(_normalize(nodes, one_line=heading or cell), cell), heading, cell)


def _marks(node: dict) -> list[dict]:
    return node.get("marks", [])


def _has_mark(node: dict, name: str) -> bool:
    return any(mark["type"] == name for mark in _marks(node))


def _text_node(text: str, marks: list[dict]) -> dict:
    node: dict = {"type": "text", "text": text}
    if marks:
        node["marks"] = marks
    return node


def _normalize(nodes: list[dict], one_line: bool) -> list[dict]:
    """The inline nodes as Markdown can express them.

    Newlines in text become spaces, and in headings and table cells (`one_line`) so do
    hard breaks and newlines in inline HTML; spaces and tabs at line edges are dropped
    (Markdown strips them); trailing hard breaks are dropped (a block cannot end with
    one); whitespace moves out of strong/em/strike runs (their delimiters must touch
    non-whitespace); equal-marked text is merged."""
    flat: list[dict] = []
    for node in nodes:
        if node["type"] == "text":
            flat.append(_text_node(node["text"].replace("\n", " "), _marks(node)))
        elif node["type"] == "hard_break" and one_line:
            flat.append(_text_node(" ", _marks(node)))
        elif node["type"] == "html_inline" and one_line:
            flat.append({**node, "attrs": {"source": node["attrs"]["source"].replace("\n", " ")}})
        else:
            flat.append(node)
    lines: list[list[dict]] = [[]]
    for node in flat:
        if node["type"] == "hard_break":
            lines.append([])
        lines[-1].append(node)
    out: list[dict] = []
    for line in lines:
        out.extend(_strip_line(line))
    while out and out[-1]["type"] == "hard_break":
        out.pop()
    return _merge(_expel_whitespace(out))


def _strip_line(line: list[dict]) -> list[dict]:
    """Drop spaces and tabs at both edges of one line (which may start with its hard_break)."""
    nodes = list(line)
    _strip_edge(nodes, range(len(nodes)), str.lstrip)
    _strip_edge(nodes, range(len(nodes) - 1, -1, -1), str.rstrip)
    return [node for node in nodes if node["type"] != "text" or node["text"]]


def _strip_edge(nodes: list[dict], order: range, strip) -> None:
    for i in order:
        node = nodes[i]
        if node["type"] == "hard_break":
            continue
        if node["type"] != "text" or _has_mark(node, "code"):
            return
        nodes[i] = _text_node(strip(node["text"], " \t"), _marks(node))
        if nodes[i]["text"]:
            return


def _shared(marks: list[dict], *neighbors: list[dict]) -> list[dict]:
    """`marks` without the strong/em/strike marks that some neighbor lacks."""
    return [mark for mark in marks if mark["type"] not in _FLANKED or all(mark in other for other in neighbors)]


def _expel_whitespace(nodes: list[dict]) -> list[dict]:
    """Move leading/trailing whitespace of strong/em/strike runs outside the run.

    Runs also end at the edges of links and strike runs, where _pieces closes them."""
    out: list[dict] = []
    for i, node in enumerate(nodes):
        before = _marks(nodes[i - 1]) if i > 0 and not _edge(nodes[i - 1], node) else []
        after = _marks(nodes[i + 1]) if i + 1 < len(nodes) and not _edge(node, nodes[i + 1]) else []
        if node["type"] == "hard_break":  # whitespace too: inside a run only between its parts
            marks = _shared(_marks(node), before, after)
            out.append({"type": "hard_break", "marks": marks} if marks else {"type": "hard_break"})
            continue
        if node["type"] != "text" or _has_mark(node, "code"):
            out.append(node)
            continue
        text, marks = node["text"], _marks(node)
        core = text.strip()
        if not core:
            out.append(_text_node(text, _shared(marks, before, after)))
            continue
        start, end = len(text) - len(text.lstrip()), len(text.rstrip())
        out.append(_text_node(text[:start], _shared(marks, before)))
        out.append(_text_node(core, marks))
        out.append(_text_node(text[end:], _shared(marks, after)))
    return [node for node in out if node["type"] != "text" or node["text"]]


def _merge(nodes: list[dict]) -> list[dict]:
    merged: list[dict] = []
    for node in nodes:
        previous = merged[-1] if merged else None
        if previous and previous["type"] == node["type"] == "text" and _marks(previous) == _marks(node):
            merged[-1] = _text_node(previous["text"] + node["text"], _marks(node))
        else:
            merged.append(node)
    return merged


# --- inline: marks and pieces ---------------------------------------------------
# Inline content becomes a list of pieces: (document text, inside-link flag) or
# (markup, None) for delimiters, code spans, link syntax, hard breaks, images,
# footnote references and inline HTML. Text is escaped afterwards, when the output
# characters around each text piece are known.


def _pieces(nodes: list[dict], cell: bool = False) -> list[tuple[str, bool | None]]:
    pieces: list[tuple[str, bool | None]] = []
    stack: list[dict] = []  # open marks, outermost first
    for i, node in enumerate(nodes):
        wanted = [mark for mark in _marks(node) if mark["type"] != "code"]
        keep = 0
        if i == 0 or not _edge(nodes[i - 1], node):  # at a link or strike edge all marks close
            while keep < len(stack) and stack[keep] in wanted:
                keep += 1
        for mark in reversed(stack[keep:]):
            pieces.append((_close(mark), None))
        del stack[keep:]
        if autolink := _autolink(nodes, i, cell):
            pieces.append((autolink, None))
            continue
        # Link, then strike; then longer strong/em runs outside shorter ones, strong first on ties.
        opening = [mark for mark in wanted if mark not in stack]
        opening.sort(key=lambda m: (_OUTER_RANK.get(m["type"], 2), -_extent(nodes, i, m), m["type"] != "strong"))
        for mark in opening:
            pieces.append((_DELIMITERS.get(mark["type"], "["), None))
            stack.append(mark)
        pieces.append(_content(node, in_link=_link(node) is not None))
    for mark in reversed(stack):
        pieces.append((_close(mark), None))
    return pieces


def _link(node: dict) -> dict | None:
    return next((mark for mark in _marks(node) if mark["type"] == "link"), None)


def _edge(left: dict, right: dict) -> bool:
    """A link or strike run starts or ends between two adjacent nodes."""
    return _link(left) != _link(right) or _has_mark(left, "strike") != _has_mark(right, "strike")


def _extent(nodes: list[dict], index: int, mark: dict) -> int:
    """How many nodes from `index` on carry `mark`; strong/em runs stop at link and strike edges."""
    count = 1
    while index + count < len(nodes) and mark in _marks(nodes[index + count]):
        if mark["type"] not in _OUTER_RANK and _edge(nodes[index + count - 1], nodes[index + count]):
            break
        count += 1
    return count


def _content(node: dict, in_link: bool) -> tuple[str, bool | None]:
    kind = node["type"]
    if kind == "text":
        if _has_mark(node, "code"):
            return _code_span(node["text"]), None
        return node["text"], in_link
    if kind == "hard_break":
        return "\\\n", None
    if kind == "image":
        return _image(node["attrs"]), None
    if kind == "footnote_ref":
        return f"[^{node['attrs']['label']}]", None
    if kind == "html_inline":
        return node["attrs"]["source"], None
    raise ValueError(f"cannot serialize a {kind!r} node")


def _image(attrs: dict) -> str:
    """![alt](src "title"); the alt text is escaped like link text."""
    alt = _escape(attrs["alt"].replace("\n", " "), "[", "]", True, False, False, False)
    return f"![{alt}](" + _link_target(attrs["src"], attrs["title"]) + ")"


def _close(mark: dict) -> str:
    if mark["type"] == "link":
        return "](" + _link_target(mark["attrs"]["href"], mark["attrs"]["title"]) + ")"
    return _DELIMITERS[mark["type"]]


def _autolink(nodes: list[dict], index: int, cell: bool = False) -> str | None:
    """The node written as an autolink (spec 6.5), or None for a [text](href) link.

    Only an untitled link that is the node's only mark and covers just this node
    qualifies. An http(s) URL whose text is its href stays bare when nothing that
    follows could be read as part of the URL; otherwise it becomes <href>. A mailto:
    link whose text is the address becomes <address>. In a table cell a URL holding
    "|" is written [text](href), where "\\|" can escape the pipe."""
    node = nodes[index]
    link = _link(node)
    if node["type"] != "text" or _marks(node) != [link] or link["attrs"]["title"] is not None:
        return None
    if _extent(nodes, index, link) != 1 or (index > 0 and link in _marks(nodes[index - 1])):
        return None
    text, href = node["text"], link["attrs"]["href"]
    if cell and "|" in text + href:
        return None
    if text == href and _BARE_URL.fullmatch(text) and _bare_url_ends(nodes, index) and not set("&\\") & set(text):
        return text
    if text == href and _URI_AUTOLINK.fullmatch(href):
        return f"<{href}>"
    if href == "mailto:" + text and _EMAIL_AUTOLINK.fullmatch(text):
        return f"<{text}>"
    return None


def _bare_url_ends(nodes: list[dict], index: int) -> bool:
    """Nothing after nodes[index] extends a bare URL: a line end, or (closing punctuation and) whitespace."""
    following = nodes[index + 1] if index + 1 < len(nodes) else None
    if following is None:
        return True
    if following["type"] != "text" or _marks(following):  # also a hard break: the URL would take its "\"
        return False
    rest = following["text"].lstrip(_URL_TRAILING)
    if rest:
        return rest[0].isspace()
    return index + 2 == len(nodes)


def _code_span(code: str) -> str:
    """A backtick run longer than any inside; padded where CommonMark would strip or merge."""
    fence = "`" * (max((len(run) for run in re.findall("`+", code)), default=0) + 1)
    pad = code[0] == "`" or code[-1] == "`" or (code[0] == code[-1] == " " and code.strip(" ") != "")
    return f"{fence} {code} {fence}" if pad else f"{fence}{code}{fence}"


def _link_target(href: str, title: str | None) -> str:
    """The inside of a link's parentheses: destination, then an optional "title"."""
    href = _escape_entities(href)
    if any(ch.isspace() or ord(ch) < 0x20 or ch in "<>" for ch in href):
        target = "<" + re.sub(r"([<>\\])", r"\\\1", href) + ">"
    else:
        target = _escape_backslashes(href)
        if not _parens_balanced(target):
            target = re.sub(r"(?<!\\)([()])", r"\\\1", target)
    if title is None:
        return target
    return target + ' "' + _escape_backslashes(_escape_entities(title)).replace('"', '\\"') + '"'


def _escape_entities(value: str) -> str:
    """Keep a literal "&name;" from being decoded by writing its "&" as "&amp;"."""
    return _ENTITY.sub(lambda m: "&amp;" + m.group()[1:], value)


def _escape_backslashes(value: str) -> str:
    """Double each backslash that would otherwise escape the character after it."""
    return re.sub(r"\\(?=[" + re.escape(string.punctuation) + r"]|$)", r"\\\\", value)


def _parens_balanced(value: str) -> bool:
    depth = 0
    for i, ch in enumerate(value):
        if ch in "()" and i > 0 and value[i - 1] == "\\":
            continue
        depth += {"(": 1, ")": -1}.get(ch, 0)
        if depth < 0:
            return False
    return depth == 0


# --- inline: escaping -----------------------------------------------------------


def _escape_pieces(pieces: list[tuple[str, bool | None]], heading: bool, cell: bool = False) -> str:
    out: list[str] = []
    for i, (value, in_link) in enumerate(pieces):
        if in_link is None:
            out.append(value)
            continue
        before = out[-1][-1:] if out else ""
        after = pieces[i + 1][0][:1] if i + 1 < len(pieces) else ""
        line_start = before in ("", "\n")
        line_end = i + 1 == len(pieces) or pieces[i + 1][0] == "\\\n"
        text = _escape(value, before, after, in_link, line_start, line_end, heading, cell)
        if i == 1 and before == "]" and text[:1] == ":" and not (heading or cell):
            text = "\\" + text  # "[^1]: x" at a paragraph start would define footnote 1
        out.append(text)
    return "".join(out)


def _escape(
    text: str,
    before: str,
    after: str,
    in_link: bool,
    line_start: bool,
    line_end: bool,
    heading: bool,
    cell: bool = False,
) -> str:
    """Backslash-escape what Markdown would read as syntax in `text`, and nothing else.

    `before`/`after` are the output characters around the text ("" at a block edge,
    "\\n" after a hard break); line_start/line_end say whether the text starts/ends a line."""
    escaped: set[int] = set()
    # mistune links bare http(s) URLs anywhere; inside link text one swallows the markup up to "]".
    escaped |= {match.end() for match in _BARE_URL_SCHEME.finditer(text)}
    if line_start and not (heading or cell):
        escaped |= _line_start_escapes(text, line_end)
    if heading and after == "" and (match := _HEADING_CLOSE.search(text)):
        escaped.add(match.start(1))
    # Whitespace that mistune would drop is written as a character reference: after a hard
    # break, and at the edges of a table cell (which mistune strips like str.strip).
    references: set[int] = set()
    if text and text[0].isspace() and (before == "\n" or (cell and line_start)):
        references.add(0)
    if text and text[-1].isspace() and cell and line_end:
        references.add(len(text) - 1)
    for i, ch in enumerate(text):
        prev = ";" if i - 1 in references else text[i - 1] if i > 0 else before
        nxt = "&" if i + 1 in references else text[i + 1] if i + 1 < len(text) else after
        if (
            ch in "*`["
            or (ch == "]" and in_link)
            or (ch == "\\" and nxt in _ASCII_PUNCT)  # a hard break's "\" counts: it follows
            or (ch == "_" and not (prev.isalnum() and nxt.isalnum()))
            or (ch == "~" and "~" in (prev, nxt))
            or (ch == "!" and nxt == "[")
            or (ch == "<" and ((nxt.isascii() and nxt.isalpha()) or nxt in ("/", "!", "?")))
            or (ch == "&" and _ENTITY.match(text, i))
        ):
            escaped.add(i)
    return "".join(
        _char_reference(ch) if i in references else "\\" + ch if i in escaped else ch for i, ch in enumerate(text)
    )


def _char_reference(ch: str) -> str:
    return "&nbsp;" if ch == "\xa0" else f"&#{ord(ch)};"


def _line_start_escapes(text: str, line_end: bool) -> set[int]:
    """Positions to escape so that a line starting with `text` stays paragraph text."""
    if line_end and _UNDERLINE.fullmatch(text):
        return {min(i for i, ch in enumerate(text) if ch in "-=")}
    probe = text if line_end else text + "x"  # markup (non-blank) follows the text
    if text[:1] == ">" or _HEADING_START.match(probe) or _BULLET_START.match(probe):
        return {0}
    if match := _ORDERED_START.match(probe):
        return {match.start(1)}
    return set()
```

- [x] **Step 5: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_serialize.py tests/test_roundtrip.py -q`
Expected: 356 passed.

- [x] **Step 6: Run the full suite and the Qt-import check**

Run:

```bash
.venv/Scripts/python -m pytest -v
rg -n "import (PySide|Qt)|from PySide" mdviewer/core tests
```

Expected: all tests pass (711); the `rg` line prints nothing.

- [x] **Step 7: Commit**

```bash
git add mdviewer/core/serialize.py tests/test_serialize.py tests/test_roundtrip.py tests/corpus
git commit -m "feat: serialize lists, code, tables and protected blocks; add round-trip tests"
```

**Review Focus:**

- Every tight/loose decision matches how mistune reads the output back:
  `test_tight_list_is_written_loose_when_an_item_cannot_be_tight` and
  `test_loose_list_is_written_tight_when_mistune_would_read_it_tight` check
  the parsed `tight` attr, and `test_random_block_trees_round_trip` checks that
  the first save is a fixed point. A change to `_joins`, `_tight_item` or
  `_reads_loose` must keep them green without narrowing the generator.
- Lists never merge or split: adjacent lists switch markers, `- - -` and
  `- ---` never become rules, and an item's lines are all indented to its own
  content column (`10. ` indents by 4).
- Table cells: every unescaped `|` is escaped (code spans, link targets and
  alt text included), rows are padded, and nothing in a cell can end the row.
- `footnote_def` sources come out verbatim and last, in document order;
  `html_block`, `html_inline` and `front_matter` sources are never changed
  except for newlines in inline HTML inside headings and cells.
- The round-trip properties run over `tests/corpus`, `README.md` and every
  Markdown file under `docs/`: valid documents, a fixed point after one pass,
  the same document back (`line` aside), and the same rendered HTML
  (whitespace-normalized; the only extra normalization is the newline before
  `</code></pre>` that indented code lacks).
- The known limits are exactly those listed above. The random generators
  avoid them, with a comment at each place that works around one; loosening a
  generator beyond that must not be needed to keep the tests green.
- The module imports nothing from Qt and only `frontmatter` from `mdviewer`.

## Phase 2 - JS editor (bundle rebuilt and committed in each task)

### Task 8: Schema and node views

**Status: steps detailed.** All code below was run before being written into
this plan (2026-10-20, PySide6 6.12.0 offscreen, Node 26, the Task 1 pins:
prosemirror-model 1.25.12, prosemirror-view 1.42.6, prosemirror-tables 1.8.5,
esbuild 0.28.2), on top of the Task 1 and Task 2 code from this plan. Results:
- `scripts/check_web.py` prints `WEB OK`.
- `tests/test_docschema.py` has 59 passing tests and `tests/test_web_assets.py` 10.
- The full suite passes, `SMOKE OK`, and a second `build_web.py` changes no bytes.
- Run against the Task 1 bundle, the new checks fail with
  `window.mdEditor exposes schema and setDocument`.
- Six deliberate breaks each fail a check:
  - highlight sanitizer removed
  - stale-highlight plugin removed
  - caret plugin removed
  - `allow-scripts` added to the frame
  - unsafe `href` accepted on paste
  - `html_inline` parse priority dropped

**Findings that shape this task:**

- **ProseMirror JSON:**
  - `toJSON()` writes every declared attr. So nested top-level-capable nodes
    carry `line: null` (allowed by docschema), and the three
    `prosemirror-tables` cell attrs appear on every cell.
  - Empty `content` and `marks` are omitted.
  - `check_web.py` compares documents written in exactly this shape.
- **prosemirror-tables:**
  - `tableNodes()` declares `table_row` content as
    `(table_cell | table_header)*`. docschema requires one cell, so the schema
    overrides it with `+`.
  - Cell content `inline*` works.
- **Parse rule order:** at equal priority, `DOMParser` tries mark rules
  before node rules. So `code.md-html-inline` needs `priority: 60`, or the
  `code` mark's `<code>` rule swallows it (break 6 above).
- **Clipboard:**
  - Copying inside the editor serializes with `toDOM` and pastes with
    `parseDOM`, not with the node views.
  - With the rules below, a copy-and-paste of every node type except
    `front_matter` comes back equal, with `line` reset to `null` and
    `highlight` to `""`.
  - `view.serializeForClipboard` and `view.pasteHTML` are public in
    prosemirror-view 1.42, and the check uses them.
- **Node decorations:** a `Decoration.node` class lands on a node view's
  `dom`. The caret plugin uses this to switch a code block between its
  highlight overlay and plain text without re-rendering it.
- **Raw HTML frame (decided with the user on 2026-10-20; spec section 5
  updated in Step 13):**
  - Measured with an **empty sandbox**: the parent cannot read the frame
    (`contentDocument` is `null`), so the frame cannot be sized to its
    content. Local images inside it are refused (`Not allowed to load local
    resource`).
  - Measured with **`sandbox="allow-same-origin"`** (no `allow-scripts`): the
    parent reads the content height and local images load. `<script>` and
    `onerror=` still never run (Chromium logs
    `Blocked script execution in 'about:srcdoc' because the document's frame is sandboxed`).
  - `allow-same-origin` is only dangerous combined with `allow-scripts`. So
    the frame uses `allow-same-origin` alone.
- **Known limit (as in v1):** relative URLs inside raw HTML resolve against
  the page's temp folder, not the document's folder. So
  `<img src="logo.png">` in an `html_block` shows nothing; absolute `file:`,
  `http(s):` and `data:` images show.

**Design decisions:**

- **One contract, two checks.** `schema.js` starts with
  `export const CONTRACT = {...};`, docschema's tables as strict JSON:
  - `tests/test_docschema.py` parses that block and compares it with the
    Python tables, including order.
  - The node and mark specs get their attrs from `CONTRACT`. The module
    throws at load time if the spec names differ from it, so the page never
    reaches `ready()`.
  - `check_web.py` then compares the **live** schema with docschema: attrs,
    the child types each content expression can reach, whether content may
    be empty, the marks allowed per inline-content node, and mark rank.
- **Spec order matters:**
  - Group `block` starts with `paragraph` and group `inline` with `text`,
    because `createAndFill` uses a group's first type.
  - Marks are declared in `docschema.MARKS` order (their rank).
- **Attr defaults:** every attr has a default so ProseMirror can create nodes
  on its own, except `label` (footnotes) and `href` (links), which are never
  created implicitly.
- **`doc` content** is `front_matter? (block | footnote_def)+`. It is
  stricter than docschema's "at least one child", but docmodel always emits
  a block (Task 5: empty documents get an empty paragraph).
- **Protected nodes are atoms.** They are selected and deleted as a unit:
  - `front_matter` and `footnote_def` render via `toDOM` as bordered `<pre>`
    boxes.
  - `footnote_ref` and `html_inline` render as dashed inline chips.
  - `html_block` uses a node view.
  - `front_matter` has **no** `parseDOM`: it is only valid as the first
    node, so a pasted copy becomes a code block.
  - The other protected nodes parse back only from our own classes and
    `data-*` attributes.
- **Double-click** uses a DOM `dblclick` handler (`handleDOMEvents`), not
  ProseMirror's mousedown-based `handleDoubleClickOn`. It is simpler to
  drive from the check and reaches the shield over the `html_block` frame.
  - It works on blocks and on chips: an `html_inline` chip cannot be edited
    in place either.
  - The callback receives the index of the enclosing **top-level** block.
- **Code blocks:**
  - The node view lays a `<pre class="highlight">` copy of the text over the
    editable `<pre>`, with `pointer-events: none`. Both use the same font,
    padding and `pre-wrap`, so clicks land on the right character.
  - The caret plugin adds `md-code-active` while the selection is inside, and
    CSS then hides the overlay.
  - The `highlight` markup is shown only if it is `<span class>` elements
    (parsed in an inert `<template>`).
  - Any transaction that changes a code block's text or attrs clears its
    `highlight` (`appendTransaction`, grouped with the edit in history).
    This includes Task 10's `setCodeLanguage`.
  - The language field is an `<input list>` over the v1 fence languages
    (`FENCE_LANGUAGES`, kept equal to `core/completion.py` by a test). It
    commits a cleaned first word on change or Enter.
- **Images:**
  - The node view shows `display_src`, and keeps `src` in `data-src` so a
    copy-paste keeps the Markdown path.
  - A load error swaps in a dashed placeholder with the alt text (or the
    `src`).
- **Raw HTML:**
  - `<iframe sandbox="allow-same-origin" srcdoc>` with theme colors read from
    the page's CSS variables.
  - The frame is fitted to its content on `load` (after its images) and when
    the width changes.
  - A shield `div` takes all clicks.
  - `refreshFrames()` re-renders the frames for a theme change (Task 9's
    `setTheme` calls it).
- **Paste safety lives in `parseDOM`:**
  - `isSafeUrl` (same policy as `core/urls.is_safe`) drops unsafe link marks
    (the text stays) and unsafe images.
  - GitHub's task-list checkboxes, `language-*` classes and cell alignment
    are read.
- **Minimal page API until Task 9:** `window.mdEditor` gains `schema`,
  `view`, `events`, `setDocument(json)` (validates with `doc.check()`) and
  `focusBlock(index)`.
  - `events` records the calls meant for Python (`["editProtected", index]`).
    Task 9 turns them into bridge signals.

**Files:**
- Create: `web-src/src/schema.js`, `web-src/src/nodeviews.js`, `web-src/src/editor.css`
- Replace: `web-src/src/editor.js`
- Modify: `tests/test_docschema.py`, `tests/test_web_assets.py`, `scripts/check_web.py`
- Modify: `docs/superpowers/specs/2026-10-20-wysiwyg-editing-design.md` (section 5, item 1)
- Regenerate and commit: `mdviewer/web/editor.js`, `mdviewer/web/editor.css`, `mdviewer/web/THIRD_PARTY.txt`

**Interfaces:**
- Consumes:
  - `docschema` tables (Task 2) and `completion.FENCE_LANGUAGES` (v1)
  - `render.highlight_code` markup shape (Task 5): `<span class>` only, text
    kept exactly
  - Task 1's page shell, `build_web.py` and `check_web.py` helpers (`check`,
    `pump`, `run_js`, `build_page`)
- Produces (later tasks rely on these exact names):
  - `web-src/src/schema.js`:
    - `CONTRACT`, `schema`
    - `isSafeUrl(url) -> boolean` (Task 11's paste and link paths)
    - `cleanLanguage(value) -> string` (Task 10's `setCodeLanguage`)
  - `web-src/src/nodeviews.js`:
    - `FENCE_LANGUAGES`
    - `createNodeViews()`
    - `displayPlugins(callbacks)`, where `callbacks.editProtected(index)`
      is called on double-click
    - `refreshFrames()`
  - `window.mdEditor` (`web-src/src/editor.js`):
    - `{ schema, view, events, setDocument(json), getDocument(), focusBlock(index) }`
    - Task 9 keeps `schema`, `view`, `setDocument`, `getDocument` and
      `focusBlock` (`check_web.py` uses them).
    - Task 9 also wires `callbacks.editProtected` to the bridge, replaces
      `events`, and updates the double-click check to watch the bridge
      signal.
    - Task 9's `getDocument` drops the cell attrs `colspan`, `rowspan` and
      `colwidth`. `check_web.py`'s `without_cell_extras` then has nothing
      left to strip.
  - DOM hooks:
    - `li.task-list-item > input.task-list-item-checkbox` (Task 10 toggles
      `checked` on click)
    - `.md-code-block`, `input.md-code-language`, `.md-protected`,
      `.md-chip`, `.md-html-block`, `.md-image`, `.md-image-broken`
  - `scripts/check_web.py`:
    - `every_node_doc()`, `without_cell_extras()`,
      `without_lines_and_highlight()`, `set_doc()`, `get_doc()`,
      `check_editor(app, view, folder)`
    - Tasks 9-11 append their checks to `check_editor`.

- [x] **Step 1: Write the failing schema-sync tests**

In `tests/test_docschema.py`, replace the first line

```python
import pytest
```

with

```python
import json
import re
from pathlib import Path

import pytest
```

and append to the end of the file:

```python


# --- web-src/src/schema.js mirrors this module ------------------------------------------------

def js_contract():
    """The CONTRACT block of web-src/src/schema.js, parsed as JSON."""
    source = (Path(__file__).resolve().parent.parent / "web-src" / "src" / "schema.js").read_text(encoding="utf-8")
    match = re.search(r"^export const CONTRACT = (\{.*?^\});$", source, flags=re.S | re.M)
    assert match, "schema.js has no 'export const CONTRACT = {...};' block"
    return json.loads(match.group(1))


def test_js_schema_nodes_match_docschema_in_order():
    contract = js_contract()
    assert list(contract["blockNodes"].items()) == [(name, list(attrs)) for name, attrs in BLOCK_NODES.items()]
    assert list(contract["inlineNodes"].items()) == [(name, list(attrs)) for name, attrs in INLINE_NODES.items()]


def test_js_schema_marks_match_docschema_in_rank_order():
    assert list(js_contract()["marks"].items()) == [(name, list(attrs)) for name, attrs in MARKS.items()]


def test_js_schema_node_sets_match_docschema():
    contract = js_contract()
    assert contract["protectedNodes"] == sorted(PROTECTED_NODES)
    assert contract["topLevelNodes"] == sorted(TOP_LEVEL_NODES)
```

In `tests/test_web_assets.py`, replace

```python
import re
```

with

```python
import json
import re
```

and append to the end of the file:

```python


def test_code_block_languages_match_the_source_editor():
    from mdviewer.core.completion import FENCE_LANGUAGES

    source = (ROOT / "web-src" / "src" / "nodeviews.js").read_text(encoding="utf-8")
    match = re.search(r"^export const FENCE_LANGUAGES = (\[.*?^\]);$", source, flags=re.S | re.M)
    assert match, "nodeviews.js has no 'export const FENCE_LANGUAGES = [...];' block"
    assert json.loads(match.group(1)) == list(FENCE_LANGUAGES)
```

(`completion.py` is Qt-free, so `tests/` stays Qt-free.)

- [x] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_docschema.py tests/test_web_assets.py -v`
Expected: the 4 new tests FAIL with `FileNotFoundError` (`web-src/src/schema.js`,
`web-src/src/nodeviews.js`); the 65 existing tests pass.

- [x] **Step 3: Write the failing page checks**

In `scripts/check_web.py`, replace

```python
import json
```

with

```python
import base64
import json
```

replace

```python
from mdviewer.core import render  # noqa: E402
```

with

```python
from mdviewer.core import docschema, render  # noqa: E402
from mdviewer.core.completion import FENCE_LANGUAGES  # noqa: E402
```

insert the following block directly above `def main() -> int:` (two blank
lines before and after it):

```python
# --- Task 8: schema and node views ----------------------------------------------------------

# Attrs the JS schema declares beyond docschema: prosemirror-tables needs them on cells.
CELL_EXTRAS = ("colspan", "rowspan", "colwidth")
PNG_1PX = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGD4DwAB"
    "BAEAwS2OUAAAAABJRU5ErkJggg=="
)
# Raw HTML: pixel.png (written next to the page by check_editor) must load in the frame;
# the script and the error handler would post a message if they ever ran.
HTML_SOURCE = (
    '<div id="raw">raw <b>html</b></div>\n<img src="pixel.png" height="120">\n'
    "<script>parent.postMessage('script ran', '*')</script>\n"
    "<img src=\"missing.png\" onerror=\"parent.postMessage('handler ran', '*')\">"
)
HIGHLIGHT = '<span class="k">pass</span>'
CODE_INDEX = 6  # top-level index of the highlighted code block in every_node_doc()

# Per node type: [attr names, child types its content can hold, content may be empty];
# per inline-content type: the marks it allows; and the marks in rank order.
SCHEMA_SHAPE_JS = """(() => {
  const schema = window.mdEditor.schema;
  const nodes = {};
  for (const type of Object.values(schema.nodes)) {
    const children = new Set(), seen = new Set(), todo = [type.contentMatch];
    while (todo.length) {
      const match = todo.pop();
      if (seen.has(match)) continue;
      seen.add(match);
      for (let i = 0; i < match.edgeCount; i++) {
        children.add(match.edge(i).type.name);
        todo.push(match.edge(i).next);
      }
    }
    nodes[type.name] = [Object.keys(type.spec.attrs || {}).sort(), [...children].sort(), type.contentMatch.validEnd];
  }
  const marks = Object.keys(schema.marks);
  const marked = Object.values(schema.nodes).filter((type) => type.inlineContent)
    .map((type) => [type.name, marks.filter((mark) => type.allowsMarkType(schema.marks[mark]))]);
  return { nodes, marks, marked: Object.fromEntries(marked) };
})()"""


def every_node_doc() -> dict:
    """Every node and mark, written exactly as ProseMirror's toJSON() returns it."""
    def text(value, *marks):
        node = {"type": "text", "text": value}
        if marks:
            node["marks"] = list(marks)
        return node

    def para(*inline, line=None):
        node = {"type": "paragraph", "attrs": {"line": line}}
        if inline:
            node["content"] = list(inline)
        return node

    def item(*blocks, checked=None):
        return {"type": "list_item", "attrs": {"checked": checked}, "content": list(blocks)}

    def cell(kind, align, *inline):
        node = {"type": kind, "attrs": {"align": align}}
        if inline:
            node["content"] = list(inline)
        return node

    link = {"type": "link", "attrs": {"href": "https://example.com", "title": "Example"}}
    return {"type": "doc", "content": [
        {"type": "front_matter", "attrs": {"source": "---\ntitle: x\n---\n", "line": 1}},
        {"type": "heading", "attrs": {"level": 2, "line": 5}, "content": [text("Title")]},
        para(
            text("all", {"type": "strong"}, {"type": "em"}, {"type": "strike"}, {"type": "code"}, link),
            text(" plain "),
            {"type": "hard_break"},
            {"type": "image", "attrs": {"src": "pixel.png", "display_src": PNG_1PX, "alt": "pixel", "title": None},
             "marks": [link]},
            {"type": "image",
             "attrs": {"src": "gone.png", "display_src": "file:///nowhere/gone.png", "alt": "Gone", "title": "t"}},
            {"type": "footnote_ref", "attrs": {"label": "1"}},
            {"type": "html_inline", "attrs": {"source": "<kbd>"}},
            line=7,
        ),
        {"type": "blockquote", "attrs": {"line": 9}, "content": [para(text("quoted"))]},
        {"type": "bullet_list", "attrs": {"tight": True, "line": 11}, "content": [
            item(para(text("one"))),
            item(para(text("done")), {"type": "ordered_list", "attrs": {"start": 0, "tight": False, "line": None},
                                      "content": [item(para(), checked=False)]}, checked=True),
        ]},
        {"type": "ordered_list", "attrs": {"start": 3, "tight": True, "line": 14}, "content": [
            item({"type": "code_block", "attrs": {"language": "", "highlight": "", "line": None},
                  "content": [text("first block is code")]}),
        ]},
        {"type": "code_block", "attrs": {"language": "python", "highlight": HIGHLIGHT, "line": 16},
         "content": [text("pass")]},
        {"type": "code_block", "attrs": {"language": "", "highlight": "", "line": 19}},
        {"type": "horizontal_rule", "attrs": {"line": 21}},
        {"type": "table", "attrs": {"line": 23}, "content": [
            {"type": "table_row", "content": [cell("table_header", "left", text("h")), cell("table_header", None)]},
            {"type": "table_row", "content": [cell("table_cell", "right", text("c", {"type": "em"})),
                                              cell("table_cell", "center")]},
        ]},
        {"type": "html_block", "attrs": {"source": HTML_SOURCE, "line": 27}},
        para(line=31),
        {"type": "footnote_def", "attrs": {"label": "1", "source": "[^1]: note", "line": 33}},
    ]}


def without_cell_extras(node):
    """`node` without prosemirror-tables' cell attrs (Task 9's getDocument removes them itself)."""
    if isinstance(node, list):
        return [without_cell_extras(child) for child in node]
    if not isinstance(node, dict):
        return node
    copy = {key: without_cell_extras(value) for key, value in node.items()}
    if copy.get("type") in ("table_header", "table_cell"):
        copy["attrs"] = {key: value for key, value in copy["attrs"].items() if key not in CELL_EXTRAS}
    return copy


def without_lines_and_highlight(node):
    """`node` as a paste rebuilds it: no source lines, no precomputed highlight."""
    if isinstance(node, list):
        return [without_lines_and_highlight(child) for child in node]
    if not isinstance(node, dict):
        return node
    copy = {key: without_lines_and_highlight(value) for key, value in node.items()}
    attrs = copy.get("attrs")
    if isinstance(attrs, dict):
        copy["attrs"] = {**attrs}
        if docschema.LINE_ATTR in attrs:
            copy["attrs"][docschema.LINE_ATTR] = None
        if "highlight" in attrs:
            copy["attrs"]["highlight"] = ""
    return copy


def expected_schema_shape() -> dict:
    nodes = {}
    for name, attrs in {**docschema.BLOCK_NODES, **docschema.INLINE_NODES}.items():
        names = set(attrs)
        if name in docschema.TOP_LEVEL_NODES:
            names.add(docschema.LINE_ATTR)
        if name in ("table_header", "table_cell"):
            names.update(CELL_EXTRAS)
        allowed, minimum = docschema.CONTENT.get(name, (frozenset(), 0))
        nodes[name] = [sorted(names), sorted(allowed), minimum == 0]
    marked = {
        name: [] if name == "code_block" else list(docschema.MARKS)
        for name, (allowed, _) in docschema.CONTENT.items()
        if allowed <= set(docschema.INLINE_NODES)
    }
    return {"nodes": nodes, "marks": list(docschema.MARKS), "marked": marked}


def set_doc(app: QApplication, view: QWebEngineView, doc: dict) -> None:
    run_js(app, view, f"(window.mdEditor.setDocument({json.dumps(doc)}), 0)")


def get_doc(app: QApplication, view: QWebEngineView):
    return without_cell_extras(run_js(app, view, "window.mdEditor.getDocument()"))


def code_block_state(app: QApplication, view: QWebEngineView) -> dict:
    """DOM state of the second code block, the highlighted one at CODE_INDEX."""
    return run_js(app, view, f"""(() => {{
      const block = document.querySelectorAll('#editor .md-code-block')[1];
      return {{
        classes: [...block.classList].sort(),
        overlay: getComputedStyle(block.querySelector('.md-code-highlight')).display,
        keyword: block.querySelector('.md-code-highlight span.k')?.textContent ?? null,
        language: block.querySelector('input.md-code-language').value,
        highlight: window.mdEditor.getDocument().content[{CODE_INDEX}].attrs.highlight,
      }};
    }})()""")


def check_editor(app: QApplication, view: QWebEngineView, folder: Path) -> None:
    if not run_js(app, view, "Boolean(window.mdEditor && window.mdEditor.schema && window.mdEditor.setDocument)"):
        check(False, "window.mdEditor exposes schema and setDocument")
        return
    (folder / "pixel.png").write_bytes(base64.b64decode(PNG_1PX.split(",", 1)[1]))
    check(run_js(app, view, SCHEMA_SHAPE_JS) == expected_schema_shape(),
          "JS schema: names, attrs, content rules and mark ranks match core/docschema.py")

    run_js(app, view, "(window.frameMessages = [], addEventListener('message', (e) => frameMessages.push(e.data)), 0)")
    doc = every_node_doc()
    check(docschema.validate(without_cell_extras(doc)) == [], "the every-node document is valid in Python")
    set_doc(app, view, doc)
    check(get_doc(app, view) == doc, "every node type comes back unchanged from setDocument/getDocument")
    check(run_js(app, view, "window.mdEditor.events.length") == 0, "loading a document sends no events")

    # Code block: highlight overlay while the caret is elsewhere, plain text inside, cleared on edit.
    state = code_block_state(app, view)
    check("md-has-highlight" in state["classes"] and "md-code-active" not in state["classes"]
          and state["overlay"] == "block" and state["keyword"] == "pass" and state["language"] == "python",
          f"code block shows the Python highlight while the caret is outside ({state})")
    run_js(app, view, f"(window.mdEditor.focusBlock({CODE_INDEX}), 0)")
    state = code_block_state(app, view)
    check("md-code-active" in state["classes"] and state["overlay"] == "none",
          f"code block shows plain text while the caret is inside ({state})")
    run_js(app, view, "(window.mdEditor.focusBlock(1), 0)")
    check(code_block_state(app, view)["overlay"] == "block", "the highlight comes back when the caret leaves")
    run_js(app, view, "(window.mdEditor.view.dispatch(window.mdEditor.view.state.tr.insertText('y', 2)), 0)")
    check(get_doc(app, view)["content"][1]["content"][0]["text"] == "yTitle"
          and code_block_state(app, view)["highlight"] == HIGHLIGHT,
          "typing outside a code block keeps its highlight")
    run_js(app, view, f"""(window.mdEditor.focusBlock({CODE_INDEX}),
        window.mdEditor.view.dispatch(window.mdEditor.view.state.tr.insertText('x')), 0)""")
    state = code_block_state(app, view)
    check(state["highlight"] == "" and "md-has-highlight" not in state["classes"],
          f"typing in a code block clears its highlight ({state})")

    set_doc(app, view, doc)
    run_js(app, view, """(() => {
      const field = document.querySelectorAll('#editor .md-code-block')[1].querySelector('input');
      field.value = '  rust extra`';
      field.dispatchEvent(new Event('change'));
      return 0;
    })()""")
    block = get_doc(app, view)["content"][CODE_INDEX]["attrs"]
    check(block["language"] == "rust" and block["highlight"] == "",
          f"the language field sets a cleaned language and clears the highlight ({block})")
    check(run_js(app, view, "document.querySelectorAll('datalist#md-fence-languages option').length")
          == len(FENCE_LANGUAGES), "the language field offers the fence languages")

    set_doc(app, view, {"type": "doc", "content": [
        {"type": "code_block", "attrs": {"language": "x", "highlight": '<img src="x">', "line": None},
         "content": [{"type": "text", "text": "x"}]}]})
    check(run_js(app, view, "document.querySelector('#editor .md-code-block.md-has-highlight') === null"),
          "highlight markup other than <span class> is not shown")

    # Images: a loaded image shows display_src; a missing one shows its alt text.
    set_doc(app, view, doc)
    pump(app, lambda: run_js(app, view, "document.querySelector('#editor .md-image-broken') !== null"), 3)
    images = run_js(app, view, """[...document.querySelectorAll('#editor .md-image')].map((span) => {
      const img = span.querySelector('img');
      return img ? ['img', img.naturalWidth, img.dataset.src] : ['broken', span.textContent, span.firstChild.title];
    })""")
    check(images == [["img", 1, "pixel.png"], ["broken", "Gone", "gone.png"]], f"image node views ({images})")

    # Raw HTML: same-origin sandbox without scripts, fitted to its content, nothing in it runs.
    fitted = """(() => {
      const frame = document.querySelector('#editor .md-html-block iframe');
      const root = frame.contentDocument?.documentElement;
      return root ? [frame.offsetHeight, Math.ceil(root.getBoundingClientRect().height),
                     frame.contentDocument.images[0]?.naturalWidth ?? 0] : null;
    })()"""
    pump(app, lambda: (run_js(app, view, fitted) or [0, 1, 0])[2] == 1, 3)
    pump(app, lambda: False, 0.3)  # the error handler and the fit after "load" would have run by now
    frame = run_js(app, view, """(() => {
      const frame = document.querySelector('#editor .md-html-block iframe');
      return [frame.getAttribute('sandbox'), frame.srcdoc.includes('<div id="raw">'),
              document.querySelector('#editor .md-html-block .md-shield') !== null];
    })()""")
    check(frame == ["allow-same-origin", True, True],
          f"html_block renders in a script-less sandboxed iframe behind a shield ({frame})")
    size = run_js(app, view, fitted)
    check(size is not None and size[0] == size[1] and size[0] >= 120 and size[2] == 1,
          f"the raw HTML frame loads local images and fits its content ([height, content, image] = {size})")
    check(run_js(app, view, "window.frameMessages") == [], "scripts and handlers in raw HTML never run")
    check(run_js(app, view, "document.querySelector('#editor #raw, #editor script') === null"),
          "raw HTML never enters the editor DOM")

    # Double-click on protected nodes reports the top-level block index.
    run_js(app, view, """(() => {
      const hit = (selector) => document.querySelector('#editor ' + selector)
        .dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true }));
      ['.md-front-matter', '.md-html-inline', '.md-html-block .md-shield', '.md-footnote-def'].forEach(hit);
      return 0;
    })()""")
    events = run_js(app, view, "window.mdEditor.events")
    check(events == [["editProtected", 0], ["editProtected", 2], ["editProtected", 10], ["editProtected", 12]],
          f"double-click on protected nodes ({events})")

    # Copy and paste inside the editor keeps every node (front matter aside: it is only valid first).
    body = {"type": "doc", "content": doc["content"][1:]}
    set_doc(app, view, body)
    run_js(app, view, """(() => {
      const view = window.mdEditor.view;
      const html = view.serializeForClipboard(view.state.doc.slice(0, view.state.doc.content.size)).dom.innerHTML;
      window.mdEditor.setDocument({ type: 'doc', content: [{ type: 'paragraph' }] });
      view.pasteHTML(html);
      return 0;
    })()""")
    check(get_doc(app, view) == without_lines_and_highlight(body),
          "copy and paste inside the editor keeps every node (line and highlight reset)")

    # Pasted HTML from elsewhere: unsafe URLs are dropped, GitHub markup is read.
    set_doc(app, view, {"type": "doc", "content": [{"type": "paragraph"}]})
    run_js(app, view, """(window.mdEditor.view.pasteHTML(
      '<p><a href="java\tscript:alert(1)">bad</a> <a href="https://ok.example/">ok</a>' +
      '<img src="javascript:x" alt="no"><img src="data:text/html,x" alt="no2"></p>' +
      '<ul><li class="task-list-item"><input type="checkbox" class="task-list-item-checkbox" checked> t</li></ul>' +
      '<pre><code class="language-go">x</code></pre><table><tr><th align="center">h</th></tr></table>'), 0)""")
    pasted = get_doc(app, view)["content"]
    para = {"type": "paragraph", "attrs": {"line": None}}
    check(pasted == [
        {**para, "content": [
            {"type": "text", "text": "bad "},
            {"type": "text", "text": "ok",
             "marks": [{"type": "link", "attrs": {"href": "https://ok.example/", "title": None}}]},
        ]},
        {"type": "bullet_list", "attrs": {"tight": True, "line": None}, "content": [
            {"type": "list_item", "attrs": {"checked": True},
             "content": [{**para, "content": [{"type": "text", "text": "t"}]}]},
        ]},
        {"type": "code_block", "attrs": {"language": "go", "highlight": "", "line": None},
         "content": [{"type": "text", "text": "x"}]},
        {"type": "table", "attrs": {"line": None}, "content": [{"type": "table_row", "content": [
            {"type": "table_header", "attrs": {"align": "center"}, "content": [{"type": "text", "text": "h"}]},
        ]}]},
    ], f"pasted HTML: unsafe URLs dropped, task box, code language and cell align kept ({pasted})")
```

and in `main()`, directly after

```python
    check(isinstance(doc, dict) and doc.get("type") == "doc", f"mdEditor.getDocument() returns a doc ({doc!r})")
```

add

```python
    check_editor(app, view, folder)
```

- [x] **Step 4: Run the page check to verify it fails**

Run: `.venv/Scripts/python scripts/check_web.py`
Expected: exit code 1 with

```
WEB CHECK FAILED:
  - window.mdEditor exposes schema and setDocument
```

(the committed bundle is still Task 1's), plus the console dump.

- [x] **Step 5: Write the schema**

Create `web-src/src/schema.js`:

```js
// ProseMirror schema of the Rendered editor, mirroring mdviewer/core/docschema.py.
// CONTRACT holds docschema's names and required attrs as strict JSON:
// tests/test_docschema.py parses it and compares it with the Python tables. The specs
// below get their attrs from CONTRACT and must list the same names in the same order
// (checked when this module loads). Change both files together and rebuild the bundle.
import { Schema } from "prosemirror-model";
import { tableNodes } from "prosemirror-tables";

export const CONTRACT = {
  "blockNodes": {
    "doc": [],
    "paragraph": [],
    "heading": ["level"],
    "blockquote": [],
    "bullet_list": ["tight"],
    "ordered_list": ["start", "tight"],
    "list_item": ["checked"],
    "code_block": ["language", "highlight"],
    "horizontal_rule": [],
    "table": [],
    "table_row": [],
    "table_header": ["align"],
    "table_cell": ["align"],
    "front_matter": ["source"],
    "html_block": ["source"],
    "footnote_def": ["label", "source"]
  },
  "inlineNodes": {
    "text": [],
    "hard_break": [],
    "image": ["src", "display_src", "alt", "title"],
    "footnote_ref": ["label"],
    "html_inline": ["source"]
  },
  "marks": {
    "strong": [],
    "em": [],
    "strike": [],
    "code": [],
    "link": ["href", "title"]
  },
  "protectedNodes": ["footnote_def", "footnote_ref", "front_matter", "html_block", "html_inline"],
  "topLevelNodes": [
    "blockquote", "bullet_list", "code_block", "footnote_def", "front_matter", "heading",
    "horizontal_rule", "html_block", "ordered_list", "paragraph", "table"
  ]
};

// Defaults let ProseMirror create nodes on its own (createAndFill, paste). label and
// href have none: a footnote or link without them is never created implicitly.
const ATTR_DEFAULTS = {
  level: 1, tight: true, start: 1, checked: null, language: "", highlight: "",
  align: null, source: "", src: "", display_src: "", alt: "", title: null,
};
const TOP_LEVEL = new Set(CONTRACT.topLevelNodes);
const ALIGNMENTS = ["left", "center", "right"];

// Same policy as core/urls.is_safe: no script URLs, no data: URLs except images.
// Browsers ignore ASCII whitespace and control characters inside a scheme.
export function isSafeUrl(url) {
  const compact = [...String(url)].filter((ch) => ch.codePointAt(0) > 0x20).join("").toLowerCase();
  return compact.startsWith("data:image/") || !/^(javascript|vbscript|data):/.test(compact);
}

// A fence info word: no whitespace, no backticks (they would end a backtick fence).
export function cleanLanguage(value) {
  return (String(value).trim().split(/\s+/)[0] || "").replace(/`/g, "");
}

function tightFromDOM(dom) {
  const tight = dom.getAttribute("data-tight");
  return tight === null ? !dom.querySelector(":scope > li > p") : tight === "true";
}

function startFromDOM(dom) {
  const start = parseInt(dom.getAttribute("start") ?? "1", 10);
  return Number.isInteger(start) && start >= 0 ? start : 1;
}

// GitHub task items: <li class="task-list-item"><input type="checkbox" checked> text</li>,
// or with the box inside the first <p> of a loose list.
function checkedFromDOM(dom) {
  const box = dom.querySelector(
    ":scope > input[type=checkbox], :scope > p:first-child > input[type=checkbox]",
  );
  return box ? box.hasAttribute("checked") : null;
}

function languageFromDOM(dom) {
  const code = dom.querySelector("code");
  const fromClass = /(?:^|\s)language-(\S+)/.exec(code ? code.className : "");
  return cleanLanguage(dom.getAttribute("data-language") || (fromClass ? fromClass[1] : ""));
}

function alignFromDOM(dom) {
  const align = (dom.style.textAlign || dom.getAttribute("align") || "").toLowerCase();
  return ALIGNMENTS.includes(align) ? align : null;
}

function imageFromDOM(dom) {
  const src = dom.getAttribute("data-src") ?? dom.getAttribute("src");
  const displaySrc = dom.getAttribute("src");
  if (!isSafeUrl(src) || !isSafeUrl(displaySrc)) return false;
  return { src, display_src: displaySrc, alt: dom.getAttribute("alt") ?? "", title: dom.getAttribute("title") };
}

const tables = tableNodes({
  tableGroup: "block",
  cellContent: "inline*",
  cellAttributes: {
    align: {
      default: null,
      getFromDOM: alignFromDOM,
      setDOMAttr: (value, attrs) => {
        if (value) attrs.style = `${attrs.style || ""}text-align: ${value};`;
      },
    },
  },
});

// Node specs in CONTRACT order. Group "block" must start with paragraph and group
// "inline" with text: ProseMirror fills required content with a group's first type.
// toDOM is what ProseMirror renders without a node view and what it puts on the
// clipboard; parseDOM reads pasted HTML, including our own clipboard output.
const nodes = {
  doc: { content: "front_matter? (block | footnote_def)+" },
  paragraph: {
    content: "inline*",
    group: "block",
    parseDOM: [{ tag: "p" }],
    toDOM: () => ["p", 0],
  },
  heading: {
    content: "inline*",
    group: "block",
    defining: true,
    parseDOM: [1, 2, 3, 4, 5, 6].map((level) => ({ tag: `h${level}`, attrs: { level } })),
    toDOM: (node) => [`h${node.attrs.level}`, 0],
  },
  blockquote: {
    content: "block+",
    group: "block",
    defining: true,
    parseDOM: [{ tag: "blockquote" }],
    toDOM: () => ["blockquote", 0],
  },
  bullet_list: {
    content: "list_item+",
    group: "block",
    parseDOM: [{ tag: "ul", getAttrs: (dom) => ({ tight: tightFromDOM(dom) }) }],
    toDOM: (node) => ["ul", { "data-tight": String(node.attrs.tight) }, 0],
  },
  ordered_list: {
    content: "list_item+",
    group: "block",
    parseDOM: [{ tag: "ol", getAttrs: (dom) => ({ start: startFromDOM(dom), tight: tightFromDOM(dom) }) }],
    toDOM: (node) => [
      "ol",
      { start: node.attrs.start === 1 ? null : node.attrs.start, "data-tight": String(node.attrs.tight) },
      0,
    ],
  },
  list_item: {
    content: "block+",
    defining: true,
    parseDOM: [{ tag: "li", getAttrs: (dom) => ({ checked: checkedFromDOM(dom) }) }],
    toDOM: (node) => {
      if (node.attrs.checked === null) return ["li", 0];
      const box = { type: "checkbox", class: "task-list-item-checkbox", contenteditable: "false" };
      if (node.attrs.checked) box.checked = "";
      return ["li", { class: "task-list-item" }, ["input", box], ["div", 0]];
    },
  },
  code_block: {
    content: "text*",
    marks: "",
    group: "block",
    code: true,
    defining: true,
    parseDOM: [{ tag: "pre", preserveWhitespace: "full", getAttrs: (dom) => ({ language: languageFromDOM(dom) }) }],
    toDOM: (node) => ["pre", { "data-language": node.attrs.language || null }, ["code", 0]],
  },
  horizontal_rule: {
    group: "block",
    parseDOM: [{ tag: "hr" }],
    toDOM: () => ["hr"],
  },
  table: tables.table,
  // prosemirror-tables allows empty rows ("*"); docschema requires a cell.
  table_row: { ...tables.table_row, content: "(table_cell | table_header)+" },
  table_header: tables.table_header,
  table_cell: tables.table_cell,
  // No parseDOM: front matter is only valid as the first node, so a pasted copy
  // arrives as a code block instead.
  front_matter: {
    atom: true,
    toDOM: (node) => ["pre", { class: "md-protected md-front-matter" }, node.attrs.source],
  },
  html_block: {
    group: "block",
    atom: true,
    parseDOM: [{ tag: "div.md-html-block", getAttrs: (dom) => ({ source: dom.getAttribute("data-source") ?? "" }) }],
    toDOM: (node) => [
      "div",
      { class: "md-protected md-html-block", "data-source": node.attrs.source },
      ["pre", node.attrs.source],
    ],
  },
  footnote_def: {
    atom: true,
    parseDOM: [{
      tag: "div.md-footnote-def[data-label]",
      getAttrs: (dom) => dom.getAttribute("data-label")
        ? { label: dom.getAttribute("data-label"), source: dom.getAttribute("data-source") ?? "" }
        : false,
    }],
    toDOM: (node) => [
      "div",
      { class: "md-protected md-footnote-def", "data-label": node.attrs.label, "data-source": node.attrs.source },
      ["pre", node.attrs.source],
    ],
  },
  text: { group: "inline" },
  hard_break: {
    inline: true,
    group: "inline",
    selectable: false,
    parseDOM: [{ tag: "br" }],
    toDOM: () => ["br"],
  },
  image: {
    inline: true,
    group: "inline",
    draggable: true,
    parseDOM: [{ tag: "img[src]", getAttrs: imageFromDOM }],
    toDOM: (node) => [
      "img",
      { src: node.attrs.display_src, "data-src": node.attrs.src, alt: node.attrs.alt, title: node.attrs.title },
    ],
  },
  footnote_ref: {
    inline: true,
    group: "inline",
    atom: true,
    parseDOM: [{
      tag: "sup.md-footnote-ref[data-label]",
      getAttrs: (dom) => (dom.getAttribute("data-label") ? { label: dom.getAttribute("data-label") } : false),
    }],
    toDOM: (node) => ["sup", { class: "md-chip md-footnote-ref", "data-label": node.attrs.label }, node.attrs.label],
  },
  html_inline: {
    inline: true,
    group: "inline",
    atom: true,
    // Above the code mark's <code> rule, which would otherwise win.
    parseDOM: [{ tag: "code.md-html-inline", priority: 60, getAttrs: (dom) => ({ source: dom.textContent }) }],
    toDOM: (node) => ["code", { class: "md-chip md-html-inline" }, node.attrs.source],
  },
};

// Mark specs in CONTRACT order: ProseMirror sorts a node's marks by this rank, and
// docmodel emits them in docschema.MARKS order.
const marks = {
  strong: {
    parseDOM: [
      { tag: "strong" },
      // Google Docs wraps whole pastes in <b style="font-weight: normal">.
      { tag: "b", getAttrs: (dom) => dom.style.fontWeight !== "normal" && null },
      { style: "font-weight", getAttrs: (value) => /^(bold(er)?|[5-9]\d{2,})$/.test(value) && null },
    ],
    toDOM: () => ["strong", 0],
  },
  em: {
    parseDOM: [{ tag: "em" }, { tag: "i" }, { style: "font-style=italic" }],
    toDOM: () => ["em", 0],
  },
  strike: {
    parseDOM: [{ tag: "del" }, { tag: "s" }, { tag: "strike" }, { style: "text-decoration=line-through" }],
    toDOM: () => ["del", 0],
  },
  code: {
    parseDOM: [{ tag: "code" }],
    toDOM: () => ["code", 0],
  },
  link: {
    inclusive: false,
    parseDOM: [{
      tag: "a[href]",
      getAttrs: (dom) => (isSafeUrl(dom.getAttribute("href"))
        ? { href: dom.getAttribute("href"), title: dom.getAttribute("title") }
        : false),
    }],
    toDOM: (mark) => ["a", { href: isSafeUrl(mark.attrs.href) ? mark.attrs.href : null, title: mark.attrs.title }, 0],
  },
};

function withContractAttrs(specs, contract, what) {
  if (Object.keys(specs).join() !== Object.keys(contract).join()) {
    throw new Error(`schema.js: ${what} differ from CONTRACT`);
  }
  for (const [name, spec] of Object.entries(specs)) {
    const attrs = {};
    for (const attr of contract[name]) attrs[attr] = attr in ATTR_DEFAULTS ? { default: ATTR_DEFAULTS[attr] } : {};
    if (what === "nodes" && TOP_LEVEL.has(name)) attrs.line = { default: null };
    // Table cells keep the extra attrs prosemirror-tables declares (colspan, rowspan, colwidth).
    specs[name] = { ...spec, attrs: { ...attrs, ...spec.attrs } };
  }
  return specs;
}

export const schema = new Schema({
  nodes: withContractAttrs(nodes, { ...CONTRACT.blockNodes, ...CONTRACT.inlineNodes }, "nodes"),
  marks: withContractAttrs(marks, CONTRACT.marks, "marks"),
});
```

- [x] **Step 6: Run the schema-sync tests**

Run: `.venv/Scripts/python -m pytest tests/test_docschema.py -v`
Expected: 59 passed.

- [x] **Step 7: Write the node views and display plugins**

Create `web-src/src/nodeviews.js`:

```js
// Node views and display plugins of the Rendered editor: code blocks (Pygments
// highlight from Python, language field), images (broken-image placeholder), raw HTML
// blocks (sandboxed iframe) and double-click on protected nodes.
import { Plugin } from "prosemirror-state";
import { Decoration, DecorationSet } from "prosemirror-view";
import { cleanLanguage, isSafeUrl } from "./schema.js";

// Must equal mdviewer/core/completion.py FENCE_LANGUAGES (tests/test_web_assets.py).
export const FENCE_LANGUAGES = [
  "python", "bash", "powershell", "javascript", "typescript", "json",
  "yaml", "xml", "html", "css", "c", "cpp", "csharp", "go", "rust",
  "java", "sql", "toml", "text"
];
const LANGUAGE_LIST_ID = "md-fence-languages";

function element(tag, className) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  return node;
}

// The page has one <datalist> of fence languages, shared by every code block's field.
function languageList() {
  let list = document.getElementById(LANGUAGE_LIST_ID);
  if (!list) {
    list = element("datalist");
    list.id = LANGUAGE_LIST_ID;
    for (const language of FENCE_LANGUAGES) list.append(new Option(language));
    document.body.append(list);
  }
  return list.id;
}

// The highlight attr comes from Python (render.highlight_code): <span class> markup
// only. Anything else is not shown, so a malformed attr cannot inject elements.
function highlightFragment(markup) {
  if (!markup) return null;
  const template = element("template");
  template.innerHTML = markup;
  for (const node of template.content.querySelectorAll("*")) {
    if (node.tagName !== "SPAN" || [...node.attributes].some((attr) => attr.name !== "class")) return null;
  }
  return template.content;
}

// Index of the top-level block that contains document position `pos`.
function topLevelIndex(state, pos) {
  return state.doc.resolve(pos).index(0);
}

class CodeBlockView {
  constructor(node, view, getPos) {
    this.node = node;
    this.view = view;
    this.getPos = getPos;
    this.dom = element("div", "md-code-block");
    this.tools = element("div", "md-code-tools");
    this.tools.contentEditable = "false";
    this.language = element("input", "md-code-language");
    this.language.type = "text";
    this.language.placeholder = "language";
    this.language.spellcheck = false;
    this.language.setAttribute("list", languageList());
    this.language.addEventListener("change", () => this.commitLanguage());
    this.language.addEventListener("keydown", (event) => this.languageKey(event));
    this.tools.append(this.language);
    const source = element("pre", "md-code-source");
    this.contentDOM = element("code");
    source.append(this.contentDOM);
    // Highlighted copy of the text, laid over the source while the caret is elsewhere.
    // Clicks go through it to the source text (pointer-events: none in editor.css).
    this.overlay = element("pre", "highlight md-code-highlight");
    this.overlay.setAttribute("aria-hidden", "true");
    this.overlayCode = element("code");
    this.overlay.append(this.overlayCode);
    this.dom.append(this.tools, source, this.overlay);
    this.shownHighlight = null;
    this.render();
  }

  render() {
    const { language, highlight } = this.node.attrs;
    if (document.activeElement !== this.language) this.language.value = language;
    if (highlight !== this.shownHighlight) {
      this.shownHighlight = highlight;
      const fragment = highlightFragment(highlight);
      this.overlayCode.replaceChildren(...(fragment ? [fragment] : []));
      this.dom.classList.toggle("md-has-highlight", fragment !== null);
    }
  }

  update(node) {
    if (node.type !== this.node.type) return false;
    this.node = node;
    this.render();
    return true;
  }

  commitLanguage() {
    const language = cleanLanguage(this.language.value);
    this.language.value = language;
    const pos = this.getPos();
    if (pos === undefined || language === this.node.attrs.language) return;
    // The highlight belongs to the old language: drop it (Python recomputes it on the next load).
    this.view.dispatch(this.view.state.tr.setNodeMarkup(pos, null, { ...this.node.attrs, language, highlight: "" }));
  }

  languageKey(event) {
    if (event.key === "Enter") {
      event.preventDefault();
      this.commitLanguage();
      this.view.focus();
    } else if (event.key === "Escape") {
      event.preventDefault();
      this.language.value = this.node.attrs.language;
      this.view.focus();
    }
  }

  // Keys and clicks in the language field belong to the field, not to ProseMirror.
  stopEvent(event) {
    return this.tools.contains(event.target);
  }

  ignoreMutation(mutation) {
    if (this.tools.contains(mutation.target) || this.overlay.contains(mutation.target)) return true;
    return mutation.type !== "selection" && !this.contentDOM.contains(mutation.target);
  }
}

class ImageView {
  constructor(node) {
    this.node = node;
    this.dom = element("span", "md-image");
    this.render();
  }

  render() {
    const { src, display_src: displaySrc, alt, title } = this.node.attrs;
    if (!isSafeUrl(displaySrc)) {
      this.showBroken();
      return;
    }
    const img = element("img");
    img.alt = alt;
    if (title !== null) img.title = title;
    img.addEventListener("error", () => this.showBroken(), { once: true });
    img.src = displaySrc;
    img.setAttribute("data-src", src);
    this.dom.replaceChildren(img);
  }

  // `src` is never rewritten: the placeholder only shows the alt text (or the path).
  showBroken() {
    const box = element("span", "md-image-broken");
    box.textContent = this.node.attrs.alt || this.node.attrs.src || "image";
    box.title = this.node.attrs.src;
    this.dom.replaceChildren(box);
  }

  update(node) {
    if (node.type !== this.node.type) return false;
    const changed = ["src", "display_src", "alt", "title"].some((name) => node.attrs[name] !== this.node.attrs[name]);
    this.node = node;
    if (changed) this.render();
    return true;
  }

  ignoreMutation() {
    return true;
  }
}

// Raw HTML is shown in an iframe built from srcdoc whose sandbox allows same-origin
// access but no scripts: nothing in it runs, and the editor can read the frame's
// content height to fit it. A transparent shield on top takes the clicks, so the
// block is selected and double-clicked like the other protected blocks and links
// inside it are not followed.
const frames = new Set();

// Theme colors for the frame document; refreshFrames() re-applies them after a theme change.
function frameDocument(source) {
  const css = getComputedStyle(document.documentElement);
  const color = (name) => css.getPropertyValue(name).trim();
  return '<!DOCTYPE html><html><head><meta charset="utf-8"><style>'
    + `html,body{margin:0;background:transparent;color:${color("--fg")}}`
    + 'body{font:16px/1.5 "Segoe UI","Noto Sans",Helvetica,Arial,sans-serif;padding:8px 12px}'
    + `a{color:${color("--link")}}img{max-width:100%}`
    + `</style></head><body>${source}</body></html>`;
}

class HtmlBlockView {
  constructor(node) {
    this.node = node;
    this.dom = element("div", "md-protected md-html-block");
    this.dom.title = "Raw HTML. Double-click to edit it in Source mode.";
    this.frame = element("iframe");
    this.frame.setAttribute("sandbox", "allow-same-origin");
    this.frame.setAttribute("tabindex", "-1");
    // "load" fires after the frame's images; the observer refits when the width changes.
    this.frame.addEventListener("load", () => this.fit());
    this.resizer = new ResizeObserver(() => this.fit());
    this.resizer.observe(this.dom);
    this.dom.append(this.frame, element("div", "md-shield"));
    frames.add(this);
    this.render();
  }

  render() {
    this.frame.srcdoc = frameDocument(this.node.attrs.source);
  }

  fit() {
    const root = this.frame.contentDocument?.documentElement;
    if (root) this.frame.style.height = `${Math.ceil(root.getBoundingClientRect().height)}px`;
  }

  update(node) {
    if (node.type !== this.node.type) return false;
    const changed = node.attrs.source !== this.node.attrs.source;
    this.node = node;
    if (changed) this.render();
    return true;
  }

  ignoreMutation() {
    return true;
  }

  destroy() {
    frames.delete(this);
    this.resizer.disconnect();
  }
}

// Task 9's setTheme calls this after swapping the theme stylesheet.
export function refreshFrames() {
  for (const view of frames) view.render();
}

export function createNodeViews() {
  return {
    code_block: (node, view, getPos) => new CodeBlockView(node, view, getPos),
    image: (node) => new ImageView(node),
    html_block: (node) => new HtmlBlockView(node),
  };
}

// Marks the code block that holds the selection: CSS then shows its plain text
// instead of the highlight overlay.
const activeCodePlugin = new Plugin({
  props: {
    decorations(state) {
      const { $from, $to } = state.selection;
      const found = [];
      for (const $pos of [$from, $to]) {
        for (let depth = $pos.depth; depth > 0; depth--) {
          if ($pos.node(depth).type.name === "code_block") {
            const start = $pos.before(depth);
            if (!found.some((d) => d.from === start)) {
              found.push(Decoration.node(start, start + $pos.node(depth).nodeSize, { class: "md-code-active" }));
            }
          }
        }
      }
      return found.length ? DecorationSet.create(state.doc, found) : null;
    },
  },
});

// Clears `highlight` on every code block inside the changed range: the markup no
// longer matches the text (or language) and Python recomputes it on the next load.
const staleHighlightPlugin = new Plugin({
  appendTransaction(transactions, oldState, newState) {
    if (!transactions.some((tr) => tr.docChanged)) return null;
    const start = oldState.doc.content.findDiffStart(newState.doc.content);
    if (start === null) return null;
    const end = Math.max(start, oldState.doc.content.findDiffEnd(newState.doc.content).b);
    const tr = newState.tr;
    newState.doc.nodesBetween(start, end, (node, pos) => {
      if (node.type.name === "code_block" && node.attrs.highlight) {
        tr.setNodeMarkup(pos, null, { ...node.attrs, highlight: "" });
      }
    });
    return tr.docChanged ? tr : null;
  },
});

// Double-click on a protected block or chip asks Python to show it in Source mode.
// callbacks.editProtected(index) receives the index of the enclosing top-level block.
function protectedPlugin(callbacks) {
  return new Plugin({
    props: {
      handleDOMEvents: {
        dblclick(view, event) {
          const target = event.target instanceof Element ? event.target.closest(".md-protected, .md-chip") : null;
          if (!target || !view.dom.contains(target)) return false;
          event.preventDefault();
          callbacks.editProtected(topLevelIndex(view.state, view.posAtDOM(target, 0)));
          return true;
        },
      },
    },
  });
}

export function displayPlugins(callbacks) {
  return [activeCodePlugin, staleHighlightPlugin, protectedPlugin(callbacks)];
}
```

- [x] **Step 8: Write the editor stylesheet**

Create `web-src/src/editor.css` (esbuild merges it with ProseMirror's CSS
into `mdviewer/web/editor.css`; the page CSP allows it as a `'self'`
stylesheet):

```css
/* Rendered editor styles on top of the page CSS (render.page_css): lists, code
   blocks, images and protected nodes. Colors come from the theme's CSS variables. */
.ProseMirror { outline: none; }

/* Lists: tight items keep their paragraphs flush; task boxes sit in the bullet gutter. */
.ProseMirror ul[data-tight="true"] > li > p,
.ProseMirror ol[data-tight="true"] > li > p { margin: 0; }
.ProseMirror li.task-list-item { position: relative; }
.ProseMirror li.task-list-item > .task-list-item-checkbox { position: absolute; left: -1.4em; top: .3em; margin: 0; }

/* Code blocks: the source <pre> is edited; the highlight <pre> is laid over it while
   the caret is elsewhere. Both use the same font, padding and wrapping. */
.md-code-block { position: relative; margin: 0 0 16px; }
.md-code-block > pre { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.md-code-highlight { display: none; position: absolute; inset: 0; pointer-events: none; }
.md-code-block.md-has-highlight:not(.md-code-active) > .md-code-highlight { display: block; }
.md-code-tools { position: absolute; top: 4px; right: 4px; z-index: 1; opacity: 0; }
.md-code-block:hover > .md-code-tools,
.md-code-block.md-code-active > .md-code-tools,
.md-code-tools:focus-within { opacity: 1; }
.md-code-language { width: 9em; font: 12px Consolas, Menlo, monospace; color: var(--fg);
  background: var(--bg); border: 1px solid var(--border); border-radius: 4px; padding: 1px 4px; }

/* Images: a missing file shows its alt text in a dashed box. */
.md-image-broken { display: inline-block; padding: 0 .4em; color: var(--muted);
  border: 1px dashed var(--border); border-radius: 4px; }
.md-image-broken::before { content: "\1F5BC\FE0E  "; }

/* Protected blocks and chips: not editable, selected and deleted as a unit. */
.md-protected { margin: 0 0 16px; border: 1px dashed var(--border); border-radius: 6px; cursor: default; }
.md-protected > pre { margin: 0; background: transparent; }
pre.md-protected { white-space: pre-wrap; }
.md-html-block { position: relative; }
.md-html-block > iframe { display: block; width: 100%; height: 24px; border: 0; }
.md-html-block > .md-shield { position: absolute; inset: 0; }
.md-chip { padding: 0 .3em; color: var(--muted); border: 1px dashed var(--border); border-radius: 4px;
  cursor: default; }
code.md-chip { background: transparent; }
```

- [x] **Step 9: Replace the editor entry point**

Replace the whole of `web-src/src/editor.js` with:

```js
// Rendered editor bundle: schema, node views and a minimal page API.
// Task 9 adds the QWebChannel bridge and replaces `events` with bridge signals.
/* global QWebChannel, qt */
import "prosemirror-view/style/prosemirror.css";
import "./editor.css";
import { NodeSelection, Selection, EditorState } from "prosemirror-state";
import { EditorView } from "prosemirror-view";
import { schema } from "./schema.js";
import { createNodeViews, displayPlugins } from "./nodeviews.js";

// Calls meant for Python, recorded until Task 9 sends them over the bridge.
const events = [];
const callbacks = { editProtected: (index) => events.push(["editProtected", index]) };
const plugins = displayPlugins(callbacks);

function createState(json) {
  if (!json) return EditorState.create({ schema, plugins });
  const doc = schema.nodeFromJSON(json);
  doc.check(); // throws on content the schema does not allow
  return EditorState.create({ schema, plugins, doc });
}

const view = new EditorView(document.getElementById("editor"), {
  state: createState(null),
  nodeViews: createNodeViews(),
});

window.mdEditor = {
  schema,
  view,
  events,
  setDocument: (json) => view.updateState(createState(json)),
  getDocument: () => view.state.doc.toJSON(),
  // Caret at the start of top-level block `index`; atoms (protected blocks, rules) are selected.
  focusBlock: (index) => {
    const { doc } = view.state;
    if (!Number.isInteger(index) || index < 0 || index >= doc.childCount) return;
    let pos = 0;
    for (let i = 0; i < index; i++) pos += doc.child(i).nodeSize;
    const block = doc.child(index);
    const selection = block.isLeaf ? NodeSelection.create(doc, pos) : Selection.near(doc.resolve(pos + 1));
    view.dispatch(view.state.tr.setSelection(selection).scrollIntoView());
    view.focus();
  },
};

// qwebchannel.js is loaded by its own <script> before this bundle.
new QWebChannel(qt.webChannelTransport, (channel) => {
  channel.objects.bridge.ready();
});
```

- [x] **Step 10: Rebuild the bundle**

Run: `.venv/Scripts/python scripts/build_web.py`
Expected: exit code 0; esbuild reports `editor.js` at about 210 KB and
`editor.css` at about 2.3 KB; `THIRD_PARTY.txt: 8 packages` (`orderedmap`,
`prosemirror-keymap`, `prosemirror-model`, `prosemirror-state`,
`prosemirror-tables`, `prosemirror-transform`, `prosemirror-view`,
`w3c-keyname`; `tableNodes` pulls in the keymap packages).

- [x] **Step 11: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_docschema.py tests/test_web_assets.py -v`
Expected: 69 passed (59 + 10).

- [x] **Step 12: Run the page check to verify it passes**

Run: `.venv/Scripts/python scripts/check_web.py`
Expected: `WEB OK`, exit code 0.

If only the frame-size check fails on another Qt version, print `size` and
the frame's `contentDocument.readyState` before changing the timing. Do
**not** weaken the sandbox: `allow-scripts` must never be added.

- [x] **Step 13: Record the raw-HTML frame decision in the spec**

In `docs/superpowers/specs/2026-10-20-wysiwyg-editing-design.md`, section 5,
replace

```
1. **No untrusted HTML in the editor DOM.** ProseMirror renders schema nodes
   only. `html_block` content is shown in `<iframe sandbox srcdoc="...">`
   without `allow-scripts` or `allow-same-origin`. `html_inline` is shown as
   an escaped source chip, never rendered.
```

with

```
1. **No untrusted HTML in the editor DOM.** ProseMirror renders schema nodes
   only. `html_block` content is shown in
   `<iframe sandbox="allow-same-origin" srcdoc="...">` without
   `allow-scripts`: nothing in it runs, while the editor can read its content
   height to fit the frame and local images load (decided 2026-10-20; with an
   empty sandbox the frame can be neither measured nor show `file:` images).
   `html_inline` is shown as an escaped source chip, never rendered.
```

- [x] **Step 14: Run the full verification**

Run:

```bash
.venv/Scripts/python -m pytest -v
.venv/Scripts/python scripts/smoke_ui.py
.venv/Scripts/python scripts/check_web.py
rg -n "import (PySide|Qt)|from PySide" mdviewer/core tests
sha256sum mdviewer/web/* > /tmp/web1.txt && .venv/Scripts/python scripts/build_web.py > /dev/null && sha256sum mdviewer/web/* | diff /tmp/web1.txt - && echo REPRODUCIBLE
```

Expected: all tests pass; `SMOKE OK` (nothing in `mdviewer/` loads the web
editor yet); `WEB OK`; the `rg` line prints nothing; `REPRODUCIBLE`.

- [x] **Step 15: Commit**

```bash
git add web-src/src/schema.js web-src/src/nodeviews.js web-src/src/editor.css web-src/src/editor.js mdviewer/web tests/test_docschema.py tests/test_web_assets.py scripts/check_web.py docs/superpowers/specs/2026-10-20-wysiwyg-editing-design.md
git status --short   # must not list web-src/node_modules
git commit -m "feat: add ProseMirror schema and node views for the rendered editor"
```

**Review Focus:**

- **Contract:**
  - `CONTRACT` is strict JSON (double quotes, no trailing commas, no
    comments inside the braces) and equals docschema.
  - The node and mark specs list the same names in the same order.
  - `line` (default `null`) is declared on exactly `TOP_LEVEL_NODES`. Cells
    add only `colspan`, `rowspan` and `colwidth`.
- **Schema rules:**
  - `code_block` has `marks: ""` and `code: true`.
  - `link` is `inclusive: false`.
  - `table_row` requires a cell.
  - The `block` group starts with `paragraph`.
- **No untrusted markup reaches the editor DOM:**
  - `html_block` source only goes into `srcdoc`.
  - `html_inline` and `front_matter` and `footnote_def` sources only go into
    text nodes.
  - `highlight` passes the `<span class>` filter, and no other `innerHTML`
    is used.
  - The sandbox is exactly `allow-same-origin`.
- **Unsafe URLs:** every `parseDOM` path that reads a URL calls `isSafeUrl`
  (link `href`; image `src` and `data-src`). `toDOM` never writes an unsafe
  `href`.
- **Code block node view:**
  - `stopEvent` claims only events inside the language field.
  - `ignoreMutation` ignores the field and the overlay and keeps selection
    mutations, so typing in the field never reaches ProseMirror.
- **Highlight clearing:** the stale-highlight plugin only touches code blocks
  inside the changed range, and returns `null` when there is nothing to
  clear (no endless `appendTransaction` loop).
- **Accepted behaviors:**
  - After undoing an edit inside a code block, the highlight stays cleared
    until the next load. This is conservative and correct.
  - `line` values are only meaningful until the first edit. Splitting a
    block copies them. Task 13 must use them only while the document is
    unchanged.
  - Pasted HTML that carries our `md-html-block`, `md-footnote-def` or
    `md-html-inline` markup becomes a protected node. It is shown
    sandboxed or escaped, and saved verbatim, as if typed in Source mode.
- **No regressions:** `tests/` stays Qt-free; `mdviewer/` still does not
  load `mdviewer/web`.

### Task 9: Bridge and document lifecycle

- **Files:** `web-src/src/bridge.js`, `web-src/src/editor.js`, rebuilt bundle.
- **Produces:** `window.mdEditor` API (`setDocument`, `getDocument`, `command`, `setTheme`, `focusBlock`; keeps Task 8's `schema` and `view` for `check_web.py`; `setTheme` calls `refreshFrames()`; Task 8's `events` list becomes bridge signals (`editProtected` first); `getDocument` deletes the `prosemirror-tables` cell attrs `colspan`/`rowspan`/`colwidth` so the JSON matches `docschema`); signals `ready`, `changed` (once per load), `selectionState` (~50 ms throttle), `caretBlock`, `hoverLink`, `openLink` (Ctrl+click only); history plugin reset on `setDocument`; scroll kept on `keepScroll`.
- **Test:** covered by Task 12's smoke checks (bundle-only task: verify by loading the page offscreen and calling each API once).
- **Commit:** `feat: add QWebChannel bridge and document lifecycle to the editor bundle`

### Task 10: Formatting commands, keymaps and input rules

- **Files:** `web-src/src/editor.js` (or `web-src/src/commands.js` if it exceeds ~300 lines), rebuilt bundle.
- **Produces:** `command()` names: `toggleMark`, `setBlock`, `toggleList`, `toggleQuote`, `insertCodeBlock`, `insertTable`, `insertImage`, `insertRule`, `setLink`, `removeLink`, `clearFormatting`, `setCodeLanguage`; keymaps from spec section 3; input rules from spec section 4; list sink/lift with Tab/Shift+Tab; Enter on empty item exits; task checkbox click toggles; code block Tab = 4 spaces, Ctrl+Enter exits.
- **Test:** smoke (Task 12 onwards) drives each command and checks the pulled Markdown.
- **Commit:** `feat: add formatting commands, keymaps and input rules to the editor`

### Task 11: Tables, paste and links

- **Files:** `web-src/src/editor.js`, `web-src/src/tables.js`, rebuilt bundle.
- **Produces:** `prosemirror-tables` integration (cell navigation, Tab in last cell appends a row), context-menu commands (`addRowBefore/After`, `addColumnBefore/After`, `deleteRow`, `deleteColumn`, `deleteTable`, `setColumnAlign`); paste coerced to schema with unsafe URLs stripped and merged table cells (`colspan`/`rowspan` > 1) split, since merged cells are a non-goal; Ctrl+Shift+V plain paste; protected nodes selectable and deletable as a unit.
- **Test:** smoke checks in Task 14 (table edits round-trip; pasted `javascript:` link dropped).
- **Commit:** `feat: add table editing, safe paste and plain-text paste`

## Phase 3 - Qt integration

### Task 12: RichView and Bridge

- **Files:** `mdviewer/richview.py`, `mdviewer/core/render.py` (`editor_page`), `scripts/smoke_ui.py`.
- **Produces:** `RichView` per Key Interfaces: writes `editor_page(theme)` and copies `editor.js`, `editor.css`, `qwebchannel.js` to its temp dir, registers the `Bridge` under the channel name `"bridge"`, navigation guard (from `preview._Page`), JS enabled with CSP, `ready` 5 s timeout -> `load_failed` signal, `request_document` with 3 s timeout -> `callback(None)`, `renderProcessTerminated` -> `crashed` signal, zoom passthrough.
- **Test:** smoke: standalone `RichView` loads, `set_document(from_markdown(...))` then `request_document` returns an equal document; a sandboxed `<script>` marker is never set.
- **Commit:** `feat: add RichView web editor host with QWebChannel bridge`

### Task 13: Rendered/Source modes and synchronous paths

- **Files:** `mdviewer/main_window.py`, delete `mdviewer/preview.py`, `scripts/smoke_ui.py` (update existing preview checks).
- **Covers:** menu items renamed (View > Rendered / Source), `RENDERED`/`SOURCE` mode constants, `with_buffer`, `_rendered_changed` flag (no re-serialization when unchanged), switching without prompt, caret mapping by top-level block, open in Rendered (Source above 5 MB), New in Rendered, Save/Save As through `with_buffer`, theme via `set_theme`, status bar left text `Rendered`, load-failure fallback to Source with warning.
- **Test:** smoke: open -> Rendered; switch both ways without edits keeps buffer byte-identical; command `toggleMark strong` + Save writes `**...**`; 5 MB file opens in Source; theme change does not reload the page.
- **Commit:** `feat: replace preview with editable Rendered mode and Source mode`

### Task 14: Asynchronous lifecycle and error handling

- **Files:** `mdviewer/main_window.py`, `scripts/smoke_ui.py`.
- **Covers:** `_pending_pull` guard; Close, Exit (`closeEvent` ignore + re-issue), Open, drop and Open Recent over a dirty Rendered document; external-change policy by dirty flag (spec section 2 table); pull timeout / renderer crash dialog (`Switch to Source` / `Retry`); serializer exception aborts the action with a message box.
- **Test:** smoke per flow using `FAKE` (`answer`, `during_ask`), plus faked timeout and serializer failure; table edits and unsafe paste checks from Task 11.
- **Commit:** `feat: handle save prompts, external changes and editor failures in Rendered mode`

### Task 15: Format toolbar

- **Files:** `mdviewer/toolbar.py`, `mdviewer/main_window.py`, `mdviewer/core/settings.py`, `tests/test_settings.py`, `scripts/smoke_ui.py`.
- **Produces:** `FormatToolbar(QToolBar)` with QPainter glyph icons, block combo, buttons and tooltips per spec section 3; `update_state(dict)` from `selectionState`; visible only in Rendered; View > Toolbar persisted as `show_toolbar` (default `True`).
- **Test:** pytest for `show_toolbar` cleaning; smoke: toolbar hidden in Source, checked state follows a bold selection, each button issues the expected `command`.
- **Commit:** `feat: add the Rendered-mode format toolbar`

### Task 16: Link and image dialogs, link navigation, protected blocks

- **Files:** `mdviewer/dialogs.py`, `mdviewer/main_window.py`, `scripts/smoke_ui.py`.
- **Covers:** `LinkDialog`, `ImageDialog` (relative path when possible, absolute for Untitled), seams `run_link_dialog` / `run_image_dialog`, `FAKE` entries for them; `openLink` -> scheme check -> `open_external` or in-page anchor; `hoverLink` -> status bar; `editProtected` -> Source mode at that block.
- **Test:** smoke: faked dialogs insert a link and an image and the saved Markdown matches; `javascript:` openLink ignored; double-click path switches to Source with caret on the block's line.
- **Commit:** `feat: add link and image dialogs and link navigation in Rendered mode`

### Task 17: Edit menu and Find in Rendered mode

- **Files:** `mdviewer/main_window.py`, `mdviewer/findbar.py`, `scripts/smoke_ui.py`.
- **Covers:** Undo/Redo/Cut/Copy/Paste/Select All routed to the web view in Rendered mode; Paste as plain text (Ctrl+Shift+V); FindBar find-only mode via `QWebEnginePage.findText` (match count, Previous/Next); Ctrl+H switches to Source and opens Replace.
- **Test:** smoke: action enablement per mode; Find in Rendered reports the match count; Ctrl+H lands in Source with the Replace bar open.
- **Commit:** `feat: route Edit menu and Find to the Rendered editor`

## Phase 4 - Packaging and documentation

### Task 18: Packaging

- **Files:** `scripts/build_exe.py`, `installer/MDViewer.wxs` (only if the harvest needs it).
- **Covers:** `--add-data mdviewer/web`; QtWebChannel collected; devtools `.pak` removal kept; built exe opens a file in Rendered mode and saves an edit.
- **Test:** `scripts/build_exe.py` then launch `dist/MDViewer/MDViewer.exe` on a sample file (manual, recorded in the commit body); `scripts/build_msi.py` succeeds.
- **Commit:** `chore: bundle the web editor in the exe and MSI`

### Task 19: Docs and final verification

- **Files:** `README.md`, `CLAUDE.md`, `docs/superpowers/specs/2026-10-16-md-viewer-design.md` (non-goals pointer to v2).
- **Covers:** modes and toolbar shortcuts, normalization note, manual checklist from spec section 8, layout and schema-sync rule in CLAUDE.md, rebuild-bundle command.
- **Test:** full `pytest -v`, `scripts/smoke_ui.py` prints `SMOKE OK`, Qt-import `rg` check prints nothing.
- **Commit:** `docs: document WYSIWYG editing, shortcuts and manual checklist`

## Dependency Order

Phase 1 (Tasks 2-7) and Phase 2 (Tasks 8-11) only meet at the schema; Task 8
needs Task 2. Task 12 needs Tasks 1, 5 and 9. Tasks 13-17 are sequential
(each edits `main_window.py`). Tasks 18-19 come last.
