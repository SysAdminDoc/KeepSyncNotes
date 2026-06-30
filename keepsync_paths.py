"""Platform data directory helpers for KeepSyncNotes."""

import os
import platform
from pathlib import Path
from typing import Mapping, Optional


APP_DATA_DIR_NAME = "KeepSyncNotes"
LEGACY_DATA_DIR_NAME = ".keepsync_notes"


def get_legacy_data_dir(home: Optional[Path] = None) -> Path:
    root = Path(home) if home is not None else Path.home()
    return root / LEGACY_DATA_DIR_NAME


def get_platform_data_dir(
    app_name: str = APP_DATA_DIR_NAME,
    home: Optional[Path] = None,
    env: Optional[Mapping[str, str]] = None,
    system: Optional[str] = None,
) -> Path:
    root = Path(home) if home is not None else Path.home()
    values = env if env is not None else os.environ
    os_name = system or platform.system()

    if os_name == "Windows":
        base = values.get("LOCALAPPDATA") or values.get("APPDATA")
        if base:
            return Path(base) / app_name
        return root / "AppData" / "Local" / app_name

    if os_name == "Darwin":
        return root / "Library" / "Application Support" / app_name

    base = values.get("XDG_DATA_HOME")
    if base:
        return Path(base) / app_name
    return root / ".local" / "share" / app_name


def get_app_data_dir(
    app_name: str = APP_DATA_DIR_NAME,
    prefer_existing_legacy: bool = True,
    home: Optional[Path] = None,
    env: Optional[Mapping[str, str]] = None,
    system: Optional[str] = None,
) -> Path:
    platform_dir = get_platform_data_dir(app_name, home, env, system)
    legacy_dir = get_legacy_data_dir(home)
    if prefer_existing_legacy and legacy_dir.exists() and not platform_dir.exists():
        return legacy_dir
    return platform_dir


def get_app_file_path(filename: str, data_dir: Optional[Path] = None) -> Path:
    root = Path(data_dir) if data_dir is not None else get_app_data_dir()
    return root / filename


def get_google_drive_credentials_path(data_dir: Optional[Path] = None) -> Path:
    return get_app_file_path("gdrive_credentials.json", data_dir)


def get_google_drive_token_path(data_dir: Optional[Path] = None) -> Path:
    return get_app_file_path("gdrive_token.json", data_dir)
