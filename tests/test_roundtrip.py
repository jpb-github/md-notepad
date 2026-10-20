"""Round-trip properties of docmodel + serialize (spec 8) over tests/corpus, README.md and docs/."""

import html
import random
import re
from pathlib import Path

import pytest

from mdviewer.core import docschema, frontmatter
from mdviewer.core.docmodel import from_markdown
from mdviewer.core.render import render_body
from mdviewer.core.serialize import to_text

ROOT = Path(__file__).resolve().parent.parent
CORPUS = sorted((ROOT / "tests" / "corpus").glob("*.md"))
SOURCES = CORPUS + [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]


def load(text: str) -> dict:
    front, body = frontmatter.split(text)
    return from_markdown(body, front)


def without_lines(node: dict) -> dict:
    copy = dict(node)
    if "attrs" in copy and docschema.LINE_ATTR in copy["attrs"]:
        copy["attrs"] = {**copy["attrs"], docschema.LINE_ATTR: None}
    if "content" in copy:
        copy["content"] = [without_lines(child) for child in copy["content"]]
    return copy


def rendered(text: str) -> str:
    """render_body of the text's body, whitespace-normalized and entity-decoded.

    Fenced code keeps the newline before its closing fence, indented code does not; the
    serializer writes all code fenced, so that newline is dropped before comparing."""
    body = frontmatter.split(text)[1]
    markup = render_body(body).replace("\n</code></pre>", "</code></pre>")
    return re.sub(r"\s+", " ", html.unescape(markup)).strip()


@pytest.fixture(params=SOURCES, ids=lambda path: path.relative_to(ROOT).as_posix())
def source(request) -> str:
    return request.param.read_text(encoding="utf-8").replace("\r\n", "\n")


def test_corpus_exists():
    assert len(CORPUS) >= 5


def test_corpus_uses_every_node_type_and_mark():
    nodes, marks = set(), set()

    def collect(node):
        nodes.add(node["type"])
        marks.update(mark["type"] for mark in node.get("marks", []))
        for child in node.get("content", []):
            collect(child)

    for path in CORPUS:
        collect(load(path.read_text(encoding="utf-8")))
    assert nodes == set(docschema.BLOCK_NODES) | set(docschema.INLINE_NODES)
    assert marks == set(docschema.MARKS)


def test_documents_are_valid(source):
    assert docschema.validate(load(source)) == []


def test_serialization_is_a_fixed_point_after_one_pass(source):
    once = to_text(load(source))
    assert to_text(load(once)) == once


def test_serialized_text_loads_as_the_same_document(source):
    document = load(source)
    assert without_lines(load(to_text(document))) == without_lines(document)


def test_serialized_text_renders_the_same_html(source):
    assert rendered(to_text(load(source))) == rendered(source)


def test_corpus_is_not_already_in_normal_form():
    """Every corpus file exercises normalization, so the fixed-point test is not vacuous.

    (Spec 1: a file that is only viewed is never rewritten; MainWindow ensures that by not
    serializing an unchanged document, not by the serializer reproducing the source.)"""
    for path in CORPUS:
        source = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        assert to_text(load(source)) != source, path


# --- random block structure ---------------------------------------------------------------
# Random trees of paragraphs, headings, code, rules, HTML, quotes, lists and tables must come
# back with the same structure (tight flags and empty paragraphs aside) and be a fixed point.
# Known limit kept out of the generator (see the plan's Task 7 Review Focus): a list whose
# last item is empty.

_WORDS = ["a", "b", "word", "x_y", "1.", "-", "#", ">", "*", "`", "|", "[x]", "---", "===", "<b>", "&amp;", "\\"]


def _text(value):
    return {"type": "text", "text": value}


def _paragraph(rng):
    value = " ".join(rng.choice(_WORDS) for _ in range(rng.randint(0, 4)))
    node = {"type": "paragraph", "attrs": {"line": None}}
    if value:
        node["content"] = [_text(value)]
    return node


def _random_block(rng, depth, top):
    kinds = ["paragraph", "paragraph", "paragraph", "heading", "code", "rule", "html"]
    if depth < 3:
        kinds += ["quote", "bullets", "ordered", "bullets", "ordered"]
    if top:  # mistune reads tables at the top level only (no table_in_quote / table_in_list)
        kinds.append("table")
    kind = rng.choice(kinds)
    if kind == "paragraph":
        return _paragraph(rng)
    if kind == "heading":
        return {**_paragraph(rng), "type": "heading", "attrs": {"level": rng.randint(1, 6), "line": None}}
    if kind == "code":
        node = {"type": "code_block", "attrs": {"language": rng.choice(["", "py"]), "highlight": "", "line": None}}
        code = rng.choice(["", "x", "a\n\nb", "```\ny", "  indented", "x\n"])
        if code:
            node["content"] = [_text(code)]
        return node
    if kind == "rule":
        return {"type": "horizontal_rule", "attrs": {"line": None}}
    if kind == "html":
        return {"type": "html_block", "attrs": {"source": rng.choice(["<div>x</div>", "<!-- c\n\nd -->"]),
                                                "line": None}}
    if kind == "quote":
        return {"type": "blockquote", "attrs": {"line": None}, "content": _random_blocks(rng, depth + 1)}
    if kind == "table":
        return _random_table(rng)
    items = [{"type": "list_item", "attrs": {"checked": rng.choice([None, None, True, False])},
              "content": _random_blocks(rng, depth + 1)} for _ in range(rng.randint(1, 3))]
    last = items[-1]
    if last["attrs"]["checked"] is None and not any(_skeleton(block) != {"type": "paragraph"}
                                                    for block in last["content"]):
        last["content"] = [{"type": "paragraph", "attrs": {"line": None}, "content": [_text("z")]}]
    attrs = {"tight": rng.random() < 0.6, "line": None}
    if kind == "ordered":
        return {"type": "ordered_list", "attrs": {"start": rng.choice([1, 1, 0, 3, 9]), **attrs}, "content": items}
    return {"type": "bullet_list", "attrs": attrs, "content": items}


def _random_table(rng):
    width = rng.randint(1, 3)
    aligns = [rng.choice([None, "left", "center", "right"]) for _ in range(width)]
    rows = []
    for index in range(rng.randint(1, 3)):
        cells = []
        for align in aligns:
            cell = {"type": "table_header" if index == 0 else "table_cell", "attrs": {"align": align}}
            if "content" in (paragraph := _paragraph(rng)):
                cell["content"] = paragraph["content"]
            cells.append(cell)
        rows.append({"type": "table_row", "content": cells})
    return {"type": "table", "attrs": {"line": None}, "content": rows}


def _random_blocks(rng, depth, top=False):
    return [_random_block(rng, depth, top) for _ in range(rng.randint(1, 3))]


def _skeleton(node):
    """The node without what serialization may change: line, tight, highlight, empty paragraphs."""
    out = {"type": node["type"]}
    attrs = {key: value for key, value in node.get("attrs", {}).items() if key not in ("line", "tight", "highlight")}
    if attrs:
        out["attrs"] = attrs
    if "text" in node:
        out["text"] = node["text"]
    children = [_skeleton(child) for child in node.get("content", [])
                if child["type"] != "paragraph" or child.get("content")]
    if children:
        out["content"] = children
    return out


def test_random_block_trees_round_trip():
    rng = random.Random(7)
    for _ in range(600):
        document = {"type": "doc", "content": _random_blocks(rng, 0, top=True)}
        markdown = to_text(document)
        back = load(markdown)
        assert docschema.validate(back) == [], markdown
        assert _skeleton(back) == _skeleton(document), markdown
        assert to_text(back) == markdown, markdown
