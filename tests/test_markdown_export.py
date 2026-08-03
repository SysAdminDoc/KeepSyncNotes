import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from keepsync_models import Attachment, ChecklistItem, Note, NoteType
import keepsync_markdown_export as markdown_export
import keepsync_notes as app


class MarkdownExportTests(unittest.TestCase):
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
            "labels": ["Work", ".md"],
            "created_at": self.created,
            "updated_at": self.created,
        }
        values.update(kwargs)
        return Note(**values)

    def test_export_markdown_vault_writes_frontmatter_and_copies_attachments(self):
        source = self.root / "scan image.png"
        source.write_bytes(b"image")
        attachment = Attachment(
            id="att-1",
            filename="scan image.png",
            stored_path=str(source),
            mime_type="image/png",
        )

        result = markdown_export.export_markdown_vault(
            [self.make_note(attachments=[attachment])],
            self.root / "vault",
        )

        note_path = self.root / "vault" / "notes" / "2024-01-02-hello-world.md"
        copied = self.root / "vault" / "attachments" / "note-1" / "scan image.png"
        self.assertEqual(result.notes_exported, 1)
        self.assertEqual(result.attachments_copied, 1)
        self.assertEqual(result.attachments_missing, 0)
        self.assertTrue(note_path.exists())
        self.assertTrue(copied.exists())

        text = note_path.read_text(encoding="utf-8")
        self.assertIn('title: "Hello World!"', text)
        self.assertIn('  - "Work"', text)
        self.assertIn("# Hello World!", text)
        self.assertIn("Body text", text)
        self.assertIn("![scan image.png](../attachments/note-1/scan image.png)", text)

    def test_export_markdown_vault_deduplicates_matching_titles(self):
        first = self.make_note(id="note-1", title="Same")
        second = self.make_note(id="note-2", title="Same")

        result = markdown_export.export_markdown_vault([first, second], self.root / "vault")

        self.assertEqual(
            [path.name for path in result.note_paths],
            ["2024-01-02-same.md", "2024-01-02-same-2.md"],
        )

    def test_render_checklist_note_as_gfm_tasks(self):
        note = self.make_note(
            note_type=NoteType.CHECKLIST,
            checklist_items=[
                ChecklistItem(text="Parent", checked=True, indent=0),
                ChecklistItem(text="Child", checked=False, indent=1),
            ],
        )

        markdown = markdown_export.render_note_markdown(note)

        self.assertIn("- [x] Parent", markdown)
        self.assertIn("  - [ ] Child", markdown)

    def test_export_reports_missing_attachments(self):
        attachment = Attachment(filename="missing.png", stored_path=str(self.root / "missing.png"))

        result = markdown_export.export_markdown_vault(
            [self.make_note(attachments=[attachment])],
            self.root / "vault",
        )

        self.assertEqual(result.attachments_copied, 0)
        self.assertEqual(result.attachments_missing, 1)

    def test_app_reexports_markdown_export_helpers_for_compatibility(self):
        self.assertIs(app.export_markdown_vault, markdown_export.export_markdown_vault)
        self.assertIs(app.render_note_markdown, markdown_export.render_note_markdown)
        self.assertIs(app.MarkdownVaultExportResult, markdown_export.MarkdownVaultExportResult)


if __name__ == "__main__":
    unittest.main()
