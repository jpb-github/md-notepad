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
