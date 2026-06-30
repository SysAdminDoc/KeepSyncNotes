import unittest

import keepsync_note_editor as editor
import keepsync_note_text as note_text
import keepsync_notes as app


class NoteEditorModuleTests(unittest.TestCase):
    def test_app_reexports_note_editor_for_compatibility(self):
        self.assertIs(app.NoteEditor, editor.NoteEditor)

    def test_app_reexports_note_text_helpers_for_compatibility(self):
        self.assertIs(app.parse_reminder_datetime, note_text.parse_reminder_datetime)
        self.assertIs(app.format_reminder_datetime, note_text.format_reminder_datetime)
        self.assertIs(app.note_uses_markdown, note_text.note_uses_markdown)
        self.assertIs(app.markdown_preview_blocks, note_text.markdown_preview_blocks)
        self.assertIs(app.markdown_preview_text, note_text.markdown_preview_text)


if __name__ == "__main__":
    unittest.main()
