import tempfile
import unittest
import zipfile
from pathlib import Path

import keepsync_notes as app


class LocalBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "notes.db"
        self.db = app.DatabaseManager(str(self.db_path))

    def tearDown(self):
        if self.db.conn:
            self.db.close()
        self.tmp.cleanup()

    def test_backup_contains_database_manifest_and_attachments(self):
        attachments = self.root / "attachments" / "note1"
        attachments.mkdir(parents=True)
        (attachments / "scan.png").write_bytes(b"image")
        self.db.save_note(app.Note(id="original", title="Original", content="Body"))

        backup = app.LocalBackupManager(self.db).create_backup("unit test")

        with zipfile.ZipFile(backup) as zf:
            names = set(zf.namelist())

        self.assertIn("notes.db", names)
        self.assertIn("manifest.json", names)
        self.assertIn("attachments/note1/scan.png", names)

    def test_restore_replaces_database_and_attachment_state(self):
        attachments = self.root / "attachments" / "note1"
        attachments.mkdir(parents=True)
        attachment_path = attachments / "scan.png"
        attachment_path.write_bytes(b"original")
        self.db.save_note(app.Note(id="original", title="Original", content="Body"))

        manager = app.LocalBackupManager(self.db)
        backup = manager.create_backup("restore point")

        self.db.save_note(app.Note(id="new", title="New", content="Later"))
        attachment_path.write_bytes(b"changed")
        manager.restore_backup(backup)

        self.db = app.DatabaseManager(str(self.db_path))

        self.assertIsNotNone(self.db.get_note("original"))
        self.assertIsNone(self.db.get_note("new"))
        self.assertEqual(attachment_path.read_bytes(), b"original")


if __name__ == "__main__":
    unittest.main()
