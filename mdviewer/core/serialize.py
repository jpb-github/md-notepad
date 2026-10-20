"""ProseMirror document JSON -> normalized Markdown for the Rendered editor (spec 6.5).

The inverse of core/docmodel.py: from_markdown(to_markdown(doc)) gives the same
document back, up to the normalizations of spec 6.5. Output uses "\\n" only and
ends with exactly one "\\n" ("" for an empty body); MainWindow applies the file's
newline style on save. LINE_ATTR and code_block.highlight are display-only and
ignored here.
"""

import re
import string

from mdviewer.core import frontmatter

# CommonMark entity references, as docmodel decodes them; a "&" that starts one is escaped.
_ENTITY = re.compile(r"&(?:#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});")
_ASCII_PUNCT = frozenset(string.punctuation)
# Marks whose delimiters must touch non-whitespace (CommonMark flanking rules).
_FLANKED = frozenset({"strong", "em", "strike"})
_DELIMITERS = {"strong": "**", "em": "*", "strike": "~~"}
# Links, then strike, always open outermost: their syntax has no flanking rules. Strong
# and em runs are split at every edge of a link or strike run, which never changes the
# document (equal-marked text merges back) but keeps their delimiters next to text.
_OUTER_RANK = {"link": 0, "strike": 1}

# Line starts that would begin a block: ATX heading, bullet item, ordered item.
_HEADING_START = re.compile(r"#{1,6}(?=[ \t]|$)")
_BULLET_START = re.compile(r"[-+](?=[ \t]|$)")
_ORDERED_START = re.compile(r"[0-9]{1,9}([.)])(?=[ \t]|$)")
# Whole lines that would be a setext underline, a thematic break or a table delimiter row.
_UNDERLINE = re.compile(r"[-=]+[ \t]*|[-:| \t]*-[-:| \t]*")  # mistune also takes "-=" as an underline
# Trailing "#"s of a heading's text would be read as its closing sequence.
_HEADING_CLOSE = re.compile(r"(?:^|[ \t])(#+)[ \t]*$")
# mistune's url plugin links bare http(s) URLs; it never ends one on these characters.
_BARE_URL = re.compile(r"""https?://[^\s<]+[^<.,:;"')\]\s]""")
_BARE_URL_SCHEME = re.compile(r"https?(?=://)")
_URL_TRAILING = ".,:;\"')]"
# CommonMark autolinks: <scheme:...> and <address>.
_URI_AUTOLINK = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]{1,31}:[^\s<>&\\]*")
_EMAIL_AUTOLINK = re.compile(
    r"[a-zA-Z0-9.!#$%'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*"
)


# --- public API -----------------------------------------------------------------


def to_markdown(doc: dict) -> str:
    """Normalized Markdown for the document body; "" when the body has no content.

    The front_matter node is not part of the body: see front_matter() and to_text()."""
    body = _blocks([node for node in doc.get("content", []) if node["type"] != "front_matter"])
    return body + "\n" if body else ""


def front_matter(doc: dict) -> str | None:
    """The front_matter node's source, verbatim; None when the document has none."""
    content = doc.get("content", [])
    if content and content[0]["type"] == "front_matter":
        return content[0]["attrs"]["source"]
    return None


def to_text(doc: dict) -> str:
    """The whole buffer (spec 6.4 pull): front matter verbatim, then the body.

    A front-matter block that ended the file without a newline gets one when a body follows."""
    front, body = front_matter(doc), to_markdown(doc)
    if front is not None and body and not front.endswith("\n"):
        front += "\n"
    return frontmatter.join(front, body)


# --- blocks ---------------------------------------------------------------------


def _blocks(nodes: list[dict]) -> str:
    """Blocks separated by one blank line; blocks that serialize to "" are left out."""
    return "\n\n".join(text for text in (_block(node) for node in nodes) if text)


def _block(node: dict) -> str:
    handler = _BLOCKS.get(node["type"])
    if handler is None:
        raise ValueError(f"cannot serialize a {node['type']!r} node")
    return handler(node)


def _paragraph(node: dict) -> str:
    return _inline(node.get("content", []))


def _heading(node: dict) -> str:
    text = _inline(node.get("content", []), heading=True)
    marker = "#" * node["attrs"]["level"]
    return f"{marker} {text}" if text else marker


def _blockquote(node: dict) -> str:
    inner = _blocks(node.get("content", []))
    if not inner:
        return ">"
    return "\n".join(f"> {line}" if line else ">" for line in inner.split("\n"))


def _horizontal_rule(node: dict) -> str:
    return "---"


# Node type -> serializer returning the block's lines without a trailing newline ("" = nothing).
_BLOCKS = {
    "paragraph": _paragraph,
    "heading": _heading,
    "blockquote": _blockquote,
    "horizontal_rule": _horizontal_rule,
}


# --- inline: normalization ------------------------------------------------------


def _inline(nodes: list[dict], heading: bool = False) -> str:
    """Markdown for the inline content of a paragraph or heading."""
    return _escape_pieces(_pieces(_normalize(nodes, heading)), heading)


def _marks(node: dict) -> list[dict]:
    return node.get("marks", [])


def _has_mark(node: dict, name: str) -> bool:
    return any(mark["type"] == name for mark in _marks(node))


def _text_node(text: str, marks: list[dict]) -> dict:
    node: dict = {"type": "text", "text": text}
    if marks:
        node["marks"] = marks
    return node


def _normalize(nodes: list[dict], heading: bool) -> list[dict]:
    """The inline nodes as Markdown can express them.

    Newlines in text and hard breaks in headings become spaces; spaces and tabs at
    line edges are dropped (Markdown strips them); trailing hard breaks are dropped
    (a block cannot end with one); whitespace moves out of strong/em/strike runs
    (their delimiters must touch non-whitespace); equal-marked text is merged."""
    flat: list[dict] = []
    for node in nodes:
        if node["type"] == "text":
            flat.append(_text_node(node["text"].replace("\n", " "), _marks(node)))
        elif node["type"] == "hard_break" and heading:
            flat.append(_text_node(" ", _marks(node)))
        else:
            flat.append(node)
    lines: list[list[dict]] = [[]]
    for node in flat:
        if node["type"] == "hard_break":
            lines.append([])
        lines[-1].append(node)
    out: list[dict] = []
    for line in lines:
        out.extend(_strip_line(line))
    while out and out[-1]["type"] == "hard_break":
        out.pop()
    return _merge(_expel_whitespace(out))


def _strip_line(line: list[dict]) -> list[dict]:
    """Drop spaces and tabs at both edges of one line (which may start with its hard_break)."""
    nodes = list(line)
    _strip_edge(nodes, range(len(nodes)), str.lstrip)
    _strip_edge(nodes, range(len(nodes) - 1, -1, -1), str.rstrip)
    return [node for node in nodes if node["type"] != "text" or node["text"]]


def _strip_edge(nodes: list[dict], order: range, strip) -> None:
    for i in order:
        node = nodes[i]
        if node["type"] == "hard_break":
            continue
        if node["type"] != "text" or _has_mark(node, "code"):
            return
        nodes[i] = _text_node(strip(node["text"], " \t"), _marks(node))
        if nodes[i]["text"]:
            return


def _shared(marks: list[dict], *neighbors: list[dict]) -> list[dict]:
    """`marks` without the strong/em/strike marks that some neighbor lacks."""
    return [mark for mark in marks if mark["type"] not in _FLANKED or all(mark in other for other in neighbors)]


def _expel_whitespace(nodes: list[dict]) -> list[dict]:
    """Move leading/trailing whitespace of strong/em/strike runs outside the run.

    Runs also end at the edges of links and strike runs, where _pieces closes them."""
    out: list[dict] = []
    for i, node in enumerate(nodes):
        before = _marks(nodes[i - 1]) if i > 0 and not _edge(nodes[i - 1], node) else []
        after = _marks(nodes[i + 1]) if i + 1 < len(nodes) and not _edge(node, nodes[i + 1]) else []
        if node["type"] == "hard_break":  # whitespace too: inside a run only between its parts
            marks = _shared(_marks(node), before, after)
            out.append({"type": "hard_break", "marks": marks} if marks else {"type": "hard_break"})
            continue
        if node["type"] != "text" or _has_mark(node, "code"):
            out.append(node)
            continue
        text, marks = node["text"], _marks(node)
        core = text.strip()
        if not core:
            out.append(_text_node(text, _shared(marks, before, after)))
            continue
        start, end = len(text) - len(text.lstrip()), len(text.rstrip())
        out.append(_text_node(text[:start], _shared(marks, before)))
        out.append(_text_node(core, marks))
        out.append(_text_node(text[end:], _shared(marks, after)))
    return [node for node in out if node["type"] != "text" or node["text"]]


def _merge(nodes: list[dict]) -> list[dict]:
    merged: list[dict] = []
    for node in nodes:
        previous = merged[-1] if merged else None
        if previous and previous["type"] == node["type"] == "text" and _marks(previous) == _marks(node):
            merged[-1] = _text_node(previous["text"] + node["text"], _marks(node))
        else:
            merged.append(node)
    return merged


# --- inline: marks and pieces ---------------------------------------------------
# Inline content becomes a list of pieces: (document text, inside-link flag) or
# (markup, None) for delimiters, code spans, link syntax and hard breaks. Text is
# escaped afterwards, when the output characters around each text piece are known.


def _pieces(nodes: list[dict]) -> list[tuple[str, bool | None]]:
    pieces: list[tuple[str, bool | None]] = []
    stack: list[dict] = []  # open marks, outermost first
    for i, node in enumerate(nodes):
        wanted = [mark for mark in _marks(node) if mark["type"] != "code"]
        keep = 0
        if i == 0 or not _edge(nodes[i - 1], node):  # at a link or strike edge all marks close
            while keep < len(stack) and stack[keep] in wanted:
                keep += 1
        for mark in reversed(stack[keep:]):
            pieces.append((_close(mark), None))
        del stack[keep:]
        if autolink := _autolink(nodes, i):
            pieces.append((autolink, None))
            continue
        # Link, then strike; then longer strong/em runs outside shorter ones, strong first on ties.
        opening = [mark for mark in wanted if mark not in stack]
        opening.sort(key=lambda m: (_OUTER_RANK.get(m["type"], 2), -_extent(nodes, i, m), m["type"] != "strong"))
        for mark in opening:
            pieces.append((_DELIMITERS.get(mark["type"], "["), None))
            stack.append(mark)
        pieces.append(_content(node, in_link=_link(node) is not None))
    for mark in reversed(stack):
        pieces.append((_close(mark), None))
    return pieces


def _link(node: dict) -> dict | None:
    return next((mark for mark in _marks(node) if mark["type"] == "link"), None)


def _edge(left: dict, right: dict) -> bool:
    """A link or strike run starts or ends between two adjacent nodes."""
    return _link(left) != _link(right) or _has_mark(left, "strike") != _has_mark(right, "strike")


def _extent(nodes: list[dict], index: int, mark: dict) -> int:
    """How many nodes from `index` on carry `mark`; strong/em runs stop at link and strike edges."""
    count = 1
    while index + count < len(nodes) and mark in _marks(nodes[index + count]):
        if mark["type"] not in _OUTER_RANK and _edge(nodes[index + count - 1], nodes[index + count]):
            break
        count += 1
    return count


def _content(node: dict, in_link: bool) -> tuple[str, bool | None]:
    if node["type"] == "text":
        if _has_mark(node, "code"):
            return _code_span(node["text"]), None
        return node["text"], in_link
    if node["type"] == "hard_break":
        return "\\\n", None
    raise ValueError(f"cannot serialize a {node['type']!r} node")


def _close(mark: dict) -> str:
    if mark["type"] == "link":
        return "](" + _link_target(mark["attrs"]["href"], mark["attrs"]["title"]) + ")"
    return _DELIMITERS[mark["type"]]


def _autolink(nodes: list[dict], index: int) -> str | None:
    """The node written as an autolink (spec 6.5), or None for a [text](href) link.

    Only an untitled link that is the node's only mark and covers just this node
    qualifies. An http(s) URL whose text is its href stays bare when nothing that
    follows could be read as part of the URL; otherwise it becomes <href>. A mailto:
    link whose text is the address becomes <address>."""
    node = nodes[index]
    link = _link(node)
    if node["type"] != "text" or _marks(node) != [link] or link["attrs"]["title"] is not None:
        return None
    if _extent(nodes, index, link) != 1 or (index > 0 and link in _marks(nodes[index - 1])):
        return None
    text, href = node["text"], link["attrs"]["href"]
    if text == href and _BARE_URL.fullmatch(text) and _bare_url_ends(nodes, index) and not set("&\\") & set(text):
        return text
    if text == href and _URI_AUTOLINK.fullmatch(href):
        return f"<{href}>"
    if href == "mailto:" + text and _EMAIL_AUTOLINK.fullmatch(text):
        return f"<{text}>"
    return None


def _bare_url_ends(nodes: list[dict], index: int) -> bool:
    """Nothing after nodes[index] extends a bare URL: a line end, or (closing punctuation and) whitespace."""
    following = nodes[index + 1] if index + 1 < len(nodes) else None
    if following is None:
        return True
    if following["type"] != "text" or _marks(following):  # also a hard break: the URL would take its "\"
        return False
    rest = following["text"].lstrip(_URL_TRAILING)
    if rest:
        return rest[0].isspace()
    return index + 2 == len(nodes)


def _code_span(code: str) -> str:
    """A backtick run longer than any inside; padded where CommonMark would strip or merge."""
    fence = "`" * (max((len(run) for run in re.findall("`+", code)), default=0) + 1)
    pad = code[0] == "`" or code[-1] == "`" or (code[0] == code[-1] == " " and code.strip(" ") != "")
    return f"{fence} {code} {fence}" if pad else f"{fence}{code}{fence}"


def _link_target(href: str, title: str | None) -> str:
    """The inside of a link's parentheses: destination, then an optional "title"."""
    href = _escape_entities(href)
    if any(ch.isspace() or ord(ch) < 0x20 or ch in "<>" for ch in href):
        target = "<" + re.sub(r"([<>\\])", r"\\\1", href) + ">"
    else:
        target = _escape_backslashes(href)
        if not _parens_balanced(target):
            target = re.sub(r"(?<!\\)([()])", r"\\\1", target)
    if title is None:
        return target
    return target + ' "' + _escape_backslashes(_escape_entities(title)).replace('"', '\\"') + '"'


def _escape_entities(value: str) -> str:
    """Keep a literal "&name;" from being decoded by writing its "&" as "&amp;"."""
    return _ENTITY.sub(lambda m: "&amp;" + m.group()[1:], value)


def _escape_backslashes(value: str) -> str:
    """Double each backslash that would otherwise escape the character after it."""
    return re.sub(r"\\(?=[" + re.escape(string.punctuation) + r"]|$)", r"\\\\", value)


def _parens_balanced(value: str) -> bool:
    depth = 0
    for i, ch in enumerate(value):
        if ch in "()" and i > 0 and value[i - 1] == "\\":
            continue
        depth += {"(": 1, ")": -1}.get(ch, 0)
        if depth < 0:
            return False
    return depth == 0


# --- inline: escaping -----------------------------------------------------------


def _escape_pieces(pieces: list[tuple[str, bool | None]], heading: bool) -> str:
    out: list[str] = []
    for i, (value, in_link) in enumerate(pieces):
        if in_link is None:
            out.append(value)
            continue
        before = out[-1][-1:] if out else ""
        after = pieces[i + 1][0][:1] if i + 1 < len(pieces) else ""
        line_start = before in ("", "\n")
        line_end = i + 1 == len(pieces) or pieces[i + 1][0] == "\\\n"
        out.append(_escape(value, before, after, in_link, line_start, line_end, heading))
    return "".join(out)


def _escape(
    text: str, before: str, after: str, in_link: bool, line_start: bool, line_end: bool, heading: bool
) -> str:
    """Backslash-escape what Markdown would read as syntax in `text`, and nothing else.

    `before`/`after` are the output characters around the text ("" at a block edge,
    "\\n" after a hard break); line_start/line_end say whether the text starts/ends a line."""
    escaped: set[int] = set()
    # mistune links bare http(s) URLs anywhere; inside link text one swallows the markup up to "]".
    escaped |= {match.end() for match in _BARE_URL_SCHEME.finditer(text)}
    if line_start and not heading:
        escaped |= _line_start_escapes(text, line_end)
    if heading and after == "" and (match := _HEADING_CLOSE.search(text)):
        escaped.add(match.start(1))
    for i, ch in enumerate(text):
        prev = text[i - 1] if i > 0 else before
        nxt = text[i + 1] if i + 1 < len(text) else after
        if (
            ch in "*`["
            or (ch == "]" and in_link)
            or (ch == "\\" and nxt in _ASCII_PUNCT)  # a hard break's "\" counts: it follows
            or (ch == "_" and not (prev.isalnum() and nxt.isalnum()))
            or (ch == "~" and "~" in (prev, nxt))
            or (ch == "!" and nxt == "[")
            or (ch == "<" and ((nxt.isascii() and nxt.isalpha()) or nxt in ("/", "!", "?")))
            or (ch == "&" and _ENTITY.match(text, i))
        ):
            escaped.add(i)
    out = ["\\" + ch if i in escaped else ch for i, ch in enumerate(text)]
    if before == "\n" and text[0].isspace():  # mistune drops any whitespace after a hard break
        out[0] = "&nbsp;" if text[0] == "\xa0" else f"&#{ord(text[0])};"
    return "".join(out)


def _line_start_escapes(text: str, line_end: bool) -> set[int]:
    """Positions to escape so that a line starting with `text` stays paragraph text."""
    if line_end and _UNDERLINE.fullmatch(text):
        return {min(i for i, ch in enumerate(text) if ch in "-=")}
    probe = text if line_end else text + "x"  # markup (non-blank) follows the text
    if text[:1] == ">" or _HEADING_START.match(probe) or _BULLET_START.match(probe):
        return {0}
    if match := _ORDERED_START.match(probe):
        return {match.start(1)}
    return set()
