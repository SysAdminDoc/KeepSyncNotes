#!/usr/bin/env python3
"""Capture deterministic product screenshots without using the active display."""

from __future__ import annotations

import argparse
import ctypes
import os
import shutil
import subprocess
import sys
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


if sys.platform != "win32":
    raise SystemExit("This capture helper currently requires Windows.")

ctypes.windll.user32.SetProcessDPIAware()

import win32con  # noqa: E402
import win32event  # noqa: E402
import win32gui  # noqa: E402
import win32process  # noqa: E402
import win32service  # noqa: E402
import win32ui  # noqa: E402
from PIL import Image  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _prepare_sample_data(output_dir: Path) -> Path:
    data_root = output_dir / "sample-data"
    resolved_output = output_dir.resolve()
    resolved_data = data_root.resolve()
    if resolved_data.parent != resolved_output:
        raise RuntimeError("Refusing to clear a capture directory outside the requested output folder.")
    if data_root.exists():
        shutil.rmtree(data_root)
    app_data = data_root / "KeepSyncNotes"
    app_data.mkdir(parents=True)
    os.environ["LOCALAPPDATA"] = str(data_root)
    os.environ["APPDATA"] = str(data_root)
    return app_data


def _seed_workspace(app_data: Path) -> None:
    from keepsync_models import ChecklistItem, Note, NoteType
    from keepsync_storage import DatabaseManager

    database = DatabaseManager(str(app_data / "notes.db"))
    database.set_setting("auto_sync", False)
    database.set_setting("system_tray", False)
    database.set_setting("takeout_watch_enabled", False)
    database.set_setting("saved_searches", [])

    now = datetime.now(timezone.utc)
    notes = [
        Note(
            id=str(uuid.uuid4()),
            title="Move my notes out of Keep",
            content=(
                "Sample workspace for product screenshots.\n\n"
                "Import the Takeout archive, verify labels and attachments, then export the finished library "
                "to a portable Markdown vault. Everything stays local unless cloud backup is enabled."
            ),
            labels=["Sample workspace", "Migration"],
            pinned=True,
            color="blue",
            created_at=now - timedelta(days=18),
            updated_at=now - timedelta(minutes=4),
        ),
        Note(
            id=str(uuid.uuid4()),
            title="Launch checklist",
            content="",
            note_type=NoteType.CHECKLIST,
            checklist_items=[
                ChecklistItem(text="Export Google Keep from Takeout", checked=True),
                ChecklistItem(text="Review imported labels", checked=True),
                ChecklistItem(text="Create encrypted backup"),
                ChecklistItem(text="Export a Markdown vault"),
            ],
            labels=["Sample workspace", "Projects"],
            color="green",
            created_at=now - timedelta(days=9),
            updated_at=now - timedelta(hours=2),
        ),
        Note(
            id=str(uuid.uuid4()),
            title="Quarterly planning notes",
            content="Pull the goals, decisions, and open questions into one searchable place.",
            labels=["Sample workspace", "Work/Planning"],
            color="yellow",
            created_at=now - timedelta(days=31),
            updated_at=now - timedelta(days=1),
        ),
        Note(
            id=str(uuid.uuid4()),
            title="Books to revisit",
            content="A short list of highlights worth resurfacing during daily review.",
            labels=["Sample workspace", "Reading"],
            created_at=now - timedelta(days=72),
            updated_at=now - timedelta(days=6),
        ),
    ]
    for note in notes:
        database.save_note(note)
        for label in note.labels:
            database.ensure_label(label)
    database.close()


def _root_window_handle(widget) -> int:
    widget.update_idletasks()
    return win32gui.GetAncestor(widget.winfo_id(), win32con.GA_ROOT)


def _show_on_private_desktop(widget, width: int, height: int) -> int:
    hwnd = _root_window_handle(widget)
    flags = win32con.SWP_SHOWWINDOW
    win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, 40, 40, width, height, flags)
    win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
    widget.update()
    time.sleep(0.35)
    widget.update()
    return hwnd


def _capture_window(hwnd: int, output_path: Path) -> None:
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width = right - left
    height = bottom - top
    if width < 1 or height < 1:
        raise RuntimeError("Capture window has invalid dimensions.")

    source_dc_handle = win32gui.GetWindowDC(hwnd)
    source_dc = win32ui.CreateDCFromHandle(source_dc_handle)
    memory_dc = source_dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(source_dc, width, height)
    memory_dc.SelectObject(bitmap)

    try:
        rendered = ctypes.windll.user32.PrintWindow(hwnd, memory_dc.GetSafeHdc(), 2)
        if rendered != 1:
            raise RuntimeError("PrintWindow could not render the private-desktop window.")
        info = bitmap.GetInfo()
        bits = bitmap.GetBitmapBits(True)
        image = Image.frombuffer(
            "RGB",
            (info["bmWidth"], info["bmHeight"]),
            bits,
            "raw",
            "BGRX",
            0,
            1,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, optimize=True)
    finally:
        win32gui.DeleteObject(bitmap.GetHandle())
        memory_dc.DeleteDC()
        source_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, source_dc_handle)


def _capture_child(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    app_data = _prepare_sample_data(output_dir)
    _seed_workspace(app_data)

    import customtkinter as ctk
    from keepsync_app import KeepSyncNotesApp
    from keepsync_settings_dialog import SettingsDialog

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    KeepSyncNotesApp._try_auto_connect = lambda self: None
    KeepSyncNotesApp._try_restore_cloud_sync = lambda self: None
    KeepSyncNotesApp._schedule_reminder_check = lambda self, delay_ms=1000: None
    KeepSyncNotesApp._schedule_takeout_watch_check = lambda self, delay_ms=5000: None
    KeepSyncNotesApp._start_tray = lambda self: None

    app = KeepSyncNotesApp()
    app.geometry("1440x900+40+40")

    notes = app.db.get_all_notes(include_archived=True)
    selected = next(note for note in notes if note.title == "Move my notes out of Keep")
    app._refresh_notes_list()
    app._open_note(selected)
    app.update()

    library_path = output_dir / "library-and-editor.png"
    app_hwnd = _show_on_private_desktop(app, 1440, 900)
    _capture_window(app_hwnd, library_path)

    dialog = SettingsDialog(
        app,
        app.db,
        app.sync_engine,
        cloud_sync=app.cloud_sync,
        app_name="KeepSync Notes",
        app_version="",
        db_version=1,
        gkeepapi_available=True,
    )
    tab_names = dialog.tabview._segmented_button.cget("values")
    dialog.tabview.set(tab_names[-1])
    dialog.geometry("760x820+320+90")
    dialog.update()

    data_path = output_dir / "import-export-and-backup.png"
    dialog_hwnd = _show_on_private_desktop(dialog, 760, 820)
    _capture_window(dialog_hwnd, data_path)

    dialog.grab_release()
    dialog.destroy()
    app.destroy()
    return [library_path, data_path]


def capture(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    desktop_name = f"KeepSyncCapture_{uuid.uuid4().hex}"
    desktop = win32service.CreateDesktop(desktop_name, 0, win32con.MAXIMUM_ALLOWED, None)
    startup = win32process.STARTUPINFO()
    startup.lpDesktop = f"Winsta0\\{desktop_name}"
    command = subprocess.list2cmdline(
        [sys.executable, str(Path(__file__).resolve()), "--child", "--output-dir", str(output_dir)]
    )
    process = thread = None
    try:
        process, thread, _, _ = win32process.CreateProcess(
            sys.executable,
            command,
            None,
            None,
            False,
            win32con.CREATE_NO_WINDOW,
            dict(os.environ),
            str(REPO_ROOT),
            startup,
        )
        thread.Close()
        thread = None
        wait_result = win32event.WaitForSingleObject(process, 60000)
        if wait_result != win32con.WAIT_OBJECT_0:
            win32process.TerminateProcess(process, 2)
            raise RuntimeError("Private-desktop capture timed out.")
        exit_code = win32process.GetExitCodeProcess(process)
        if exit_code != 0:
            raise RuntimeError(f"Private-desktop capture failed with exit code {exit_code}.")
    finally:
        if thread is not None:
            thread.Close()
        if process is not None:
            process.Close()
        desktop.CloseDesktop()

    expected = [output_dir / "library-and-editor.png", output_dir / "import-export-and-backup.png"]
    missing = [path for path in expected if not path.is_file()]
    if missing:
        raise RuntimeError(f"Private-desktop capture did not create: {missing}")
    return expected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    runner = _capture_child if args.child else capture
    try:
        for path in runner(args.output_dir.resolve()):
            print(path)
        return 0
    except Exception:
        if args.child:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            (args.output_dir / "capture-error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
