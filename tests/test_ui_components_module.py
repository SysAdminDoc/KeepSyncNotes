import unittest

import keepsync_notes as app
import keepsync_ui_components as components


class UIComponentsModuleTests(unittest.TestCase):
    def test_app_reexports_component_api_for_compatibility(self):
        self.assertIs(app.IconManager, components.IconManager)
        self.assertIs(app.SyncStatusBadge, components.SyncStatusBadge)
        self.assertIs(app.NoteCard, components.NoteCard)
        self.assertIs(app.configure_note_card_helpers, components.configure_note_card_helpers)

    def test_app_wires_note_card_helper_functions(self):
        self.assertIs(components.note_uses_markdown, app.note_uses_markdown)
        self.assertIs(components.markdown_preview_text, app.markdown_preview_text)
        self.assertIs(components.format_reminder_datetime, app.format_reminder_datetime)


if __name__ == "__main__":
    unittest.main()
