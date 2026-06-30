import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import keepsync_cloud_sync as cloud_sync
import keepsync_notes as app


class FakeCloudProvider(cloud_sync.CloudSyncProvider):
    def __init__(self, db):
        super().__init__(db, "Backup App", "9.8.7", 6)
        self.is_connected = True
        self.synced = False

    def connect(self, **kwargs):
        return True, "connected"

    def disconnect(self):
        self.is_connected = False

    def sync(self):
        self.synced = True
        return True, "synced", {"uploaded": 0}

    def get_provider_name(self):
        return "Fake Cloud"


class CloudSyncModuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = app.DatabaseManager(str(Path(self.tmp.name) / "notes.db"))

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_app_reexports_cloud_sync_api_for_compatibility(self):
        self.assertIs(app.CloudSyncManager, cloud_sync.CloudSyncManager)
        self.assertIs(app.CloudSyncProvider, cloud_sync.CloudSyncProvider)
        self.assertIs(app.GoogleDriveSync, cloud_sync.GoogleDriveSync)
        self.assertIs(app.GitHubSync, cloud_sync.GitHubSync)

    def test_manager_initializes_providers_with_app_metadata(self):
        manager = cloud_sync.CloudSyncManager(self.db, "Unit App", "9.9.9", 42)

        self.assertEqual(manager.app_name, "Unit App")
        self.assertEqual(manager.app_version, "9.9.9")
        self.assertEqual(manager.db_version, 42)
        self.assertIsInstance(manager.get_provider("gdrive"), cloud_sync.GoogleDriveSync)
        self.assertIsInstance(manager.get_provider("github"), cloud_sync.GitHubSync)
        self.assertEqual(manager.get_provider("gdrive").app_version, "9.9.9")
        self.assertEqual(manager.get_provider("github").db_version, 42)
        self.assertIsNone(manager.get_provider("missing"))

    def test_sync_creates_local_backup_before_provider_sync(self):
        manager = cloud_sync.CloudSyncManager(self.db, "Backup App", "9.8.7", 6)
        provider = FakeCloudProvider(self.db)
        manager.providers = {"fake": provider}
        manager.active_provider = provider

        success, message, stats = manager.sync()

        self.assertTrue(success)
        self.assertEqual(message, "synced")
        self.assertEqual(stats, {"uploaded": 0})
        self.assertTrue(provider.synced)
        backups = list((Path(self.tmp.name) / "backups").glob("keepsync-backup-*.zip"))
        self.assertEqual(len(backups), 1)
        with zipfile.ZipFile(backups[0]) as zf:
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        self.assertEqual(manifest["app"], "Backup App")
        self.assertEqual(manifest["app_version"], "9.8.7")
        self.assertEqual(manifest["reason"], "before Fake Cloud sync")


if __name__ == "__main__":
    unittest.main()
