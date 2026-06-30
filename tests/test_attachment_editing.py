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

    def test_parse_drop_file_paths_handles_tk_file_lists(self):
        paths = editing.parse_drop_file_paths("{/tmp/space image.png} /tmp/second.jpg file:///tmp/third.png")

        self.assertEqual(
            paths,
            [
                Path("/tmp/space image.png"),
                Path("/tmp/second.jpg"),
                Path("/tmp/third.png"),
            ],
        )

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

    def test_copy_image_attachments_copies_supported_images_and_skips_other_files(self):
        first = self.make_image("first.png")
        second = self.make_image("second.jpg")
        text_file = self.root / "note.txt"
        text_file.write_text("not an image", encoding="utf-8")

        result = editing.copy_image_attachments([first, text_file, second], self.db_path, "note-3")

        self.assertEqual(len(result.attachments), 2)
        self.assertEqual(result.skipped_paths, [text_file])
        self.assertEqual(result.failed_paths, [])
        self.assertTrue(all(Path(item.stored_path).exists() for item in result.attachments))

    def test_copy_image_attachments_reports_invalid_image_failures(self):
        bad_image = self.root / "bad.png"
        bad_image.write_text("not an image", encoding="utf-8")

        result = editing.copy_image_attachments([bad_image], self.db_path, "note-4")

        self.assertEqual(result.attachments, [])
        self.assertEqual(result.skipped_paths, [])
        self.assertEqual(len(result.failed_paths), 1)
        self.assertEqual(result.failed_paths[0][0], bad_image)

    def test_app_reexports_attachment_editing_helpers_for_compatibility(self):
        self.assertIs(app.copy_image_attachment, editing.copy_image_attachment)
        self.assertIs(app.copy_image_attachments, editing.copy_image_attachments)
        self.assertIs(app.save_clipboard_image_attachment, editing.save_clipboard_image_attachment)
        self.assertIs(app.note_attachment_dir, editing.note_attachment_dir)
        self.assertIs(app.parse_drop_file_paths, editing.parse_drop_file_paths)


if __name__ == "__main__":
    unittest.main()
