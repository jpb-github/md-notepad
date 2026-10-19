import pytest

from mdviewer.core.encoding import detect, encode


def test_utf8_bom():
    text, name = detect("héllo".encode("utf-8-sig"))
    assert text == "héllo"
    assert name == "utf-8-sig"


def test_plain_utf8():
    text, name = detect("héllo wörld".encode("utf-8"))
    assert text == "héllo wörld"
    assert name == "utf-8"


def test_utf16_le_bom():
    text, name = detect(b"\xff\xfe" + "abc".encode("utf-16-le"))
    assert text == "abc"
    assert name == "utf-16"


def test_utf16_be_bom():
    text, name = detect(b"\xfe\xff" + "abc".encode("utf-16-be"))
    assert text == "abc"
    assert name == "utf-16"


def test_windows_1252_fallback():
    # 0xE9 and 0x93/0x94 are invalid UTF-8 but valid Windows-1252
    raw = b"caf\xe9 \x93quotes\x94"
    text, name = detect(raw)
    assert text == "café \u201cquotes\u201d"
    assert name == "windows-1252"


def test_empty_bytes():
    assert detect(b"") == ("", "utf-8")


def test_encode_utf8():
    assert encode("héllo", "utf-8") == "héllo".encode("utf-8")


def test_encode_utf8_sig_preserves_bom():
    assert encode("héllo", "utf-8-sig") == "héllo".encode("utf-8-sig")


def test_encode_utf16_has_bom():
    raw = encode("abc", "utf-16")
    assert raw.startswith((b"\xff\xfe", b"\xfe\xff"))
    assert raw.decode("utf-16") == "abc"


def test_encode_windows_1252():
    assert encode("café", "windows-1252") == b"caf\xe9"


def test_encode_unrepresentable_raises():
    with pytest.raises(UnicodeEncodeError):
        encode("日本語", "windows-1252")


def test_windows_1252_undefined_bytes_do_not_raise():
    # 0x81, 0x8D, 0x8F, 0x90, 0x9D are unassigned in Python's cp1252 codec;
    # Windows maps them to the matching C1 control characters.
    raw = b"caf\xe9 \x81\x8d\x8f\x90\x9d"
    text, name = detect(raw)
    assert name == "windows-1252"
    assert text == "café \x81\x8d\x8f\x90\x9d"


def test_windows_1252_undefined_bytes_round_trip():
    raw = b"caf\xe9 \x81\x8d\x8f\x90\x9d"
    text, name = detect(raw)
    assert encode(text, name) == raw
