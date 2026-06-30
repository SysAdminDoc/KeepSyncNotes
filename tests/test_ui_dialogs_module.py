import unittest

import keepsync_notes as app
import keepsync_settings_dialog as settings_dialog
import keepsync_theme as theme
import keepsync_ui_dialogs as dialogs


class UIDialogsModuleTests(unittest.TestCase):
    def test_app_reexports_theme_for_compatibility(self):
        self.assertIs(app.COLORS, theme.COLORS)
        self.assertEqual(theme.COLORS["bg_darkest"], "#020617")
        self.assertIn("accent_green", theme.COLORS)

    def test_app_reexports_dialog_api_for_compatibility(self):
        self.assertIs(app.AdvancedFilterDialog, dialogs.AdvancedFilterDialog)
        self.assertIs(app.ImportConflictDialog, dialogs.ImportConflictDialog)
        self.assertIs(app.TakeoutInstructionsDialog, dialogs.TakeoutInstructionsDialog)
        self.assertIs(app.TokenGeneratorDialog, dialogs.TokenGeneratorDialog)
        self.assertIs(app.ImportProgressDialog, dialogs.ImportProgressDialog)
        self.assertIs(app.DiagnosticsDialog, dialogs.DiagnosticsDialog)
        self.assertIs(app.SettingsDialog, settings_dialog.SettingsDialog)


if __name__ == "__main__":
    unittest.main()
