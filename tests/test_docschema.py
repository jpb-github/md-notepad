import json
import re
from pathlib import Path

import pytest

from mdviewer.core.docschema import (
    BLOCK_CONTENT,
    BLOCK_NODES,
    CONTENT,
    INLINE_NODES,
    LINE_ATTR,
    MARKS,
    PROTECTED_NODES,
    TOP_LEVEL_NODES,
    validate,
)


def t(text, *marks):
    node = {"type": "text", "text": text}
    if marks:
        node["marks"] = list(marks)
    return node


def p(*inline):
    node = {"type": "paragraph"}
    if inline:
        node["content"] = list(inline)
    return node


def item(*blocks, checked=None):
    return {"type": "list_item", "attrs": {"checked": checked}, "content": list(blocks) or [p(t("x"))]}


def doc(*blocks):
    return {"type": "doc", "content": list(blocks)}


def link(href="https://example.com", title=None):
    return {"type": "link", "attrs": {"href": href, "title": title}}


def every_node_doc():
    """One document using every node type and mark, shaped like ProseMirror's toJSON()."""
    return doc(
        {"type": "front_matter", "attrs": {"source": "---\ntitle: x\n---\n", "line": 1}},
        {"type": "heading", "attrs": {"level": 1, "line": 5}, "content": [t("Title")]},
        {"type": "paragraph", "attrs": {"line": 7}, "content": [
            t("bold", {"type": "strong"}),
            t("it", {"type": "em"}),
            t("gone", {"type": "strike"}),
            t("x()", {"type": "code"}),
            t("link", link()),
            {"type": "hard_break"},
            {"type": "image",
             "attrs": {"src": "a.png", "display_src": "file:///C:/d/a.png", "alt": "A", "title": None},
             "marks": [link("https://ci.example/badge", "Build")]},
            {"type": "footnote_ref", "attrs": {"label": "1"}},
            {"type": "html_inline", "attrs": {"source": "<kbd>"}},
        ]},
        {"type": "blockquote", "attrs": {"line": 9}, "content": [
            {"type": "paragraph", "attrs": {"line": None}, "content": [t("quoted")]},
        ]},
        {"type": "bullet_list", "attrs": {"tight": True, "line": 11}, "content": [
            item(p(t("one"))),
            item(p(t("done")), {"type": "ordered_list", "attrs": {"start": 3, "tight": False},
                                "content": [item(p(t("nested")), checked=False)]}, checked=True),
        ]},
        {"type": "code_block",
         "attrs": {"language": "python", "highlight": '<span class="k">pass</span>', "line": 15},
         "content": [t("pass")]},
        {"type": "horizontal_rule", "attrs": {"line": 18}},
        {"type": "table", "attrs": {"line": 20}, "content": [
            {"type": "table_row", "content": [
                {"type": "table_header", "attrs": {"align": "left"}, "content": [t("h")]},
                {"type": "table_header", "attrs": {"align": None}},
            ]},
            {"type": "table_row", "content": [
                {"type": "table_cell", "attrs": {"align": "right"}, "content": [t("c")]},
                {"type": "table_cell", "attrs": {"align": "center"}},
            ]},
        ]},
        {"type": "html_block", "attrs": {"source": "<div>x</div>\n", "line": 24}},
        {"type": "footnote_def", "attrs": {"label": "1", "source": "[^1]: note\n", "line": 26}},
    )


def collect_types(node, nodes, marks):
    nodes.add(node["type"])
    for mark in node.get("marks", []):
        marks.add(mark["type"])
    for child in node.get("content", []):
        collect_types(child, nodes, marks)


# --- name tables -------------------------------------------------------------

def test_block_node_names_and_attrs_match_spec():
    assert BLOCK_NODES == {
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


def test_inline_node_names_and_attrs_match_spec():
    assert INLINE_NODES == {
        "text": (),
        "hard_break": (),
        "image": ("src", "display_src", "alt", "title"),
        "footnote_ref": ("label",),
        "html_inline": ("source",),
    }


def test_marks_match_spec():
    assert MARKS == {"strong": (), "em": (), "strike": (), "code": (), "link": ("href", "title")}


def test_protected_nodes_match_spec():
    assert PROTECTED_NODES == {"front_matter", "html_block", "footnote_def", "footnote_ref", "html_inline"}
    assert PROTECTED_NODES <= set(BLOCK_NODES) | set(INLINE_NODES)


def test_name_tables_do_not_overlap():
    assert not set(BLOCK_NODES) & set(INLINE_NODES)
    assert not (set(BLOCK_NODES) | set(INLINE_NODES)) & set(MARKS)


def test_content_rules_only_name_known_nodes():
    known = set(BLOCK_NODES) | set(INLINE_NODES)
    assert set(CONTENT) <= set(BLOCK_NODES)
    for allowed, minimum in CONTENT.values():
        assert allowed <= known
        assert minimum in (0, 1)
    assert BLOCK_CONTENT < TOP_LEVEL_NODES <= set(BLOCK_NODES)
    assert LINE_ATTR == "line"


# --- valid documents ----------------------------------------------------------

def test_every_node_doc_uses_every_name():
    nodes, marks = set(), set()
    collect_types(every_node_doc(), nodes, marks)
    assert nodes == set(BLOCK_NODES) | set(INLINE_NODES)
    assert marks == set(MARKS)


def test_every_node_doc_is_valid():
    assert validate(every_node_doc()) == []


def test_empty_paragraph_doc_is_valid():
    assert validate(doc(p())) == []


def test_marks_on_inline_non_text_nodes_are_valid():
    image = {"type": "image", "attrs": {"src": "b.svg", "display_src": "b.svg", "alt": "", "title": None},
             "marks": [link()]}
    assert validate(doc(p(image, {"type": "hard_break", "marks": [{"type": "em"}]}))) == []


def test_line_may_be_none_on_nested_blocks():
    assert validate(doc({"type": "blockquote", "content": [
        {"type": "paragraph", "attrs": {"line": None}, "content": [t("x")]},
    ]})) == []


# --- rejected documents -------------------------------------------------------

@pytest.mark.parametrize("root", [None, [], {}, {"type": "paragraph"}, {"type": 3}])
def test_root_must_be_doc(root):
    assert validate(root) == ["$: root must be a doc node"]


def test_unknown_node_type():
    assert validate(doc(p(t("a")), {"type": "callout"})) == ["$.content[1]: unknown node type 'callout'"]


def test_non_object_child():
    assert validate(doc("text")) == ["$.content[0]: not a node object"]


def test_unknown_mark_type():
    assert validate(doc(p(t("a", {"type": "bold"})))) == [
        "$.content[0].content[0].marks[0]: unknown mark type 'bold'"
    ]


def test_duplicate_mark():
    assert validate(doc(p(t("a", {"type": "em"}, {"type": "em"})))) == [
        "$.content[0].content[0].marks[1]: duplicate mark 'em'"
    ]


def test_missing_node_attr():
    assert validate(doc({"type": "heading", "content": [t("x")]})) == [
        "$.content[0]: heading is missing attr 'level'"
    ]


def test_missing_mark_attr():
    assert validate(doc(p(t("a", {"type": "link", "attrs": {"href": "x"}})))) == [
        "$.content[0].content[0].marks[0]: mark link is missing attr 'title'"
    ]


def test_unknown_attr():
    assert validate(doc({"type": "paragraph", "attrs": {"align": "left"}})) == [
        "$.content[0]: paragraph has unknown attr 'align'"
    ]


def test_line_is_unknown_on_nodes_that_are_never_top_level():
    assert validate(doc({"type": "bullet_list", "attrs": {"tight": True}, "content": [
        {"type": "list_item", "attrs": {"checked": None, "line": None}, "content": [p()]},
    ]})) == ["$.content[0].content[0]: list_item has unknown attr 'line'"]


def test_attrs_must_be_an_object():
    assert validate(doc({"type": "paragraph", "attrs": []})) == ["$.content[0]: attrs must be an object"]


@pytest.mark.parametrize("block, message", [
    ({"type": "heading", "attrs": {"level": 7}}, "heading.level has invalid value 7"),
    ({"type": "heading", "attrs": {"level": True}}, "heading.level has invalid value True"),
    ({"type": "bullet_list", "attrs": {"tight": "yes"}, "content": [item()]},
     "bullet_list.tight has invalid value 'yes'"),
    ({"type": "ordered_list", "attrs": {"start": -1, "tight": True}, "content": [item()]},
     "ordered_list.start has invalid value -1"),
    ({"type": "code_block", "attrs": {"language": None, "highlight": ""}},
     "code_block.language has invalid value None"),
    ({"type": "html_block", "attrs": {"source": "<br>", "line": 0}}, "html_block.line has invalid value 0"),
    ({"type": "footnote_def", "attrs": {"label": "", "source": "[^]: x"}},
     "footnote_def.label has invalid value ''"),
])
def test_invalid_top_level_attr_values(block, message):
    assert validate(doc(block)) == [f"$.content[0]: {message}"]


def test_invalid_nested_attr_values():
    cell = {"type": "table_cell", "attrs": {"align": "justify"}}
    image = {"type": "image", "attrs": {"src": "a", "display_src": "a", "alt": "", "title": 5}}
    assert validate(doc(
        {"type": "table", "content": [{"type": "table_row", "content": [cell]}]},
        {"type": "bullet_list", "attrs": {"tight": True}, "content": [item(checked="x")]},
        p(image, t("a", link(href=None))),
    )) == [
        "$.content[0].content[0].content[0]: table_cell.align has invalid value 'justify'",
        "$.content[1].content[0]: list_item.checked has invalid value 'x'",
        "$.content[2].content[0]: image.title has invalid value 5",
        "$.content[2].content[1].marks[0]: mark link.href has invalid value None",
    ]


def test_line_only_on_top_level_blocks():
    assert validate(doc({"type": "blockquote", "content": [
        {"type": "paragraph", "attrs": {"line": 3}, "content": [t("x")]},
    ]})) == ["$.content[0].content[0]: line is only allowed on top-level blocks"]


@pytest.mark.parametrize("node", [{"type": "text"}, {"type": "text", "text": ""}, {"type": "text", "text": 5}])
def test_text_node_needs_text(node):
    assert validate(doc(p(node))) == ["$.content[0].content[0]: text node needs a non-empty 'text' string"]


def test_only_text_nodes_have_text():
    assert validate(doc({"type": "paragraph", "text": "a"})) == ["$.content[0]: only text nodes have 'text'"]


def test_block_nodes_cannot_have_marks():
    assert validate(doc({"type": "paragraph", "marks": [{"type": "strong"}], "content": [t("a")]})) == [
        "$.content[0]: paragraph cannot have marks"
    ]


def test_marks_must_be_a_list():
    assert validate(doc(p({"type": "text", "text": "a", "marks": {"type": "em"}}))) == [
        "$.content[0].content[0]: marks must be a list"
    ]


def test_no_marks_inside_code_block():
    code = {"type": "code_block", "attrs": {"language": "", "highlight": ""},
            "content": [t("x", {"type": "strong"})]}
    assert validate(doc(code)) == ["$.content[0].content[0]: marks are not allowed inside code_block"]


ONE_CELL_TABLE = {"type": "table", "content": [
    {"type": "table_row", "content": [{"type": "table_header", "attrs": {"align": None}}]},
]}


@pytest.mark.parametrize("block, message", [
    (p(p(t("a"))), "$.content[0].content[0]: paragraph is not allowed in paragraph"),
    ({"type": "heading", "attrs": {"level": 2}, "content": [{"type": "horizontal_rule"}]},
     "$.content[0].content[0]: horizontal_rule is not allowed in heading"),
    ({"type": "bullet_list", "attrs": {"tight": True}, "content": [p(t("a"))]},
     "$.content[0].content[0]: paragraph is not allowed in bullet_list"),
    ({"type": "code_block", "attrs": {"language": "", "highlight": ""}, "content": [{"type": "hard_break"}]},
     "$.content[0].content[0]: hard_break is not allowed in code_block"),
    ({"type": "blockquote", "content": [{"type": "footnote_def", "attrs": {"label": "1", "source": "x"}}]},
     "$.content[0].content[0]: footnote_def is not allowed in blockquote"),
    ({"type": "table", "content": [{"type": "table_cell", "attrs": {"align": None}}]},
     "$.content[0].content[0]: table_cell is not allowed in table"),
    # mistune reads pipe tables at the top level only: a nested one would come back as a paragraph.
    ({"type": "blockquote", "content": [ONE_CELL_TABLE]}, "$.content[0].content[0]: table is not allowed in blockquote"),
    ({"type": "bullet_list", "attrs": {"tight": True}, "content": [item(ONE_CELL_TABLE)]},
     "$.content[0].content[0].content[0]: table is not allowed in list_item"),
])
def test_child_not_allowed_in_parent(block, message):
    assert validate(doc(block)) == [message]


def test_inline_node_at_top_level():
    assert validate(doc(t("a"))) == ["$.content[0]: text is not allowed in doc"]


@pytest.mark.parametrize("block", [
    {"type": "blockquote"},
    {"type": "bullet_list", "attrs": {"tight": True}, "content": []},
    {"type": "table", "content": [{"type": "table_row"}]},
])
def test_containers_need_children(block):
    problems = validate(doc(block))
    assert len(problems) == 1 and problems[0].endswith("needs at least one child")


def test_doc_needs_a_child():
    assert validate({"type": "doc"}) == ["$: doc needs at least one child"]


def test_leaves_cannot_have_content():
    image = {"type": "image", "attrs": {"src": "a", "display_src": "a", "alt": "", "title": None},
             "content": [t("x")]}
    assert validate(doc({"type": "horizontal_rule", "content": []}, p(image))) == [
        "$.content[0]: horizontal_rule is a leaf and cannot have content",
        "$.content[1].content[0]: image is a leaf and cannot have content",
    ]


def test_content_must_be_a_list():
    assert validate(doc({"type": "paragraph", "content": "a"})) == ["$.content[0]: content must be a list"]


def test_front_matter_only_first_in_doc():
    front = {"type": "front_matter", "attrs": {"source": "---\na: 1\n---\n"}}
    assert validate(doc(p(t("a")), front)) == ["$.content[1]: front_matter must be the first child of doc"]
    assert validate(doc({"type": "blockquote", "content": [front]})) == [
        "$.content[0].content[0]: front_matter is not allowed in blockquote"
    ]


def test_reports_every_problem_in_document_order():
    bad = doc({"type": "heading", "attrs": {"level": 9}, "content": [t("x", {"type": "bold"})]}, {"type": "x"})
    assert validate(bad) == [
        "$.content[0]: heading.level has invalid value 9",
        "$.content[0].content[0].marks[0]: unknown mark type 'bold'",
        "$.content[1]: unknown node type 'x'",
    ]


# --- web-src/src/schema.js mirrors this module ------------------------------------------------

def js_contract():
    """The CONTRACT block of web-src/src/schema.js, parsed as JSON."""
    source = (Path(__file__).resolve().parent.parent / "web-src" / "src" / "schema.js").read_text(encoding="utf-8")
    match = re.search(r"^export const CONTRACT = (\{.*?^\});$", source, flags=re.S | re.M)
    assert match, "schema.js has no 'export const CONTRACT = {...};' block"
    return json.loads(match.group(1))


def test_js_schema_nodes_match_docschema_in_order():
    contract = js_contract()
    assert list(contract["blockNodes"].items()) == [(name, list(attrs)) for name, attrs in BLOCK_NODES.items()]
    assert list(contract["inlineNodes"].items()) == [(name, list(attrs)) for name, attrs in INLINE_NODES.items()]


def test_js_schema_marks_match_docschema_in_rank_order():
    assert list(js_contract()["marks"].items()) == [(name, list(attrs)) for name, attrs in MARKS.items()]


def test_js_schema_node_sets_match_docschema():
    contract = js_contract()
    assert contract["protectedNodes"] == sorted(PROTECTED_NODES)
    assert contract["topLevelNodes"] == sorted(TOP_LEVEL_NODES)
