import sqlite3
import tempfile
import unittest
from pathlib import Path

import keepsync_encrypted_backup as enc_backup


class EncryptedBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = str(self.root / "notes.db")
        self._create_test_db()

    def tearDown(self):
        self.tmp.cleanup()

    def _create_test_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE notes (
                id TEXT PRIMARY KEY,
                title TEXT DEFAULT '',
                content TEXT DEFAULT '',
                trashed INTEGER DEFAULT 0
            )
        """)
        conn.execute("INSERT INTO notes (id, title, content) VALUES ('n1', 'Test', 'Hello')")
        conn.execute("INSERT INTO notes (id, title, content) VALUES ('n2', 'Second', 'World')")
        conn.execute("INSERT INTO notes (id, title, content, trashed) VALUES ('n3', 'Trash', 'Gone', 1)")
        conn.commit()
        conn.close()

    def test_create_and_restore_encrypted_backup(self):
        backup = self.root / "backup.ksenc"
        result = enc_backup.create_encrypted_backup(self.db_path, backup, "secret123")

        self.assertTrue(backup.exists())
        self.assertEqual(result.notes_count, 2)
        self.assertGreater(result.size_bytes, 0)

        restore_path = str(self.root / "restored.db")
        count = enc_backup.restore_encrypted_backup(backup, "secret123", restore_path)

        self.assertEqual(count, 2)
        conn = sqlite3.connect(restore_path)
        rows = conn.execute("SELECT title FROM notes WHERE trashed = 0 ORDER BY title").fetchall()
        conn.close()
        self.assertEqual([r[0] for r in rows], ["Second", "Test"])

    def test_wrong_password_raises(self):
        backup = self.root / "backup.ksenc"
        enc_backup.create_encrypted_backup(self.db_path, backup, "correct")

        with self.assertRaises(ValueError) as ctx:
            enc_backup.restore_encrypted_backup(backup, "wrong", str(self.root / "fail.db"))
        self.assertIn("wrong password", str(ctx.exception).lower())

    def test_invalid_file_raises(self):
        bad_file = self.root / "bad.ksenc"
        bad_file.write_bytes(b"not a backup")

        with self.assertRaises(ValueError):
            enc_backup.restore_encrypted_backup(bad_file, "pass", str(self.root / "fail.db"))

    def test_read_backup_header(self):
        backup = self.root / "backup.ksenc"
        enc_backup.create_encrypted_backup(self.db_path, backup, "pw")

        header = enc_backup.read_backup_header(backup)
        self.assertIsNotNone(header)
        self.assertEqual(header["cipher"], "aes-256-gcm")
        self.assertIn("created", header)

    def test_read_header_returns_none_for_invalid(self):
        bad = self.root / "bad.dat"
        bad.write_bytes(b"garbage")
        self.assertIsNone(enc_backup.read_backup_header(bad))

    def test_restore_creates_pre_restore_copy(self):
        backup = self.root / "backup.ksenc"
        enc_backup.create_encrypted_backup(self.db_path, backup, "pw")

        restore_path = self.root / "target.db"
        restore_path.write_bytes(b"old db content")

        enc_backup.restore_encrypted_backup(backup, "pw", str(restore_path))
        self.assertTrue(restore_path.with_suffix(".db.pre-restore").exists())


if __name__ == "__main__":
    unittest.main()
