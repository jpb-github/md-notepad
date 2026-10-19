"""System theme detection for MD Viewer (Windows AppsUseLightTheme DWORD)."""

REGISTRY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
REGISTRY_VALUE = "AppsUseLightTheme"


def read_system_theme(reader) -> str:
    """Return 'light' or 'dark' from a caller-provided DWORD reader.

    Any read failure (missing key, access denied, unexpected value)
    means 'light'.
    """
    try:
        return "light" if int(reader()) == 1 else "dark"
    except Exception:
        return "light"


def system_theme_reader():
    """Return a reader for the real Windows registry (Windows only)."""
    import winreg

    def read():
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_PATH)
        try:
            value, _ = winreg.QueryValueEx(key, REGISTRY_VALUE)
        finally:
            winreg.CloseKey(key)
        return int(value)

    return read
