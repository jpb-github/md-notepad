# CLAUDE.md

Guidance for agents working in this repository.

## Project

MD Viewer: a single-window, Notepad-like Markdown viewer for Windows 10/11,
built with Python 3.12+ and PySide6 (Qt >= 6.5, QtWebEngine). Files open in a
rendered, GitHub-styled preview that follows the Windows light/dark theme;
View > Edit Mode switches to a plain-text editor with structural completion
and wavy syntax-check underlines; the open file is watched and re-rendered
when it changes on disk.

## Source of truth

- Spec: `docs/superpowers/specs/2026-10-16-md-viewer-design.md` - behavior,
  menus, wording, non-goals. Read it before changing behavior.
- Implementation plan: `docs/superpowers/plans/2026-10-16-md-viewer.md` -
  Tasks 1-14 with exact code, tests, and commit steps, plus "Review Focus"
  sections listing edge cases each task must handle. Execute it with
  superpowers:subagent-driven-development or superpowers:executing-plans,
  task by task, in order. Later tasks edit earlier tasks' code by matching
  exact text, so do not freelance refactors while executing the plan.

Status: the spec and the plan are committed; implementation has not started
(no `mdviewer/` package yet). Check `git log` for which plan tasks are done.

## Repository layout (target, per the plan)

```
main.py                    entry point -> mdviewer.app.main(argv)
mdviewer/
  app.py                   QApplication bootstrap, settings load/save on exit
  main_window.py           menus, mode switching, file ops, status bar,
                           file-watch timer, theme system, dialog seams
  preview.py               QWebEngineView wrapper (JS disabled, temp-file load)
  editor.py                QPlainTextEdit + highlighter + completer
  findbar.py               Find/Replace bar under the editor
  core/                    Qt-free, unit-tested logic
    encoding.py            BOM/UTF-8/Windows-1252 detect + encode
    settings.py            %APPDATA%\MDViewer\settings.json
    themeservice.py        AppsUseLightTheme registry reading (injectable)
    filewatch.py           (mtime_ns, size) watcher state machine
    mdcheck.py             line-level Markdown errors/warnings
    completion.py          suggestions, Enter continuation, auto-close
    render.py              Markdown -> themed HTML page (mistune + Pygments)
tests/                     pytest for mdviewer/core only
scripts/smoke_ui.py        headless UI smoke test (prints SMOKE OK)
docs/superpowers/          spec and plan
```

## Hard rules

- `mdviewer/core/` and `tests/` must never import Qt. Put any logic that can
  be pure into `core/` and unit-test it there.
- Save writes the buffer in the encoding detected on open, preserving the
  file's newline style (`MainWindow.newline`). Never use
  `QPlainTextEdit.toPlainText()` for the buffer (it turns NBSP into spaces);
  use the `MainWindow.buffer` property.
- Text search in the editor goes through `QTextDocument.find` (Qt positions
  are UTF-16 units; Python offsets drift after emoji).
- Every modal dialog goes through the seams in `mdviewer/main_window.py`
  (`ask`, `show_error`, `pick_open_path`, `pick_save_path`,
  `read_system_theme`) so the smoke script can fake them.
- v1 non-goals (do not add): tabs/multiple documents, printing, cross-file
  search, default `.md` handler registration, WYSIWYG, custom CSS/themes,
  localization, executable packaging.

## Commands (PowerShell, repo root)

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pip install -e .
.venv\Scripts\python -m pytest -v              # core unit tests
.venv\Scripts\python scripts\smoke_ui.py       # UI smoke, expects SMOKE OK
rg -n "import (PySide|Qt)|from PySide" mdviewer/core tests   # must print nothing
.venv\Scripts\python main.py path\to\file.md   # run the app
```

The shell available to agents is Git Bash; use forward slashes there
(`.venv/Scripts/python`).

## Testing conventions

- Core: TDD with pytest; write the failing test first.
- UI: add checks to `scripts/smoke_ui.py` directly above the line
  `# --- Later tasks insert their checks directly above this line. ---`.
  Use `check(condition, label)`; drive dialogs via the `FAKE` dict
  (`answer`, `open_path`, `save_path`, `system_theme`, `during_ask`).
  The smoke sets `QT_QPA_PLATFORM=offscreen` and a temporary `APPDATA`, so it
  never touches real user settings.
- Behavior that needs a real desktop (drag-and-drop from Explorer, live
  Windows theme flips, scroll retention) is covered by the manual checklist
  in `README.md` (written in plan Task 14).

## Commits

Small commits per plan task, conventional prefixes (`feat:`, `fix:`,
`docs:`, `chore:`), using the exact messages given in the plan steps.
