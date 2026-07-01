"""Daily review mode — surface random old notes for memory refresh."""

import random
from datetime import datetime, timezone
from typing import List

from keepsync_models import Note


def pick_review_notes(
    notes: List[Note],
    count: int = 3,
    min_age_days: int = 7,
) -> List[Note]:
    now = datetime.now(timezone.utc)
    candidates = [
        note for note in notes
        if not note.trashed
        and note.created_at
        and (now - note.created_at).days >= min_age_days
    ]
    if not candidates:
        return []
    return random.sample(candidates, min(count, len(candidates)))


def review_summary(note: Note) -> str:
    title = note.title.strip() or "Untitled"
    age = (datetime.now(timezone.utc) - note.created_at).days if note.created_at else 0
    preview = (note.content or "").strip()[:120]
    if note.checklist_items:
        items = [item.text for item in note.checklist_items if item.text.strip()]
        preview = ", ".join(items[:3])
    parts = [title]
    if age > 0:
        parts.append(f"({age} days ago)")
    if note.labels:
        parts.append(f"[{', '.join(note.labels)}]")
    return f"{' '.join(parts)}\n{preview}"
