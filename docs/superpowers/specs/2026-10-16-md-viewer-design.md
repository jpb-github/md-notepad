# MD Viewer - Design Specification

- **Date:** 2026-10-16
- **Status:** Approved via brainstorming; ready for implementation planning
- **Target platform:** Windows 10/11
- **Language/runtime:** Python 3.12+ (dev environment: 3.14.2)

## 1. Overview

MD Viewer is a single-file Windows desktop application with a Notepad-like
look. It opens Markdown files directly into a rendered **preview mode** using
standard (GitHub-like) Markdown styling that follows the Windows system
light/dark theme, including live switches while the app is running. A menu
option switches to **edit mode**: a Notepad-style plain-text editor with
structural inline completion and Markdown syntax-check underlines.

Behavioral contract:

- The rendered view updates automatically, within ~2 seconds, when the file
  changes on disk (silent re-render in preview mode).
- In edit mode, an external file change always shows a message before content
  is replaced (Reload vs. Keep my version).
- The user can force Light or Dark from the View menu, overriding the
  system theme.

### Non-goals (v1)

Multiple documents/tabs; printing; cross-file search; registering as the
default `.md` handler; WYSIWYG; custom user CSS or themes; localization;
executable packaging (a PyInstaller note may be added to the README later).

## 2. Tech Stack

- **Python 3.12+** - verify PySide6 wheel support for 3.14 during
  implementation; fall back to 3.12/3.13 if no wheel exists.
- **PySide6 (Qt 6, >= 6.5)** - `QtWidgets`, `QtGui`,
  `QtWebEngineWidgets`. Native Windows look via the `windowsvista` style.
- **mistune** - Markdown to HTML (tables, strikethrough, footnotes).
- **Pygments** - syntax highlighting of fenced code blocks in rendered HTML.
- **pytest** - unit tests for the Qt-free core.

## 3. Window and UI (Notepad mapping)

### Layout

- `QMainWindow`
  - Menu bar: File / Edit / View / Help
  - Central: `QStackedWidget` - page 0: preview (`QWebEngineView`),
    page 1: editor (custom `QPlainTextEdit`)
  - Find/Replace bar (hidden by default, shown on the editor page)
  - Status bar

### Menus and shortcuts

- **File:** New (Ctrl+N), Open... (Ctrl+O), Save (Ctrl+S), Save As...
  (Ctrl+Shift+S), Close (Ctrl+W), Exit (Alt+F4)
- **Edit:** Undo (Ctrl+Z), Redo (Ctrl+Y), Cut (Ctrl+X), Copy (Ctrl+C),
  Paste (Ctrl+V), Find... (Ctrl+F), Replace... (Ctrl+H), Select All (Ctrl+A).
  Enabled only in edit mode, except Copy, which is also enabled in preview
  mode (copies the selected rendered text).
- **View:**
  - Preview Mode (Ctrl+P) / Edit Mode (Ctrl+E) - checkable radio pair.
    Any opened file starts in Preview.
  - Word Wrap - checkable, default on, editor page only.
  - Zoom In (Ctrl+=), Zoom Out (Ctrl+-), Zoom Reset (Ctrl+0) - preview only.
  - Theme submenu - checkable radio trio: **System (auto)** (default),
    **Light**, **Dark**.
- **Help:** About

### Theme menu behavior

- **System (auto):** follows the Windows theme via live registry polling
  (section 6).
- **Light / Dark:** forces the full app theme (Qt chrome palette + preview
  CSS) regardless of the system theme; the system poll is ignored while a
  forced choice is active.
- The selection persists in `%APPDATA%\MDViewer\settings.json` (together
  with window geometry and preview zoom) and is restored on startup.

### Title bar

- `filename.md - MD Viewer`
- `*filename.md - MD Viewer` while unsaved changes exist
- `Untitled - MD Viewer` for a new, never-saved document

### Status bar

- Left (edit): `Ln X, Col Y`. Left (preview): `Preview` and zoom % when not
  100%.
- Right (both modes): zoom %, encoding (e.g. `UTF-8`), file size.
- Transient warnings: file not found on disk, render fallback.

### Editor page

- Monospace font (Consolas 11), word wrap on by default, no line numbers
  (Notepad fidelity).
- Cursor position drives the status bar Ln/Col.

### Find/Replace bar

- Find: text field, case-sensitive checkbox, match count, Previous/Next.
- Replace mode adds a replacement field, Replace, and Replace All.
- Esc closes the bar and restores focus to the editor.

## 4. Modes, Saving, and the File on Disk

### State

    mode: preview | edit
    dirty: bool
    loaded_path: Path | None
    encoding: str            # detected on open; default utf-8
    buffer: str              # single source of truth for both pages
    expected_disk_state: (mtime_ns, size) | None   # set after each own save

### Opening

- Sources: command-line argument, File > Open... (filters: `*.md *.markdown
  *.mdown *.txt`), drag-and-drop onto the window.
- Decode: BOM-aware (utf-8-sig, utf-16), then strict UTF-8, then Windows-1252
  fallback. Remember the detected encoding for saving.
- On success: load buffer, mode = preview, render, update title/status.
- Drag-and-drop with a dirty buffer first offers the standard save dialog.
- Open failure (missing, access denied, unreadable) -> message box with
  Notepad-style wording; the app stays usable.

### Mode switching

- Preview -> Edit: show the editor page with the current buffer, focus it.
- Edit -> Preview:
  - buffer not dirty: switch immediately and re-render.
  - buffer dirty: message box `Save changes to <name>?`
    - **Save** - write buffer, clear dirty, re-render, switch.
    - **Don't Save** - reload from disk (or empty buffer for Untitled),
      clear dirty, re-render, switch. Preview shows disk content, not the
      discarded edits.
    - **Cancel** - remain in edit mode.
- File > New: empty `Untitled` buffer in **edit** mode (a preview of an
  empty file is meaningless).
- File > Close: save prompt if dirty, then reset to a fresh empty state.

### Saving

- Save writes the buffer exactly as-is (no line-ending conversion) in the
  remembered encoding; for a new/Untitled file it acts as Save As (default
  filter `.md`).
- After a successful write: refresh `expected_disk_state` from a new stat,
  clear dirty, update title and status bar.

### File watching

- A `QTimer` polls `stat(loaded_path)` every 1000 ms and compares
  (mtime_ns, size).
- If the current state equals `expected_disk_state` (our own save), ignore it
  and clear the expectation; this suppresses save-echo false alarms.
- Path missing: one status-bar warning ("not found on disk"); stop warning
  until the path reappears.
- Change detected:
  - **Preview mode:** silently re-read and re-render. Read failure keeps the
    last rendered content and shows a status-bar warning.
  - **Edit mode:** message box first, always - title `File changed on disk`,
    body `"<name>" was modified externally at HH:MM:SS. Reload it now? Your
    unsaved changes will be lost.`
    - **Reload** - buffer := disk content, dirty = false, refresh
      highlighting, title, status.
    - **Keep my version** - no change; the watcher stays armed, so the next
      external change asks again.
  - The dialog is shown even when the buffer is not dirty (default button:
    Reload).

## 5. Editor Intelligence

### Completion (structural)

- Auto-close pairs on typing: `*`, `_`, backtick, `[`, `(`. The closing
  partner is inserted at the cursor; typing a closing character that already
  sits at the cursor types over it instead of inserting.
- Enter key (editor page only):
  - list item: continue the same marker and indent; ordered lists increment
    their number; an empty item drops the marker (exits the list).
  - blockquote line: continue with `> `.
  - inside a fenced code block or table row: no continuation.
- QCompleter popup - trigger characters #, |, backtick, >, -, *, _, [ - plus manual
  Ctrl+Space:
  - `#` at line start -> heading levels `#` through `######` (with trailing
    space).
  - line containing `|` -> table separator row `| --- | ... |` matching the
    line's column count, and a same-width data row.
  - `> ` -> quote continuations (`> `, `> - `).
  - triple backtick at line start -> fence languages: python, bash,
    powershell, javascript, typescript, json, yaml, xml, html, css, c, cpp,
    csharp, go, rust, java, sql, toml, text.
  - `- `, `* `, `+ ` at line start -> task-list snippets `- [ ] `, `- [x] `.
- Suggestion logic lives in Qt-free `core/completion.py` (line text + column
  -> list) so it is unit-testable.

### Syntax check (underlines)

A custom `QSyntaxHighlighter` over the editor does two jobs:

1. Structural colors: headings, bold/italic, inline code, links (link color
   + underline), list markers, blockquotes, table separators, uniform color
   for fenced-code content, HTML comments.
2. Wavy underlines (Qt `Wave_Underline`, requires Qt 6.4+):
   - **Errors (red):** unclosed fenced code block; table data row whose
     column count differs from the header; table block missing its
     `|---|` separator row.
   - **Warnings (orange):** heading missing the space after `#`; unbalanced
     `**`/`__` markers on a line outside code; odd number of inline
     backticks on a line outside code.

Rules are line-level and recomputed only for blocks that change (Qt
highlighter model). Rule implementations live in Qt-free
`core/mdcheck.py`: `check(text) -> list[Issue]` where
`Issue(line, start, end, severity, message)`. No full CommonMark parsing.

## 6. Theming

- **Theme source (System mode):** poll the registry key
  `HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize\AppsUseLightTheme`
  (DWORD: 1 = light, 0 = dark) every 2000 ms. The poll runs only while
  View > Theme is **System (auto)**; a forced Light/Dark skips it.
- Key missing or unreadable: assume light.
- Effective theme change applies:
  - a light or dark `QPalette` to the whole app (chrome, editor, status bar),
  - a re-render of the preview with the matching CSS variable set (same HTML,
    different variables) - no content reload from disk, no mode switch.
- **Preview CSS:** standard GitHub-like stylesheet - system font stack,
  ~835 px content column, h1/h2 bottom borders, bordered tables, styled
  blockquotes, Consolas/Menlo code font. Light variables: white background,
  `#1f2328` text. Dark variables: `#0d1117`-style GitHub dark palette.
- Pygments formatter follows the theme: `default` (light), `native` (dark).

## 7. Error Handling

- Open/read failure -> message box (Notepad-style wording); app stays usable.
- Watch-time read failure -> keep last good content, one status-bar warning
  per change event.
- Render exception -> preview falls back to the escaped raw text in a `<pre>`
  plus a status-bar warning.
- File deleted on disk -> one-time status-bar warning; editing continues in
  memory; Save recreates the file.
- No hard file-size limit; files above ~10 MB may render slowly - accepted
  and documented.

## 8. Architecture and Files

    MD-viewer/
    |-- main.py                 # entry: args, QApplication, MainWindow
    |-- mdviewer/
    |   |-- app.py              # bootstrap, settings load/save
    |   |-- main_window.py      # menus, status bar, mode switch, dialogs,
    |   |                       #   watcher timer, find/replace bar
    |   |-- preview.py          # QWebEngineView wrapper, HTML assembly, zoom
    |   |-- editor.py           # QPlainTextEdit subclass, highlighter,
    |   |                       #   completer, auto-close/enter rules
    |   +-- core/               # Qt-free, fully unit-tested
    |       |-- mdcheck.py      # structural Markdown errors/warnings
    |       |-- completion.py   # context -> suggestions; enter/autoclose
    |       |-- filewatch.py    # watcher state machine (injectable stat)
    |       |-- themeservice.py # theme key parsing/polling (injectable)
    |       |-- encoding.py     # BOM/UTF-8/1252 detection and save encoding
    |       +-- settings.py     # %APPDATA%\MDViewer\settings.json
    |-- tests/                  # pytest; must not import Qt
    |-- pyproject.toml
    |-- requirements.txt        # PySide6, mistune, pygments, pytest
    +-- README.md

Unit responsibilities:

- `mdcheck.check(text)` - pure function returning issues for the whole
  document; the highlighter maps them onto line ranges.
- `completion.suggestions_for(line, col)`,
  `completion.should_continue_on_enter(line, col)`,
  `completion.AUTOCLOSE_PAIRS`.
- `filewatch.Watcher(path, stat_fn).poll() -> Event`
  (`unchanged` / `changed` / `missing`) plus `note_write(mtime, size)` for
  save-echo suppression.
- `themeservice.read_system_theme(reader) -> "light" | "dark"`.
- `encoding.detect(raw_bytes) -> (text, name)`, `encoding.encode(text, name)`.

## 9. Testing

- **Unit (pytest, no Qt imports):**
  - `mdcheck`: snippet corpus covering valid/unclosed fences, table
    variants (missing separator, column mismatch), heading-without-space,
    emphasis balance (including markers inside code spans and inside fenced
    blocks).
  - `completion`: heading, table, quote, fence-language, and task-list
    contexts; enter-continuation cases (ordered increment, empty-item exit,
    no continuation inside fences/tables).
  - `filewatch`: external change detection, own-save echo suppression,
    missing path, path reappearing.
  - `encoding`: UTF-8 BOM, plain UTF-8, Windows-1252 bytes, UTF-16 BOM.
  - `themeservice`: value 1, value 0, missing key.
- **Manual checklist (documented in the README):** open via argument,
  dialog, and drag-and-drop; switch the Windows theme live and watch chrome
  + preview adapt; force Light/Dark and restart to confirm persistence;
  external edit while previewing (silent re-render); external edit while
  editing with and without unsaved changes (Reload vs. Keep);
  dirty-buffer preview switch (Save / Don't Save / Cancel); Save, Save As,
  Close; every completion trigger; each underline type; Find/Replace;
  Word Wrap; preview zoom; title dirty marker; status bar updates.

## 10. Success Criteria

- Opening any `.md` file shows standard-styled rendered Markdown matching
  the current Windows theme, and the app adapts live when Windows' theme
  flips.
- View > Edit Mode yields a Notepad-feel editor; completion and syntax
  underlines behave as specified in section 5.
- An external file change updates the preview without user action within
  ~2 seconds; in edit mode the dialog always precedes any content change.
- `pytest` passes with zero Qt imports in the core.

## 11. Risks

- **PySide6 wheel for Python 3.14** - verify during implementation; fall
  back to 3.12/3.13 if unavailable.
- **QtWebEngine memory** (~150-300 MB) - accepted for a desktop viewer.
- **`Wave_Underline` availability** - pin `PySide6 >= 6.5`.

