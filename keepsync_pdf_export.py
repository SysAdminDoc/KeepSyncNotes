"""PDF book export for KeepSyncNotes."""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

from keepsync_models import Note, NoteType, keep_color_name


@dataclass
class PdfExportResult:
    output_path: Path
    notes_exported: int
    pages: int


def export_pdf_book(
    notes: Iterable[Note],
    output_path: Path,
    title: str = "KeepSync Notes",
    page_size: str = "A4",
) -> PdfExportResult:
    from fpdf import FPDF

    pdf = FPDF(orientation="P", unit="mm", format=page_size)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_margins(20, 20, 20)

    _add_title_page(pdf, title)

    notes_list = list(notes)
    for note in notes_list:
        _add_note_page(pdf, note)

    pdf.output(str(output_path))

    return PdfExportResult(
        output_path=output_path,
        notes_exported=len(notes_list),
        pages=pdf.pages_count,
    )


def _add_title_page(pdf, title: str):
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 28)
    pdf.ln(60)
    pdf.cell(0, 15, _safe(title), new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(120, 120, 120)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    pdf.cell(0, 10, f"Exported {now}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_text_color(0, 0, 0)


def _add_note_page(pdf, note: Note):
    pdf.add_page()

    note_title = note.title.strip() or "Untitled"
    pdf.set_font("Helvetica", "B", 18)
    pdf.multi_cell(0, 9, _safe(note_title), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    meta_parts = []
    created = note.created_at.strftime("%Y-%m-%d %H:%M") if note.created_at else ""
    if created:
        meta_parts.append(f"Created: {created}")
    if note.labels:
        meta_parts.append(f"Labels: {', '.join(note.labels)}")
    if note.color:
        meta_parts.append(f"Color: {keep_color_name(note.color)}")
    if note.pinned:
        meta_parts.append("Pinned")
    if note.archived:
        meta_parts.append("Archived")
    if note.shared_with:
        meta_parts.append(f"Shared with: {', '.join(note.shared_with)}")
    if note.reminder_at:
        meta_parts.append(f"Reminder: {note.reminder_at.strftime('%Y-%m-%d %H:%M')}")

    if meta_parts:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(120, 120, 120)
        pdf.multi_cell(0, 5, _safe(" | ".join(meta_parts)), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(4)

    pdf.set_draw_color(200, 200, 200)
    pdf.line(20, pdf.get_y(), pdf.w - 20, pdf.get_y())
    pdf.ln(6)

    if note.note_type == NoteType.CHECKLIST:
        _render_checklist(pdf, note)
    else:
        _render_text_body(pdf, note.content or "")


def _render_text_body(pdf, content: str):
    pdf.set_font("Helvetica", "", 11)
    for line in content.split("\n"):
        pdf.multi_cell(0, 6, _safe(line), new_x="LMARGIN", new_y="NEXT")


def _render_checklist(pdf, note: Note):
    pdf.set_font("Helvetica", "", 11)
    for item in note.checklist_items:
        if not item.text.strip():
            continue
        indent = "    " * max(0, item.indent)
        marker = "[x]" if item.checked else "[ ]"
        pdf.multi_cell(0, 6, _safe(f"{indent}{marker} {item.text}"), new_x="LMARGIN", new_y="NEXT")


def _safe(text: str) -> str:
    return text.encode("latin-1", errors="replace").decode("latin-1")
