"""Multi-source note importers and Takeout parsing helpers."""

import json
import re
import shutil
import tempfile
import uuid
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, List, Optional

import keepsync_import_safety as import_safety
from keepsync_import_safety import (
    ImportCancelled,
    ImportSafetyError,
    decode_zip_member,
    extract_zip_member_safely,
    guarded_import_files,
    validate_zip_members,
)
from keepsync_models import (
    Attachment,
    ChecklistItem,
    Note,
    NoteType,
    SyncStatus,
    guess_attachment_mime,
    normalize_keep_color,
    normalize_people,
    sanitize_filename,
)
from keepsync_note_ops import normalize_import_labels


def extract_shared_with(data: dict) -> List[str]:
    shared = []
    for key in ("sharees", "collaborators", "contributors", "sharedWith", "sharingUserInfo"):
        for person in normalize_people(data.get(key)):
            if person not in shared:
                shared.append(person)
    if not shared and data.get("isShared"):
        shared.append("Shared")
    return shared


def first_present(data: dict, keys: List[str]) -> str:
    for key in keys:
        value = data.get(key)
        if value:
            return str(value)
    return ""


def takeout_attachment_specs(data: dict) -> List[Any]:
    specs: List[Any] = []
    for key in ("attachments", "media", "files", "blobs"):
        value = data.get(key)
        if isinstance(value, dict):
            specs.append(value)
        elif isinstance(value, list):
            specs.extend([item for item in value if isinstance(item, (dict, str))])

    for key in ("drawingInfo", "audio", "image"):
        value = data.get(key)
        if isinstance(value, dict):
            specs.append(value)
    return specs


def resolve_takeout_attachment_path(source: str, base_path: Optional[Path]) -> Optional[Path]:
    if not source or re.match(r"^[a-z]+://", source, re.IGNORECASE):
        return None

    source_path = Path(source)
    candidates = [source_path]
    if base_path:
        candidates.extend([
            base_path / source_path,
            base_path / source_path.name,
            base_path.parent / source_path,
        ])

    for candidate in candidates:
        try:
            if candidate.exists():
                return candidate
        except OSError:
            continue
    return None


def copy_attachment_to_store(source_path: Path, attachments_root: Path, note_id: str, filename: str) -> Path:
    note_dir = attachments_root / note_id
    note_dir.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_filename(filename or source_path.name)
    destination = note_dir / safe_name
    stem = destination.stem
    suffix = destination.suffix
    counter = 1
    while destination.exists():
        destination = note_dir / f"{stem}-{counter}{suffix}"
        counter += 1
    shutil.copy2(source_path, destination)
    return destination


def import_takeout_attachments(data: dict, base_path: Optional[Path], attachments_root: Path, note_id: str) -> List[Attachment]:
    attachments = []
    for raw in takeout_attachment_specs(data):
        if isinstance(raw, str):
            source = raw
            filename = Path(raw).name
            mime_type = guess_attachment_mime(filename)
        else:
            source = first_present(raw, [
                "filePath", "path", "sourcePath", "url", "filename", "fileName",
                "drawingFilePath", "snapshotFilePath", "audioFilePath",
            ])
            filename = first_present(raw, ["filename", "fileName", "name", "title"]) or Path(source).name
            mime_type = first_present(raw, ["mimeType", "mimetype", "contentType"])

        if not source and not filename:
            continue

        resolved = resolve_takeout_attachment_path(source, base_path)
        stored_path = source
        if resolved:
            stored_path = str(copy_attachment_to_store(resolved, attachments_root, note_id, filename))

        attachments.append(Attachment(
            filename=filename or Path(stored_path).name,
            stored_path=stored_path,
            source_path=str(resolved or source),
            mime_type=guess_attachment_mime(stored_path or filename, mime_type),
        ))
    return attachments


class HTMLTextExtractor(HTMLParser):
    """Small HTML-to-text extractor for imported note formats."""

    BLOCK_TAGS = {
        "address", "article", "aside", "blockquote", "br", "div", "dl", "dt", "dd",
        "figcaption", "figure", "footer", "h1", "h2", "h3", "h4", "h5", "h6",
        "header", "hr", "li", "main", "ol", "p", "pre", "section", "table", "tr",
        "ul",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "en-todo":
            checked = any(name == "checked" and value == "true" for name, value in attrs)
            self.parts.append("[x] " if checked else "[ ] ")
        elif tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag.lower() in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)

    def text(self) -> str:
        value = unescape("".join(self.parts))
        value = re.sub(r"[ \t\r\f\v]+", " ", value)
        value = re.sub(r" *\n *", "\n", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
        return value.strip()


def html_to_text(value: str) -> str:
    extractor = HTMLTextExtractor()
    try:
        extractor.feed(value or "")
        return extractor.text()
    except Exception:
        return re.sub(r"<[^>]+>", "", value or "").strip()


def strip_enex_content(value: str) -> str:
    content = value or ""
    content = re.sub(r"<!DOCTYPE[^>]*>", "", content, flags=re.IGNORECASE)
    content = re.sub(r"<\?xml[^>]*\?>", "", content, flags=re.IGNORECASE)
    return html_to_text(content)


def title_from_content(content: str, fallback: str) -> str:
    for line in (content or "").splitlines():
        cleaned = line.strip().strip("#").strip()
        if cleaned:
            return cleaned[:120]
    return fallback[:120] or "Untitled"


def labels_from_hashtags(content: str) -> List[str]:
    return sorted({match.group(1) for match in re.finditer(r"(?<!\w)#([A-Za-z0-9_-]+)", content or "")})


def parse_external_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    candidates = [text, text.replace("Z", "+00:00")]
    if re.fullmatch(r"\d{8}T\d{6}Z?", text):
        candidates.append(f"{text[0:4]}-{text[4:6]}-{text[6:8]}T{text[9:11]}:{text[11:13]}:{text[13:15]}+00:00")
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


class MultiSourceImporter:
    """Import notes from common note-app export formats."""

    TEXT_SUFFIXES = {".txt", ".md", ".markdown"}
    HTML_SUFFIXES = {".html", ".htm", ".mht", ".mhtml"}
    TAKEOUT_ATTACHMENT_SUFFIXES = {
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff",
        ".svg", ".mp3", ".wav", ".m4a", ".ogg", ".oga", ".opus", ".aac",
        ".amr", ".3gp", ".mp4", ".mov", ".pdf",
    }
    TAKEOUT_ZIP_SUFFIXES = {".json"} | TAKEOUT_ATTACHMENT_SUFFIXES

    def __init__(
        self,
        db: Any,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ):
        self.db = db
        self.progress_callback = progress_callback
        self.cancel_check = cancel_check

    def _check_cancelled(self):
        if self.cancel_check and self.cancel_check():
            raise ImportCancelled("Import cancelled")

    def _progress(self, message: str, current: int, total: int):
        if self.progress_callback:
            self.progress_callback(message, current, total)

    def save_notes(self, notes: List[Note]) -> int:
        imported = 0
        for note in notes:
            note.keep_id = None
            note.sync_status = SyncStatus.LOCAL_ONLY
            result = self.db.save_imported_note(note, conflict_policy="copy")
            if result in {"imported", "conflict_copy"}:
                imported += 1
        return imported

    def _note_from_text(
        self,
        title: str,
        content: str,
        source: str,
        labels: Optional[List[str]] = None,
        markdown: bool = False,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ) -> Note:
        label_values = normalize_import_labels(labels or [], source, markdown)
        now = datetime.now(timezone.utc)
        created = created_at or now
        updated = updated_at or created
        return Note(
            id=str(uuid.uuid4()),
            title=(title or "").strip() or title_from_content(content, "Untitled"),
            content=(content or "").strip(),
            labels=label_values,
            sync_status=SyncStatus.LOCAL_ONLY,
            created_at=created,
            updated_at=updated,
            local_modified=updated,
        )

    def import_enex(self, path: Path, source: str = "Evernote") -> List[Note]:
        tree = ET.parse(path)
        root = tree.getroot()
        notes = []
        for raw_note in root.findall(".//note"):
            title = (raw_note.findtext("title") or path.stem).strip()
            content = strip_enex_content(raw_note.findtext("content") or "")
            labels = [tag.text.strip() for tag in raw_note.findall("tag") if tag.text and tag.text.strip()]
            created = parse_external_datetime(raw_note.findtext("created"))
            updated = parse_external_datetime(raw_note.findtext("updated"))
            notes.append(self._note_from_text(title, content, source, labels, False, created, updated))
        return notes

    def import_text_folder(self, folder: Path, source: str, markdown_default: bool = False) -> List[Note]:
        notes = []
        files = guarded_import_files(folder, self.TEXT_SUFFIXES | self.HTML_SUFFIXES)
        total = len(files)
        for index, file_path in enumerate(files, start=1):
            self._check_cancelled()
            self._progress(f"Reading {file_path.name}", index, total)
            suffix = file_path.suffix.lower()
            raw = file_path.read_text(encoding="utf-8-sig", errors="replace")
            content = html_to_text(raw) if suffix in self.HTML_SUFFIXES else raw
            relative_parent = file_path.relative_to(folder).parent
            folder_labels = [part for part in relative_parent.parts if part and part != "."]
            markdown = markdown_default or suffix in {".md", ".markdown"}
            notes.append(self._note_from_text(file_path.stem, content, source, folder_labels, markdown))
        return notes

    def import_text_zip(self, path: Path, source: str, markdown_default: bool = False) -> List[Note]:
        notes = []
        with zipfile.ZipFile(path) as zf:
            members = validate_zip_members(zf, self.TEXT_SUFFIXES | self.HTML_SUFFIXES)
            total = len(members)
            for index, member in enumerate(members, start=1):
                self._check_cancelled()
                self._progress(f"Reading {Path(member.filename).name}", index, total)
                suffix = Path(member.filename).suffix.lower()
                content = decode_zip_member(zf, member)
                if suffix in self.HTML_SUFFIXES:
                    content = html_to_text(content)
                labels = [part for part in Path(member.filename).parent.parts if part and part != "."]
                labels.extend(labels_from_hashtags(content))
                markdown = markdown_default or suffix in {".md", ".markdown"} or "textbundle" in Path(member.filename).parts
                notes.append(self._note_from_text(Path(member.filename).stem, content, source, labels, markdown))
        return notes

    def import_simplenote_json(self, data: Any) -> List[Note]:
        if isinstance(data, dict):
            raw_notes = list(data.get("activeNotes") or data.get("notes") or data.get("items") or [])
            raw_notes.extend(data.get("trashedNotes") or [])
        elif isinstance(data, list):
            raw_notes = data
        else:
            raw_notes = []

        notes = []
        for item in raw_notes:
            if not isinstance(item, dict):
                continue
            content = item.get("content") or item.get("text") or item.get("body") or ""
            title = item.get("title") or title_from_content(content, "Simplenote note")
            labels = item.get("tags") or item.get("labels") or []
            markdown = "markdown" in [str(tag).lower() for tag in item.get("systemTags", [])]
            created = parse_external_datetime(item.get("creationDate") or item.get("created_at") or item.get("created"))
            updated = parse_external_datetime(item.get("modificationDate") or item.get("updated_at") or item.get("updated"))
            note = self._note_from_text(title, content, "Simplenote", labels, markdown, created, updated)
            note.trashed = bool(item.get("deleted") or item.get("trashed"))
            notes.append(note)
        return notes

    def import_simplenote_export(self, path: Path) -> List[Note]:
        if path.suffix.lower() == ".json":
            return self.import_simplenote_json(json.loads(path.read_text(encoding="utf-8-sig")))

        notes = []
        with zipfile.ZipFile(path) as zf:
            members = validate_zip_members(zf, self.TEXT_SUFFIXES | self.HTML_SUFFIXES | {".json"})
            json_members = [member for member in members if Path(member.filename).suffix.lower() == ".json"]
            total = len(json_members)
            for index, member in enumerate(json_members, start=1):
                self._check_cancelled()
                self._progress(f"Reading {Path(member.filename).name}", index, total)
                try:
                    parsed = json.loads(decode_zip_member(zf, member))
                    notes.extend(self.import_simplenote_json(parsed))
                except json.JSONDecodeError:
                    continue
            if notes:
                return notes

        return self.import_text_zip(path, "Simplenote")

    def _takeout_json_files(self, folder: Path) -> List[Path]:
        candidates = [
            folder,
            folder / "Keep",
            folder / "Takeout" / "Keep",
        ]
        for candidate in candidates:
            if candidate.exists():
                files = sorted(candidate.glob("*.json"))
                if files:
                    return files
        return []

    def import_takeout_folder(self, folder: Path) -> List[Note]:
        notes = []
        json_files = self._takeout_json_files(folder)
        if len(json_files) > import_safety.MAX_IMPORT_FOLDER_FILES:
            raise ImportSafetyError(f"Takeout folder contains more than {import_safety.MAX_IMPORT_FOLDER_FILES} JSON files")
        total_size = sum(file_path.stat().st_size for file_path in json_files)
        if total_size > import_safety.MAX_IMPORT_FOLDER_BYTES:
            raise ImportSafetyError("Takeout folder JSON size exceeds the import limit")
        total = len(json_files)
        for index, json_file in enumerate(json_files, start=1):
            self._check_cancelled()
            self._progress(f"Reading {json_file.name}", index, total)
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                note = self.parse_takeout_note(data, json_file.parent)
                if note:
                    notes.append(note)
            except Exception:
                continue
        return notes

    def import_takeout_zip(self, path: Path) -> List[Note]:
        with tempfile.TemporaryDirectory() as temp_dir:
            with zipfile.ZipFile(path) as zf:
                members = validate_zip_members(zf, self.TAKEOUT_ZIP_SUFFIXES)
                total = len(members)
                for index, member in enumerate(members, start=1):
                    self._check_cancelled()
                    self._progress(f"Extracting {Path(member.filename).name}", index, total)
                    extract_zip_member_safely(zf, member, Path(temp_dir))
            return self.import_takeout_folder(Path(temp_dir))

    def import_takeout_path(self, path: Path) -> List[Note]:
        if path.is_file() and path.suffix.lower() == ".zip":
            return self.import_takeout_zip(path)
        if path.is_dir():
            return self.import_takeout_folder(path)
        return []

    def parse_takeout_note(self, data: dict, base_path: Optional[Path] = None) -> Optional[Note]:
        try:
            note_id = str(uuid.uuid4())
            title = data.get("title", "")
            content = data.get("textContent", "")

            checklist_items = []
            if "listContent" in data:
                for item in data["listContent"]:
                    checklist_items.append(ChecklistItem(
                        text=item.get("text", ""),
                        checked=item.get("isChecked", False),
                    ))

            labels = []
            if "labels" in data:
                labels = [label.get("name", "") for label in data["labels"] if label.get("name")]

            attachments_root = Path(self.db.db_path).parent / "attachments"
            attachments = import_takeout_attachments(data, base_path, attachments_root, note_id)

            return Note(
                id=note_id,
                title=title,
                content=content,
                note_type=NoteType.CHECKLIST if checklist_items else NoteType.NOTE,
                checklist_items=checklist_items,
                labels=labels,
                attachments=attachments,
                pinned=data.get("isPinned", False),
                archived=data.get("isArchived", False),
                trashed=data.get("isTrashed", False),
                color=normalize_keep_color(data.get("color", "")),
                shared_with=extract_shared_with(data),
                sync_status=SyncStatus.LOCAL_ONLY,
            )
        except Exception:
            return None

    def import_external(self, source_type: str, path: Path) -> List[Note]:
        if source_type == "Evernote / Apple Notes ENEX":
            return self.import_enex(path, "Evernote")
        if source_type == "Standard Notes ZIP":
            return self.import_text_zip(path, "Standard Notes")
        if source_type == "Obsidian Vault":
            return self.import_text_folder(path, "Obsidian", markdown_default=True)
        if source_type == "Bear ZIP":
            return self.import_text_zip(path, "Bear", markdown_default=True)
        if source_type == "Simplenote Export":
            return self.import_simplenote_export(path)
        if source_type == "OneNote HTML Folder":
            return self.import_text_folder(path, "OneNote")
        raise ValueError(f"Unsupported source type: {source_type}")
