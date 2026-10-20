"""Markdown -> ProseMirror document JSON for the Rendered editor (spec 6.3, 6.4).

Parses with mistune's AST and render.py's plugin list, and returns exactly what
ProseMirror's toJSON() gives for the same document: every declared attr present
(LINE_ATTR is None below the top level), empty content and marks omitted,
adjacent text nodes with equal marks merged, marks in docschema.MARKS order.
A top-level block containing anything this module cannot map becomes a protected
html_block holding its source text, so nothing is lost. Footnote definitions
become footnote_def nodes at the end of the document, in source order.
"""

import html
import re
from bisect import bisect_left
from dataclasses import dataclass
from pathlib import Path

import mistune
from mistune.plugins import import_plugin
from mistune.util import unikey

from mdviewer.core import docschema, urls
from mdviewer.core.render import PLUGINS, highlight_code

# CommonMark entity references (the ';' is required); html.unescape decodes each match.
_ENTITY = re.compile(r"&(?:#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});")
_MARK_RANK = {name: rank for rank, name in enumerate(docschema.MARKS)}
# mistune inline token -> mark without attrs.
_SIMPLE_MARKS = {"strong": "strong", "emphasis": "em", "strikethrough": "strike"}
# mistune's block rule for "[^label]: text" (footnotes plugin) and where we keep what it matched.
_FOOTNOTE_RULE = "ref_footnote"
_FOOTNOTE_ENV = "mdviewer_footnote_defs"


class _Unmappable(Exception):
    """A token with no document node; its top-level block is kept as source."""


@dataclass
class _Footnote:
    label: str  # as written in the definition
    source: str  # the definition's text, without trailing newlines
    pos: int  # offset of the definition in the body


@dataclass
class _Context:
    base_dir: Path | None
    labels: dict[str, str]  # mistune footnote key -> label as written in its definition


# --- mistune with block start offsets -------------------------------------------
# mistune's AST has no positions. These subclasses tag each top-level token with
# "_pos", the offset where its block starts. Rules record m.start() while they run
# (a stack: the list rule may parse an interrupting block on the same state), and
# paragraphs and indented code are added while state.cursor is still at their start.
# Footnote definitions produce no token; their source is recorded in state.env.
# (mistune only recognizes them at the top level; nested ones are link definitions.)


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
            end = super().parse_method(m, state)
        finally:
            state.block_starts.pop()
        if m.lastgroup == _FOOTNOTE_RULE:
            defs = state.env.setdefault(_FOOTNOTE_ENV, {})
            key = unikey(m.group("footnote_key"))
            if key not in defs:  # mistune also keeps the first definition
                source = state.src[m.start() : end].rstrip("\n")
                defs[key] = _Footnote(m.group("footnote_key"), source, m.start())
        return end


def _parse(body: str) -> tuple[list[dict], dict[str, _Footnote]]:
    markdown = mistune.Markdown(
        renderer=None,
        block=_BlockParser(),
        inline=mistune.InlineParser(),
        plugins=[import_plugin(name) for name in PLUGINS],
    )
    tokens, state = markdown.parse(body)
    return tokens, state.env.get(_FOOTNOTE_ENV, {})


# --- public API -----------------------------------------------------------------


def from_markdown(body: str, front: str | None = None, base_dir: Path | None = None) -> dict:
    """Document JSON for `body`; `front` (from frontmatter.split) becomes a front_matter node.

    base_dir is the folder image paths resolve against (display_src); None for Untitled."""
    offset = front.count("\n") if front is not None else 0
    newlines = [m.start() for m in re.finditer("\n", body)]

    def line(pos: int) -> int:
        return offset + bisect_left(newlines, pos) + 1

    tokens, footnotes = _parse(body)
    ctx = _Context(base_dir, {key: note.label for key, note in footnotes.items()})
    note_starts = sorted(note.pos for note in footnotes.values())
    blocks: list[dict] = []
    for index, token in enumerate(tokens):
        if token["type"] in ("blank_line", "footnotes"):  # footnotes: rebuilt from the definitions
            continue
        start = token["_pos"]
        end = tokens[index + 1].get("_pos", len(body)) if index + 1 < len(tokens) else len(body)
        try:
            node = _block(ctx, token)
        except _Unmappable:
            # The slice may run into footnote definitions; those become their own nodes.
            end = next((pos for pos in note_starts if start < pos < end), end)
            source = body[start:end].rstrip("\n")
            if not source.strip():
                continue
            node = _node("html_block", {"source": source})
        node["attrs"][docschema.LINE_ATTR] = line(start)
        blocks.append(node)
    if not blocks:
        blocks.append(_node("paragraph", {docschema.LINE_ATTR: offset + 1}))
    if front is not None:
        blocks.insert(0, _node("front_matter", {"source": front, docschema.LINE_ATTR: 1}))
    for note in sorted(footnotes.values(), key=lambda note: note.pos):
        attrs = {"label": note.label, "source": note.source, docschema.LINE_ATTR: line(note.pos)}
        blocks.append(_node("footnote_def", attrs))
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


def _block(ctx: _Context, token: dict) -> dict:
    handler = _BLOCKS.get(token["type"])
    if handler is None:
        raise _Unmappable(token["type"])
    return handler(ctx, token)


def _blocks(ctx: _Context, tokens: list[dict]) -> list[dict]:
    """Child blocks without blank lines; an empty container gets one empty paragraph."""
    nodes = [_block(ctx, token) for token in tokens if token["type"] != "blank_line"]
    return nodes or [_node("paragraph")]


def _paragraph(ctx: _Context, token: dict) -> dict:
    return _node("paragraph", content=_inline(ctx, token["children"]))


def _heading(ctx: _Context, token: dict) -> dict:
    return _node("heading", {"level": token["attrs"]["level"]}, _inline(ctx, token["children"]))


def _block_quote(ctx: _Context, token: dict) -> dict:
    return _node("blockquote", content=_blocks(ctx, token["children"]))


def _thematic_break(ctx: _Context, token: dict) -> dict:
    return _node("horizontal_rule")


def _list(ctx: _Context, token: dict) -> dict:
    items = [_list_item(ctx, child) for child in token["children"]]
    if token["attrs"]["ordered"]:
        return _node("ordered_list", {"start": token["attrs"].get("start", 1), "tight": token["tight"]}, items)
    return _node("bullet_list", {"tight": token["tight"]}, items)


def _list_item(ctx: _Context, token: dict) -> dict:
    if token["type"] == "task_list_item":
        checked = token["attrs"]["checked"]
    elif token["type"] == "list_item":
        checked = None
    else:
        raise _Unmappable(token["type"])
    return _node("list_item", {"checked": checked}, _blocks(ctx, token["children"]))


def _code_block(ctx: _Context, token: dict) -> dict:
    raw = token["raw"]
    code = raw[:-1] if raw.endswith("\n") else raw  # the newline before the closing fence
    info = (token.get("attrs") or {}).get("info") or ""
    language = info.split(None, 1)[0] if info.strip() else ""
    content = [{"type": "text", "text": code}] if code else None
    return _node("code_block", {"language": language, "highlight": highlight_code(code, language)}, content)


def _table(ctx: _Context, token: dict) -> dict:
    rows: list[dict] = []
    for part in token["children"]:
        if part["type"] == "table_head":
            rows.append(_table_row(ctx, part["children"], "table_header"))
        elif part["type"] == "table_body":
            rows.extend(_table_row(ctx, row["children"], "table_cell") for row in part["children"])
        else:
            raise _Unmappable(part["type"])
    if any(len(row["content"]) != len(rows[0]["content"]) for row in rows):
        raise _Unmappable("ragged table")  # mistune never produces one; keep the source if it does
    return _node("table", content=rows)


def _table_row(ctx: _Context, cells: list[dict], kind: str) -> dict:
    content = []
    for cell in cells:
        inline = _inline(ctx, cell["children"])
        for node in inline:  # GFM: "\|" inside a code span in a table is a literal pipe
            if node["type"] == "text" and {"type": "code"} in node.get("marks", []):
                node["text"] = node["text"].replace("\\|", "|")
        content.append(_node(kind, {"align": cell["attrs"]["align"]}, inline))
    return _node("table_row", content=content)


def _html_block(ctx: _Context, token: dict) -> dict:
    return _node("html_block", {"source": token["raw"].rstrip("\n")})


_BLOCKS = {
    "paragraph": _paragraph,
    "block_text": _paragraph,  # tight list items
    "heading": _heading,
    "block_quote": _block_quote,
    "thematic_break": _thematic_break,
    "list": _list,
    "block_code": _code_block,
    "table": _table,
    "block_html": _html_block,
}


# --- inline ---------------------------------------------------------------------


def _inline(ctx: _Context, children: list[dict]) -> list[dict]:
    nodes: list[dict] = []
    _walk_inline(ctx, children, {}, nodes)
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


def _walk_inline(ctx: _Context, children: list[dict], marks: dict[str, dict | None], out: list[dict]) -> None:
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
            _walk_inline(ctx, child["children"], {**marks, _SIMPLE_MARKS[kind]: None}, out)
        elif kind == "link":
            _walk_inline(ctx, child["children"], _with_link(child["attrs"], marks), out)
        elif kind in _INLINE:
            _INLINE[kind](ctx, child, marks, out)
        else:
            raise _Unmappable(kind)


def _with_link(attrs: dict, marks: dict[str, dict | None]) -> dict[str, dict | None]:
    href = attrs["url"]
    if not urls.is_safe(href):
        return marks  # keep the text, drop the link
    title = attrs.get("title")
    return {**marks, "link": {"href": href, "title": None if title is None else _decode(title)}}


def _image(ctx: _Context, token: dict, marks: dict[str, dict | None], out: list[dict]) -> None:
    src = token["attrs"]["url"]
    alt = _plain_text(token["children"])
    if not urls.is_safe(src):
        _text(alt, marks, out)  # keep what a reader would see, drop the image
        return
    title = token["attrs"].get("title")
    attrs = {
        "src": src,
        "display_src": urls.resolve(src, ctx.base_dir),
        "alt": alt,
        "title": None if title is None else _decode(title),
    }
    out.append(_marked({"type": "image", "attrs": attrs}, marks))


def _html_inline(ctx: _Context, token: dict, marks: dict[str, dict | None], out: list[dict]) -> None:
    out.append(_marked({"type": "html_inline", "attrs": {"source": token["raw"]}}, marks))


def _footnote_ref(ctx: _Context, token: dict, marks: dict[str, dict | None], out: list[dict]) -> None:
    label = ctx.labels.get(token["raw"], token["raw"])
    out.append(_marked({"type": "footnote_ref", "attrs": {"label": label}}, marks))


# mistune inline token -> handler(ctx, token, marks, out) for tokens that become inline nodes.
_INLINE = {
    "image": _image,
    "inline_html": _html_inline,
    "footnote_ref": _footnote_ref,
}


def _plain_text(children: list[dict]) -> str:
    """Image alt text: the visible text of the inline tokens, without formatting."""
    parts = []
    for child in children:
        if child["type"] == "text":
            parts.append(_decode(child["raw"]))
        elif child["type"] in ("softbreak", "linebreak"):
            parts.append(" ")
        elif "children" in child:
            parts.append(_plain_text(child["children"]))
        else:  # codespan, inline_html, footnote_ref
            parts.append(child.get("raw", ""))
    return "".join(parts)


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
