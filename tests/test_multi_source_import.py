import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import keepsync_notes as app


class MultiSourceImporterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = app.DatabaseManager(str(self.root / "notes.db"))
        self.importer = app.MultiSourceImporter(self.db)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_imports_enex_content_and_tags(self):
        export_path = self.root / "notes.enex"
        export_path.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<en-export>
  <note>
    <title>ENEX title</title>
    <content><![CDATA[<?xml version="1.0" encoding="UTF-8"?>
      <!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml2.dtd">
      <en-note><h1>Heading</h1><div>Body</div><en-todo checked="true"/>Done</en-note>]]></content>
    <tag>Work</tag>
    <created>20260627T190000Z</created>
  </note>
</en-export>""",
            encoding="utf-8",
        )

        notes = self.importer.import_enex(export_path)

        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].title, "ENEX title")
        self.assertIn("Heading", notes[0].content)
        self.assertIn("[x] Done", notes[0].content)
        self.assertIn("Work", notes[0].labels)

    def test_imports_obsidian_vault_markdown(self):
        note_path = self.root / "Projects" / "Plan.md"
        note_path.parent.mkdir()
        note_path.write_text("# Plan\nBody", encoding="utf-8")

        notes = self.importer.import_text_folder(self.root, "Obsidian", markdown_default=True)

        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].title, "Plan")
        self.assertIn(".md", notes[0].labels)
        self.assertIn("Projects", notes[0].labels)

    def test_imports_simplenote_zip_json(self):
        export_path = self.root / "simplenote.zip"
        payload = {
            "activeNotes": [
                {
                    "content": "Simplenote title\nBody",
                    "tags": ["personal"],
                    "systemTags": ["markdown"],
                }
            ]
        }
        with zipfile.ZipFile(export_path, "w") as zf:
            zf.writestr("notes.json", json.dumps(payload))

        notes = self.importer.import_simplenote_export(export_path)

        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].title, "Simplenote title")
        self.assertIn("personal", notes[0].labels)
        self.assertIn(".md", notes[0].labels)

    def test_imports_takeout_zip(self):
        export_path = self.root / "takeout.zip"
        keep_note = {
            "title": "Keep title",
            "textContent": "Keep body",
            "labels": [{"name": "keep-label"}],
            "isPinned": True,
        }
        with zipfile.ZipFile(export_path, "w") as zf:
            zf.writestr("Takeout/Keep/keep-note.json", json.dumps(keep_note))

        notes = self.importer.import_takeout_zip(export_path)

        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].title, "Keep title")
        self.assertEqual(notes[0].content, "Keep body")
        self.assertTrue(notes[0].pinned)
        self.assertIn("keep-label", notes[0].labels)

    def test_import_conflict_copy_marks_duplicate(self):
        local = app.Note(id="local", title="Same title", content="Local body")
        incoming = app.Note(id="incoming", title="Same title", content="Imported body")
        self.assertTrue(self.db.save_note(local))

        result = self.db.save_imported_note(incoming, conflict_policy="copy")
        notes = self.db.get_all_notes()

        self.assertEqual(result, "conflict_copy")
        self.assertEqual(len(notes), 2)
        conflict = next(note for note in notes if note.id != "local")
        self.assertEqual(conflict.sync_status, app.SyncStatus.CONFLICT)
        self.assertIn("import-conflict", conflict.labels)

    def test_import_conflict_merge_combines_content(self):
        local = app.Note(id="local", title="Same title", content="Local body")
        incoming = app.Note(id="incoming", title="Same title", content="Imported body")
        self.assertTrue(self.db.save_note(local))

        result = self.db.save_imported_note(incoming, conflict_policy="merge")
        merged = self.db.get_note("local")

        self.assertEqual(result, "imported")
        self.assertIn("Local body", merged.content)
        self.assertIn("Imported body", merged.content)

    def test_import_identical_duplicate_is_skipped(self):
        local = app.Note(id="local", title="Same title", content="Same body")
        incoming = app.Note(id="incoming", title="Same title", content="Same body")
        self.assertTrue(self.db.save_note(local))

        result = self.db.save_imported_note(incoming, conflict_policy="copy")

        self.assertEqual(result, "skipped")
        self.assertEqual(len(self.db.get_all_notes()), 1)


if __name__ == "__main__":
    unittest.main()
