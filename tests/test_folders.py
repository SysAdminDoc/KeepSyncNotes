import tempfile
import unittest
from pathlib import Path

import keepsync_folders as folders
import keepsync_notes as app


class FolderTests(unittest.TestCase):
    def test_folder_paths_expand_label_hierarchy(self):
        paths = folders.folder_paths_from_labels(
            ["Work/Clients/Acme", "Personal", "Work/Clients/Beta"],
            explicit_folders=["Archive/2026"],
        )

        self.assertEqual(
            paths,
            ["Archive", "Archive/2026", "Work", "Work/Clients", "Work/Clients/Acme", "Work/Clients/Beta"],
        )

    def test_note_matches_parent_and_child_folder(self):
        note = app.Note(id="n1", title="Client", content="", labels=["Work/Clients/Acme"])

        self.assertTrue(folders.note_matches_folder(note, "Work"))
        self.assertTrue(folders.note_matches_folder(note, "Work/Clients"))
        self.assertFalse(folders.note_matches_folder(note, "Personal"))

    def test_app_reexports_folder_helpers_for_compatibility(self):
        self.assertIs(app.normalize_folder_path, folders.normalize_folder_path)
        self.assertIs(app.folder_paths_from_labels, folders.folder_paths_from_labels)
        self.assertIs(app.note_matches_folder, folders.note_matches_folder)


class FolderFilteringTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = app.DatabaseManager(str(Path(self.tmp.name) / "notes.db"))

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def make_view(self, folder_path):
        view = object.__new__(app.KeepSyncNotesApp)
        view.db = self.db
        view.current_filter = f"folder:{folder_path}"
        view.search_query = ""
        view.advanced_filters = dict(app.default_advanced_filters())
        return view

    def test_folder_filter_includes_child_paths(self):
        self.db.save_note(app.Note(id="client", title="Client", content="", labels=["Work/Clients/Acme"]))
        self.db.save_note(app.Note(id="personal", title="Personal", content="", labels=["Personal/Inbox"]))

        results = self.make_view("Work")._get_filtered_notes_for_current_view()

        self.assertEqual([note.id for note in results], ["client"])


if __name__ == "__main__":
    unittest.main()
