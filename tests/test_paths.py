import tempfile
import unittest
from pathlib import Path

import keepsync_notes as app
import keepsync_paths as paths


class PathHelperTests(unittest.TestCase):
    def test_windows_data_dir_uses_localappdata(self):
        result = paths.get_platform_data_dir(
            home=Path("C:/Users/Example"),
            env={"LOCALAPPDATA": "C:/Users/Example/AppData/Local"},
            system="Windows",
        )

        self.assertEqual(result, Path("C:/Users/Example/AppData/Local") / "KeepSyncNotes")

    def test_macos_data_dir_uses_application_support(self):
        result = paths.get_platform_data_dir(home=Path("/Users/example"), env={}, system="Darwin")

        self.assertEqual(result, Path("/Users/example/Library/Application Support/KeepSyncNotes"))

    def test_linux_data_dir_uses_xdg_data_home(self):
        result = paths.get_platform_data_dir(
            home=Path("/home/example"),
            env={"XDG_DATA_HOME": "/data/apps"},
            system="Linux",
        )

        self.assertEqual(result, Path("/data/apps/KeepSyncNotes"))

    def test_existing_legacy_dir_is_preserved_until_platform_dir_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            legacy = home / ".keepsync_notes"
            legacy.mkdir()

            result = paths.get_app_data_dir(home=home, env={}, system="Linux")

            self.assertEqual(result, legacy)

    def test_platform_dir_wins_when_it_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".keepsync_notes").mkdir()
            platform_dir = home / ".local" / "share" / "KeepSyncNotes"
            platform_dir.mkdir(parents=True)

            result = paths.get_app_data_dir(home=home, env={}, system="Linux")

            self.assertEqual(result, platform_dir)

    def test_google_drive_file_helpers_use_selected_data_dir(self):
        root = Path("/tmp/KeepSyncNotes")

        self.assertEqual(paths.get_google_drive_credentials_path(root), root / "gdrive_credentials.json")
        self.assertEqual(paths.get_google_drive_token_path(root), root / "gdrive_token.json")

    def test_app_reexports_path_helpers_for_compatibility(self):
        self.assertIs(app.get_app_data_dir, paths.get_app_data_dir)
        self.assertIs(app.get_google_drive_credentials_path, paths.get_google_drive_credentials_path)
        self.assertIs(app.get_google_drive_token_path, paths.get_google_drive_token_path)


if __name__ == "__main__":
    unittest.main()
