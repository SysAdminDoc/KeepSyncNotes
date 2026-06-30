import tempfile
import unittest
from pathlib import Path

from PIL import Image

import keepsync_attachment_editing as editing
import keepsync_notes as app


class AttachmentEditingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = str(self.root / "notes.db")

    def tearDown(self):
        self.tmp.cleanup()

    def make_image(self, name="source.png"):
        path = self.root / name
        Image.new("RGB", (8, 8), "red").save(path)
        return path

    def test_copy_image_attachment_stores_file_under_note_directory(self):
        source = self.make_image()

        attachment = editing.copy_image_attachment(source, self.db_path, "note-1")

        stored = Path(attachment.stored_path)
        self.assertTrue(stored.exists())
        self.assertEqual(stored.parent, self.root / "attachments" / "note-1")
        self.assertEqual(attachment.mime_type, "image/png")

    def test_clipboard_image_attachment_saves_png(self):
        image = Image.new("RGB", (4, 4), "blue")

        attachment = editing.save_clipboard_image_attachment(image, self.db_path, "note-2")

        self.assertTrue(Path(attachment.stored_path).exists())
        self.assertEqual(attachment.mime_type, "image/png")

    def test_app_reexports_attachment_editing_helpers_for_compatibility(self):
        self.assertIs(app.copy_image_attachment, editing.copy_image_attachment)
        self.assertIs(app.save_clipboard_image_attachment, editing.save_clipboard_image_attachment)
        self.assertIs(app.note_attachment_dir, editing.note_attachment_dir)


if __name__ == "__main__":
    unittest.main()
