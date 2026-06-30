"""Helpers for adding editor-managed image attachments."""

from pathlib import Path
from typing import Optional
import shutil
import uuid

from PIL import Image

from keepsync_models import Attachment, guess_attachment_mime, sanitize_filename


IMAGE_FILETYPES = [
    ("Images", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
    ("PNG", "*.png"),
    ("JPEG", "*.jpg *.jpeg"),
    ("All files", "*.*"),
]


def note_attachment_dir(db_path: str, note_id: str) -> Path:
    return Path(db_path).parent / "attachments" / note_id


def unique_attachment_path(directory: Path, filename: str) -> Path:
    safe_name = sanitize_filename(filename or f"image-{uuid.uuid4().hex}.png")
    stem = Path(safe_name).stem or "image"
    suffix = Path(safe_name).suffix or ".png"
    candidate = directory / f"{stem}{suffix}"
    counter = 1
    while candidate.exists():
        candidate = directory / f"{stem}-{counter}{suffix}"
        counter += 1
    return candidate


def copy_image_attachment(source_path: Path, db_path: str, note_id: str) -> Attachment:
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(str(source))
    with Image.open(source) as image:
        image.verify()
    target_dir = note_attachment_dir(db_path, note_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = unique_attachment_path(target_dir, source.name)
    shutil.copy2(source, target)
    return Attachment(
        filename=target.name,
        stored_path=str(target),
        mime_type=guess_attachment_mime(str(target), ""),
    )


def save_clipboard_image_attachment(image: Image.Image, db_path: str, note_id: str, filename: Optional[str] = None) -> Attachment:
    target_dir = note_attachment_dir(db_path, note_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = unique_attachment_path(target_dir, filename or "clipboard-image.png")
    image.save(target)
    return Attachment(filename=target.name, stored_path=str(target), mime_type="image/png")
