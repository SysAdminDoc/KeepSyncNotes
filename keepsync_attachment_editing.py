"""Helpers for adding editor-managed image attachments."""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Tuple
from urllib.parse import unquote, urlparse
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
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}


@dataclass
class ImageAttachmentBatchResult:
    attachments: List[Attachment]
    skipped_paths: List[Path]
    failed_paths: List[Tuple[Path, str]]


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


def is_supported_image_path(path: Path) -> bool:
    return Path(path).suffix.lower() in IMAGE_SUFFIXES


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


def copy_image_attachments(source_paths: Iterable[Path], db_path: str, note_id: str) -> ImageAttachmentBatchResult:
    result = ImageAttachmentBatchResult(attachments=[], skipped_paths=[], failed_paths=[])
    for source_path in source_paths:
        source = Path(source_path)
        if not is_supported_image_path(source):
            result.skipped_paths.append(source)
            continue
        try:
            result.attachments.append(copy_image_attachment(source, db_path, note_id))
        except Exception as e:
            result.failed_paths.append((source, str(e)))
    return result


def save_clipboard_image_attachment(image: Image.Image, db_path: str, note_id: str, filename: Optional[str] = None) -> Attachment:
    target_dir = note_attachment_dir(db_path, note_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = unique_attachment_path(target_dir, filename or "clipboard-image.png")
    image.save(target)
    return Attachment(filename=target.name, stored_path=str(target), mime_type="image/png")


def parse_drop_file_paths(
    drop_data: str,
    splitlist: Optional[Callable[[str], Iterable[str]]] = None,
) -> List[Path]:
    if not drop_data:
        return []

    parts: List[str] = []
    if splitlist:
        try:
            parts = [str(item) for item in splitlist(drop_data)]
        except Exception:
            parts = []
    if not parts:
        parts = _split_drop_data_fallback(drop_data)
    return [_drop_part_to_path(part) for part in parts if part]


def _split_drop_data_fallback(drop_data: str) -> List[str]:
    parts: List[str] = []
    current: List[str] = []
    in_braces = False

    for char in drop_data.strip():
        if char == "{" and not in_braces:
            in_braces = True
            continue
        if char == "}" and in_braces:
            in_braces = False
            if current:
                parts.append("".join(current))
                current = []
            continue
        if char.isspace() and not in_braces:
            if current:
                parts.append("".join(current))
                current = []
            continue
        current.append(char)

    if current:
        parts.append("".join(current))
    return parts


def _drop_part_to_path(part: str) -> Path:
    text = part.strip()
    if text.lower().startswith("file:"):
        parsed = urlparse(text)
        path_text = unquote(parsed.path)
        if parsed.netloc:
            path_text = f"//{parsed.netloc}{path_text}"
        elif len(path_text) >= 3 and path_text[0] == "/" and path_text[2] == ":":
            path_text = path_text[1:]
        return Path(path_text)
    return Path(text)
