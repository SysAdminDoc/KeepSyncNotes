"""Import and backup archive safety helpers."""

import re
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from typing import List, Optional, Set


MAX_IMPORT_ZIP_MEMBERS = 5000
MAX_IMPORT_ZIP_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_IMPORT_TEXT_MEMBER_BYTES = 25 * 1024 * 1024
MAX_IMPORT_FOLDER_FILES = 10000
MAX_IMPORT_FOLDER_BYTES = 512 * 1024 * 1024


class ImportSafetyError(ValueError):
    """Raised when an import archive or folder violates safety limits."""


class ImportCancelled(Exception):
    """Raised when the user cancels a long-running import."""


def decode_zip_member(zf: zipfile.ZipFile, member: zipfile.ZipInfo) -> str:
    if member.file_size > MAX_IMPORT_TEXT_MEMBER_BYTES:
        raise ImportSafetyError(f"Import member is too large: {member.filename}")
    raw = zf.read(member)
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def is_hidden_or_system_path(path_text: str) -> bool:
    return any(part.startswith(".") or part == "__MACOSX" for part in Path(path_text).parts)


def safe_zip_member_parts(filename: str) -> Optional[PurePosixPath]:
    normalized = (filename or "").replace("\\", "/")
    if not normalized or normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        return None
    path = PurePosixPath(normalized)
    if any(part in {"", ".", ".."} for part in path.parts):
        return None
    return path


def validate_zip_members(
    zf: zipfile.ZipFile,
    allowed_suffixes: Optional[Set[str]] = None,
    include_hidden: bool = False,
) -> List[zipfile.ZipInfo]:
    members = []
    total_size = 0
    checked_count = 0
    for member in zf.infolist():
        if member.is_dir():
            continue
        member_path = safe_zip_member_parts(member.filename)
        if member_path is None:
            raise ImportSafetyError(f"Unsafe ZIP member path: {member.filename}")
        if not include_hidden and is_hidden_or_system_path(member.filename):
            continue
        checked_count += 1
        total_size += max(0, member.file_size)
        if checked_count > MAX_IMPORT_ZIP_MEMBERS:
            raise ImportSafetyError(f"ZIP contains more than {MAX_IMPORT_ZIP_MEMBERS} importable files")
        if total_size > MAX_IMPORT_ZIP_UNCOMPRESSED_BYTES:
            raise ImportSafetyError("ZIP uncompressed size exceeds the import limit")
        suffix = member_path.suffix.lower()
        if allowed_suffixes is not None and suffix not in allowed_suffixes:
            continue
        members.append(member)
    return members


def extract_zip_member_safely(zf: zipfile.ZipFile, member: zipfile.ZipInfo, destination: Path) -> Path:
    member_path = safe_zip_member_parts(member.filename)
    if member_path is None:
        raise ImportSafetyError(f"Unsafe ZIP member path: {member.filename}")
    target = destination.joinpath(*member_path.parts)
    resolved_destination = destination.resolve()
    resolved_target = target.resolve(strict=False)
    try:
        resolved_target.relative_to(resolved_destination)
    except ValueError:
        raise ImportSafetyError(f"ZIP member escapes import directory: {member.filename}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with zf.open(member) as source, open(target, "wb") as output:
        shutil.copyfileobj(source, output)
    return target


def guarded_import_files(folder: Path, allowed_suffixes: Set[str]) -> List[Path]:
    files = []
    total_size = 0
    for file_path in folder.rglob("*"):
        if not file_path.is_file() or is_hidden_or_system_path(str(file_path.relative_to(folder))):
            continue
        if file_path.suffix.lower() not in allowed_suffixes:
            continue
        total_size += file_path.stat().st_size
        if len(files) >= MAX_IMPORT_FOLDER_FILES:
            raise ImportSafetyError(f"Import folder contains more than {MAX_IMPORT_FOLDER_FILES} files")
        if total_size > MAX_IMPORT_FOLDER_BYTES:
            raise ImportSafetyError("Import folder size exceeds the import limit")
        files.append(file_path)
    return files
