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


# --- editor helpers (Task 10) --------------------------------------------

from mdviewer.core.completion import (  # noqa: E402
    Suggestion,
    apply_suggestion,
    autoclose_action,
    deletes_pair,
    token_prefix,
)


def test_autoclose_pairs_at_line_end():
    assert autoclose_action("", 0, "(") == "pair"
    assert autoclose_action("", 0, "[") == "pair"


def test_autoclose_types_over_matching_closer():
    assert autoclose_action("()", 1, ")") == "over"
    assert autoclose_action("`a`", 2, "`") == "over"


def test_autoclose_skips_before_word():
    assert autoclose_action("word", 0, "(") is None


def test_autoclose_skips_marker_inside_word():
    assert autoclose_action("my", 2, "_") is None
    assert autoclose_action("a", 1, "*") is None


def test_autoclose_skips_bullet_star():
    assert autoclose_action("", 0, "*") is None
    assert autoclose_action("  ", 2, "*") is None


def test_autoclose_pairs_marker_after_space():
    assert autoclose_action("a ", 2, "*") == "pair"
    assert autoclose_action("a ", 2, "`") == "pair"
    assert autoclose_action("", 0, "`") == "pair"


def test_autoclose_third_backtick_is_plain():
    assert autoclose_action("``", 2, "`") is None


def test_autoclose_bracket_after_word():
    assert autoclose_action("f", 1, "(") == "pair"
    assert autoclose_action("!", 1, "[") == "pair"
    assert autoclose_action("", 0, "a") is None


def test_deletes_pair():
    assert deletes_pair("()", 1)
    assert deletes_pair("**", 1)
    assert not deletes_pair("(a)", 1)
    assert not deletes_pair("", 0)


def test_token_prefix():
    assert token_prefix("```py", 5) == "py"
    assert token_prefix("  ```", 5) == ""
    assert token_prefix("## x", 2) == ""


def test_apply_suggestion_heading():
    assert apply_suggestion("##", 2, Suggestion("### ", "token")) == ("### ", 4)
    assert apply_suggestion("# Title", 1, Suggestion("## ", "token")) == ("## Title", 3)


def test_apply_suggestion_fence_language():
    assert apply_suggestion("```py", 5, Suggestion("python", "token")) == ("```python", 9)


def test_apply_suggestion_task_list_keeps_indent():
    assert apply_suggestion("  *", 3, Suggestion("- [ ] ", "token")) == ("  - [ ] ", 8)


def test_apply_suggestion_quote():
    assert apply_suggestion("> note", 2, Suggestion("> - ", "token")) == ("> - note", 4)


def test_apply_suggestion_line_goes_below():
    assert apply_suggestion("| a |", 5, Suggestion("| --- |", "line")) == ("| a |\n| --- |", 13)


def test_apply_suggestion_fallback_inserts_at_cursor():
    assert apply_suggestion("ab", 1, Suggestion("# ", "token")) == ("a# b", 3)
