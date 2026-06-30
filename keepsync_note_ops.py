"""Pure note comparison, merge, and filter helpers."""

import difflib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from keepsync_models import Note, NoteType, normalize_keep_color


def normalize_import_labels(labels: List[str], source: str = "", markdown: bool = False) -> List[str]:
    normalized = []
    if source:
        normalized.append(source)
    if markdown:
        normalized.append(".md")
    for label in labels or []:
        label_text = str(label or "").strip()
        if label_text and label_text not in normalized:
            normalized.append(label_text)
    return normalized


def note_diff_body(note: Note) -> str:
    if note.note_type == NoteType.CHECKLIST:
        return "\n".join(
            f"{'  ' * item.indent}{'[x]' if item.checked else '[ ]'} {item.text}"
            for item in note.checklist_items
        )
    return note.content or ""


def notes_equivalent(left: Note, right: Note) -> bool:
    return (
        (left.title or "").strip() == (right.title or "").strip()
        and note_diff_body(left).strip() == note_diff_body(right).strip()
        and sorted(left.labels) == sorted(right.labels)
        and left.note_type == right.note_type
    )


def note_conflict_diff(local_note: Note, imported_note: Note) -> str:
    local_lines = [f"# {local_note.title or 'Untitled'}", *note_diff_body(local_note).splitlines()]
    imported_lines = [f"# {imported_note.title or 'Untitled'}", *note_diff_body(imported_note).splitlines()]
    return "\n".join(difflib.unified_diff(
        local_lines,
        imported_lines,
        fromfile="local",
        tofile="imported",
        lineterm="",
    ))


def merge_note_conflict(local_note: Note, imported_note: Note) -> Note:
    merged = Note.from_dict(local_note.to_dict())
    merged.labels = normalize_import_labels(local_note.labels + imported_note.labels)
    merged.attachments = local_note.attachments + [
        attachment for attachment in imported_note.attachments
        if attachment.filename not in {existing.filename for existing in local_note.attachments}
    ]
    merged.updated_at = datetime.now(timezone.utc)
    merged.local_modified = merged.updated_at

    if local_note.note_type == NoteType.CHECKLIST or imported_note.note_type == NoteType.CHECKLIST:
        merged.note_type = NoteType.NOTE
        local_body = note_diff_body(local_note)
        imported_body = note_diff_body(imported_note)
    else:
        local_body = local_note.content or ""
        imported_body = imported_note.content or ""

    if local_body.strip() == imported_body.strip():
        merged.content = local_body
    else:
        merged.content = (
            f"{local_body.strip()}\n\n"
            "--- Imported version ---\n\n"
            f"{imported_body.strip()}"
        ).strip()
    merged.checklist_items = []
    return merged


def default_advanced_filters() -> Dict[str, Any]:
    return {
        "mode": "AND",
        "label": "",
        "color": "",
        "date_from": "",
        "date_to": "",
        "has_image": False,
        "has_checklist": False,
        "is_archived": False,
    }


def advanced_filters_active(filters: Dict[str, Any]) -> bool:
    defaults = default_advanced_filters()
    return any(filters.get(key) != value for key, value in defaults.items() if key != "mode")


def parse_filter_date(value: str) -> Optional[datetime]:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def note_matches_advanced_filters(note: Note, filters: Dict[str, Any]) -> bool:
    checks = []
    label = (filters.get("label") or "").strip()
    if label:
        checks.append(any(label.lower() == existing.lower() for existing in note.labels))

    color = normalize_keep_color(filters.get("color", ""))
    if color:
        checks.append(normalize_keep_color(note.color) == color)

    date_from = parse_filter_date(filters.get("date_from", ""))
    if date_from:
        checks.append(note.updated_at.astimezone(timezone.utc) >= date_from)

    date_to = parse_filter_date(filters.get("date_to", ""))
    if date_to:
        end_of_day = date_to.replace(hour=23, minute=59, second=59)
        checks.append(note.updated_at.astimezone(timezone.utc) <= end_of_day)

    if filters.get("has_image"):
        checks.append(any(attachment.is_image for attachment in note.attachments))

    if filters.get("has_checklist"):
        checks.append(note.note_type == NoteType.CHECKLIST or bool(note.checklist_items))

    if filters.get("is_archived"):
        checks.append(note.archived)

    if not checks:
        return True
    if str(filters.get("mode", "AND")).upper() == "OR":
        return any(checks)
    return all(checks)
