from mdviewer.core.completion import (
    AUTOCLOSE_PAIRS,
    FENCE_LANGUAGES,
    should_continue_on_enter,
    suggestions_for,
)


def texts(suggestions):
    return [s.text for s in suggestions]


def test_autoclose_pairs():
    assert AUTOCLOSE_PAIRS == {"*": "*", "_": "_", "`": "`", "[": "]", "(": ")"}


def test_fence_language_list_matches_spec():
    assert list(FENCE_LANGUAGES) == [
        "python", "bash", "powershell", "javascript", "typescript", "json",
        "yaml", "xml", "html", "css", "c", "cpp", "csharp", "go", "rust",
        "java", "sql", "toml", "text",
    ]


# --- suggestions_for ----------------------------------------------------

def test_heading_suggestions():
    sugg = suggestions_for("#", 1)
    assert texts(sugg) == ["# ", "## ", "### ", "#### ", "##### ", "###### "]
    assert all(s.kind == "token" for s in sugg)


def test_heading_suggestions_after_typing_several_hashes():
    assert texts(suggestions_for("###", 3))[:3] == ["# ", "## ", "### "]


def test_no_heading_suggestions_when_cursor_past_hashes():
    assert suggestions_for("# title", 9) == []


def test_fence_language_suggestions():
    assert texts(suggestions_for("```", 3)) == list(FENCE_LANGUAGES)


def test_fence_language_suggestions_partial_language():
    assert texts(suggestions_for("```py", 5)) == list(FENCE_LANGUAGES)


def test_task_list_suggestions():
    assert texts(suggestions_for("-", 1)) == ["- [ ] ", "- [x] "]


def test_task_list_suggestions_star_marker():
    assert texts(suggestions_for("*", 1)) == ["- [ ] ", "- [x] "]


def test_no_task_list_when_text_follows_marker():
    assert suggestions_for("- item", 6) == []


def test_quote_suggestions():
    assert texts(suggestions_for(">", 1)) == ["> ", "> - "]


def test_quote_suggestions_with_text():
    assert texts(suggestions_for("> note", 5)) == ["> ", "> - "]


def test_table_suggestions_match_column_count():
    sugg = suggestions_for("| a | b |", 8)
    assert texts(sugg) == ["| --- | --- |", "|  |  |"]
    assert all(s.kind == "line" for s in sugg)


def test_table_suggestions_single_column():
    assert texts(suggestions_for("| x |", 4)) == ["| --- |", "|  |"]


def test_table_suggestions_pipe_only_line():
    assert texts(suggestions_for("|", 1)) == ["| --- |", "|  |"]


def test_no_suggestions_for_plain_line():
    assert suggestions_for("just text", 9) == []


# --- should_continue_on_enter --------------------------------------------

def test_unordered_continues_same_marker():
    assert should_continue_on_enter("- item", 6) == "- "
    assert should_continue_on_enter("* item", 6) == "* "
    assert should_continue_on_enter("+ item", 6) == "+ "


def test_unordered_preserves_indent():
    assert should_continue_on_enter("    - item", 11) == "    - "


def test_ordered_increments_number():
    assert should_continue_on_enter("1. item", 8) == "2. "
    assert should_continue_on_enter("10. item", 9) == "11. "
    assert should_continue_on_enter("3) item", 8) == "4) "


def test_empty_list_item_exits():
    assert should_continue_on_enter("- ", 2) == ""
    assert should_continue_on_enter("-", 1) == ""
    assert should_continue_on_enter("1. ", 3) == ""
    assert should_continue_on_enter("1.", 2) == ""


def test_quote_continues():
    assert should_continue_on_enter("> quote", 7) == "> "
    assert should_continue_on_enter(">> nested", 9) == ">> "


def test_empty_quote_exits():
    assert should_continue_on_enter("> ", 2) == ""
    assert should_continue_on_enter(">", 1) == ""


def test_no_continuation_inside_fence():
    assert should_continue_on_enter("- item", 6, in_fence=True) is None


def test_no_continuation_on_table_row():
    assert should_continue_on_enter("| a |", 4) is None


def test_no_continuation_plain_line():
    assert should_continue_on_enter("hello", 5) is None


def test_cursor_before_marker_gives_no_continuation():
    assert should_continue_on_enter("- item", 0) is None
    assert should_continue_on_enter("1. item", 0) is None
    assert should_continue_on_enter("> q", 0) is None
