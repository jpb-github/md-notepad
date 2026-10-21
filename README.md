# MD Viewer

A Notepad-like Markdown editor for Windows 10/11. Files open in an editable,
GitHub-styled **Rendered** view that follows the Windows light/dark/gray theme
(live), with a one-row format toolbar. View > Source is the plain-text editor
with structural completion and syntax-check underlines. The open file is
watched and reloads when it changes on disk.

## Running

```powershell
.venv\Scripts\python main.py [path\to\file.md]
```

You can also open files with File > Open... (`*.md *.markdown *.mdown *.txt`),
File > Open Recent, or by dragging one onto the window.

## Keyboard shortcuts

| Menu | Command | Shortcut |
| --- | --- | --- |
| File | New / Open... / Save / Save As... | Ctrl+N / Ctrl+O / Ctrl+S / Ctrl+Shift+S |
| File | Close / Exit | Ctrl+W / Alt+F4 |
| Edit | Undo / Redo | Ctrl+Z / Ctrl+Y |
| Edit | Cut / Copy / Paste / Paste as Plain Text / Select All | Ctrl+X / Ctrl+C / Ctrl+V / Ctrl+Shift+V / Ctrl+A |
| Edit | Find... / Replace... | Ctrl+F / Ctrl+H |
| View | Rendered / Source | Ctrl+P / Ctrl+E |
| View | Toolbar / Word Wrap | (none) |
| View | Zoom In / Zoom Out / Restore Default Zoom | Ctrl+= / Ctrl+- / Ctrl+0 |
| View | Preferences... | Ctrl+, |
| Source | Show completions | Ctrl+Space |

In Rendered mode the Edit menu acts on the rendered editor. Find has no
Replace there; Ctrl+H switches to Source and opens the Replace bar. Ctrl+click
opens a link.

### Format toolbar

| Button | Shortcut |
| --- | --- |
| Bold / Italic / Strikethrough | Ctrl+B / Ctrl+I / Ctrl+Shift+X |
| Inline code / Link | Ctrl+` / Ctrl+K |
| Bulleted / Numbered / Task list | Ctrl+Shift+8 / Ctrl+Shift+7 / Ctrl+Shift+9 |
| Quote | Ctrl+Shift+. |
| Code block / Table / Image / Horizontal rule | (none) |
| Clear formatting | Ctrl+Space |
| Block combo: Normal | Ctrl+Alt+0 |
| Block combo: Heading 1 to Heading 6 | Ctrl+Alt+1 to Ctrl+Alt+6 |

## Rendered mode

- Input rules: `# ` to `###### ` makes a heading; `- ` or `* ` a bulleted list;
  `1. ` (any number) a numbered list starting there; `[ ] ` or `[x] ` at the
  start of a list item a task item; `> ` a quote; three backticks, an optional
  language and Enter a code block; `---` and Enter a horizontal rule; inline,
  `**bold**`, `*italic*`, `` `code` `` and `~~strikethrough~~`.
- Tab and Shift+Tab sink and lift list items, and move between table cells
  (Tab in the last cell adds a row). Enter on an empty list item ends the list.
- Right-click a table cell for insert/delete row and column, delete table and
  column alignment.
- A code block has a language picker in its top-right corner and is
  syntax-highlighted while the caret is outside it.
- Clicking a task checkbox toggles it.
- Paste keeps formatting (headings, bold, links, lists, tables) and drops the
  rest; Ctrl+Shift+V pastes plain text.
- Raw HTML blocks, footnote definitions and front matter are protected blocks:
  shown but not editable, deletable as a unit. Double-click one to open Source
  mode at that block.
- A file over 5 MB opens in Source mode with the status note
  `Large file: opened in Source mode`; View > Rendered still works.

## Source mode

- Auto-close for `*`, `_`, backtick, `[`, `(`. Typing the closer steps over it,
  and Backspace between an empty pair removes both.
- Enter continues bullet, numbered (incremented) and quote lines; Enter on an
  empty item ends the list. No continuation inside code fences or tables.
- Completion popup on `#`, `|`, backtick, `>`, `-`, `*`, `_`, `[` and
  Ctrl+Space: heading levels, table separator/data rows, quote prefixes,
  code-fence languages, task-list items.
- Wavy underlines: red for an unclosed code fence, a table row with the wrong
  number of columns, or a table without a `|---|` row; orange for `#Heading`
  without a space, unbalanced `**` / `__`, or an odd number of backticks.
  Hover an underline for the message.

## Markdown normalization

Saving from Rendered mode rewrites the whole file in a canonical style: `#`
headings, `-` bullets, `1.` numbering, `**`, `*` and `~~` marks, fenced code,
aligned pipe tables, inline links, one blank line between blocks and minimal
escaping. Raw HTML, footnote definitions and front matter are kept verbatim.
A file you only view, or switch between modes without editing, is never rewritten.
Source mode saves exactly what you typed.

## Settings

View > Preferences... holds the theme (System (auto) / Light / Dark / Gray; Gray is a
mid-gray theme that is never picked automatically) and the
editor font (fixed-pitch fonts only, default Consolas 11). The theme, editor
font, window position and size, zoom, toolbar visibility (View > Toolbar)
and the recent-files list are
stored in `%APPDATA%\MDViewer\settings.json`. Delete that file to reset them.

## Known limitations

- Files are saved in the encoding they were opened with. If the text can no
  longer be represented in it (e.g. CJK text in a Windows-1252 file), MD Viewer
  offers to save as UTF-8 instead.
- Line endings are saved in the file's dominant style (CRLF if the file had
  any CRLF, else LF); mixed line endings are normalized to that style.
- Relative image paths are resolved for Markdown images and links; raw HTML
  `<img src="relative.png">` tags are not resolved.
- JavaScript in raw HTML never runs in the Rendered view: raw HTML blocks show
  in a sandboxed frame and inline HTML as a chip.
- Files over 5 MB open in Source mode (Rendered mode is slow on them).
- Not supported: merged table cells, math or diagrams, spell checking, and
  Find/Replace inside Rendered mode (Replace works in Source).
- Dark and Gray modes use Qt's Fusion style, because the native `windowsvista`
  style cannot be darkened; light mode uses the native style.

## Development

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
pytest                          # Qt-free core: mdviewer/core, tests/
python scripts\smoke_ui.py      # headless UI smoke; prints SMOKE OK
python scripts\build_web.py     # rebuild mdviewer\web\editor.js (Node.js 20+, only after changing web-src\)
python scripts\check_web.py     # verifies the committed bundle; prints WEB OK
```

The bundle `mdviewer\web\editor.js` is committed, so tests, the app and
packaging need no Node.

`mdviewer/core/` and `tests/` must never import Qt. UI behavior is covered by
`scripts/smoke_ui.py` and the manual checklist below.

## Building an executable and an installer

```powershell
pip install -e ".[build]"
python scripts\build_exe.py     # dist\MDViewer\MDViewer.exe (one folder, ~2-4 s to launch)
python scripts\build_msi.py     # dist\MDViewer-<version>-x64.msi
```

`build_exe.py` refuses to run when `mdviewer\web` lacks a runtime file and
tells you to run `build_web.py`.

`build_msi.py` runs `build_exe.py` first, then WiX (a repo-local .NET tool,
restored automatically; requires the .NET SDK). The MSI installs per user to
`%LOCALAPPDATA%\Programs\MD Viewer` without admin rights, adds a Start menu
shortcut, and is removable from Settings > Apps. Installing a newer MSI
upgrades in place. It is unsigned, so SmartScreen may warn on first run.

`build_exe.py --onefile` produces a single `dist\MDViewer.exe`, but it unpacks
about 200 MiB to a temp directory on every start (~22 s to launch), so prefer
the folder build or the MSI. Other options: `--console` (show a console for
debugging), `--icon other.ico`, `--keep-build`.

The app icon (`assets\mdviewer.ico`) is drawn in code; edit and rerun
`python scripts\make_icon.py` to change it, then rebuild.

## Manual test checklist

Run on a real Windows desktop before a release; tick each item.

### Opening
- [ ] Open via command-line argument, File > Open..., File > Open Recent, and drag-and-drop (onto the Rendered view and onto the Source editor).
- [ ] Drag-and-drop with unsaved edits first asks to save.
- [ ] Opening a missing or locked file shows a Notepad-style message and the app stays usable.

### Theme and preferences
- [ ] In System (auto), flip the Windows app mode: chrome and page adapt within about 2 s.
- [ ] Force Light and then Dark in Preferences: the system mode no longer matters. Restart: the choice persists, with no flash.
- [ ] Preferences: cancel discards edits; OK applies the editor font and size immediately and persists them.

### File watching
- [ ] External edit in Rendered mode with no unsaved changes: silent reload within about 2 s, with the scroll position kept.
- [ ] External edit in Rendered mode with unsaved changes, and in Source mode: the `File changed on disk` dialog appears and Reload works.
- [ ] Keep my version keeps the text, and the next change asks again.
- [ ] Saving from MD Viewer never triggers the dialog. Deleting the file shows one warning, and Save recreates it.

### Modes and files
- [ ] Rendered <-> Source switching keeps an unedited file byte-identical (compare on disk) and carries the dirty flag and the caret's block.
- [ ] Save and Close from Rendered mode. Alt+F4 with unsaved Rendered edits prompts.
- [ ] A file over 5 MB opens in Source mode with the `Large file: opened in Source mode` note.
- [ ] The title shows `*` while dirty. The status bar shows `Rendered` and the zoom, or `Ln/Col` in Source mode.

### Rendered editing
- [ ] Each input rule from the Rendered mode section.
- [ ] Tab and Shift+Tab in lists and tables; every item of the table context menu.
- [ ] The code language picker works, and highlighting returns when the caret leaves the block.
- [ ] Clicking a task checkbox marks the file dirty.
- [ ] Every toolbar button and its shortcut; the buttons grey out inside a code block.
- [ ] View > Toolbar hides and shows the toolbar, and the choice persists across restarts.

### Paste and links
- [ ] Paste from a browser and from Word keeps headings, bold and links and drops the rest.
- [ ] Ctrl+Shift+V pastes plain text.
- [ ] Ctrl+click opens a web link and scrolls to a `#anchor`; hovering a link shows its URL in the status bar.

### Rendering and find
- [ ] Tables, footnotes, task lists, strikethrough, relative images and a missing image render.
- [ ] A raw HTML block containing a `<script>` does nothing.
- [ ] Ctrl+F counts and steps through matches in Rendered mode; Ctrl+H lands in Source mode with the Replace bar.
- [ ] A live theme flip and zoom work while editing.

### Source mode
- [ ] Every completion trigger: `#`, `|` + Ctrl+Space, backtick x3, `>`, `-`, `*`, `_`, `[`.
- [ ] Auto-close and step-over; Backspace removes an empty pair; `snake_case` and `* bullet` type normally.
- [ ] Enter continuation for `-`, `1.`, `>`; an empty item exits; nothing continues inside a fence.
- [ ] Each underline type: unclosed fence, table column mismatch, missing separator row (red); `#Heading`, lone `**`, odd backticks (orange).
- [ ] Find/Replace: Match case, count, Previous/Next wrap, Replace, Replace All + one Ctrl+Z, Esc.
- [ ] Word Wrap toggles.

### Installed build
- [ ] The MSI installs without a UAC prompt, the Start menu shortcut and exe show the app icon, and the app launches in a few seconds.
- [ ] Uninstalling from Settings > Apps removes the folder and the shortcut.
