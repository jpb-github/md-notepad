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


# === Task 5: lists, code, tables, images, raw HTML, footnotes ===============================

from pathlib import Path  # noqa: E402

from mdviewer.core import frontmatter  # noqa: E402
from mdviewer.core.render import highlight_code  # noqa: E402


def convert_in(markdown, base_dir):
    doc = docmodel.from_markdown(markdown, None, base_dir)
    assert validate(doc) == []
    return doc


def bullets(*items, tight=True, line=None):
    return {"type": "bullet_list", "attrs": {"tight": tight, "line": line}, "content": list(items)}


def numbers(*items, start=1, tight=True, line=None):
    return {"type": "ordered_list", "attrs": {"start": start, "tight": tight, "line": line}, "content": list(items)}


def item(*blocks, checked=None):
    return {"type": "list_item", "attrs": {"checked": checked}, "content": list(blocks)}


def code(value, language="", line=None):
    node = {"type": "code_block",
            "attrs": {"language": language, "highlight": highlight_code(value, language), "line": line}}
    if value:
        node["content"] = [text(value)]
    return node


def cell(kind, *inline, align=None):
    node = {"type": kind, "attrs": {"align": align}}
    if inline:
        node["content"] = list(inline)
    return node


def row(*cells):
    return {"type": "table_row", "content": list(cells)}


def table(*rows, line=None):
    return {"type": "table", "attrs": {"line": line}, "content": list(rows)}


def image(src, display_src=None, alt="", title=None, marks=()):
    attrs = {"src": src, "display_src": src if display_src is None else display_src, "alt": alt, "title": title}
    node = {"type": "image", "attrs": attrs}
    if marks:
        node["marks"] = list(marks)
    return node


def html_block(source, line=None):
    return {"type": "html_block", "attrs": {"source": source, "line": line}}


def html_inline(source, *marks):
    node = {"type": "html_inline", "attrs": {"source": source}}
    if marks:
        node["marks"] = list(marks)
    return node


def footnote_ref(label):
    return {"type": "footnote_ref", "attrs": {"label": label}}


def footnote_def(label, source, line):
    return {"type": "footnote_def", "attrs": {"label": label, "source": source, "line": line}}


# --- lists -------------------------------------------------------------------------------


def test_tight_bullet_list_with_nested_list():
    assert convert("- a\n- b\n  - c\n") == doc(bullets(
        item(para(text("a"))),
        item(para(text("b")), bullets(item(para(text("c"))))),
        line=1,
    ))


def test_loose_ordered_list():
    assert convert("1. a\n\n2. b\n") == doc(
        numbers(item(para(text("a"))), item(para(text("b"))), tight=False, line=1)
    )


def test_ordered_list_start():
    assert convert("3) x\n4) y\n") == doc(numbers(item(para(text("x"))), item(para(text("y"))), start=3, line=1))


def test_task_items():
    assert convert("- [ ] todo\n- [x] done\n- [X] caps\n- plain\n") == doc(bullets(
        item(para(text("todo")), checked=False),
        item(para(text("done")), checked=True),
        item(para(text("caps")), checked=True),
        item(para(text("plain"))),
        line=1,
    ))


def test_empty_list_item_gets_an_empty_paragraph():
    assert convert("-\n- b\n") == doc(bullets(item(para()), item(para(text("b"))), line=1))


def test_list_item_with_several_blocks():
    assert convert("- a\n\n  para\n\n      code\n") == doc(bullets(
        item(para(text("a")), para(text("para")), code("code")), tight=False, line=1,
    ))


def test_list_lines_with_an_interrupting_heading():
    assert [block["attrs"]["line"] for block in convert("- a\n- b\n# H\n")["content"]] == [1, 3]


# --- code blocks ---------------------------------------------------------------------------


def test_fenced_code_keeps_text_and_first_info_word():
    assert convert("```python title=x\nprint(1)\n\n```\n") == doc(code("print(1)\n", "python", line=1))


def test_fenced_code_highlight_is_precomputed():
    [block] = convert("```python\nprint(1)\n```\n")["content"]
    assert '<span class="nb">print</span>' in block["attrs"]["highlight"]


def test_empty_fence():
    assert convert("```\n```\n") == doc(code("", line=1))


def test_tilde_fence():
    assert convert("~~~js\nx\n~~~\n") == doc(code("x", "js", line=1))


def test_indented_code():
    assert convert("    a\n      b\n") == doc(code("a\n  b", line=1))


def test_unknown_language_has_no_highlight():
    assert convert("```nosuchlang\nx\n```\n")["content"][0]["attrs"]["highlight"] == ""


def test_code_text_is_not_decoded():
    assert convert("```\n&amp; <b>\n```\n") == doc(code("&amp; <b>", line=1))


# --- tables --------------------------------------------------------------------------------


def test_table_with_alignment():
    markdown = "| a | b | c | d |\n|:--|:-:|--:|---|\n| 1 | 2 | 3 | 4 |\n"
    aligns = ["left", "center", "right", None]
    assert convert(markdown) == doc(table(
        row(*(cell("table_header", text(name), align=a) for name, a in zip("abcd", aligns))),
        row(*(cell("table_cell", text(value), align=a) for value, a in zip("1234", aligns))),
        line=1,
    ))


def test_table_with_header_only():
    assert convert("| a |\n|---|\n") == doc(table(row(cell("table_header", text("a"))), line=1))


def test_table_cells_keep_marks_and_unescape_pipes_in_code():
    assert convert("| `a\\|b` | **x** |\n|---|---|\n| c | |\n") == doc(table(
        row(cell("table_header", text("a|b", CODE)), cell("table_header", text("x", STRONG))),
        row(cell("table_cell", text("c")), cell("table_cell")),
        line=1,
    ))


def test_ragged_table_is_kept_as_source(monkeypatch):
    original = docmodel._table_row

    def drop_last_body_cell(ctx, cells, kind):
        node = original(ctx, cells, kind)
        if kind == "table_cell":
            node["content"].pop()
        return node

    monkeypatch.setattr(docmodel, "_table_row", drop_last_body_cell)
    assert convert("a | b\n--|--\n1 | 2\n") == doc(html_block("a | b\n--|--\n1 | 2", line=1))


# --- images ---------------------------------------------------------------------------------


def test_image_resolves_display_src_and_flattens_alt(tmp_path):
    [node] = convert_in('![alt *em* `c`](<a b.png> "T")', tmp_path)["content"][0]["content"]
    assert node == image("a%20b.png", (tmp_path / "a b.png").as_uri(), "alt em c", "T")


def test_image_without_base_dir_keeps_src():
    assert only_inline("![x](img/a.png)") == [image("img/a.png", alt="x")]


def test_web_and_drive_letter_images(tmp_path):
    inline = convert_in("![w](https://x.y/a.png) ![d](C:/pics/b.png)", tmp_path)["content"][0]["content"]
    assert inline[0] == image("https://x.y/a.png", alt="w")
    assert inline[2] == image("C:/pics/b.png", Path("C:/pics/b.png").as_uri(), "d")


def test_linked_badge_image():
    assert only_inline("[![ci](b.svg)](http://x)") == [image("b.svg", alt="ci", marks=[link("http://x")])]


def test_reference_image():
    assert only_inline("![r][i]\n\n[i]: c.png 'T'") == [image("c.png", alt="r", title="T")]


def test_unsafe_image_keeps_its_alt_text():
    assert only_inline("a ![x](javascript:y) b") == [text("a x b")]
    assert convert("![](javascript:y)") == doc(para(line=1))


# --- raw HTML --------------------------------------------------------------------------------


def test_html_blocks_keep_source_without_trailing_newline():
    assert convert("<div>\n*x*\n</div>\n\n<!-- c -->\n") == doc(
        html_block("<div>\n*x*\n</div>", line=1), html_block("<!-- c -->", line=5)
    )


def test_inline_html_keeps_marks():
    assert only_inline("**a <b>x</b>** <!-- y -->") == [
        text("a ", STRONG), html_inline("<b>", STRONG), text("x", STRONG), html_inline("</b>", STRONG),
        text(" "), html_inline("<!-- y -->"),
    ]


# --- footnotes -------------------------------------------------------------------------------


def test_footnote_refs_and_definitions():
    markdown = "A[^1] B[^note] C[^1]\n\n[^1]: first\n    more\n\n[^note]: second *em*\n\n[^unused]: never\n"
    assert convert(markdown) == doc(
        para(text("A"), footnote_ref("1"), text(" B"), footnote_ref("note"), text(" C"), footnote_ref("1"), line=1),
        footnote_def("1", "[^1]: first\n    more", 3),
        footnote_def("note", "[^note]: second *em*", 6),
        footnote_def("unused", "[^unused]: never", 8),
    )


def test_footnote_ref_uses_the_label_of_its_definition():
    assert convert("X[^Note]\n\n[^note]: y\n")["content"][0]["content"] == [text("X"), footnote_ref("note")]


def test_undefined_footnote_ref_stays_text():
    assert only_inline("X[^nope]") == [text("X[^nope]")]


def test_footnote_definitions_follow_source_order():
    content = convert("[^b]: B\n\n[^a]: A\n\nx[^a][^b]\n")["content"]
    assert [block["type"] for block in content] == ["paragraph", "footnote_def", "footnote_def"]
    assert content[0]["attrs"]["line"] == 5
    assert [block["attrs"]["label"] for block in content[1:]] == ["b", "a"]


def test_first_footnote_definition_wins():
    assert convert("x[^a]\n\n[^a]: one\n\n[^a]: two\n")["content"][1:] == [footnote_def("a", "[^a]: one", 3)]


def test_footnote_only_document_gets_an_empty_paragraph():
    assert convert("[^a]: x\n") == doc(para(line=1), footnote_def("a", "[^a]: x", 1))


def test_front_matter_shifts_footnote_lines():
    content = convert("x[^a]\n\n[^a]: n\n", "---\na: 1\n---\n")["content"]
    assert [block["attrs"]["line"] for block in content] == [1, 4, 6]


def test_fallback_source_stops_at_a_footnote_definition(monkeypatch):
    monkeypatch.delitem(docmodel._BLOCKS, "block_code")
    assert convert("```\nx\n```\n[^a]: n\n\ny[^a]\n")["content"] == [
        html_block("```\nx\n```", line=1),
        para(text("y"), footnote_ref("a"), line=6),
        footnote_def("a", "[^a]: n", 4),
    ]


# --- whole documents -------------------------------------------------------------------------


def test_repo_documents_map_without_fallback():
    """Every construct in the project's own docs has a node; html_block only holds real HTML."""
    root = Path(__file__).resolve().parent.parent
    paths = [root / "README.md", *sorted((root / "docs").rglob("*.md"))]
    assert len(paths) >= 5
    for path in paths:
        front, body = frontmatter.split(path.read_text(encoding="utf-8").replace("\r\n", "\n"))
        for block in convert(body, front)["content"]:
            if block["type"] == "html_block":
                assert block["attrs"]["source"].lstrip().startswith("<"), (path, block["attrs"]["line"])
