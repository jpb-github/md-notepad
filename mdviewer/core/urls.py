"""URL helpers shared by the preview renderer and the document model (pure, Qt-free)."""

import os
import re
from pathlib import Path, PureWindowsPath
from urllib.parse import unquote, urlsplit

# Same policy as render.py's mistune setup: script URLs and non-image data: URLs are unsafe.
_BLOCKED_PREFIXES = ("javascript:", "vbscript:", "data:")
_ALLOWED_DATA_PREFIX = "data:image/"
_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]+:")  # 2+ characters, so a drive letter is not one
_NOT_IN_SLUG = re.compile(r"[^\w\- ]")


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


def image_src(path: str, base_dir: Path | None) -> str:
    """The Markdown src for an image path typed or picked in the image dialog.

    URLs and relative paths stay as typed (backslashes become slashes); an absolute path becomes
    relative to the document's folder when possible, and a file: URI otherwise (Untitled, or
    another drive)."""
    path = path.strip()
    if len(path) >= 2 and path[0] == path[-1] == '"':  # Explorer's "Copy as path"
        path = path[1:-1].strip()
    if _SCHEME.match(path) or path.startswith("#"):
        return path
    if not PureWindowsPath(path).is_absolute():
        return path.replace("\\", "/")
    if base_dir is not None:
        try:
            relative = os.path.relpath(path, base_dir)
        except ValueError:  # another drive
            pass
        else:
            return relative.replace("\\", "/").replace("%", "%25").replace("#", "%23")
    return Path(path).as_uri()


def slug(text: str) -> str:
    """GitHub's heading anchor: lower case, punctuation dropped, spaces to hyphens."""
    return _NOT_IN_SLUG.sub("", text.strip().lower()).replace(" ", "-")


def anchor_block(headings: list[str | None], fragment: str) -> int | None:
    """The index of the heading a #fragment names, or None.

    headings holds each top-level block's heading text (None for other blocks). The second and later
    headings with the same slug are anchored as slug-1, slug-2, ..."""
    wanted = unquote(fragment).lower()
    seen: dict[str, int] = {}
    for index, text in enumerate(headings):
        if text is None:
            continue
        base = slug(text)
        count = seen.get(base, 0)
        seen[base] = count + 1
        if (base if count == 0 else f"{base}-{count}") == wanted:
            return index
    return None
