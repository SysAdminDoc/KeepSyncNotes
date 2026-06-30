"""Folder path helpers built on top of slash-delimited labels."""

from typing import Iterable, List

from keepsync_models import Note


FOLDER_SEPARATOR = "/"


def normalize_folder_path(value: str) -> str:
    parts = [
        part.strip()
        for part in str(value or "").replace("\\", FOLDER_SEPARATOR).split(FOLDER_SEPARATOR)
        if part.strip()
    ]
    return FOLDER_SEPARATOR.join(parts)


def folder_path_depth(path: str) -> int:
    normalized = normalize_folder_path(path)
    return max(0, len(normalized.split(FOLDER_SEPARATOR)) - 1) if normalized else 0


def folder_display_name(path: str) -> str:
    normalized = normalize_folder_path(path)
    return normalized.split(FOLDER_SEPARATOR)[-1] if normalized else ""


def folder_paths_from_label(label: str) -> List[str]:
    normalized = normalize_folder_path(label)
    if not normalized:
        return []
    parts = normalized.split(FOLDER_SEPARATOR)
    if len(parts) == 1:
        return []
    return [FOLDER_SEPARATOR.join(parts[:index]) for index in range(1, len(parts) + 1)]


def folder_paths_from_labels(labels: Iterable[str], explicit_folders: Iterable[str] = ()) -> List[str]:
    paths = set()
    for folder in explicit_folders or []:
        normalized = normalize_folder_path(folder)
        if normalized:
            paths.add(normalized)
            paths.update(folder_paths_from_label(normalized))
    for label in labels or []:
        paths.update(folder_paths_from_label(label))
    return sorted(paths, key=lambda item: (item.lower().split(FOLDER_SEPARATOR), item.lower()))


def note_matches_folder(note: Note, folder_path: str) -> bool:
    target = normalize_folder_path(folder_path)
    if not target:
        return False
    target_prefix = f"{target}{FOLDER_SEPARATOR}"
    for label in note.labels:
        normalized = normalize_folder_path(label)
        if normalized == target or normalized.startswith(target_prefix):
            return True
    return False
