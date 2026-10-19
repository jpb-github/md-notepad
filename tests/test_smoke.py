def test_packages_import():
    import mdviewer
    import mdviewer.core

    assert mdviewer is not None
    assert mdviewer.core is not None
