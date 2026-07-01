import unittest
from datetime import datetime, timezone

from keepsync_models import Attachment, Note
import keepsync_ocr as ocr
import keepsync_notes as app


class OcrTests(unittest.TestCase):
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

    def test_append_ocr_text_adds_block(self):
        note = self._note(content="Hello")
        result = ocr.append_ocr_text(note, ["Scanned text here"])
        self.assertIn("[OCR]", result.content)
        self.assertIn("Scanned text here", result.content)
        self.assertTrue(result.content.startswith("Hello"))

    def test_append_ocr_text_noop_on_empty(self):
        note = self._note(content="Hello")
        original_hash = note.content_hash
        result = ocr.append_ocr_text(note, [])
        self.assertEqual(result.content, "Hello")

    def test_ocr_image_returns_empty_when_unavailable(self):
        if ocr.OCR_AVAILABLE:
            self.skipTest("pytesseract installed — skip unavailable test")
        self.assertEqual(ocr.ocr_image("/nonexistent.png"), "")

    def test_ocr_note_attachments_filters_non_images(self):
        note = self._note(attachments=[
            Attachment(filename="doc.pdf", stored_path="/tmp/doc.pdf", mime_type="application/pdf"),
        ])
        results = ocr.ocr_note_attachments(note)
        self.assertEqual(results, [])

    def test_app_reexports_ocr_helpers(self):
        self.assertIs(app.OCR_AVAILABLE, ocr.OCR_AVAILABLE)
        self.assertIs(app.ocr_image, ocr.ocr_image)
        self.assertIs(app.append_ocr_text, ocr.append_ocr_text)


if __name__ == "__main__":
    unittest.main()
