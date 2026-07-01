import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from keepsync_models import ChecklistItem, Note, NoteType
import keepsync_pdf_export as pdf_export
import keepsync_notes as app


class PdfExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.created = datetime(2024, 1, 2, 10, 30, tzinfo=timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    def make_note(self, **kwargs):
        values = {
            "id": "note-1",
            "title": "Hello World!",
            "content": "Body text",
            "labels": ["Work"],
            "created_at": self.created,
            "updated_at": self.created,
        }
        values.update(kwargs)
        return Note(**values)

    def test_export_single_note_creates_pdf(self):
        out = self.root / "book.pdf"
        result = pdf_export.export_pdf_book([self.make_note()], out)

        self.assertTrue(out.exists())
        self.assertEqual(result.notes_exported, 1)
        self.assertGreaterEqual(result.pages, 2)
        header = out.read_bytes()[:5]
        self.assertEqual(header, b"%PDF-")

    def test_export_checklist_note(self):
        note = self.make_note(
            note_type=NoteType.CHECKLIST,
            checklist_items=[
                ChecklistItem(text="Buy milk", checked=True, indent=0),
                ChecklistItem(text="Eggs", checked=False, indent=1),
            ],
        )
        out = self.root / "checklist.pdf"
        result = pdf_export.export_pdf_book([note], out)

        self.assertTrue(out.exists())
        self.assertEqual(result.notes_exported, 1)

    def test_export_empty_list_creates_title_page_only(self):
        out = self.root / "empty.pdf"
        result = pdf_export.export_pdf_book([], out)

        self.assertTrue(out.exists())
        self.assertEqual(result.notes_exported, 0)
        self.assertEqual(result.pages, 1)

    def test_export_multiple_notes(self):
        notes = [
            self.make_note(id="n1", title="First"),
            self.make_note(id="n2", title="Second"),
            self.make_note(id="n3", title="Third"),
        ]
        out = self.root / "multi.pdf"
        result = pdf_export.export_pdf_book(notes, out, title="My Notes")

        self.assertTrue(out.exists())
        self.assertEqual(result.notes_exported, 3)
        self.assertGreaterEqual(result.pages, 4)

    def test_export_note_with_unicode(self):
        note = self.make_note(title="Café Notes", content="Emoji \U0001f680 and accents éèê")
        out = self.root / "unicode.pdf"
        result = pdf_export.export_pdf_book([note], out)

        self.assertTrue(out.exists())
        self.assertEqual(result.notes_exported, 1)

    def test_safe_replaces_unencodable_chars(self):
        self.assertEqual(pdf_export._safe("hello"), "hello")
        result = pdf_export._safe("\U0001f680")
        self.assertIsInstance(result, str)

    def test_app_reexports_pdf_export_helpers_for_compatibility(self):
        self.assertIs(app.export_pdf_book, pdf_export.export_pdf_book)
        self.assertIs(app.PdfExportResult, pdf_export.PdfExportResult)


if __name__ == "__main__":
    unittest.main()
