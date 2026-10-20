# MD Viewer v2 - WYSIWYG Editing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Status: high-level outline.** Phases and tasks are fixed; each task's
> bite-sized steps (tests, code, commands) are written out on request, task
> by task, below its heading. Do not execute a task whose steps are not yet
> detailed.

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
- Raw HTML never runs scripts: `html_block` in `<iframe sandbox srcdoc>` without `allow-scripts`/`allow-same-origin`; `html_inline` shown escaped; page CSP `script-src 'self'`.
- `javascript:` and `vbscript:` URLs are stripped in `docmodel` and in JS paste/link paths.
- Schema names live in `core/docschema.py` and `web-src/src/schema.js`; a pytest check keeps them equal.
- `mdviewer/web/editor.js` is committed build output; `web-src/node_modules/` is git-ignored; Node is not needed for tests or packaging.
- Files larger than 5 MB open in Source mode with status note `Large file: opened in Source mode`.
- Timeouts: page `ready()` 5 s, document pull 3 s.
- UI checks go in `scripts/smoke_ui.py` above `# --- Later tasks insert their checks directly above this line. ---`, using `check()` and `FAKE`.
- Commits: small, one per task, conventional prefixes (`feat:`, `fix:`, `docs:`, `chore:`).

## File Map

| File | Status | Responsibility | Task |
|---|---|---|---|
| `web-src/package.json`, `package-lock.json`, `build.mjs` | new | pinned ProseMirror deps, esbuild config | 1 |
| `scripts/build_web.py` | new | `npm ci` + esbuild, copies `qwebchannel.js` in, writes `mdviewer/web/editor.js` | 1 |
| `mdviewer/web/editor.html` | new | page shell: CSP, theme `<style id="theme">`, bundle `<script src>` | 1 |
| `mdviewer/web/editor.js`, `THIRD_PARTY.txt` | new | committed bundle + MIT notices | 1, rebuilt in 8-11 |
| `mdviewer/core/docschema.py` | new | node/mark names and attrs, `validate(doc)` | 2 |
| `mdviewer/core/frontmatter.py` | new | `split(text)` / `join(front, body)` | 3 |
| `mdviewer/core/urls.py` | new | URL resolution + scheme stripping (extracted from `render.py`) | 4 |
| `mdviewer/core/docmodel.py` | new | Markdown -> document JSON | 4, 5 |
| `mdviewer/core/render.py` | changed | adds `highlight_code(code, lang)`, `editor_page(theme)`; uses `core/urls.py` | 4, 5, 12 |
| `mdviewer/core/serialize.py` | new | document JSON -> normalized Markdown | 6, 7 |
| `web-src/src/schema.js` | new | ProseMirror schema mirroring `docschema` | 8 |
| `web-src/src/nodeviews.js` | new | code block, image, protected block, footnote chip | 8 |
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
BLOCK_NODES: dict[str, tuple[str, ...]]     # node name -> attr names
INLINE_NODES: dict[str, tuple[str, ...]]
PROTECTED_NODES: frozenset[str]
MARKS: dict[str, tuple[str, ...]]
def validate(doc: dict) -> list[str]        # [] when valid

# core/frontmatter.py
def split(text: str) -> tuple[str | None, str]
def join(front: str | None, body: str) -> str

# core/urls.py
def resolve(url: str, base_dir: Path | None) -> str   # moved from render._Renderer._resolve
def is_safe(url: str) -> bool                          # False for javascript:/vbscript:

# core/render.py (additions)
def highlight_code(code: str, language: str) -> str    # "" when the language is unknown
def editor_page(theme: str) -> str                     # editor.html with theme CSS filled in

# core/docmodel.py
def from_markdown(body: str, front: str | None = None, base_dir: Path | None = None) -> dict

# core/serialize.py
def to_markdown(doc: dict) -> str                      # body only; front matter via frontmatter.join

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

Retire risk R1 before anything depends on it.

- **Files:** `web-src/package.json`, `web-src/package-lock.json`, `web-src/build.mjs`, `web-src/src/editor.js` (minimal: one-paragraph schema, `EditorView`, `ready` signal), `scripts/build_web.py`, `mdviewer/web/editor.html`, `mdviewer/web/editor.js`, `mdviewer/web/THIRD_PARTY.txt`, `.gitignore`.
- **Produces:** the build pipeline; `qwebchannel.js` vendored into the bundle (read from Qt's `qrc:///qtwebchannel/qwebchannel.js` by `build_web.py`) so CSP `script-src 'self'` holds; a documented verdict on whether `'self'` matches the `file:` bundle. If it does not, this task also adds the `mdviewer:` scheme handler and the rest of the plan uses it.
- **Test:** a throwaway offscreen script loads the shell from a temp dir, receives `ready` over QWebChannel, and confirms an inline `<script>` is blocked. Its outcome is recorded in spec section 10 (R1).
- **Commit:** `chore: add web editor toolchain and CSP-checked page shell`

## Phase 1 - Python document model (pure, TDD)

### Task 2: Document schema contract

- **Files:** `mdviewer/core/docschema.py`, `tests/test_docschema.py`.
- **Produces:** `BLOCK_NODES`, `INLINE_NODES`, `PROTECTED_NODES`, `MARKS`, `validate(doc)` exactly per spec 6.3 (incl. transient `line` attr on top-level nodes).
- **Test:** valid docs pass; unknown node/mark, missing attr, text node without `text`, mark on a non-text node, block in inline context are each reported.
- **Commit:** `feat: add WYSIWYG document schema contract (core/docschema)`

### Task 3: Front matter

- **Files:** `mdviewer/core/frontmatter.py`, `tests/test_frontmatter.py`.
- **Produces:** `split`, `join` per spec 6.6.
- **Test:** byte-exact round trip (`---`/`...` closers, CRLF-free input, trailing content); near-misses (not at byte 0, no closer, empty block, `---` hr followed by text) return `(None, text)`.
- **Commit:** `feat: add YAML front-matter split/join (core/frontmatter)`

### Task 4: Markdown -> document, text and structure

- **Files:** `mdviewer/core/urls.py`, `mdviewer/core/render.py` (use `urls.resolve`), `mdviewer/core/docmodel.py`, `tests/test_urls.py`, `tests/test_docmodel.py`.
- **Covers:** paragraphs, headings (ATX and setext), blockquote, horizontal rule, hard/soft breaks, marks `strong`/`em`/`strike`/`code`/`link`, autolinks, reference links resolved to inline, `javascript:`/`vbscript:` stripped, front matter node, top-level `line` attrs.
- **Test:** snippet -> expected JSON per construct; every output passes `docschema.validate`; existing `tests/test_render.py` still green after the `urls` extraction.
- **Commit:** `feat: convert Markdown text blocks and marks to document JSON`

### Task 5: Markdown -> document, rich blocks and protected nodes

- **Files:** `mdviewer/core/docmodel.py`, `mdviewer/core/render.py` (`highlight_code`), `tests/test_docmodel.py`, `tests/test_render.py`.
- **Covers:** bullet/ordered lists (`start`, `tight`), task items (`checked`), nested lists; fenced and indented code (`language`, `highlight`); tables (`align`); images (`src`, `display_src`, `alt`, `title`); `html_block`, `html_inline`, `footnote_ref`, `footnote_def{label, source}`; unknown AST nodes -> protected `html_block` holding their source.
- **Test:** snippet -> JSON per construct; drive-letter/relative/absolute image paths; unknown-language code has `highlight == ""`; all outputs validate.
- **Commit:** `feat: convert lists, code, tables, images and protected blocks to document JSON`

### Task 6: Document -> Markdown, text and structure

- **Files:** `mdviewer/core/serialize.py`, `tests/test_serialize.py`.
- **Covers:** spec 6.5 rules for headings, paragraphs, blockquotes, rule, hard break (`\`), marks (incl. backtick-run code spans), links/autolinks, context-sensitive escaping, block spacing, single trailing `\n`; front matter emitted verbatim.
- **Test:** JSON -> exact Markdown per rule; escaping table (`*`, `_`, `#` at line start, `1.` at line start, `[`, `|` only in tables, `\`).
- **Commit:** `feat: serialize text blocks and marks to normalized Markdown`

### Task 7: Document -> Markdown, rich blocks and round-trip properties

- **Files:** `mdviewer/core/serialize.py`, `tests/test_serialize.py`, `tests/test_roundtrip.py`, `tests/corpus/*.md`.
- **Covers:** lists (indent to content column, tight/loose, task markers, ordered from `start`), fenced code (fence lengthened), tables (alignment row, `\|`), images, protected nodes verbatim, footnote definitions at the end in original order.
- **Test:** exact outputs per rule; properties over `tests/corpus/*.md` + `README.md` + both specs: (a) `to_markdown(from_markdown(md))` is a fixed point after one pass; (b) `render_body(md2) == render_body(md)` (whitespace-normalized) for supported constructs.
- **Commit:** `feat: serialize lists, code, tables and protected blocks; add round-trip tests`

## Phase 2 - JS editor (bundle rebuilt and committed in each task)

### Task 8: Schema and node views

- **Files:** `web-src/src/schema.js`, `web-src/src/nodeviews.js`, `tests/test_docschema.py` (schema-sync check), rebuilt `mdviewer/web/editor.js`.
- **Produces:** ProseMirror schema matching `docschema` (incl. `parseDOM` rules for paste and `href` sanitizing); node views: code block (highlight when caret is outside, plain while inside, language selector, clears `highlight` on edit), image (`display_src`, broken placeholder with alt), protected block (sandboxed iframe for `html_block`, bordered box, double-click -> `editProtected`), footnote and inline-HTML chips.
- **Test:** pytest parses node/mark names from `schema.js` and compares to `docschema`; offscreen smoke loads a document containing every node type and gets it back unchanged via `getDocument`.
- **Commit:** `feat: add ProseMirror schema and node views for the rendered editor`

### Task 9: Bridge and document lifecycle

- **Files:** `web-src/src/bridge.js`, `web-src/src/editor.js`, rebuilt bundle.
- **Produces:** `window.mdEditor` API (`setDocument`, `getDocument`, `command`, `setTheme`, `focusBlock`); signals `ready`, `changed` (once per load), `selectionState` (~50 ms throttle), `caretBlock`, `hoverLink`, `openLink` (Ctrl+click only); history plugin reset on `setDocument`; scroll kept on `keepScroll`.
- **Test:** covered by Task 12's smoke checks (bundle-only task: verify by loading the page offscreen and calling each API once).
- **Commit:** `feat: add QWebChannel bridge and document lifecycle to the editor bundle`

### Task 10: Formatting commands, keymaps and input rules

- **Files:** `web-src/src/editor.js` (or `web-src/src/commands.js` if it exceeds ~300 lines), rebuilt bundle.
- **Produces:** `command()` names: `toggleMark`, `setBlock`, `toggleList`, `toggleQuote`, `insertCodeBlock`, `insertTable`, `insertImage`, `insertRule`, `setLink`, `removeLink`, `clearFormatting`, `setCodeLanguage`; keymaps from spec section 3; input rules from spec section 4; list sink/lift with Tab/Shift+Tab; Enter on empty item exits; task checkbox click toggles; code block Tab = 4 spaces, Ctrl+Enter exits.
- **Test:** smoke (Task 12 onwards) drives each command and checks the pulled Markdown.
- **Commit:** `feat: add formatting commands, keymaps and input rules to the editor`

### Task 11: Tables, paste and links

- **Files:** `web-src/src/editor.js`, `web-src/src/tables.js`, rebuilt bundle.
- **Produces:** `prosemirror-tables` integration (cell navigation, Tab in last cell appends a row), context-menu commands (`addRowBefore/After`, `addColumnBefore/After`, `deleteRow`, `deleteColumn`, `deleteTable`, `setColumnAlign`); paste coerced to schema with unsafe URLs stripped; Ctrl+Shift+V plain paste; protected nodes selectable and deletable as a unit.
- **Test:** smoke checks in Task 14 (table edits round-trip; pasted `javascript:` link dropped).
- **Commit:** `feat: add table editing, safe paste and plain-text paste`

## Phase 3 - Qt integration

### Task 12: RichView and Bridge

- **Files:** `mdviewer/richview.py`, `mdviewer/core/render.py` (`editor_page`), `scripts/smoke_ui.py`.
- **Produces:** `RichView` per Key Interfaces: copies `editor.html`/`editor.js` to its temp dir, navigation guard (from `preview._Page`), JS enabled with CSP, `ready` 5 s timeout -> `load_failed` signal, `request_document` with 3 s timeout -> `callback(None)`, `renderProcessTerminated` -> `crashed` signal, zoom passthrough.
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
