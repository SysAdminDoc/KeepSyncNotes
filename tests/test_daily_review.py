import unittest
from datetime import datetime, timedelta, timezone

from keepsync_models import ChecklistItem, Note, NoteType
import keepsync_daily_review as review
import keepsync_notes as app


class DailyReviewTests(unittest.TestCase):
    def _note(self, **kwargs):
        values = {
            "id": "n1",
            "title": "Old Note",
            "content": "Body text",
            "created_at": datetime.now(timezone.utc) - timedelta(days=30),
            "updated_at": datetime.now(timezone.utc),
        }
        values.update(kwargs)
        return Note(**values)

    def test_pick_excludes_recent_notes(self):
        recent = self._note(id="r1", created_at=datetime.now(timezone.utc))
        old = self._note(id="o1", created_at=datetime.now(timezone.utc) - timedelta(days=30))
        result = review.pick_review_notes([recent, old], count=3, min_age_days=7)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "o1")

    def test_pick_excludes_trashed_notes(self):
        trashed = self._note(id="t1", trashed=True)
        result = review.pick_review_notes([trashed], count=3)
        self.assertEqual(len(result), 0)

    def test_pick_returns_up_to_count(self):
        notes = [self._note(id=f"n{i}") for i in range(10)]
        result = review.pick_review_notes(notes, count=3)
        self.assertEqual(len(result), 3)

    def test_pick_returns_all_when_fewer_than_count(self):
        notes = [self._note(id=f"n{i}") for i in range(2)]
        result = review.pick_review_notes(notes, count=5)
        self.assertEqual(len(result), 2)

    def test_pick_empty_list(self):
        self.assertEqual(review.pick_review_notes([], count=3), [])

    def test_review_summary_formats_title_age_labels(self):
        note = self._note(labels=["Work", "Project"])
        summary = review.review_summary(note)
        self.assertIn("Old Note", summary)
        self.assertIn("days ago", summary)
        self.assertIn("Work", summary)

    def test_review_summary_uses_checklist_preview(self):
        note = self._note(
            note_type=NoteType.CHECKLIST,
            checklist_items=[ChecklistItem(text="Buy milk"), ChecklistItem(text="Eggs")],
        )
        summary = review.review_summary(note)
        self.assertIn("Buy milk", summary)

    def test_app_reexports_daily_review_helpers(self):
        self.assertIs(app.pick_review_notes, review.pick_review_notes)
        self.assertIs(app.review_summary, review.review_summary)


if __name__ == "__main__":
    unittest.main()
