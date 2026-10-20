"""Document contract for the Rendered editor (spec 6.3).

ProseMirror JSON nodes look like {"type", "attrs", "content", "marks", "text"}.
core/docmodel.py produces documents, core/serialize.py consumes them, and
web-src/src/schema.js declares the same names, attrs and content rules: change
both files together and rebuild the bundle (scripts/build_web.py).

The attr tuples list required attrs. Top-level blocks (TOP_LEVEL_NODES) also
accept the transient LINE_ATTR (1-based source start line, or None); it is
non-None only on direct children of doc and the serializer ignores it.
"""

from collections.abc import Callable

BLOCK_NODES: dict[str, tuple[str, ...]] = {
    "doc": (),
    "paragraph": (),
    "heading": ("level",),
    "blockquote": (),
    "bullet_list": ("tight",),
    "ordered_list": ("start", "tight"),
    "list_item": ("checked",),
    "code_block": ("language", "highlight"),
    "horizontal_rule": (),
    "table": (),
    "table_row": (),
    "table_header": ("align",),
    "table_cell": ("align",),
    "front_matter": ("source",),
    "html_block": ("source",),
    "footnote_def": ("label", "source"),
}
INLINE_NODES: dict[str, tuple[str, ...]] = {
    "text": (),
    "hard_break": (),
    "image": ("src", "display_src", "alt", "title"),
    "footnote_ref": ("label",),
    "html_inline": ("source",),
}
PROTECTED_NODES = frozenset({"front_matter", "html_block", "footnote_def", "footnote_ref", "html_inline"})
MARKS: dict[str, tuple[str, ...]] = {
    "strong": (),
    "em": (),
    "strike": (),
    "code": (),
    "link": ("href", "title"),
}
LINE_ATTR = "line"

# Blocks allowed wherever block content goes: doc, blockquote, list_item.
BLOCK_CONTENT = frozenset({
    "paragraph", "heading", "blockquote", "bullet_list", "ordered_list",
    "code_block", "horizontal_rule", "table", "html_block",
})
# Blocks allowed directly in doc; front_matter only as its first child.
TOP_LEVEL_NODES = BLOCK_CONTENT | {"front_matter", "footnote_def"}
_INLINE_CONTENT = frozenset(INLINE_NODES)

# Container -> (allowed child types, minimum number of children). Other nodes are leaves.
CONTENT: dict[str, tuple[frozenset[str], int]] = {
    "doc": (TOP_LEVEL_NODES, 1),
    "paragraph": (_INLINE_CONTENT, 0),
    "heading": (_INLINE_CONTENT, 0),
    "blockquote": (BLOCK_CONTENT, 1),
    "bullet_list": (frozenset({"list_item"}), 1),
    "ordered_list": (frozenset({"list_item"}), 1),
    "list_item": (BLOCK_CONTENT, 1),
    "code_block": (frozenset({"text"}), 0),
    "table": (frozenset({"table_row"}), 1),
    "table_row": (frozenset({"table_header", "table_cell"}), 1),
    "table_header": (_INLINE_CONTENT, 0),
    "table_cell": (_INLINE_CONTENT, 0),
}


def _is_str(value: object) -> bool:
    return isinstance(value, str)


def _is_optional_str(value: object) -> bool:
    return value is None or isinstance(value, str)


def _is_int(value: object, low: int, high: int | None = None) -> bool:
    if not isinstance(value, int) or isinstance(value, bool):
        return False
    return value >= low and (high is None or value <= high)


_ATTR_CHECKS: dict[str, Callable[[object], bool]] = {
    "level": lambda v: _is_int(v, 1, 6),
    "tight": lambda v: isinstance(v, bool),
    "start": lambda v: _is_int(v, 0),
    "checked": lambda v: v is None or isinstance(v, bool),
    "language": _is_str,
    "highlight": _is_str,
    "align": lambda v: v in (None, "left", "center", "right"),
    "source": _is_str,
    "label": lambda v: isinstance(v, str) and v != "",
    "src": _is_str,
    "display_src": _is_str,
    "alt": _is_str,
    "title": _is_optional_str,
    "href": _is_str,
    LINE_ATTR: lambda v: v is None or _is_int(v, 1),
}


def validate(doc: dict) -> list[str]:
    """Problems found in `doc`, each prefixed with its JSON path ("$.content[2]"); [] when valid."""
    if not isinstance(doc, dict) or doc.get("type") != "doc":
        return ["$: root must be a doc node"]
    problems: list[str] = []
    _check_node(doc, "$", None, problems)
    return problems


def _check_node(node: object, path: str, parent: str | None, problems: list[str]) -> None:
    if not isinstance(node, dict) or not isinstance(node.get("type"), str):
        problems.append(f"{path}: not a node object")
        return
    name = node["type"]
    if name in BLOCK_NODES:
        required = BLOCK_NODES[name]
    elif name in INLINE_NODES:
        required = INLINE_NODES[name]
    else:
        problems.append(f"{path}: unknown node type {name!r}")
        return
    optional = (LINE_ATTR,) if name in TOP_LEVEL_NODES else ()
    attrs = _check_attrs(node, name, required, optional, path, problems)
    if attrs.get(LINE_ATTR) is not None and parent != "doc":
        problems.append(f"{path}: {LINE_ATTR} is only allowed on top-level blocks")
    _check_text(node, name, path, problems)
    _check_marks(node, name, path, parent, problems)
    _check_content(node, name, path, problems)


def _check_attrs(
    obj: dict, label: str, required: tuple[str, ...], optional: tuple[str, ...], path: str, problems: list[str]
) -> dict:
    attrs = obj.get("attrs", {})
    if not isinstance(attrs, dict):
        problems.append(f"{path}: attrs must be an object")
        return {}
    for attr in required:
        if attr not in attrs:
            problems.append(f"{path}: {label} is missing attr {attr!r}")
    for attr, value in attrs.items():
        if attr not in required and attr not in optional:
            problems.append(f"{path}: {label} has unknown attr {attr!r}")
        elif not _ATTR_CHECKS[attr](value):
            problems.append(f"{path}: {label}.{attr} has invalid value {value!r}")
    return attrs


def _check_text(node: dict, name: str, path: str, problems: list[str]) -> None:
    if name == "text":
        if not isinstance(node.get("text"), str) or node["text"] == "":
            problems.append(f"{path}: text node needs a non-empty 'text' string")
    elif "text" in node:
        problems.append(f"{path}: only text nodes have 'text'")


def _check_marks(node: dict, name: str, path: str, parent: str | None, problems: list[str]) -> None:
    if "marks" not in node:
        return
    marks = node["marks"]
    if name in BLOCK_NODES:
        problems.append(f"{path}: {name} cannot have marks")
        return
    if not isinstance(marks, list):
        problems.append(f"{path}: marks must be a list")
        return
    if marks and parent == "code_block":
        problems.append(f"{path}: marks are not allowed inside code_block")
    seen: set[str] = set()
    for index, mark in enumerate(marks):
        mark_path = f"{path}.marks[{index}]"
        mark_type = mark.get("type") if isinstance(mark, dict) else None
        if not isinstance(mark_type, str) or mark_type not in MARKS:
            problems.append(f"{mark_path}: unknown mark type {mark_type!r}")
            continue
        if mark_type in seen:
            problems.append(f"{mark_path}: duplicate mark {mark_type!r}")
        seen.add(mark_type)
        _check_attrs(mark, f"mark {mark_type}", MARKS[mark_type], (), mark_path, problems)


def _check_content(node: dict, name: str, path: str, problems: list[str]) -> None:
    if name not in CONTENT:
        if "content" in node:
            problems.append(f"{path}: {name} is a leaf and cannot have content")
        return
    content = node.get("content", [])
    if not isinstance(content, list):
        problems.append(f"{path}: content must be a list")
        return
    allowed, minimum = CONTENT[name]
    if len(content) < minimum:
        problems.append(f"{path}: {name} needs at least one child")
    for index, child in enumerate(content):
        child_path = f"{path}.content[{index}]"
        child_type = child.get("type") if isinstance(child, dict) else None
        if isinstance(child_type, str) and (child_type in BLOCK_NODES or child_type in INLINE_NODES):
            if child_type not in allowed:
                problems.append(f"{child_path}: {child_type} is not allowed in {name}")
            elif child_type == "front_matter" and index != 0:
                problems.append(f"{child_path}: front_matter must be the first child of doc")
        _check_node(child, child_path, name, problems)
