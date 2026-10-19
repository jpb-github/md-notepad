# MD Viewer

A Notepad-like Markdown viewer for Windows: a rendered preview with
GitHub-like styling that follows the Windows light/dark theme, plus an
edit mode with structural completion and syntax underlines.

## Development

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
pytest
```

The manual test checklist is documented once the UI is complete (Task 14).

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
