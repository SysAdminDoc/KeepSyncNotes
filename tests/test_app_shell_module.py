import unittest

import keepsync_app as app_shell
import keepsync_app_info as app_info
import keepsync_keep_sync as keep_sync
import keepsync_notes as app


class AppShellModuleTests(unittest.TestCase):
    def test_app_reexports_shell_and_keep_sync_api_for_compatibility(self):
        self.assertIs(app.KeepSyncNotesApp, app_shell.KeepSyncNotesApp)
        self.assertIs(app.KeepSyncEngine, keep_sync.KeepSyncEngine)
        self.assertIs(app.KeepWebScraper, keep_sync.KeepWebScraper)
        self.assertIs(app.get_master_token_cli, keep_sync.get_master_token_cli)

    def test_app_reexports_shared_metadata_for_compatibility(self):
        self.assertEqual(app.APP_NAME, app_info.APP_NAME)
        self.assertEqual(app.APP_VERSION, app_info.APP_VERSION)
        self.assertEqual(app.DB_VERSION, app_info.DB_VERSION)


if __name__ == "__main__":
    unittest.main()
