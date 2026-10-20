import random
from pathlib import Path

import pytest

from mdviewer.core import frontmatter
from mdviewer.core.docmodel import from_markdown
from mdviewer.core.serialize import front_matter, to_markdown, to_text


def doc(*blocks):
    return {"type": "doc", "content": list(blocks)}


def para(*inline, line=None):
    node = {"type": "paragraph", "attrs": {"line": line}}
    if inline:
        node["content"] = list(inline)
    return node


def heading(level, *inline):
    node = {"type": "heading", "attrs": {"level": level, "line": None}}
    if inline:
        node["content"] = list(inline)
    return node


def quote(*blocks):
    return {"type": "blockquote", "attrs": {"line": None}, "content": list(blocks)}


def rule():
    return {"type": "horizontal_rule", "attrs": {"line": None}}


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


def inline_md(*inline):
    """Markdown for a one-paragraph document, without the final newline."""
    out = to_markdown(doc(para(*inline)))
    assert out.endswith("\n") and not out.endswith("\n\n")
    return out[:-1]


def round_trip(markdown):
    return to_markdown(from_markdown(markdown))


def without_lines(node):
    """The node with every line attr set to None (line numbers move when text is normalized)."""
    copy = dict(node)
    if "attrs" in copy and "line" in copy["attrs"]:
        copy["attrs"] = {**copy["attrs"], "line": None}
    if "content" in copy:
        copy["content"] = [without_lines(child) for child in copy["content"]]
    return copy


# --- documents and blocks ---------------------------------------------------------------


@pytest.mark.parametrize("body", [doc(para()), doc(para(), para()), from_markdown(""), from_markdown("\n\n")])
def test_empty_body_is_the_empty_string(body):
    assert to_markdown(body) == ""


def test_blocks_are_separated_by_one_blank_line_and_end_with_one_newline():
    assert to_markdown(doc(para(text("a"), line=1), heading(2, text("b")), rule(), para(text("c")))) == (
        "a\n\n## b\n\n---\n\nc\n"
    )


def test_empty_paragraphs_are_dropped():
    assert to_markdown(doc(para(text("a")), para(), para(hard_break()), para(text("b")))) == "a\n\nb\n"


@pytest.mark.parametrize("level", [1, 2, 3, 4, 5, 6])
def test_atx_headings(level):
    assert to_markdown(doc(heading(level, text("Title")))) == "#" * level + " Title\n"


def test_empty_heading():
    assert to_markdown(doc(heading(3))) == "###\n"


def test_setext_heading_becomes_atx():
    assert round_trip("Title\n=====\n\nSub\n---\n") == "# Title\n\n## Sub\n"


def test_hard_break_in_heading_becomes_a_space():
    assert to_markdown(doc(heading(1, text("a"), hard_break(), text("b")))) == "# a b\n"


@pytest.mark.parametrize("content, expected", [
    ("C#", "# C#"),
    ("a #", "# a \\#"),
    ("#", "# \\#"),
    ("a ##  ", "# a \\##"),
    ("# b", "# # b"),
    ("- not a list", "# - not a list"),
])
def test_heading_text_escapes_only_a_closing_sequence(content, expected):
    assert to_markdown(doc(heading(1, text(content)))) == expected + "\n"


def test_blockquote_with_several_paragraphs():
    assert to_markdown(doc(quote(para(text("a")), para(text("b"))))) == "> a\n>\n> b\n"


def test_nested_blockquote_and_hard_break_inside():
    assert to_markdown(doc(quote(quote(para(text("a"), hard_break(), text("b")))))) == "> > a\\\n> > b\n"


def test_empty_blockquote():
    assert to_markdown(doc(quote(para()))) == ">\n"


def test_horizontal_rule_and_line_attrs_are_ignored():
    assert to_markdown(doc({"type": "horizontal_rule", "attrs": {"line": 7}})) == "---\n"


def test_unknown_block_raises():
    with pytest.raises(ValueError, match="'callout'"):
        to_markdown(doc({"type": "callout"}))


def test_unknown_inline_node_raises():
    with pytest.raises(ValueError, match="'widget'"):
        to_markdown(doc(para(text("a"), {"type": "widget"})))


# --- front matter ---------------------------------------------------------------------------

FRONT = {"type": "front_matter", "attrs": {"source": "---\ntitle: x\n---\n", "line": 1}}


def test_body_excludes_front_matter():
    assert to_markdown(doc(FRONT, para(text("a")))) == "a\n"


def test_front_matter_source_is_returned_verbatim():
    assert front_matter(doc(FRONT, para())) == "---\ntitle: x\n---\n"
    assert front_matter(doc(para(text("a")))) is None


def test_to_text_joins_front_matter_and_body():
    assert to_text(doc(FRONT, heading(1, text("Hi")))) == "---\ntitle: x\n---\n# Hi\n"
    assert to_text(doc(FRONT, para())) == "---\ntitle: x\n---\n"
    assert to_text(doc(para(text("a")))) == "a\n"


def test_to_text_adds_a_newline_after_front_matter_that_ended_the_file():
    front = {"type": "front_matter", "attrs": {"source": "---\na: 1\n---", "line": 1}}
    assert to_text(doc(front, para())) == "---\na: 1\n---"
    assert to_text(doc(front, para(text("x")))) == "---\na: 1\n---\nx\n"


def test_to_text_round_trips_a_file_with_front_matter():
    source = "---\ntitle: x\n---\n# Hi\n\nText\n"
    front, body = frontmatter.split(source)
    assert to_text(from_markdown(body, front)) == source


# --- marks ---------------------------------------------------------------------------------


def test_simple_marks():
    assert inline_md(text("b", STRONG), text(" "), text("i", EM), text(" "), text("s", STRIKE), text(" "),
                     text("c", CODE)) == "**b** *i* ~~s~~ `c`"


@pytest.mark.parametrize("markdown", [
    "***both***",
    "**a *b* c**",
    "*a **b** c*",
    "~~**x**~~ ~~a *b*~~",
    "**a**b and a**b**c",
    "*a***b**",
    "**a***b*",
    "**`x`** and [`y`](u)",
])
def test_nested_and_adjacent_marks_keep_their_markdown(markdown):
    assert round_trip(markdown) == markdown + "\n"


def test_whitespace_moves_outside_delimiters():
    assert inline_md(text("a"), text(" bold ", STRONG), text("b")) == "a **bold** b"
    assert inline_md(text("x "), text("y ", EM), text("z", EM, STRONG)) == "x *y **z***"


def test_spaces_and_tabs_at_line_edges_are_dropped():
    assert inline_md(text(" \t a  "), hard_break(), text("  b \t")) == "a\\\nb"


def test_newlines_in_text_become_spaces():
    assert inline_md(text("a\nb"), text("c\nd", CODE)) == "a b`c d`"


def test_hard_breaks():
    assert inline_md(text("a"), hard_break(), text("b"), hard_break(), hard_break(), text("c")) == "a\\\nb\\\n\\\nc"


def test_leading_hard_break_is_kept_and_trailing_ones_are_dropped():
    assert inline_md(hard_break(), text("a"), hard_break(), hard_break()) == "\\\na"


def test_hard_break_inside_marks():
    assert inline_md(text("a", STRONG), hard_break(STRONG), text("b", STRONG)) == "**a\\\nb**"


def test_whitespace_after_a_hard_break_is_written_as_an_entity():
    assert inline_md(text("a"), hard_break(), text("\xa0b")) == "a\\\n&nbsp;b"
    assert inline_md(text("a"), hard_break(), text("\u2003b")) == "a\\\n&#8195;b"


@pytest.mark.parametrize("code, expected", [
    ("a", "`a`"),
    ("a`b", "``a`b``"),
    ("a``b`", "``` a``b` ```"),
    ("`a", "`` `a ``"),
    (" a ", "`  a  `"),
    (" a", "` a`"),
    ("  ", "`  `"),
    ("*not em* &amp; \\", "`*not em* &amp; \\`"),
])
def test_code_spans(code, expected):
    assert inline_md(text(code, CODE)) == expected


# --- links ---------------------------------------------------------------------------------


def test_inline_links():
    assert inline_md(text("a", link("http://x", "T")), text(" "), text("b", link("y"))) == '[a](http://x "T") [b](y)'


def test_link_title_escapes_quotes_backslashes_and_entities():
    assert inline_md(text("a", link("u", 'say "hi" \\* &copy;'))) == '[a](u "say \\"hi\\" \\\\* &amp;copy;")'


@pytest.mark.parametrize("href, expected", [
    ("", "[a]()"),
    ("page.md#top", "[a](page.md#top)"),
    ("a b", "[a](<a b>)"),
    ("x<y>", "[a](<x\\<y\\>>)"),
    ("wiki/A_(b)", "[a](wiki/A_(b))"),
    ("a(b", "[a](a\\(b)"),
    ("a\\b", "[a](a\\b)"),
    ("a\\*b", "[a](a\\\\*b)"),
    ("q?x=1&copy;", "[a](q?x=1&amp;copy;)"),
])
def test_link_destinations(href, expected):
    assert inline_md(text("a", link(href))) == expected


def test_link_text_escapes_brackets():
    assert inline_md(text("a]b [c]", link("u")), text(" ]")) == "[a\\]b \\[c\\]](u) ]"


def test_link_is_outermost_and_splits_other_marks():
    assert inline_md(text("x", STRONG), text("y", STRONG, link("u")), text("z", STRONG)) == "**x**[**y**](u)**z**"
    assert inline_md(text("a", STRONG, EM, link("u"))) == "[***a***](u)"


def test_strike_is_outside_strong_and_em():
    assert inline_md(text("a", STRONG, STRIKE), text("b", STRONG)) == "~~**a**~~**b**"


@pytest.mark.parametrize("inline, expected", [
    ([text("see "), text("https://x.y/z", link("https://x.y/z")), text(".")], "see https://x.y/z."),
    ([text("https://x.y", link("https://x.y")), text("), next")], "https://x.y), next"),
    ([text("https://x.y", link("https://x.y")), text("abc")], "<https://x.y>abc"),
    ([text("https://x.y", link("https://x.y")), text(".x")], "<https://x.y>.x"),
    ([text("https://x.y", link("https://x.y")), hard_break(), text("b")], "<https://x.y>\\\nb"),
    ([text("https://x.y", link("https://x.y")), text("b", STRONG)], "<https://x.y>**b**"),
    ([text("https://x.y/a.", link("https://x.y/a."))], "<https://x.y/a.>"),
    ([text("mailto:a@b.co", link("mailto:a@b.co"))], "<mailto:a@b.co>"),
    ([text("a@b.co", link("mailto:a@b.co"))], "<a@b.co>"),
    ([text("https://x.y", link("https://x.y", "T"))], '[https\\://x.y](https://x.y "T")'),
    ([text("https://x.y", STRONG, link("https://x.y"))], "[**https\\://x.y**](https://x.y)"),
    ([text("x.y", link("https://x.y"))], "[x.y](https://x.y)"),
])
def test_autolinks(inline, expected):
    assert inline_md(*inline) == expected


def test_autolinks_round_trip():
    markdown = "Bare https://x.y/z. Angle <http://a.b> and <a@b.co>.\n"
    assert round_trip(markdown) == "Bare https://x.y/z. Angle http://a.b and <a@b.co>.\n"


# --- escaping ------------------------------------------------------------------------------


@pytest.mark.parametrize("value, expected", [
    ("2 * 3 = 6", "2 \\* 3 = 6"),
    ("snake_case_name", "snake_case_name"),
    ("_x_ and x_", "\\_x\\_ and x\\_"),
    ("a ~ b", "a ~ b"),
    ("~~x~~", "\\~\\~x\\~\\~"),
    ("`x`", "\\`x\\`"),
    ("[x] and a]b", "\\[x] and a]b"),
    ("C:\\Users\\me", "C:\\Users\\me"),
    ("a\\*b", "a\\\\\\*b"),
    ("ends with \\", "ends with \\"),
    ("&copy; &amp; &#35; AT&T &nosemi", "\\&copy; \\&amp; \\&#35; AT&T &nosemi"),
    ("a < b <c> </d> <!x <?y", "a < b \\<c> \\</d> \\<!x \\<?y"),
    ("Wow! [", "Wow! \\["),
    ("see https://x.y or http://a", "see https\\://x.y or http\\://a"),
    ("100% | 1.5 kg", "100% | 1.5 kg"),
    ("# not a heading", "\\# not a heading"),
    ("###### six", "\\###### six"),
    ("####### seven", "####### seven"),
    ("#hashtag", "#hashtag"),
    ("- item", "\\- item"),
    ("+ item", "\\+ item"),
    ("-5 degrees", "-5 degrees"),
    ("1. one", "1\\. one"),
    ("2) two", "2\\) two"),
    ("2024.", "2024\\."),
    ("1.5", "1.5"),
    ("> quote", "\\> quote"),
    ("a > b", "a > b"),
    ("---", "\\---"),
    ("- - -", "\\- - -"),
    ("===", "\\==="),
])
def test_text_escaping(value, expected):
    assert inline_md(text(value)) == expected


@pytest.mark.parametrize("inline, expected", [
    ([text("x!"), text("a", link("u"))], "x\\![a](u)"),
    ([text("C:\\"), text("b", STRONG)], "C:\\\\**b**"),
    ([text("a\\"), hard_break(), text("b")], "a\\\\\\\nb"),
    ([text("x_"), text("b", EM)], "x\\_*b*"),
    ([text("a~"), text("b", STRIKE)], "a\\~~~b~~"),
    ([text("a<"), text("b", EM)], "a<*b*"),
    ([text("1."), text("x", EM)], "1.*x*"),
    ([text("-"), text("x", STRONG)], "-**x**"),
    ([text("-")], "\\-"),
    ([text("a"), hard_break(), text("# b")], "a\\\n\\# b"),
    ([text("a"), hard_break(), text("1) b")], "a\\\n1\\) b"),
    ([text("a"), hard_break(), text("===")], "a\\\n\\==="),
    ([text("a"), hard_break(), text("-=")], "a\\\n\\-="),
    ([text("a|b"), hard_break(), text("-|-")], "a|b\\\n\\-|-"),
    ([text("a|b"), hard_break(), text(":-:|-")], "a|b\\\n:\\-:|-"),
])
def test_context_sensitive_escaping(inline, expected):
    assert inline_md(*inline) == expected


@pytest.mark.parametrize("value", [
    "2 * 3", "_x_", "~~x~~", "`x`", "[x](y)", "![x](y)", "&copy; &amp;", "<b>x</b>", "<http://x>",
    "https://x.y", "# h", "- i", "+ i", "1. i", "1) i", "> q", "---", "***", "___", "===", "\\", "a\\b",
    "\\*", "[^1]", "x | y", "~a~", "a  b", "C:\\Users\\", "<!-- c -->", "1.", "#", "*", "_", "]", "!",
])
def test_escaped_text_parses_back_to_the_same_text(value):
    assert from_markdown(to_markdown(doc(para(text(value)))))["content"][0]["content"] == [text(value)]


# --- round trips ----------------------------------------------------------------------------


@pytest.mark.parametrize("markdown, expected", [
    ("Title\n===\n", "# Title\n"),
    ("#   Spaced   #\n", "# Spaced\n"),
    ("a  \nb\n", "a\\\nb\n"),
    ("line one\nline two\n", "line one line two\n"),
    ("* * *\n", "---\n"),
    ("> a\nlazy\n", "> a lazy\n"),
    ("[t][r]\n\n[r]: http://r 'T'\n", '[t](http://r "T")\n'),
    ("&copy; &#35; \\&copy;\n", "© # \\&copy;\n"),
    ("__strong__ _em_\n", "**strong** *em*\n"),
    ("\\# \\- \\> \\[x\\]\n", "\\# - > \\[x]\n"),
])
def test_normalizing_round_trips(markdown, expected):
    assert round_trip(markdown) == expected


SNIPPETS = [
    "Hello *world* and **bold** and ~~gone~~ and `code`.",
    "# Title\n\n## Sub *em*\n\nText.",
    "> quote\n>\n> > nested\n\n---\n\nafter",
    "Line one\\\nline two  \nline three",
    "A [link](http://x \"T\") and [another](<a b>) and https://bare.example/x.",
    "Escapes: \\* \\_ \\` \\[ \\] \\# \\\\ &amp; &lt;b&gt;",
    "**[bold link](u)** then *[em link](v)*",
    "C:\\Users\\me\\file.md and snake_case_word",
]


@pytest.mark.parametrize("markdown", SNIPPETS)
def test_serialized_documents_parse_back_unchanged(markdown):
    original = from_markdown(markdown)
    once = to_markdown(original)
    assert without_lines(from_markdown(once)) == without_lines(original)
    assert round_trip(once) == once


def test_repo_blocks_round_trip():
    """Every top-level block in the project's docs survives serialization on its own.

    The document's footnote definitions come along, so that its references stay references."""
    root = Path(__file__).resolve().parent.parent
    paths = [root / "README.md", *sorted((root / "docs").rglob("*.md"))]
    checked = 0
    for path in paths:
        front, body = frontmatter.split(path.read_text(encoding="utf-8").replace("\r\n", "\n"))
        blocks = from_markdown(body, front)["content"]
        notes = [block for block in blocks if block["type"] == "footnote_def"]
        for block in blocks:
            if block["type"] in ("front_matter", "footnote_def"):
                continue
            markdown = to_markdown(doc(block, *notes))
            expected = [without_lines(node) for node in (block, *notes)]
            assert without_lines(from_markdown(markdown))["content"] == expected, (path, markdown)
            checked += 1
    assert checked > 500


# --- random inline content ------------------------------------------------------------------
# Random paragraphs of tricky text under random marks must parse back to the same text and
# marks. Known limits, kept out of the generator (see the plan's Task 6 Review Focus):
# strong/em runs that start or end with punctuation or a code span next to a letter, and
# strong and em runs that touch or cross each other.

_TRICKY = list("ab ") * 4 + list("*_~`[]!<>&#\\-+=|:.()/1;\"' \t\xa0") + ["https://x.y", "&copy;", "<b>", "1. "]
_ALNUM = list("abcxyz019")
_LINKS = [link("https://x.y"), link("u%20v(", 'a "q" \\*'), link("a&amp;b*")]


def _random_inline(rng, flanked):
    nodes = []
    for _ in range(rng.randint(1, 6)):
        if rng.random() < 0.1:
            nodes.append(hard_break())
            continue
        marks = [mark for mark in (flanked, STRIKE) if rng.random() < 0.3]
        if rng.random() < 0.15:
            marks = [CODE]
        if rng.random() < 0.2:
            marks.append(rng.choice(_LINKS))
        body = "".join(rng.choice(_TRICKY) for _ in range(rng.randint(0, 5)))
        if CODE in marks or not ({flanked["type"], "strike"} & {mark["type"] for mark in marks}):
            value = body or rng.choice(_ALNUM)
        else:
            value = rng.choice(_ALNUM) + body + rng.choice(_ALNUM)
        if marks and marks[-1]["type"] == "link" and len(marks) == 1 and rng.random() < 0.3:
            value = marks[-1]["attrs"]["href"]
        nodes.append(text(value, *marks))
    return nodes


def _visible(inline):
    """Lines of (character, marks): what a reader sees. Edge spaces and tabs are dropped and
    whitespace never counts as strong/em/strike, the serializer's two normalizations."""
    lines = [[]]
    for node in inline:
        if node["type"] == "hard_break":
            lines.append([])
            continue
        marks = node.get("marks", [])
        for ch in node["text"].replace("\n", " "):
            kept = marks if CODE in marks or not ch.isspace() else [m for m in marks if m["type"] == "link"]
            lines[-1].append((ch, sorted(repr(mark) for mark in kept)))
    for line in lines:
        while line and line[0][0] in " \t" and repr(CODE) not in line[0][1]:
            line.pop(0)
        while line and line[-1][0] in " \t" and repr(CODE) not in line[-1][1]:
            line.pop()
    while lines and not lines[-1]:
        lines.pop()
    return lines


@pytest.mark.parametrize("flanked", [STRONG, EM], ids=["strong", "em"])
def test_random_inline_content_round_trips(flanked):
    rng = random.Random(6)
    for _ in range(1500):
        inline = _random_inline(rng, flanked)
        markdown = to_markdown(doc(para(*inline)))
        blocks = from_markdown(markdown)["content"]
        assert [block["type"] for block in blocks] == ["paragraph"], markdown
        assert _visible(blocks[0].get("content", [])) == _visible(inline), markdown
        assert round_trip(markdown) == (markdown or ""), markdown


# === Task 7: lists, code, tables, images, raw HTML, footnotes ===============================

from mdviewer.core.docschema import validate  # noqa: E402


def bullets(*items, tight=True):
    return {"type": "bullet_list", "attrs": {"tight": tight, "line": None}, "content": list(items)}


def ordered(*items, start=1, tight=True):
    return {"type": "ordered_list", "attrs": {"start": start, "tight": tight, "line": None}, "content": list(items)}


def item(*blocks, checked=None):
    return {"type": "list_item", "attrs": {"checked": checked}, "content": list(blocks) or [para()]}


def code_block(code, language="", highlight=""):
    node = {"type": "code_block", "attrs": {"language": language, "highlight": highlight, "line": None}}
    if code:
        node["content"] = [text(code)]
    return node


def table(*rows):
    return {"type": "table", "attrs": {"line": None}, "content": list(rows)}


def row(*cells):
    return {"type": "table_row", "content": list(cells)}


def header(*inline, align=None):
    node = {"type": "table_header", "attrs": {"align": align}}
    if inline:
        node["content"] = list(inline)
    return node


def cell(*inline, align=None):
    node = {"type": "table_cell", "attrs": {"align": align}}
    if inline:
        node["content"] = list(inline)
    return node


def image(src, alt="", title=None, *marks):
    node = {"type": "image", "attrs": {"src": src, "display_src": "file:///ignored", "alt": alt, "title": title}}
    if marks:
        node["marks"] = list(marks)
    return node


def footnote_ref(label):
    return {"type": "footnote_ref", "attrs": {"label": label}}


def footnote_def(label, source):
    return {"type": "footnote_def", "attrs": {"label": label, "source": source, "line": None}}


def html_inline(source, *marks):
    node = {"type": "html_inline", "attrs": {"source": source}}
    if marks:
        node["marks"] = list(marks)
    return node


def html_block(source):
    return {"type": "html_block", "attrs": {"source": source, "line": None}}


def cell_md(*inline):
    """Markdown for a one-cell table's header cell, without the "| " and " |" around it."""
    out = to_markdown(doc(table(row(header(*inline)))))
    first = out.split("\n")[0]
    assert first.startswith("| ") and first.endswith(" |"), out
    return first[2:-2]


# --- lists ---------------------------------------------------------------------------------


def test_tight_bullet_list_with_nested_list():
    assert to_markdown(doc(bullets(item(para(text("a"))), item(para(text("b")), bullets(item(para(text("c")))))))) == (
        "- a\n- b\n  - c\n"
    )


def test_loose_list():
    assert to_markdown(doc(bullets(item(para(text("a"))), item(para(text("b"))), tight=False))) == "- a\n\n- b\n"


def test_loose_item_with_two_paragraphs():
    assert to_markdown(doc(bullets(item(para(text("a")), para(text("b"))), tight=False))) == "- a\n\n  b\n"


@pytest.mark.parametrize("start, expected", [(1, "1. a\n2. b\n"), (3, "3. a\n4. b\n"), (0, "0. a\n1. b\n")])
def test_ordered_list_counts_from_start(start, expected):
    assert to_markdown(doc(ordered(item(para(text("a"))), item(para(text("b"))), start=start))) == expected


def test_nested_lines_indent_to_each_items_content_column():
    nested = bullets(item(para(text("c"), hard_break(), text("d"))))
    assert to_markdown(doc(ordered(item(para(text("a"))), item(para(text("b")), nested), start=9))) == (
        "9. a\n10. b\n    - c\\\n      d\n"
    )


def test_task_items():
    assert to_markdown(doc(bullets(item(para(text("a")), checked=False), item(para(text("b")), checked=True)))) == (
        "- [ ] a\n- [x] b\n"
    )


def test_task_item_without_text_has_the_box_on_its_own_line():
    assert to_markdown(doc(bullets(item(para(), checked=False)))) == "- [ ]\n"
    assert to_markdown(doc(bullets(item(code_block("x"), checked=True)))) == "- [x]\n  ```\n  x\n  ```\n"


def test_empty_items():
    assert to_markdown(doc(bullets(item(para()), item(para(text("b")))))) == "-\n- b\n"
    assert to_markdown(doc(ordered(item(para())))) == "1.\n"


def test_list_item_text_that_looks_like_markup_is_escaped():
    assert to_markdown(doc(bullets(item(para(text("- x"))), item(para(text("[ ] y")))))) == "- \\- x\n- \\[ ] y\n"


def test_adjacent_lists_of_the_same_kind_alternate_markers():
    three = doc(bullets(item(para(text("a")))), bullets(item(para(text("b")))), bullets(item(para(text("c")))))
    assert to_markdown(three) == "- a\n\n* b\n\n- c\n"
    assert to_markdown(doc(ordered(item(para(text("a")))), ordered(item(para(text("b"))), start=5))) == (
        "1. a\n\n5) b\n"
    )
    assert to_markdown(doc(bullets(item(para(text("a")))), para(), ordered(item(para(text("b")))))) == (
        "- a\n\n1. b\n"
    )


def test_adjacent_lists_in_a_quote_and_in_an_item():
    assert to_markdown(doc(quote(bullets(item(para(text("a")))), bullets(item(para(text("b"))))))) == (
        "> - a\n>\n> * b\n"
    )
    inner = item(para(text("x")), bullets(item(para(text("a")))), bullets(item(para(text("b")))))
    assert to_markdown(doc(bullets(inner))) == "- x\n  - a\n  * b\n"


def test_rule_that_opens_an_item():
    assert to_markdown(doc(bullets(item(rule())))) == "- ___\n"


def test_nested_items_without_text_do_not_form_a_rule():
    assert to_markdown(doc(bullets(item(bullets(item(bullets(item(para())))))))) == "-\n  - -\n"


@pytest.mark.parametrize("blocks, expected", [
    ([para(text("a")), code_block("x")], "- a\n  ```\n  x\n  ```\n"),
    ([para(text("a")), rule()], "- a\n  ___\n"),
    ([para(text("a")), quote(para(text("q")))], "- a\n  > q\n"),
    ([para(text("a")), heading(2, text("h"))], "- a\n  ## h\n"),
    ([para(text("a")), bullets(item(para(text("b"))))], "- a\n  - b\n"),
    ([para(text("a")), ordered(item(para(text("b"))))], "- a\n  1. b\n"),
    ([heading(1, text("h")), para(text("a"))], "- # h\n  a\n"),
    ([code_block("x"), para(text("a"))], "- ```\n  x\n  ```\n  a\n"),
    ([quote(para(text("q"))), code_block("x")], "- > q\n  ```\n  x\n  ```\n"),
])
def test_tight_item_blocks_follow_line_by_line(blocks, expected):
    assert to_markdown(doc(bullets(item(*blocks)))) == expected


@pytest.mark.parametrize("blocks, expected", [
    ([para(text("a")), para(text("b"))], "- a\n\n  b\n"),
    ([para(text("a")), rule(), para(text("b"))], "- a\n\n  ---\n\n  b\n"),
    ([para(text("a")), html_block("<div>x</div>")], "- a\n\n  <div>x</div>\n"),
    ([para(text("a")), ordered(item(para(text("b"))), start=3)], "- a\n\n  3. b\n"),
    ([para(text("a")), bullets(item(para()), item(para(text("b"))))], "- a\n\n  -\n  - b\n"),
    ([quote(para(text("q"))), para(text("a"))], "- > q\n\n  a\n"),
    ([quote(para(text("q"))), heading(1, text("h"))], "- > q\n\n  # h\n"),
    ([quote(para(text("q"))), bullets(item(para(text("b"))))], "- > q\n\n  - b\n"),
    ([quote(para(text("a"))), quote(para(text("b")))], "- > a\n\n  > b\n"),
    ([para(text("a")), bullets(item(para(text("b")))), para(text("c"))], "- a\n\n  - b\n\n  c\n"),
])
def test_tight_list_is_written_loose_when_an_item_cannot_be_tight(blocks, expected):
    markdown = to_markdown(doc(bullets(item(*blocks))))
    assert markdown == expected
    assert from_markdown(markdown)["content"][0]["attrs"]["tight"] is False


def test_task_box_line_follows_the_same_rules():
    assert to_markdown(doc(bullets(item(rule(), checked=True)))) == "- [x]\n  ___\n"
    assert to_markdown(doc(bullets(item(html_block("<br>"), checked=True)))) == "- [x]\n\n  <br>\n"
    assert to_markdown(doc(bullets(item(code_block("x"), para(text("a")), checked=True)))) == (
        "- [x]\n\n  ```\n  x\n  ```\n\n  a\n"
    )


@pytest.mark.parametrize("blocks", [
    [para(text("a"))],
    [bullets(item(para(text("a")))), heading(1, text("h"))],
])
def test_loose_list_is_written_tight_when_mistune_would_read_it_tight(blocks):
    markdown = to_markdown(doc(bullets(item(*blocks), tight=False)))
    assert "\n\n" not in markdown
    assert from_markdown(markdown)["content"][0]["attrs"]["tight"] is True


@pytest.mark.parametrize("markdown", [
    "- a\n- b\n  - c\n    - d\n",
    "- a\n\n- b\n",
    "1. a\n\n   b\n\n2. c\n",
    "3. a\n4. b\n",
    "- [ ] a\n- [x] b\n  - [ ] c\n",
    "- [x]\n  ```\n  x\n  ```\n",
    "-\n- b\n",
    "- a\n  - b\n\n  - c\n- d\n",
    "10. a\n11. b\n    - c\n",
    "- a\n\n* b\n",
    "1. a\n\n1) b\n",
    "> - a\n> - b\n>\n> 1. c\n",
    "- ___\n- a\n  ___\n",
    "- # h\n  text\n- > q\n  ```py\n  x\n  ```\n",
    "- <div>x</div>\n- b\n",
])
def test_lists_keep_their_markdown(markdown):
    assert round_trip(markdown) == markdown


@pytest.mark.parametrize("markdown, expected", [
    ("* a\n* b\n", "- a\n- b\n"),
    ("+ a\n\n* b\n", "- a\n\n* b\n"),
    ("1) a\n2) b\n", "1. a\n2. b\n"),
    ("- [X] done\n", "- [x] done\n"),
    ("- ***\n", "- ___\n"),
    ("-   wide\n    marker\n", "- wide marker\n"),
    ("2. a\n2. b\n2. c\n", "2. a\n3. b\n4. c\n"),
])
def test_normalizing_list_round_trips(markdown, expected):
    assert round_trip(markdown) == expected


# --- code blocks ---------------------------------------------------------------------------


def test_fenced_code_block_with_language():
    assert to_markdown(doc(code_block("x = 1\nprint(x)", "python", '<span class="n">x</span>'))) == (
        "```python\nx = 1\nprint(x)\n```\n"
    )


def test_empty_code_block():
    assert to_markdown(doc(code_block(""))) == "```\n```\n"
    assert to_markdown(doc(code_block("", "js"))) == "```js\n```\n"


def test_code_keeps_blank_lines_and_a_trailing_newline():
    assert to_markdown(doc(code_block("\na\n\nb\n"))) == "```\n\na\n\nb\n\n```\n"


@pytest.mark.parametrize("code, fence", [
    ("x = `y`", "```"),
    ("```", "````"),
    ("a\n````\nb", "`````"),
    ("~~~", "```"),
])
def test_fence_is_longer_than_any_backtick_run(code, fence):
    assert to_markdown(doc(code_block(code))) == f"{fence}\n{code}\n{fence}\n"


@pytest.mark.parametrize("language, expected", [
    ("py thon", "```py\nx\n```\n"),
    ("  rust  ", "```rust\nx\n```\n"),
    ("c\\+\\+", "```c\\\\+\\\\+\nx\n```\n"),
    ("a`b", "~~~a`b\nx\n~~~\n"),
    ("a&amp;b", "```a&amp;b\nx\n```\n"),
])
def test_code_language(language, expected):
    assert to_markdown(doc(code_block("x", language))) == expected


def test_code_in_a_list_item_and_a_quote_indents_every_line():
    assert to_markdown(doc(bullets(item(code_block("a\n\n  b"))))) == "- ```\n  a\n\n    b\n  ```\n"
    assert to_markdown(doc(quote(code_block("a\n\nb")))) == "> ```\n> a\n>\n> b\n> ```\n"


@pytest.mark.parametrize("markdown, expected", [
    ("    indented\n    code\n", "```\nindented\ncode\n```\n"),
    ("~~~\nx\n~~~\n", "```\nx\n```\n"),
    ("```python title=x\nx\n```\n", "```python\nx\n```\n"),
    ("```\nx\n", "```\nx\n```\n"),
    ("~~~ a`b\nx\n~~~\n", "~~~a`b\nx\n~~~\n"),
    ("````\n```\n````\n", "````\n```\n````\n"),
])
def test_code_block_round_trips(markdown, expected):
    assert round_trip(markdown) == expected


# --- tables --------------------------------------------------------------------------------


def test_table_with_alignment():
    markdown = to_markdown(doc(table(
        row(header(text("L"), align="left"), header(text("C"), align="center"), header(text("R"), align="right"),
            header(text("N"))),
        row(cell(text("1"), align="left"), cell(text("2", STRONG), align="center"), cell(align="right"), cell()),
    )))
    assert markdown == "| L | C | R | N |\n| :--- | :---: | ---: | --- |\n| 1 | **2** |  |  |\n"


def test_short_rows_are_padded_and_the_first_row_is_the_header():
    assert to_markdown(doc(table(row(cell(text("a"))), row(cell(text("b")), cell(text("c")))))) == (
        "| a |  |\n| --- | --- |\n| b | c |\n"
    )


@pytest.mark.parametrize("inline, expected", [
    ([text("a|b")], "a\\|b"),
    ([text("a\\|b")], "a\\\\\\|b"),
    ([text("x|y", CODE)], "`x\\|y`"),
    ([text("l", link("u|v", "t|"))], '[l](u\\|v "t\\|")'),
    ([text("https://x.y/a|b", link("https://x.y/a|b"))], "[https\\://x.y/a\\|b](https://x.y/a\\|b)"),
    ([text("https://x.y", link("https://x.y"))], "https://x.y"),
    ([image("a|b.png", "x|y")], "![x\\|y](a\\|b.png)"),
    ([html_inline('<a title="\\|">'), text("x"), html_inline("</a>")], '<a title="\\|">x</a>'),
])
def test_pipes_in_cells_are_escaped(inline, expected):
    assert cell_md(*inline) == expected


@pytest.mark.parametrize("inline, expected", [
    ([text("# x - y 1. z > q")], "# x - y 1. z > q"),
    ([text("---")], "---"),
    ([text("a"), hard_break(), text("b")], "a b"),
    ([html_inline("<a\nhref='x'>"), text("y")], "<a href='x'>y"),
    ([text("\xa0a\xa0")], "&nbsp;a&nbsp;"),
    ([text("a\\\xa0")], "a\\\\&nbsp;"),
    ([text("  a\t")], "a"),
])
def test_cell_text_is_one_line(inline, expected):
    assert cell_md(*inline) == expected


def test_empty_cells():
    assert to_markdown(doc(table(row(header(), header()), row(cell(), cell(text("x")))))) == (
        "|  |  |\n| --- | --- |\n|  | x |\n"
    )


@pytest.mark.parametrize("markdown, expected", [
    ("| a | b |\n|:-|-:|\n| 1 | 2 |\n", "| a | b |\n| :--- | ---: |\n| 1 | 2 |\n"),
    ("a | b\n--- | ---\n1 | 2\n", "| a | b |\n| --- | --- |\n| 1 | 2 |\n"),
    ("| a \\| b | `c \\| d` |\n| --- | --- |\n", "| a \\| b | `c \\| d` |\n| --- | --- |\n"),
    ("| x |\n| --- |\n| &nbsp;y |\n", "| x |\n| --- |\n| &nbsp;y |\n"),
])
def test_table_round_trips(markdown, expected):
    assert round_trip(markdown) == expected


# --- images ----------------------------------------------------------------------------------


@pytest.mark.parametrize("node, expected", [
    (image("a.png", "alt"), "![alt](a.png)"),
    (image("a.png"), "![](a.png)"),
    (image("img/a%20b.png", "x", 'say "hi"'), '![x](img/a%20b.png "say \\"hi\\"")'),
    (image("a b.png", "x"), "![x](<a b.png>)"),
    (image("a.png", "a]b *c* https://x.y"), "![a\\]b \\*c\\* https\\://x.y](a.png)"),
    (image("a.png", "line\nbreak"), "![line break](a.png)"),
])
def test_images(node, expected):
    assert inline_md(node) == expected


def test_display_src_is_ignored():
    assert inline_md(image("a.png", "x")) == inline_md({**image("a.png", "x"), "attrs": {
        "src": "a.png", "display_src": "file:///C:/elsewhere/a.png", "alt": "x", "title": None}})


def test_marked_images():
    assert inline_md(image("b.svg", "ci", None, link("https://ci"))) == "[![ci](b.svg)](https://ci)"
    assert inline_md(text("see "), image("a.png", "A", None, STRONG)) == "see **![A](a.png)**"


@pytest.mark.parametrize("inline, expected", [
    ([text("wow!"), image("a.png")], "wow!![](a.png)"),
    ([image("a.png"), text("(not a link)")], "![](a.png)(not a link)"),
    ([text("https://x.y", link("https://x.y")), image("a.png")], "<https://x.y>![](a.png)"),
])
def test_text_next_to_images(inline, expected):
    assert inline_md(*inline) == expected


# --- raw HTML and footnotes ------------------------------------------------------------------


def test_html_block_is_verbatim_and_indented_in_containers():
    source = "<div>\n  <b>x</b>\n</div>"
    assert to_markdown(doc(html_block(source))) == source + "\n"
    assert to_markdown(doc(quote(html_block("<!--\n\nc\n-->")))) == "> <!--\n>\n> c\n> -->\n"
    assert to_markdown(doc(bullets(item(html_block("<div>\nx\n</div>"))))) == "- <div>\n  x\n  </div>\n"


def test_html_inline_is_verbatim():
    assert inline_md(text("a "), html_inline("<kbd>"), text("Ctrl"), html_inline("</kbd>")) == "a <kbd>Ctrl</kbd>"
    assert inline_md(text("x", STRONG), html_inline("<br>", STRONG)) == "**x<br>**"


def test_newlines_in_html_inline_are_kept_in_paragraphs_and_dropped_in_headings():
    assert inline_md(text("a "), html_inline("<a\nhref='x'>")) == "a <a\nhref='x'>"
    assert to_markdown(doc(heading(1, html_inline("<a\nhref='x'>")))) == "# <a href='x'>\n"


def test_footnote_definitions_go_last_in_document_order():
    body = doc(footnote_def("b", "[^b]: B"), para(text("x"), footnote_ref("a")), footnote_def("a", "[^a]: A\n    more"),
               para(text("y"), footnote_ref("b")))
    assert to_markdown(body) == "x[^a]\n\ny[^b]\n\n[^b]: B\n\n[^a]: A\n    more\n"


def test_colon_after_a_footnote_reference_at_a_paragraph_start_is_escaped():
    note = footnote_def("1", "[^1]: note")
    assert to_markdown(doc(para(footnote_ref("1"), text(": not a definition")), note)) == (
        "[^1]\\: not a definition\n\n[^1]: note\n"
    )
    assert to_markdown(doc(para(text("a "), footnote_ref("1"), text(": fine")), note)) == "a [^1]: fine\n\n[^1]: note\n"
    assert to_markdown(doc(quote(para(footnote_ref("1"), text(": q"))), note)) == "> [^1]\\: q\n\n[^1]: note\n"


@pytest.mark.parametrize("markdown, expected", [
    ("[^1]: first\n\nPara[^1].\n", "Para[^1].\n\n[^1]: first\n"),
    ("A[^n] b[^m].\n\n[^m]: M\n[^n]: N\n    more\n", "A[^n] b[^m].\n\n[^m]: M\n\n[^n]: N\n    more\n"),
    ("[^1]\\: x\n\n[^1]: n\n", "[^1]\\: x\n\n[^1]: n\n"),
    ("<div>\nblock\n</div>\n\nafter\n", "<div>\nblock\n</div>\n\nafter\n"),
    ("<!-- c -->\n\ntext\n", "<!-- c -->\n\ntext\n"),
])
def test_protected_round_trips(markdown, expected):
    assert round_trip(markdown) == expected


# --- whole documents -------------------------------------------------------------------------


def test_unknown_node_inside_a_list_raises():
    with pytest.raises(ValueError, match="'callout'"):
        to_markdown(doc(bullets(item({"type": "callout"}))))


def test_every_node_type_serializes_and_parses_back_valid():
    body = doc(
        {"type": "front_matter", "attrs": {"source": "---\nt: 1\n---\n", "line": 1}},
        heading(1, text("T")),
        para(text("b", STRONG), text(" "), image("a.png", "A"), footnote_ref("1"), html_inline("<br>")),
        quote(para(text("q"))),
        bullets(item(para(text("t")), checked=True)),
        ordered(item(para(text("o"))), start=2),
        code_block("x", "py"),
        rule(),
        table(row(header(text("h"))), row(cell(text("c")))),
        html_block("<div>x</div>"),
        footnote_def("1", "[^1]: n"),
    )
    text_out = to_text(body)
    front, rest = frontmatter.split(text_out)
    back = from_markdown(rest, front)
    assert validate(back) == []
    assert [node["type"] for node in back["content"]] == [node["type"] for node in body["content"]]
    assert to_text(back) == text_out


# --- random table cells and inline chips -----------------------------------------------------
# Known limits kept out of the generators (see the plan's Task 7 Review Focus): "\|" inside a
# code span in a table cell, and an inline HTML chip at the start of a line.


def _units(inline, one_line=False):
    """What a reader sees, as lines of (unit, marks), like _visible; images, footnote references
    and inline HTML are one unit each. In a table cell (one_line) hard breaks are spaces."""
    lines = [[]]
    for node in inline:
        marks = node.get("marks", [])
        if node["type"] == "hard_break":
            if not one_line:
                lines.append([])
                continue
            node = text(" ", *marks)
        if node["type"] != "text":
            attrs = {key: value for key, value in node["attrs"].items() if key != "display_src"}
            lines[-1].append((repr(sorted(attrs.items())), sorted(repr(mark) for mark in marks)))
            continue
        for ch in node["text"].replace("\n", " "):
            kept = marks if CODE in marks or not ch.isspace() else [m for m in marks if m["type"] == "link"]
            lines[-1].append((ch, sorted(repr(mark) for mark in kept)))
    for line in lines:
        while line and line[0][0] in " \t" and repr(CODE) not in line[0][1]:
            line.pop(0)
        while line and line[-1][0] in " \t" and repr(CODE) not in line[-1][1]:
            line.pop()
    while lines and not lines[-1]:
        lines.pop()
    return lines


def _random_cell(rng, flanked):
    inline = _random_inline(rng, flanked)
    for node in inline:
        if node["type"] != "text" or rng.random() >= 0.3:
            continue
        coded = CODE in node.get("marks", [])
        cut = rng.randint(1, len(node["text"]) - 1) if len(node["text"]) > 1 else 0
        node["text"] = node["text"][:cut] + rng.choice(["|", "a|b"] if coded else ["|", "\\|", "a|b"]) + node["text"][cut:]
        if cut == 0 and not coded:
            node.pop("marks", None)  # a "|" at the edge of a strong/em run: the Task 6 limit
    for node in inline:
        if node["type"] == "text" and CODE in node.get("marks", []):
            while "\\|" in node["text"]:
                node["text"] = node["text"].replace("\\|", "|")
    if rng.random() < 0.2:
        inline.append(image(rng.choice(["p.png", "a%7Cb.png"]), rng.choice(["", "x|y", "a]"])))
    if rng.random() < 0.1:
        inline.insert(0, html_inline("<kbd>"))
    return inline


@pytest.mark.parametrize("flanked", [STRONG, EM], ids=["strong", "em"])
def test_random_cell_content_round_trips(flanked):
    rng = random.Random(7)
    for _ in range(800):
        cells = [_random_cell(rng, flanked) for _ in range(rng.randint(1, 3))]
        markdown = to_markdown(doc(table(row(*(header(*inline) for inline in cells)))))
        blocks = from_markdown(markdown)["content"]
        assert [block["type"] for block in blocks] == ["table"], markdown
        back = [node.get("content", []) for node in blocks[0]["content"][0]["content"]]
        assert [_units(inline, True) for inline in back] == [_units(inline, True) for inline in cells], markdown
        assert round_trip(markdown) == markdown


def _random_chip(rng):
    kind = rng.choice(["image", "footnote_ref", "html_inline"])
    if kind == "image":
        node = image(rng.choice(["p.png", "a%20b.png", "x(y"]), rng.choice(["", "alt", "a]b", "*x*", "https://x.y"]),
                     rng.choice([None, "T"]))
    elif kind == "footnote_ref":
        node = footnote_ref("n")
    else:
        node = html_inline(rng.choice(["<kbd>", "</kbd>", "<!-- c -->"]))
    if rng.random() < 0.3:
        node["marks"] = [rng.choice([STRONG, EM, link("u")])]
    return node


@pytest.mark.parametrize("flanked", [STRONG, EM], ids=["strong", "em"])
def test_random_inline_chips_round_trip(flanked):
    rng = random.Random(5)
    note = footnote_def("n", "[^n]: note")
    for _ in range(800):
        inline = _random_inline(rng, flanked)
        position = rng.randint(0, len(inline))
        inline[position:position] = [text("x "), _random_chip(rng), text(" ")]
        markdown = to_markdown(doc(para(*inline), note))
        blocks = from_markdown(markdown)["content"]
        assert [block["type"] for block in blocks] == ["paragraph", "footnote_def"], markdown
        assert _units(blocks[0].get("content", [])) == _units(inline), markdown
        assert round_trip(markdown) == markdown
