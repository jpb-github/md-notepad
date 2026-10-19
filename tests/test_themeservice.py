from mdviewer.core import themeservice


def _reader(value):
    def read():
        return value

    return read


def _failing_reader(exc):
    def read():
        raise exc

    return read


def test_value_one_is_light():
    assert themeservice.read_system_theme(_reader(1)) == "light"


def test_value_zero_is_dark():
    assert themeservice.read_system_theme(_reader(0)) == "dark"


def test_missing_key_means_light():
    assert themeservice.read_system_theme(_failing_reader(FileNotFoundError("no key"))) == "light"


def test_access_denied_means_light():
    assert themeservice.read_system_theme(_failing_reader(PermissionError("denied"))) == "light"


def test_registry_contract():
    assert themeservice.REGISTRY_VALUE == "AppsUseLightTheme"
    assert "Personalize" in themeservice.REGISTRY_PATH
