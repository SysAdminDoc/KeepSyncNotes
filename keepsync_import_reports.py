"""Import fidelity summary helpers."""

from dataclasses import dataclass
from typing import Iterable, List, Sequence

from keepsync_models import Note, NoteType


IMPORT_SUCCESS_STATUSES = {"imported", "conflict_copy", "conflict_replace", "conflict_merge"}
IMPORT_CONFLICT_STATUSES = {"conflict_copy", "conflict_replace", "conflict_merge"}


@dataclass
class ImportFidelityReport:
    total_notes: int = 0
    imported_notes: int = 0
    skipped_notes: int = 0
    failed_notes: int = 0
    conflict_notes: int = 0
    checklist_notes: int = 0
    checklist_items: int = 0
    attachments: int = 0
    label_assignments: int = 0
    unique_labels: int = 0
    reminders: int = 0
    archived: int = 0
    trashed: int = 0
    shared: int = 0
    unsupported_fields: int = 0


def _unsupported_field_count(note: Note) -> int:
    value = getattr(note, "unsupported_fields", None)
    if isinstance(value, dict):
        return len(value)
    if isinstance(value, (list, tuple, set)):
        return len(value)
    return 0


def build_import_fidelity_report(notes: Iterable[Note], statuses: Sequence[str]) -> ImportFidelityReport:
    note_list = [note for note in notes if note is not None]
    labels = set()
    for note in note_list:
        labels.update(label for label in note.labels if label)

    return ImportFidelityReport(
        total_notes=len(note_list),
        imported_notes=sum(1 for status in statuses if status in IMPORT_SUCCESS_STATUSES),
        skipped_notes=statuses.count("skipped"),
        failed_notes=statuses.count("failed"),
        conflict_notes=sum(1 for status in statuses if status in IMPORT_CONFLICT_STATUSES),
        checklist_notes=sum(
            1 for note in note_list
            if note.note_type == NoteType.CHECKLIST or bool(note.checklist_items)
        ),
        checklist_items=sum(len(note.checklist_items) for note in note_list),
        attachments=sum(len(note.attachments) for note in note_list),
        label_assignments=sum(len(note.labels) for note in note_list),
        unique_labels=len(labels),
        reminders=sum(1 for note in note_list if note.reminder_at),
        archived=sum(1 for note in note_list if note.archived),
        trashed=sum(1 for note in note_list if note.trashed),
        shared=sum(1 for note in note_list if note.shared_with),
        unsupported_fields=sum(_unsupported_field_count(note) for note in note_list),
    )


def import_summary_lines(source: str, notes: Iterable[Note], statuses: Sequence[str]) -> List[str]:
    report = build_import_fidelity_report(notes, statuses)
    return [
        f"Imported {report.imported_notes} of {report.total_notes} notes from {source}.",
        (
            "Fidelity: "
            f"checklist notes {report.checklist_notes}, "
            f"checklist items {report.checklist_items}, "
            f"attachments {report.attachments}, "
            f"label assignments {report.label_assignments} ({report.unique_labels} unique)."
        ),
        (
            "Metadata: "
            f"reminders {report.reminders}, "
            f"archived {report.archived}, "
            f"trashed {report.trashed}, "
            f"shared {report.shared}, "
            f"unsupported fields {report.unsupported_fields}."
        ),
        (
            "Outcomes: "
            f"conflicts {report.conflict_notes}, "
            f"skipped unchanged/local-kept {report.skipped_notes}, "
            f"failed {report.failed_notes}."
        ),
    ]
