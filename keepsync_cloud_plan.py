"""Cloud sync planning primitives for Google Drive and GitHub providers."""

import hashlib
import json
import uuid
from typing import Any, Dict, List, Optional

from keepsync_models import Note, SyncStatus


def note_data_hash(data: Dict[str, Any]) -> str:
    try:
        note = Note.from_dict(data)
        return note.content_hash
    except Exception:
        comparable = {
            key: value
            for key, value in data.items()
            if key not in {"local_modified", "remote_modified", "sync_status"}
        }
        return hashlib.md5(json.dumps(comparable, sort_keys=True, default=str).encode()).hexdigest()


def build_cloud_sync_plan(
    local_notes: List[Note],
    remote_notes: Dict[str, Dict[str, Any]],
    base_versions: Dict[str, str],
) -> Dict[str, List[Any]]:
    plan = {
        "download_creates": [],
        "download_updates": [],
        "upload_creates": [],
        "upload_updates": [],
        "conflicts": [],
        "delete_local": [],
        "delete_remote": [],
    }
    local_by_id = {note.id: note for note in local_notes}
    for note_id in sorted(set(local_by_id) | set(remote_notes)):
        local_note = local_by_id.get(note_id)
        remote_data = remote_notes.get(note_id)
        base_hash = base_versions.get(note_id)
        local_hash = local_note.content_hash if local_note else None
        remote_hash = note_data_hash(remote_data) if remote_data else None

        if local_note and not remote_data:
            if base_hash and local_hash == base_hash:
                plan["delete_local"].append(local_note)
            else:
                plan["upload_creates"].append(local_note)
            continue
        if remote_data and not local_note:
            if base_hash and remote_hash == base_hash:
                plan["delete_remote"].append(remote_data)
            else:
                plan["download_creates"].append(remote_data)
            continue
        if not local_note or not remote_data or local_hash == remote_hash:
            continue

        local_changed = bool(local_hash and local_hash != base_hash)
        remote_changed = bool(remote_hash and remote_hash != base_hash)
        if not base_hash and local_hash != remote_hash:
            plan["conflicts"].append((local_note, remote_data))
        elif base_hash and local_changed and remote_changed:
            plan["conflicts"].append((local_note, remote_data))
        elif remote_changed and not local_changed:
            plan["download_updates"].append(remote_data)
        else:
            plan["upload_updates"].append(local_note)
    return plan


def cloud_plan_counts(plan: Dict[str, List[Any]]) -> Dict[str, int]:
    return {
        "create": len(plan["download_creates"]) + len(plan["upload_creates"]),
        "update": len(plan["download_updates"]) + len(plan["upload_updates"]),
        "delete": len(plan["delete_local"]) + len(plan["delete_remote"]),
        "conflict": len(plan["conflicts"]),
    }


def conflict_copy_labels(labels: List[str], provider: str) -> List[str]:
    normalized = []
    for label in [*(labels or []), "cloud-conflict", f"{provider.lower()}-conflict"]:
        label_text = str(label or "").strip()
        if label_text and label_text not in normalized:
            normalized.append(label_text)
    return normalized


def save_cloud_conflict_copy(db: Any, remote_data: Dict[str, Any], provider: str) -> Optional[Note]:
    note = Note.from_dict(remote_data)
    note.id = str(uuid.uuid4())
    note.title = f"{note.title or 'Untitled'} ({provider} conflict)"
    note.labels = conflict_copy_labels(note.labels, provider)
    note.sync_status = SyncStatus.CONFLICT
    note.keep_id = None
    if db.save_note(note):
        return note
    return None


def cloud_base_versions(notes: List[Note]) -> Dict[str, str]:
    return {note.id: note.content_hash for note in notes}
