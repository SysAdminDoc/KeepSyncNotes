"""File-backed diagnostics and crash logging for KeepSync Notes."""

import importlib.util
import sys
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional


class DiagnosticsManager:
    """File-backed diagnostics and crash logging."""

    DEPENDENCIES = {
        "customtkinter": "customtkinter",
        "Pillow": "PIL",
        "requests": "requests",
        "gkeepapi": "gkeepapi",
        "gpsoauth": "gpsoauth",
        "browser-cookie3": "browser_cookie3",
        "plyer": "plyer",
        "keyring": "keyring",
        "PyGithub": "github",
        "google-api-python-client": "googleapiclient",
        "google-auth": "google.auth",
        "google-auth-oauthlib": "google_auth_oauthlib",
    }

    def __init__(
        self,
        data_dir: Path,
        app_name: str = "KeepSync Notes",
        app_version: str = "",
        feature_state: Optional[Dict[str, bool]] = None,
    ):
        self.data_dir = Path(data_dir)
        self.app_name = app_name
        self.app_version = app_version
        self.feature_state = feature_state or {}
        self.log_dir = self.data_dir / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.log_dir / "keepsync-diagnostics.log"
        self.last_exception = ""
        self._previous_sys_hook = None
        self._previous_thread_hook = None

    def install_hooks(self):
        self._previous_sys_hook = sys.excepthook
        sys.excepthook = self._handle_unhandled_exception
        if hasattr(threading, "excepthook"):
            self._previous_thread_hook = threading.excepthook
            threading.excepthook = self._handle_thread_exception

    def _write(self, level: str, message: str):
        timestamp = datetime.now(timezone.utc).isoformat()
        with open(self.log_path, "a", encoding="utf-8") as fh:
            fh.write(f"[{timestamp}] {level.upper()} {message}\n")

    def log_event(self, level: str, message: str):
        self._write(level, message)

    def log_exception(self, context: str, exc: BaseException):
        detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip()
        self.last_exception = f"{context}: {exc}"
        self._write("error", f"{context}: {detail}")

    def _handle_unhandled_exception(self, exc_type, exc, tb):
        detail = "".join(traceback.format_exception(exc_type, exc, tb)).strip()
        self.last_exception = f"unhandled: {exc}"
        self._write("critical", f"Unhandled exception: {detail}")
        if self._previous_sys_hook:
            self._previous_sys_hook(exc_type, exc, tb)

    def _handle_thread_exception(self, args):
        detail = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)).strip()
        self.last_exception = f"thread: {args.exc_value}"
        self._write("critical", f"Thread exception: {detail}")
        if self._previous_thread_hook:
            self._previous_thread_hook(args)

    def dependency_state(self) -> Dict[str, str]:
        state = {}
        for package, import_name in self.DEPENDENCIES.items():
            state[package] = "available" if importlib.util.find_spec(import_name) else "missing"
        return state

    def recent_log(self, limit: int = 80) -> str:
        if not self.log_path.exists():
            return ""
        lines = self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-limit:])

    def report(self, db_path: Path, attachments_path: Path) -> str:
        dependencies = "\n".join(
            f"- {package}: {state}"
            for package, state in sorted(self.dependency_state().items())
        )
        app_header = f"{self.app_name} v{self.app_version}" if self.app_version else self.app_name
        keyring_available = self.feature_state.get("keyring_available", False)
        keep_api_available = self.feature_state.get("gkeepapi_available", False)
        notifications_available = self.feature_state.get("desktop_notifications_available", False)
        return (
            f"{app_header}\n"
            f"Database: {db_path}\n"
            f"Attachments: {attachments_path}\n"
            f"Diagnostics log: {self.log_path}\n"
            f"Keyring available: {keyring_available}\n"
            f"Google Keep API available: {keep_api_available}\n"
            f"Desktop notifications available: {notifications_available}\n"
            f"Last exception: {self.last_exception or 'None'}\n\n"
            f"Dependencies:\n{dependencies}\n\n"
            f"Recent log:\n{self.recent_log() or 'No log entries.'}"
        )


DIAGNOSTICS: Optional[DiagnosticsManager] = None


def set_diagnostics_manager(manager: DiagnosticsManager):
    global DIAGNOSTICS
    DIAGNOSTICS = manager


def log_diagnostic_event(level: str, message: str):
    if DIAGNOSTICS:
        DIAGNOSTICS.log_event(level, message)


def log_diagnostic_exception(context: str, exc: BaseException):
    if DIAGNOSTICS:
        DIAGNOSTICS.log_exception(context, exc)
