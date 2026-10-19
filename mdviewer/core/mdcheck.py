"""Line-level structural Markdown checks for MD Viewer (pure, Qt-free).

Errors (spec section 5.2): unclosed fenced code block; table data row whose
column count differs from the header; table row without a |---| separator
row. Warnings: heading missing the space after #; unbalanced ** or __
markers; odd number of inline backticks. Warnings ignore inline code spans
and fenced block content. No full CommonMark parsing is performed.
"""

import re
from dataclasses import dataclass

_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})(?=[^\s#])")
_CODE_SPAN_RE = re.compile(r"`+[^`]+`+")


@dataclass(frozen=True)
class Issue:
    line: int      # 1-based
    start: int     # 0-based column, inclusive
    end: int       # 0-based column, exclusive
    severity: str  # "error" or "warning"
    message: str


def column_count(line: str) -> int:
    """Count pipe-separated cells in a Markdown table row."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return len(s.split("|"))


def _fence_info(line: str):
    """Return (fence_char, marker_length, rest) when the line is a fence line."""
    m = _FENCE_RE.match(line)
    if not m:
        return None
    return m.group(1)[0], len(m.group(1)), m.group(2)


def _is_table_separator(line: str) -> bool:
    """True for GFM separator rows such as `| --- | :---: |`."""
    s = line.strip()
    if not s or "|" not in s:
        return False
    body = s
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    for cell in body.split("|"):
        c = cell.strip()
        if not c or "-" not in c or not all(ch in "-:" for ch in c):
            return False
    return True


def _is_table_data_row(lines: list[str], i: int) -> bool:
    """True when lines[i] belongs to a table whose separator row is above it."""
    j = i - 1
    while j >= 0:
        if _is_table_separator(lines[j]):
            return True
        if "|" not in lines[j] or _fence_info(lines[j]) is not None:
            return False
        j -= 1
    return False


def _check_content(lines: list[str], i: int, issues: list[Issue]) -> None:
    line = lines[i]
    n = len(lines)

    if _is_table_separator(line):
        if i > 0 and "|" in lines[i - 1] and not _is_table_separator(lines[i - 1]):
            expected = column_count(lines[i - 1])
            j = i + 1
            while (j < n and "|" in lines[j]
                   and not _is_table_separator(lines[j])
                   and _fence_info(lines[j]) is None):
                got = column_count(lines[j])
                if got != expected:
                    issues.append(Issue(
                        j + 1, 0, len(lines[j]), "error",
                        f"Table column count differs from header "
                        f"(expected {expected}, got {got})",
                    ))
                j += 1
        return

    if ("|" in line and not _is_table_data_row(lines, i)
            and i + 1 < n and "|" in lines[i + 1]
            and not _is_table_separator(lines[i + 1])
            and _fence_info(lines[i + 1]) is None):
        issues.append(Issue(
            i + 2, 0, len(lines[i + 1]), "error",
            "Table row is missing a |---| separator row",
        ))

    m = _HEADING_RE.match(line)
    if m:
        indent = len(line) - len(line.lstrip(" "))
        issues.append(Issue(
            i + 1, indent, indent + len(m.group(1)), "warning",
            "Heading is missing a space after #",
        ))

    stripped = _CODE_SPAN_RE.sub("", line)
    if stripped.count("**") % 2 == 1:
        issues.append(Issue(i + 1, 0, len(line), "warning", "Unbalanced ** markers"))
    if stripped.count("__") % 2 == 1:
        issues.append(Issue(i + 1, 0, len(line), "warning", "Unbalanced __ markers"))
    if line.count("`") % 2 == 1:
        issues.append(Issue(i + 1, 0, len(line), "warning", "Odd number of inline backticks"))


def check(text: str) -> list[Issue]:
    """Scan a whole document; return issues sorted by (line, start)."""
    lines = text.split("\n")
    issues: list[Issue] = []
    fence = None       # (fence_char, marker_length) of the open fence
    fence_open = None  # (line_index, indent, marker_length) of the open fence

    for i, line in enumerate(lines):
        info = _fence_info(line)
        if fence is None:
            if info is not None:
                char, length, rest = info
                if not (char == "`" and "`" in rest):
                    fence = (char, length)
                    indent = len(line) - len(line.lstrip(" "))
                    fence_open = (i, indent, length)
            else:
                _check_content(lines, i, issues)
        elif (info is not None and info[0] == fence[0]
              and info[1] >= fence[1] and info[2].strip() == ""):
            fence = None
            fence_open = None

    if fence is not None:
        i, indent, length = fence_open
        issues.append(Issue(
            i + 1, indent, indent + length, "error",
            "Unclosed fenced code block",
        ))

    issues.sort(key=lambda issue: (issue.line, issue.start))
    return issues
