import pytest

from mdviewer.core import docmodel
from mdviewer.core.docschema import validate


def convert(markdown, front=None):
    """from_markdown, plus the contract every output must meet."""
    doc = docmodel.from_markdown(markdown, front)
    assert validate(doc) == []
    return doc


def doc(*blocks):
    return {"type": "doc", "content": list(blocks)}


def para(*inline, line=None):
    node = {"type": "paragraph", "attrs": {"line": line}}
    if inline:
        node["content"] = list(inline)
    return node


def heading(level, *inline, line=None):
    node = {"type": "heading", "attrs": {"level": level, "line": line}}
    if inline:
        node["content"] = list(inline)
    return node


def quote(*blocks, line=None):
    return {"type": "blockquote", "attrs": {"line": line}, "content": list(blocks)}


def rule(line=None):
    return {"type": "horizontal_rule", "attrs": {"line": line}}


def text(value, *marks):
    node = {"type": "text", "text": value}
    if marks:
        node["marks"] = list(marks)
    return node


def hard_break(*marks):
    node = {"type": "hard_break"}
    if marks:
        node["marks"] = list(marks)
    return node


STRONG, EM, STRIKE, CODE = ({"type": name} for name in ("strong", "em", "strike", "code"))


def link(href, title=None):
    return {"type": "link", "attrs": {"href": href, "title": title}}


def only_inline(markdown):
    """Inline content of a one-paragraph document."""
    [block] = convert(markdown)["content"]
    assert block["type"] == "paragraph"
    return block.get("content", [])


# --- documents and paragraphs ---------------------------------------------------------


@pytest.mark.parametrize("markdown", ["", "\n", "\n\n  \n"])
def test_empty_body_is_one_empty_paragraph(markdown):
    assert convert(markdown) == doc(para(line=1))


def test_paragraphs_with_lines():
    assert convert("Hello\n\nWorld\n") == doc(para(text("Hello"), line=1), para(text("World"), line=3))


def test_soft_break_becomes_a_space():
    assert only_inline("line one\nline two") == [text("line one line two")]


def test_hard_breaks():
    assert only_inline("a  \nb\\\nc") == [text("a"), hard_break(), text("b"), hard_break(), text("c")]


def test_hard_break_keeps_active_marks():
    assert only_inline("**a  \nb**") == [text("a", STRONG), hard_break(STRONG), text("b", STRONG)]


# --- headings ------------------------------------------------------------------------


@pytest.mark.parametrize("level", [1, 2, 3, 4, 5, 6])
def test_atx_headings(level):
    assert convert("#" * level + " Title") == doc(heading(level, text("Title"), line=1))


def test_atx_closing_hashes_are_dropped():
    assert convert("#   Title   #\n") == doc(heading(1, text("Title"), line=1))


def test_setext_headings():
    assert convert("One\n===\n\nTwo\n---\n") == doc(
        heading(1, text("One"), line=1), heading(2, text("Two"), line=4)
    )


def test_empty_heading_has_no_content():
    assert convert("#\n") == doc(heading(1, line=1))


# --- block quotes and rules -------------------------------------------------------------


def test_blockquote_nested_blocks_have_line_none():
    assert convert("> a\n>\n> b\n") == doc(quote(para(text("a")), para(text("b")), line=1))


def test_blockquote_lazy_continuation():
    assert convert("> quote\nlazy\n") == doc(quote(para(text("quote lazy")), line=1))


def test_empty_blockquote_gets_an_empty_paragraph():
    assert convert(">\n") == doc(quote(para(), line=1))


def test_nested_blockquote():
    assert convert("> > deep\n") == doc(quote(quote(para(text("deep"))), line=1))


@pytest.mark.parametrize("markdown", ["***", "---", "___", " - - -"])
def test_horizontal_rules(markdown):
    assert convert(f"text\n\n{markdown}\n") == doc(para(text("text"), line=1), rule(line=3))


# --- marks ---------------------------------------------------------------------------


def test_simple_marks():
    assert only_inline("**b** *i* ~~s~~ `c`") == [
        text("b", STRONG), text(" "), text("i", EM), text(" "), text("s", STRIKE), text(" "), text("c", CODE),
    ]


def test_marks_are_sorted_in_schema_order():
    assert only_inline("***both***") == [text("both", STRONG, EM)]
    assert only_inline("~~**x**~~") == [text("x", STRONG, STRIKE)]


def test_nested_marks_split_text():
    assert only_inline("**a *b* c**") == [text("a ", STRONG), text("b", STRONG, EM), text(" c", STRONG)]


def test_code_span_keeps_outer_marks_and_raw_text():
    assert only_inline("**`a &amp; *b*`**") == [text("a &amp; *b*", STRONG, CODE)]


def test_code_span_line_ending_becomes_space():
    assert only_inline("`a\nb`") == [text("a b", CODE)]


# --- links ---------------------------------------------------------------------------


def test_inline_link_with_and_without_title():
    assert only_inline('[a](http://x "T") [b](y)') == [
        text("a", link("http://x", "T")), text(" "), text("b", link("y")),
    ]


def test_link_title_entities_are_decoded():
    assert only_inline('[a](u "x &amp; y")') == [text("a", link("u", "x & y"))]


def test_marks_inside_and_around_links():
    assert only_inline("[**b** l](u) **[in](v)**") == [
        text("b", STRONG, link("u")), text(" l", link("u")), text(" "), text("in", STRONG, link("v")),
    ]


def test_autolinks():
    assert only_inline("<http://a.b> <a@b.co> https://x.y/z.") == [
        text("http://a.b", link("http://a.b")), text(" "),
        text("a@b.co", link("mailto:a@b.co")), text(" "),
        text("https://x.y/z", link("https://x.y/z")), text("."),
    ]


def test_reference_links_become_inline_links():
    assert convert('[t][r] and [r]\n\n[r]: http://r "RT"\n') == doc(
        para(text("t", link("http://r", "RT")), text(" and "), text("r", link("http://r", "RT")), line=1)
    )


@pytest.mark.parametrize("markdown", [
    "[a](javascript:alert(1))",
    "[a](JAVASCRIPT:alert(1))",
    "[a](javascript&#58;alert(1))",
    "[a](vbscript:msgbox)",
    "[a](data:text/html,x)",
    "<javascript:alert(1)>",
])
def test_unsafe_links_keep_text_without_link(markdown):
    [node] = only_inline(markdown)
    assert "marks" not in node


def test_image_data_url_link_is_kept():
    assert only_inline("[a](data:image/png;base64,AA)") == [text("a", link("data:image/png;base64,AA"))]


# --- text decoding -------------------------------------------------------------------


def test_entities_are_decoded_strictly():
    assert only_inline("a &amp; b &copy; &#35; &#x41; &nosuch; AT&T &copy") == [
        text("a & b © # A &nosuch; AT&T &copy")
    ]


def test_backslash_escapes():
    assert only_inline("\\*not em\\* \\&amp;") == [text("*not em* &amp;")]


# --- front matter and line numbers ---------------------------------------------------------


def test_front_matter_node_and_line_offset():
    front = "---\na: 1\n---\n"
    assert convert("# T\n", front) == doc(
        {"type": "front_matter", "attrs": {"source": front, "line": 1}},
        heading(1, text("T"), line=4),
    )


def test_front_matter_only_adds_an_empty_paragraph():
    front = "---\na: 1\n---\n"
    assert convert("", front) == doc(
        {"type": "front_matter", "attrs": {"source": front, "line": 1}}, para(line=4)
    )


def test_top_level_lines_follow_the_source():
    markdown = "Title\n=====\n\n\n> quote\nlazy\n\n[r]: http://x\npara\n\n***\n"
    assert [block["attrs"]["line"] for block in convert(markdown)["content"]] == [1, 5, 9, 11]


# --- fallback: unmappable blocks are kept as source -------------------------------------------


def test_unmappable_top_level_block_keeps_its_source(monkeypatch):
    monkeypatch.delitem(docmodel._BLOCKS, "block_quote")
    assert convert("> a\n> b\n\nafter\n") == doc(
        {"type": "html_block", "attrs": {"source": "> a\n> b", "line": 1}},
        para(text("after"), line=4),
    )


def test_unmappable_nested_block_protects_the_whole_top_level_block(monkeypatch):
    monkeypatch.delitem(docmodel._BLOCKS, "thematic_break")
    assert convert("> a\n>\n> ***\n\nz\n") == doc(
        {"type": "html_block", "attrs": {"source": "> a\n>\n> ***", "line": 1}},
        para(text("z"), line=5),
    )


def test_unmappable_inline_protects_its_block(monkeypatch):
    monkeypatch.delitem(docmodel._SIMPLE_MARKS, "strikethrough")
    assert convert("# H\n\na ~~b~~ c\n") == doc(
        heading(1, text("H"), line=1),
        {"type": "html_block", "attrs": {"source": "a ~~b~~ c", "line": 3}},
    )


def test_unmappable_block_absorbs_a_following_reference_definition(monkeypatch):
    monkeypatch.delitem(docmodel._BLOCKS, "block_quote")
    assert convert("> [a][r]\n[r]: http://x\n\nz\n")["content"][0] == {
        "type": "html_block", "attrs": {"source": "> [a][r]\n[r]: http://x", "line": 1},
    }


def test_documents_with_footnotes_convert():
    assert convert("A[^1]\n\n[^1]: note\n")["content"][0]["attrs"]["line"] == 1
