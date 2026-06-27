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


if __name__ == "__main__":
    unittest.main()
