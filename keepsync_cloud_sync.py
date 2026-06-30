"""Cloud sync providers for Google Drive and GitHub backends."""

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

import keepsync_credentials as credentials_state
from keepsync_backups import LocalBackupManager
from keepsync_cloud_plan import (
    build_cloud_sync_plan,
    cloud_base_versions,
    cloud_plan_counts,
    save_cloud_conflict_copy,
)
from keepsync_credentials import (
    GDRIVE_OAUTH_TOKEN_CREDENTIAL,
    GITHUB_PAT_CREDENTIAL,
    migrate_file_secret,
    migrate_setting_secret,
    store_file_secret,
)
from keepsync_diagnostics import log_diagnostic_event, log_diagnostic_exception
from keepsync_models import Note
from keepsync_paths import (
    get_app_data_dir,
    get_google_drive_credentials_path,
    get_google_drive_token_path,
)
from keepsync_storage import DatabaseManager


class CloudSyncProvider:
    """Base class for cloud sync providers"""

    def __init__(
        self,
        db: DatabaseManager,
        app_name: str = "KeepSync Notes",
        app_version: str = "0.0.0",
        db_version: int = 1,
    ):
        self.db = db
        self.app_name = app_name
        self.app_version = app_version
        self.db_version = db_version
        self.is_connected = False
        self.last_sync: Optional[datetime] = None
        self.sync_callbacks: List[Callable] = []

    def add_callback(self, callback: Callable):
        self.sync_callbacks.append(callback)

    def _notify(self, status: str, message: str):
        for cb in self.sync_callbacks:
            try:
                cb(status, message)
            except:
                pass

    def connect(self, **kwargs) -> tuple[bool, str]:
        raise NotImplementedError

    def disconnect(self):
        raise NotImplementedError

    def sync(self) -> tuple[bool, str, dict]:
        raise NotImplementedError

    def get_provider_name(self) -> str:
        raise NotImplementedError


class GoogleDriveSync(CloudSyncProvider):
    """
    Sync notes to Google Drive as JSON files.
    Uses a dedicated folder to store all notes.
    """

    FOLDER_NAME = "KeepSync Notes Backup"
    NOTES_FILE = "notes_backup.json"
    SCOPES = ['https://www.googleapis.com/auth/drive.file']

    def __init__(
        self,
        db: DatabaseManager,
        app_name: str = "KeepSync Notes",
        app_version: str = "0.0.0",
        db_version: int = 1,
    ):
        super().__init__(db, app_name, app_version, db_version)
        self.service = None
        self.folder_id = None
        self.creds = None

    def get_provider_name(self) -> str:
        return "Google Drive"

    def connect(self, credentials_path: str = None, token_path: str = None) -> tuple[bool, str]:
        """
        Connect to Google Drive using OAuth credentials.

        Args:
            credentials_path: Path to OAuth client credentials JSON (from Google Cloud Console)
            token_path: Path to store/load the user's auth token
        """
        try:
            try:
                from google.oauth2.credentials import Credentials
                from google_auth_oauthlib.flow import InstalledAppFlow
                from google.auth.transport.requests import Request
                from googleapiclient.discovery import build
                from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
            except ImportError:
                return False, "Google Drive dependencies are not installed. Run: python -m pip install -r requirements.txt"

            # Default paths
            data_dir = get_app_data_dir()
            if not token_path:
                token_path = str(get_google_drive_token_path(data_dir))
            if not credentials_path:
                credentials_path = str(get_google_drive_credentials_path(data_dir))

            creds = None

            # Load existing token from OS keyring, migrating the old JSON token file if present.
            token_json = migrate_file_secret(token_path, GDRIVE_OAUTH_TOKEN_CREDENTIAL)
            if token_json:
                creds = Credentials.from_authorized_user_info(json.loads(token_json), self.SCOPES)

            # Refresh or get new credentials
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    if not os.path.exists(credentials_path):
                        return False, (
                            "Google Drive credentials not found.\n\n"
                            "To set up Google Drive sync:\n"
                            "1. Go to console.cloud.google.com\n"
                            "2. Create a project and enable Drive API\n"
                            "3. Create OAuth credentials (Desktop app)\n"
                            "4. Download and save as:\n"
                            f"   {credentials_path}"
                        )

                    flow = InstalledAppFlow.from_client_secrets_file(credentials_path, self.SCOPES)
                    creds = flow.run_local_server(port=0)

                if not store_file_secret(GDRIVE_OAUTH_TOKEN_CREDENTIAL, creds.to_json(), token_path):
                    return False, f"Google Drive token was not saved because OS keyring is unavailable: {credentials_state.SECURE_CREDENTIALS.last_error}"

            self.creds = creds
            self.service = build('drive', 'v3', credentials=creds)

            # Find or create our folder
            self._ensure_folder()

            self.is_connected = True
            self.db.set_setting("cloud_provider", "gdrive")
            self._notify("connected", "Connected to Google Drive")

            return True, "Connected to Google Drive successfully"

        except Exception as e:
            log_diagnostic_exception("Google Drive connection", e)
            return False, f"Google Drive connection failed: {str(e)}"

    def _ensure_folder(self):
        """Find or create the backup folder in Google Drive"""
        # Search for existing folder
        results = self.service.files().list(
            q=f"name='{self.FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
            spaces='drive',
            fields='files(id, name)'
        ).execute()

        files = results.get('files', [])

        if files:
            self.folder_id = files[0]['id']
        else:
            # Create folder
            file_metadata = {
                'name': self.FOLDER_NAME,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            folder = self.service.files().create(body=file_metadata, fields='id').execute()
            self.folder_id = folder.get('id')

    def disconnect(self):
        """Disconnect from Google Drive"""
        self.service = None
        self.creds = None
        self.folder_id = None
        self.is_connected = False
        self.db.set_setting("cloud_provider", None)
        credentials_state.SECURE_CREDENTIALS.delete_secret(GDRIVE_OAUTH_TOKEN_CREDENTIAL)
        self._notify("disconnected", "Disconnected from Google Drive")

    def sync(self) -> tuple[bool, str, dict]:
        """
        Sync notes with Google Drive.
        Uses a single JSON file containing all notes.
        """
        if not self.is_connected or not self.service:
            return False, "Not connected to Google Drive", {}

        stats = {"uploaded": 0, "downloaded": 0, "conflicts": 0, "deleted": 0}

        try:
            self._notify("syncing", "Syncing with Google Drive...")

            # Get local notes
            local_notes = self.db.get_all_notes(include_archived=True, include_trashed=False)
            local_data = {
                "version": self.db_version,
                "synced_at": datetime.now(timezone.utc).isoformat(),
                "notes": [n.to_dict() for n in local_notes],
                "labels": [l.to_dict() for l in self.db.get_all_labels()]
            }

            # Check for existing backup file
            results = self.service.files().list(
                q=f"name='{self.NOTES_FILE}' and '{self.folder_id}' in parents and trashed=false",
                spaces='drive',
                fields='files(id, name, modifiedTime)'
            ).execute()

            remote_files = results.get('files', [])
            remote_notes = {}

            if remote_files:
                # Download and merge with remote
                file_id = remote_files[0]['id']

                # Download remote file
                import io
                from googleapiclient.http import MediaIoBaseDownload

                request = self.service.files().get_media(fileId=file_id)
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()

                fh.seek(0)
                remote_data = json.loads(fh.read().decode('utf-8'))
                remote_notes = {
                    note["id"]: note for note in remote_data.get("notes", [])
                    if isinstance(note, dict) and note.get("id")
                }

            base_versions = self.db.get_setting("cloud_base_gdrive", {})
            if not isinstance(base_versions, dict):
                base_versions = {}
            plan = build_cloud_sync_plan(local_notes, remote_notes, base_versions)
            dry_run = cloud_plan_counts(plan)
            stats["dry_run"] = dry_run
            log_diagnostic_event("info", f"Google Drive sync plan: {dry_run}")
            self._notify(
                "syncing",
                f"Drive plan c{dry_run['create']} u{dry_run['update']} d{dry_run['delete']} x{dry_run['conflict']}"
            )

            for local_note in plan["delete_local"]:
                if self.db.delete_note(local_note.id):
                    stats["deleted"] += 1

            for remote_note in plan["download_creates"] + plan["download_updates"]:
                self.db.save_note(Note.from_dict(remote_note))
                stats["downloaded"] += 1

            for _local_note, remote_note in plan["conflicts"]:
                if save_cloud_conflict_copy(self.db, remote_note, "Drive"):
                    stats["conflicts"] += 1

            stats["deleted"] += len(plan["delete_remote"])
            stats["uploaded"] = len(plan["upload_creates"]) + len(plan["upload_updates"])
            local_notes = self.db.get_all_notes(include_archived=True, include_trashed=False)
            local_data["notes"] = [n.to_dict() for n in local_notes]

            # Upload merged data
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(local_data, f, indent=2)
                temp_path = f.name

            from googleapiclient.http import MediaFileUpload
            media = MediaFileUpload(temp_path, mimetype='application/json')

            if remote_files:
                # Update existing file
                self.service.files().update(
                    fileId=remote_files[0]['id'],
                    media_body=media
                ).execute()
            else:
                # Create new file
                file_metadata = {
                    'name': self.NOTES_FILE,
                    'parents': [self.folder_id]
                }
                self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()

            os.unlink(temp_path)

            self.last_sync = datetime.now(timezone.utc)
            self.db.set_setting("gdrive_last_sync", self.last_sync.isoformat())
            self.db.set_setting("cloud_base_gdrive", cloud_base_versions(local_notes))

            self._notify("synced", f"Drive sync: ↑{stats['uploaded']} ↓{stats['downloaded']}")
            return True, "Sync completed", stats

        except Exception as e:
            log_diagnostic_exception("Google Drive sync", e)
            self._notify("error", f"Sync error: {str(e)}")
            return False, f"Sync error: {str(e)}", stats


class GitHubSync(CloudSyncProvider):
    """
    Sync notes to a private GitHub repository.
    Stores notes as individual JSON files for better version history.
    """

    NOTES_DIR = "notes"
    LABELS_FILE = "labels.json"
    METADATA_FILE = "metadata.json"

    def __init__(
        self,
        db: DatabaseManager,
        app_name: str = "KeepSync Notes",
        app_version: str = "0.0.0",
        db_version: int = 1,
    ):
        super().__init__(db, app_name, app_version, db_version)
        self.token = None
        self.repo_name = None
        self.repo = None
        self.github = None

    def get_provider_name(self) -> str:
        return "GitHub"

    def connect(self, token: str = None, repo_name: str = "", create_if_missing: bool = True) -> tuple[bool, str]:
        """
        Connect to GitHub and set up the notes repository.

        Args:
            token: GitHub Personal Access Token (needs 'repo' scope)
            repo_name: Repository name (e.g., 'my-notes-backup')
            create_if_missing: Create repo if it doesn't exist
        """
        try:
            try:
                from github import Github, GithubException
            except ImportError:
                return False, "PyGithub is not installed. Run: python -m pip install -r requirements.txt"

            token = token or migrate_setting_secret(self.db, "github_token", GITHUB_PAT_CREDENTIAL)
            if not token:
                return False, "GitHub token not found in the OS keyring. Enter a token once to save it securely."

            self.github = Github(token)
            self.token = token
            self.repo_name = repo_name

            # Get authenticated user
            user = self.github.get_user()

            # Find or create repo
            try:
                self.repo = user.get_repo(repo_name)
            except GithubException as e:
                if e.status == 404 and create_if_missing:
                    # Create private repo
                    self.repo = user.create_repo(
                        repo_name,
                        description="KeepSync Notes Backup - Auto-synced notes",
                        private=True,
                        auto_init=True
                    )
                else:
                    return False, f"Repository '{repo_name}' not found"

            # Verify repo is accessible
            try:
                self.repo.get_contents("")
            except GithubException:
                # Empty repo, initialize it
                self.repo.create_file(
                    "README.md",
                    "Initial commit",
                    f"# {repo_name}\n\nKeepSync Notes Backup - Auto-synced notes\n"
                )

            self.is_connected = True
            self.db.set_setting("cloud_provider", "github")
            self.db.set_setting("github_repo", repo_name)
            if not credentials_state.SECURE_CREDENTIALS.set_secret(GITHUB_PAT_CREDENTIAL, token):
                self.db.log_sync("credentials", "github", "warning", credentials_state.SECURE_CREDENTIALS.last_error)
                self._notify("connected", f"Connected to GitHub: {repo_name}")
                return True, f"Connected to GitHub repository: {repo_name}. Token was not saved because OS keyring is unavailable."
            self.db.delete_setting("github_token")

            self._notify("connected", f"Connected to GitHub: {repo_name}")
            return True, f"Connected to GitHub repository: {repo_name}"

        except Exception as e:
            log_diagnostic_exception("GitHub connection", e)
            return False, f"GitHub connection failed: {str(e)}"

    def disconnect(self):
        """Disconnect from GitHub"""
        self.github = None
        self.repo = None
        self.token = None
        self.is_connected = False
        self.db.set_setting("cloud_provider", None)
        self.db.delete_setting("github_token")
        credentials_state.SECURE_CREDENTIALS.delete_secret(GITHUB_PAT_CREDENTIAL)
        self._notify("disconnected", "Disconnected from GitHub")

    def sync(self) -> tuple[bool, str, dict]:
        """
        Sync notes with GitHub repository.
        Each note is stored as a separate JSON file for better git history.
        """
        if not self.is_connected or not self.repo:
            return False, "Not connected to GitHub", {}

        stats = {"uploaded": 0, "downloaded": 0, "conflicts": 0, "deleted": 0}

        try:
            from github import GithubException

            self._notify("syncing", "Syncing with GitHub...")

            # Get local notes
            local_notes = self.db.get_all_notes(include_archived=True, include_trashed=False)

            # Get remote notes
            remote_notes = {}
            try:
                contents = self.repo.get_contents(self.NOTES_DIR)
                for content in contents:
                    if content.name.endswith('.json'):
                        note_data = json.loads(content.decoded_content.decode('utf-8'))
                        remote_notes[note_data['id']] = (note_data, content.sha)
            except GithubException as e:
                if e.status != 404:  # 404 means folder doesn't exist yet
                    raise
            remote_note_data = {note_id: note_data for note_id, (note_data, _sha) in remote_notes.items()}
            base_versions = self.db.get_setting("cloud_base_github", {})
            if not isinstance(base_versions, dict):
                base_versions = {}
            plan = build_cloud_sync_plan(local_notes, remote_note_data, base_versions)
            dry_run = cloud_plan_counts(plan)
            stats["dry_run"] = dry_run
            log_diagnostic_event("info", f"GitHub sync plan: {dry_run}")
            self._notify(
                "syncing",
                f"GitHub plan c{dry_run['create']} u{dry_run['update']} d{dry_run['delete']} x{dry_run['conflict']}"
            )

            for local_note in plan["delete_local"]:
                if self.db.delete_note(local_note.id):
                    stats["deleted"] += 1

            for remote_note in plan["download_creates"] + plan["download_updates"]:
                self.db.save_note(Note.from_dict(remote_note))
                stats["downloaded"] += 1

            conflict_local_ids = set()
            conflict_copy_ids = set()
            for local_note, remote_note in plan["conflicts"]:
                conflict_copy = save_cloud_conflict_copy(self.db, remote_note, "GitHub")
                if conflict_copy:
                    stats["conflicts"] += 1
                    conflict_local_ids.add(local_note.id)
                    conflict_copy_ids.add(conflict_copy.id)

            upload_create_ids = {note.id for note in plan["upload_creates"]} | conflict_copy_ids
            upload_update_ids = {note.id for note in plan["upload_updates"]} | conflict_local_ids
            local_notes = self.db.get_all_notes(include_archived=True, include_trashed=False)

            for remote_note in plan["delete_remote"]:
                note_id = remote_note["id"]
                if note_id in remote_notes:
                    _, sha = remote_notes[note_id]
                    self.repo.delete_file(
                        f"{self.NOTES_DIR}/{note_id}.json",
                        f"Delete note: {remote_note.get('title', 'Untitled')[:50]}",
                        sha
                    )
                    stats["deleted"] += 1

            # Upload local note changes
            for note in local_notes:
                note_filename = f"{self.NOTES_DIR}/{note.id}.json"
                note_content = json.dumps(note.to_dict(), indent=2)

                try:
                    if note.id in remote_notes:
                        if note.id not in upload_update_ids:
                            continue
                        # Update existing
                        _, sha = remote_notes[note.id]
                        self.repo.update_file(
                            note_filename,
                            f"Update note: {note.title[:50]}",
                            note_content,
                            sha
                        )
                        stats["uploaded"] += 1
                    else:
                        if note.id not in upload_create_ids:
                            continue
                        # Create new
                        self.repo.create_file(
                            note_filename,
                            f"Add note: {note.title[:50]}",
                            note_content
                        )
                        stats["uploaded"] += 1
                except GithubException as e:
                    if e.status == 409:  # Conflict
                        stats["conflicts"] += 1
                    else:
                        raise

            # Upload labels
            labels = self.db.get_all_labels()
            labels_content = json.dumps([l.to_dict() for l in labels], indent=2)
            try:
                contents = self.repo.get_contents(self.LABELS_FILE)
                self.repo.update_file(
                    self.LABELS_FILE,
                    "Update labels",
                    labels_content,
                    contents.sha
                )
            except GithubException:
                self.repo.create_file(
                    self.LABELS_FILE,
                    "Add labels",
                    labels_content
                )

            # Update metadata
            metadata = {
                "last_sync": datetime.now(timezone.utc).isoformat(),
                "note_count": len(local_notes),
                "app_version": self.app_version
            }
            metadata_content = json.dumps(metadata, indent=2)
            try:
                contents = self.repo.get_contents(self.METADATA_FILE)
                self.repo.update_file(
                    self.METADATA_FILE,
                    "Update sync metadata",
                    metadata_content,
                    contents.sha
                )
            except GithubException:
                self.repo.create_file(
                    self.METADATA_FILE,
                    "Add sync metadata",
                    metadata_content
                )

            self.last_sync = datetime.now(timezone.utc)
            self.db.set_setting("github_last_sync", self.last_sync.isoformat())
            self.db.set_setting("cloud_base_github", cloud_base_versions(local_notes))

            self._notify("synced", f"GitHub sync: ↑{stats['uploaded']} ↓{stats['downloaded']}")
            return True, "Sync completed", stats

        except Exception as e:
            log_diagnostic_exception("GitHub sync", e)
            self._notify("error", f"Sync error: {str(e)}")
            return False, f"Sync error: {str(e)}", stats


class CloudSyncManager:
    """
    Manages cloud sync providers and auto-sync functionality.
    """

    def __init__(
        self,
        db: DatabaseManager,
        app_name: str = "KeepSync Notes",
        app_version: str = "0.0.0",
        db_version: int = 1,
    ):
        self.db = db
        self.app_name = app_name
        self.app_version = app_version
        self.db_version = db_version
        self.providers: Dict[str, CloudSyncProvider] = {
            "gdrive": GoogleDriveSync(db, app_name, app_version, db_version),
            "github": GitHubSync(db, app_name, app_version, db_version),
        }
        self.active_provider: Optional[CloudSyncProvider] = None
        self.auto_sync_thread: Optional[threading.Thread] = None
        self._stop_sync = threading.Event()
        self.sync_callbacks: List[Callable] = []

    def add_callback(self, callback: Callable):
        """Add callback for sync status updates"""
        self.sync_callbacks.append(callback)
        for provider in self.providers.values():
            provider.add_callback(callback)

    def get_provider(self, name: str) -> Optional[CloudSyncProvider]:
        """Get a sync provider by name"""
        return self.providers.get(name)

    def set_active_provider(self, name: str) -> bool:
        """Set the active sync provider"""
        if name in self.providers:
            self.active_provider = self.providers[name]
            return True
        return False

    def connect_gdrive(self, credentials_path: str = None) -> tuple[bool, str]:
        """Connect to Google Drive"""
        provider = self.providers["gdrive"]
        success, message = provider.connect(credentials_path=credentials_path)
        if success:
            self.active_provider = provider
        return success, message

    def connect_github(self, token: str = None, repo_name: str = "") -> tuple[bool, str]:
        """Connect to GitHub"""
        provider = self.providers["github"]
        success, message = provider.connect(token=token, repo_name=repo_name)
        if success:
            self.active_provider = provider
        return success, message

    def disconnect(self):
        """Disconnect from active provider"""
        if self.active_provider:
            self.active_provider.disconnect()
            self.active_provider = None

    def sync(self) -> tuple[bool, str, dict]:
        """Sync with active provider"""
        if not self.active_provider or not self.active_provider.is_connected:
            return False, "No cloud provider connected", {}
        try:
            LocalBackupManager(self.db, self.app_name, self.app_version).create_backup(f"before {self.active_provider.get_provider_name()} sync")
        except Exception as e:
            return False, f"Backup failed before cloud sync: {e}", {}
        return self.active_provider.sync()

    def start_auto_sync(self, interval_minutes: int = 15):
        """Start automatic background sync"""
        self._stop_sync.clear()

        def sync_loop():
            while not self._stop_sync.is_set():
                if self.active_provider and self.active_provider.is_connected:
                    try:
                        self.sync()
                    except Exception as e:
                        print(f"Auto-sync error: {e}")
                self._stop_sync.wait(interval_minutes * 60)

        self.auto_sync_thread = threading.Thread(target=sync_loop, daemon=True)
        self.auto_sync_thread.start()

    def stop_auto_sync(self):
        """Stop automatic background sync"""
        self._stop_sync.set()
        if self.auto_sync_thread:
            self.auto_sync_thread.join(timeout=1)

    def is_connected(self) -> bool:
        """Check if any provider is connected"""
        return self.active_provider is not None and self.active_provider.is_connected

    def get_status(self) -> dict:
        """Get current sync status"""
        if not self.active_provider:
            return {"connected": False, "provider": None}

        return {
            "connected": self.active_provider.is_connected,
            "provider": self.active_provider.get_provider_name(),
            "last_sync": self.active_provider.last_sync.isoformat() if self.active_provider.last_sync else None
        }
