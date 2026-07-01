import unittest

import keepsync_clipboard_import as clip
import keepsync_notes as app


class ClipboardImportTests(unittest.TestCase):
    def test_clipboard_items_to_notes_creates_labeled_notes(self):
        items = [
            {"text": "First line\nMore text here", "timestamp": None},
            {"text": "Single line", "timestamp": None},
        ]
        notes = clip.clipboard_items_to_notes(items)
        self.assertEqual(len(notes), 2)
        self.assertEqual(notes[0].title, "First line")
        self.assertIn("clipboard-import", notes[0].labels)
        self.assertEqual(notes[1].title, "Single line")

    def test_empty_items_are_skipped(self):
        items = [{"text": "", "timestamp": None}, {"text": "   ", "timestamp": None}]
        notes = clip.clipboard_items_to_notes(items)
        self.assertEqual(len(notes), 0)

    def test_title_truncated_to_80_chars(self):
        items = [{"text": "A" * 200, "timestamp": None}]
        notes = clip.clipboard_items_to_notes(items)
        self.assertLessEqual(len(notes[0].title), 80)

    def test_app_reexports_clipboard_import_helpers(self):
        self.assertIs(app.CLIPBOARD_HISTORY_AVAILABLE, clip.CLIPBOARD_HISTORY_AVAILABLE)
        self.assertIs(app.clipboard_items_to_notes, clip.clipboard_items_to_notes)


if __name__ == "__main__":
    unittest.main()
