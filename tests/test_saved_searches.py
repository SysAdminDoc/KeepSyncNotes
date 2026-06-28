import tempfile
import unittest
from pathlib import Path

import keepsync_notes as app


class SavedSearchFilteringTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = app.DatabaseManager(str(Path(self.tmp.name) / "notes.db"))

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def make_view(self, query="", filters=None):
        view = object.__new__(app.KeepSyncNotesApp)
        view.db = self.db
        view.current_filter = "saved:test"
        view.search_query = query
        view.advanced_filters = dict(app.default_advanced_filters())
        view.advanced_filters.update(filters or {})
        return view

    def test_saved_search_preserves_label_fts_matches(self):
        self.db.save_note(app.Note(
            id="label-hit",
            title="Planning",
            content="",
            labels=["strategy"],
        ))

        results = self.make_view(query="strategy")._get_filtered_notes_for_current_view()

        self.assertEqual([note.id for note in results], ["label-hit"])

    def test_saved_search_preserves_checklist_fts_matches(self):
        self.db.save_note(app.Note(
            id="checklist-hit",
            title="Shopping",
            content="",
            note_type=app.NoteType.CHECKLIST,
            checklist_items=[app.ChecklistItem(text="Buy projector cable")],
        ))

        results = self.make_view(query="projector")._get_filtered_notes_for_current_view()

        self.assertEqual([note.id for note in results], ["checklist-hit"])

    def test_filter_only_saved_search_can_return_archived_notes(self):
        self.db.save_note(app.Note(
            id="archived-hit",
            title="Archived",
            content="",
            archived=True,
        ))

        results = self.make_view(filters={"is_archived": True})._get_filtered_notes_for_current_view()

        self.assertEqual([note.id for note in results], ["archived-hit"])


if __name__ == "__main__":
    unittest.main()
