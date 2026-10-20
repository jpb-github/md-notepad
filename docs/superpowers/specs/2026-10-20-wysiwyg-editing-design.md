# MD Viewer v2 - WYSIWYG Editing - Design Specification

- **Date:** 2026-10-20
- **Status:** Approved via brainstorming; ready for implementation planning
- **Builds on:** `2026-10-16-md-viewer-design.md` (v1). Everything in v1 stays
  valid unless this document changes it.
- **Target platform:** Windows 10/11, Python 3.12+, PySide6 (Qt >= 6.5)

## 1. Overview

v2 makes the rendered view editable: the user edits the GitHub-styled page
directly (WYSIWYG), with a single-row format toolbar. The plain-text editor
remains as **Source** mode. The UI stays Notepad-lean: one window, one
document, one toolbar row that only appears in the rendered mode.

Key decisions:

- **Normalized output is accepted.** Saving from the rendered editor
  re-serializes the whole document into a canonical Markdown style. Byte-exact
  preservation of untouched source is a non-goal. A file that is only viewed
  (never edited in Rendered mode) is never rewritten.
- **The preview becomes editable.** Two modes: **Rendered** and **Source**.
  There is no separate read-only preview.
- **ProseMirror** is the editing core in the web view. **Python owns
  Markdown in both directions**: Markdown -> document JSON and document
  JSON -> Markdown are pure functions in `mdviewer/core/`, unit-tested with
  pytest. JS contains no Markdown parser.

### Non-goals (v2)

The v1 list stays (tabs, printing, cross-file search, default handler
registration, custom CSS/themes, localization, signing/MSIX/auto-update),
**minus WYSIWYG**, plus: byte-exact source preservation, collaborative
editing, merged table cells, math and diagrams (Mermaid), spell checking,
Find/Replace inside Rendered mode, comments, track changes.

## 2. Modes

| Mode | View menu | Shortcut | Page |
|---|---|---|---|
| **Rendered** (default on open) | View > Rendered | Ctrl+P | Editable GitHub-styled view + format toolbar |
| **Source** | View > Source | Ctrl+E | v1 plain-text editor, unchanged (completion, underlines, Find/Replace) |

The two items are a checkable radio pair, replacing v1's Preview Mode / Edit
Mode.

### Switching

- **Rendered -> Source:** if the rendered document changed since it was last
  loaded, it is serialized into the buffer (normalized Markdown). If not, the
  buffer is left byte-identical.
- **Source -> Rendered:** the buffer is parsed into the rendered document.
- No save prompt on switching (both modes edit). The dirty flag carries
  across. Each switch starts a fresh undo history in the target mode.
- The caret maps across a switch at **top-level block** granularity: the
  parser records each top-level block's source line span; Source -> Rendered
  places the caret at the start of the block containing the source line,
  Rendered -> Source places it on that block's first line. No column mapping.

### Opening and New

- Opening a file shows Rendered mode, except files larger than **5 MB**, which
  open in Source mode with the status note `Large file: opened in Source mode`.
  The user may still switch to Rendered manually.
- File > New: empty `Untitled` document in **Rendered** mode.

### Saving

- In Rendered mode, Save first pulls and serializes the document (section
  6.4), then follows the v1 path: remembered encoding, preserved newline
  style, Save As for Untitled.

### External changes on disk

| State | Behavior |
|---|---|
| Rendered, not dirty | Silent reload, scroll position kept |
| Rendered, dirty | v1 dialog `File changed on disk` (Reload / Keep my version) |
| Source (dirty or not) | Unchanged from v1: dialog always shown |

### Edit menu in Rendered mode

- Undo (Ctrl+Z), Redo (Ctrl+Y), Cut, Copy, Paste, Select All act on the
  rendered editor.
- Paste keeps formatting, coerced to the schema; **Ctrl+Shift+V** pastes as
  plain text.
- Find (Ctrl+F) uses the web view's find-in-page (highlight, match count,
  Previous/Next in the existing Find bar; no replace).
- Replace (Ctrl+H) switches to Source mode and opens the Replace bar.

### Links in Rendered mode

- Plain click places the caret. **Ctrl+click** opens the link (external via
  `open_external`; `#anchor` scrolls in-page).
- Hovering a link shows its URL in the status bar.

### Status bar

- Left (Rendered): `Rendered`, plus zoom % when not 100%.
- Left (Source): `Ln X, Col Y` (v1).
- Right (both): zoom %, encoding, file size (v1).

## 3. Toolbar

A single native `QToolBar` row under the menu bar, visible only in Rendered
mode. View > Toolbar (checkable, default on) hides it; the choice persists as
`show_toolbar` in `settings.json`. Icons are flat glyphs drawn with QPainter
(no icon files). Each tooltip includes the shortcut.

```
[Normal v] | B  I  S  <>  Link | Bullets  Numbers  Tasks | Quote  {}  Table  Image  Rule | Clear
```

| Control | Action | Shortcut |
|---|---|---|
| Block combo: Normal, Heading 1-6, Code block | Set block type | Ctrl+Alt+0 (Normal), Ctrl+Alt+1..6 |
| Bold / Italic / Strikethrough / Inline code | Toggle mark | Ctrl+B, Ctrl+I, Ctrl+Shift+X, Ctrl+` |
| Link | Insert/edit link (dialog) | Ctrl+K |
| Bulleted / Numbered / Task list | Toggle list type | Ctrl+Shift+8 / Ctrl+Shift+7 / Ctrl+Shift+9 |
| Quote | Wrap in / lift out of blockquote | Ctrl+Shift+. |
| Code block | Insert code block (language picker) | - |
| Table | Insert 3x3 table with header row | - |
| Image | Insert image (dialog) | - |
| Horizontal rule | Insert rule | - |
| Clear formatting | Remove inline marks, set block to Normal | Ctrl+Space |

Heading shortcuts use Ctrl+Alt because Ctrl+0 is Zoom Reset and Ctrl+1..9
stay free for future use.

- Buttons reflect the selection: active marks are checked, the combo shows the
  current block type, inapplicable actions are disabled (e.g. Link and marks
  inside a code block).
- **Link dialog:** modal, fields Text and URL, plus `Remove link` when editing
  an existing link. Seam: `run_link_dialog(parent, text, url) -> (text, url) |
  "remove" | None`.
- **Image dialog:** modal, fields Path/URL (with Browse...) and Alt text. The
  path is stored relative to the document's folder when possible, absolute for
  Untitled documents. Seam: `run_image_dialog(parent, base_dir) -> (src, alt) |
  None`.

## 4. Editing behavior

### Input rules (at block start unless noted)

- `# ` .. `###### ` -> heading 1..6
- `- `, `* ` -> bulleted list; `1. ` (any number) -> numbered list starting
  there
- `[ ] ` / `[x] ` at the start of a list item -> task item
- `> ` -> blockquote
- ```` ``` ```` + optional language + Enter -> code block
- `---` + Enter -> horizontal rule
- Inline: `**text**` -> bold, `*text*` -> italic, `` `text` `` -> inline code,
  `~~text~~` -> strikethrough

### Lists

- Tab / Shift+Tab: sink / lift list item.
- Enter on an empty item exits the list.
- Clicking a task checkbox toggles it and marks the document dirty.

### Code blocks

- Plain-text editing in the code font; Tab inserts 4 spaces.
- Language selector at the block's top-right corner, offering the v1 fence
  language list (`core/completion.py`) plus free text.
- While the caret is outside the block, it shows Pygments highlighting
  (pre-computed in Python, section 6.3); while inside, plain text.
- Arrow keys and Ctrl+Enter leave the block.

### Tables

- Tab / Shift+Tab move between cells; Tab in the last cell appends a row.
- Cell context menu: Insert row above / below, Insert column left / right,
  Delete row, Delete column, Delete table, Align column left / center / right.
- No merged cells.

### Images

- Displayed inline at their resolved location (section 6.3). A missing file
  shows a broken-image placeholder with the alt text; `src` is never
  rewritten.

### Protected blocks

`html_block`, `footnote_def` and `front_matter` render as non-editable blocks
with a subtle border. They can be selected and deleted as a unit;
double-clicking one switches to Source mode with the caret on that construct.
`footnote_ref` and `html_inline` are non-editable inline chips.

## 5. Security

v1 disabled JavaScript for the whole page. v2 must enable it for the editor,
so script safety becomes layered:

1. **No untrusted HTML in the editor DOM.** ProseMirror renders schema nodes
   only. `html_block` content is shown in
   `<iframe sandbox="allow-same-origin" srcdoc="...">` without
   `allow-scripts`: nothing in it runs, while the editor can read its content
   height to fit the frame and local images load (decided 2026-10-20; with an
   empty sandbox the frame can be neither measured nor show `file:` images).
   `html_inline` is shown as an escaped source chip, never rendered.
2. **Content Security Policy** in the page shell:
   `default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline';
   img-src file: data: https: http:; frame-src 'self' about:; child-src 'self'`.
   No inline scripts, no `eval`. `'self'` matches the bundle and
   `qwebchannel.js` loaded from the page's own `file:` folder (R1, retired;
   re-checked by `scripts/check_web.py`).
3. **Paste** goes through ProseMirror's schema `DOMParser`; anything outside
   the schema (scripts, styles, event attributes) is dropped.
4. **Link and image URLs:** `javascript:` and `vbscript:` are stripped in
   `docmodel` and in the JS paste/link paths. The allowlist matches
   `render.py` (`file:`, `data:image/`, plus normal web schemes).
5. **Navigation:** `_Page.acceptNavigationRequest` keeps blocking every
   navigation except our own loads; Ctrl+click is routed to Python's
   `open_external`.
6. **Bridge surface:** the `QWebChannel` exposes one `Bridge` object with the
   slots/signals in section 6.2 only - no filesystem access, no path
   arguments.

## 6. Architecture

### 6.1 Files

```
mdviewer/
  richview.py        NEW  QWebEngineView + QWebChannel Bridge (replaces preview.py)
  toolbar.py         NEW  format toolbar, QPainter glyph icons, selection-state sync
  dialogs.py         NEW  link and image dialogs
  main_window.py     CHG  Rendered/Source modes, async pulls, new seams
  core/
    docmodel.py      NEW  Markdown -> document JSON (from mistune AST)
    serialize.py     NEW  document JSON -> normalized Markdown
    docschema.py     NEW  node/mark names and attrs, validate(doc)
    frontmatter.py   NEW  split/join a leading YAML front-matter block
    render.py        CHG  keeps CSS + Pygments; adds highlight_code(); editor page shell
  web/               NEW  shipped runtime files (committed build output)
    editor.js            esbuild bundle: ProseMirror + our code (~200 KB)
    editor.css           ProseMirror's required stylesheet (esbuild output)
    qwebchannel.js       Qt WebChannel client, copied unmodified from PySide6
    editor.html          page shell template (CSP, CSS slot, script references)
    THIRD_PARTY.txt      license notices of the bundled npm packages
web-src/             NEW  JS sources, only needed to rebuild web/editor.js
  package.json, package-lock.json   pinned prosemirror-* packages and esbuild
  src/schema.js      nodes/marks mirroring core/docschema.py
  src/editor.js      EditorView setup, keymaps, input rules, commands
  src/nodeviews.js   code block, image, protected block, footnote chip
  src/bridge.js      QWebChannel glue
scripts/build_web.py NEW  npm ci + esbuild -> mdviewer/web/*, copies qwebchannel.js
scripts/check_web.py NEW  offscreen load of the shell: ready(), CSP blocks inline scripts
```

ProseMirror packages: `prosemirror-model`, `-state`, `-view`, `-transform`,
`-commands`, `-keymap`, `-history`, `-schema-list`, `-tables`,
`-inputrules`, `-dropcursor`, `-gapcursor`. Node is required only to rebuild
the bundle; normal development, tests and packaging use the committed
`mdviewer/web/editor.js`.

### 6.2 Bridge contract

Python -> JS (slots called on the JS `editor` object via `runJavaScript` /
channel signals):

| Call | Purpose |
|---|---|
| `setDocument(json, keepScroll)` | Replace the document; new EditorState (empty undo history) |
| `getDocument() -> json` | Return the current document (async callback in Python) |
| `command(name, args)` | Run a toolbar/menu command, e.g. `("toggleMark", "strong")`, `("setBlock", {"type": "heading", "level": 2})`, `("insertTable", {"rows": 3, "cols": 3})` |
| `setTheme(theme)` | Swap CSS variables and code-highlight variant, no reload |
| `focusBlock(index)` | Place caret at the start of top-level block `index` |

JS -> Python (`Bridge` signals/slots):

| Call | Purpose |
|---|---|
| `ready()` | Page and bundle loaded, channel connected |
| `changed()` | First change since the last `setDocument` (sets dirty) |
| `selectionState(dict)` | `{marks, block, can}` throttled to ~50 ms; drives the toolbar |
| `requestLinkDialog(text, href)` / `requestImageDialog()` | Python runs the seam, then calls `command` with the result |
| `openLink(href)` | Ctrl+click; Python validates the scheme and calls `open_external` |
| `hoverLink(href)` | Status-bar URL (empty string clears) |
| `editProtected(index)` | Double-click on a protected block: switch to Source at that block |
| `caretBlock(index)` | Current top-level block index, for mode-switch caret mapping |

### 6.3 Document model

ProseMirror JSON: `{"type", "attrs", "content", "marks", "text"}`.

| Kind | Names and attrs |
|---|---|
| Block nodes | `doc`, `paragraph`, `heading{level}`, `blockquote`, `bullet_list{tight}`, `ordered_list{start, tight}`, `list_item{checked: null\|true\|false}`, `code_block{language, highlight}`, `horizontal_rule`, `table`, `table_row`, `table_header{align}`, `table_cell{align}` |
| Inline nodes | `text`, `hard_break`, `image{src, display_src, alt, title}` |
| Protected | `front_matter{source}`, `html_block{source}`, `footnote_def{label, source}`, `footnote_ref{label}`, `html_inline{source}` |
| Marks | `strong`, `em`, `strike`, `code`, `link{href, title}` |

- `core/docschema.py` is the single source of these names and attrs and
  provides `validate(doc) -> list[str]` (problems; empty when valid).
- `highlight` holds Pygments HTML from `render.highlight_code(code,
  language)`; empty when the language is unknown. The markup is class-based
  and theme-independent: colors come from the page CSS, which carries the
  Pygments style of the current theme (`light`, `dark`, `gray`). It is
  display-only and ignored by the serializer. When a code block's text or
  language changes, JS clears the attr; the block then displays without
  highlighting until the next `setDocument` (mode switch, reload or save),
  which recomputes it in Python.
- `display_src` is the resolved `file:` URI (v1 `_Renderer._resolve` logic);
  `src` is kept as written and is what the serializer emits.
- Every top-level node carries a transient `line` attr (source start line)
  for caret mapping; ignored by the serializer.

### 6.4 Data flow

**Load** (open, Source -> Rendered, external reload, theme-independent):

1. `frontmatter.split(buffer) -> (front | None, body)`.
2. `docmodel.from_markdown(body, front, base_dir) -> doc` using mistune's AST
   renderer with the v1 plugin list (`table`, `strikethrough`, `footnotes`,
   `task_lists`, `url`).
3. `richview.set_document(doc, keep_scroll)`.

**Edit:** JS handles typing and commands locally; it emits `changed()` once
per load and `selectionState` as the selection moves.

**Pull** (Save, Save As, Rendered -> Source, Close, Exit, Open/drop/recent
over a dirty document, external-change Reload decision):

1. `richview.request_document(callback)` -> JS `getDocument()`.
2. `serialize.to_markdown(doc)` -> `frontmatter.join(front, body)`.
3. The buffer is updated; the caller's continuation runs.

These flows are asynchronous. `MainWindow.with_buffer(fn)` wraps "pull if
Rendered and changed, then call `fn(text)`"; in Source mode or when
unchanged it calls `fn` synchronously. A single `_pending_pull` guard drops
re-triggers while a pull is in flight. `MainWindow.buffer` remains the
synchronous truth in Source mode and returns the last pulled text in Rendered
mode. `closeEvent` ignores the first close event when a pull is needed and
re-issues `close()` from the continuation.

### 6.5 Serializer normalization rules

- ATX headings (`## Title`); setext input becomes ATX.
- Bullets `-`; ordered lists `1.`, `2.`, ... continuing from `start`;
  nested lists indented to the content column of the parent item.
- Tight lists without blank lines between items; loose lists with one.
- Task items `- [ ] ` / `- [x] `.
- `**strong**`, `*em*`, `~~strike~~`, `` `code` `` (backtick run lengthened
  and padded when the code contains backticks).
- Fenced code blocks with ```` ``` ```` (lengthened when the code contains a
  backtick run of 3+); indented code input becomes fenced without language.
- Pipe tables: header row, separator with `:---`, `:---:`, `---:` or `---`,
  cell pipes escaped as `\|`.
- Inline links `[text](url "title")`; reference-style input becomes inline.
  Autolinked bare URLs stay bare when text equals href.
- Images `![alt](src "title")`.
- Hard break: backslash at end of line.
- Escaping of characters that would otherwise start Markdown syntax
  (`\*`, `\_`, `\#` at line start, `\[`, leading `1\.`, etc.), minimal and
  context-sensitive.
- Protected nodes emit their `source` verbatim; `footnote_ref` emits
  `[^label]`; footnote definitions are written at the document end in
  original order.
- One blank line between blocks; output ends with exactly one `\n`. Output
  uses `\n`; `MainWindow` applies the file's newline style on save (v1).

### 6.6 Front matter

`frontmatter.split` recognizes a block that starts at byte 0 with a line
`---`, ends at the next line that is exactly `---` or `...`, and has at least
one non-blank line in between; otherwise there is no front matter and the
text is parsed normally (a leading `---` is then a horizontal rule). It is
kept byte-exact as
`front_matter{source}` and rejoined unchanged.

### 6.7 Theming and zoom

A theme change (`light`, `dark` or `gray`, v1.1) calls `setTheme(theme)`:
the page's theme stylesheet (CSS variables plus the theme's Pygments style
from `render.page_css`) is swapped in place. No reload, and code-block
markup is unchanged. Zoom
uses `setZoomFactor` as in v1 and persists as before.

## 7. Error handling

| Case | Behavior |
|---|---|
| A construct `docmodel` cannot map | Becomes a protected `html_block` holding its source text; nothing lost |
| `from_markdown` raises | File opens in Source mode; status warning `Opened in Source mode: the rendered editor could not load this file.` |
| Page or bundle fails to load (`ready()` never arrives within 5 s) | Rendered mode disabled for the session (menu item greyed), status warning; Source works |
| Serializer raises during a pull | Pending action aborted; message box; document stays dirty |
| Pull callback missing after 3 s (renderer crash) | Message box: `The rendered editor stopped responding.` with **Switch to Source** (uses the last pulled buffer; edits since then are lost - stated in the box) or **Retry** |
| Renderer process crash (`renderProcessTerminated`) | Same as above; the view is reloaded from the buffer afterwards |

v1 error handling (open/read failures, watch-time read failures, deleted
file) is unchanged.

## 8. Testing

### Unit (pytest, no Qt imports)

- `test_docmodel.py`: snippet corpus, one per node/mark, plus front matter,
  footnotes, raw HTML (block and inline), nested and loose lists, task lists,
  table alignment, reference links, setext headings, indented code,
  `javascript:` links (stripped), relative/absolute/drive-letter image paths.
- `test_serialize.py`: doc JSON -> exact Markdown for every rule in 6.5,
  including escaping, backticks inside code spans and fences, pipes in
  cells, nested list indentation, hard breaks.
- Round-trip properties over the corpus plus the repo's `README.md` and
  specs:
  - `to_markdown(from_markdown(md))` is a fixed point after one pass.
  - `render_body(md2)` equals `render_body(md)` (whitespace-normalized) for
    supported constructs.
- `test_docschema.py`: `validate()` accepts every `from_markdown` output and
  rejects malformed docs; node/mark names parsed from
  `web-src/src/schema.js` equal `docschema`'s.
- `test_frontmatter.py`: byte-exact split/join; near-misses rejected.

### UI smoke (`scripts/smoke_ui.py`, offscreen)

- Open a file -> Rendered page loads, `ready()` received.
- Toolbar commands via the bridge (bold, H2, bullet list, table, link via the
  faked `run_link_dialog`, image via `run_image_dialog`), then Save -> the
  file contains the expected Markdown.
- Mode switch without edits keeps the buffer byte-identical.
- External change: silent reload when clean; dialog when dirty.
- Raw HTML `<script>` in a sandboxed block does not run (it would set a
  marker the smoke checks); a `javascript:` link is stripped.
- Close and Exit with a dirty Rendered document go through the async pull and
  the save prompt.

JS has no separate test suite: its logic is schema, keymaps and node views,
covered by the smoke test; all conversion logic is in Python.

### Manual checklist (README)

Input rules; table context menu; paste from a browser and from Word;
Ctrl+Shift+V; Ctrl+click links and anchors; code language picker and
highlight on leaving the block; task checkbox click; live theme flip while
editing; zoom; a >5 MB file opening in Source mode; toolbar hide/show
persistence.

## 9. Packaging and repository rules

- `scripts/build_exe.py` bundles `mdviewer/web/*` and Qt's WebChannel
  module; the MSI picks up the new files without WXS changes beyond what the
  harvest needs.
- `mdviewer/web/editor.js` is committed build output (like
  `assets/mdviewer.ico`); `web-src/package-lock.json` pins its inputs;
  `web-src/node_modules/` is git-ignored.
- CLAUDE.md updates: new layout; rule that schema changes must be made in both
  `core/docschema.py` and `web-src/src/schema.js` and the bundle rebuilt;
  `core/` stays Qt-free; WYSIWYG removed from the non-goals list.

## 10. Risks

1. **CSP `'self'` on `file:` pages** - retired 2026-10-20 (PySide6 6.12.0,
   offscreen): scripts loaded from the page's own folder run, inline scripts
   and `eval` are refused, QWebChannel connects. No custom scheme is needed;
   `scripts/check_web.py` re-verifies this after every bundle rebuild.
2. **Async pulls complicate Save/Close/Exit/Open flows** - single
   `with_buffer` continuation helper, `_pending_pull` guard, a smoke check per
   flow.
3. **Normalization surprises users** on the first save from Rendered mode -
   documented in the README (accepted).
4. **Bundle maintenance** - pinned lockfile, `THIRD_PARTY.txt`, rebuild script.
5. **Large documents** - 5 MB threshold opens in Source mode.

## 11. Success criteria

- Opening a `.md` file shows the GitHub-styled view, and typing in it edits
  the document; the toolbar applies every style in section 3.
- Saving from Rendered mode produces Markdown that re-renders to the same
  HTML (for supported constructs) and follows the rules in 6.5.
- Viewing and switching modes without editing never changes the file.
- Raw HTML scripts never execute.
- `pytest` passes with zero Qt imports in `core/`; the smoke script prints
  `SMOKE OK`.
