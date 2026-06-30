"""Markdown editing helpers for the note editor toolbar."""

from typing import Dict


MARKDOWN_PLACEHOLDERS: Dict[str, str] = {
    "bold": "bold text",
    "italic": "italic text",
    "code": "code",
    "link": "link text",
    "task": "Task item",
}


def format_markdown_selection(selection: str, style: str) -> str:
    text = selection or MARKDOWN_PLACEHOLDERS.get(style, "text")
    if style == "bold":
        return f"**{text}**"
    if style == "italic":
        return f"_{text}_"
    if style == "code":
        return f"`{text}`"
    if style == "link":
        return f"[{text}](url)"
    if style == "task":
        lines = text.splitlines() or [text]
        return "\n".join(f"- [ ] {line}" if line.strip() else "- [ ] " for line in lines)
    return text
