# Google Keep sync and auth helpers.

from datetime import datetime, timezone
from typing import Callable, List, Optional
import json
import re
import threading
import uuid

import requests

from keepsync_app_info import APP_NAME, APP_VERSION
from keepsync_backups import LocalBackupManager
import keepsync_credentials as credentials_state
from keepsync_credentials import KEEP_MASTER_TOKEN_CREDENTIAL, migrate_setting_secret
from keepsync_diagnostics import log_diagnostic_exception
from keepsync_models import (
    ChecklistItem,
    Note,
    NoteType,
    SyncStatus,
    normalize_keep_color,
    normalize_people,
)
from keepsync_storage import DatabaseManager

try:
    import gkeepapi
    GKEEPAPI_AVAILABLE = True
except ImportError:
    gkeepapi = None
    GKEEPAPI_AVAILABLE = False

SECURE_CREDENTIALS = credentials_state.SECURE_CREDENTIALS


def set_secure_credential_store(store):
    """Swap the credential store for tests while preserving app-level compatibility."""
    global SECURE_CREDENTIALS
    credentials_state.set_secure_credential_store(store)
    SECURE_CREDENTIALS = credentials_state.SECURE_CREDENTIALS


class KeepSyncEngine:
    """Google Keep synchronization engine using gkeepapi"""

    def __init__(self, db: DatabaseManager):
        self.db = db
        self.keep: Optional[gkeepapi.Keep] = None if not GKEEPAPI_AVAILABLE else gkeepapi.Keep()
        self.is_authenticated = False
        self.sync_in_progress = False
        self.last_sync: Optional[datetime] = None
        self.sync_callbacks: List[Callable] = []
        self._sync_thread: Optional[threading.Thread] = None
        self._stop_sync = threading.Event()

    def add_sync_callback(self, callback: Callable):
        """Add callback for sync status updates"""
        self.sync_callbacks.append(callback)

    def _notify_callbacks(self, status: str, message: str):
        """Notify all callbacks of sync status change"""
        for callback in self.sync_callbacks:
            try:
                callback(status, message)
            except:
                pass

    def login(self, email: str, master_token: str = None, password: str = None) -> tuple[bool, str]:
        """Authenticate with Google Keep using the new API"""
        if not GKEEPAPI_AVAILABLE:
            return False, "gkeepapi is not installed. Run: python -m pip install -r requirements.txt"

        try:
            # Use the new authenticate() method
            if master_token:
                # Master token authentication (preferred)
                self.keep.authenticate(email, master_token)
            elif password:
                # Try password auth (may not work with Google's security)
                # This typically requires a master token now
                try:
                    self.keep.authenticate(email, password)
                except Exception:
                    return False, (
                        "Password authentication failed. Google requires a Master Token.\n\n"
                        "To get your master token:\n"
                        "1. Click 'Get Master Token' button below\n"
                        "2. Or run: python keep_sync_notes.py --get-token"
                    )
            else:
                return False, "Either master_token or password required"

            self.is_authenticated = True
            self.db.set_setting("keep_email", email)
            token_to_store = master_token
            try:
                token_to_store = self.keep.getMasterToken() or token_to_store
            except:
                pass  # Token retrieval may fail on some auth methods
            if token_to_store:
                if SECURE_CREDENTIALS.set_secret(KEEP_MASTER_TOKEN_CREDENTIAL, token_to_store):
                    self.db.delete_setting("keep_master_token")
                else:
                    self.db.log_sync("credentials", "google_keep", "warning", SECURE_CREDENTIALS.last_error)
                    self._notify_callbacks("connected", "Connected to Google Keep")
                    return True, "Connected to Google Keep. Token was not saved because OS keyring is unavailable."

            self._notify_callbacks("connected", "Connected to Google Keep")
            return True, "Successfully connected to Google Keep"
        except Exception as e:
            self.is_authenticated = False
            log_diagnostic_exception("Google Keep login", e)
            error_msg = str(e)
            if "BadAuthentication" in error_msg:
                return False, (
                    "Authentication failed. Google requires a Master Token.\n\n"
                    "App Passwords no longer work with gkeepapi.\n"
                    "Use the 'Get Master Token' button or run:\n"
                    "  python keep_sync_notes.py --get-token"
                )
            return False, f"Authentication failed: {error_msg}"

    def try_auto_login(self) -> bool:
        """Attempt to login using saved credentials"""
        if not GKEEPAPI_AVAILABLE:
            return False

        email = self.db.get_setting("keep_email")
        token = migrate_setting_secret(self.db, "keep_master_token", KEEP_MASTER_TOKEN_CREDENTIAL)

        if email and token:
            try:
                self.keep.authenticate(email, token)
                self.is_authenticated = True
                self._notify_callbacks("connected", "Connected to Google Keep")
                return True
            except Exception as e:
                print(f"Auto-login failed: {e}")
                log_diagnostic_exception("Google Keep auto-login", e)
                return False
        return False

    def logout(self):
        """Disconnect from Google Keep"""
        self.is_authenticated = False
        self.keep = gkeepapi.Keep() if GKEEPAPI_AVAILABLE else None
        self.db.set_setting("keep_email", None)
        self.db.delete_setting("keep_master_token")
        SECURE_CREDENTIALS.delete_secret(KEEP_MASTER_TOKEN_CREDENTIAL)
        self._notify_callbacks("disconnected", "Disconnected from Google Keep")

    def sync(self, full_sync: bool = False) -> tuple[bool, str, dict]:
        """
        Perform synchronization with Google Keep
        Returns: (success, message, stats)
        """
        if not self.is_authenticated:
            return False, "Not authenticated with Google Keep", {}

        if self.sync_in_progress:
            return False, "Sync already in progress", {}

        try:
            LocalBackupManager(self.db, APP_NAME, APP_VERSION).create_backup("before keep sync")
        except Exception as e:
            return False, f"Backup failed before Keep sync: {e}", {}

        self.sync_in_progress = True
        self._notify_callbacks("syncing", "Synchronizing...")

        stats = {"pulled": 0, "pushed": 0, "conflicts": 0, "errors": 0}

        try:
            # Sync with Google Keep servers
            self.keep.sync()

            # Pull remote notes
            pull_stats = self._pull_from_keep()
            stats["pulled"] = pull_stats.get("new", 0) + pull_stats.get("updated", 0)

            # Push local changes
            push_stats = self._push_to_keep()
            stats["pushed"] = push_stats.get("created", 0) + push_stats.get("updated", 0)

            # Final sync to commit changes
            self.keep.sync()

            self.last_sync = datetime.now(timezone.utc)
            self.db.set_setting("last_sync", self.last_sync.isoformat())

            self._notify_callbacks("synced", f"Synced: ↓{stats['pulled']} ↑{stats['pushed']}")
            return True, "Sync completed successfully", stats

        except Exception as e:
            stats["errors"] += 1
            log_diagnostic_exception("Google Keep sync", e)
            self.db.log_sync("sync", "", "error", str(e))
            self._notify_callbacks("error", f"Sync error: {str(e)}")
            return False, f"Sync error: {str(e)}", stats
        finally:
            self.sync_in_progress = False

    def _pull_from_keep(self) -> dict:
        """Pull notes from Google Keep to local database"""
        stats = {"new": 0, "updated": 0, "skipped": 0}

        for keep_note in self.keep.all():
            try:
                # Find existing local note
                cursor = self.db.conn.cursor()
                cursor.execute("SELECT * FROM notes WHERE keep_id = ?", (keep_note.id,))
                row = cursor.fetchone()

                if row:
                    local_note = self.db._row_to_note(row)

                    # Check if remote is newer
                    if keep_note.timestamps.updated > (local_note.remote_modified or datetime.min.replace(tzinfo=timezone.utc)):
                        # Update local note from remote
                        local_note = self._keep_note_to_local(keep_note, local_note)
                        local_note.sync_status = SyncStatus.SYNCED
                        self.db.save_note(local_note)
                        stats["updated"] += 1
                    else:
                        stats["skipped"] += 1
                else:
                    # Create new local note from Keep
                    local_note = self._keep_note_to_local(keep_note)
                    local_note.sync_status = SyncStatus.SYNCED
                    self.db.save_note(local_note)
                    stats["new"] += 1

            except Exception as e:
                self.db.log_sync("pull", keep_note.id, "error", str(e))

        return stats

    def _push_to_keep(self) -> dict:
        """Push local changes to Google Keep"""
        stats = {"created": 0, "updated": 0, "deleted": 0, "errors": 0}

        # Get notes that need pushing
        cursor = self.db.conn.cursor()
        cursor.execute(
            "SELECT * FROM notes WHERE sync_status IN (?, ?) AND trashed = 0",
            (SyncStatus.PENDING_PUSH.value, SyncStatus.LOCAL_ONLY.value)
        )

        for row in cursor.fetchall():
            local_note = self.db._row_to_note(row)

            try:
                if local_note.keep_id:
                    # Update existing Keep note
                    keep_note = self.keep.get(local_note.keep_id)
                    if keep_note:
                        self._update_keep_note(keep_note, local_note)
                        stats["updated"] += 1
                else:
                    # Create new Keep note
                    keep_note = self._create_keep_note(local_note)
                    local_note.keep_id = keep_note.id
                    stats["created"] += 1

                local_note.sync_status = SyncStatus.SYNCED
                local_note.remote_modified = datetime.now(timezone.utc)
                self.db.save_note(local_note)

            except Exception as e:
                stats["errors"] += 1
                self.db.log_sync("push", local_note.id, "error", str(e))

        return stats

    def _keep_note_to_local(self, keep_note, existing: Note = None) -> Note:
        """Convert gkeepapi note to local Note object"""
        note_id = existing.id if existing else str(uuid.uuid4())

        # Determine note type and content
        if hasattr(keep_note, 'items') and keep_note.items:
            note_type = NoteType.CHECKLIST
            checklist_items = [
                ChecklistItem(text=item.text, checked=item.checked)
                for item in keep_note.items
            ]
            content = ""
        else:
            note_type = NoteType.NOTE
            checklist_items = []
            content = keep_note.text or ""

        # Get labels
        labels = [label.name for label in keep_note.labels.all()]
        shared_with = self._extract_keep_shared_with(keep_note)

        return Note(
            id=note_id,
            title=keep_note.title or "",
            content=content,
            note_type=note_type,
            checklist_items=checklist_items,
            labels=labels,
            shared_with=shared_with,
            pinned=keep_note.pinned,
            archived=keep_note.archived,
            trashed=keep_note.trashed,
            color=normalize_keep_color(keep_note.color.value if keep_note.color else ""),
            keep_id=keep_note.id,
            remote_modified=keep_note.timestamps.updated,
            created_at=existing.created_at if existing else (keep_note.timestamps.created or datetime.now(timezone.utc)),
            updated_at=datetime.now(timezone.utc),
        )

    def _extract_keep_shared_with(self, keep_note) -> List[str]:
        """Best-effort collaborator metadata extraction from gkeepapi notes."""
        shared = []
        for attr in ("collaborators", "sharees", "shared_with"):
            value = getattr(keep_note, attr, None)
            if value is None:
                continue
            try:
                if hasattr(value, "all"):
                    value = value.all()
                for person in normalize_people(value):
                    if person not in shared:
                        shared.append(person)
            except Exception:
                continue
        return shared

    def _create_keep_note(self, local_note: Note):
        """Create a new note in Google Keep"""
        if local_note.note_type == NoteType.CHECKLIST:
            keep_note = self.keep.createList(
                local_note.title,
                [(item.text, item.checked) for item in local_note.checklist_items]
            )
        else:
            keep_note = self.keep.createNote(local_note.title, local_note.content)

        keep_note.pinned = local_note.pinned
        keep_note.archived = local_note.archived
        self._apply_keep_color(keep_note, local_note.color)

        # Add labels
        for label_name in local_note.labels:
            label = self.keep.findLabel(label_name)
            if not label:
                label = self.keep.createLabel(label_name)
            keep_note.labels.add(label)

        return keep_note

    def _update_keep_note(self, keep_note, local_note: Note):
        """Update an existing Google Keep note"""
        keep_note.title = local_note.title

        if local_note.note_type == NoteType.CHECKLIST:
            # Update checklist items (simplified - full implementation would be more complex)
            keep_note.text = ""
            # Note: Updating list items requires more complex handling
        else:
            keep_note.text = local_note.content

        keep_note.pinned = local_note.pinned
        keep_note.archived = local_note.archived
        self._apply_keep_color(keep_note, local_note.color)

    def _apply_keep_color(self, keep_note, color: str):
        """Apply local color to a gkeepapi note when the API supports it."""
        normalized = normalize_keep_color(color)
        if not normalized or not GKEEPAPI_AVAILABLE:
            return
        try:
            color_enum = getattr(gkeepapi.node.ColorValue, normalized.upper(), None)
            if color_enum is not None:
                keep_note.color = color_enum
        except Exception:
            pass

    def unlink_note(self, note_id: str, delete_from_keep: bool = True) -> bool:
        """
        Unlink a note from Google Keep (keep locally, optionally delete from Keep)
        """
        note = self.db.get_note(note_id)
        if not note:
            return False

        if delete_from_keep and note.keep_id and self.is_authenticated:
            try:
                keep_note = self.keep.get(note.keep_id)
                if keep_note:
                    keep_note.delete()
                    self.keep.sync()
            except Exception as e:
                self.db.log_sync("unlink", note_id, "error", str(e))

        note.keep_id = None
        note.sync_status = SyncStatus.LOCAL_ONLY
        self.db.save_note(note)
        return True

    def start_auto_sync(self, interval_minutes: int = 5):
        """Start automatic background sync"""
        self._stop_sync.clear()

        def sync_loop():
            while not self._stop_sync.is_set():
                if self.is_authenticated and not self.sync_in_progress:
                    self.sync()
                self._stop_sync.wait(interval_minutes * 60)

        self._sync_thread = threading.Thread(target=sync_loop, daemon=True)
        self._sync_thread.start()

    def stop_auto_sync(self):
        """Stop automatic background sync"""
        self._stop_sync.set()
        if self._sync_thread:
            self._sync_thread.join(timeout=1)


def get_master_token_cli():
    """
    Command-line utility to get a Google Master Token for gkeepapi.
    This is required because Google no longer allows simple password auth.
    """
    print("=" * 60)
    print("Google Keep Master Token Generator")
    print("=" * 60)
    print()
    print("This will generate a master token for Google Keep sync.")
    print("You'll need your Google email and password.")
    print()
    print("NOTE: If you have 2FA enabled, you need an App Password:")
    print("  1. Go to: https://myaccount.google.com/apppasswords")
    print("  2. Generate a new app password")
    print("  3. Use that password below (not your regular password)")
    print()

    try:
        import gpsoauth
    except ImportError:
        print("ERROR: gpsoauth is not installed.")
        print("Run: python -m pip install -r requirements.txt")
        return None

    email = input("Enter your Google email: ").strip()

    import getpass
    password = getpass.getpass("Enter your password (or App Password if 2FA enabled): ")

    # Android device ID (can be any hex string)
    android_id = "0123456789abcdef"

    print()
    print("Authenticating with Google...")

    try:
        # Perform master login
        master_response = gpsoauth.perform_master_login(email, password, android_id)

        if "Token" not in master_response:
            error = master_response.get("Error", "Unknown error")
            if "BadAuthentication" in str(error):
                print()
                print("ERROR: Authentication failed!")
                print()
                print("This usually means:")
                print("  1. Wrong password")
                print("  2. 2FA is enabled but you didn't use an App Password")
                print("  3. Google blocked the sign-in (check your email for alerts)")
                print()
                print("Solutions:")
                print("  - Create an App Password at: https://myaccount.google.com/apppasswords")
                print("  - Check your email for 'Critical security alert' and approve the sign-in")
                print("  - Try again in a few minutes")
                return None
            else:
                print(f"ERROR: {error}")
                return None

        master_token = master_response["Token"]

        print()
        print("=" * 60)
        print("SUCCESS! Here's your master token:")
        print("=" * 60)
        print()
        print(master_token)
        print()
        print("=" * 60)
        print()
        print("Copy this token and paste it in the app's Settings dialog.")
        print("The app stores saved tokens in the OS keyring.")
        print()

        # Offer to save to the OS credential store
        save = input("Save token to OS keyring for KeepSync Notes? (y/n): ").strip().lower()
        if save == 'y':
            if SECURE_CREDENTIALS.set_secret(KEEP_MASTER_TOKEN_CREDENTIAL, master_token):
                print("Token saved to OS keyring.")
            else:
                print(f"Could not save token to OS keyring: {SECURE_CREDENTIALS.last_error}")

        return master_token

    except Exception as e:
        print(f"ERROR: {e}")
        print()
        print("If you're seeing dependency errors, run:")
        print("  python -m pip install -r requirements.txt")
        return None


def extract_token_from_browser():
    """
    Extract Google authentication token from browser cookies.
    This is the most reliable method when gpsoauth fails.
    """
    print("=" * 60)
    print("Browser Token Extractor")
    print("=" * 60)
    print()
    print("This extracts your Google auth from an existing browser session.")
    print("Make sure you're logged into Google Keep in Chrome or Firefox.")
    print()

    # Import browser_cookie3 if the deterministic environment includes it.
    try:
        import browser_cookie3
    except ImportError:
        print("ERROR: browser-cookie3 is not installed.")
        print("Run: python -m pip install -r requirements.txt")
        return None

    print("Checking browsers for Google cookies...")
    print()

    cookies_found = {}

    # Try Chrome
    try:
        chrome_cookies = browser_cookie3.chrome(domain_name='.google.com')
        for cookie in chrome_cookies:
            if cookie.name in ('SID', 'HSID', 'SSID', 'APISID', 'SAPISID'):
                cookies_found[cookie.name] = cookie.value
        if cookies_found:
            print(f"✓ Found {len(cookies_found)} Google cookies in Chrome")
    except Exception as e:
        print(f"✗ Chrome: {e}")

    # Try Firefox
    if len(cookies_found) < 3:
        try:
            ff_cookies = browser_cookie3.firefox(domain_name='.google.com')
            for cookie in ff_cookies:
                if cookie.name in ('SID', 'HSID', 'SSID', 'APISID', 'SAPISID'):
                    cookies_found[cookie.name] = cookie.value
            if cookies_found:
                print(f"✓ Found {len(cookies_found)} Google cookies in Firefox")
        except Exception as e:
            print(f"✗ Firefox: {e}")

    # Try Edge
    if len(cookies_found) < 3:
        try:
            edge_cookies = browser_cookie3.edge(domain_name='.google.com')
            for cookie in edge_cookies:
                if cookie.name in ('SID', 'HSID', 'SSID', 'APISID', 'SAPISID'):
                    cookies_found[cookie.name] = cookie.value
            if cookies_found:
                print(f"✓ Found {len(cookies_found)} Google cookies in Edge")
        except Exception as e:
            print(f"✗ Edge: {e}")

    if len(cookies_found) >= 3:
        print()
        print("=" * 60)
        print("SUCCESS! Found Google authentication cookies.")
        print("=" * 60)
        return cookies_found
    else:
        print()
        print("ERROR: Could not find enough Google cookies.")
        print("Make sure you're logged into Google in your browser.")
        return None


class KeepWebScraper:
    """
    Scrapes Google Keep using browser cookies.
    This is a fallback when gkeepapi authentication fails.
    """

    KEEP_URL = "https://keep.google.com"
    API_URL = "https://keep.google.com/u/0/api"

    def __init__(self):
        self.session = None
        self.cookies = None
        self.is_authenticated = False

    def authenticate_from_browser(self, browser: str = "auto") -> tuple[bool, str]:
        """
        Authenticate using cookies from the user's browser.

        Args:
            browser: "chrome", "firefox", "edge", or "auto" to try all

        Returns:
            (success, message)
        """
        try:
            import browser_cookie3
        except ImportError:
            return False, "browser-cookie3 is not installed. Run: python -m pip install -r requirements.txt"

        import requests

        # Try to get cookies from browser
        cj = None
        browser_used = None

        browsers_to_try = []
        if browser == "auto":
            browsers_to_try = [
                ("chrome", browser_cookie3.chrome),
                ("firefox", browser_cookie3.firefox),
                ("edge", browser_cookie3.edge),
                ("chromium", browser_cookie3.chromium),
            ]
        else:
            browser_funcs = {
                "chrome": browser_cookie3.chrome,
                "firefox": browser_cookie3.firefox,
                "edge": browser_cookie3.edge,
                "chromium": browser_cookie3.chromium,
            }
            if browser in browser_funcs:
                browsers_to_try = [(browser, browser_funcs[browser])]

        for name, func in browsers_to_try:
            try:
                cj = func(domain_name='.google.com')
                # Verify we have the essential cookies
                cookie_names = [c.name for c in cj]
                if 'SID' in cookie_names or 'HSID' in cookie_names:
                    browser_used = name
                    break
            except Exception:
                continue

        if not cj or not browser_used:
            return False, (
                "Could not find Google cookies in any browser.\n\n"
                "Make sure you:\n"
                "1. Are logged into Google Keep in your browser\n"
                "2. Have visited keep.google.com recently\n"
                "3. Close the browser before trying (cookies may be locked)"
            )

        # Create session with cookies
        self.session = requests.Session()
        self.session.cookies = cj
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Origin': 'https://keep.google.com',
            'Referer': 'https://keep.google.com/',
        })

        # Verify authentication by trying to access Keep
        try:
            response = self.session.get(self.KEEP_URL, timeout=10)
            if response.status_code == 200 and 'keep' in response.url.lower():
                self.is_authenticated = True
                self.cookies = cj
                return True, f"Authenticated via {browser_used.title()} browser cookies"
            else:
                return False, "Could not verify Google Keep access"
        except Exception as e:
            return False, f"Connection error: {str(e)}"

    def fetch_notes(self) -> tuple[bool, str, List[dict]]:
        """
        Fetch notes from Google Keep.

        Returns:
            (success, message, list of note dicts)
        """
        if not self.is_authenticated or not self.session:
            return False, "Not authenticated", []

        try:
            # Google Keep uses a complex internal API, so we'll scrape the HTML
            # and extract embedded JSON data
            response = self.session.get(self.KEEP_URL, timeout=15)

            if response.status_code != 200:
                return False, f"Failed to fetch Keep: HTTP {response.status_code}", []

            html = response.text
            notes = []

            # Try to find embedded note data in the page
            # Google Keep embeds initial data in a script tag
            import re

            # Look for the data payload
            patterns = [
                r'data:(\[.*?\])\s*,\s*sideChannel',
                r"AF_initDataCallback\(\{key:\s*'[^']*',\s*data:(\[.*?\])\}\);",
                r'key:\s*[\'"]ds:1[\'"]\s*,\s*data:\s*(\[.*?\])',
            ]

            data_found = None
            for pattern in patterns:
                matches = re.findall(pattern, html, re.DOTALL)
                if matches:
                    for match in matches:
                        try:
                            data_found = json.loads(match)
                            if isinstance(data_found, list) and len(data_found) > 0:
                                break
                        except json.JSONDecodeError:
                            continue
                    if data_found:
                        break

            if not data_found:
                # Fallback: Try to extract notes from the HTML structure
                # This is a simplified extraction
                note_pattern = r'data-id="([^"]+)"[^>]*>.*?<div[^>]*class="[^"]*title[^"]*"[^>]*>([^<]*)</div>.*?<div[^>]*class="[^"]*content[^"]*"[^>]*>([^<]*)</div>'
                note_matches = re.findall(note_pattern, html, re.DOTALL | re.IGNORECASE)

                for note_id, title, content in note_matches:
                    notes.append({
                        'id': note_id,
                        'title': title.strip(),
                        'content': content.strip(),
                        'type': 'note',
                    })

            if notes:
                return True, f"Found {len(notes)} notes", notes
            else:
                # If we couldn't parse notes but the page loaded, provide instructions
                return False, (
                    "Connected to Google Keep but couldn't parse notes.\n\n"
                    "Alternative: Export your notes manually:\n"
                    "1. Go to takeout.google.com\n"
                    "2. Select only 'Keep' and export\n"
                    "3. Use 'Import Notes' in Settings to import the JSON files"
                ), []

        except Exception as e:
            return False, f"Error fetching notes: {str(e)}", []

    def import_notes_to_db(self, db: DatabaseManager) -> tuple[int, int]:
        """
        Fetch and import notes to the local database.

        Returns:
            (imported_count, error_count)
        """
        success, message, notes = self.fetch_notes()

        if not success:
            return 0, 0

        imported = 0
        errors = 0

        for note_data in notes:
            try:
                note = Note(
                    id=str(uuid.uuid4()),
                    title=note_data.get('title', ''),
                    content=note_data.get('content', ''),
                    note_type=NoteType.CHECKLIST if note_data.get('type') == 'list' else NoteType.NOTE,
                    labels=note_data.get('labels', []),
                    pinned=note_data.get('pinned', False),
                    archived=note_data.get('archived', False),
                    keep_id=note_data.get('id'),
                    sync_status=SyncStatus.SYNCED,
                    remote_modified=datetime.now(timezone.utc),
                )

                if db.save_note(note):
                    imported += 1
                else:
                    errors += 1
            except Exception:
                errors += 1

        return imported, errors
