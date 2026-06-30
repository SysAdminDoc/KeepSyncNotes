"""SQLite storage for KeepSyncNotes notes, labels, settings, and sync logs."""

import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from keepsync_models import (
    Attachment,
    ChecklistItem,
    Label,
    Note,
    NoteType,
    SyncStatus,
    normalize_keep_color,
    normalize_people,
)
from keepsync_note_ops import merge_note_conflict, normalize_import_labels, notes_equivalent


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
            self.conn = None
