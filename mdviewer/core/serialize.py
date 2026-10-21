"""ProseMirror document JSON -> normalized Markdown for the Rendered editor (spec 6.5).

The inverse of core/docmodel.py: from_markdown(to_markdown(doc)) gives the same
document back, up to the normalizations of spec 6.5. Output uses "\\n" only and
ends with exactly one "\\n" ("" for an empty body); MainWindow applies the file's
newline style on save. LINE_ATTR, code_block.highlight and image.display_src are
display-only and ignored here.
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

_LISTS = frozenset({"bullet_list", "ordered_list"})
# A list directly after a list of the same kind uses the second marker, or the two would merge.
_BULLETS = ("-", "*")
_ORDERED_DELIMITERS = (".", ")")
# Blocks that end on their own line: anything may follow on the next line.
_CLOSED_BLOCKS = frozenset({"heading", "code_block", "horizontal_rule"})
# Blocks whose last line could take the next line in as a lazy paragraph continuation.
_OPEN_BLOCKS = frozenset({"paragraph", "blockquote", "bullet_list", "ordered_list"})
# Item markers with no text after them can add up to a thematic break: "- - -", "* * *".
_THEMATIC_BREAK = re.compile(r"(?:-[ \t]*){3,}|(?:\*[ \t]*){3,}")
_ALIGN_ROW = {None: "---", "left": ":---", "center": ":---:", "right": "---:"}
# A "|" after an even number of backslashes (none included) splits a table cell.
_UNESCAPED_PIPE = re.compile(r"(?<!\\)((?:\\\\)*)\|")


# --- public API -----------------------------------------------------------------


def to_markdown(doc: dict) -> str:
    """Normalized Markdown for the document body; "" when the body has no content.

    The front_matter node is not part of the body: see front_matter() and to_text().
    Footnote definitions are written last, in document order."""
    content = [node for node in doc.get("content", []) if node["type"] != "front_matter"]
    notes = [node for node in content if node["type"] == "footnote_def"]
    body = _blocks([node for node in content if node["type"] != "footnote_def"] + notes)
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
    if front is None and frontmatter.split(body)[0] is not None:
        body = "***" + body[3:]  # a leading rule plus a later "---" would read back as front matter
    return frontmatter.join(front, body)


# --- blocks ---------------------------------------------------------------------


def _blocks(nodes: list[dict]) -> str:
    """Blocks separated by one blank line; blocks that serialize to "" are left out."""
    return _join(_parts(nodes), tight=False)


def _parts(nodes: list[dict]) -> list[tuple[dict, str]]:
    """(node, Markdown) for each block that serializes to something.

    A list right after a list of the same kind switches markers, or the two would merge."""
    parts: list[tuple[dict, str]] = []
    alternate = False
    for node in nodes:
        if node["type"] in _LISTS:
            previous = parts[-1][0] if parts else None
            alternate = previous is not None and previous["type"] == node["type"] and not alternate
            text = _list(node, alternate)
        else:
            text = _block(node)
        if text:
            parts.append((node, text))
    return parts


def _join(parts: list[tuple[dict, str]], tight: bool) -> str:
    """The blocks one blank line apart, or one line apart in a tight list item (see _joins)."""
    out: list[str] = []
    for index, (node, text) in enumerate(parts):
        if index:
            out.append("\n" if tight else "\n\n")
            if tight and text == "---":  # right under a line of text, "---" would underline it
                text = "___"
        out.append(text)
    return "".join(out)


def _tight_item(parts: list[tuple[dict, str]]) -> bool:
    """The item's blocks can be written line by line and mistune reads them back as tight.

    mistune reads an item with two paragraphs as loose, wherever they are."""
    if sum(node["type"] == "paragraph" for node, _ in parts) > 1:
        return False
    return all(_joins(parts[index - 1][0], node, text) for index, (node, text) in enumerate(parts) if index)


def _reads_loose(items: list[list[tuple[dict, str]]]) -> bool:
    """mistune reads the list back as loose when its items and blocks are a blank line apart.

    It sees a blank line between items, and one between an item's blocks unless the
    blank line follows a nested list (which takes it in without becoming loose)."""
    if len(items) > 1:
        return True
    return any(
        sum(node["type"] == "paragraph" for node, _ in parts) > 1
        or any(parts[index - 1][0]["type"] not in _LISTS for index in range(1, len(parts)))
        for parts in items
    )


def _joins(previous: dict, node: dict, text: str) -> bool:
    """True when `node`, written as `text`, may start on the line right after `previous`."""
    if previous["type"] in _CLOSED_BLOCKS:
        return True
    if previous["type"] not in _OPEN_BLOCKS:  # tables and HTML blocks run on to a blank line
        return False
    if previous["type"] == "blockquote":
        # mistune keeps a heading or HTML block in the quote, merges two quotes, and moves a
        # list that follows a quote in front of it once a later block interrupts the list.
        return node["type"] in ("code_block", "horizontal_rule")
    # The next line must interrupt a paragraph, or it would continue the previous block.
    if node["type"] in ("heading", "code_block", "blockquote", "horizontal_rule"):
        return True
    if node["type"] == "bullet_list" or (node["type"] == "ordered_list" and node["attrs"]["start"] == 1):
        return " " in text.split("\n", 1)[0]  # an empty first item cannot interrupt ("-" underlines)
    return False


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


def _list(node: dict, alternate: bool = False) -> str:
    """Items with `-` or `1.`, `2.`, ... from `start`; one line apart when tight, a blank line when loose.

    The list is written tight or loose as mistune will read it back: a tight list is
    written loose when some item cannot be tight (_tight_item), and a loose list is
    written tight when mistune would not see its blank lines (_reads_loose)."""
    items = [_item_parts(item) for item in node["content"]]
    tight = all(_tight_item(parts) for parts in items) and (node["attrs"]["tight"] or not _reads_loose(items))
    lines = []
    for index, parts in enumerate(items):
        if node["type"] == "ordered_list":
            marker = f"{node['attrs']['start'] + index}{_ORDERED_DELIMITERS[alternate]}"
        else:
            marker = _BULLETS[alternate]
        lines.append(_list_item(_join(parts, tight), marker))
    return ("\n" if tight else "\n\n").join(lines)


# A task box with no text reads back as an empty first paragraph (docmodel: "- [ ]" + a block).
_BOX_LINE = {"type": "paragraph"}


def _item_parts(node: dict) -> list[tuple[dict, str]]:
    """The item's blocks; a task item's box opens its first paragraph, or stands on its own line."""
    parts = _parts(node.get("content", []))
    checked = node["attrs"]["checked"]
    if checked is None:
        return parts
    box = "[x]" if checked else "[ ]"
    if parts and parts[0][0]["type"] == "paragraph":
        return [(parts[0][0], f"{box} {parts[0][1]}"), *parts[1:]]
    return [(_BOX_LINE, box), *parts]


def _list_item(inner: str, marker: str) -> str:
    """The marker, then the item's Markdown indented to its content column."""
    if not inner:
        return marker
    lines = inner.split("\n")
    if lines[0] == "---":  # "- ---" would be one thematic break, not an item holding a rule
        lines[0] = "___"
    indent = " " * (len(marker) + 1)
    if _THEMATIC_BREAK.fullmatch(f"{marker} {lines[0]}"):  # "- - -": nested items with no text
        return "\n".join([marker] + [indent + line if line else "" for line in lines])
    return "\n".join([f"{marker} {lines[0]}"] + [indent + line if line else "" for line in lines[1:]])


def _code_block(node: dict) -> str:
    """A fence longer than any run of its character in the code; only the language's first word."""
    code = "".join(child["text"] for child in node.get("content", []))
    words = node["attrs"]["language"].split()
    language = _escape_backslashes(words[0]) if words else ""  # the info string takes backslash escapes
    char = "~" if "`" in language else "`"  # a backtick fence's info string cannot hold a backtick
    longest = max((len(run) for run in re.findall(re.escape(char) + "+", code)), default=0)
    fence = char * max(3, longest + 1)
    return f"{fence}{language}\n{code}\n{fence}" if code else f"{fence}{language}\n{fence}"


def _table(node: dict) -> str:
    """A pipe table: the first row is the header, its cells' align attrs give the delimiter row.

    Short rows are padded with empty cells: mistune reads a table whose rows differ in width
    as a paragraph."""
    rows = [[_cell(cell) for cell in row.get("content", [])] for row in node["content"]]
    width = max(len(row) for row in rows)
    aligns = [cell["attrs"]["align"] for cell in node["content"][0].get("content", [])]
    aligns += [None] * (width - len(aligns))
    lines = [rows[0], [_ALIGN_ROW[align] for align in aligns], *rows[1:]]
    return "\n".join("| " + " | ".join(cells + [""] * (width - len(cells))) + " |" for cells in lines)


def _cell(node: dict) -> str:
    """One line of inline Markdown with every unescaped "|" escaped, code spans included.

    docmodel turns "\\|" inside a code span in a cell back into "|" (GFM)."""
    return _UNESCAPED_PIPE.sub(r"\1\\|", _inline(node.get("content", []), cell=True))


def _source(node: dict) -> str:
    return node["attrs"]["source"]


# Node type -> serializer returning the block's lines without a trailing newline ("" = nothing).
_BLOCKS = {
    "paragraph": _paragraph,
    "heading": _heading,
    "blockquote": _blockquote,
    "horizontal_rule": _horizontal_rule,
    "bullet_list": _list,
    "ordered_list": _list,
    "code_block": _code_block,
    "table": _table,
    "html_block": _source,
    "footnote_def": _source,
}


# --- inline: normalization ------------------------------------------------------


def _inline(nodes: list[dict], heading: bool = False, cell: bool = False) -> str:
    """Markdown for the inline content of a paragraph, heading or table cell."""
    return _escape_pieces(_pieces(_normalize(nodes, one_line=heading or cell), cell), heading, cell)


def _marks(node: dict) -> list[dict]:
    return node.get("marks", [])


def _has_mark(node: dict, name: str) -> bool:
    return any(mark["type"] == name for mark in _marks(node))


def _text_node(text: str, marks: list[dict]) -> dict:
    node: dict = {"type": "text", "text": text}
    if marks:
        node["marks"] = marks
    return node


def _normalize(nodes: list[dict], one_line: bool) -> list[dict]:
    """The inline nodes as Markdown can express them.

    Newlines in text become spaces, and in headings and table cells (`one_line`) so do
    hard breaks and newlines in inline HTML; spaces and tabs at line edges are dropped
    (Markdown strips them); trailing hard breaks are dropped (a block cannot end with
    one); whitespace moves out of strong/em/strike runs (their delimiters must touch
    non-whitespace); equal-marked text is merged."""
    flat: list[dict] = []
    for node in nodes:
        if node["type"] == "text":
            flat.append(_text_node(node["text"].replace("\n", " "), _marks(node)))
        elif node["type"] == "hard_break" and one_line:
            flat.append(_text_node(" ", _marks(node)))
        elif node["type"] == "html_inline" and one_line:
            flat.append({**node, "attrs": {"source": node["attrs"]["source"].replace("\n", " ")}})
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
# (markup, None) for delimiters, code spans, link syntax, hard breaks, images,
# footnote references and inline HTML. Text is escaped afterwards, when the output
# characters around each text piece are known.


def _pieces(nodes: list[dict], cell: bool = False) -> list[tuple[str, bool | None]]:
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
        if autolink := _autolink(nodes, i, cell):
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
    kind = node["type"]
    if kind == "text":
        if _has_mark(node, "code"):
            return _code_span(node["text"]), None
        return node["text"], in_link
    if kind == "hard_break":
        return "\\\n", None
    if kind == "image":
        return _image(node["attrs"]), None
    if kind == "footnote_ref":
        return f"[^{node['attrs']['label']}]", None
    if kind == "html_inline":
        return node["attrs"]["source"], None
    raise ValueError(f"cannot serialize a {kind!r} node")


def _image(attrs: dict) -> str:
    """![alt](src "title"); the alt text is escaped like link text."""
    alt = _escape(attrs["alt"].replace("\n", " "), "[", "]", True, False, False, False)
    return f"![{alt}](" + _link_target(attrs["src"], attrs["title"]) + ")"


def _close(mark: dict) -> str:
    if mark["type"] == "link":
        return "](" + _link_target(mark["attrs"]["href"], mark["attrs"]["title"]) + ")"
    return _DELIMITERS[mark["type"]]


def _autolink(nodes: list[dict], index: int, cell: bool = False) -> str | None:
    """The node written as an autolink (spec 6.5), or None for a [text](href) link.

    Only an untitled link that is the node's only mark and covers just this node
    qualifies. An http(s) URL whose text is its href stays bare when nothing that
    follows could be read as part of the URL; otherwise it becomes <href>. A mailto:
    link whose text is the address becomes <address>. In a table cell a URL holding
    "|" is written [text](href), where "\\|" can escape the pipe."""
    node = nodes[index]
    link = _link(node)
    if node["type"] != "text" or _marks(node) != [link] or link["attrs"]["title"] is not None:
        return None
    if _extent(nodes, index, link) != 1 or (index > 0 and link in _marks(nodes[index - 1])):
        return None
    text, href = node["text"], link["attrs"]["href"]
    if cell and "|" in text + href:
        return None
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


def _escape_pieces(pieces: list[tuple[str, bool | None]], heading: bool, cell: bool = False) -> str:
    out: list[str] = []
    for i, (value, in_link) in enumerate(pieces):
        if in_link is None:
            out.append(value)
            continue
        before = out[-1][-1:] if out else ""
        after = pieces[i + 1][0][:1] if i + 1 < len(pieces) else ""
        line_start = before in ("", "\n")
        line_end = i + 1 == len(pieces) or pieces[i + 1][0] == "\\\n"
        text = _escape(value, before, after, in_link, line_start, line_end, heading, cell)
        if i == 1 and before == "]" and text[:1] == ":" and not (heading or cell):
            text = "\\" + text  # "[^1]: x" at a paragraph start would define footnote 1
        out.append(text)
    return "".join(out)


def _escape(
    text: str,
    before: str,
    after: str,
    in_link: bool,
    line_start: bool,
    line_end: bool,
    heading: bool,
    cell: bool = False,
) -> str:
    """Backslash-escape what Markdown would read as syntax in `text`, and nothing else.

    `before`/`after` are the output characters around the text ("" at a block edge,
    "\\n" after a hard break); line_start/line_end say whether the text starts/ends a line."""
    escaped: set[int] = set()
    # mistune links bare http(s) URLs anywhere; inside link text one swallows the markup up to "]".
    escaped |= {match.end() for match in _BARE_URL_SCHEME.finditer(text)}
    if line_start and not (heading or cell):
        escaped |= _line_start_escapes(text, line_end)
    if heading and after == "" and (match := _HEADING_CLOSE.search(text)):
        escaped.add(match.start(1))
    # Whitespace that mistune would drop is written as a character reference: after a hard
    # break, and at the edges of a table cell (which mistune strips like str.strip).
    references: set[int] = set()
    if text and text[0].isspace() and (before == "\n" or (cell and line_start)):
        references.add(0)
    if text and text[-1].isspace() and cell and line_end:
        references.add(len(text) - 1)
    for i, ch in enumerate(text):
        prev = ";" if i - 1 in references else text[i - 1] if i > 0 else before
        nxt = "&" if i + 1 in references else text[i + 1] if i + 1 < len(text) else after
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
    return "".join(
        _char_reference(ch) if i in references else "\\" + ch if i in escaped else ch for i, ch in enumerate(text)
    )


def _char_reference(ch: str) -> str:
    return "&nbsp;" if ch == "\xa0" else f"&#{ord(ch)};"


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
