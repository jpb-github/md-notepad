import json

from mdviewer.core import settings


def test_default_settings():
    assert settings.default_settings() == {
        "theme": "system",
        "window": None,
        "preview_zoom": 1.0,
        "recent_files": [],
        "editor_font": {"family": "Consolas", "size": 11},
    }


def test_default_settings_is_fresh_dict():
    first = settings.default_settings()
    first["theme"] = "dark"
    first["recent_files"].append("x.md")
    first["editor_font"]["size"] = 99
    assert settings.default_settings()["theme"] == "system"
    assert settings.default_settings()["recent_files"] == []
    assert settings.default_settings()["editor_font"]["size"] == 11


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
        "recent_files": ["C:/docs/a.md", "C:/docs/b.md"],
        "editor_font": {"family": "Cascadia Mono", "size": 14},
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
    assert settings.load(path) == {**settings.default_settings(), "theme": "light"}


def _font(tmp_path, raw):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"editor_font": raw}), encoding="utf-8")
    return settings.load(path)["editor_font"]


def test_load_editor_font_roundtrips_valid_values(tmp_path):
    assert _font(tmp_path, {"family": "Courier New", "size": 9}) == {"family": "Courier New", "size": 9}


def test_load_editor_font_must_be_a_dict(tmp_path):
    assert _font(tmp_path, "Consolas") == settings.DEFAULT_FONT


def test_load_editor_font_bad_family_falls_back(tmp_path):
    assert _font(tmp_path, {"family": 7, "size": 12})["family"] == "Consolas"
    assert _font(tmp_path, {"family": "   ", "size": 12})["family"] == "Consolas"
    assert _font(tmp_path, {"family": "x" * 500, "size": 12})["family"] == "Consolas"


def test_load_editor_font_family_is_trimmed(tmp_path):
    assert _font(tmp_path, {"family": "  Lucida Console ", "size": 12})["family"] == "Lucida Console"


def test_load_editor_font_size_clamped_and_typed(tmp_path):
    assert _font(tmp_path, {"family": "A", "size": 1})["size"] == settings.FONT_SIZE_MIN
    assert _font(tmp_path, {"family": "A", "size": 500})["size"] == settings.FONT_SIZE_MAX
    assert _font(tmp_path, {"family": "A", "size": "big"})["size"] == 11
    assert _font(tmp_path, {"family": "A", "size": True})["size"] == 11
    assert _font(tmp_path, {"family": "A", "size": 12.7})["size"] == 12


def test_load_editor_font_non_finite_size_does_not_crash(tmp_path):
    for literal in ("NaN", "Infinity", "-Infinity"):
        path = tmp_path / "settings.json"
        path.write_text('{"editor_font": {"family": "A", "size": %s}}' % literal, encoding="utf-8")
        assert settings.load(path)["editor_font"] == {"family": "A", "size": 11}


def test_load_editor_font_unknown_keys_dropped(tmp_path):
    assert _font(tmp_path, {"family": "A", "size": 10, "bold": True}) == {"family": "A", "size": 10}


def test_load_recent_files_must_be_a_list(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"recent_files": "a.md"}', encoding="utf-8")
    assert settings.load(path)["recent_files"] == []


def test_load_recent_files_drops_non_strings_empties_and_duplicates(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"recent_files": ["a.md", 5, "", null, "b.md", "a.md"]}', encoding="utf-8")
    assert settings.load(path)["recent_files"] == ["a.md", "b.md"]


def test_load_recent_files_capped(tmp_path):
    path = tmp_path / "settings.json"
    names = [f"f{i}.md" for i in range(settings.MAX_RECENT + 5)]
    path.write_text(json.dumps({"recent_files": names}), encoding="utf-8")
    assert settings.load(path)["recent_files"] == names[: settings.MAX_RECENT]


def test_add_recent_puts_newest_first():
    assert settings.add_recent(["b.md", "c.md"], "a.md") == ["a.md", "b.md", "c.md"]


def test_add_recent_moves_existing_entry_to_front():
    assert settings.add_recent(["a.md", "b.md", "c.md"], "c.md") == ["c.md", "a.md", "b.md"]


def test_add_recent_dedupes_case_insensitively_on_windows(monkeypatch):
    monkeypatch.setattr(settings.os.path, "normcase", str.lower)  # what ntpath does
    assert settings.add_recent(["C:/Docs/A.md", "b.md"], "c:/docs/a.md") == ["c:/docs/a.md", "b.md"]


def test_add_recent_caps_the_list():
    recent = [f"f{i}.md" for i in range(settings.MAX_RECENT)]
    result = settings.add_recent(recent, "new.md")
    assert len(result) == settings.MAX_RECENT
    assert result[0] == "new.md"
    assert recent[-1] not in result


def test_add_recent_does_not_mutate_its_input():
    recent = ["a.md"]
    settings.add_recent(recent, "b.md")
    assert recent == ["a.md"]
