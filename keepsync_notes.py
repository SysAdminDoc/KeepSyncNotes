#!/usr/bin/env python3
"""
KeepSync Notes - Professional Note Application with Google Keep Integration
A premium offline-first note manager with Google Keep synchronization.

Features:
- Full offline functionality with local SQLite database
- Google Keep sync via gkeepapi (unofficial API)
- Conflict resolution and sync status tracking
- Rich text editing with markdown support
- Labels/tags organization
- Search and filtering
- Import/Export capabilities
- Professional dark theme UI
"""

# ═══════════════════════════════════════════════════════════════════════════════
# Dependencies are managed by requirements.txt; the app never installs packages at runtime.
# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════════
# IMPORTS
# ═══════════════════════════════════════════════════════════════════════════════

import customtkinter as ctk
from tkinter import messagebox, filedialog
import tkinter as tk
from PIL import Image
import json
import hashlib
import threading
import queue
import time
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
import webbrowser
import uuid

from keepsync_models import (
    Attachment,
    ChecklistItem,
    KEEP_COLOR_ALIASES,
    KEEP_COLOR_PALETTE,
    Label,
    Note,
    NoteType,
    SyncStatus,
    clamp_checklist_indent,
    guess_attachment_mime,
    keep_color_hex,
    keep_color_name,
    normalize_keep_color,
    normalize_people,
    sanitize_filename,
)
from keepsync_bootstrap import run_bootstrap
from keepsync_cloud_plan import (
    build_cloud_sync_plan,
    cloud_base_versions,
    cloud_plan_counts,
    note_data_hash,
    save_cloud_conflict_copy,
)
from keepsync_cloud_sync import (
    CloudSyncManager,
    CloudSyncProvider,
    GitHubSync,
    GoogleDriveSync,
)
from keepsync_import_safety import (
    MAX_IMPORT_FOLDER_BYTES,
    MAX_IMPORT_FOLDER_FILES,
    MAX_IMPORT_TEXT_MEMBER_BYTES,
    MAX_IMPORT_ZIP_MEMBERS,
    MAX_IMPORT_ZIP_UNCOMPRESSED_BYTES,
    ImportCancelled,
    ImportSafetyError,
    decode_zip_member,
    extract_zip_member_safely,
    guarded_import_files,
    is_hidden_or_system_path,
    safe_zip_member_parts,
    validate_zip_members,
)
from keepsync_importers import (
    HTMLTextExtractor,
    MultiSourceImporter,
    copy_attachment_to_store,
    extract_shared_with,
    first_present,
    html_to_text,
    import_takeout_attachments,
    labels_from_hashtags,
    parse_external_datetime,
    resolve_takeout_attachment_path,
    strip_enex_content,
    takeout_attachment_specs,
    title_from_content,
)
from keepsync_import_reports import IMPORT_SUCCESS_STATUSES, import_summary_lines
from keepsync_storage import DatabaseManager
from keepsync_backups import LocalBackupManager
import keepsync_diagnostics as diagnostics_state
from keepsync_diagnostics import (
    DiagnosticsManager,
    log_diagnostic_event,
    log_diagnostic_exception,
    set_diagnostics_manager,
)
from keepsync_note_ops import (
    advanced_filters_active,
    default_advanced_filters,
    merge_note_conflict,
    normalize_import_labels,
    note_conflict_diff,
    note_diff_body,
    note_matches_advanced_filters,
    notes_equivalent,
    parse_filter_date,
)
import keepsync_credentials as credentials_state
from keepsync_credentials import (
    GDRIVE_OAUTH_TOKEN_CREDENTIAL,
    GITHUB_PAT_CREDENTIAL,
    KEEP_MASTER_TOKEN_CREDENTIAL,
    KEYRING_AVAILABLE,
    KEYRING_SERVICE,
    KeyringCredentialStore,
    migrate_file_secret,
    migrate_setting_secret,
    store_file_secret,
)
from keepsync_paths import (
    get_app_data_dir,
    get_google_drive_credentials_path,
    get_google_drive_token_path,
)
from keepsync_settings_dialog import SettingsDialog
from keepsync_theme import COLORS
from keepsync_ui_components import (
    IconManager,
    NoteCard,
    SyncStatusBadge,
    configure_note_card_helpers,
)
from keepsync_ui_dialogs import (
    AdvancedFilterDialog,
    DiagnosticsDialog,
    ImportConflictDialog,
    ImportProgressDialog,
    TakeoutInstructionsDialog,
    TokenGeneratorDialog,
)
from keepsync_ui_modal import configure_modal_dialog

# Optional: gkeepapi for Google Keep sync
try:
    import gkeepapi
    GKEEPAPI_AVAILABLE = True
except ImportError:
    GKEEPAPI_AVAILABLE = False

try:
    from plyer import notification as desktop_notification
    DESKTOP_NOTIFICATIONS_AVAILABLE = True
except ImportError:
    desktop_notification = None
    DESKTOP_NOTIFICATIONS_AVAILABLE = False

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION & CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

APP_NAME = "KeepSync Notes"
APP_VERSION = "1.38.0"
DB_VERSION = 1

def parse_reminder_datetime(value: str) -> Optional[datetime]:
    text = (value or "").strip()
    if not text:
        return None

    candidates = [text, text.replace("T", " ")]
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            break
        except ValueError:
            parsed = None
    else:
        parsed = None

    if parsed is None:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue

    if parsed is None:
        raise ValueError("Use YYYY-MM-DD HH:MM for reminders.")

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return parsed.astimezone(timezone.utc)

def format_reminder_datetime(value: Optional[datetime]) -> str:
    if not value:
        return ""
    return value.astimezone().strftime("%Y-%m-%d %H:%M")

def is_markdown_label(value: Any) -> bool:
    """Return True when a note label enables markdown preview mode."""
    return str(value or "").strip().lower() == ".md"

def note_uses_markdown(labels: List[str]) -> bool:
    return any(is_markdown_label(label) for label in labels)

def split_inline_markdown(text: str) -> List[Dict[str, str]]:
    """Split a markdown line into display segments with lightweight styles."""
    pattern = re.compile(r"(`([^`]+)`|\*\*([^*]+)\*\*|__([^_]+)__|\*([^*]+)\*|_([^_]+)_)")
    segments = []
    cursor = 0

    for match in pattern.finditer(text or ""):
        if match.start() > cursor:
            segments.append({"text": text[cursor:match.start()], "style": "plain"})

        if match.group(2) is not None:
            segments.append({"text": match.group(2), "style": "inline_code"})
        elif match.group(3) is not None or match.group(4) is not None:
            segments.append({"text": match.group(3) or match.group(4), "style": "bold"})
        else:
            segments.append({"text": match.group(5) or match.group(6), "style": "italic"})
        cursor = match.end()

    if cursor < len(text or ""):
        segments.append({"text": text[cursor:], "style": "plain"})
    return segments

def markdown_preview_blocks(markdown_text: str) -> List[Dict[str, Any]]:
    """Convert a conservative markdown subset into styled preview blocks."""
    blocks = []
    in_code_block = False

    for raw_line in (markdown_text or "").splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue

        if in_code_block:
            blocks.append({
                "style": "code_block",
                "segments": [{"text": raw_line, "style": "plain"}],
            })
            continue

        if not stripped:
            blocks.append({"style": "blank", "segments": []})
            continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            level = min(len(heading.group(1)), 3)
            blocks.append({
                "style": f"heading_{level}",
                "segments": split_inline_markdown(heading.group(2).strip()),
            })
            continue

        task = re.match(r"^\s*[-*+]\s+\[([ xX])\]\s+(.+)$", raw_line)
        if task:
            mark = "[x]" if task.group(1).lower() == "x" else "[ ]"
            blocks.append({
                "style": "task",
                "segments": split_inline_markdown(f"{mark} {task.group(2).strip()}"),
            })
            continue

        bullet = re.match(r"^\s*[-*+]\s+(.+)$", raw_line)
        if bullet:
            blocks.append({
                "style": "list_item",
                "segments": split_inline_markdown(f"- {bullet.group(1).strip()}"),
            })
            continue

        numbered = re.match(r"^\s*(\d+)[.)]\s+(.+)$", raw_line)
        if numbered:
            blocks.append({
                "style": "list_item",
                "segments": split_inline_markdown(f"{numbered.group(1)}. {numbered.group(2).strip()}"),
            })
            continue

        if stripped.startswith(">"):
            blocks.append({
                "style": "quote",
                "segments": split_inline_markdown(stripped.lstrip("> ").strip()),
            })
            continue

        blocks.append({
            "style": "paragraph",
            "segments": split_inline_markdown(raw_line.strip()),
        })

    return blocks

def markdown_preview_text(markdown_text: str, limit: int = 150) -> str:
    preview_parts = []
    for block in markdown_preview_blocks(markdown_text):
        text = "".join(segment["text"] for segment in block["segments"]).strip()
        if text:
            preview_parts.append(text)
    preview = " ".join(preview_parts)
    return preview[:limit] + ("..." if len(preview) > limit else "")


configure_note_card_helpers(
    note_uses_markdown_func=note_uses_markdown,
    markdown_preview_text_func=markdown_preview_text,
    format_reminder_datetime_func=format_reminder_datetime,
)

SECURE_CREDENTIALS = credentials_state.SECURE_CREDENTIALS


def set_secure_credential_store(store: Any):
    """Swap the credential store for tests while preserving app-level compatibility."""
    global SECURE_CREDENTIALS
    credentials_state.set_secure_credential_store(store)
    SECURE_CREDENTIALS = credentials_state.SECURE_CREDENTIALS


# ═══════════════════════════════════════════════════════════════════════════════

# GOOGLE KEEP SYNC ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════════
# MASTER TOKEN GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════════
# GOOGLE KEEP WEB SCRAPER (Alternative to gkeepapi)
# ═══════════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════════
# CLOUD SYNC PROVIDERS (Google Drive & GitHub)
# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════════
# UI COMPONENTS
# ═══════════════════════════════════════════════════════════════════════════════

class NoteEditor(ctk.CTkFrame):
    """Full note editor panel"""
    
    def __init__(self, parent, db: DatabaseManager, sync_engine: KeepSyncEngine,
                 on_save: Callable, on_close: Callable, **kwargs):
        super().__init__(parent, fg_color=COLORS["bg_dark"], **kwargs)
        
        self.db = db
        self.sync_engine = sync_engine
        self.on_save_callback = on_save
        self.on_close_callback = on_close
        self.current_note: Optional[Note] = None
        self.is_modified = False
        self.selected_color = ""
        
        self._build_ui()
    
    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent", height=50)
        header.pack(fill="x", padx=16, pady=(12, 0))
        header.pack_propagate(False)
        
        # Close button
        self.close_btn = ctk.CTkButton(
            header,
            text="",
            image=IconManager.get_icon("close", 20, COLORS["text_secondary"]),
            width=36,
            height=36,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            command=self._handle_close
        )
        self.close_btn.pack(side="left")
        
        # Title
        self.header_title = ctk.CTkLabel(
            header,
            text="New Note",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text_primary"]
        )
        self.header_title.pack(side="left", padx=12)
        
        # Sync status
        self.sync_badge = SyncStatusBadge(header, SyncStatus.LOCAL_ONLY)
        self.sync_badge.pack(side="left", padx=8)
        
        # Actions
        actions_frame = ctk.CTkFrame(header, fg_color="transparent")
        actions_frame.pack(side="right")
        
        self.pin_btn = ctk.CTkButton(
            actions_frame,
            text="",
            image=IconManager.get_icon("pin", 18, COLORS["text_secondary"]),
            width=36,
            height=36,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            command=self._toggle_pin
        )
        self.pin_btn.pack(side="left", padx=2)
        
        self.save_btn = ctk.CTkButton(
            actions_frame,
            text="Save",
            font=ctk.CTkFont(size=13, weight="bold"),
            width=80,
            height=36,
            fg_color=COLORS["accent_green"],
            hover_color=COLORS["accent_green_hover"],
            text_color=COLORS["bg_darkest"],
            command=self._save_note
        )
        self.save_btn.pack(side="left", padx=(8, 0))
        
        # Divider
        divider = ctk.CTkFrame(self, fg_color=COLORS["divider"], height=1)
        divider.pack(fill="x", pady=12)
        
        # Editor content
        editor_frame = ctk.CTkFrame(self, fg_color="transparent")
        editor_frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        
        # Title input
        self.title_entry = ctk.CTkEntry(
            editor_frame,
            placeholder_text="Title",
            font=ctk.CTkFont(size=20, weight="bold"),
            height=45,
            fg_color="transparent",
            border_width=0,
            text_color=COLORS["text_primary"],
            placeholder_text_color=COLORS["text_muted"]
        )
        self.title_entry.pack(fill="x", pady=(0, 8))
        self.title_entry.bind("<KeyRelease>", self._on_modify)
        
        # Note type selector
        type_frame = ctk.CTkFrame(editor_frame, fg_color="transparent")
        type_frame.pack(fill="x", pady=(0, 12))
        
        self.note_type_var = ctk.StringVar(value="note")
        
        self.note_radio = ctk.CTkRadioButton(
            type_frame,
            text="Text Note",
            variable=self.note_type_var,
            value="note",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"],
            fg_color=COLORS["accent_blue"],
            hover_color=COLORS["accent_blue_hover"],
            command=self._on_type_change
        )
        self.note_radio.pack(side="left", padx=(0, 16))
        
        self.checklist_radio = ctk.CTkRadioButton(
            type_frame,
            text="Checklist",
            variable=self.note_type_var,
            value="checklist",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"],
            fg_color=COLORS["accent_blue"],
            hover_color=COLORS["accent_blue_hover"],
            command=self._on_type_change
        )
        self.checklist_radio.pack(side="left")

        # Color selector
        color_section = ctk.CTkFrame(editor_frame, fg_color="transparent")
        color_section.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            color_section,
            text="Color",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["text_secondary"]
        ).pack(side="left", padx=(0, 10))

        self.color_buttons = {}
        for color_key, (color_name, color_hex) in KEEP_COLOR_PALETTE.items():
            button = ctk.CTkButton(
                color_section,
                text="",
                width=24,
                height=24,
                fg_color=color_hex,
                hover_color=color_hex,
                border_width=2,
                border_color=COLORS["border"],
                corner_radius=12,
                command=lambda c=color_key: self._select_color(c)
            )
            button.pack(side="left", padx=(0, 5))
            self.color_buttons[color_key] = button
        
        # Content area (switchable between text and checklist)
        self.content_container = ctk.CTkFrame(editor_frame, fg_color="transparent")
        self.content_container.pack(fill="both", expand=True)
        
        # Text editor
        self.text_frame = ctk.CTkFrame(self.content_container, fg_color="transparent")

        self.markdown_mode_var = ctk.StringVar(value="Edit")
        self.markdown_controls = ctk.CTkFrame(self.text_frame, fg_color="transparent")
        ctk.CTkLabel(
            self.markdown_controls,
            text="Markdown",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["accent_cyan"]
        ).pack(side="left", padx=(0, 10))

        self.markdown_toggle = ctk.CTkSegmentedButton(
            self.markdown_controls,
            values=["Edit", "Preview"],
            variable=self.markdown_mode_var,
            command=self._set_markdown_mode,
            selected_color=COLORS["accent_blue"],
            selected_hover_color=COLORS["accent_blue_hover"],
            unselected_color=COLORS["bg_medium"],
            unselected_hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_primary"],
            height=30
        )
        self.markdown_toggle.pack(side="right")
        
        self.content_text = ctk.CTkTextbox(
            self.text_frame,
            font=ctk.CTkFont(size=14),
            fg_color=COLORS["bg_medium"],
            border_width=1,
            border_color=COLORS["border"],
            text_color=COLORS["text_primary"],
            corner_radius=8
        )
        self.content_text.pack(fill="both", expand=True)
        self.content_text.bind("<KeyRelease>", self._on_modify)

        self.markdown_preview = ctk.CTkTextbox(
            self.text_frame,
            font=ctk.CTkFont(size=14),
            fg_color=COLORS["bg_medium"],
            border_width=1,
            border_color=COLORS["border"],
            text_color=COLORS["text_primary"],
            corner_radius=8,
            wrap="word"
        )
        self._configure_markdown_preview_tags()
        
        # Checklist editor
        self.checklist_frame = ctk.CTkFrame(self.content_container, fg_color="transparent")
        
        self.checklist_scroll = ctk.CTkScrollableFrame(
            self.checklist_frame,
            fg_color=COLORS["bg_medium"],
            corner_radius=8
        )
        self.checklist_scroll.pack(fill="both", expand=True)
        
        self.add_item_btn = ctk.CTkButton(
            self.checklist_frame,
            text="+ Add Item",
            font=ctk.CTkFont(size=13),
            height=36,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["accent_blue"],
            anchor="w",
            command=self._add_checklist_item
        )
        self.add_item_btn.pack(fill="x", pady=(8, 0))
        
        # Labels section
        labels_section = ctk.CTkFrame(editor_frame, fg_color="transparent")
        labels_section.pack(fill="x", pady=(12, 0))
        
        labels_header = ctk.CTkLabel(
            labels_section,
            text="Labels",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["text_secondary"]
        )
        labels_header.pack(anchor="w")
        
        self.labels_frame = ctk.CTkFrame(labels_section, fg_color="transparent")
        self.labels_frame.pack(fill="x", pady=(4, 0))
        
        self.label_entry = ctk.CTkEntry(
            self.labels_frame,
            placeholder_text="Add label...",
            font=ctk.CTkFont(size=12),
            width=150,
            height=30,
            fg_color=COLORS["bg_medium"],
            border_width=1,
            border_color=COLORS["border"]
        )
        self.label_entry.pack(side="left")
        self.label_entry.bind("<Return>", self._add_label)
        
        self.labels_display = ctk.CTkFrame(self.labels_frame, fg_color="transparent")
        self.labels_display.pack(side="left", fill="x", expand=True, padx=(8, 0))

        # Reminder section
        reminder_section = ctk.CTkFrame(editor_frame, fg_color="transparent")
        reminder_section.pack(fill="x", pady=(12, 0))

        ctk.CTkLabel(
            reminder_section,
            text="Reminder",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w")

        reminder_inputs = ctk.CTkFrame(reminder_section, fg_color="transparent")
        reminder_inputs.pack(fill="x", pady=(4, 0))

        self.reminder_entry = ctk.CTkEntry(
            reminder_inputs,
            placeholder_text="YYYY-MM-DD HH:MM",
            font=ctk.CTkFont(size=12),
            width=150,
            height=30,
            fg_color=COLORS["bg_medium"],
            border_width=1,
            border_color=COLORS["border"]
        )
        self.reminder_entry.pack(side="left")
        self.reminder_entry.bind("<KeyRelease>", self._on_modify)

        self.reminder_location_entry = ctk.CTkEntry(
            reminder_inputs,
            placeholder_text="Optional location",
            font=ctk.CTkFont(size=12),
            height=30,
            fg_color=COLORS["bg_medium"],
            border_width=1,
            border_color=COLORS["border"]
        )
        self.reminder_location_entry.pack(side="left", fill="x", expand=True, padx=(8, 0))
        self.reminder_location_entry.bind("<KeyRelease>", self._on_modify)

        self.clear_reminder_btn = ctk.CTkButton(
            reminder_inputs,
            text="Clear",
            font=ctk.CTkFont(size=12),
            width=58,
            height=30,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_secondary"],
            command=self._clear_reminder
        )
        self.clear_reminder_btn.pack(side="left", padx=(8, 0))

        shared_section = ctk.CTkFrame(editor_frame, fg_color="transparent")
        shared_section.pack(fill="x", pady=(12, 0))

        ctk.CTkLabel(
            shared_section,
            text="Shared With",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w")

        self.shared_display = ctk.CTkLabel(
            shared_section,
            text="Not shared",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_muted"],
            anchor="w",
            justify="left",
            wraplength=520
        )
        self.shared_display.pack(fill="x", pady=(4, 0))

        attachments_section = ctk.CTkFrame(editor_frame, fg_color="transparent")
        attachments_section.pack(fill="x", pady=(12, 0))

        ctk.CTkLabel(
            attachments_section,
            text="Attachments",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w")

        self.attachments_frame = ctk.CTkFrame(attachments_section, fg_color="transparent")
        self.attachments_frame.pack(fill="x", pady=(4, 0))
        self.attachment_images = []
        
        # Advanced options (collapsible)
        self.advanced_frame = ctk.CTkFrame(editor_frame, fg_color="transparent")
        self.advanced_frame.pack(fill="x", pady=(12, 0))
        
        # Unlink from Keep button (only shown for synced notes)
        self.unlink_btn = ctk.CTkButton(
            self.advanced_frame,
            text="Unlink from Google Keep",
            font=ctk.CTkFont(size=12),
            height=32,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["accent_red"],
            border_width=1,
            border_color=COLORS["accent_red"],
            command=self._unlink_from_keep
        )
        
        # Initialize with text editor
        self.text_frame.pack(fill="both", expand=True)
        self.checklist_items_widgets: List[ctk.CTkFrame] = []
    
    def load_note(self, note: Optional[Note] = None):
        """Load a note into the editor"""
        if note:
            self.current_note = note
            self.header_title.configure(text="Edit Note")
            
            self.title_entry.delete(0, "end")
            self.title_entry.insert(0, note.title)
            
            self.note_type_var.set(note.note_type.value)
            self._on_type_change()
            
            if note.note_type == NoteType.CHECKLIST:
                self._load_checklist_items(note.checklist_items)
            else:
                self.content_text.delete("1.0", "end")
                self.content_text.insert("1.0", note.content)

            self.selected_color = normalize_keep_color(note.color)
            self._refresh_color_buttons()

            self.reminder_entry.delete(0, "end")
            self.reminder_entry.insert(0, format_reminder_datetime(note.reminder_at))
            self.reminder_location_entry.delete(0, "end")
            self.reminder_location_entry.insert(0, note.reminder_location)
            self._load_shared_with(note.shared_with)
            self._load_attachments(note.attachments)
            
            self._load_labels(note.labels)
            self.sync_badge.update_status(note.sync_status)
            
            # Show/hide unlink button
            if note.keep_id:
                self.unlink_btn.pack(side="left")
            else:
                self.unlink_btn.pack_forget()
            
            # Update pin button
            pin_color = COLORS["accent_yellow"] if note.pinned else COLORS["text_secondary"]
            self.pin_btn.configure(image=IconManager.get_icon("pin", 18, pin_color))
        else:
            self.current_note = Note(
                id=str(uuid.uuid4()),
                title="",
                content="",
                sync_status=SyncStatus.LOCAL_ONLY
            )
            self.header_title.configure(text="New Note")
            
            self.title_entry.delete(0, "end")
            self.content_text.delete("1.0", "end")
            self.note_type_var.set("note")
            self._on_type_change()
            self.selected_color = ""
            self._refresh_color_buttons()
            self._clear_checklist_items()
            self._load_labels([])
            self._clear_reminder(mark_modified=False)
            self._load_shared_with([])
            self._load_attachments([])
            self.sync_badge.update_status(SyncStatus.LOCAL_ONLY)
            self.unlink_btn.pack_forget()
            self.pin_btn.configure(image=IconManager.get_icon("pin", 18, COLORS["text_secondary"]))
        
        self.is_modified = False
    
    def _on_modify(self, event=None):
        """Mark note as modified"""
        self.is_modified = True

    def _markdown_preview_widget(self):
        return getattr(self.markdown_preview, "_textbox", self.markdown_preview)

    def _configure_markdown_preview_tags(self):
        widget = self._markdown_preview_widget()
        widget.tag_configure("paragraph", foreground=COLORS["text_primary"], font=("Segoe UI", 13), spacing3=4)
        widget.tag_configure("heading_1", foreground=COLORS["text_primary"], font=("Segoe UI", 22, "bold"), spacing1=8, spacing3=6)
        widget.tag_configure("heading_2", foreground=COLORS["text_primary"], font=("Segoe UI", 18, "bold"), spacing1=8, spacing3=5)
        widget.tag_configure("heading_3", foreground=COLORS["text_primary"], font=("Segoe UI", 15, "bold"), spacing1=6, spacing3=4)
        widget.tag_configure("list_item", foreground=COLORS["text_primary"], lmargin1=18, lmargin2=30, spacing3=3)
        widget.tag_configure("task", foreground=COLORS["text_primary"], lmargin1=18, lmargin2=30, spacing3=3)
        widget.tag_configure("quote", foreground=COLORS["text_secondary"], lmargin1=18, lmargin2=18, spacing1=4, spacing3=4)
        widget.tag_configure("code_block", foreground=COLORS["accent_cyan"], background=COLORS["bg_darkest"], font=("Consolas", 12), lmargin1=12, lmargin2=12, spacing1=3, spacing3=3)
        widget.tag_configure("bold", font=("Segoe UI", 13, "bold"))
        widget.tag_configure("italic", font=("Segoe UI", 13, "italic"))
        widget.tag_configure("inline_code", foreground=COLORS["accent_cyan"], background=COLORS["bg_darkest"], font=("Consolas", 12))

    def _markdown_enabled(self) -> bool:
        return (
            self.current_note is not None
            and self.note_type_var.get() == NoteType.NOTE.value
            and note_uses_markdown(self.current_note.labels)
        )

    def _set_markdown_mode(self, value: str):
        self.markdown_mode_var.set(value)
        self._refresh_markdown_controls()

    def _refresh_markdown_controls(self):
        if not hasattr(self, "markdown_controls"):
            return

        self.markdown_controls.pack_forget()
        self.content_text.pack_forget()
        self.markdown_preview.pack_forget()

        if not self._markdown_enabled():
            self.markdown_mode_var.set("Edit")
            self.content_text.pack(fill="both", expand=True)
            return

        self.markdown_controls.pack(fill="x", pady=(0, 8))
        if self.markdown_mode_var.get() == "Preview":
            self._render_markdown_preview()
            self.markdown_preview.pack(fill="both", expand=True)
        else:
            self.content_text.pack(fill="both", expand=True)

    def _render_markdown_preview(self):
        widget = self._markdown_preview_widget()
        widget.configure(state="normal")
        widget.delete("1.0", "end")

        for block in markdown_preview_blocks(self.content_text.get("1.0", "end-1c")):
            segments = block["segments"]
            if not segments:
                widget.insert("end", "\n")
                continue

            line_style = block["style"]
            for segment in segments:
                text = segment["text"]
                if not text:
                    continue
                start = widget.index("end-1c")
                widget.insert("end", text)
                end = widget.index("end-1c")
                widget.tag_add(line_style, start, end)
                if segment["style"] != "plain":
                    widget.tag_add(segment["style"], start, end)
            widget.insert("end", "\n")

        widget.configure(state="disabled")

    def _select_color(self, color: str):
        """Select a Keep color for the note."""
        self.selected_color = normalize_keep_color(color)
        self._refresh_color_buttons()
        self._on_modify()

    def _refresh_color_buttons(self):
        """Update color selector button borders."""
        if not hasattr(self, "color_buttons"):
            return
        for color_key, button in self.color_buttons.items():
            is_selected = color_key == self.selected_color
            button.configure(
                border_color=COLORS["text_primary"] if is_selected else COLORS["border"],
                border_width=3 if is_selected else 2
            )

    def _clear_reminder(self, mark_modified: bool = True):
        """Clear reminder inputs."""
        self.reminder_entry.delete(0, "end")
        self.reminder_location_entry.delete(0, "end")
        if mark_modified:
            self._on_modify()

    def _load_shared_with(self, shared_with: List[str]):
        """Display imported sharing metadata."""
        if shared_with:
            self.shared_display.configure(
                text=", ".join(shared_with),
                text_color=COLORS["accent_cyan"]
            )
        else:
            self.shared_display.configure(
                text="Not shared",
                text_color=COLORS["text_muted"]
            )

    def _load_attachments(self, attachments: List[Attachment]):
        """Render imported attachments in the editor."""
        for widget in self.attachments_frame.winfo_children():
            widget.destroy()
        self.attachment_images.clear()

        if not attachments:
            ctk.CTkLabel(
                self.attachments_frame,
                text="No attachments",
                font=ctk.CTkFont(size=12),
                text_color=COLORS["text_muted"],
                anchor="w"
            ).pack(anchor="w")
            return

        for attachment in attachments:
            row = ctk.CTkFrame(self.attachments_frame, fg_color=COLORS["bg_medium"], corner_radius=8)
            row.pack(fill="x", pady=(0, 6))

            if attachment.is_image and attachment.exists:
                try:
                    image = Image.open(attachment.stored_path)
                    image.thumbnail((180, 120))
                    ctk_image = ctk.CTkImage(light_image=image.copy(), dark_image=image.copy(), size=image.size)
                    self.attachment_images.append(ctk_image)
                    preview = ctk.CTkLabel(row, text="", image=ctk_image)
                    preview.pack(side="left", padx=8, pady=8)
                except Exception:
                    pass

            details = ctk.CTkFrame(row, fg_color="transparent")
            details.pack(side="left", fill="x", expand=True, padx=8, pady=8)

            ctk.CTkLabel(
                details,
                text=attachment.filename,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=COLORS["text_primary"],
                anchor="w"
            ).pack(fill="x")

            ctk.CTkLabel(
                details,
                text=attachment.mime_type,
                font=ctk.CTkFont(size=11),
                text_color=COLORS["text_muted"],
                anchor="w"
            ).pack(fill="x")

            open_btn = ctk.CTkButton(
                row,
                text="Open",
                font=ctk.CTkFont(size=12),
                width=58,
                height=30,
                fg_color="transparent",
                hover_color=COLORS["bg_hover"],
                text_color=COLORS["accent_blue"],
                command=lambda item=attachment: self._open_attachment(item)
            )
            open_btn.pack(side="right", padx=8)

    def _open_attachment(self, attachment: Attachment):
        """Open an attachment with the system default handler."""
        target = attachment.stored_path
        try:
            path = Path(target)
            if path.exists():
                webbrowser.open(path.resolve().as_uri())
                return
        except (OSError, ValueError):
            pass
        if target:
            webbrowser.open(target)
    
    def _on_type_change(self):
        """Switch between text and checklist editor"""
        if self.note_type_var.get() == "checklist":
            self.text_frame.pack_forget()
            self.checklist_frame.pack(fill="both", expand=True)
        else:
            self.checklist_frame.pack_forget()
            self.text_frame.pack(fill="both", expand=True)
        self._refresh_markdown_controls()
        self._on_modify()
    
    def _toggle_pin(self):
        """Toggle note pinned status"""
        if self.current_note:
            self.current_note.pinned = not self.current_note.pinned
            pin_color = COLORS["accent_yellow"] if self.current_note.pinned else COLORS["text_secondary"]
            self.pin_btn.configure(image=IconManager.get_icon("pin", 18, pin_color))
            self._on_modify()
    
    def _add_checklist_item(
        self,
        text: str = "",
        checked: bool = False,
        item_id: Optional[str] = None,
        indent: int = 0,
        focus: bool = True
    ):
        """Add a checklist item widget."""
        item_frame = ctk.CTkFrame(self.checklist_scroll, fg_color="transparent")
        item_frame.item_id = item_id or str(uuid.uuid4())
        item_frame.indent = clamp_checklist_indent(indent)

        drag_handle = ctk.CTkLabel(
            item_frame,
            text="::",
            width=22,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLORS["text_muted"]
        )
        drag_handle.pack(side="left", padx=(4, 4))
        drag_handle.bind("<ButtonPress-1>", lambda e, frame=item_frame: self._start_checklist_drag(frame))
        drag_handle.bind("<ButtonRelease-1>", lambda e, frame=item_frame: self._finish_checklist_drag(frame, e))

        check_var = ctk.BooleanVar(value=checked)
        checkbox = ctk.CTkCheckBox(
            item_frame,
            text="",
            variable=check_var,
            width=24,
            height=24,
            fg_color=COLORS["accent_green"],
            hover_color=COLORS["accent_green_hover"],
            border_color=COLORS["border_light"],
            command=self._on_modify
        )
        checkbox.pack(side="left", padx=(0, 8))

        entry = ctk.CTkEntry(
            item_frame,
            placeholder_text="List item",
            font=ctk.CTkFont(size=13),
            fg_color="transparent",
            border_width=0,
            text_color=COLORS["text_primary"]
        )
        entry.pack(side="left", fill="x", expand=True)
        entry.insert(0, text)
        entry.bind("<KeyRelease>", self._on_modify)
        entry.bind("<Return>", lambda e: self._add_checklist_item())

        for label, delta in (("<", -1), (">", 1)):
            indent_btn = ctk.CTkButton(
                item_frame,
                text=label,
                width=24,
                height=24,
                fg_color="transparent",
                hover_color=COLORS["bg_hover"],
                text_color=COLORS["text_muted"],
                command=lambda d=delta, frame=item_frame: self._adjust_checklist_indent(frame, d)
            )
            indent_btn.pack(side="right", padx=(2, 0))

        down_btn = ctk.CTkButton(
            item_frame,
            text="Dn",
            width=32,
            height=24,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_muted"],
            command=lambda: self._move_checklist_item(item_frame, 1)
        )
        down_btn.pack(side="right", padx=(2, 0))

        up_btn = ctk.CTkButton(
            item_frame,
            text="Up",
            width=32,
            height=24,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_muted"],
            command=lambda: self._move_checklist_item(item_frame, -1)
        )
        up_btn.pack(side="right", padx=(2, 0))

        delete_btn = ctk.CTkButton(
            item_frame,
            text="x",
            width=24,
            height=24,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_muted"],
            command=lambda: self._remove_checklist_item(item_frame)
        )
        delete_btn.pack(side="right", padx=(4, 4))

        item_frame.check_var = check_var
        item_frame.entry = entry
        self.checklist_items_widgets.append(item_frame)
        self._repack_checklist_items()

        if focus:
            entry.focus_set()
        self._on_modify()

    def _repack_checklist_items(self):
        """Pack checklist rows in stored order with visual indentation."""
        for widget in self.checklist_items_widgets:
            widget.pack_forget()
            widget.pack(fill="x", pady=2, padx=(4 + widget.indent * 24, 4))

    def _move_checklist_item(self, item_frame, delta: int):
        """Move a checklist item up or down."""
        try:
            index = self.checklist_items_widgets.index(item_frame)
        except ValueError:
            return
        new_index = max(0, min(len(self.checklist_items_widgets) - 1, index + delta))
        if new_index == index:
            return
        self.checklist_items_widgets.pop(index)
        self.checklist_items_widgets.insert(new_index, item_frame)
        self._repack_checklist_items()
        self._on_modify()

    def _adjust_checklist_indent(self, item_frame, delta: int):
        """Indent or outdent a checklist item."""
        item_frame.indent = max(0, min(4, item_frame.indent + delta))
        self._repack_checklist_items()
        self._on_modify()

    def _start_checklist_drag(self, item_frame):
        """Record which checklist row is being dragged."""
        self._dragging_checklist_item = item_frame
        item_frame.configure(fg_color=COLORS["bg_light"])

    def _finish_checklist_drag(self, item_frame, event):
        """Drop a dragged checklist row near the row under the pointer."""
        if getattr(self, "_dragging_checklist_item", None) is not item_frame:
            return

        others = [widget for widget in self.checklist_items_widgets if widget is not item_frame]
        insert_at = len(others)
        for index, widget in enumerate(others):
            midpoint = widget.winfo_rooty() + (widget.winfo_height() / 2)
            if event.y_root < midpoint:
                insert_at = index
                break

        self.checklist_items_widgets = others
        self.checklist_items_widgets.insert(insert_at, item_frame)
        item_frame.configure(fg_color="transparent")
        self._dragging_checklist_item = None
        self._repack_checklist_items()
        self._on_modify()

    def _remove_checklist_item(self, item_frame):
        """Remove a checklist item widget."""
        item_frame.destroy()
        if item_frame in self.checklist_items_widgets:
            self.checklist_items_widgets.remove(item_frame)
        self._on_modify()

    def _clear_checklist_items(self):
        """Clear all checklist item widgets."""
        for widget in self.checklist_items_widgets:
            widget.destroy()
        self.checklist_items_widgets.clear()

    def _load_checklist_items(self, items: List[ChecklistItem]):
        """Load checklist items into widgets."""
        self._clear_checklist_items()
        for item in items:
            self._add_checklist_item(item.text, item.checked, item.id, item.indent, focus=False)
    
    def _add_label(self, event=None):
        """Add a label to the note"""
        label_text = self.label_entry.get().strip()
        if label_text and self.current_note:
            if label_text not in self.current_note.labels:
                self.current_note.labels.append(label_text)
                self._load_labels(self.current_note.labels)
                self._on_modify()
            self.label_entry.delete(0, "end")
    
    def _remove_label(self, label: str):
        """Remove a label from the note"""
        if self.current_note and label in self.current_note.labels:
            self.current_note.labels.remove(label)
            self._load_labels(self.current_note.labels)
            self._on_modify()
    
    def _load_labels(self, labels: List[str]):
        """Load labels into display"""
        for widget in self.labels_display.winfo_children():
            widget.destroy()
        
        for label in labels:
            label_frame = ctk.CTkFrame(
                self.labels_display,
                fg_color=COLORS["accent_purple"],
                corner_radius=12
            )
            label_frame.pack(side="left", padx=(0, 4))
            
            label_text = ctk.CTkLabel(
                label_frame,
                text=label,
                font=ctk.CTkFont(size=11),
                text_color=COLORS["bg_darkest"]
            )
            label_text.pack(side="left", padx=(8, 4), pady=4)
            
            remove_btn = ctk.CTkButton(
                label_frame,
                text="×",
                width=16,
                height=16,
                fg_color="transparent",
                hover_color=COLORS["accent_purple"],
                text_color=COLORS["bg_darkest"],
                command=lambda l=label: self._remove_label(l)
            )
            remove_btn.pack(side="left", padx=(0, 4))

        self._refresh_markdown_controls()
    
    def _save_note(self):
        """Save the current note"""
        if not self.current_note:
            return
        
        # Update note data
        self.current_note.title = self.title_entry.get()
        self.current_note.note_type = NoteType(self.note_type_var.get())
        self.current_note.color = self.selected_color
        previous_reminder = self.current_note.reminder_at

        try:
            self.current_note.reminder_at = parse_reminder_datetime(self.reminder_entry.get())
        except ValueError as e:
            messagebox.showerror("Invalid Reminder", str(e))
            return

        self.current_note.reminder_location = self.reminder_location_entry.get().strip()
        if self.current_note.reminder_at != previous_reminder:
            self.current_note.reminder_notified = False
        
        if self.current_note.note_type == NoteType.CHECKLIST:
            self.current_note.checklist_items = [
                ChecklistItem(
                    id=widget.item_id,
                    text=widget.entry.get(),
                    checked=widget.check_var.get(),
                    indent=widget.indent
                )
                for widget in self.checklist_items_widgets
                if widget.entry.get().strip()
            ]
            self.current_note.content = ""
        else:
            self.current_note.content = self.content_text.get("1.0", "end-1c")
            self.current_note.checklist_items = []
        
        self.current_note.local_modified = datetime.now(timezone.utc)
        
        # Update sync status if linked to Keep
        if self.current_note.keep_id:
            self.current_note.sync_status = SyncStatus.PENDING_PUSH
        
        # Save to database
        if self.db.save_note(self.current_note):
            self.is_modified = False
            self.sync_badge.update_status(self.current_note.sync_status)
            self.on_save_callback(self.current_note)
    
    def _unlink_from_keep(self):
        """Unlink the note from Google Keep"""
        if not self.current_note or not self.current_note.keep_id:
            return
        
        result = messagebox.askyesnocancel(
            "Unlink from Google Keep",
            "Do you want to delete this note from Google Keep?\n\n"
            "• Yes: Delete from Keep, keep locally\n"
            "• No: Just unlink (keep in both places)\n"
            "• Cancel: Don't unlink"
        )
        
        if result is None:  # Cancel
            return
        
        if self.sync_engine.unlink_note(self.current_note.id, delete_from_keep=result):
            self.current_note.keep_id = None
            self.current_note.sync_status = SyncStatus.LOCAL_ONLY
            self.sync_badge.update_status(SyncStatus.LOCAL_ONLY)
            self.unlink_btn.pack_forget()
            self.on_save_callback(self.current_note)
    
    def _handle_close(self):
        """Handle close with unsaved changes check"""
        if self.is_modified:
            result = messagebox.askyesnocancel(
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save before closing?"
            )
            if result is None:  # Cancel
                return
            if result:  # Yes
                self._save_note()
        
        self.on_close_callback()


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════════

class KeepSyncNotesApp(ctk.CTk):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        
        # Configure window
        self.title(APP_NAME)
        self.geometry("1200x800")
        self.minsize(900, 600)
        self.configure(fg_color=COLORS["bg_darkest"])
        
        # Set up data directory
        self.data_dir = get_app_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.diagnostics = DiagnosticsManager(
            self.data_dir,
            APP_NAME,
            APP_VERSION,
            {
                "keyring_available": KEYRING_AVAILABLE,
                "gkeepapi_available": GKEEPAPI_AVAILABLE,
                "desktop_notifications_available": DESKTOP_NOTIFICATIONS_AVAILABLE,
            },
        )
        set_diagnostics_manager(self.diagnostics)
        self.diagnostics.install_hooks()
        self.diagnostics.log_event("info", f"Started {APP_NAME} v{APP_VERSION}")
        
        # Initialize database and sync engine
        self.db = DatabaseManager(str(self.data_dir / "notes.db"))
        self.sync_engine = KeepSyncEngine(self.db)
        self.sync_engine.add_sync_callback(self._on_sync_status_change)
        
        # Initialize cloud sync manager
        self.cloud_sync = CloudSyncManager(self.db, APP_NAME, APP_VERSION, DB_VERSION)
        self.cloud_sync.add_callback(self._on_cloud_sync_status_change)
        
        # State
        self.current_filter = "all"  # all, archived, trash, label:<name>
        self.search_query = ""
        self.advanced_filters = default_advanced_filters()
        self.pending_delete_undo_note_id: Optional[str] = None
        self.saved_searches = self.db.get_setting("saved_searches", [])
        if not isinstance(self.saved_searches, list):
            self.saved_searches = []
        self.selected_note: Optional[Note] = None
        self._reminder_after_id = None
        self._takeout_watch_after_id = None
        self._takeout_watch_in_progress = False
        
        # Build UI
        self._build_ui()
        
        # Try auto-login to Keep
        self.after(1000, self._try_auto_connect)
        
        # Try to restore cloud sync
        self.after(1500, self._try_restore_cloud_sync)
        
        # Load notes
        self._refresh_notes_list()
        self._schedule_reminder_check(delay_ms=1000)
        self._schedule_takeout_watch_check(delay_ms=5000)
        
        # Start auto-sync if enabled
        if self.db.get_setting("auto_sync", True):
            interval = self.db.get_setting("sync_interval", 5)
            self.sync_engine.start_auto_sync(interval)
    
    def _build_ui(self):
        """Build the main UI"""
        # Main container with sidebar and content
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True)
        
        # Configure grid
        self.main_container.grid_columnconfigure(0, weight=0, minsize=240)  # Sidebar
        self.main_container.grid_columnconfigure(1, weight=1, minsize=300)  # Notes list
        self.main_container.grid_columnconfigure(2, weight=2, minsize=400)  # Editor
        self.main_container.grid_rowconfigure(0, weight=1)
        
        # Sidebar
        self._build_sidebar()
        
        # Notes list
        self._build_notes_list()
        
        # Editor panel (initially hidden)
        self._build_editor()
    
    def _build_sidebar(self):
        """Build the sidebar with navigation"""
        sidebar = ctk.CTkFrame(
            self.main_container,
            fg_color=COLORS["bg_dark"],
            corner_radius=0
        )
        sidebar.grid(row=0, column=0, sticky="nsew")
        
        # Logo/Title
        logo_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        logo_frame.pack(fill="x", padx=16, pady=20)
        
        title = ctk.CTkLabel(
            logo_frame,
            text="KeepSync",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=COLORS["accent_green"]
        )
        title.pack(anchor="w")
        
        subtitle = ctk.CTkLabel(
            logo_frame,
            text="Notes",
            font=ctk.CTkFont(size=14),
            text_color=COLORS["text_muted"]
        )
        subtitle.pack(anchor="w")
        
        # New Note button
        new_btn = ctk.CTkButton(
            sidebar,
            text="New Note",
            image=IconManager.get_icon("plus", 18, COLORS["bg_darkest"]),
            font=ctk.CTkFont(size=14, weight="bold"),
            height=44,
            fg_color=COLORS["accent_green"],
            hover_color=COLORS["accent_green_hover"],
            text_color=COLORS["bg_darkest"],
            corner_radius=10,
            command=self._new_note
        )
        new_btn.pack(fill="x", padx=16, pady=(0, 20))
        
        # Navigation items
        nav_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        nav_frame.pack(fill="x", padx=8)
        
        self.nav_buttons = {}
        nav_items = [
            ("all", "All Notes", "note"),
            ("archived", "Archive", "archive"),
            ("trash", "Trash", "trash"),
        ]
        
        for key, text, icon in nav_items:
            btn = ctk.CTkButton(
                nav_frame,
                text=text,
                image=IconManager.get_icon(icon, 18, COLORS["text_secondary"]),
                font=ctk.CTkFont(size=13),
                height=40,
                fg_color="transparent",
                hover_color=COLORS["bg_hover"],
                text_color=COLORS["text_secondary"],
                anchor="w",
                command=lambda k=key: self._set_filter(k)
            )
            btn.pack(fill="x", pady=2)
            self.nav_buttons[key] = btn
        
        # Labels section
        labels_header = ctk.CTkFrame(sidebar, fg_color="transparent")
        labels_header.pack(fill="x", padx=16, pady=(20, 8))
        
        ctk.CTkLabel(
            labels_header,
            text="LABELS",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLORS["text_muted"]
        ).pack(side="left")
        
        add_label_btn = ctk.CTkButton(
            labels_header,
            text="+",
            width=24,
            height=24,
            font=ctk.CTkFont(size=14),
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_muted"],
            command=self._add_label_dialog
        )
        add_label_btn.pack(side="right")
        
        self.labels_frame = ctk.CTkScrollableFrame(
            sidebar,
            fg_color="transparent",
            height=200
        )
        self.labels_frame.pack(fill="x", padx=8)

        ctk.CTkLabel(
            sidebar,
            text="SAVED SEARCHES",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLORS["text_muted"]
        ).pack(anchor="w", padx=16, pady=(16, 8))

        self.saved_searches_frame = ctk.CTkScrollableFrame(
            sidebar,
            fg_color="transparent",
            height=120
        )
        self.saved_searches_frame.pack(fill="x", padx=8)
        
        # Sync status section
        sync_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        sync_frame.pack(fill="x", side="bottom", padx=16, pady=16)
        
        self.sync_status_label = ctk.CTkLabel(
            sync_frame,
            text="Offline",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_muted"]
        )
        self.sync_status_label.pack(side="left")

        self.undo_delete_btn = ctk.CTkButton(
            sync_frame,
            text="Undo",
            width=54,
            height=28,
            font=ctk.CTkFont(size=12),
            fg_color=COLORS["accent_blue"],
            hover_color=COLORS["accent_blue_hover"],
            command=self._undo_delete_note
        )
        self.undo_delete_btn.pack(side="left", padx=(8, 0))
        self.undo_delete_btn.pack_forget()
        
        self.sync_btn = ctk.CTkButton(
            sync_frame,
            text="",
            image=IconManager.get_icon("sync", 18, COLORS["text_secondary"]),
            width=36,
            height=36,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            command=self._cloud_sync_now
        )
        self.sync_btn.pack(side="right")
        
        settings_btn = ctk.CTkButton(
            sync_frame,
            text="",
            image=IconManager.get_icon("settings", 18, COLORS["text_secondary"]),
            width=36,
            height=36,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            command=self._open_settings
        )
        settings_btn.pack(side="right", padx=(0, 4))
        
        # Set initial nav state
        self._update_nav_state()
        self._refresh_labels()
        self._refresh_saved_searches()
    
    def _build_notes_list(self):
        """Build the notes list panel"""
        list_panel = ctk.CTkFrame(
            self.main_container,
            fg_color=COLORS["bg_darkest"],
            corner_radius=0
        )
        list_panel.grid(row=0, column=1, sticky="nsew")
        
        # Search bar
        search_frame = ctk.CTkFrame(list_panel, fg_color="transparent")
        search_frame.pack(fill="x", padx=16, pady=16)
        
        self.search_entry = ctk.CTkEntry(
            search_frame,
            placeholder_text="Search notes...",
            font=ctk.CTkFont(size=13),
            height=40,
            fg_color=COLORS["bg_medium"],
            border_width=1,
            border_color=COLORS["border"],
            corner_radius=10
        )
        self.search_entry.pack(fill="x")
        self.search_entry.bind("<KeyRelease>", self._on_search)

        filter_row = ctk.CTkFrame(list_panel, fg_color="transparent")
        filter_row.pack(fill="x", padx=16, pady=(0, 8))

        self.filter_summary_label = ctk.CTkLabel(
            filter_row,
            text="No filters",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_muted"],
            anchor="w"
        )
        self.filter_summary_label.pack(side="left", fill="x", expand=True)

        filter_btn = ctk.CTkButton(
            filter_row,
            text="Filters",
            font=ctk.CTkFont(size=12),
            width=74,
            height=30,
            fg_color=COLORS["bg_medium"],
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_primary"],
            command=self._open_advanced_filters
        )
        filter_btn.pack(side="right")

        save_search_btn = ctk.CTkButton(
            filter_row,
            text="Save",
            font=ctk.CTkFont(size=12),
            width=58,
            height=30,
            fg_color=COLORS["bg_medium"],
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_primary"],
            command=self._save_current_search
        )
        save_search_btn.pack(side="right", padx=(0, 8))
        
        # Notes count
        self.notes_count_label = ctk.CTkLabel(
            list_panel,
            text="0 notes",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_muted"]
        )
        self.notes_count_label.pack(anchor="w", padx=16, pady=(0, 8))
        
        # Notes scroll area
        self.notes_scroll = ctk.CTkScrollableFrame(
            list_panel,
            fg_color="transparent"
        )
        self.notes_scroll.pack(fill="both", expand=True, padx=8)
        
        self.note_cards: List[NoteCard] = []
    
    def _build_editor(self):
        """Build the editor panel"""
        self.editor_panel = ctk.CTkFrame(
            self.main_container,
            fg_color=COLORS["bg_dark"],
            corner_radius=0
        )
        self.editor_panel.grid(row=0, column=2, sticky="nsew")
        
        # Empty state
        self.empty_state = ctk.CTkFrame(self.editor_panel, fg_color="transparent")
        self.empty_state.pack(fill="both", expand=True)
        
        empty_icon = ctk.CTkLabel(
            self.empty_state,
            text="",
            image=IconManager.get_icon("note", 64, COLORS["text_muted"])
        )
        empty_icon.pack(pady=(100, 16))
        
        empty_text = ctk.CTkLabel(
            self.empty_state,
            text="Select a note to view or edit",
            font=ctk.CTkFont(size=14),
            text_color=COLORS["text_muted"]
        )
        empty_text.pack()
        
        empty_hint = ctk.CTkLabel(
            self.empty_state,
            text="or create a new one",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_disabled"]
        )
        empty_hint.pack(pady=(4, 0))
        
        # Editor (initially hidden)
        self.editor = NoteEditor(
            self.editor_panel,
            self.db,
            self.sync_engine,
            on_save=self._on_note_saved,
            on_close=self._close_editor
        )
    
    def _set_filter(self, filter_key: str):
        """Set the current filter and refresh notes"""
        self.current_filter = filter_key
        self._update_nav_state()
        self._refresh_saved_searches()
        self._refresh_notes_list()
    
    def _update_nav_state(self):
        """Update navigation button states"""
        for key, btn in self.nav_buttons.items():
            if key == self.current_filter:
                btn.configure(
                    fg_color=COLORS["bg_light"],
                    text_color=COLORS["text_primary"]
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=COLORS["text_secondary"]
                )
    
    def _get_filtered_notes_for_current_view(self) -> List[Note]:
        """Return notes for the active sidebar/search/filter state."""
        advanced_active = advanced_filters_active(self.advanced_filters)
        include_archived = bool(self.advanced_filters.get("is_archived"))
        used_indexed_search = False

        if self.current_filter == "all" and self.search_query:
            notes = self.db.search_notes(self.search_query, include_archived=include_archived)
            used_indexed_search = True
        elif self.current_filter == "all":
            notes = self.db.get_all_notes(include_archived=include_archived)
        elif self.current_filter == "archived":
            notes = self.db.get_all_notes(include_archived=True)
            notes = [n for n in notes if n.archived]
        elif self.current_filter == "trash":
            notes = self.db.get_all_notes(include_trashed=True)
            notes = [n for n in notes if n.trashed]
        elif self.current_filter.startswith("label:"):
            label = self.current_filter[6:]
            notes = self.db.get_notes_by_label(label)
        elif self.current_filter.startswith("saved:") and self.search_query:
            notes = self.db.search_notes(self.search_query, include_archived=include_archived)
            used_indexed_search = True
        elif self.current_filter.startswith("saved:"):
            notes = self.db.get_all_notes(include_archived=include_archived)
        else:
            notes = self.db.get_all_notes()

        if self.search_query and not (self.current_filter == "all") and not used_indexed_search:
            query_lower = self.search_query.lower()
            notes = [n for n in notes if 
                     query_lower in n.title.lower() or 
                     query_lower in n.content.lower()]

        if advanced_active:
            notes = [note for note in notes if note_matches_advanced_filters(note, self.advanced_filters)]
        return notes

    def _refresh_notes_list(self):
        """Refresh the notes list based on current filter"""
        # Clear existing cards
        for card in self.note_cards:
            card.destroy()
        self.note_cards.clear()

        notes = self._get_filtered_notes_for_current_view()
        self._update_filter_summary()
        
        # Update count
        self.notes_count_label.configure(text=f"{len(notes)} note{'s' if len(notes) != 1 else ''}")
        
        # Create cards
        for note in notes:
            card = NoteCard(
                self.notes_scroll,
                note,
                on_click=self._open_note,
                on_pin=self._toggle_pin,
                on_delete=self._delete_note,
                on_archive=self._archive_note
            )
            card.pack(fill="x", pady=4, padx=4)
            self.note_cards.append(card)
    
    def _refresh_labels(self):
        """Refresh the labels list in sidebar"""
        for widget in self.labels_frame.winfo_children():
            widget.destroy()
        
        labels = self.db.get_all_labels()
        for label in labels:
            btn = ctk.CTkButton(
                self.labels_frame,
                text=label.name,
                image=IconManager.get_icon("label", 16, COLORS["accent_purple"]),
                font=ctk.CTkFont(size=12),
                height=36,
                fg_color="transparent",
                hover_color=COLORS["bg_hover"],
                text_color=COLORS["text_secondary"],
                anchor="w",
                command=lambda l=label.name: self._set_filter(f"label:{l}")
            )
            btn.pack(fill="x", pady=1)

    def _refresh_saved_searches(self):
        if not hasattr(self, "saved_searches_frame"):
            return
        for widget in self.saved_searches_frame.winfo_children():
            widget.destroy()
        for saved in self.saved_searches:
            btn = ctk.CTkButton(
                self.saved_searches_frame,
                text=saved.get("name", "Saved search"),
                image=IconManager.get_icon("search", 16, COLORS["accent_cyan"]),
                font=ctk.CTkFont(size=12),
                height=34,
                fg_color=COLORS["bg_light"] if self.current_filter == f"saved:{saved.get('id')}" else "transparent",
                hover_color=COLORS["bg_hover"],
                text_color=COLORS["text_secondary"],
                anchor="w",
                command=lambda item=saved: self._open_saved_search(item)
            )
            btn.pack(fill="x", pady=1)
    
    def _on_search(self, event=None):
        """Handle search input"""
        self.search_query = self.search_entry.get()
        self._refresh_notes_list()

    def _open_advanced_filters(self):
        AdvancedFilterDialog(self, self.advanced_filters, self._apply_advanced_filters)

    def _apply_advanced_filters(self, filters: Dict[str, Any]):
        self.advanced_filters = dict(default_advanced_filters())
        self.advanced_filters.update(filters or {})
        self._refresh_notes_list()

    def _save_current_search(self):
        if not self.search_query and not advanced_filters_active(self.advanced_filters):
            self.sync_status_label.configure(text="No search to save", text_color=COLORS["text_muted"])
            return
        dialog = ctk.CTkInputDialog(text="Saved search name:", title="Save Search")
        name = dialog.get_input()
        if not name:
            return
        saved = {
            "id": str(uuid.uuid4()),
            "name": name.strip(),
            "query": self.search_query,
            "filters": dict(self.advanced_filters),
        }
        self.saved_searches.append(saved)
        self.db.set_setting("saved_searches", self.saved_searches)
        self._refresh_saved_searches()
        self.sync_status_label.configure(text="Saved search", text_color=COLORS["accent_green"])

    def _open_saved_search(self, saved: Dict[str, Any]):
        self.current_filter = f"saved:{saved.get('id')}"
        self.search_query = saved.get("query", "")
        self.search_entry.delete(0, "end")
        if self.search_query:
            self.search_entry.insert(0, self.search_query)
        self.advanced_filters = dict(default_advanced_filters())
        self.advanced_filters.update(saved.get("filters") or {})
        self._update_nav_state()
        self._refresh_saved_searches()
        self._refresh_notes_list()

    def _update_filter_summary(self):
        if not hasattr(self, "filter_summary_label"):
            return
        if not advanced_filters_active(self.advanced_filters):
            self.filter_summary_label.configure(text="No filters", text_color=COLORS["text_muted"])
            return
        parts = [self.advanced_filters.get("mode", "AND")]
        if self.advanced_filters.get("label"):
            parts.append(f"label:{self.advanced_filters['label']}")
        if self.advanced_filters.get("color"):
            parts.append(f"color:{self.advanced_filters['color']}")
        if self.advanced_filters.get("date_from") or self.advanced_filters.get("date_to"):
            parts.append(f"{self.advanced_filters.get('date_from') or '*'}..{self.advanced_filters.get('date_to') or '*'}")
        for key, label in (("has_image", "image"), ("has_checklist", "checklist"), ("is_archived", "archived")):
            if self.advanced_filters.get(key):
                parts.append(label)
        self.filter_summary_label.configure(text=" | ".join(parts[:4]), text_color=COLORS["accent_blue"])
    
    def _new_note(self):
        """Create a new note"""
        self.empty_state.pack_forget()
        self.editor.pack(fill="both", expand=True)
        self.editor.load_note(None)
    
    def _open_note(self, note: Note):
        """Open a note in the editor"""
        self.selected_note = note
        self.empty_state.pack_forget()
        self.editor.pack(fill="both", expand=True)
        self.editor.load_note(note)
    
    def _close_editor(self):
        """Close the editor and show empty state"""
        self.editor.pack_forget()
        self.empty_state.pack(fill="both", expand=True)
        self.selected_note = None
    
    def _on_note_saved(self, note: Note):
        """Handle note save"""
        self._refresh_notes_list()
        self._refresh_labels()
    
    def _toggle_pin(self, note: Note):
        """Toggle note pinned status"""
        note.pinned = not note.pinned
        note.local_modified = datetime.now(timezone.utc)
        if note.keep_id:
            note.sync_status = SyncStatus.PENDING_PUSH
        self.db.save_note(note)
        self._refresh_notes_list()
    
    def _archive_note(self, note: Note):
        """Archive a note"""
        note.archived = True
        note.local_modified = datetime.now(timezone.utc)
        if note.keep_id:
            note.sync_status = SyncStatus.PENDING_PUSH
        self.db.save_note(note)
        self._refresh_notes_list()
    
    def _delete_note(self, note: Note):
        """Delete a note (move to trash)"""
        if note.trashed:
            try:
                LocalBackupManager(self.db, APP_NAME, APP_VERSION).create_backup("before permanent delete")
            except Exception as e:
                log_diagnostic_exception("permanent delete backup", e)
            if self.db.delete_note(note.id, permanent=True):
                self._clear_delete_undo()
                self.sync_status_label.configure(text="Deleted permanently", text_color=COLORS["accent_red"])
        else:
            if self.db.delete_note(note.id):
                self.pending_delete_undo_note_id = note.id
                self.undo_delete_btn.pack(side="left", padx=(8, 0))
                self.sync_status_label.configure(text="Moved to trash", text_color=COLORS["accent_yellow"])
        
        if self.selected_note and self.selected_note.id == note.id:
            self._close_editor()
        self._refresh_notes_list()

    def _clear_delete_undo(self):
        self.pending_delete_undo_note_id = None
        if hasattr(self, "undo_delete_btn"):
            self.undo_delete_btn.pack_forget()

    def _undo_delete_note(self):
        note_id = self.pending_delete_undo_note_id
        if not note_id:
            self._clear_delete_undo()
            return
        if self.db.restore_note(note_id):
            self._clear_delete_undo()
            self.sync_status_label.configure(text="Restored note", text_color=COLORS["accent_green"])
            self._refresh_notes_list()
            self._refresh_labels()
        else:
            self.sync_status_label.configure(text="Restore failed", text_color=COLORS["accent_red"])
    
    def _add_label_dialog(self):
        """Show dialog to add a new label"""
        dialog = ctk.CTkInputDialog(
            text="Enter label name:",
            title="New Label"
        )
        label_name = dialog.get_input()
        if label_name:
            label = Label(id=str(uuid.uuid4()), name=label_name)
            self.db.save_label(label)
            self._refresh_labels()
    
    def _manual_sync(self):
        """Trigger manual sync"""
        if not self.sync_engine.is_authenticated:
            messagebox.showinfo("Not Connected", 
                              "Connect to Google Keep in Settings to enable sync.")
            return
        
        self.sync_btn.configure(state="disabled")
        self.sync_status_label.configure(text="Syncing...")
        
        def do_sync():
            success, message, stats = self.sync_engine.sync()
            self.after(0, lambda: self._on_sync_complete(success, message, stats))
        
        threading.Thread(target=do_sync, daemon=True).start()
    
    def _on_sync_complete(self, success: bool, message: str, stats: dict):
        """Handle sync completion"""
        self.sync_btn.configure(state="normal")
        if success:
            self.sync_status_label.configure(
                text=f"Synced ↓{stats.get('pulled', 0)} ↑{stats.get('pushed', 0)}",
                text_color=COLORS["accent_green"]
            )
        else:
            log_diagnostic_event("error", f"Keep sync failed: {message}")
            self.sync_status_label.configure(
                text="Sync error",
                text_color=COLORS["accent_red"]
            )
        self._refresh_notes_list()
    
    def _on_sync_status_change(self, status: str, message: str):
        """Handle sync status changes from background sync"""
        def update():
            if status == "syncing":
                self.sync_status_label.configure(text="Syncing...", text_color=COLORS["accent_yellow"])
            elif status == "synced":
                self.sync_status_label.configure(text=message, text_color=COLORS["accent_green"])
                self._refresh_notes_list()
            elif status == "error":
                log_diagnostic_event("error", f"Keep sync status error: {message}")
                self.sync_status_label.configure(text="Error", text_color=COLORS["accent_red"])
            elif status == "connected":
                self.sync_status_label.configure(text="Connected", text_color=COLORS["accent_green"])
            elif status == "disconnected":
                self.sync_status_label.configure(text="Offline", text_color=COLORS["text_muted"])
        
        self.after(0, update)
    
    def _try_auto_connect(self):
        """Try to auto-connect to Keep on startup"""
        if self.sync_engine.try_auto_login():
            self.sync_status_label.configure(text="Connected", text_color=COLORS["accent_green"])
            # Initial sync
            self._manual_sync()
    
    def _open_settings(self):
        """Open settings dialog"""
        SettingsDialog(
            self,
            self.db,
            self.sync_engine,
            self.cloud_sync,
            app_name=APP_NAME,
            app_version=APP_VERSION,
            db_version=DB_VERSION,
            gkeepapi_available=GKEEPAPI_AVAILABLE,
            web_scraper_factory=KeepWebScraper,
        )

    def restore_local_backup(self, backup_path: Path) -> Path:
        """Restore a local backup and rebind app services to the restored database."""
        if self._reminder_after_id:
            self.after_cancel(self._reminder_after_id)
            self._reminder_after_id = None
        if self._takeout_watch_after_id:
            self.after_cancel(self._takeout_watch_after_id)
            self._takeout_watch_after_id = None

        self.sync_engine.stop_auto_sync()
        self.cloud_sync.stop_auto_sync()

        manager = LocalBackupManager(self.db, APP_NAME, APP_VERSION)
        safety_backup = manager.create_backup("pre-restore")
        manager.restore_backup(Path(backup_path))

        self.db = DatabaseManager(str(self.data_dir / "notes.db"))
        self.sync_engine = KeepSyncEngine(self.db)
        self.sync_engine.add_sync_callback(self._on_sync_status_change)
        self.cloud_sync = CloudSyncManager(self.db, APP_NAME, APP_VERSION, DB_VERSION)
        self.cloud_sync.add_callback(self._on_cloud_sync_status_change)
        self.editor.db = self.db
        self.editor.sync_engine = self.sync_engine

        self.saved_searches = self.db.get_setting("saved_searches", [])
        if not isinstance(self.saved_searches, list):
            self.saved_searches = []
        self.selected_note = None
        self._close_editor()
        self._refresh_labels()
        self._refresh_saved_searches()
        self._refresh_notes_list()
        self._update_cloud_status_display()
        self._schedule_reminder_check(delay_ms=1000)
        self._schedule_takeout_watch_check(delay_ms=5000)
        if self.db.get_setting("auto_sync", True):
            interval = self.db.get_setting("sync_interval", 5)
            self.sync_engine.start_auto_sync(interval)
        return safety_backup
    
    def _try_restore_cloud_sync(self):
        """Try to restore cloud sync connection"""
        provider = self.db.get_setting("cloud_provider")
        
        if provider == "gdrive":
            # Google Drive can auto-reconnect via saved token
            try:
                success, _ = self.cloud_sync.connect_gdrive()
                if success:
                    self._update_cloud_status_display()
                    if self.db.get_setting("cloud_auto_sync", True):
                        interval = self.db.get_setting("cloud_sync_interval", 15)
                        self.cloud_sync.start_auto_sync(interval)
            except:
                pass
        elif provider == "github":
            repo = self.db.get_setting("github_repo", "")
            if repo:
                try:
                    success, _ = self.cloud_sync.connect_github(None, repo)
                    if success:
                        self._update_cloud_status_display()
                        if self.db.get_setting("cloud_auto_sync", True):
                            interval = self.db.get_setting("cloud_sync_interval", 15)
                            self.cloud_sync.start_auto_sync(interval)
                except:
                    pass
    
    def _on_cloud_sync_status_change(self, status: str, message: str):
        """Handle cloud sync status changes"""
        def update():
            self._update_cloud_status_display()
            if status == "synced":
                self._refresh_notes_list()
        self.after(0, update)
    
    def _update_cloud_status_display(self):
        """Update the cloud sync status in the sidebar"""
        if self.cloud_sync.is_connected():
            status = self.cloud_sync.get_status()
            provider = status.get("provider", "Cloud")
            self.sync_status_label.configure(
                text=f"☁️ {provider}",
                text_color=COLORS["accent_green"]
            )
        else:
            if self.sync_engine.is_authenticated:
                self.sync_status_label.configure(text="Connected", text_color=COLORS["accent_green"])
            else:
                self.sync_status_label.configure(text="Local only", text_color=COLORS["text_muted"])
    
    def _cloud_sync_now(self):
        """Manually trigger cloud sync"""
        if self.cloud_sync.is_connected():
            self.sync_status_label.configure(text="Syncing...", text_color=COLORS["accent_yellow"])
            
            def do_sync():
                success, message, stats = self.cloud_sync.sync()
                self.after(0, lambda: self._on_cloud_sync_complete(success, message, stats))
            
            threading.Thread(target=do_sync, daemon=True).start()
        else:
            self._manual_sync()  # Fall back to Keep sync
    
    def _on_cloud_sync_complete(self, success: bool, message: str, stats: dict):
        """Handle cloud sync completion"""
        if success:
            pulled = stats.get("downloaded", 0)
            pushed = stats.get("uploaded", 0)
            self.sync_status_label.configure(
                text=f"☁️ ↑{pushed} ↓{pulled}",
                text_color=COLORS["accent_green"]
            )
        else:
            log_diagnostic_event("error", f"Cloud sync failed: {message}")
            self.sync_status_label.configure(text="Sync error", text_color=COLORS["accent_red"])
        self._refresh_notes_list()

    def _schedule_reminder_check(self, delay_ms: int = 60000):
        """Schedule the next due-reminder check."""
        self._reminder_after_id = self.after(delay_ms, self._check_due_reminders)

    def _check_due_reminders(self):
        """Notify for due reminders."""
        try:
            due_notes = self.db.get_due_reminders()
            for note in due_notes:
                self._notify_reminder(note)
                self.db.mark_reminder_notified(note.id)
            if due_notes:
                self._refresh_notes_list()
        finally:
            self._schedule_reminder_check()

    def _schedule_takeout_watch_check(self, delay_ms: int = 60000):
        """Schedule the watched Takeout folder poll."""
        self._takeout_watch_after_id = self.after(delay_ms, self._check_takeout_watch_folder)

    def _takeout_watch_enabled(self) -> bool:
        folder = self.db.get_setting("takeout_watch_folder", "")
        return bool(self.db.get_setting("takeout_watch_enabled", False) and folder and Path(folder).exists())

    def _takeout_candidate_signature(self, path: Path) -> str:
        if path.is_file():
            stat = path.stat()
            return f"file:{stat.st_size}:{stat.st_mtime_ns}"

        json_files = MultiSourceImporter(self.db)._takeout_json_files(path)
        if not json_files:
            return ""
        size = 0
        latest = 0
        for json_file in json_files:
            stat = json_file.stat()
            size += stat.st_size
            latest = max(latest, stat.st_mtime_ns)
        return f"folder:{len(json_files)}:{size}:{latest}"

    def _takeout_watch_candidates(self, folder: Path) -> List[Path]:
        candidates = []
        for child in folder.iterdir():
            if child.name.startswith("."):
                continue
            try:
                if time.time() - child.stat().st_mtime < 10:
                    continue
            except OSError:
                continue
            if child.is_file() and child.suffix.lower() == ".zip":
                candidates.append(child)
            elif child.is_dir() and MultiSourceImporter(self.db)._takeout_json_files(child):
                candidates.append(child)
        return sorted(candidates, key=lambda item: item.name.lower())

    def _check_takeout_watch_folder(self):
        """Import new Takeout ZIPs/folders from the configured watch folder."""
        if self._takeout_watch_in_progress or not self._takeout_watch_enabled():
            self._schedule_takeout_watch_check()
            return

        watch_folder = Path(self.db.get_setting("takeout_watch_folder", ""))
        processed = self.db.get_setting("takeout_processed_imports", {})
        if not isinstance(processed, dict):
            processed = {}

        pending = []
        for candidate in self._takeout_watch_candidates(watch_folder):
            try:
                signature = self._takeout_candidate_signature(candidate)
            except OSError:
                continue
            key = str(candidate.resolve())
            if signature and processed.get(key) != signature:
                pending.append((candidate, key, signature))

        if not pending:
            self._schedule_takeout_watch_check()
            return

        self._takeout_watch_in_progress = True
        self.sync_status_label.configure(text="Auto-importing...", text_color=COLORS["accent_yellow"])

        def do_import():
            importer = MultiSourceImporter(self.db)
            imported = 0
            errors = 0
            updated_processed = dict(processed)

            try:
                LocalBackupManager(self.db, APP_NAME, APP_VERSION).create_backup("before auto takeout import")
            except Exception as e:
                self.db.log_sync("auto_import", "backup", "error", str(e))
                errors += 1
                self.db.set_setting("takeout_processed_imports", updated_processed)
                self.after(0, lambda: self._on_takeout_watch_complete(imported, errors))
                return

            for path, key, signature in pending:
                try:
                    notes = importer.import_takeout_path(path)
                    imported += importer.save_notes(notes)
                    updated_processed[key] = signature
                except Exception as e:
                    errors += 1
                    self.db.log_sync("auto_import", key, "error", str(e))

            self.db.set_setting("takeout_processed_imports", updated_processed)
            self.after(0, lambda: self._on_takeout_watch_complete(imported, errors))

        threading.Thread(target=do_import, daemon=True).start()

    def _on_takeout_watch_complete(self, imported: int, errors: int):
        self._takeout_watch_in_progress = False
        if imported:
            self.sync_status_label.configure(text=f"Auto-imported {imported}", text_color=COLORS["accent_green"])
            self._refresh_notes_list()
            self._refresh_labels()
        elif errors:
            self.sync_status_label.configure(text="Auto-import error", text_color=COLORS["accent_red"])
        self._schedule_takeout_watch_check()

    def _notify_reminder(self, note: Note):
        """Show a desktop reminder notification when possible."""
        title = note.title or "Untitled"
        message = note.content[:160] if note.content else ""
        if note.note_type == NoteType.CHECKLIST and note.checklist_items:
            remaining = [item.text for item in note.checklist_items if not item.checked]
            message = ", ".join(remaining[:3]) or "Checklist complete"
        if note.reminder_location:
            message = f"{message}\nLocation: {note.reminder_location}" if message else f"Location: {note.reminder_location}"

        notified = False
        if DESKTOP_NOTIFICATIONS_AVAILABLE:
            try:
                desktop_notification.notify(
                    title=f"{APP_NAME}: {title}",
                    message=message or "Reminder due",
                    app_name=APP_NAME,
                    timeout=10
                )
                notified = True
            except Exception as e:
                self.db.log_sync("reminder", note.id, "error", str(e))

        self.sync_status_label.configure(
            text=f"Reminder: {title[:24]}",
            text_color=COLORS["accent_yellow"]
        )
        if not notified:
            self.bell()
    
    def on_closing(self):
        """Handle window close"""
        if self._reminder_after_id:
            self.after_cancel(self._reminder_after_id)
        if self._takeout_watch_after_id:
            self.after_cancel(self._takeout_watch_after_id)
        self.sync_engine.stop_auto_sync()
        self.cloud_sync.stop_auto_sync()
        self.db.close()
        self.destroy()


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main(argv=None):
    """Main entry point"""
    import sys

    return run_bootstrap(
        sys.argv if argv is None else argv,
        app_factory=KeepSyncNotesApp,
        token_cli=get_master_token_cli,
        app_name=APP_NAME,
        app_version=APP_VERSION,
        set_appearance_mode=ctk.set_appearance_mode,
        set_default_color_theme=ctk.set_default_color_theme,
    )


if __name__ == "__main__":
    main()
