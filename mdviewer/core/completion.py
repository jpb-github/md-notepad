"""Contextual Markdown completion and Enter continuation logic (Qt-free)."""

import re
from dataclasses import dataclass

from mdviewer.core.mdcheck import column_count

AUTOCLOSE_PAIRS = {"*": "*", "_": "_", "`": "`", "[": "]", "(": ")"}

FENCE_LANGUAGES = (
    "python", "bash", "powershell", "javascript", "typescript", "json",
    "yaml", "xml", "html", "css", "c", "cpp", "csharp", "go", "rust",
    "java", "sql", "toml", "text",
)

_FENCE_LINE_RE = re.compile(r"^\s*```")
_HEADING_RE = re.compile(r"^(\s*)(#+)")
_TASK_MARKER_RE = re.compile(r"^\s*[-*+]\s*$")
_QUOTE_RE = re.compile(r"^\s*((?:>[ \t]*)+)\S")
_QUOTE_BARE_RE = re.compile(r"^\s*((?:>[ \t]*)+)$")
_BULLET_RE = re.compile(r"^(\s*)([-*+])([ \t]+)(.*)$")
_BULLET_BARE_RE = re.compile(r"^(\s*)([-*+])$")
_ORDERED_RE = re.compile(r"^(\s*)(\d+)([.)])([ \t]+)(.*)$")
_ORDERED_BARE_RE = re.compile(r"^(\s*)(\d+)([.)])$")


@dataclass(frozen=True)
class Suggestion:
    text: str
    kind: str  # "token" completes in place; "line" inserts a new line below


def suggestions_for(line: str, col: int) -> list[Suggestion]:
    """Completion candidates for a line/cursor context.

    Priority: fence languages, heading, task list, quote, table.
    """
    if _FENCE_LINE_RE.match(line):
        return [Suggestion(lang, "token") for lang in FENCE_LANGUAGES]
    heading = _HEADING_RE.match(line)
    if heading is not None and col <= heading.end(2) + 1:
        return [Suggestion("#" * n + " ", "token") for n in range(1, 7)]
    if _TASK_MARKER_RE.match(line):
        return [Suggestion("- [ ] ", "token"), Suggestion("- [x] ", "token")]
    if line.lstrip().startswith(">"):
        return [Suggestion("> ", "token"), Suggestion("> - ", "token")]
    if "|" in line:
        count = column_count(line)
        return [
            Suggestion("| " + " | ".join(["---"] * count) + " |", "line"),
            Suggestion("| " + " | ".join([""] * count) + " |", "line"),
        ]
    return []


def should_continue_on_enter(line: str, col: int, in_fence: bool = False) -> str | None:
    """Decide Enter continuation on the editor page.

    None: plain Enter. "": clear the current marker and insert a blank
    line (empty list item or empty quote = exit). Non-empty: prefix to
    insert after the newline. No continuation inside fences or on lines
    containing |.
    """
    if in_fence or "|" in line:
        return None

    quote = _QUOTE_RE.match(line)
    if quote is not None and col >= quote.end(1):
        return quote.group(1).rstrip() + " "
    if _QUOTE_BARE_RE.match(line) is not None and col >= len(line):
        return ""

    bullet = _BULLET_RE.match(line)
    if bullet is not None and col >= len(bullet.group(1)) + 1:
        if bullet.group(4).strip():
            return f"{bullet.group(1)}{bullet.group(2)} "
        return ""
    if _BULLET_BARE_RE.match(line) is not None and col >= len(line):
        return ""

    ordered = _ORDERED_RE.match(line)
    if ordered is not None and col >= len(ordered.group(1)) + len(ordered.group(2)) + 1:
        if ordered.group(5).strip():
            return f"{ordered.group(1)}{int(ordered.group(2)) + 1}{ordered.group(3)} "
        return ""
    if _ORDERED_BARE_RE.match(line) is not None and col >= len(line):
        return ""

    return None
