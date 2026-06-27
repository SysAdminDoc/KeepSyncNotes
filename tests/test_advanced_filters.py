import unittest
from datetime import datetime, timezone

import keepsync_notes as app


class AdvancedFilterTests(unittest.TestCase):
    def test_and_filter_matches_all_selected_predicates(self):
        note = app.Note(
            id="n1",
            title="Filtered",
            content="",
            labels=["work"],
            color="yellow",
            note_type=app.NoteType.CHECKLIST,
            checklist_items=[app.ChecklistItem(text="Task")],
            updated_at=datetime(2026, 6, 27, tzinfo=timezone.utc),
        )
        filters = app.default_advanced_filters()
        filters.update({
            "label": "work",
            "color": "yellow",
            "date_from": "2026-06-01",
            "date_to": "2026-06-30",
            "has_checklist": True,
        })

        self.assertTrue(app.note_matches_advanced_filters(note, filters))

    def test_or_filter_matches_any_selected_predicate(self):
        note = app.Note(id="n1", title="Filtered", content="", labels=["personal"], color="blue")
        filters = app.default_advanced_filters()
        filters.update({"mode": "OR", "label": "work", "color": "blue"})

        self.assertTrue(app.note_matches_advanced_filters(note, filters))

    def test_filter_rejects_out_of_range_dates(self):
        note = app.Note(
            id="n1",
            title="Old",
            content="",
            updated_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )
        filters = app.default_advanced_filters()
        filters.update({"date_from": "2026-06-01"})

        self.assertFalse(app.note_matches_advanced_filters(note, filters))

    def test_image_and_archived_filters(self):
        note = app.Note(
            id="n1",
            title="Image",
            content="",
            archived=True,
            attachments=[app.Attachment(filename="scan.png", stored_path="scan.png", mime_type="image/png")],
        )
        filters = app.default_advanced_filters()
        filters.update({"has_image": True, "is_archived": True})

        self.assertTrue(app.note_matches_advanced_filters(note, filters))


if __name__ == "__main__":
    unittest.main()
