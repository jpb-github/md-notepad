"""Markdown -> ProseMirror document JSON for the Rendered editor (spec 6.3, 6.4).

Parses with mistune's AST and render.py's plugin list, and returns exactly what
ProseMirror's toJSON() gives for the same document: every declared attr present
(LINE_ATTR is None below the top level), empty content and marks omitted,
adjacent text nodes with equal marks merged, marks in docschema.MARKS order.
A top-level block containing anything this module cannot map becomes a protected
html_block holding its source text, so nothing is lost.
"""

import html
import re
from bisect import bisect_left
from pathlib import Path

import mistune
from mistune.plugins import import_plugin

from mdviewer.core import docschema, urls
from mdviewer.core.render import PLUGINS

# CommonMark entity references (the ';' is required); html.unescape decodes each match.
_ENTITY = re.compile(r"&(?:#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});")
_MARK_RANK = {name: rank for rank, name in enumerate(docschema.MARKS)}
# mistune inline token -> mark without attrs.
_SIMPLE_MARKS = {"strong": "strong", "emphasis": "em", "strikethrough": "strike"}


class _Unmappable(Exception):
    """A token with no document node; its top-level block is kept as source."""


# --- mistune with block start offsets -------------------------------------------
# mistune's AST has no positions. These subclasses tag each top-level token with
# "_pos", the offset where its block starts. Rules record m.start() while they run
# (a stack: the list rule may parse an interrupting block on the same state), and
# paragraphs and indented code are added while state.cursor is still at their start.


class _Tokens(list):
    def __init__(self, state: "_State"):
        super().__init__()
        self._state = state

    def _tag(self, token: dict) -> None:
        starts = self._state.block_starts
        token.setdefault("_pos", starts[-1] if starts else self._state.cursor)

    def append(self, token: dict) -> None:
        self._tag(token)
        super().append(token)

    def insert(self, index: int, token: dict) -> None:
        self._tag(token)
        super().insert(index, token)


class _State(mistune.BlockState):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.block_starts: list[int] = []
        if parent is None:
            self.tokens = _Tokens(self)


class _BlockParser(mistune.BlockParser):
    state_cls = _State

    def parse_method(self, m, state):
        if state.parent is not None:
            return super().parse_method(m, state)
        state.block_starts.append(m.start())
        try:
            return super().parse_method(m, state)
        finally:
            state.block_starts.pop()


def _parse(body: str) -> list[dict]:
    markdown = mistune.Markdown(
        renderer=None,
        block=_BlockParser(),
        inline=mistune.InlineParser(),
        plugins=[import_plugin(name) for name in PLUGINS],
    )
    return markdown(body)


# --- public API -----------------------------------------------------------------


def from_markdown(body: str, front: str | None = None, base_dir: Path | None = None) -> dict:
    """Document JSON for `body`; `front` (from frontmatter.split) becomes a front_matter node.

    base_dir is the folder image paths resolve against (display_src); None for Untitled."""
    offset = front.count("\n") if front is not None else 0
    newlines = [m.start() for m in re.finditer("\n", body)]
    blocks: list[dict] = []
    if front is not None:
        blocks.append(_node("front_matter", {"source": front, docschema.LINE_ATTR: 1}))
    tokens = _parse(body)
    for index, token in enumerate(tokens):
        if token["type"] == "blank_line":
            continue
        start = token.get("_pos", len(body))  # the footnotes token is added after parsing
        end = tokens[index + 1].get("_pos", len(body)) if index + 1 < len(tokens) else len(body)
        try:
            node = _block(token)
        except _Unmappable:
            source = body[start:end].rstrip("\n")
            if not source.strip():
                continue
            node = _node("html_block", {"source": source})
        node["attrs"][docschema.LINE_ATTR] = offset + bisect_left(newlines, start) + 1
        blocks.append(node)
    if not any(block["type"] != "front_matter" for block in blocks):
        blocks.append(_node("paragraph", {docschema.LINE_ATTR: offset + 1}))
    return {"type": "doc", "content": blocks}


# --- blocks ---------------------------------------------------------------------


def _node(kind: str, attrs: dict | None = None, content: list | None = None) -> dict:
    """A node shaped like ProseMirror's toJSON(): all attrs, no empty content."""
    full = dict(attrs or {})
    if kind in docschema.TOP_LEVEL_NODES:
        full.setdefault(docschema.LINE_ATTR, None)
    node: dict = {"type": kind}
    if full:
        node["attrs"] = full
    if content:
        node["content"] = content
    return node


def _block(token: dict) -> dict:
    handler = _BLOCKS.get(token["type"])
    if handler is None:
        raise _Unmappable(token["type"])
    return handler(token)


def _blocks(tokens: list[dict]) -> list[dict]:
    """Child blocks without blank lines; an empty container gets one empty paragraph."""
    nodes = [_block(token) for token in tokens if token["type"] != "blank_line"]
    return nodes or [_node("paragraph")]


def _paragraph(token: dict) -> dict:
    return _node("paragraph", content=_inline(token["children"]))


def _heading(token: dict) -> dict:
    return _node("heading", {"level": token["attrs"]["level"]}, _inline(token["children"]))


def _block_quote(token: dict) -> dict:
    return _node("blockquote", content=_blocks(token["children"]))


def _thematic_break(token: dict) -> dict:
    return _node("horizontal_rule")


_BLOCKS = {
    "paragraph": _paragraph,
    "heading": _heading,
    "block_quote": _block_quote,
    "thematic_break": _thematic_break,
}


# --- inline ---------------------------------------------------------------------


def _inline(children: list[dict]) -> list[dict]:
    nodes: list[dict] = []
    _walk_inline(children, {}, nodes)
    merged: list[dict] = []
    for node in nodes:
        previous = merged[-1] if merged else None
        if (
            previous is not None
            and previous["type"] == node["type"] == "text"
            and previous.get("marks") == node.get("marks")
        ):
            previous["text"] += node["text"]
        else:
            merged.append(node)
    return merged


def _walk_inline(children: list[dict], marks: dict[str, dict | None], out: list[dict]) -> None:
    """Append inline nodes to `out`; `marks` maps each active mark name to its attrs (or None)."""
    for child in children:
        kind = child["type"]
        if kind == "text":
            _text(_decode(child["raw"]), marks, out)
        elif kind == "softbreak":
            _text(" ", marks, out)
        elif kind == "linebreak":
            out.append(_marked({"type": "hard_break"}, marks))
        elif kind == "codespan":
            _text(child["raw"], {**marks, "code": None}, out)
        elif kind in _SIMPLE_MARKS:
            _walk_inline(child["children"], {**marks, _SIMPLE_MARKS[kind]: None}, out)
        elif kind == "link":
            _walk_inline(child["children"], _with_link(child["attrs"], marks), out)
        else:
            raise _Unmappable(kind)


def _with_link(attrs: dict, marks: dict[str, dict | None]) -> dict[str, dict | None]:
    href = attrs["url"]
    if not urls.is_safe(href):
        return marks  # keep the text, drop the link
    title = attrs.get("title")
    return {**marks, "link": {"href": href, "title": None if title is None else _decode(title)}}


def _text(text: str, marks: dict[str, dict | None], out: list[dict]) -> None:
    if text:
        out.append(_marked({"type": "text", "text": text}, marks))


def _marked(node: dict, marks: dict[str, dict | None]) -> dict:
    if marks:
        node["marks"] = [
            {"type": name} if attrs is None else {"type": name, "attrs": dict(attrs)}
            for name, attrs in sorted(marks.items(), key=lambda item: _MARK_RANK[item[0]])
        ]
    return node


def _decode(raw: str) -> str:
    return _ENTITY.sub(lambda m: html.unescape(m.group()), raw)
