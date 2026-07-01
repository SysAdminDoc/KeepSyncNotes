"""Optional OCR for image attachments via Tesseract."""

from pathlib import Path
from typing import List, Optional

from keepsync_models import Attachment, Note

try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:
    pytesseract = None
    OCR_AVAILABLE = False


def ocr_image(path: str, lang: str = "eng") -> str:
    if not OCR_AVAILABLE:
        return ""
    source = Path(path)
    if not source.exists():
        return ""
    try:
        img = Image.open(source)
        text = pytesseract.image_to_string(img, lang=lang)
        return (text or "").strip()
    except Exception:
        return ""


def ocr_note_attachments(note: Note, lang: str = "eng") -> List[str]:
    results = []
    for attachment in note.attachments:
        if not attachment.is_image:
            continue
        text = ocr_image(attachment.stored_path, lang=lang)
        if text:
            results.append(text)
    return results


def append_ocr_text(note: Note, ocr_texts: List[str]) -> Note:
    if not ocr_texts:
        return note
    block = "\n\n---\n[OCR]\n" + "\n---\n".join(ocr_texts)
    note.content = (note.content or "") + block
    note.update_hash()
    return note
