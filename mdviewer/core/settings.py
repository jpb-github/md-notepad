"""Persistence for MD Viewer user settings (%APPDATA%\\MDViewer\\settings.json)."""

import json
import math
import os
from pathlib import Path

_VALID_THEMES = ("system", "light", "dark", "gray")
_ZOOM_MIN = 0.25
_ZOOM_MAX = 3.0
_WINDOW_KEYS = ("x", "y", "width", "height")
MAX_RECENT = 10
FONT_SIZE_MIN = 6
FONT_SIZE_MAX = 72
_FONT_FAMILY_MAX_LEN = 100
DEFAULT_FONT = {"family": "Consolas", "size": 11}


def default_path() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / ".config"
    return base / "MDViewer" / "settings.json"


def default_settings() -> dict:
    return {
        "theme": "system",
        "window": None,
        "preview_zoom": 1.0,
        "recent_files": [],
        "editor_font": dict(DEFAULT_FONT),
        "show_toolbar": True,
    }


def _clean_window(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    for key in _WINDOW_KEYS:
        if type(value.get(key)) is not int:
            return None
    return {key: value[key] for key in _WINDOW_KEYS}


def _clean_recent(value) -> list[str]:
    """Keep the first MAX_RECENT distinct, non-empty string paths."""
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen = set()
    for item in value:
        key = os.path.normcase(item) if isinstance(item, str) and item else None
        if key is None or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result[:MAX_RECENT]


def _clean_font(value) -> dict:
    """A {family, size} dict; anything unusable falls back to the default per field."""
    font = dict(DEFAULT_FONT)
    if not isinstance(value, dict):
        return font
    family = value.get("family")
    if isinstance(family, str) and 0 < len(family.strip()) <= _FONT_FAMILY_MAX_LEN:
        font["family"] = family.strip()
    size = value.get("size")
    if isinstance(size, (int, float)) and not isinstance(size, bool) and math.isfinite(size):
        font["size"] = min(max(int(size), FONT_SIZE_MIN), FONT_SIZE_MAX)
    return font


def add_recent(recent: list[str], path: str) -> list[str]:
    """Return a new recent-files list with path first (paths compare like the OS does)."""
    key = os.path.normcase(path)
    rest = [item for item in recent if os.path.normcase(item) != key]
    return [path, *rest][:MAX_RECENT]


def _clean(data) -> dict:
    result = default_settings()
    if not isinstance(data, dict):
        return result
    if data.get("theme") in _VALID_THEMES:
        result["theme"] = data["theme"]
    window = _clean_window(data.get("window"))
    if window is not None:
        result["window"] = window
    zoom = data.get("preview_zoom")
    if isinstance(zoom, (int, float)) and not isinstance(zoom, bool):
        result["preview_zoom"] = float(min(max(zoom, _ZOOM_MIN), _ZOOM_MAX))
    result["recent_files"] = _clean_recent(data.get("recent_files"))
    result["editor_font"] = _clean_font(data.get("editor_font"))
    if isinstance(data.get("show_toolbar"), bool):
        result["show_toolbar"] = data["show_toolbar"]
    return result


def load(path: Path | None = None) -> dict:
    path = path or default_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default_settings()
    return _clean(data)


def save(path: Path | None, data: dict) -> None:
    path = path or default_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_clean(data), indent=2), encoding="utf-8")
