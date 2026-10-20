"""Leading YAML front matter (spec 6.6): split it off byte-exact, join it back unchanged.

Input is the editor buffer: BOM already stripped, newlines already "\\n".
"""

_OPENER = "---\n"
_CLOSERS = ("---", "...")


def split(text: str) -> tuple[str | None, str]:
    """(front, body) when text starts with a front-matter block, else (None, text).

    The block opens with a "---" line at offset 0 and ends at the next line that is
    exactly "---" or "..."; at least one line in between must be non-blank. `front`
    runs through the closing line and its newline, so join(*split(text)) == text.
    """
    if not text.startswith(_OPENER):
        return None, text
    has_content = False
    pos = len(_OPENER)
    while pos < len(text):
        newline = text.find("\n", pos)
        end = len(text) if newline == -1 else newline
        line = text[pos:end]
        if line in _CLOSERS:
            if not has_content:
                return None, text
            cut = len(text) if newline == -1 else newline + 1
            return text[:cut], text[cut:]
        has_content = has_content or line.strip() != ""
        pos = end + 1
    return None, text


def join(front: str | None, body: str) -> str:
    """Inverse of split: the front-matter block (if any) followed by the body."""
    return (front or "") + body
