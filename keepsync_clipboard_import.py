"""Import notes from Windows clipboard history."""

import sys
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from keepsync_models import Note, NoteType, SyncStatus

CLIPBOARD_HISTORY_AVAILABLE = False

if sys.platform == "win32":
    try:
        import winrt.windows.applicationmodel.datatransfer as wrt_dt
        CLIPBOARD_HISTORY_AVAILABLE = True
    except ImportError:
        pass


def fetch_clipboard_text_items(max_items: int = 50) -> List[dict]:
    if not CLIPBOARD_HISTORY_AVAILABLE:
        return []

    import asyncio
    import winrt.windows.applicationmodel.datatransfer as wrt_dt

    async def _fetch():
        items = []
        try:
            result = wrt_dt.Clipboard.get_history_items_async()
            history = await result
            if history.status != wrt_dt.ClipboardHistoryItemsResultStatus.SUCCESS:
                return items
            for item in history.items:
                content = item.content
                if content.contains(wrt_dt.StandardDataFormats.text):
                    text_op = content.get_text_async()
                    text = await text_op
                    if text and text.strip():
                        items.append({
                            "text": text.strip(),
                            "timestamp": item.timestamp.universal_time if hasattr(item, "timestamp") else None,
                        })
                if len(items) >= max_items:
                    break
        except Exception:
            pass
        return items

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_fetch())
    finally:
        loop.close()


def clipboard_items_to_notes(items: List[dict]) -> List[Note]:
    notes = []
    for item in items:
        text = item.get("text", "").strip()
        if not text:
            continue
        lines = text.split("\n", 1)
        title = lines[0][:80].strip()
        content = text

        notes.append(Note(
            id=str(uuid.uuid4()),
            title=title,
            content=content,
            note_type=NoteType.NOTE,
            labels=["clipboard-import"],
            sync_status=SyncStatus.LOCAL_ONLY,
        ))
    return notes
