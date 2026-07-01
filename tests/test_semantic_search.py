import unittest
from datetime import datetime, timezone

from keepsync_models import Note
import keepsync_semantic_search as sem
import keepsync_notes as app


class SemanticSearchTests(unittest.TestCase):
    def _note(self, **kwargs):
        values = {
            "id": "n1",
            "title": "Test",
            "content": "Body",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        values.update(kwargs)
        return Note(**values)

    def test_semantic_search_available_flag(self):
        self.assertIsInstance(sem.SEMANTIC_SEARCH_AVAILABLE, bool)

    def test_note_text_combines_title_content_labels(self):
        if not sem.SEMANTIC_SEARCH_AVAILABLE:
            self.skipTest("fastembed/lancedb not installed")
        index = sem.SemanticIndex.__new__(sem.SemanticIndex)
        note = self._note(title="Hello", content="World", labels=["Work"])
        text = index._note_text(note)
        self.assertIn("Hello", text)
        self.assertIn("World", text)
        self.assertIn("Work", text)

    def test_app_reexports_semantic_search_helpers(self):
        self.assertIs(app.SEMANTIC_SEARCH_AVAILABLE, sem.SEMANTIC_SEARCH_AVAILABLE)
        self.assertIs(app.SemanticIndex, sem.SemanticIndex)


if __name__ == "__main__":
    unittest.main()
