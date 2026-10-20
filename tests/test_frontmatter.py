import pytest

from mdviewer.core.frontmatter import join, split

# --- recognized blocks ---------------------------------------------------------


@pytest.mark.parametrize("text, front, body", [
    ("---\ntitle: x\n---\n# Hi\n", "---\ntitle: x\n---\n", "# Hi\n"),
    ("---\ntitle: x\n...\n# Hi\n", "---\ntitle: x\n...\n", "# Hi\n"),
    ("---\na: 1\n---\n", "---\na: 1\n---\n", ""),
    ("---\na: 1\n---", "---\na: 1\n---", ""),
    ("---\na: 1\n---\n\n\nText", "---\na: 1\n---\n", "\n\nText"),
    ("---\n\na: 1\n\n---\nx", "---\n\na: 1\n\n---\n", "x"),
    ("---\ntitle: Café ✓\n---\nbody", "---\ntitle: Café ✓\n---\n", "body"),
])
def test_split_recognizes_front_matter(text, front, body):
    assert split(text) == (front, body)


def test_block_ends_at_the_first_closing_line():
    assert split("---\na: 1\n---\nb\n---\n") == ("---\na: 1\n---\n", "b\n---\n")


def test_closer_must_be_exact():
    text = "---\na: |\n  ---\n--- \n....\n...\nrest\n"
    assert split(text) == ("---\na: |\n  ---\n--- \n....\n...\n", "rest\n")


# --- near misses: no front matter, text parsed normally -----------------------------


@pytest.mark.parametrize("text", [
    "",
    "---",
    "---\n",
    "---\na: 1\n",                 # no closing line
    "\n---\na: 1\n---\n",          # not at offset 0
    " ---\na: 1\n---\n",           # indented opener
    "--- \na: 1\n---\n",           # trailing space on the opener
    "----\na: 1\n----\n",          # four dashes
    "...\na: 1\n...\n",            # dots only close a block
    "---\n---\nText\n",            # empty block: a horizontal rule, then text
    "---\n  \n\t\n---\nText\n",    # blank-only block
    "---\n\n---\na: 1\n---\n",     # the first closer ends the (blank) block
    "---\nText\n--- \n",           # closer with a trailing space
    "# Title\n---\na\n---\n",
    "---\r\na: 1\r\n---\r\n",      # CRLF never reaches core/: the buffer is "\n" only
])
def test_split_near_misses(text):
    assert split(text) == (None, text)


# --- join ------------------------------------------------------------------------


def test_join_without_front_matter_is_the_body():
    assert join(None, "# Hi\n") == "# Hi\n"


def test_join_puts_the_block_back_unchanged():
    assert join("---\na: 1\n...\n", "\nbody") == "---\na: 1\n...\n\nbody"


@pytest.mark.parametrize("text", [
    "---\ntitle: x\n---\n# Hi\n",
    "---\na: 1\n---",
    "---\n\na: 1\n\n---\n\n\nx",
    "---\n---\nText\n",
    "---\na: 1\n",
    "",
    "plain\n",
])
def test_join_split_round_trip_is_byte_exact(text):
    assert join(*split(text)) == text
