"""Markdown vault export helpers."""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set
import re
import shutil

from keepsync_models import Attachment, ChecklistItem, Note, NoteType


@dataclass
class MarkdownVaultExportResult:
    output_dir: Path
    notes_exported: int
    attachments_copied: int
    attachments_missing: int
    note_paths: List[Path]


def export_markdown_vault(notes: Iterable[Note], output_dir: Path) -> MarkdownVaultExportResult:
    root = Path(output_dir)
    notes_dir = root / "notes"
    attachments_dir = root / "attachments"
    notes_dir.mkdir(parents=True, exist_ok=True)
    attachments_dir.mkdir(parents=True, exist_ok=True)

    used_names: Set[str] = set()
    note_paths: List[Path] = []
    attachments_copied = 0
    attachments_missing = 0

    for note in notes:
        attachment_links, copied, missing = _copy_note_attachments(note, attachments_dir)
        attachments_copied += copied
        attachments_missing += missing

        filename = unique_markdown_filename(note, used_names)
        path = notes_dir / filename
        path.write_text(render_note_markdown(note, attachment_links), encoding="utf-8")
        note_paths.append(path)

    return MarkdownVaultExportResult(
        output_dir=root,
        notes_exported=len(note_paths),
        attachments_copied=attachments_copied,
        attachments_missing=attachments_missing,
        note_paths=note_paths,
    )


def unique_markdown_filename(note: Note, used_names: Set[str]) -> str:
    date_prefix = note_date_prefix(note)
    slug = slugify_title(note.title or note.content or "untitled")
    base = f"{date_prefix}-{slug}"
    filename = f"{base}.md"
    counter = 2
    while filename.lower() in used_names:
        filename = f"{base}-{counter}.md"
        counter += 1
    used_names.add(filename.lower())
    return filename


def note_date_prefix(note: Note) -> str:
    value = note.created_at or note.updated_at or datetime.now(timezone.utc)
    return value.date().isoformat()


def slugify_title(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._ -]+", "-", value.strip())
    text = re.sub(r"\s+", "-", text).strip(" .-").lower()
    return text[:80] or "untitled"


def render_note_markdown(note: Note, attachment_links: Optional[Dict[str, str]] = None) -> str:
    links = attachment_links or {}
    parts = [render_frontmatter(note, links), ""]
    if note.title.strip():
        parts.extend([f"# {note.title.strip()}", ""])

    body = render_note_body(note).strip()
    if body:
        parts.extend([body, ""])

    attachment_block = render_attachment_block(note.attachments, links)
    if attachment_block:
        parts.extend([attachment_block, ""])

    return "\n".join(parts).rstrip() + "\n"


def render_frontmatter(note: Note, attachment_links: Dict[str, str]) -> str:
    lines = [
        "---",
        f"id: {yaml_scalar(note.id)}",
        f"title: {yaml_scalar(note.title)}",
        f"created: {yaml_scalar(note.created_at.isoformat())}",
        f"updated: {yaml_scalar(note.updated_at.isoformat())}",
        f"pinned: {yaml_bool(note.pinned)}",
        f"archived: {yaml_bool(note.archived)}",
        f"trashed: {yaml_bool(note.trashed)}",
        f"color: {yaml_scalar(note.color)}",
        f"note_type: {yaml_scalar(note.note_type.value)}",
    ]
    if note.reminder_at:
        lines.append(f"reminder_at: {yaml_scalar(note.reminder_at.isoformat())}")
    if note.reminder_location:
        lines.append(f"reminder_location: {yaml_scalar(note.reminder_location)}")
    if note.keep_id:
        lines.append(f"keep_id: {yaml_scalar(note.keep_id)}")
    lines.extend(yaml_list("labels", note.labels))
    lines.extend(yaml_list("shared_with", note.shared_with))
    lines.extend(yaml_list("attachments", [attachment_links[item.id] for item in note.attachments if item.id in attachment_links]))
    lines.append("---")
    return "\n".join(lines)


def render_note_body(note: Note) -> str:
    if note.note_type == NoteType.CHECKLIST:
        return "\n".join(render_checklist_item(item) for item in note.checklist_items if item.text.strip())
    return note.content or ""


def render_checklist_item(item: ChecklistItem) -> str:
    indent = "  " * max(0, item.indent)
    marker = "x" if item.checked else " "
    return f"{indent}- [{marker}] {item.text}"


def render_attachment_block(attachments: List[Attachment], links: Dict[str, str]) -> str:
    lines = []
    for attachment in attachments:
        link = links.get(attachment.id)
        if not link:
            continue
        label = attachment.filename
        if attachment.is_image:
            lines.append(f"![{label}]({link})")
        else:
            lines.append(f"[{label}]({link})")
    if not lines:
        return ""
    return "## Attachments\n\n" + "\n".join(lines)


def yaml_scalar(value: object) -> str:
    text = "" if value is None else str(value)
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def yaml_bool(value: bool) -> str:
    return "true" if value else "false"


def yaml_list(name: str, values: Iterable[str]) -> List[str]:
    items = list(values or [])
    if not items:
        return [f"{name}: []"]
    lines = [f"{name}:"]
    lines.extend(f"  - {yaml_scalar(item)}" for item in items)
    return lines


def _copy_note_attachments(note: Note, attachments_dir: Path) -> tuple[Dict[str, str], int, int]:
    links: Dict[str, str] = {}
    copied = 0
    missing = 0
    note_dir = attachments_dir / note.id

    for attachment in note.attachments:
        source = Path(attachment.stored_path)
        if not source.exists():
            missing += 1
            continue
        note_dir.mkdir(parents=True, exist_ok=True)
        target = _unique_attachment_target(note_dir, attachment.filename)
        shutil.copy2(source, target)
        links[attachment.id] = Path("..", "attachments", note.id, target.name).as_posix()
        copied += 1

    return links, copied, missing


def _unique_attachment_target(directory: Path, filename: str) -> Path:
    safe_name = slugify_attachment_filename(filename)
    base = directory / safe_name
    candidate = base
    counter = 2
    while candidate.exists():
        candidate = directory / f"{base.stem}-{counter}{base.suffix}"
        counter += 1
    return candidate


def slugify_attachment_filename(filename: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._ -]+", "-", Path(filename or "attachment").name).strip(" .-")
    return safe or "attachment"
