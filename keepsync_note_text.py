"""Reminder parsing and markdown preview helpers."""

from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional


def parse_reminder_datetime(value: str) -> Optional[datetime]:
    text = (value or "").strip()
    if not text:
        return None

    candidates = [text, text.replace("T", " ")]
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            break
        except ValueError:
            parsed = None
    else:
        parsed = None

    if parsed is None:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue

    if parsed is None:
        raise ValueError("Use YYYY-MM-DD HH:MM for reminders.")

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return parsed.astimezone(timezone.utc)

def format_reminder_datetime(value: Optional[datetime]) -> str:
    if not value:
        return ""
    return value.astimezone().strftime("%Y-%m-%d %H:%M")

def is_markdown_label(value: Any) -> bool:
    """Return True when a note label enables markdown preview mode."""
    return str(value or "").strip().lower() == ".md"

def note_uses_markdown(labels: List[str]) -> bool:
    return any(is_markdown_label(label) for label in labels)

def split_inline_markdown(text: str) -> List[Dict[str, str]]:
    """Split a markdown line into display segments with lightweight styles."""
    pattern = re.compile(r"(`([^`]+)`|\*\*([^*]+)\*\*|__([^_]+)__|\*([^*]+)\*|_([^_]+)_)")
    segments = []
    cursor = 0

    for match in pattern.finditer(text or ""):
        if match.start() > cursor:
            segments.append({"text": text[cursor:match.start()], "style": "plain"})

        if match.group(2) is not None:
            segments.append({"text": match.group(2), "style": "inline_code"})
        elif match.group(3) is not None or match.group(4) is not None:
            segments.append({"text": match.group(3) or match.group(4), "style": "bold"})
        else:
            segments.append({"text": match.group(5) or match.group(6), "style": "italic"})
        cursor = match.end()

    if cursor < len(text or ""):
        segments.append({"text": text[cursor:], "style": "plain"})
    return segments

def markdown_preview_blocks(markdown_text: str) -> List[Dict[str, Any]]:
    """Convert a conservative markdown subset into styled preview blocks."""
    blocks = []
    in_code_block = False

    for raw_line in (markdown_text or "").splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue

        if in_code_block:
            blocks.append({
                "style": "code_block",
                "segments": [{"text": raw_line, "style": "plain"}],
            })
            continue

        if not stripped:
            blocks.append({"style": "blank", "segments": []})
            continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            level = min(len(heading.group(1)), 3)
            blocks.append({
                "style": f"heading_{level}",
                "segments": split_inline_markdown(heading.group(2).strip()),
            })
            continue

        task = re.match(r"^\s*[-*+]\s+\[([ xX])\]\s+(.+)$", raw_line)
        if task:
            mark = "[x]" if task.group(1).lower() == "x" else "[ ]"
            blocks.append({
                "style": "task",
                "segments": split_inline_markdown(f"{mark} {task.group(2).strip()}"),
            })
            continue

        bullet = re.match(r"^\s*[-*+]\s+(.+)$", raw_line)
        if bullet:
            blocks.append({
                "style": "list_item",
                "segments": split_inline_markdown(f"- {bullet.group(1).strip()}"),
            })
            continue

        numbered = re.match(r"^\s*(\d+)[.)]\s+(.+)$", raw_line)
        if numbered:
            blocks.append({
                "style": "list_item",
                "segments": split_inline_markdown(f"{numbered.group(1)}. {numbered.group(2).strip()}"),
            })
            continue

        if stripped.startswith(">"):
            blocks.append({
                "style": "quote",
                "segments": split_inline_markdown(stripped.lstrip("> ").strip()),
            })
            continue

        blocks.append({
            "style": "paragraph",
            "segments": split_inline_markdown(raw_line.strip()),
        })

    return blocks

def markdown_preview_text(markdown_text: str, limit: int = 150) -> str:
    preview_parts = []
    for block in markdown_preview_blocks(markdown_text):
        text = "".join(segment["text"] for segment in block["segments"]).strip()
        if text:
            preview_parts.append(text)
    preview = " ".join(preview_parts)
    return preview[:limit] + ("..." if len(preview) > limit else "")
