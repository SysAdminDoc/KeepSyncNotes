"""OS keyring-backed credential storage and legacy secret migration."""

from pathlib import Path
from typing import Any, Optional

try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    keyring = None
    KEYRING_AVAILABLE = False


KEYRING_SERVICE = "KeepSyncNotes"
KEEP_MASTER_TOKEN_CREDENTIAL = "google_keep_master_token"
GDRIVE_OAUTH_TOKEN_CREDENTIAL = "google_drive_oauth_token"
GITHUB_PAT_CREDENTIAL = "github_personal_access_token"


class KeyringCredentialStore:
    """Small wrapper around the OS credential store used for sync secrets."""

    service_name = KEYRING_SERVICE

    def __init__(self):
        self.last_error = ""

    def _available(self) -> bool:
        if KEYRING_AVAILABLE and keyring is not None:
            return True
        self.last_error = "Python keyring package is not available."
        return False

    def get_secret(self, key: str) -> Optional[str]:
        if not self._available():
            return None
        try:
            return keyring.get_password(self.service_name, key)
        except Exception as e:
            self.last_error = str(e)
            return None

    def set_secret(self, key: str, value: str) -> bool:
        if not value:
            return self.delete_secret(key)
        if not self._available():
            return False
        try:
            keyring.set_password(self.service_name, key, value)
            self.last_error = ""
            return True
        except Exception as e:
            self.last_error = str(e)
            return False

    def delete_secret(self, key: str) -> bool:
        if not self._available():
            return False
        try:
            keyring.delete_password(self.service_name, key)
            self.last_error = ""
            return True
        except Exception as e:
            if "not found" not in str(e).lower():
                self.last_error = str(e)
            return False


SECURE_CREDENTIALS = KeyringCredentialStore()


def set_secure_credential_store(store: Any):
    """Swap the credential store for tests."""
    global SECURE_CREDENTIALS
    SECURE_CREDENTIALS = store


def migrate_setting_secret(db: Any, setting_key: str, credential_key: str) -> Optional[str]:
    """Move a legacy SQLite setting secret into the OS credential store."""
    secret = SECURE_CREDENTIALS.get_secret(credential_key)
    legacy_secret = db.get_setting(setting_key)
    if not legacy_secret:
        return secret

    if SECURE_CREDENTIALS.set_secret(credential_key, str(legacy_secret)):
        if hasattr(db, "delete_setting"):
            db.delete_setting(setting_key)
        else:
            db.set_setting(setting_key, None)
        return str(legacy_secret)
    return secret or str(legacy_secret)


def migrate_file_secret(file_path: str, credential_key: str) -> Optional[str]:
    """Move a legacy token file into the OS credential store."""
    path = Path(file_path)
    secret = SECURE_CREDENTIALS.get_secret(credential_key)
    legacy_secret = ""
    if path.exists():
        legacy_secret = path.read_text(encoding="utf-8").strip()

    if legacy_secret and not secret:
        if SECURE_CREDENTIALS.set_secret(credential_key, legacy_secret):
            secret = legacy_secret

    if secret and path.exists():
        try:
            path.unlink()
        except OSError:
            pass

    return secret or legacy_secret or None


def store_file_secret(credential_key: str, value: str, legacy_file_path: Optional[str] = None) -> bool:
    """Persist a token in the OS credential store and remove any legacy file copy."""
    if not SECURE_CREDENTIALS.set_secret(credential_key, value):
        return False
    if legacy_file_path:
        try:
            Path(legacy_file_path).unlink(missing_ok=True)
        except OSError:
            pass
    return True
