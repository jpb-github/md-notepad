"""BOM-aware text decoding and save-time encoding for MD Viewer."""

import codecs

# Bytes unassigned in Python's cp1252 codec. Windows maps them to the matching
# C1 control characters, so the fallback decode never fails and round-trips.
_CP1252_UNDEFINED = frozenset(b"\x81\x8d\x8f\x90\x9d")
_C1_ERRORS = "mdviewer-cp1252-c1"


def _c1_passthrough(exc: UnicodeError):
    if isinstance(exc, UnicodeDecodeError):
        chunk = exc.object[exc.start:exc.end]
        if all(b in _CP1252_UNDEFINED for b in chunk):
            return "".join(map(chr, chunk)), exc.end
    elif isinstance(exc, UnicodeEncodeError):
        chunk = exc.object[exc.start:exc.end]
        if all(ord(c) in _CP1252_UNDEFINED for c in chunk):
            return bytes(map(ord, chunk)), exc.end
    raise exc


codecs.register_error(_C1_ERRORS, _c1_passthrough)

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
        return raw_bytes.decode("windows-1252", _C1_ERRORS), "windows-1252"


def encode(text: str, name: str) -> bytes:
    """Encode text with the named codec (re-adds BOM for utf-8-sig/utf-16)."""
    if name == "windows-1252":
        return text.encode(name, _C1_ERRORS)
    return text.encode(name)
