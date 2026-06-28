import unittest

import keepsync_models as models
import keepsync_notes as app


class ModelsModuleTests(unittest.TestCase):
    def test_app_reexports_model_api_for_compatibility(self):
        self.assertIs(app.Note, models.Note)
        self.assertIs(app.NoteType, models.NoteType)
        self.assertIs(app.SyncStatus, models.SyncStatus)
        self.assertIs(app.ChecklistItem, models.ChecklistItem)
        self.assertIs(app.Attachment, models.Attachment)
        self.assertIs(app.Label, models.Label)

    def test_note_roundtrip_normalizes_core_fields(self):
        note = models.Note(
            id="note-1",
            title="Checklist",
            content="",
            note_type=models.NoteType.CHECKLIST,
            checklist_items=[models.ChecklistItem(text="Indented", indent=99)],
            color="dark-blue",
            shared_with=[{"user": {"email": "person@example.com"}}, "person@example.com"],
            attachments=[{"filename": "../scan?.png", "stored_path": "scan.png"}],
        )

        round_tripped = models.Note.from_dict(note.to_dict())

        self.assertEqual(round_tripped.color, "darkblue")
        self.assertEqual(round_tripped.shared_with, ["person@example.com"])
        self.assertEqual(round_tripped.checklist_items[0].indent, 4)
        self.assertEqual(round_tripped.attachments[0].filename, "scan_.png")
        self.assertEqual(round_tripped.attachments[0].mime_type, "image/png")
        self.assertEqual(round_tripped.content_hash, note.content_hash)

    def test_color_and_filename_helpers_are_standalone(self):
        self.assertEqual(models.normalize_keep_color("ColorValue.Dark Blue"), "darkblue")
        self.assertEqual(models.keep_color_name("dark_blue"), "Dark blue")
        self.assertEqual(models.keep_color_hex("missing"), "#1e293b")
        self.assertEqual(models.sanitize_filename("../bad:name?.txt"), "bad_name_.txt")

    def test_label_roundtrip(self):
        label = models.Label(id="label-1", name="Work", color="blue", keep_id="keep-label")

        self.assertEqual(models.Label.from_dict(label.to_dict()), label)


if __name__ == "__main__":
    unittest.main()
