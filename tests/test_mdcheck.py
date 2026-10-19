from mdviewer.core.mdcheck import Issue, check, column_count


def test_issue_fields():
    issue = Issue(3, 0, 5, "error", "msg")
    assert (issue.line, issue.start, issue.end, issue.severity, issue.message) == (3, 0, 5, "error", "msg")


def test_column_count():
    assert column_count("| a | b |") == 2
    assert column_count("a | b") == 2
    assert column_count("|") == 1


def test_clean_document():
    text = (
        "# Title\n"
        "\n"
        "Some **bold** and *italic* and `code`.\n"
        "\n"
        "- one\n"
        "- two\n"
    )
    assert check(text) == []


def test_clean_table():
    assert check("| a | b |\n| --- | --- |\n| 1 | 2 |\n") == []


def test_closed_fence_has_no_issues():
    assert check("```python\n# not a heading\n**\n```\n") == []


def test_unclosed_fence_is_error():
    issues = check("```python\nprint(1)\n")
    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert issues[0].message == "Unclosed fenced code block"
    assert issues[0].line == 1
    assert (issues[0].start, issues[0].end) == (0, 3)


def test_unclosed_tilde_fence_is_error():
    issues = check("~~~\nhello\n")
    assert [i.message for i in issues] == ["Unclosed fenced code block"]


def test_fence_content_is_not_checked():
    assert check("```\n# heading no space\n**odd\n```\n") == []


def test_table_column_mismatch_is_error():
    issues = check("| a | b |\n| --- | --- |\n| 1 | 2 | 3 |\n")
    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert issues[0].line == 3
    assert "expected 2, got 3" in issues[0].message


def test_each_bad_row_flagged():
    issues = check("| a |\n| --- |\n| 1 | 2 |\n| 3 |\n| 4 | 5 |\n")
    assert [i.line for i in issues] == [3, 5]


def test_missing_separator_is_error():
    issues = check("| a | b |\n| 1 | 2 |\n")
    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert issues[0].line == 2
    assert "separator" in issues[0].message


def test_valid_table_rows_not_flagged_missing_separator():
    assert check("| a | b |\n| --- | --- |\n| 1 | 2 |\n| 3 | 4 |\n") == []


def test_heading_without_space_is_warning():
    issues = check("#Title\n")
    assert len(issues) == 1
    assert issues[0].severity == "warning"
    assert issues[0].message == "Heading is missing a space after #"
    assert (issues[0].start, issues[0].end) == (0, 1)


def test_indented_heading_without_space_is_warning():
    issues = check("  #Title\n")
    assert (issues[0].start, issues[0].end) == (2, 3)


def test_seven_hashes_not_flagged():
    assert check("####### eight hashes\n") == []


def test_unbalanced_bold_is_warning():
    issues = check("a ** b\n")
    assert [i.message for i in issues] == ["Unbalanced ** markers"]


def test_unbalanced_double_underscore_is_warning():
    issues = check("a __ b\n")
    assert [i.message for i in issues] == ["Unbalanced __ markers"]


def test_bold_in_code_span_ignored():
    assert check("a `**` b\n") == []


def test_odd_backticks_is_warning():
    issues = check("a ` b\n")
    assert [i.message for i in issues] == ["Odd number of inline backticks"]


def test_issues_sorted_by_line_and_start():
    issues = check("  #Bad ** x\n")
    assert [(i.line, i.start) for i in issues] == [(1, 0), (1, 2)]
