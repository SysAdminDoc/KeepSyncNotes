import tempfile
import unittest
from pathlib import Path

import keepsync_notes as app


class FakeCredentialStore:
    def __init__(self):
        self.values = {}
        self.last_error = ""

    def get_secret(self, key):
        return self.values.get(key)

    def set_secret(self, key, value):
        self.values[key] = value
        return True

    def delete_secret(self, key):
        self.values.pop(key, None)
        return True


class SecureCredentialTests(unittest.TestCase):
    def setUp(self):
        self.original_store = app.SECURE_CREDENTIALS
        self.store = FakeCredentialStore()
        app.set_secure_credential_store(self.store)
        self.tmp = tempfile.TemporaryDirectory()
        self.db = app.DatabaseManager(str(Path(self.tmp.name) / "notes.db"))

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()
        app.set_secure_credential_store(self.original_store)

    def test_migrates_sqlite_secret_to_keyring_and_deletes_setting(self):
        self.db.set_setting("keep_master_token", "legacy-token")

        secret = app.migrate_setting_secret(
            self.db,
            "keep_master_token",
            app.KEEP_MASTER_TOKEN_CREDENTIAL,
        )

        self.assertEqual(secret, "legacy-token")
        self.assertEqual(self.store.values[app.KEEP_MASTER_TOKEN_CREDENTIAL], "legacy-token")
        self.assertIsNone(self.db.get_setting("keep_master_token"))

    def test_migrates_legacy_token_file_to_keyring_and_deletes_file(self):
        token_file = Path(self.tmp.name) / "gdrive_token.json"
        token_file.write_text('{"refresh_token": "legacy"}', encoding="utf-8")

        secret = app.migrate_file_secret(str(token_file), app.GDRIVE_OAUTH_TOKEN_CREDENTIAL)

        self.assertEqual(secret, '{"refresh_token": "legacy"}')
        self.assertEqual(self.store.values[app.GDRIVE_OAUTH_TOKEN_CREDENTIAL], '{"refresh_token": "legacy"}')
        self.assertFalse(token_file.exists())

    def test_store_file_secret_removes_legacy_file_copy(self):
        token_file = Path(self.tmp.name) / "gdrive_token.json"
        token_file.write_text('{"refresh_token": "legacy"}', encoding="utf-8")

        saved = app.store_file_secret(
            app.GDRIVE_OAUTH_TOKEN_CREDENTIAL,
            '{"refresh_token": "new"}',
            str(token_file),
        )

        self.assertTrue(saved)
        self.assertEqual(self.store.values[app.GDRIVE_OAUTH_TOKEN_CREDENTIAL], '{"refresh_token": "new"}')
        self.assertFalse(token_file.exists())


if __name__ == "__main__":
    unittest.main()
