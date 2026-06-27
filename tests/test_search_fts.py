import tempfile
import unittest
from pathlib import Path

import keepsync_notes as app


class SearchFtsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = app.DatabaseManager(str(Path(self.tmp.name) / "notes.db"))

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_search_finds_content_and_labels(self):
        self.db.save_note(app.Note(
            id="alpha",
            title="Project Alpha",
            content="Quarterly planning notes",
            labels=["strategy"],
        ))

        content_results = self.db.search_notes("quarterly")
        label_results = self.db.search_notes("strategy")

        self.assertEqual([note.id for note in content_results], ["alpha"])
        self.assertEqual([note.id for note in label_results], ["alpha"])

    def test_search_indexes_checklist_items(self):
        self.db.save_note(app.Note(
            id="checklist",
            title="Shopping",
            content="",
            note_type=app.NoteType.CHECKLIST,
            checklist_items=[app.ChecklistItem(text="Buy projector cable")],
        ))

        results = self.db.search_notes("projector")

        self.assertEqual([note.id for note in results], ["checklist"])

    def test_search_excludes_trashed_notes(self):
        self.db.save_note(app.Note(id="trash", title="Trash", content="needle"))
        self.db.delete_note("trash")

        self.assertEqual(self.db.search_notes("needle"), [])


if __name__ == "__main__":
    unittest.main()
