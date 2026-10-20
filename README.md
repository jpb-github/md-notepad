# MD Viewer

A Notepad-like Markdown viewer for Windows 10/11. Files open in a rendered
preview with GitHub-like styling that follows the Windows light/dark theme
(live), and View > Edit Mode turns the window into a plain-text editor with
structural completion and syntax-check underlines. The open file is watched:
the preview refreshes on its own when the file changes on disk.

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
| Edit | Cut / Copy / Paste / Select All | Ctrl+X / Ctrl+C / Ctrl+V / Ctrl+A |
| Edit | Find... / Replace... | Ctrl+F / Ctrl+H |
| View | Preview Mode / Edit Mode | Ctrl+P / Ctrl+E |
| View | Zoom In / Zoom Out / Restore Default Zoom | Ctrl+= / Ctrl+- / Ctrl+0 |
| View | Preferences... | Ctrl+, |
| Editor | Show completions | Ctrl+Space |

Edit commands work in Edit Mode only, except Copy, which also copies
selected text from the preview.

## Editing features

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

## Settings

View > Preferences... holds the theme (System (auto) / Light / Dark / Gray; Gray is a
mid-gray theme that is never picked automatically) and the
editor font (fixed-pitch fonts only, default Consolas 11). The theme, editor
font, window position and size, preview zoom and the recent-files list are
stored in `%APPDATA%\MDViewer\settings.json`. Delete that file to reset them.

## Known limitations

- Files are saved in the encoding they were opened with. If the text can no
  longer be represented in it (e.g. CJK text in a Windows-1252 file), MD Viewer
  offers to save as UTF-8 instead.
- Line endings are saved in the file's dominant style (CRLF if the file had
  any CRLF, else LF); mixed line endings are normalized to that style.
- Relative image paths are resolved for Markdown images and links; raw HTML
  `<img src="relative.png">` tags are not resolved.
- JavaScript in raw HTML never runs in the preview.
- Files above roughly 10 MB render slowly.
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
```

`mdviewer/core/` and `tests/` must never import Qt. UI behavior is covered by
`scripts/smoke_ui.py` and the manual checklist below.

## Building an executable and an installer

```powershell
pip install -e ".[build]"
python scripts\build_exe.py     # dist\MDViewer\MDViewer.exe (one folder, ~2-4 s to launch)
python scripts\build_msi.py     # dist\MDViewer-<version>-x64.msi
```

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
- [ ] Open via command-line argument, File > Open..., File > Open Recent, and drag-and-drop (onto the preview and onto the editor).
- [ ] Drag-and-drop with unsaved edits first asks to save.
- [ ] Opening a missing or locked file shows a Notepad-style message and the app stays usable.

### Theme and preferences
- [ ] In System (auto), flip the Windows app mode: chrome and preview adapt within about 2 s.
- [ ] Force Light and then Dark in Preferences: the system mode no longer matters. Restart: the choice persists, with no flash.
- [ ] Preferences: cancel discards edits; OK applies the editor font and size immediately and persists them.

### File watching
- [ ] External edit while previewing: silent re-render within about 2 s, with the scroll position kept.
- [ ] External edit while editing, with no unsaved changes: the `File changed on disk` dialog appears and Reload works.
- [ ] External edit while editing with unsaved changes: Keep my version keeps the text, and the next change asks again.
- [ ] Saving from MD Viewer never triggers the dialog. Deleting the file shows one warning, and Save recreates it.

### Modes and files
- [ ] Dirty Edit -> Preview: Save writes and previews; Don't Save previews the disk version; Cancel stays in the editor.
- [ ] Save, Save As (adds `.md`), Close (prompts if dirty), New (opens in edit mode). Alt+F4 with unsaved edits prompts.
- [ ] The title shows `*` while dirty. The status bar shows Ln/Col in edit mode, Preview + zoom, encoding and size.

### Editor
- [ ] Every completion trigger: `#`, `|` + Ctrl+Space, backtick ×3, `>`, `-`, `*`, `_`, `[`.
- [ ] Auto-close and step-over; Backspace removes an empty pair; `snake_case` and `* bullet` type normally.
- [ ] Enter continuation for `-`, `1.`, `>`; an empty item exits; nothing continues inside a fence.
- [ ] Each underline type: unclosed fence, table column mismatch, missing separator row (red); `#Heading`, lone `**`, odd backticks (orange).
- [ ] Find/Replace: Match case, count, Previous/Next wrap, Replace, Replace All + one Ctrl+Z, Esc.
- [ ] Word Wrap toggles; preview zoom in/out/reset persists across restarts.

### Preview
- [ ] Tables, footnotes, task lists, strikethrough, highlighted code, and relative images render.
- [ ] A web link opens the browser; a footnote link jumps within the page.

### Installed build
- [ ] The MSI installs without a UAC prompt, the Start menu shortcut and exe show the app icon, and the app launches in a few seconds.
- [ ] Uninstalling from Settings > Apps removes the folder and the shortcut.
