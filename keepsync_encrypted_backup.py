"""AES-GCM encrypted backup for KeepSyncNotes SQLite database."""

import json
import os
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from keepsync_app_info import APP_NAME, APP_VERSION


BACKUP_MAGIC = b"KSENC1"
SALT_BYTES = 32
NONCE_BYTES = 12
TAG_BYTES = 16
KDF_ITERATIONS = 600_000


@dataclass
class EncryptedBackupResult:
    output_path: Path
    size_bytes: int
    notes_count: int


def _derive_key(password: str, salt: bytes) -> bytes:
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=KDF_ITERATIONS,
    )
    return kdf.derive(password.encode("utf-8"))


def create_encrypted_backup(
    db_path: str,
    output_path: Path,
    password: str,
) -> EncryptedBackupResult:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    conn = sqlite3.connect(db_path)
    try:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = tmp.name
        backup_conn = sqlite3.connect(tmp_path)
        conn.backup(backup_conn)
        backup_conn.close()

        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM notes WHERE trashed = 0")
        notes_count = cursor.fetchone()[0]
    finally:
        conn.close()

    try:
        plaintext = Path(tmp_path).read_bytes()
    finally:
        os.unlink(tmp_path)

    salt = os.urandom(SALT_BYTES)
    key = _derive_key(password, salt)
    nonce = os.urandom(NONCE_BYTES)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)

    header = json.dumps({
        "app": APP_NAME,
        "version": APP_VERSION,
        "created": datetime.now(timezone.utc).isoformat(),
        "kdf": "pbkdf2-sha256",
        "iterations": KDF_ITERATIONS,
        "cipher": "aes-256-gcm",
    }).encode("utf-8")

    header_len = len(header).to_bytes(4, "big")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(BACKUP_MAGIC)
        f.write(header_len)
        f.write(header)
        f.write(salt)
        f.write(nonce)
        f.write(ciphertext)

    return EncryptedBackupResult(
        output_path=output_path,
        size_bytes=output_path.stat().st_size,
        notes_count=notes_count,
    )


def restore_encrypted_backup(
    backup_path: Path,
    password: str,
    restore_db_path: str,
) -> int:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    data = backup_path.read_bytes()
    if not data.startswith(BACKUP_MAGIC):
        raise ValueError("Not a valid KeepSync encrypted backup")

    offset = len(BACKUP_MAGIC)
    header_len = int.from_bytes(data[offset:offset + 4], "big")
    offset += 4
    offset += header_len

    salt = data[offset:offset + SALT_BYTES]
    offset += SALT_BYTES
    nonce = data[offset:offset + NONCE_BYTES]
    offset += NONCE_BYTES
    ciphertext = data[offset:]

    key = _derive_key(password, salt)
    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    except Exception:
        raise ValueError("Decryption failed — wrong password or corrupted backup")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp.write(plaintext)
        tmp_path = tmp.name

    try:
        source = sqlite3.connect(tmp_path)
        try:
            cursor = source.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}
            if "notes" not in tables:
                raise ValueError("Backup does not contain a valid KeepSync database")

            cursor.execute("SELECT COUNT(*) FROM notes WHERE trashed = 0")
            notes_count = cursor.fetchone()[0]
        finally:
            source.close()

        dest_path = Path(restore_db_path)
        if dest_path.exists():
            shutil.copy2(dest_path, dest_path.with_suffix(".db.pre-restore"))
        shutil.copy2(tmp_path, dest_path)
    finally:
        os.unlink(tmp_path)

    return notes_count


def read_backup_header(backup_path: Path) -> Optional[dict]:
    try:
        with open(backup_path, "rb") as f:
            magic = f.read(len(BACKUP_MAGIC))
            if magic != BACKUP_MAGIC:
                return None
            header_len = int.from_bytes(f.read(4), "big")
            header_bytes = f.read(header_len)
            return json.loads(header_bytes)
    except Exception:
        return None
