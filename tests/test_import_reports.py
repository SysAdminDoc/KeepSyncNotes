import unittest

import keepsync_import_reports as reports
import keepsync_notes as app
from keepsync_models import Attachment, ChecklistItem, Note, NoteType


class ImportReportTests(unittest.TestCase):
    def test_build_import_fidelity_report_counts_note_fields_and_statuses(self):
        checklist = Note(
            id="checklist",
            title="Tasks",
            content="",
            note_type=NoteType.CHECKLIST,
            checklist_items=[
                ChecklistItem(text="One"),
                ChecklistItem(text="Two", checked=True),
            ],
            labels=["work", "todo"],
            attachments=[Attachment(filename="scan.png", stored_path="scan.png")],
            archived=True,
            shared_with=["person@example.com"],
        )
        reminder = Note(
            id="reminder",
            title="Reminder",
            content="Body",
            labels=["work"],
            trashed=True,
        )
        reminder.unsupported_fields = ["location"]

        report = reports.build_import_fidelity_report(
            [checklist, reminder],
            ["imported", "conflict_merge", "skipped", "failed"],
        )

        self.assertEqual(report.total_notes, 2)
        self.assertEqual(report.imported_notes, 2)
        self.assertEqual(report.conflict_notes, 1)
        self.assertEqual(report.skipped_notes, 1)
        self.assertEqual(report.failed_notes, 1)
        self.assertEqual(report.checklist_notes, 1)
        self.assertEqual(report.checklist_items, 2)
        self.assertEqual(report.attachments, 1)
        self.assertEqual(report.label_assignments, 3)
        self.assertEqual(report.unique_labels, 2)
        self.assertEqual(report.archived, 1)
        self.assertEqual(report.trashed, 1)
        self.assertEqual(report.shared, 1)
        self.assertEqual(report.unsupported_fields, 1)

    def test_summary_lines_include_required_fidelity_categories(self):
        note = Note(id="note", title="Note", content="Body", labels=["tag"])

        lines = reports.import_summary_lines("Unit", [note], ["imported"])
        text = "\n".join(lines)

        self.assertIn("Imported 1 of 1 notes from Unit.", text)
        self.assertIn("checklist notes 0", text)
        self.assertIn("attachments 0", text)
        self.assertIn("label assignments 1", text)
        self.assertIn("unsupported fields 0", text)

    def test_app_reexports_import_report_helpers_for_compatibility(self):
        self.assertIs(app.IMPORT_SUCCESS_STATUSES, reports.IMPORT_SUCCESS_STATUSES)
        self.assertIs(app.import_summary_lines, reports.import_summary_lines)


if __name__ == "__main__":
    unittest.main()
