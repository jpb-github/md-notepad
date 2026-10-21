# CLAUDE.md

Guidance for agents working in this repository.

## Project

MD Viewer: a single-window, Notepad-like Markdown editor for Windows 10/11,
built with Python 3.12+ and PySide6 (Qt >= 6.5, QtWebEngine). Files open in
Rendered mode: an editable, GitHub-styled WYSIWYG view (ProseMirror running in
QtWebEngine, with a one-row format toolbar) that follows the Windows
light/dark theme. View > Source switches to a plain-text editor with
structural completion and wavy syntax-check underlines. The open file is
watched and re-rendered when it changes on disk.

## Source of truth

- Spec: `docs/superpowers/specs/2026-10-16-md-viewer-design.md` - v1 behavior,
  menus, wording, non-goals. Read it before changing behavior.
- WYSIWYG spec: `docs/superpowers/specs/2026-10-20-wysiwyg-editing-design.md` -
  Rendered mode, toolbar, schema, serializer, bridge; it supersedes v1 where
  they differ.
- Implementation plan: `docs/superpowers/plans/2026-10-16-md-viewer.md` -
  Tasks 1-14 with exact code, tests, and commit steps, plus "Review Focus"
  sections listing edge cases each task must handle. Execute it with
  superpowers:subagent-driven-development or superpowers:executing-plans,
  task by task, in order. Later tasks edit earlier tasks' code by matching
  exact text, so do not freelance refactors while executing the plan.
- WYSIWYG plan: `docs/superpowers/plans/2026-10-20-wysiwyg-editing.md` -
  Tasks 1-19, executed the same way.

Status: plan Tasks 1-14 are done, plus the user-requested Open Recent,
Preferences and packaging (one-folder build, MSI, icon) work; WYSIWYG plan
Tasks 1-19 are done (version 2.0.0, released; the manual desktop check was
done by hand). Check `git log` for details.

## Repository layout

```
main.py                    entry point -> mdviewer.app.main(argv)
mdviewer/
  app.py                   QApplication bootstrap, settings load/save on exit
  main_window.py           menus, Rendered/Source mode switching, file ops,
                           status bar, file-watch timer, theme system, dialog seams
  richview.py              QWebEngineView + QWebChannel bridge to the web editor
  toolbar.py               format toolbar (BLOCKS, BUTTONS, shortcuts, icons)
  dialogs.py               link and image dialogs
  editor.py                Source mode: QPlainTextEdit + highlighter + completer
  findbar.py               Find/Replace bar under the editor
  preferences.py           Preferences dialog (theme, fixed-pitch editor font)
  web/                     committed build output of web-src/ (editor.js, .css,
                           .html, qwebchannel.js, THIRD_PARTY.txt); never hand-edit
  core/                    Qt-free, unit-tested logic
    encoding.py            BOM/UTF-8/Windows-1252 detect + encode
    settings.py            %APPDATA%\MDViewer\settings.json
    themeservice.py        AppsUseLightTheme registry reading (injectable)
    filewatch.py           (mtime_ns, size) watcher state machine
    mdcheck.py             line-level Markdown errors/warnings
    completion.py          suggestions, Enter continuation, auto-close
    render.py              themed HTML page shell for the web editor (Pygments)
    docmodel.py            Markdown -> ProseMirror-shaped document (mistune)
    docschema.py           the document schema contract (mirrors schema.js)
    serialize.py           document -> canonical Markdown
    frontmatter.py         YAML front matter split/join
    urls.py                link/image URL classification and sanitizing
web-src/                   ProseMirror editor source (Node 20+, esbuild);
                           src/schema.js, bridge.js, commands.js, input.js,
                           nodeviews.js, tables.js, editor.js, editor.css
tests/                     pytest for mdviewer/core only (+ docs and web asset checks)
tests/corpus/              Markdown round-trip corpus
scripts/smoke_ui.py        headless UI smoke test (prints SMOKE OK)
scripts/build_web.py       esbuild bundle of web-src/ -> mdviewer/web/editor.js
scripts/check_web.py       verifies the committed bundle is current (prints WEB OK)
scripts/build_exe.py       PyInstaller one-folder build -> dist/MDViewer/MDViewer.exe
scripts/build_msi.py       builds the exe folder, then a per-user MSI (WiX)
scripts/make_icon.py       draws assets/mdviewer.ico (+ .png preview) with QPainter
assets/                    generated app icon, committed; used by the exe and MSI
installer/MDViewer.wxs     WiX source for the MSI (keep UpgradeCode constant)
.config/dotnet-tools.json  pins the repo-local WiX tool (dotnet tool restore)
docs/superpowers/          specs and plans
```

## Hard rules

- `mdviewer/core/` and `tests/` must never import Qt. Put any logic that can
  be pure into `core/` and unit-test it there.
- Save writes the buffer in the encoding detected on open, preserving the
  file's newline style (`MainWindow.newline`). Never use
  `QPlainTextEdit.toPlainText()` for the buffer (it turns NBSP into spaces);
  use the `MainWindow.buffer` property. In Rendered mode the rendered document
  may be newer than the buffer: `with_buffer(fn)` pulls and serializes it
  asynchronously when Rendered changed, then calls `fn` with the text.
- Text search in the editor goes through `QTextDocument.find` (Qt positions
  are UTF-16 units; Python offsets drift after emoji).
- Every modal dialog goes through the seams in `mdviewer/main_window.py`
  (`ask`, `show_error`, `pick_open_path`, `pick_save_path`,
  `run_preferences`, `run_link_dialog`, `run_image_dialog`,
  `read_system_theme`) so the smoke script can fake them.
- Schema names (node and mark types, attributes) change in both
  `core/docschema.py` and `web-src/src/schema.js`, and the bundle is rebuilt
  with `scripts/build_web.py`.
- `mdviewer/web/*` is committed build output: never hand-edit it. After a
  rebuild `scripts/check_web.py` must print `WEB OK`.
- Raw HTML never gets `allow-scripts`, and `javascript:` URLs are stripped in
  both Python and JS.
- Non-goals (do not add): tabs/multiple documents, printing, cross-file
  search, default `.md` handler registration, custom CSS/themes,
  localization, signing/MSIX/auto-update, merged table cells, math and
  diagrams, spell checking, Find/Replace inside Rendered mode, comments,
  track changes, byte-exact source preservation.
- Packaging: the supported distribution artifact is the per-user MSI
  `dist/MDViewer-<version>-x64.msi` built by `scripts/build_msi.py` from the
  PyInstaller one-folder build (`scripts/build_exe.py`, `build` extra) and
  `installer/MDViewer.wxs` (WiX 5, pinned in `.config/dotnet-tools.json`).
  Do not make one-file the default: it unpacks ~200 MiB to %TEMP% on every
  launch (~22 s vs ~2-4 s for one-folder); `--onefile` exists only as an
  opt-in. Keep the build scripts in sync when adding runtime dependencies or
  data files (bundle them explicitly; Pygments lexers are collected with
  `--collect-submodules pygments`). `mdviewer/web` ships via one `--add-data`
  entry (`_internal/mdviewer/web`), and `build_exe.py` checks for it before
  and after the build. The version lives in `pyproject.toml` and `mdviewer/__init__.py` (a test keeps them equal); bump both so
  the MSI replaces an installed one. `build/` and `dist/` are git-ignored;
  never commit build output. Signing, MSIX and auto-update are out of scope.

## Commands (PowerShell, repo root)

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pip install -e .
.venv\Scripts\python -m pytest -v              # core unit tests
.venv\Scripts\python scripts\smoke_ui.py       # UI smoke, expects SMOKE OK
.venv\Scripts\python scripts\check_web.py      # committed web bundle is current, expects WEB OK
.venv\Scripts\python scripts\build_web.py      # rebuild mdviewer\web\editor.js after editing web-src\ (needs Node 20+)
rg -n "import (PySide|Qt)|from PySide" mdviewer/core tests   # must print nothing
.venv\Scripts\python main.py path\to\file.md   # run the app
.venv\Scripts\python scripts\build_exe.py      # dist\MDViewer\MDViewer.exe (needs pip install -e ".[build]")
.venv\Scripts\python scripts\build_msi.py      # dist\MDViewer-<ver>-x64.msi (also needs the .NET SDK)
```

The shell available to agents is Git Bash; use forward slashes there
(`.venv/Scripts/python`).

## Testing conventions

- Core: TDD with pytest; write the failing test first.
- UI: add checks to `scripts/smoke_ui.py` directly above the line
  `# --- Later tasks insert their checks directly above this line. ---`.
  Use `check(condition, label)`; drive dialogs via the `FAKE` dict
  (`answer`, `open_path`, `save_path`, `system_theme`, `during_ask`, `link`,
  `image`, `image_path`, `prefs`, `during_dialog`). Checks on the web page use
  the `page_js`/`pump` helpers in `scripts/smoke_ui.py`.
  The smoke sets `QT_QPA_PLATFORM=offscreen` and a temporary `APPDATA`, so it
  never touches real user settings.
- `tests/test_docs.py` pins the README shortcut tables to the shortcut
  literals in `main_window.py` and `toolbar.py`: a shortcut change updates the
  README table.
- Behavior that needs a real desktop (drag-and-drop from Explorer, live
  Windows theme flips, scroll retention, paste from Word or a browser) has no
  automated test: check it by hand on a real desktop before a release.

## Commits

Small commits per plan task, conventional prefixes (`feat:`, `fix:`,
`docs:`, `chore:`), using the exact messages given in the plan steps.
