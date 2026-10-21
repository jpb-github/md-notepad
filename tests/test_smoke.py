def test_packages_import():
    import mdviewer
    import mdviewer.core

    assert mdviewer is not None
    assert mdviewer.core is not None


def test_package_version_matches_pyproject():
    import tomllib
    from pathlib import Path

    import mdviewer

    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    assert mdviewer.__version__ == tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
