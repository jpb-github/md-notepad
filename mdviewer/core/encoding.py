"""BOM-aware text decoding and save-time encoding for MD Viewer."""

_BOMS = (
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe", "utf-16"),
    (b"\xfe\xff", "utf-16"),
)


def detect(raw_bytes: bytes) -> tuple[str, str]:
    """Decode file bytes to text; return (text, encoding_name)."""
    for bom, name in _BOMS:
        if raw_bytes.startswith(bom):
            return raw_bytes.decode(name), name
    try:
        return raw_bytes.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return raw_bytes.decode("windows-1252"), "windows-1252"


def encode(text: str, name: str) -> bytes:
    """Encode text with the named codec (re-adds BOM for utf-8-sig/utf-16)."""
    return text.encode(name)
