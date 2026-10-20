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


def _task6_only(node):
    """True when the node uses only the node types this serializer handles so far."""
    if node["type"] not in {"paragraph", "heading", "blockquote", "horizontal_rule", "text", "hard_break"}:
        return False
    return all(_task6_only(child) for child in node.get("content", []))


def test_repo_text_blocks_round_trip():
    """Every paragraph, heading, quote and rule in the project's docs survives serialization."""
    root = Path(__file__).resolve().parent.parent
    paths = [root / "README.md", *sorted((root / "docs").rglob("*.md"))]
    checked = 0
    for path in paths:
        front, body = frontmatter.split(path.read_text(encoding="utf-8").replace("\r\n", "\n"))
        for block in from_markdown(body, front)["content"]:
            if not _task6_only(block):
                continue
            markdown = to_markdown(doc(block))
            assert without_lines(from_markdown(markdown))["content"] == [without_lines(block)], (path, markdown)
            checked += 1
    assert checked > 100


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
