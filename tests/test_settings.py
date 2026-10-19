from mdviewer.core import settings


def test_default_settings():
    assert settings.default_settings() == {
        "theme": "system",
        "window": None,
        "preview_zoom": 1.0,
    }


def test_default_settings_is_fresh_dict():
    first = settings.default_settings()
    first["theme"] = "dark"
    assert settings.default_settings()["theme"] == "system"


def test_default_path_location():
    import os

    if os.environ.get("APPDATA"):
        assert settings.default_path().parts[-2:] == ("MDViewer", "settings.json")


def test_load_missing_file_returns_defaults(tmp_path):
    assert settings.load(tmp_path / "nope" / "settings.json") == settings.default_settings()


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    data = {
        "theme": "dark",
        "window": {"x": 10, "y": 20, "width": 800, "height": 600},
        "preview_zoom": 1.5,
    }
    settings.save(path, data)
    assert settings.load(path) == data


def test_save_creates_parent_dirs(tmp_path):
    path = tmp_path / "deep" / "nested" / "settings.json"
    settings.save(path, settings.default_settings())
    assert path.is_file()


def test_load_corrupt_json_returns_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    assert settings.load(path) == settings.default_settings()


def test_load_non_dict_json_returns_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert settings.load(path) == settings.default_settings()


def test_load_invalid_theme_falls_back(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"theme": "neon"}', encoding="utf-8")
    assert settings.load(path)["theme"] == "system"


def test_load_zoom_clamped(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"preview_zoom": 99}', encoding="utf-8")
    assert settings.load(path)["preview_zoom"] == 3.0


def test_load_bad_window_dropped(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"window": {"x": "wide"}}', encoding="utf-8")
    assert settings.load(path)["window"] is None


def test_load_unknown_keys_dropped(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"theme": "light", "bogus": 1}', encoding="utf-8")
    assert settings.load(path) == {"theme": "light", "window": None, "preview_zoom": 1.0}
