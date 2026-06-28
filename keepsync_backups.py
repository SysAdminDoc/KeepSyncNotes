"""Local SQLite and attachment backup/restore support."""

import json
import re
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from keepsync_import_safety import ImportSafetyError, extract_zip_member_safely, validate_zip_members


class LocalBackupManager:
    """Create and restore local versioned backups of the database and attachments."""

    BACKUP_PREFIX = "keepsync-backup"

    def __init__(self, db: Any, app_name: str = "KeepSync Notes", app_version: str = ""):
        self.db = db
        self.app_name = app_name
        self.app_version = app_version
        self.db_path = Path(db.db_path)
        self.data_dir = self.db_path.parent
        self.backups_dir = self.data_dir / "backups"
        self.attachments_dir = self.data_dir / "attachments"

    def _backup_name(self, reason: str) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        slug = re.sub(r"[^A-Za-z0-9_-]+", "-", reason.lower()).strip("-") or "manual"
        return f"{self.BACKUP_PREFIX}-{timestamp}-{slug[:40]}.zip"

    def create_backup(self, reason: str) -> Path:
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        backup_path = self.backups_dir / self._backup_name(reason)
        counter = 1
        while backup_path.exists():
            backup_path = backup_path.with_name(f"{backup_path.stem}-{counter}{backup_path.suffix}")
            counter += 1
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_db = Path(temp_dir) / "notes.db"
            if self.db.conn:
                self.db.conn.commit()
                target = sqlite3.connect(temp_db)
                try:
                    self.db.conn.backup(target)
                finally:
                    target.close()
            elif self.db_path.exists():
                shutil.copy2(self.db_path, temp_db)
            else:
                raise FileNotFoundError(f"Database not found: {self.db_path}")

            manifest = {
                "app": self.app_name,
                "app_version": self.app_version,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "reason": reason,
                "database": "notes.db",
                "attachments": "attachments",
            }

            with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.write(temp_db, "notes.db")
                zf.writestr("manifest.json", json.dumps(manifest, indent=2))
                if self.attachments_dir.exists():
                    for file_path in self.attachments_dir.rglob("*"):
                        if file_path.is_file():
                            archive_name = Path("attachments") / file_path.relative_to(self.attachments_dir)
                            zf.write(file_path, str(archive_name).replace("\\", "/"))
        return backup_path

    def list_backups(self) -> List[Dict[str, Any]]:
        backups = []
        if not self.backups_dir.exists():
            return backups
        for backup_path in sorted(self.backups_dir.glob(f"{self.BACKUP_PREFIX}-*.zip"), reverse=True):
            manifest = {}
            try:
                with zipfile.ZipFile(backup_path) as zf:
                    if "manifest.json" in zf.namelist():
                        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            except Exception:
                manifest = {}
            backups.append({
                "path": backup_path,
                "name": backup_path.name,
                "created_at": manifest.get("created_at", ""),
                "reason": manifest.get("reason", ""),
            })
        return backups

    def restore_backup(self, backup_path: Path) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            with zipfile.ZipFile(backup_path) as zf:
                members = validate_zip_members(zf)
                if "notes.db" not in {member.filename for member in members}:
                    raise ImportSafetyError("Backup does not contain notes.db")
                for member in members:
                    extract_zip_member_safely(zf, member, temp_root)

            restored_db = temp_root / "notes.db"
            if self.db.conn:
                self.db.close()
            shutil.copy2(restored_db, self.db_path)

            restored_attachments = temp_root / "attachments"
            if self.attachments_dir.exists():
                shutil.rmtree(self.attachments_dir)
            if restored_attachments.exists():
                shutil.copytree(restored_attachments, self.attachments_dir)
