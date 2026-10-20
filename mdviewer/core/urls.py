"""URL helpers shared by the preview renderer and the document model (pure, Qt-free)."""

import os
from pathlib import Path
from urllib.parse import unquote, urlsplit

# Same policy as render.py's mistune setup: script URLs and non-image data: URLs are unsafe.
_BLOCKED_PREFIXES = ("javascript:", "vbscript:", "data:")
_ALLOWED_DATA_PREFIX = "data:image/"


def resolve(url: str, base_dir: Path | None) -> str:
    """Turn a document-relative URL into an absolute file: URI; leave anything else as is."""
    if base_dir is None or not url or url.startswith(("#", "/", "\\")):
        return url
    parts = urlsplit(url)
    if len(parts.scheme) == 1:  # C:/pics/a.png - a Windows drive path
        return Path(unquote(url)).as_uri()
    if parts.scheme or parts.netloc:  # http:, mailto:, file:, ...
        return url
    target = Path(os.path.normpath(Path(base_dir).absolute() / unquote(parts.path)))
    uri = target.as_uri()
    if parts.query:
        uri += "?" + parts.query
    if parts.fragment:
        uri += "#" + parts.fragment
    return uri


def is_safe(url: str) -> bool:
    """False for javascript:, vbscript: and non-image data: URLs.

    Browsers ignore ASCII whitespace and control characters inside a scheme
    ("java\\tscript:"), so those are dropped before comparing."""
    compact = "".join(ch for ch in url if ord(ch) > 0x20).lower()
    return compact.startswith(_ALLOWED_DATA_PREFIX) or not compact.startswith(_BLOCKED_PREFIXES)
