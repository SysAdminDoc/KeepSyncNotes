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
from PIL import Image, ImageDraw, ImageFont
import sqlite3
import json
import hashlib
import threading
import queue
import time
import os
import sys
import re
import mimetypes
import shutil
import tempfile
import zipfile
import difflib
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from html import unescape
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Callable
from enum import Enum
import webbrowser
import uuid

try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    keyring = None
    KEYRING_AVAILABLE = False

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
APP_VERSION = "1.14.0"
DB_VERSION = 1
KEYRING_SERVICE = "KeepSyncNotes"
KEEP_MASTER_TOKEN_CREDENTIAL = "google_keep_master_token"
GDRIVE_OAUTH_TOKEN_CREDENTIAL = "google_drive_oauth_token"
GITHUB_PAT_CREDENTIAL = "github_personal_access_token"

# Theme Colors (User's preferred palette)
COLORS = {
    "bg_darkest": "#020617",      # Main background
    "bg_dark": "#0f172a",          # Secondary background
    "bg_medium": "#1e293b",        # Card/panel background
    "bg_light": "#334155",         # Elevated elements
    "bg_hover": "#475569",         # Hover states
    
    "accent_green": "#22c55e",     # Primary accent
    "accent_green_hover": "#16a34a",
    "accent_green_dim": "#166534",
    
    "accent_blue": "#60a5fa",      # Secondary accent
    "accent_blue_hover": "#3b82f6",
    "accent_blue_dim": "#1e40af",
    
    "accent_yellow": "#fbbf24",    # Warning/pinned
    "accent_red": "#ef4444",       # Error/delete
    "accent_purple": "#a78bfa",    # Labels
    "accent_cyan": "#22d3ee",      # Info
    
    "text_primary": "#f8fafc",     # Primary text
    "text_secondary": "#94a3b8",   # Secondary text
    "text_muted": "#64748b",       # Muted text
    "text_disabled": "#475569",    # Disabled text
    
    "border": "#334155",           # Borders
    "border_light": "#475569",     # Light borders
    "divider": "#1e293b",          # Dividers
    
    "sync_synced": "#22c55e",      # Synced status
    "sync_pending": "#fbbf24",     # Pending sync
    "sync_error": "#ef4444",       # Sync error
    "sync_local": "#60a5fa",       # Local only
}

KEEP_COLOR_PALETTE = {
    "": ("Default", COLORS["bg_medium"]),
    "red": ("Red", "#f28b82"),
    "orange": ("Orange", "#fbbc04"),
    "yellow": ("Yellow", "#fff475"),
    "green": ("Green", "#ccff90"),
    "teal": ("Teal", "#a7ffeb"),
    "blue": ("Blue", "#cbf0f8"),
    "darkblue": ("Dark blue", "#aecbfa"),
    "purple": ("Purple", "#d7aefb"),
    "pink": ("Pink", "#fdcfe8"),
    "brown": ("Brown", "#e6c9a8"),
    "gray": ("Gray", "#e8eaed"),
}

KEEP_COLOR_ALIASES = {
    "default": "",
    "white": "",
    "none": "",
    "": "",
    "dark_blue": "darkblue",
    "dark blue": "darkblue",
}

def normalize_keep_color(value: Any) -> str:
    """Normalize Keep color names from Takeout/gkeepapi/storage."""
    if value is None:
        return ""
    color = str(value).strip().lower().replace("colorvalue.", "")
    color = color.replace("-", "_")
    color = KEEP_COLOR_ALIASES.get(color, color)
    return color if color in KEEP_COLOR_PALETTE else ""

def keep_color_hex(value: Any) -> str:
    color = normalize_keep_color(value)
    return KEEP_COLOR_PALETTE[color][1]

def keep_color_name(value: Any) -> str:
    color = normalize_keep_color(value)
    return KEEP_COLOR_PALETTE[color][0]

def clamp_checklist_indent(value: Any) -> int:
    try:
        indent = int(value or 0)
    except (TypeError, ValueError):
        indent = 0
    return max(0, min(4, indent))

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

def normalize_people(values: Any) -> List[str]:
    """Normalize shared-with metadata from Takeout/export structures."""
    people = []
    if not values:
        return people
    if isinstance(values, str):
        values = [values]
    if isinstance(values, dict):
        values = [values]

    for item in values:
        person = ""
        if isinstance(item, str):
            person = item
        elif isinstance(item, dict):
            for key in ("email", "emailAddress", "displayName", "name", "userName"):
                if item.get(key):
                    person = str(item[key])
                    break
            if not person and isinstance(item.get("user"), dict):
                nested_people = normalize_people(item["user"])
                person = nested_people[0] if nested_people else ""
        person = person.strip()
        if person and person not in people:
            people.append(person)
    return people

def extract_shared_with(data: dict) -> List[str]:
    shared = []
    for key in ("sharees", "collaborators", "contributors", "sharedWith", "sharingUserInfo"):
        for person in normalize_people(data.get(key)):
            if person not in shared:
                shared.append(person)
    if not shared and data.get("isShared"):
        shared.append("Shared")
    return shared

def sanitize_filename(value: str) -> str:
    name = Path(value or "attachment").name
    return re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .") or "attachment"

def guess_attachment_mime(path: str, fallback: str = "") -> str:
    guessed, _ = mimetypes.guess_type(path or "")
    return fallback or guessed or "application/octet-stream"

def first_present(data: dict, keys: List[str]) -> str:
    for key in keys:
        value = data.get(key)
        if value:
            return str(value)
    return ""

def takeout_attachment_specs(data: dict) -> List[dict]:
    specs = []
    for key in ("attachments", "media", "files", "blobs"):
        value = data.get(key)
        if isinstance(value, dict):
            specs.append(value)
        elif isinstance(value, list):
            specs.extend([item for item in value if isinstance(item, (dict, str))])

    for key in ("drawingInfo", "audio", "image"):
        value = data.get(key)
        if isinstance(value, dict):
            specs.append(value)
    return specs

def resolve_takeout_attachment_path(source: str, base_path: Optional[Path]) -> Optional[Path]:
    if not source or re.match(r"^[a-z]+://", source, re.IGNORECASE):
        return None

    source_path = Path(source)
    candidates = [source_path]
    if base_path:
        candidates.extend([
            base_path / source_path,
            base_path / source_path.name,
            base_path.parent / source_path,
        ])

    for candidate in candidates:
        try:
            if candidate.exists():
                return candidate
        except OSError:
            continue
    return None

def copy_attachment_to_store(source_path: Path, attachments_root: Path, note_id: str, filename: str) -> Path:
    note_dir = attachments_root / note_id
    note_dir.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_filename(filename or source_path.name)
    destination = note_dir / safe_name
    stem = destination.stem
    suffix = destination.suffix
    counter = 1
    while destination.exists():
        destination = note_dir / f"{stem}-{counter}{suffix}"
        counter += 1
    shutil.copy2(source_path, destination)
    return destination


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


def import_takeout_attachments(data: dict, base_path: Optional[Path], attachments_root: Path, note_id: str) -> List["Attachment"]:
    attachments = []
    for raw in takeout_attachment_specs(data):
        if isinstance(raw, str):
            source = raw
            filename = Path(raw).name
            mime_type = guess_attachment_mime(filename)
        else:
            source = first_present(raw, [
                "filePath", "path", "sourcePath", "url", "filename", "fileName",
                "drawingFilePath", "snapshotFilePath", "audioFilePath"
            ])
            filename = first_present(raw, ["filename", "fileName", "name", "title"]) or Path(source).name
            mime_type = first_present(raw, ["mimeType", "mimetype", "contentType"])

        if not source and not filename:
            continue

        resolved = resolve_takeout_attachment_path(source, base_path)
        stored_path = source
        if resolved:
            stored_path = str(copy_attachment_to_store(resolved, attachments_root, note_id, filename))

        attachments.append(Attachment(
            filename=filename or Path(stored_path).name,
            stored_path=stored_path,
            source_path=str(resolved or source),
            mime_type=guess_attachment_mime(stored_path or filename, mime_type),
        ))
    return attachments

class HTMLTextExtractor(HTMLParser):
    """Small HTML-to-text extractor for imported note formats."""

    BLOCK_TAGS = {
        "address", "article", "aside", "blockquote", "br", "div", "dl", "dt", "dd",
        "figcaption", "figure", "footer", "h1", "h2", "h3", "h4", "h5", "h6",
        "header", "hr", "li", "main", "ol", "p", "pre", "section", "table", "tr",
        "ul",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "en-todo":
            checked = any(name == "checked" and value == "true" for name, value in attrs)
            self.parts.append("[x] " if checked else "[ ] ")
        elif tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag.lower() in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)

    def text(self) -> str:
        value = unescape("".join(self.parts))
        value = re.sub(r"[ \t\r\f\v]+", " ", value)
        value = re.sub(r" *\n *", "\n", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
        return value.strip()

def html_to_text(value: str) -> str:
    extractor = HTMLTextExtractor()
    try:
        extractor.feed(value or "")
        return extractor.text()
    except Exception:
        return re.sub(r"<[^>]+>", "", value or "").strip()

def strip_enex_content(value: str) -> str:
    content = value or ""
    content = re.sub(r"<!DOCTYPE[^>]*>", "", content, flags=re.IGNORECASE)
    content = re.sub(r"<\?xml[^>]*\?>", "", content, flags=re.IGNORECASE)
    return html_to_text(content)

def normalize_import_labels(labels: List[str], source: str = "", markdown: bool = False) -> List[str]:
    normalized = []
    if source:
        normalized.append(source)
    if markdown:
        normalized.append(".md")
    for label in labels or []:
        label_text = str(label or "").strip()
        if label_text and label_text not in normalized:
            normalized.append(label_text)
    return normalized

def title_from_content(content: str, fallback: str) -> str:
    for line in (content or "").splitlines():
        cleaned = line.strip().strip("#").strip()
        if cleaned:
            return cleaned[:120]
    return fallback[:120] or "Untitled"

def labels_from_hashtags(content: str) -> List[str]:
    return sorted({match.group(1) for match in re.finditer(r"(?<!\w)#([A-Za-z0-9_-]+)", content or "")})

def parse_external_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    candidates = [text, text.replace("Z", "+00:00")]
    if re.fullmatch(r"\d{8}T\d{6}Z?", text):
        candidates.append(f"{text[0:4]}-{text[4:6]}-{text[6:8]}T{text[9:11]}:{text[11:13]}:{text[13:15]}+00:00")
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            continue
    return None

def decode_zip_member(zf: zipfile.ZipFile, member: zipfile.ZipInfo) -> str:
    raw = zf.read(member)
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")

def is_hidden_or_system_path(path_text: str) -> bool:
    return any(part.startswith(".") or part == "__MACOSX" for part in Path(path_text).parts)

# ═══════════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class SyncStatus(Enum):
    LOCAL_ONLY = "local_only"       # Never synced to Keep
    SYNCED = "synced"               # In sync with Keep
    PENDING_PUSH = "pending_push"   # Local changes need pushing
    PENDING_PULL = "pending_pull"   # Remote changes need pulling
    CONFLICT = "conflict"           # Conflicting changes
    DELETED_REMOTE = "deleted_remote"  # Deleted from Keep, kept locally
    ERROR = "error"                 # Sync error

class NoteType(Enum):
    NOTE = "note"
    CHECKLIST = "checklist"

@dataclass
class Attachment:
    filename: str
    stored_path: str
    mime_type: str = ""
    source_path: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self):
        self.filename = sanitize_filename(self.filename)
        self.mime_type = guess_attachment_mime(self.stored_path or self.filename, self.mime_type)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "stored_path": self.stored_path,
            "source_path": self.source_path,
            "mime_type": self.mime_type,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Attachment":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            filename=data.get("filename", Path(data.get("stored_path", "attachment")).name),
            stored_path=data.get("stored_path", ""),
            source_path=data.get("source_path", ""),
            mime_type=data.get("mime_type", ""),
        )

    @property
    def is_image(self) -> bool:
        return self.mime_type.startswith("image/")

    @property
    def exists(self) -> bool:
        return bool(self.stored_path and Path(self.stored_path).exists())

@dataclass
class ChecklistItem:
    text: str
    checked: bool = False
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    indent: int = 0
    
    def to_dict(self) -> dict:
        return {"id": self.id, "text": self.text, "checked": self.checked, "indent": self.indent}
    
    @classmethod
    def from_dict(cls, data: dict) -> "ChecklistItem":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            text=data.get("text", ""),
            checked=data.get("checked", False),
            indent=clamp_checklist_indent(data.get("indent", 0))
        )

@dataclass
class Note:
    id: str
    title: str
    content: str
    note_type: NoteType = NoteType.NOTE
    checklist_items: List[ChecklistItem] = field(default_factory=list)
    labels: List[str] = field(default_factory=list)
    pinned: bool = False
    archived: bool = False
    trashed: bool = False
    color: str = ""
    reminder_at: Optional[datetime] = None
    reminder_location: str = ""
    reminder_notified: bool = False
    shared_with: List[str] = field(default_factory=list)
    attachments: List[Attachment] = field(default_factory=list)
    
    # Sync metadata
    keep_id: Optional[str] = None
    sync_status: SyncStatus = SyncStatus.LOCAL_ONLY
    local_modified: Optional[datetime] = None
    remote_modified: Optional[datetime] = None
    content_hash: str = ""
    
    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def __post_init__(self):
        self.color = normalize_keep_color(self.color)
        self.shared_with = normalize_people(self.shared_with)
        self.attachments = [Attachment.from_dict(a) if isinstance(a, dict) else a for a in self.attachments]
        for item in self.checklist_items:
            item.indent = clamp_checklist_indent(item.indent)
        self.update_hash()
    
    def update_hash(self):
        """Generate content hash for change detection"""
        content = (
            f"{self.title}|{self.content}|{json.dumps([i.to_dict() for i in self.checklist_items])}|"
            f"{json.dumps(self.labels)}|{self.pinned}|{self.archived}|{self.trashed}|{self.color}|"
            f"{self.reminder_at.isoformat() if self.reminder_at else ''}|{self.reminder_location}|"
            f"{json.dumps(self.shared_with)}|{json.dumps([a.to_dict() for a in self.attachments])}"
        )
        self.content_hash = hashlib.md5(content.encode()).hexdigest()
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "note_type": self.note_type.value,
            "checklist_items": [i.to_dict() for i in self.checklist_items],
            "labels": self.labels,
            "pinned": self.pinned,
            "archived": self.archived,
            "trashed": self.trashed,
            "color": self.color,
            "reminder_at": self.reminder_at.isoformat() if self.reminder_at else None,
            "reminder_location": self.reminder_location,
            "reminder_notified": self.reminder_notified,
            "shared_with": self.shared_with,
            "attachments": [a.to_dict() for a in self.attachments],
            "keep_id": self.keep_id,
            "sync_status": self.sync_status.value,
            "local_modified": self.local_modified.isoformat() if self.local_modified else None,
            "remote_modified": self.remote_modified.isoformat() if self.remote_modified else None,
            "content_hash": self.content_hash,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Note":
        return cls(
            id=data["id"],
            title=data.get("title", ""),
            content=data.get("content", ""),
            note_type=NoteType(data.get("note_type", "note")),
            checklist_items=[ChecklistItem.from_dict(i) for i in data.get("checklist_items", [])],
            labels=data.get("labels", []),
            pinned=data.get("pinned", False),
            archived=data.get("archived", False),
            trashed=data.get("trashed", False),
            color=normalize_keep_color(data.get("color", "")),
            reminder_at=datetime.fromisoformat(data["reminder_at"]) if data.get("reminder_at") else None,
            reminder_location=data.get("reminder_location", ""),
            reminder_notified=data.get("reminder_notified", False),
            shared_with=normalize_people(data.get("shared_with", [])),
            attachments=[Attachment.from_dict(a) for a in data.get("attachments", [])],
            keep_id=data.get("keep_id"),
            sync_status=SyncStatus(data.get("sync_status", "local_only")),
            local_modified=datetime.fromisoformat(data["local_modified"]) if data.get("local_modified") else None,
            remote_modified=datetime.fromisoformat(data["remote_modified"]) if data.get("remote_modified") else None,
            content_hash=data.get("content_hash", ""),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(timezone.utc),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(timezone.utc),
        )

def note_diff_body(note: Note) -> str:
    if note.note_type == NoteType.CHECKLIST:
        return "\n".join(
            f"{'  ' * item.indent}{'[x]' if item.checked else '[ ]'} {item.text}"
            for item in note.checklist_items
        )
    return note.content or ""

def notes_equivalent(left: Note, right: Note) -> bool:
    return (
        (left.title or "").strip() == (right.title or "").strip()
        and note_diff_body(left).strip() == note_diff_body(right).strip()
        and sorted(left.labels) == sorted(right.labels)
        and left.note_type == right.note_type
    )

def note_conflict_diff(local_note: Note, imported_note: Note) -> str:
    local_lines = [f"# {local_note.title or 'Untitled'}", *note_diff_body(local_note).splitlines()]
    imported_lines = [f"# {imported_note.title or 'Untitled'}", *note_diff_body(imported_note).splitlines()]
    return "\n".join(difflib.unified_diff(
        local_lines,
        imported_lines,
        fromfile="local",
        tofile="imported",
        lineterm=""
    ))

def merge_note_conflict(local_note: Note, imported_note: Note) -> Note:
    merged = Note.from_dict(local_note.to_dict())
    merged.labels = normalize_import_labels(local_note.labels + imported_note.labels)
    merged.attachments = local_note.attachments + [
        attachment for attachment in imported_note.attachments
        if attachment.filename not in {existing.filename for existing in local_note.attachments}
    ]
    merged.updated_at = datetime.now(timezone.utc)
    merged.local_modified = merged.updated_at

    if local_note.note_type == NoteType.CHECKLIST or imported_note.note_type == NoteType.CHECKLIST:
        merged.note_type = NoteType.NOTE
        local_body = note_diff_body(local_note)
        imported_body = note_diff_body(imported_note)
    else:
        local_body = local_note.content or ""
        imported_body = imported_note.content or ""

    if local_body.strip() == imported_body.strip():
        merged.content = local_body
    else:
        merged.content = (
            f"{local_body.strip()}\n\n"
            "--- Imported version ---\n\n"
            f"{imported_body.strip()}"
        ).strip()
    merged.checklist_items = []
    return merged

def default_advanced_filters() -> Dict[str, Any]:
    return {
        "mode": "AND",
        "label": "",
        "color": "",
        "date_from": "",
        "date_to": "",
        "has_image": False,
        "has_checklist": False,
        "is_archived": False,
    }

def advanced_filters_active(filters: Dict[str, Any]) -> bool:
    defaults = default_advanced_filters()
    return any(filters.get(key) != value for key, value in defaults.items() if key != "mode")

def parse_filter_date(value: str) -> Optional[datetime]:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None

def note_matches_advanced_filters(note: Note, filters: Dict[str, Any]) -> bool:
    checks = []
    label = (filters.get("label") or "").strip()
    if label:
        checks.append(any(label.lower() == existing.lower() for existing in note.labels))

    color = normalize_keep_color(filters.get("color", ""))
    if color:
        checks.append(normalize_keep_color(note.color) == color)

    date_from = parse_filter_date(filters.get("date_from", ""))
    if date_from:
        checks.append(note.updated_at.astimezone(timezone.utc) >= date_from)

    date_to = parse_filter_date(filters.get("date_to", ""))
    if date_to:
        end_of_day = date_to.replace(hour=23, minute=59, second=59)
        checks.append(note.updated_at.astimezone(timezone.utc) <= end_of_day)

    if filters.get("has_image"):
        checks.append(any(attachment.is_image for attachment in note.attachments))

    if filters.get("has_checklist"):
        checks.append(note.note_type == NoteType.CHECKLIST or bool(note.checklist_items))

    if filters.get("is_archived"):
        checks.append(note.archived)

    if not checks:
        return True
    if str(filters.get("mode", "AND")).upper() == "OR":
        return any(checks)
    return all(checks)

@dataclass
class Label:
    id: str
    name: str
    color: str = ""
    keep_id: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "color": self.color, "keep_id": self.keep_id}
    
    @classmethod
    def from_dict(cls, data: dict) -> "Label":
        return cls(
            id=data["id"],
            name=data["name"],
            color=data.get("color", ""),
            keep_id=data.get("keep_id")
        )

# ═══════════════════════════════════════════════════════════════════════════════
# DATABASE MANAGER
# ═══════════════════════════════════════════════════════════════════════════════

class DatabaseManager:
    """SQLite database manager for local note storage"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema"""
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        
        cursor = self.conn.cursor()
        
        # Notes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id TEXT PRIMARY KEY,
                title TEXT DEFAULT '',
                content TEXT DEFAULT '',
                note_type TEXT DEFAULT 'note',
                checklist_items TEXT DEFAULT '[]',
                labels TEXT DEFAULT '[]',
                pinned INTEGER DEFAULT 0,
                archived INTEGER DEFAULT 0,
                trashed INTEGER DEFAULT 0,
                color TEXT DEFAULT '',
                reminder_at TEXT,
                reminder_location TEXT DEFAULT '',
                reminder_notified INTEGER DEFAULT 0,
                shared_with TEXT DEFAULT '[]',
                attachments TEXT DEFAULT '[]',
                keep_id TEXT,
                sync_status TEXT DEFAULT 'local_only',
                local_modified TEXT,
                remote_modified TEXT,
                content_hash TEXT DEFAULT '',
                created_at TEXT,
                updated_at TEXT
            )
        """)

        self._ensure_column("notes", "reminder_at", "TEXT")
        self._ensure_column("notes", "reminder_location", "TEXT DEFAULT ''")
        self._ensure_column("notes", "reminder_notified", "INTEGER DEFAULT 0")
        self._ensure_column("notes", "shared_with", "TEXT DEFAULT '[]'")
        self._ensure_column("notes", "attachments", "TEXT DEFAULT '[]'")
        
        # Labels table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS labels (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                color TEXT DEFAULT '',
                keep_id TEXT
            )
        """)
        
        # Settings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        
        # Sync log table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                action TEXT,
                note_id TEXT,
                status TEXT,
                message TEXT
            )
        """)
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_notes_keep_id ON notes(keep_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_notes_sync_status ON notes(sync_status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_notes_pinned ON notes(pinned)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_notes_archived ON notes(archived)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_notes_trashed ON notes(trashed)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_notes_reminder_at ON notes(reminder_at)")

        self.fts_available = self._init_fts(cursor)
        if self.fts_available:
            self._rebuild_fts(cursor)
        
        self.conn.commit()

    def _init_fts(self, cursor: sqlite3.Cursor) -> bool:
        try:
            cursor.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts
                USING fts5(note_id UNINDEXED, title, content, labels)
            """)
            return True
        except sqlite3.OperationalError as e:
            print(f"FTS5 unavailable: {e}")
            return False

    def _fts_text(self, note: Note) -> str:
        if note.note_type == NoteType.CHECKLIST:
            return "\n".join(item.text for item in note.checklist_items)
        return note.content or ""

    def _update_fts(self, cursor: sqlite3.Cursor, note: Note):
        if not getattr(self, "fts_available", False):
            return
        cursor.execute("DELETE FROM notes_fts WHERE note_id = ?", (note.id,))
        if note.trashed:
            return
        cursor.execute(
            "INSERT INTO notes_fts (note_id, title, content, labels) VALUES (?, ?, ?, ?)",
            (note.id, note.title, self._fts_text(note), " ".join(note.labels))
        )

    def _delete_fts(self, cursor: sqlite3.Cursor, note_id: str):
        if getattr(self, "fts_available", False):
            cursor.execute("DELETE FROM notes_fts WHERE note_id = ?", (note_id,))

    def _rebuild_fts(self, cursor: sqlite3.Cursor):
        cursor.execute("DELETE FROM notes_fts")
        cursor.execute("SELECT * FROM notes WHERE trashed = 0")
        for row in cursor.fetchall():
            self._update_fts(cursor, self._row_to_note(row))

    def _fts_query(self, query: str) -> str:
        terms = re.findall(r"[A-Za-z0-9_]+", query or "")
        return " ".join(f"{term}*" for term in terms)

    def _ensure_column(self, table: str, column: str, definition: str):
        cursor = self.conn.cursor()
        cursor.execute(f"PRAGMA table_info({table})")
        existing = {row["name"] for row in cursor.fetchall()}
        if column not in existing:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    
    def save_note(self, note: Note) -> bool:
        """Save or update a note"""
        try:
            cursor = self.conn.cursor()
            note.updated_at = datetime.now(timezone.utc)
            note.update_hash()
            
            cursor.execute("""
                INSERT OR REPLACE INTO notes 
                (id, title, content, note_type, checklist_items, labels, pinned, archived, 
                 trashed, color, reminder_at, reminder_location, reminder_notified,
                 shared_with, attachments, keep_id, sync_status, local_modified, remote_modified,
                 content_hash, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                note.id, note.title, note.content, note.note_type.value,
                json.dumps([i.to_dict() for i in note.checklist_items]),
                json.dumps(note.labels), int(note.pinned), int(note.archived),
                int(note.trashed), note.color,
                note.reminder_at.isoformat() if note.reminder_at else None,
                note.reminder_location, int(note.reminder_notified),
                json.dumps(note.shared_with),
                json.dumps([a.to_dict() for a in note.attachments]),
                note.keep_id, note.sync_status.value,
                note.local_modified.isoformat() if note.local_modified else None,
                note.remote_modified.isoformat() if note.remote_modified else None,
                note.content_hash, note.created_at.isoformat(), note.updated_at.isoformat()
            ))
            self._update_fts(cursor, note)
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error saving note: {e}")
            return False
    
    def get_note(self, note_id: str) -> Optional[Note]:
        """Get a note by ID"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM notes WHERE id = ?", (note_id,))
        row = cursor.fetchone()
        if row:
            return self._row_to_note(row)
        return None
    
    def get_all_notes(self, include_trashed: bool = False, include_archived: bool = False) -> List[Note]:
        """Get all notes with optional filters"""
        cursor = self.conn.cursor()
        query = "SELECT * FROM notes WHERE 1=1"
        if not include_trashed:
            query += " AND trashed = 0"
        if not include_archived:
            query += " AND archived = 0"
        query += " ORDER BY pinned DESC, updated_at DESC"
        
        cursor.execute(query)
        return [self._row_to_note(row) for row in cursor.fetchall()]

    def find_import_conflict(self, note: Note) -> Optional[Note]:
        """Find an existing local note that likely represents the same imported note."""
        title = (note.title or "").strip()
        if not title:
            return None
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM notes WHERE lower(title) = lower(?) AND trashed = 0 ORDER BY updated_at DESC",
            (title,)
        )
        for row in cursor.fetchall():
            existing = self._row_to_note(row)
            if existing.id != note.id:
                return existing
        return None

    def save_imported_note(self, note: Note, conflict_policy: str = "copy") -> str:
        """Save an imported note and return imported, skipped, conflict_copy, or failed."""
        conflict = self.find_import_conflict(note)
        if conflict:
            if notes_equivalent(conflict, note):
                return "skipped"
            if conflict_policy == "skip":
                return "skipped"
            if conflict_policy == "replace":
                note.id = conflict.id
                note.created_at = conflict.created_at
                note.keep_id = conflict.keep_id
            elif conflict_policy == "merge":
                note = merge_note_conflict(conflict, note)
            else:
                note.title = f"{note.title} (import conflict)"
                note.sync_status = SyncStatus.CONFLICT
                note.labels = normalize_import_labels(note.labels + ["import-conflict"])
                if self.save_note(note):
                    for label in note.labels:
                        self.ensure_label(label)
                    return "conflict_copy"
                return "failed"

        if self.save_note(note):
            for label in note.labels:
                self.ensure_label(label)
            return "imported"
        return "failed"
    
    def get_notes_by_label(self, label: str) -> List[Note]:
        """Get notes with a specific label"""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM notes WHERE labels LIKE ? AND trashed = 0 ORDER BY pinned DESC, updated_at DESC",
            (f'%"{label}"%',)
        )
        return [self._row_to_note(row) for row in cursor.fetchall()]
    
    def search_notes(self, query: str, include_archived: bool = False) -> List[Note]:
        """Search notes by indexed note text, checklist items, and labels."""
        cursor = self.conn.cursor()
        fts_query = self._fts_query(query)
        archived_clause = "" if include_archived else "AND notes.archived = 0"
        if getattr(self, "fts_available", False) and fts_query:
            try:
                cursor.execute(
                    f"""SELECT notes.*
                       FROM notes_fts
                       JOIN notes ON notes.id = notes_fts.note_id
                       WHERE notes_fts MATCH ?
                         AND notes.trashed = 0
                         {archived_clause}
                       ORDER BY bm25(notes_fts), notes.pinned DESC, notes.updated_at DESC""",
                    (fts_query,)
                )
                return [self._row_to_note(row) for row in cursor.fetchall()]
            except sqlite3.Error as e:
                print(f"FTS search failed, falling back to LIKE: {e}")

        search_term = f"%{query}%"
        cursor.execute(
            f"""SELECT * FROM notes WHERE (title LIKE ? OR content LIKE ? OR labels LIKE ? OR checklist_items LIKE ?)
               AND trashed = 0 {archived_clause} ORDER BY pinned DESC, updated_at DESC""",
            (search_term, search_term, search_term, search_term)
        )
        return [self._row_to_note(row) for row in cursor.fetchall()]
    
    def delete_note(self, note_id: str, permanent: bool = False) -> bool:
        """Delete a note (move to trash or permanent delete)"""
        try:
            cursor = self.conn.cursor()
            if permanent:
                cursor.execute("DELETE FROM notes WHERE id = ?", (note_id,))
                self._delete_fts(cursor, note_id)
            else:
                cursor.execute(
                    "UPDATE notes SET trashed = 1, updated_at = ? WHERE id = ?",
                    (datetime.now(timezone.utc).isoformat(), note_id)
                )
                self._delete_fts(cursor, note_id)
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error deleting note: {e}")
            return False
    
    def restore_note(self, note_id: str) -> bool:
        """Restore a note from trash"""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "UPDATE notes SET trashed = 0, updated_at = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), note_id)
            )
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error restoring note: {e}")
            return False

    def get_due_reminders(self, now: Optional[datetime] = None) -> List[Note]:
        """Get notes with reminders that should fire."""
        cursor = self.conn.cursor()
        due_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
        cursor.execute(
            """SELECT * FROM notes
               WHERE reminder_at IS NOT NULL
                 AND reminder_at <= ?
                 AND reminder_notified = 0
                 AND trashed = 0
               ORDER BY reminder_at ASC""",
            (due_at,)
        )
        return [self._row_to_note(row) for row in cursor.fetchall()]

    def mark_reminder_notified(self, note_id: str) -> bool:
        """Mark a reminder notification as delivered."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "UPDATE notes SET reminder_notified = 1, updated_at = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), note_id)
            )
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error marking reminder notified: {e}")
            return False
    
    def _row_to_note(self, row: sqlite3.Row) -> Note:
        """Convert database row to Note object"""
        return Note(
            id=row["id"],
            title=row["title"] or "",
            content=row["content"] or "",
            note_type=NoteType(row["note_type"]) if row["note_type"] else NoteType.NOTE,
            checklist_items=[ChecklistItem.from_dict(i) for i in json.loads(row["checklist_items"] or "[]")],
            labels=json.loads(row["labels"] or "[]"),
            pinned=bool(row["pinned"]),
            archived=bool(row["archived"]),
            trashed=bool(row["trashed"]),
            color=normalize_keep_color(row["color"] or ""),
            reminder_at=datetime.fromisoformat(row["reminder_at"]) if row["reminder_at"] else None,
            reminder_location=row["reminder_location"] or "",
            reminder_notified=bool(row["reminder_notified"]),
            shared_with=normalize_people(json.loads(row["shared_with"] or "[]")),
            attachments=[Attachment.from_dict(a) for a in json.loads(row["attachments"] or "[]")],
            keep_id=row["keep_id"],
            sync_status=SyncStatus(row["sync_status"]) if row["sync_status"] else SyncStatus.LOCAL_ONLY,
            local_modified=datetime.fromisoformat(row["local_modified"]) if row["local_modified"] else None,
            remote_modified=datetime.fromisoformat(row["remote_modified"]) if row["remote_modified"] else None,
            content_hash=row["content_hash"] or "",
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(timezone.utc),
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else datetime.now(timezone.utc),
        )
    
    # Label operations
    def save_label(self, label: Label) -> bool:
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO labels (id, name, color, keep_id) VALUES (?, ?, ?, ?)",
                (label.id, label.name, label.color, label.keep_id)
            )
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error saving label: {e}")
            return False

    def ensure_label(self, name: str) -> bool:
        label_name = str(name or "").strip()
        if not label_name:
            return False
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT id FROM labels WHERE name = ?", (label_name,))
            if cursor.fetchone():
                return True
            cursor.execute(
                "INSERT INTO labels (id, name, color, keep_id) VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), label_name, "", None)
            )
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error ensuring label: {e}")
            return False
    
    def get_all_labels(self) -> List[Label]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM labels ORDER BY name")
        return [Label(id=row["id"], name=row["name"], color=row["color"], keep_id=row["keep_id"]) 
                for row in cursor.fetchall()]
    
    def delete_label(self, label_id: str) -> bool:
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM labels WHERE id = ?", (label_id,))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error deleting label: {e}")
            return False
    
    # Settings operations
    def get_setting(self, key: str, default: Any = None) -> Any:
        cursor = self.conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        if row:
            try:
                return json.loads(row["value"])
            except:
                return row["value"]
        return default
    
    def set_setting(self, key: str, value: Any) -> bool:
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, json.dumps(value) if not isinstance(value, str) else value)
            )
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error saving setting: {e}")
            return False

    def delete_setting(self, key: str) -> bool:
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM settings WHERE key = ?", (key,))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error deleting setting: {e}")
            return False
    
    def log_sync(self, action: str, note_id: str, status: str, message: str):
        """Log sync activity"""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO sync_log (timestamp, action, note_id, status, message) VALUES (?, ?, ?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), action, note_id, status, message)
            )
            self.conn.commit()
        except Exception as e:
            print(f"Error logging sync: {e}")
    
    def close(self):
        if self.conn:
            self.conn.close()

class MultiSourceImporter:
    """Import notes from common note-app export formats."""

    TEXT_SUFFIXES = {".txt", ".md", ".markdown"}
    HTML_SUFFIXES = {".html", ".htm", ".mht", ".mhtml"}

    def __init__(self, db: DatabaseManager):
        self.db = db

    def save_notes(self, notes: List[Note]) -> int:
        imported = 0
        for note in notes:
            note.keep_id = None
            note.sync_status = SyncStatus.LOCAL_ONLY
            result = self.db.save_imported_note(note, conflict_policy="copy")
            if result in {"imported", "conflict_copy"}:
                imported += 1
        return imported

    def _note_from_text(
        self,
        title: str,
        content: str,
        source: str,
        labels: Optional[List[str]] = None,
        markdown: bool = False,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ) -> Note:
        label_values = normalize_import_labels(labels or [], source, markdown)
        now = datetime.now(timezone.utc)
        created = created_at or now
        updated = updated_at or created
        return Note(
            id=str(uuid.uuid4()),
            title=(title or "").strip() or title_from_content(content, "Untitled"),
            content=(content or "").strip(),
            labels=label_values,
            sync_status=SyncStatus.LOCAL_ONLY,
            created_at=created,
            updated_at=updated,
            local_modified=updated,
        )

    def import_enex(self, path: Path, source: str = "Evernote") -> List[Note]:
        tree = ET.parse(path)
        root = tree.getroot()
        notes = []
        for raw_note in root.findall(".//note"):
            title = (raw_note.findtext("title") or path.stem).strip()
            content = strip_enex_content(raw_note.findtext("content") or "")
            labels = [tag.text.strip() for tag in raw_note.findall("tag") if tag.text and tag.text.strip()]
            created = parse_external_datetime(raw_note.findtext("created"))
            updated = parse_external_datetime(raw_note.findtext("updated"))
            notes.append(self._note_from_text(title, content, source, labels, False, created, updated))
        return notes

    def import_text_folder(self, folder: Path, source: str, markdown_default: bool = False) -> List[Note]:
        notes = []
        for file_path in folder.rglob("*"):
            if not file_path.is_file() or is_hidden_or_system_path(str(file_path.relative_to(folder))):
                continue
            suffix = file_path.suffix.lower()
            if suffix not in self.TEXT_SUFFIXES and suffix not in self.HTML_SUFFIXES:
                continue
            raw = file_path.read_text(encoding="utf-8-sig", errors="replace")
            content = html_to_text(raw) if suffix in self.HTML_SUFFIXES else raw
            relative_parent = file_path.relative_to(folder).parent
            folder_labels = [part for part in relative_parent.parts if part and part != "."]
            markdown = markdown_default or suffix in {".md", ".markdown"}
            notes.append(self._note_from_text(file_path.stem, content, source, folder_labels, markdown))
        return notes

    def import_text_zip(self, path: Path, source: str, markdown_default: bool = False) -> List[Note]:
        notes = []
        with zipfile.ZipFile(path) as zf:
            members = [member for member in zf.infolist() if not member.is_dir() and not is_hidden_or_system_path(member.filename)]
            for member in members:
                suffix = Path(member.filename).suffix.lower()
                if suffix not in self.TEXT_SUFFIXES and suffix not in self.HTML_SUFFIXES:
                    continue
                content = decode_zip_member(zf, member)
                if suffix in self.HTML_SUFFIXES:
                    content = html_to_text(content)
                labels = [part for part in Path(member.filename).parent.parts if part and part != "."]
                labels.extend(labels_from_hashtags(content))
                markdown = markdown_default or suffix in {".md", ".markdown"} or "textbundle" in Path(member.filename).parts
                notes.append(self._note_from_text(Path(member.filename).stem, content, source, labels, markdown))
        return notes

    def import_simplenote_json(self, data: Any) -> List[Note]:
        if isinstance(data, dict):
            raw_notes = list(data.get("activeNotes") or data.get("notes") or data.get("items") or [])
            raw_notes.extend(data.get("trashedNotes") or [])
        elif isinstance(data, list):
            raw_notes = data
        else:
            raw_notes = []

        notes = []
        for item in raw_notes:
            if not isinstance(item, dict):
                continue
            content = item.get("content") or item.get("text") or item.get("body") or ""
            title = item.get("title") or title_from_content(content, "Simplenote note")
            labels = item.get("tags") or item.get("labels") or []
            markdown = "markdown" in [str(tag).lower() for tag in item.get("systemTags", [])]
            created = parse_external_datetime(item.get("creationDate") or item.get("created_at") or item.get("created"))
            updated = parse_external_datetime(item.get("modificationDate") or item.get("updated_at") or item.get("updated"))
            note = self._note_from_text(title, content, "Simplenote", labels, markdown, created, updated)
            note.trashed = bool(item.get("deleted") or item.get("trashed"))
            notes.append(note)
        return notes

    def import_simplenote_export(self, path: Path) -> List[Note]:
        if path.suffix.lower() == ".json":
            return self.import_simplenote_json(json.loads(path.read_text(encoding="utf-8-sig")))

        notes = []
        with zipfile.ZipFile(path) as zf:
            members = [member for member in zf.infolist() if not member.is_dir() and not is_hidden_or_system_path(member.filename)]
            json_members = [member for member in members if Path(member.filename).suffix.lower() == ".json"]
            for member in json_members:
                try:
                    parsed = json.loads(decode_zip_member(zf, member))
                    notes.extend(self.import_simplenote_json(parsed))
                except json.JSONDecodeError:
                    continue
            if notes:
                return notes

        return self.import_text_zip(path, "Simplenote")

    def _takeout_json_files(self, folder: Path) -> List[Path]:
        candidates = [
            folder,
            folder / "Keep",
            folder / "Takeout" / "Keep",
        ]
        for candidate in candidates:
            if candidate.exists():
                files = sorted(candidate.glob("*.json"))
                if files:
                    return files
        return []

    def import_takeout_folder(self, folder: Path) -> List[Note]:
        notes = []
        for json_file in self._takeout_json_files(folder):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                note = self.parse_takeout_note(data, json_file.parent)
                if note:
                    notes.append(note)
            except Exception:
                continue
        return notes

    def import_takeout_zip(self, path: Path) -> List[Note]:
        with tempfile.TemporaryDirectory() as temp_dir:
            with zipfile.ZipFile(path) as zf:
                zf.extractall(temp_dir)
            return self.import_takeout_folder(Path(temp_dir))

    def import_takeout_path(self, path: Path) -> List[Note]:
        if path.is_file() and path.suffix.lower() == ".zip":
            return self.import_takeout_zip(path)
        if path.is_dir():
            return self.import_takeout_folder(path)
        return []

    def parse_takeout_note(self, data: dict, base_path: Optional[Path] = None) -> Optional[Note]:
        try:
            note_id = str(uuid.uuid4())
            title = data.get("title", "")
            content = data.get("textContent", "")

            checklist_items = []
            if "listContent" in data:
                for item in data["listContent"]:
                    checklist_items.append(ChecklistItem(
                        text=item.get("text", ""),
                        checked=item.get("isChecked", False)
                    ))

            labels = []
            if "labels" in data:
                labels = [label.get("name", "") for label in data["labels"] if label.get("name")]

            attachments_root = Path(self.db.db_path).parent / "attachments"
            attachments = import_takeout_attachments(data, base_path, attachments_root, note_id)

            return Note(
                id=note_id,
                title=title,
                content=content,
                note_type=NoteType.CHECKLIST if checklist_items else NoteType.NOTE,
                checklist_items=checklist_items,
                labels=labels,
                attachments=attachments,
                pinned=data.get("isPinned", False),
                archived=data.get("isArchived", False),
                trashed=data.get("isTrashed", False),
                color=normalize_keep_color(data.get("color", "")),
                shared_with=extract_shared_with(data),
                sync_status=SyncStatus.LOCAL_ONLY,
            )
        except Exception:
            return None

    def import_external(self, source_type: str, path: Path) -> List[Note]:
        if source_type == "Evernote / Apple Notes ENEX":
            return self.import_enex(path, "Evernote")
        if source_type == "Standard Notes ZIP":
            return self.import_text_zip(path, "Standard Notes")
        if source_type == "Obsidian Vault":
            return self.import_text_folder(path, "Obsidian", markdown_default=True)
        if source_type == "Bear ZIP":
            return self.import_text_zip(path, "Bear", markdown_default=True)
        if source_type == "Simplenote Export":
            return self.import_simplenote_export(path)
        if source_type == "OneNote HTML Folder":
            return self.import_text_folder(path, "OneNote")
        raise ValueError(f"Unsupported source type: {source_type}")

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

class CloudSyncProvider:
    """Base class for cloud sync providers"""
    
    def __init__(self, db: DatabaseManager):
        self.db = db
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
    
    def __init__(self, db: DatabaseManager):
        super().__init__(db)
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
            if not token_path:
                token_path = str(Path.home() / ".keepsync_notes" / "gdrive_token.json")
            if not credentials_path:
                credentials_path = str(Path.home() / ".keepsync_notes" / "gdrive_credentials.json")
            
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
                    return False, f"Google Drive token was not saved because OS keyring is unavailable: {SECURE_CREDENTIALS.last_error}"
            
            self.creds = creds
            self.service = build('drive', 'v3', credentials=creds)
            
            # Find or create our folder
            self._ensure_folder()
            
            self.is_connected = True
            self.db.set_setting("cloud_provider", "gdrive")
            self._notify("connected", "Connected to Google Drive")
            
            return True, "Connected to Google Drive successfully"
            
        except Exception as e:
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
        SECURE_CREDENTIALS.delete_secret(GDRIVE_OAUTH_TOKEN_CREDENTIAL)
        self._notify("disconnected", "Disconnected from Google Drive")
    
    def sync(self) -> tuple[bool, str, dict]:
        """
        Sync notes with Google Drive.
        Uses a single JSON file containing all notes.
        """
        if not self.is_connected or not self.service:
            return False, "Not connected to Google Drive", {}
        
        stats = {"uploaded": 0, "downloaded": 0, "conflicts": 0}
        
        try:
            self._notify("syncing", "Syncing with Google Drive...")
            
            # Get local notes
            local_notes = self.db.get_all_notes(include_archived=True, include_trashed=False)
            local_data = {
                "version": DB_VERSION,
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
            
            if remote_files:
                # Download and merge with remote
                file_id = remote_files[0]['id']
                remote_modified = remote_files[0].get('modifiedTime')
                
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
                
                # Merge: remote notes that don't exist locally
                local_ids = {n.id for n in local_notes}
                for remote_note in remote_data.get("notes", []):
                    if remote_note["id"] not in local_ids:
                        note = Note.from_dict(remote_note)
                        self.db.save_note(note)
                        stats["downloaded"] += 1
                
                # Update the file with merged data
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
            stats["uploaded"] = len(local_notes)
            
            self.last_sync = datetime.now(timezone.utc)
            self.db.set_setting("gdrive_last_sync", self.last_sync.isoformat())
            
            self._notify("synced", f"Drive sync: ↑{stats['uploaded']} ↓{stats['downloaded']}")
            return True, "Sync completed", stats
            
        except Exception as e:
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
    
    def __init__(self, db: DatabaseManager):
        super().__init__(db)
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
            if not SECURE_CREDENTIALS.set_secret(GITHUB_PAT_CREDENTIAL, token):
                self.db.log_sync("credentials", "github", "warning", SECURE_CREDENTIALS.last_error)
                self._notify("connected", f"Connected to GitHub: {repo_name}")
                return True, f"Connected to GitHub repository: {repo_name}. Token was not saved because OS keyring is unavailable."
            self.db.delete_setting("github_token")
            
            self._notify("connected", f"Connected to GitHub: {repo_name}")
            return True, f"Connected to GitHub repository: {repo_name}"
            
        except Exception as e:
            return False, f"GitHub connection failed: {str(e)}"
    
    def disconnect(self):
        """Disconnect from GitHub"""
        self.github = None
        self.repo = None
        self.token = None
        self.is_connected = False
        self.db.set_setting("cloud_provider", None)
        self.db.delete_setting("github_token")
        SECURE_CREDENTIALS.delete_secret(GITHUB_PAT_CREDENTIAL)
        self._notify("disconnected", "Disconnected from GitHub")
    
    def sync(self) -> tuple[bool, str, dict]:
        """
        Sync notes with GitHub repository.
        Each note is stored as a separate JSON file for better git history.
        """
        if not self.is_connected or not self.repo:
            return False, "Not connected to GitHub", {}
        
        stats = {"uploaded": 0, "downloaded": 0, "conflicts": 0}
        
        try:
            from github import GithubException
            
            self._notify("syncing", "Syncing with GitHub...")
            
            # Get local notes
            local_notes = self.db.get_all_notes(include_archived=True, include_trashed=False)
            local_notes_dict = {n.id: n for n in local_notes}
            
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
            
            # Download new remote notes
            for note_id, (note_data, sha) in remote_notes.items():
                if note_id not in local_notes_dict:
                    note = Note.from_dict(note_data)
                    self.db.save_note(note)
                    stats["downloaded"] += 1
            
            # Upload local notes
            for note in local_notes:
                note_filename = f"{self.NOTES_DIR}/{note.id}.json"
                note_content = json.dumps(note.to_dict(), indent=2)
                
                try:
                    if note.id in remote_notes:
                        # Update existing
                        _, sha = remote_notes[note.id]
                        remote_data = remote_notes[note.id][0]
                        
                        # Only update if local is newer
                        if note.updated_at.isoformat() > remote_data.get('updated_at', ''):
                            self.repo.update_file(
                                note_filename,
                                f"Update note: {note.title[:50]}",
                                note_content,
                                sha
                            )
                            stats["uploaded"] += 1
                    else:
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
                "app_version": APP_VERSION
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
            
            self._notify("synced", f"GitHub sync: ↑{stats['uploaded']} ↓{stats['downloaded']}")
            return True, "Sync completed", stats
            
        except Exception as e:
            self._notify("error", f"Sync error: {str(e)}")
            return False, f"Sync error: {str(e)}", stats


class CloudSyncManager:
    """
    Manages cloud sync providers and auto-sync functionality.
    """
    
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.providers: Dict[str, CloudSyncProvider] = {
            "gdrive": GoogleDriveSync(db),
            "github": GitHubSync(db),
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

# ═══════════════════════════════════════════════════════════════════════════════
# UI COMPONENTS
# ═══════════════════════════════════════════════════════════════════════════════

class IconManager:
    """Generate and cache icons for the application"""
    
    _cache: Dict[str, ctk.CTkImage] = {}
    
    @classmethod
    def get_icon(cls, name: str, size: int = 20, color: str = None) -> ctk.CTkImage:
        """Get or create an icon"""
        cache_key = f"{name}_{size}_{color}"
        if cache_key not in cls._cache:
            cls._cache[cache_key] = cls._create_icon(name, size, color or COLORS["text_secondary"])
        return cls._cache[cache_key]
    
    @classmethod
    def _create_icon(cls, name: str, size: int, color: str) -> ctk.CTkImage:
        """Create an icon image"""
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Parse color
        if color.startswith("#"):
            r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
        else:
            r, g, b = 148, 163, 184  # Default
        
        icon_color = (r, g, b, 255)
        
        # Draw icons based on name
        if name == "search":
            draw.ellipse([3, 3, size-7, size-7], outline=icon_color, width=2)
            draw.line([size-8, size-8, size-3, size-3], fill=icon_color, width=2)
        elif name == "plus":
            mid = size // 2
            draw.line([mid, 4, mid, size-4], fill=icon_color, width=2)
            draw.line([4, mid, size-4, mid], fill=icon_color, width=2)
        elif name == "pin":
            draw.polygon([(size//2, 2), (size-4, size//2), (size//2, size-2), (4, size//2)], 
                        fill=icon_color)
        elif name == "trash":
            draw.rectangle([5, 5, size-5, 7], fill=icon_color)
            draw.rectangle([6, 8, size-6, size-3], outline=icon_color, width=1)
        elif name == "archive":
            draw.rectangle([3, 3, size-3, 8], fill=icon_color)
            draw.rectangle([5, 9, size-5, size-3], outline=icon_color, width=1)
        elif name == "sync":
            draw.arc([3, 3, size-3, size-3], 0, 270, fill=icon_color, width=2)
            draw.polygon([(size-5, size//2-3), (size-5, size//2+3), (size-2, size//2)], fill=icon_color)
        elif name == "settings":
            draw.ellipse([size//2-4, size//2-4, size//2+4, size//2+4], outline=icon_color, width=2)
            for angle in range(0, 360, 45):
                import math
                x1 = size//2 + int(6 * math.cos(math.radians(angle)))
                y1 = size//2 + int(6 * math.sin(math.radians(angle)))
                x2 = size//2 + int(9 * math.cos(math.radians(angle)))
                y2 = size//2 + int(9 * math.sin(math.radians(angle)))
                draw.line([x1, y1, x2, y2], fill=icon_color, width=2)
        elif name == "label":
            draw.polygon([(4, size//2), (10, 4), (size-3, 4), (size-3, size-4), (10, size-4)], 
                        outline=icon_color, width=1)
        elif name == "check":
            draw.line([4, size//2, size//2-2, size-5], fill=icon_color, width=2)
            draw.line([size//2-2, size-5, size-3, 5], fill=icon_color, width=2)
        elif name == "close":
            draw.line([5, 5, size-5, size-5], fill=icon_color, width=2)
            draw.line([5, size-5, size-5, 5], fill=icon_color, width=2)
        elif name == "edit":
            draw.polygon([(4, size-4), (4, size-8), (size-8, 4), (size-4, 4)], 
                        outline=icon_color, width=1)
        elif name == "cloud":
            draw.ellipse([3, size//2-2, size//2, size-3], outline=icon_color, width=1)
            draw.ellipse([size//2-3, size//2-4, size-3, size-3], outline=icon_color, width=1)
            draw.ellipse([size//3, 4, size-size//3, size//2+2], outline=icon_color, width=1)
        elif name == "local":
            draw.rectangle([4, 6, size-4, size-4], outline=icon_color, width=1)
            draw.line([size//2, 6, size//2, size-4], fill=icon_color, width=1)
            draw.line([4, size//2+1, size-4, size//2+1], fill=icon_color, width=1)
        elif name == "checklist":
            y_positions = [5, size//2, size-5]
            for y in y_positions:
                draw.rectangle([4, y-2, 8, y+2], outline=icon_color, width=1)
                draw.line([11, y, size-4, y], fill=icon_color, width=1)
        elif name == "note":
            draw.rectangle([4, 3, size-4, size-3], outline=icon_color, width=1)
            for y in [7, 11, 15]:
                if y < size - 5:
                    draw.line([7, y, size-7, y], fill=icon_color, width=1)
        elif name == "export":
            draw.rectangle([5, 8, size-5, size-3], outline=icon_color, width=1)
            draw.line([size//2, 3, size//2, 12], fill=icon_color, width=2)
            draw.polygon([(size//2-3, 6), (size//2+3, 6), (size//2, 2)], fill=icon_color)
        elif name == "import":
            draw.rectangle([5, 8, size-5, size-3], outline=icon_color, width=1)
            draw.line([size//2, 3, size//2, 12], fill=icon_color, width=2)
            draw.polygon([(size//2-3, 9), (size//2+3, 9), (size//2, 13)], fill=icon_color)
        else:
            # Default circle
            draw.ellipse([4, 4, size-4, size-4], outline=icon_color, width=2)
        
        return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))


class SyncStatusBadge(ctk.CTkFrame):
    """Badge showing sync status"""
    
    STATUS_CONFIG = {
        SyncStatus.LOCAL_ONLY: ("Local", COLORS["sync_local"], "local"),
        SyncStatus.SYNCED: ("Synced", COLORS["sync_synced"], "cloud"),
        SyncStatus.PENDING_PUSH: ("Pending", COLORS["sync_pending"], "sync"),
        SyncStatus.PENDING_PULL: ("Update", COLORS["sync_pending"], "sync"),
        SyncStatus.CONFLICT: ("Conflict", COLORS["accent_red"], "close"),
        SyncStatus.DELETED_REMOTE: ("Unlinked", COLORS["text_muted"], "local"),
        SyncStatus.ERROR: ("Error", COLORS["sync_error"], "close"),
    }
    
    def __init__(self, parent, status: SyncStatus = SyncStatus.LOCAL_ONLY, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        
        self.status = status
        text, color, icon_name = self.STATUS_CONFIG.get(status, ("Unknown", COLORS["text_muted"], "cloud"))
        
        self.icon = ctk.CTkLabel(
            self,
            text="",
            image=IconManager.get_icon(icon_name, 14, color),
            width=14
        )
        self.icon.pack(side="left", padx=(0, 4))
        
        self.label = ctk.CTkLabel(
            self,
            text=text,
            font=ctk.CTkFont(size=11),
            text_color=color
        )
        self.label.pack(side="left")
    
    def update_status(self, status: SyncStatus):
        """Update displayed status"""
        self.status = status
        text, color, icon_name = self.STATUS_CONFIG.get(status, ("Unknown", COLORS["text_muted"], "cloud"))
        self.icon.configure(image=IconManager.get_icon(icon_name, 14, color))
        self.label.configure(text=text, text_color=color)


class NoteCard(ctk.CTkFrame):
    """Card displaying a note preview"""
    
    def __init__(self, parent, note: Note, on_click: Callable, on_pin: Callable, 
                 on_delete: Callable, on_archive: Callable, **kwargs):
        super().__init__(
            parent,
            fg_color=COLORS["bg_medium"],
            corner_radius=12,
            border_width=1,
            border_color=COLORS["border"],
            **kwargs
        )
        
        self.note = note
        self.on_click = on_click
        self.on_pin = on_pin
        self.on_delete = on_delete
        self.on_archive = on_archive
        
        self._is_hovered = False
        self._build_ui()
        self._bind_events()
    
    def _build_ui(self):
        if normalize_keep_color(self.note.color):
            color_strip = ctk.CTkFrame(
                self,
                fg_color=keep_color_hex(self.note.color),
                height=5,
                corner_radius=2
            )
            color_strip.pack(fill="x", padx=1, pady=(1, 0))

        # Main content area
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True, padx=12, pady=10)
        
        # Header with title and pin
        header = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, 6))
        
        # Pin indicator
        if self.note.pinned:
            pin_icon = ctk.CTkLabel(
                header,
                text="",
                image=IconManager.get_icon("pin", 16, COLORS["accent_yellow"]),
                width=16
            )
            pin_icon.pack(side="left", padx=(0, 6))
        
        # Title
        title_text = self.note.title if self.note.title else "Untitled"
        self.title_label = ctk.CTkLabel(
            header,
            text=title_text[:50] + ("..." if len(title_text) > 50 else ""),
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLORS["text_primary"],
            anchor="w"
        )
        self.title_label.pack(side="left", fill="x", expand=True)
        
        # Note type icon
        icon_name = "checklist" if self.note.note_type == NoteType.CHECKLIST else "note"
        type_icon = ctk.CTkLabel(
            header,
            text="",
            image=IconManager.get_icon(icon_name, 16, COLORS["text_muted"]),
            width=16
        )
        type_icon.pack(side="right")
        
        # Content preview
        if self.note.note_type == NoteType.CHECKLIST:
            preview_text = "\n".join([
                f"{'  ' * min(item.indent, 3)}{'[x]' if item.checked else '[ ]'} {item.text}"
                for item in self.note.checklist_items[:3]
            ])
            if len(self.note.checklist_items) > 3:
                preview_text += f"\n  +{len(self.note.checklist_items) - 3} more..."
        else:
            if note_uses_markdown(self.note.labels):
                preview_text = markdown_preview_text(self.note.content)
            else:
                preview_text = self.note.content[:150]
                if len(self.note.content) > 150:
                    preview_text += "..."
        
        if preview_text:
            self.preview_label = ctk.CTkLabel(
                self.content_frame,
                text=preview_text,
                font=ctk.CTkFont(size=12),
                text_color=COLORS["text_secondary"],
                anchor="nw",
                justify="left",
                wraplength=250
            )
            self.preview_label.pack(fill="x", pady=(0, 8))

        if self.note.reminder_at:
            reminder_text = f"Reminder: {format_reminder_datetime(self.note.reminder_at)}"
            if self.note.reminder_location:
                reminder_text += f" @ {self.note.reminder_location}"
            self.reminder_label = ctk.CTkLabel(
                self.content_frame,
                text=reminder_text,
                font=ctk.CTkFont(size=11),
                text_color=COLORS["accent_yellow"],
                anchor="w",
                wraplength=250
            )
            self.reminder_label.pack(fill="x", pady=(0, 8))

        if self.note.shared_with:
            shared_text = "Shared with " + ", ".join(self.note.shared_with[:2])
            if len(self.note.shared_with) > 2:
                shared_text += f" +{len(self.note.shared_with) - 2}"
            self.shared_label = ctk.CTkLabel(
                self.content_frame,
                text=shared_text,
                font=ctk.CTkFont(size=11),
                text_color=COLORS["accent_cyan"],
                anchor="w",
                wraplength=250
            )
            self.shared_label.pack(fill="x", pady=(0, 8))

        if self.note.attachments:
            image_count = sum(1 for attachment in self.note.attachments if attachment.is_image)
            other_count = len(self.note.attachments) - image_count
            parts = []
            if image_count:
                parts.append(f"{image_count} image{'s' if image_count != 1 else ''}")
            if other_count:
                parts.append(f"{other_count} file{'s' if other_count != 1 else ''}")
            self.attachments_label = ctk.CTkLabel(
                self.content_frame,
                text="Attachments: " + ", ".join(parts),
                font=ctk.CTkFont(size=11),
                text_color=COLORS["accent_blue"],
                anchor="w",
                wraplength=250
            )
            self.attachments_label.pack(fill="x", pady=(0, 8))

        if note_uses_markdown(self.note.labels):
            self.markdown_label = ctk.CTkLabel(
                self.content_frame,
                text="Markdown",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=COLORS["accent_cyan"],
                anchor="w"
            )
            self.markdown_label.pack(fill="x", pady=(0, 8))
        
        # Footer with labels and sync status
        footer = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        footer.pack(fill="x")
        
        # Labels
        if self.note.labels:
            labels_frame = ctk.CTkFrame(footer, fg_color="transparent")
            labels_frame.pack(side="left", fill="x", expand=True)
            
            for label in self.note.labels[:3]:
                label_badge = ctk.CTkLabel(
                    labels_frame,
                    text=label,
                    font=ctk.CTkFont(size=10),
                    text_color=COLORS["accent_purple"],
                    fg_color=COLORS["bg_dark"],
                    corner_radius=4,
                    padx=6,
                    pady=2
                )
                label_badge.pack(side="left", padx=(0, 4))
        
        # Sync status
        self.sync_badge = SyncStatusBadge(footer, self.note.sync_status)
        self.sync_badge.pack(side="right")
        
        # Action buttons (hidden until hover)
        self.actions_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_light"], corner_radius=8)
        
        pin_text = "Unpin" if self.note.pinned else "Pin"
        self.pin_btn = ctk.CTkButton(
            self.actions_frame,
            text=pin_text,
            font=ctk.CTkFont(size=11),
            width=50,
            height=26,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_secondary"],
            command=lambda: self.on_pin(self.note)
        )
        self.pin_btn.pack(side="left", padx=2, pady=2)
        
        self.archive_btn = ctk.CTkButton(
            self.actions_frame,
            text="Archive",
            font=ctk.CTkFont(size=11),
            width=60,
            height=26,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_secondary"],
            command=lambda: self.on_archive(self.note)
        )
        self.archive_btn.pack(side="left", padx=2, pady=2)
        
        self.delete_btn = ctk.CTkButton(
            self.actions_frame,
            text="Delete",
            font=ctk.CTkFont(size=11),
            width=50,
            height=26,
            fg_color="transparent",
            hover_color=COLORS["accent_red"],
            text_color=COLORS["accent_red"],
            command=lambda: self.on_delete(self.note)
        )
        self.delete_btn.pack(side="left", padx=2, pady=2)
    
    def _bind_events(self):
        # Click to open
        for widget in [self, self.content_frame, self.title_label]:
            widget.bind("<Button-1>", lambda e: self.on_click(self.note))
        
        if hasattr(self, 'preview_label'):
            self.preview_label.bind("<Button-1>", lambda e: self.on_click(self.note))
        
        # Hover effects
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
    
    def _on_enter(self, event):
        self._is_hovered = True
        self.configure(border_color=COLORS["accent_blue"])
        self.actions_frame.place(relx=1.0, rely=0, anchor="ne", x=-8, y=8)
    
    def _on_leave(self, event):
        self._is_hovered = False
        self.configure(border_color=COLORS["border"])
        self.actions_frame.place_forget()


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


class AdvancedFilterDialog(ctk.CTkToplevel):
    """Advanced note filter editor."""

    def __init__(self, parent, filters: Dict[str, Any], on_apply: Callable[[Dict[str, Any]], None]):
        super().__init__(parent)
        self.filters = dict(default_advanced_filters())
        self.filters.update(filters or {})
        self.on_apply = on_apply

        self.title("Advanced Filters")
        self.geometry("420x520")
        self.configure(fg_color=COLORS["bg_dark"])
        self.transient(parent)
        self.grab_set()
        self._build_ui()

    def _build_ui(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            frame,
            text="Advanced Filters",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(anchor="w", pady=(0, 16))

        self.mode_var = ctk.StringVar(value=self.filters.get("mode", "AND"))
        self.mode_menu = ctk.CTkOptionMenu(
            frame,
            values=["AND", "OR"],
            variable=self.mode_var,
            fg_color=COLORS["bg_medium"],
            button_color=COLORS["bg_hover"],
            button_hover_color=COLORS["accent_blue"],
            text_color=COLORS["text_primary"]
        )
        self.mode_menu.pack(fill="x", pady=(0, 10))

        self.label_entry = self._entry(frame, "Label", self.filters.get("label", ""))
        color_values = [""] + [name for name in KEEP_COLOR_PALETTE.keys() if name]
        self.color_var = ctk.StringVar(value=normalize_keep_color(self.filters.get("color", "")))
        self.color_menu = ctk.CTkOptionMenu(
            frame,
            values=color_values,
            variable=self.color_var,
            fg_color=COLORS["bg_medium"],
            button_color=COLORS["bg_hover"],
            button_hover_color=COLORS["accent_blue"],
            text_color=COLORS["text_primary"]
        )
        self.color_menu.pack(fill="x", pady=(0, 10))

        self.date_from_entry = self._entry(frame, "From date YYYY-MM-DD", self.filters.get("date_from", ""))
        self.date_to_entry = self._entry(frame, "To date YYYY-MM-DD", self.filters.get("date_to", ""))

        self.has_image_var = ctk.BooleanVar(value=bool(self.filters.get("has_image")))
        self.has_checklist_var = ctk.BooleanVar(value=bool(self.filters.get("has_checklist")))
        self.is_archived_var = ctk.BooleanVar(value=bool(self.filters.get("is_archived")))
        for label, variable in (
            ("Has image", self.has_image_var),
            ("Has checklist", self.has_checklist_var),
            ("Is archived", self.is_archived_var),
        ):
            ctk.CTkCheckBox(
                frame,
                text=label,
                variable=variable,
                font=ctk.CTkFont(size=13),
                text_color=COLORS["text_secondary"],
                fg_color=COLORS["accent_green"],
                hover_color=COLORS["accent_green_hover"]
            ).pack(anchor="w", pady=(0, 8))

        actions = ctk.CTkFrame(frame, fg_color="transparent")
        actions.pack(fill="x", side="bottom", pady=(18, 0))

        ctk.CTkButton(
            actions,
            text="Clear",
            height=38,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_primary"],
            command=self._clear
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            actions,
            text="Apply",
            height=38,
            fg_color=COLORS["accent_green"],
            hover_color=COLORS["accent_green_hover"],
            text_color=COLORS["bg_darkest"],
            command=self._apply
        ).pack(side="left", fill="x", expand=True)

    def _entry(self, parent, placeholder: str, value: str):
        entry = ctk.CTkEntry(
            parent,
            placeholder_text=placeholder,
            font=ctk.CTkFont(size=13),
            height=36,
            fg_color=COLORS["bg_medium"],
            border_color=COLORS["border"],
            text_color=COLORS["text_primary"]
        )
        entry.pack(fill="x", pady=(0, 10))
        if value:
            entry.insert(0, value)
        return entry

    def _current_filters(self) -> Dict[str, Any]:
        return {
            "mode": self.mode_var.get(),
            "label": self.label_entry.get().strip(),
            "color": self.color_var.get(),
            "date_from": self.date_from_entry.get().strip(),
            "date_to": self.date_to_entry.get().strip(),
            "has_image": self.has_image_var.get(),
            "has_checklist": self.has_checklist_var.get(),
            "is_archived": self.is_archived_var.get(),
        }

    def _clear(self):
        self.on_apply(default_advanced_filters())
        self.destroy()

    def _apply(self):
        self.on_apply(self._current_filters())
        self.destroy()


class ImportConflictDialog(ctk.CTkToplevel):
    """Modal import conflict resolver."""

    def __init__(self, parent, local_note: Note, imported_note: Note):
        super().__init__(parent)
        self.local_note = local_note
        self.imported_note = imported_note
        self.result = "local"

        self.title("Import Conflict")
        self.geometry("760x560")
        self.configure(fg_color=COLORS["bg_dark"])
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self.wait_window()

    def _build_ui(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(18, 10))

        ctk.CTkLabel(
            header,
            text="Import Conflict",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(anchor="w")

        ctk.CTkLabel(
            header,
            text=self.imported_note.title or "Untitled",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"],
            anchor="w"
        ).pack(anchor="w", pady=(4, 0))

        diff_box = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(size=12, family="Consolas"),
            fg_color=COLORS["bg_medium"],
            border_width=1,
            border_color=COLORS["border"],
            text_color=COLORS["text_primary"],
            corner_radius=8,
            wrap="none"
        )
        diff_box.pack(fill="both", expand=True, padx=20, pady=(0, 14))
        diff_text = note_conflict_diff(self.local_note, self.imported_note) or "Metadata differs; content is identical."
        diff_box.insert("1.0", diff_text)
        diff_box.configure(state="disabled")

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=20, pady=(0, 18))

        for label, result, color in (
            ("Keep Local", "local", COLORS["bg_light"]),
            ("Use Imported", "imported", COLORS["accent_blue"]),
            ("Merge", "merge", COLORS["accent_green"]),
        ):
            button = ctk.CTkButton(
                actions,
                text=label,
                font=ctk.CTkFont(size=13, weight="bold"),
                height=38,
                fg_color=color,
                hover_color=COLORS["bg_hover"] if result == "local" else color,
                text_color=COLORS["text_primary"] if result == "local" else COLORS["bg_darkest"],
                command=lambda choice=result: self._finish(choice)
            )
            button.pack(side="left", fill="x", expand=True, padx=(0, 8))

    def _finish(self, result: str):
        self.result = result
        self.destroy()


class TakeoutInstructionsDialog(ctk.CTkToplevel):
    """Dialog showing Google Takeout export instructions"""
    
    def __init__(self, parent):
        super().__init__(parent)
        
        self.title("Import via Google Takeout")
        self.geometry("550x500")
        self.configure(fg_color=COLORS["bg_dark"])
        
        self.transient(parent)
        self.grab_set()
        
        self._build_ui()
    
    def _build_ui(self):
        # Header
        header = ctk.CTkLabel(
            self,
            text="📦 Import via Google Takeout",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["text_primary"]
        )
        header.pack(pady=(20, 10))
        
        subtitle = ctk.CTkLabel(
            self,
            text="The most reliable way to get your Google Keep notes",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"]
        )
        subtitle.pack(pady=(0, 20))
        
        # Instructions frame
        instructions_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_medium"], corner_radius=12)
        instructions_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        steps = [
            ("1", "Go to Google Takeout", "takeout.google.com"),
            ("2", "Click 'Deselect all'", "Then scroll down and select only 'Keep'"),
            ("3", "Click 'Next step'", "Choose 'Export once' and '.zip' format"),
            ("4", "Click 'Create export'", "Wait for Google to prepare your data"),
            ("5", "Download the ZIP", "Check your email for the download link"),
            ("6", "Extract the ZIP", "Find the 'Keep' folder inside"),
            ("7", "Import JSON files", "Use Settings → Import Notes in this app"),
        ]
        
        for num, title, desc in steps:
            step_frame = ctk.CTkFrame(instructions_frame, fg_color="transparent")
            step_frame.pack(fill="x", padx=16, pady=8)
            
            num_label = ctk.CTkLabel(
                step_frame,
                text=num,
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color=COLORS["accent_green"],
                width=30
            )
            num_label.pack(side="left")
            
            text_frame = ctk.CTkFrame(step_frame, fg_color="transparent")
            text_frame.pack(side="left", fill="x", expand=True, padx=(8, 0))
            
            title_label = ctk.CTkLabel(
                text_frame,
                text=title,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=COLORS["text_primary"],
                anchor="w"
            )
            title_label.pack(anchor="w")
            
            desc_label = ctk.CTkLabel(
                text_frame,
                text=desc,
                font=ctk.CTkFont(size=11),
                text_color=COLORS["text_muted"],
                anchor="w"
            )
            desc_label.pack(anchor="w")
        
        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(0, 20))
        
        open_takeout_btn = ctk.CTkButton(
            btn_frame,
            text="Open Google Takeout",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=40,
            fg_color=COLORS["accent_blue"],
            hover_color=COLORS["accent_blue_hover"],
            text_color=COLORS["bg_darkest"],
            command=lambda: webbrowser.open("https://takeout.google.com")
        )
        open_takeout_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))
        
        close_btn = ctk.CTkButton(
            btn_frame,
            text="Close",
            font=ctk.CTkFont(size=13),
            height=40,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_secondary"],
            border_width=1,
            border_color=COLORS["border"],
            command=self.destroy
        )
        close_btn.pack(side="left", fill="x", expand=True)


class TokenGeneratorDialog(ctk.CTkToplevel):
    """Dialog to generate Google Master Token"""
    
    def __init__(self, parent, prefill_email: str = ""):
        super().__init__(parent)
        
        self.title("Get Master Token")
        self.geometry("500x550")
        self.configure(fg_color=COLORS["bg_dark"])
        
        self.transient(parent)
        self.grab_set()
        
        self.parent_dialog = parent
        self._build_ui(prefill_email)
    
    def _build_ui(self, prefill_email: str):
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=20)
        
        title = ctk.CTkLabel(
            header,
            text="🔑 Master Token Generator",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["text_primary"]
        )
        title.pack(anchor="w")
        
        # Instructions
        instructions = ctk.CTkLabel(
            self,
            text="Google requires a Master Token for Keep sync.\n"
                 "This will authenticate with Google and generate your token.",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"],
            justify="left"
        )
        instructions.pack(anchor="w", padx=20, pady=(0, 16))
        
        # Form frame
        form_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_medium"], corner_radius=12)
        form_frame.pack(fill="x", padx=20, pady=(0, 16))
        
        # Email
        ctk.CTkLabel(
            form_frame,
            text="Google Email",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w", padx=16, pady=(16, 4))
        
        self.email_entry = ctk.CTkEntry(
            form_frame,
            placeholder_text="your.email@gmail.com",
            font=ctk.CTkFont(size=13),
            height=40,
            fg_color=COLORS["bg_dark"],
            border_color=COLORS["border"]
        )
        self.email_entry.pack(fill="x", padx=16)
        if prefill_email:
            self.email_entry.insert(0, prefill_email)
        
        # Password
        ctk.CTkLabel(
            form_frame,
            text="Password (or App Password if 2FA enabled)",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w", padx=16, pady=(12, 4))
        
        self.password_entry = ctk.CTkEntry(
            form_frame,
            placeholder_text="Your password",
            font=ctk.CTkFont(size=13),
            height=40,
            fg_color=COLORS["bg_dark"],
            border_color=COLORS["border"],
            show="•"
        )
        self.password_entry.pack(fill="x", padx=16)
        
        # 2FA note
        note = ctk.CTkLabel(
            form_frame,
            text="⚠️ If you have 2FA enabled, create an App Password at:\n"
                 "   myaccount.google.com/apppasswords",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["accent_yellow"],
            justify="left"
        )
        note.pack(anchor="w", padx=16, pady=(8, 16))
        
        # Generate button
        self.generate_btn = ctk.CTkButton(
            self,
            text="Generate Master Token",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=44,
            fg_color=COLORS["accent_green"],
            hover_color=COLORS["accent_green_hover"],
            text_color=COLORS["bg_darkest"],
            command=self._generate_token
        )
        self.generate_btn.pack(fill="x", padx=20, pady=(0, 16))
        
        # Result frame (initially hidden)
        self.result_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_medium"], corner_radius=12)
        
        ctk.CTkLabel(
            self.result_frame,
            text="✓ Master Token Generated!",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLORS["accent_green"]
        ).pack(anchor="w", padx=16, pady=(16, 8))
        
        self.token_display = ctk.CTkTextbox(
            self.result_frame,
            height=80,
            font=ctk.CTkFont(size=11, family="Consolas"),
            fg_color=COLORS["bg_dark"],
            text_color=COLORS["text_primary"]
        )
        self.token_display.pack(fill="x", padx=16, pady=(0, 8))
        
        btn_frame = ctk.CTkFrame(self.result_frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=(0, 16))
        
        self.copy_btn = ctk.CTkButton(
            btn_frame,
            text="Copy & Use Token",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=36,
            fg_color=COLORS["accent_blue"],
            hover_color=COLORS["accent_blue_hover"],
            text_color=COLORS["bg_darkest"],
            command=self._copy_and_use
        )
        self.copy_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))
        
        close_btn = ctk.CTkButton(
            btn_frame,
            text="Close",
            font=ctk.CTkFont(size=13),
            height=36,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_secondary"],
            border_width=1,
            border_color=COLORS["border"],
            command=self.destroy
        )
        close_btn.pack(side="left", fill="x", expand=True)
        
        # Status label
        self.status_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_muted"]
        )
        self.status_label.pack(pady=(8, 20))
        
        self.generated_token = None
    
    def _generate_token(self):
        """Generate the master token"""
        email = self.email_entry.get().strip()
        password = self.password_entry.get()
        
        if not email or not password:
            messagebox.showerror("Error", "Please enter both email and password")
            return
        
        self.generate_btn.configure(state="disabled", text="Generating...")
        self.status_label.configure(text="Checking gpsoauth...", text_color=COLORS["text_muted"])
        self.update()
        
        # Run in thread to not block UI
        def generate():
            try:
                try:
                    import gpsoauth
                except ImportError:
                    self.after(0, lambda: self._show_error(
                        "gpsoauth is not installed. Run: python -m pip install -r requirements.txt"
                    ))
                    return
                
                self.after(0, lambda: self.status_label.configure(
                    text="Authenticating with Google...", text_color=COLORS["text_muted"]))
                
                # Generate token
                android_id = "0123456789abcdef"
                master_response = gpsoauth.perform_master_login(email, password, android_id)
                
                if "Token" not in master_response:
                    error = master_response.get("Error", "Unknown error")
                    self.after(0, lambda: self._show_error(error))
                    return
                
                token = master_response["Token"]
                self.after(0, lambda: self._show_success(token))
                
            except Exception as e:
                self.after(0, lambda: self._show_error(str(e)))
        
        threading.Thread(target=generate, daemon=True).start()
    
    def _show_error(self, error: str):
        """Show error message"""
        self.generate_btn.configure(state="normal", text="Generate Master Token")
        
        if "BadAuthentication" in error:
            self.status_label.configure(
                text="Authentication failed. Check password or use App Password for 2FA.",
                text_color=COLORS["accent_red"]
            )
            messagebox.showerror("Authentication Failed",
                "Google rejected the authentication.\n\n"
                "If you have 2FA enabled:\n"
                "1. Go to myaccount.google.com/apppasswords\n"
                "2. Create an App Password\n"
                "3. Use that instead of your regular password\n\n"
                "Also check your email for security alerts from Google.")
        else:
            self.status_label.configure(text=f"Error: {error}", text_color=COLORS["accent_red"])
    
    def _show_success(self, token: str):
        """Show success and token"""
        self.generated_token = token
        self.generate_btn.configure(state="normal", text="Generate Master Token")
        self.status_label.configure(text="", text_color=COLORS["text_muted"])
        
        self.result_frame.pack(fill="x", padx=20, pady=(0, 16))
        self.token_display.delete("1.0", "end")
        self.token_display.insert("1.0", token)
    
    def _copy_and_use(self):
        """Copy token to clipboard and fill in parent dialog"""
        if self.generated_token:
            self.clipboard_clear()
            self.clipboard_append(self.generated_token)
            
            # Fill in the parent dialog's token entry
            if hasattr(self.parent_dialog, 'token_entry'):
                self.parent_dialog.token_entry.delete(0, "end")
                self.parent_dialog.token_entry.insert(0, self.generated_token)
            
            messagebox.showinfo("Token Copied", 
                "Token copied to clipboard and filled in.\n"
                "Click 'Connect' to authenticate.")
            self.destroy()


class SettingsDialog(ctk.CTkToplevel):
    """Settings dialog for Google Keep connection and app settings"""
    
    def __init__(self, parent, db: DatabaseManager, sync_engine: KeepSyncEngine, 
                 cloud_sync: 'CloudSyncManager' = None):
        super().__init__(parent)
        
        self.app = parent
        self.db = db
        self.sync_engine = sync_engine
        self.cloud_sync = cloud_sync
        
        self.title("Settings")
        self.geometry("550x700")
        self.configure(fg_color=COLORS["bg_dark"])
        
        # Center on parent
        self.transient(parent)
        self.grab_set()
        
        self._build_ui()
        self._load_settings()
    
    def _build_ui(self):
        # Create tabview for different settings sections
        self.tabview = ctk.CTkTabview(self, fg_color=COLORS["bg_dark"])
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Add tabs
        self.tabview.add("☁️ Cloud Sync")
        self.tabview.add("🔄 Google Keep")
        self.tabview.add("📦 Data")
        
        # Build each tab
        self._build_cloud_sync_tab()
        self._build_keep_tab()
        self._build_data_tab()
        
        # Close button
        close_btn = ctk.CTkButton(
            self,
            text="Close",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=44,
            fg_color=COLORS["accent_blue"],
            hover_color=COLORS["accent_blue_hover"],
            text_color=COLORS["bg_darkest"],
            command=self.destroy
        )
        close_btn.pack(fill="x", padx=20, pady=(0, 15))
    
    def _build_cloud_sync_tab(self):
        """Build the Cloud Sync settings tab"""
        tab = self.tabview.tab("☁️ Cloud Sync")
        
        # Scroll frame
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        
        # Header
        ctk.CTkLabel(
            scroll,
            text="Cloud Backup",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(anchor="w", pady=(10, 5))
        
        ctk.CTkLabel(
            scroll,
            text="Sync your notes to Google Drive or GitHub for backup",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w", pady=(0, 15))
        
        # Current status
        status_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_medium"], corner_radius=10)
        status_frame.pack(fill="x", pady=(0, 15))
        
        self.cloud_status_label = ctk.CTkLabel(
            status_frame,
            text="Not connected to any cloud service",
            font=ctk.CTkFont(size=13),
            text_color=COLORS["text_muted"]
        )
        self.cloud_status_label.pack(pady=15)
        
        # === GitHub Section ===
        github_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_medium"], corner_radius=12)
        github_frame.pack(fill="x", pady=(0, 15))
        
        github_header = ctk.CTkFrame(github_frame, fg_color="transparent")
        github_header.pack(fill="x", padx=16, pady=(16, 8))
        
        ctk.CTkLabel(
            github_header,
            text="🐙 GitHub Sync",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(side="left")
        
        ctk.CTkLabel(
            github_header,
            text="Recommended",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["accent_green"]
        ).pack(side="right")
        
        ctk.CTkLabel(
            github_frame,
            text="Store notes in a private GitHub repository with version history",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_muted"]
        ).pack(anchor="w", padx=16, pady=(0, 10))
        
        # GitHub Token
        ctk.CTkLabel(
            github_frame,
            text="Personal Access Token",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w", padx=16, pady=(0, 4))
        
        self.github_token_entry = ctk.CTkEntry(
            github_frame,
            placeholder_text="Leave blank to reuse saved keyring token",
            font=ctk.CTkFont(size=12),
            height=38,
            fg_color=COLORS["bg_dark"],
            border_color=COLORS["border"],
            show="•"
        )
        self.github_token_entry.pack(fill="x", padx=16)
        
        # GitHub Repo
        ctk.CTkLabel(
            github_frame,
            text="Repository Name",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w", padx=16, pady=(10, 4))
        
        self.github_repo_entry = ctk.CTkEntry(
            github_frame,
            placeholder_text="my-notes-backup",
            font=ctk.CTkFont(size=12),
            height=38,
            fg_color=COLORS["bg_dark"],
            border_color=COLORS["border"]
        )
        self.github_repo_entry.pack(fill="x", padx=16)
        
        # Help link
        help_btn = ctk.CTkButton(
            github_frame,
            text="📖 How to get a GitHub token",
            font=ctk.CTkFont(size=11),
            height=28,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["accent_blue"],
            anchor="w",
            command=lambda: webbrowser.open("https://github.com/settings/tokens/new?description=KeepSync%20Notes&scopes=repo")
        )
        help_btn.pack(anchor="w", padx=12, pady=(4, 0))
        
        # Connect button
        self.github_connect_btn = ctk.CTkButton(
            github_frame,
            text="Connect to GitHub",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=40,
            fg_color=COLORS["accent_green"],
            hover_color=COLORS["accent_green_hover"],
            text_color=COLORS["bg_darkest"],
            command=self._connect_github
        )
        self.github_connect_btn.pack(fill="x", padx=16, pady=(10, 16))
        
        # === Google Drive Section ===
        gdrive_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_medium"], corner_radius=12)
        gdrive_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(
            gdrive_frame,
            text="📁 Google Drive Sync",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(anchor="w", padx=16, pady=(16, 8))
        
        ctk.CTkLabel(
            gdrive_frame,
            text="Store notes in a Google Drive folder\nRequires OAuth setup (more complex)",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_muted"],
            justify="left"
        ).pack(anchor="w", padx=16, pady=(0, 10))
        
        self.gdrive_connect_btn = ctk.CTkButton(
            gdrive_frame,
            text="Connect to Google Drive",
            font=ctk.CTkFont(size=13),
            height=40,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_primary"],
            command=self._connect_gdrive
        )
        self.gdrive_connect_btn.pack(fill="x", padx=16, pady=(0, 8))
        
        gdrive_help = ctk.CTkButton(
            gdrive_frame,
            text="📖 Google Drive setup instructions",
            font=ctk.CTkFont(size=11),
            height=28,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["accent_blue"],
            anchor="w",
            command=self._show_gdrive_instructions
        )
        gdrive_help.pack(anchor="w", padx=12, pady=(0, 16))
        
        # === Auto-sync Settings ===
        autosync_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_medium"], corner_radius=12)
        autosync_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(
            autosync_frame,
            text="⏱️ Auto-Sync Settings",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(anchor="w", padx=16, pady=(16, 8))
        
        self.cloud_autosync_var = ctk.BooleanVar(value=True)
        autosync_check = ctk.CTkCheckBox(
            autosync_frame,
            text="Enable automatic cloud sync",
            variable=self.cloud_autosync_var,
            font=ctk.CTkFont(size=13),
            text_color=COLORS["text_secondary"],
            fg_color=COLORS["accent_green"],
            hover_color=COLORS["accent_green_hover"],
            command=self._save_autosync_settings
        )
        autosync_check.pack(anchor="w", padx=16, pady=(0, 8))
        
        interval_frame = ctk.CTkFrame(autosync_frame, fg_color="transparent")
        interval_frame.pack(fill="x", padx=16, pady=(0, 16))
        
        ctk.CTkLabel(
            interval_frame,
            text="Sync interval:",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"]
        ).pack(side="left")
        
        self.cloud_sync_interval = ctk.CTkEntry(
            interval_frame,
            width=60,
            height=32,
            font=ctk.CTkFont(size=13),
            fg_color=COLORS["bg_dark"],
            border_color=COLORS["border"]
        )
        self.cloud_sync_interval.pack(side="left", padx=(8, 4))
        self.cloud_sync_interval.insert(0, "15")
        
        ctk.CTkLabel(
            interval_frame,
            text="minutes",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"]
        ).pack(side="left")
        
        # Disconnect button
        self.cloud_disconnect_btn = ctk.CTkButton(
            scroll,
            text="Disconnect from Cloud",
            font=ctk.CTkFont(size=13),
            height=40,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["accent_red"],
            border_width=1,
            border_color=COLORS["accent_red"],
            command=self._disconnect_cloud
        )
        # Initially hidden, shown when connected
    
    def _build_keep_tab(self):
        """Build the Google Keep import tab"""
        tab = self.tabview.tab("🔄 Google Keep")
        
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        
        # Header
        ctk.CTkLabel(
            scroll,
            text="Import from Google Keep",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(anchor="w", pady=(10, 5))
        
        ctk.CTkLabel(
            scroll,
            text="One-time import to migrate your notes from Google Keep",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w", pady=(0, 15))
        
        # Takeout import (primary)
        takeout_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_medium"], corner_radius=12)
        takeout_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(
            takeout_frame,
            text="📦 Google Takeout Import",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(anchor="w", padx=16, pady=(16, 4))
        
        ctk.CTkLabel(
            takeout_frame,
            text="Recommended",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["accent_green"]
        ).pack(anchor="w", padx=16, pady=(0, 8))
        
        takeout_btn = ctk.CTkButton(
            takeout_frame,
            text="Import from Takeout Folder",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=40,
            fg_color=COLORS["accent_green"],
            hover_color=COLORS["accent_green_hover"],
            text_color=COLORS["bg_darkest"],
            command=self._import_takeout_folder
        )
        takeout_btn.pack(fill="x", padx=16, pady=(0, 8))
        
        takeout_help = ctk.CTkButton(
            takeout_frame,
            text="📖 How to export from Google Takeout",
            font=ctk.CTkFont(size=11),
            height=28,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["accent_blue"],
            anchor="w",
            command=lambda: TakeoutInstructionsDialog(self)
        )
        takeout_help.pack(anchor="w", padx=12, pady=(0, 16))
        
        # Browser import (alternative)
        browser_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_medium"], corner_radius=12)
        browser_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(
            browser_frame,
            text="🌐 Browser Session Import",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(anchor="w", padx=16, pady=(16, 8))
        
        ctk.CTkLabel(
            browser_frame,
            text="Extract notes using your browser's Google login\n(Close browser before using)",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_muted"],
            justify="left"
        ).pack(anchor="w", padx=16, pady=(0, 10))
        
        browser_btn = ctk.CTkButton(
            browser_frame,
            text="Import from Browser",
            font=ctk.CTkFont(size=13),
            height=40,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_primary"],
            command=self._import_from_browser
        )
        browser_btn.pack(fill="x", padx=16, pady=(0, 16))
        
        # Legacy gkeepapi (hidden, mostly broken)
        legacy_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_medium"], corner_radius=12)
        legacy_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(
            legacy_frame,
            text="🔑 API Token Method",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLORS["text_muted"]
        ).pack(anchor="w", padx=16, pady=(16, 4))
        
        ctk.CTkLabel(
            legacy_frame,
            text="⚠️ Often blocked by Google - use Takeout instead",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["accent_yellow"]
        ).pack(anchor="w", padx=16, pady=(0, 16))
    
    def _build_data_tab(self):
        """Build the Data Management tab"""
        tab = self.tabview.tab("📦 Data")
        
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        
        # Header
        ctk.CTkLabel(
            scroll,
            text="Data Management",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(anchor="w", pady=(10, 15))
        
        # Export/Import
        data_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_medium"], corner_radius=12)
        data_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(
            data_frame,
            text="Export & Import",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(anchor="w", padx=16, pady=(16, 10))
        
        btn_frame = ctk.CTkFrame(data_frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=(0, 16))
        
        export_btn = ctk.CTkButton(
            btn_frame,
            text="Export Notes",
            font=ctk.CTkFont(size=13),
            height=40,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_primary"],
            command=self._export_notes
        )
        export_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))
        
        import_btn = ctk.CTkButton(
            btn_frame,
            text="Import JSON",
            font=ctk.CTkFont(size=13),
            height=40,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_primary"],
            command=self._import_notes
        )
        import_btn.pack(side="left", fill="x", expand=True)

        source_frame = ctk.CTkFrame(data_frame, fg_color="transparent")
        source_frame.pack(fill="x", padx=16, pady=(0, 16))

        self.external_source_var = ctk.StringVar(value="Evernote / Apple Notes ENEX")
        source_menu = ctk.CTkOptionMenu(
            source_frame,
            values=[
                "Evernote / Apple Notes ENEX",
                "Standard Notes ZIP",
                "Obsidian Vault",
                "Bear ZIP",
                "Simplenote Export",
                "OneNote HTML Folder",
            ],
            variable=self.external_source_var,
            font=ctk.CTkFont(size=12),
            fg_color=COLORS["bg_light"],
            button_color=COLORS["bg_hover"],
            button_hover_color=COLORS["accent_blue"],
            dropdown_fg_color=COLORS["bg_medium"],
            dropdown_hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_primary"],
            height=36
        )
        source_menu.pack(side="left", fill="x", expand=True, padx=(0, 8))

        external_btn = ctk.CTkButton(
            source_frame,
            text="Import Source",
            font=ctk.CTkFont(size=13),
            height=36,
            fg_color=COLORS["accent_blue"],
            hover_color=COLORS["accent_blue_hover"],
            text_color=COLORS["bg_darkest"],
            command=self._import_external_source
        )
        external_btn.pack(side="left")

        watcher_frame = ctk.CTkFrame(data_frame, fg_color=COLORS["bg_dark"], corner_radius=8)
        watcher_frame.pack(fill="x", padx=16, pady=(0, 16))

        self.takeout_watch_enabled_var = ctk.BooleanVar(value=False)
        watcher_check = ctk.CTkCheckBox(
            watcher_frame,
            text="Auto-import Google Takeout drops",
            variable=self.takeout_watch_enabled_var,
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"],
            fg_color=COLORS["accent_green"],
            hover_color=COLORS["accent_green_hover"],
            command=self._save_takeout_watch_settings
        )
        watcher_check.pack(anchor="w", padx=12, pady=(12, 8))

        watcher_inputs = ctk.CTkFrame(watcher_frame, fg_color="transparent")
        watcher_inputs.pack(fill="x", padx=12, pady=(0, 12))

        self.takeout_watch_entry = ctk.CTkEntry(
            watcher_inputs,
            placeholder_text="Watched folder",
            font=ctk.CTkFont(size=12),
            height=32,
            fg_color=COLORS["bg_medium"],
            border_color=COLORS["border"]
        )
        self.takeout_watch_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.takeout_watch_entry.bind("<FocusOut>", lambda _event: self._save_takeout_watch_settings())

        browse_watch_btn = ctk.CTkButton(
            watcher_inputs,
            text="Browse",
            font=ctk.CTkFont(size=12),
            width=74,
            height=32,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_primary"],
            command=self._select_takeout_watch_folder
        )
        browse_watch_btn.pack(side="left")
        
        # Database info
        info_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_medium"], corner_radius=12)
        info_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(
            info_frame,
            text="Database Location",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(anchor="w", padx=16, pady=(16, 8))
        
        db_path = str(Path.home() / ".keepsync_notes" / "notes.db")
        ctk.CTkLabel(
            info_frame,
            text=db_path,
            font=ctk.CTkFont(size=11, family="Consolas"),
            text_color=COLORS["text_muted"]
        ).pack(anchor="w", padx=16, pady=(0, 16))
        
        # gkeepapi status
        if not GKEEPAPI_AVAILABLE:
            warning_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_medium"], corner_radius=12)
            warning_frame.pack(fill="x", pady=(0, 15))
            
            ctk.CTkLabel(
                warning_frame,
                text="ℹ️ gkeepapi not installed",
                font=ctk.CTkFont(size=14),
                text_color=COLORS["text_muted"]
            ).pack(anchor="w", padx=16, pady=(12, 4))
            
            ctk.CTkLabel(
                warning_frame,
                text="Google Keep API sync disabled. Use Takeout import instead.",
                font=ctk.CTkFont(size=11),
                text_color=COLORS["text_muted"]
            ).pack(anchor="w", padx=16, pady=(0, 12))
    
    def _load_settings(self):
        """Load saved settings"""
        # Load cloud sync settings
        auto_sync = self.db.get_setting("cloud_auto_sync", True)
        self.cloud_autosync_var.set(auto_sync)
        
        interval = self.db.get_setting("cloud_sync_interval", 15)
        self.cloud_sync_interval.delete(0, "end")
        self.cloud_sync_interval.insert(0, str(interval))
        
        # Load GitHub repo name if saved
        github_repo = self.db.get_setting("github_repo", "")
        if github_repo:
            self.github_repo_entry.insert(0, github_repo)

        self.takeout_watch_enabled_var.set(self.db.get_setting("takeout_watch_enabled", False))
        self.takeout_watch_entry.delete(0, "end")
        self.takeout_watch_entry.insert(0, self.db.get_setting("takeout_watch_folder", ""))
        
        # Update cloud status
        self._update_cloud_status()
    
    def _update_cloud_status(self):
        """Update the cloud connection status display"""
        if self.cloud_sync and self.cloud_sync.is_connected():
            status = self.cloud_sync.get_status()
            provider = status.get("provider", "Unknown")
            last_sync = status.get("last_sync")
            
            if last_sync:
                sync_time = datetime.fromisoformat(last_sync).strftime("%Y-%m-%d %H:%M")
                status_text = f"✓ Connected to {provider}\nLast sync: {sync_time}"
            else:
                status_text = f"✓ Connected to {provider}"
            
            self.cloud_status_label.configure(
                text=status_text,
                text_color=COLORS["accent_green"]
            )
            self.cloud_disconnect_btn.pack(fill="x", pady=(0, 15))
        else:
            self.cloud_status_label.configure(
                text="Not connected to any cloud service",
                text_color=COLORS["text_muted"]
            )
    
    def _connect_github(self):
        """Connect to GitHub"""
        if not self.cloud_sync:
            messagebox.showerror("Error", "Cloud sync not available")
            return
        
        token = self.github_token_entry.get().strip()
        repo = self.github_repo_entry.get().strip()
        
        if not repo:
            repo = "keepsync-notes-backup"
            self.github_repo_entry.insert(0, repo)
        
        self.github_connect_btn.configure(state="disabled", text="Connecting...")
        self.update()
        
        success, message = self.cloud_sync.connect_github(token, repo)
        
        self.github_connect_btn.configure(state="normal", text="Connect to GitHub")
        
        if success:
            self._update_cloud_status()
            self._save_autosync_settings()
            messagebox.showinfo("Success", f"{message}\n\nYour notes will now sync to GitHub.")
            
            # Do initial sync
            if messagebox.askyesno("Initial Sync", "Would you like to sync your notes now?"):
                self.cloud_sync.sync()
        else:
            messagebox.showerror("Connection Failed", message)
    
    def _connect_gdrive(self):
        """Connect to Google Drive"""
        if not self.cloud_sync:
            messagebox.showerror("Error", "Cloud sync not available")
            return
        
        self.gdrive_connect_btn.configure(state="disabled", text="Connecting...")
        self.update()
        
        success, message = self.cloud_sync.connect_gdrive()
        
        self.gdrive_connect_btn.configure(state="normal", text="Connect to Google Drive")
        
        if success:
            self._update_cloud_status()
            self._save_autosync_settings()
            messagebox.showinfo("Success", message)
            
            if messagebox.askyesno("Initial Sync", "Would you like to sync your notes now?"):
                self.cloud_sync.sync()
        else:
            messagebox.showerror("Connection Failed", message)
    
    def _disconnect_cloud(self):
        """Disconnect from cloud provider"""
        if not self.cloud_sync:
            return
        
        if messagebox.askyesno("Confirm", "Disconnect from cloud sync?\n\nYour notes will remain stored locally."):
            self.cloud_sync.disconnect()
            self._update_cloud_status()
    
    def _save_autosync_settings(self):
        """Save auto-sync settings"""
        self.db.set_setting("cloud_auto_sync", self.cloud_autosync_var.get())
        try:
            interval = int(self.cloud_sync_interval.get())
            self.db.set_setting("cloud_sync_interval", interval)
        except ValueError:
            pass

    def _select_takeout_watch_folder(self):
        folder = filedialog.askdirectory(title="Select Takeout watch folder")
        if not folder:
            return
        self.takeout_watch_entry.delete(0, "end")
        self.takeout_watch_entry.insert(0, folder)
        self._save_takeout_watch_settings()

    def _save_takeout_watch_settings(self):
        self.db.set_setting("takeout_watch_enabled", self.takeout_watch_enabled_var.get())
        self.db.set_setting("takeout_watch_folder", self.takeout_watch_entry.get().strip())
        if hasattr(self.app, "_schedule_takeout_watch_check"):
            if self.app._takeout_watch_after_id:
                self.app.after_cancel(self.app._takeout_watch_after_id)
                self.app._takeout_watch_after_id = None
            self.app._schedule_takeout_watch_check(delay_ms=1000)
    
    def _show_gdrive_instructions(self):
        """Show Google Drive setup instructions"""
        instructions = """Google Drive Setup Instructions

1. Go to console.cloud.google.com

2. Create a new project (or select existing)

3. Enable the Google Drive API:
   - Go to "APIs & Services" → "Library"
   - Search for "Google Drive API"
   - Click "Enable"

4. Create OAuth credentials:
   - Go to "APIs & Services" → "Credentials"
   - Click "Create Credentials" → "OAuth client ID"
   - Select "Desktop app"
   - Download the JSON file

5. Save the JSON file as:
   ~/.keepsync_notes/gdrive_credentials.json

6. Click "Connect to Google Drive" again

The first time you connect, a browser window will open
for you to authorize the app."""
        
        messagebox.showinfo("Google Drive Setup", instructions)
    
    def _connect_keep(self):
        """Connect to Google Keep (legacy)"""
        messagebox.showinfo(
            "Google Keep Sync",
            "Google Keep API sync is no longer reliable.\n\n"
            "Please use the Takeout import method instead:\n"
            "1. Go to takeout.google.com\n"
            "2. Export your Keep notes\n"
            "3. Use 'Import from Takeout Folder'"
        )
    
    def _disconnect_keep(self):
        """Disconnect from Google Keep"""
        if messagebox.askyesno("Confirm", "Disconnect from Google Keep?"):
            self.sync_engine.logout()
    
    def _get_master_token(self):
        """Open master token generator"""
        TokenGeneratorDialog(self, "")

    def _save_imported_note(self, note: Note) -> bool:
        return self._save_imported_note_status(note) in {"imported", "conflict_copy"}

    def _save_imported_note_status(self, note: Note) -> str:
        if not note:
            return "failed"
        conflict = self.db.find_import_conflict(note)
        if conflict:
            if notes_equivalent(conflict, note):
                return "skipped"
            action = ImportConflictDialog(self, conflict, note).result
            if action == "local":
                return "skipped"
            if action == "imported":
                note.id = conflict.id
                note.created_at = conflict.created_at
                note.keep_id = conflict.keep_id
                return self.db.save_imported_note(note, conflict_policy="replace")
            if action == "merge":
                return self.db.save_imported_note(note, conflict_policy="merge")
        return self.db.save_imported_note(note, conflict_policy="copy")

    def _show_import_summary(self, source: str, statuses: List[str]):
        imported = sum(1 for status in statuses if status in {"imported", "conflict_copy"})
        skipped = statuses.count("skipped")
        failed = statuses.count("failed")
        lines = [f"Imported {imported} notes from {source}."]
        if skipped:
            lines.append(f"Skipped unchanged/local-kept notes: {skipped}")
        if failed:
            lines.append(f"Failed notes: {failed}")
        messagebox.showinfo("Import Complete", "\n".join(lines))
    
    def _export_notes(self):
        """Export notes to JSON"""
        filepath = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if filepath:
            notes = self.db.get_all_notes(include_trashed=True, include_archived=True)
            data = {
                "version": DB_VERSION,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "notes": [note.to_dict() for note in notes],
                "labels": [label.to_dict() for label in self.db.get_all_labels()]
            }
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2)
            messagebox.showinfo("Export Complete", f"Exported {len(notes)} notes to {filepath}")

    def _import_external_source(self):
        """Import notes from another note app export."""
        source_type = self.external_source_var.get()
        folder_sources = {"Obsidian Vault", "OneNote HTML Folder"}

        if source_type in folder_sources:
            selected = filedialog.askdirectory(title=f"Select {source_type}")
        else:
            selected = filedialog.askopenfilename(
                title=f"Select {source_type}",
                filetypes=[
                    ("Supported exports", "*.enex *.zip *.json"),
                    ("ENEX files", "*.enex"),
                    ("ZIP files", "*.zip"),
                    ("JSON files", "*.json"),
                    ("All files", "*.*"),
                ],
            )

        if not selected:
            return

        try:
            importer = MultiSourceImporter(self.db)
            notes = importer.import_external(source_type, Path(selected))
            statuses = [self._save_imported_note_status(note) for note in notes]
            self._show_import_summary(source_type, statuses)
        except Exception as e:
            messagebox.showerror("Import Failed", str(e))
    
    def _import_notes(self):
        """Import notes from JSON"""
        filepath = filedialog.askopenfilename(
            filetypes=[
                ("JSON files", "*.json"),
                ("Google Takeout", "*.json"),
                ("All files", "*.*")
            ]
        )
        if filepath:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                imported = 0
                
                # Check if this is a Google Takeout export
                if isinstance(data, dict) and "textContent" in data:
                    # Single Google Keep note from Takeout
                    note = self._parse_takeout_note(data, Path(filepath).parent)
                    if self._save_imported_note(note):
                        imported = 1
                elif isinstance(data, list):
                    # Multiple notes or Takeout folder
                    for item in data:
                        if isinstance(item, dict):
                            if "textContent" in item or "title" in item:
                                # Takeout format
                                note = self._parse_takeout_note(item, Path(filepath).parent)
                            else:
                                # Our export format
                                note = Note.from_dict(item)
                            
                            if note:
                                note.id = str(uuid.uuid4())
                                note.keep_id = None
                                note.sync_status = SyncStatus.LOCAL_ONLY
                                if self._save_imported_note(note):
                                    imported += 1
                elif isinstance(data, dict) and "notes" in data:
                    # Our export format
                    for note_data in data.get("notes", []):
                        note = Note.from_dict(note_data)
                        note.id = str(uuid.uuid4())
                        note.keep_id = None
                        note.sync_status = SyncStatus.LOCAL_ONLY
                        if self._save_imported_note(note):
                            imported += 1
                
                messagebox.showinfo("Import Complete", f"Imported {imported} notes")
            except Exception as e:
                messagebox.showerror("Import Failed", str(e))
    
    def _parse_takeout_note(self, data: dict, base_path: Optional[Path] = None) -> Optional[Note]:
        """Parse a Google Takeout Keep note format"""
        try:
            note_id = str(uuid.uuid4())
            title = data.get("title", "")
            content = data.get("textContent", "")
            
            # Check for checklist
            checklist_items = []
            if "listContent" in data:
                for item in data["listContent"]:
                    checklist_items.append(ChecklistItem(
                        text=item.get("text", ""),
                        checked=item.get("isChecked", False)
                    ))
            
            # Parse labels
            labels = []
            if "labels" in data:
                labels = [l.get("name", "") for l in data["labels"] if l.get("name")]

            attachments_root = Path(self.db.db_path).parent / "attachments"
            attachments = import_takeout_attachments(data, base_path, attachments_root, note_id)
            
            return Note(
                id=note_id,
                title=title,
                content=content,
                note_type=NoteType.CHECKLIST if checklist_items else NoteType.NOTE,
                checklist_items=checklist_items,
                labels=labels,
                attachments=attachments,
                pinned=data.get("isPinned", False),
                archived=data.get("isArchived", False),
                trashed=data.get("isTrashed", False),
                color=normalize_keep_color(data.get("color", "")),
                shared_with=extract_shared_with(data),
                sync_status=SyncStatus.LOCAL_ONLY,
            )
        except Exception:
            return None
    
    def _import_from_browser(self):
        """Import notes using browser cookies"""
        # Show progress
        progress_dialog = ctk.CTkToplevel(self)
        progress_dialog.title("Importing from Browser")
        progress_dialog.geometry("400x200")
        progress_dialog.configure(fg_color=COLORS["bg_dark"])
        progress_dialog.transient(self)
        progress_dialog.grab_set()
        
        status_label = ctk.CTkLabel(
            progress_dialog,
            text="Checking browser for Google cookies...",
            font=ctk.CTkFont(size=13),
            text_color=COLORS["text_primary"]
        )
        status_label.pack(pady=(40, 20))
        
        progress_bar = ctk.CTkProgressBar(progress_dialog, mode="indeterminate")
        progress_bar.pack(fill="x", padx=40)
        progress_bar.start()
        
        def do_import():
            scraper = KeepWebScraper()
            
            # Update status
            self.after(0, lambda: status_label.configure(text="Authenticating via browser cookies..."))
            
            success, message = scraper.authenticate_from_browser()
            
            if not success:
                self.after(0, lambda: self._browser_import_failed(progress_dialog, message))
                return
            
            self.after(0, lambda: status_label.configure(text="Fetching notes from Google Keep..."))
            
            imported, errors = scraper.import_notes_to_db(self.db)
            
            self.after(0, lambda: self._browser_import_complete(progress_dialog, imported, errors, message))
        
        threading.Thread(target=do_import, daemon=True).start()
    
    def _browser_import_failed(self, dialog, message: str):
        """Handle browser import failure"""
        dialog.destroy()
        
        # Offer Google Takeout as alternative
        result = messagebox.askyesno(
            "Browser Import Failed",
            f"{message}\n\n"
            "Would you like instructions for importing via Google Takeout instead?\n"
            "(This is the most reliable method)"
        )
        
        if result:
            TakeoutInstructionsDialog(self)
    
    def _browser_import_complete(self, dialog, imported: int, errors: int, auth_message: str):
        """Handle browser import completion"""
        dialog.destroy()
        
        if imported > 0:
            messagebox.showinfo(
                "Import Complete",
                f"Successfully imported {imported} notes!\n\n"
                f"Authentication: {auth_message}\n"
                f"Errors: {errors}"
            )
        else:
            # Offer Takeout instructions
            result = messagebox.askyesno(
                "No Notes Imported",
                "Could not extract notes from Google Keep page.\n\n"
                "This can happen if Google changed their page structure.\n\n"
                "Would you like instructions for importing via Google Takeout?\n"
                "(This is the most reliable method)"
            )
            
            if result:
                TakeoutInstructionsDialog(self)
    
    def _import_takeout_folder(self):
        """Import all notes from a Google Takeout Keep folder"""
        folder = filedialog.askdirectory(
            title="Select Google Takeout Keep Folder"
        )
        
        if not folder:
            return
        
        folder_path = Path(folder)
        importer = MultiSourceImporter(self.db)
        notes = importer.import_takeout_folder(folder_path)

        if not notes:
            messagebox.showerror(
                "No Notes Found",
                "No JSON files found in the selected folder.\n\n"
                "Make sure you:\n"
                "1. Extracted the ZIP file from Google Takeout\n"
                "2. Selected the 'Keep' folder inside"
            )
            return

        statuses = [self._save_imported_note_status(note) for note in notes]
        self._show_import_summary("Google Takeout", statuses)


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
        self.data_dir = Path.home() / ".keepsync_notes"
        self.data_dir.mkdir(exist_ok=True)
        
        # Initialize database and sync engine
        self.db = DatabaseManager(str(self.data_dir / "notes.db"))
        self.sync_engine = KeepSyncEngine(self.db)
        self.sync_engine.add_sync_callback(self._on_sync_status_change)
        
        # Initialize cloud sync manager
        self.cloud_sync = CloudSyncManager(self.db)
        self.cloud_sync.add_callback(self._on_cloud_sync_status_change)
        
        # State
        self.current_filter = "all"  # all, archived, trash, label:<name>
        self.search_query = ""
        self.advanced_filters = default_advanced_filters()
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
            # Permanent delete
            if messagebox.askyesno("Delete Permanently", 
                                   "This will permanently delete the note. Continue?"):
                self.db.delete_note(note.id, permanent=True)
        else:
            self.db.delete_note(note.id)
        
        if self.selected_note and self.selected_note.id == note.id:
            self._close_editor()
        self._refresh_notes_list()
    
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
        SettingsDialog(self, self.db, self.sync_engine, self.cloud_sync)
    
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

def main():
    """Main entry point"""
    import sys
    
    # Handle command-line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] in ("--get-token", "-t", "--token"):
            get_master_token_cli()
            return
        elif sys.argv[1] in ("--help", "-h"):
            print(f"{APP_NAME} v{APP_VERSION}")
            print()
            print("Usage: python keep_sync_notes.py [OPTIONS]")
            print()
            print("Options:")
            print("  --get-token, -t  Generate a Google Master Token for Keep sync")
            print("  --help, -h       Show this help message")
            print()
            print("Run without arguments to start the application.")
            return
    
    # Set appearance mode
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    
    # Create and run app
    app = KeepSyncNotesApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()


if __name__ == "__main__":
    main()
