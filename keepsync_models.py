"""Core note data models and normalization helpers for KeepSync Notes."""

import hashlib
import json
import mimetypes
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, List, Optional


KEEP_COLOR_PALETTE = {
    "": ("Default", "#1e293b"),
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


def sanitize_filename(value: str) -> str:
    name = Path(value or "attachment").name
    return re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .") or "attachment"


def guess_attachment_mime(path: str, fallback: str = "") -> str:
    guessed, _ = mimetypes.guess_type(path or "")
    return fallback or guessed or "application/octet-stream"


class SyncStatus(Enum):
    LOCAL_ONLY = "local_only"
    SYNCED = "synced"
    PENDING_PUSH = "pending_push"
    PENDING_PULL = "pending_pull"
    CONFLICT = "conflict"
    DELETED_REMOTE = "deleted_remote"
    ERROR = "error"


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
            indent=clamp_checklist_indent(data.get("indent", 0)),
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
    keep_id: Optional[str] = None
    sync_status: SyncStatus = SyncStatus.LOCAL_ONLY
    local_modified: Optional[datetime] = None
    remote_modified: Optional[datetime] = None
    content_hash: str = ""
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
        """Generate content hash for change detection."""
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
            keep_id=data.get("keep_id"),
        )
