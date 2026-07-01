"""Optional local semantic search via fastembed + lancedb."""

import os
from pathlib import Path
from typing import List, Optional

from keepsync_models import Note, NoteType

try:
    import lancedb
    from fastembed import TextEmbedding
    SEMANTIC_SEARCH_AVAILABLE = True
except ImportError:
    lancedb = None
    TextEmbedding = None
    SEMANTIC_SEARCH_AVAILABLE = False

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
TABLE_NAME = "notes_vectors"


class SemanticIndex:
    def __init__(self, data_dir: Path, model_name: str = DEFAULT_MODEL):
        if not SEMANTIC_SEARCH_AVAILABLE:
            raise RuntimeError("fastembed and lancedb are required for semantic search")
        self.db_path = str(data_dir / "semantic.lance")
        self.db = lancedb.connect(self.db_path)
        self.model = TextEmbedding(model_name=model_name)
        self._ensure_table()

    def _ensure_table(self):
        if TABLE_NAME not in self.db.table_names():
            dummy = list(self.model.embed(["init"]))
            dim = len(dummy[0])
            self.db.create_table(TABLE_NAME, data=[{
                "note_id": "__init__",
                "text": "",
                "vector": [0.0] * dim,
            }])

    def _note_text(self, note: Note) -> str:
        parts = [note.title or ""]
        if note.note_type == NoteType.CHECKLIST:
            parts.extend(item.text for item in note.checklist_items if item.text.strip())
        else:
            parts.append(note.content or "")
        if note.labels:
            parts.append(" ".join(note.labels))
        return " ".join(parts).strip()

    def index_notes(self, notes: List[Note]):
        table = self.db.open_table(TABLE_NAME)
        records = []
        for note in notes:
            text = self._note_text(note)
            if not text:
                continue
            embeddings = list(self.model.embed([text]))
            records.append({
                "note_id": note.id,
                "text": text[:500],
                "vector": embeddings[0].tolist(),
            })
        if records:
            table.add(records)

    def search(self, query: str, limit: int = 10) -> List[str]:
        if not query.strip():
            return []
        table = self.db.open_table(TABLE_NAME)
        embeddings = list(self.model.embed([query]))
        results = table.search(embeddings[0].tolist()).limit(limit).to_list()
        return [r["note_id"] for r in results if r.get("note_id") != "__init__"]

    def clear(self):
        if TABLE_NAME in self.db.table_names():
            self.db.drop_table(TABLE_NAME)
        self._ensure_table()
