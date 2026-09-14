#!/usr/bin/env python3
"""Exercise the exact packaged executable on a private Windows desktop."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
import uuid
from pathlib import Path


if sys.platform != "win32":
    raise SystemExit("Packaged verification currently requires Windows.")

ctypes.windll.user32.SetProcessDPIAware()

import win32api  # noqa: E402
import win32con  # noqa: E402
import win32event  # noqa: E402
import win32gui  # noqa: E402
import win32process  # noqa: E402
import win32service  # noqa: E402
from PIL import Image  # noqa: E402

from capture_marketing import _capture_window, _prepare_sample_data, _seed_workspace  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]


def _window_with_title(title: str) -> int | None:
    matches: list[int] = []

    def visit(hwnd: int, _extra) -> None:
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd) == title:
            matches.append(hwnd)

    win32gui.EnumWindows(visit, None)
    return matches[0] if matches else None


def _wait_for_window(title: str, timeout: float) -> int:
    deadline = time.time() + timeout
    while time.time() < deadline:
        hwnd = _window_with_title(title)
        if hwnd:
            return hwnd
        time.sleep(0.2)
    raise RuntimeError(f"Timed out waiting for the packaged window: {title}")


def _file_version(executable: Path) -> str:
    return win32api.GetFileVersionInfo(
        str(executable), r"\StringFileInfo\040904B0\FileVersion"
    ).strip()


def _verify_child(executable: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    app_data = _prepare_sample_data(output_dir)
    _seed_workspace(app_data)

    environment = dict(os.environ)
    environment["LOCALAPPDATA"] = str(app_data.parent)
    environment["APPDATA"] = str(app_data.parent)
    process = subprocess.Popen(
        [str(executable)],
        cwd=str(ROOT),
        env=environment,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    hwnd = None
    try:
        hwnd = _wait_for_window("KeepSync Notes", 60)
        time.sleep(0.8)
        screenshot = output_dir / "packaged-library.png"
        _capture_window(hwnd, screenshot)
        with Image.open(screenshot) as image:
            colors = image.convert("RGB").resize((160, 100)).getcolors(maxcolors=16000) or []
            if len(colors) < 20:
                raise RuntimeError("Packaged screenshot did not contain a rendered interface.")
            dimensions = list(image.size)

        digest = hashlib.sha256(executable.read_bytes()).hexdigest()
        result = {
            "executable": executable.name,
            "sha256": digest,
            "fileVersion": _file_version(executable),
            "windowTitle": win32gui.GetWindowText(hwnd),
            "screenshot": screenshot.name,
            "screenshotDimensions": dimensions,
            "sampleDataLabel": "Sample workspace",
            "desktopIsolation": "named private Windows desktop",
        }
        (output_dir / "verification.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
        return result
    finally:
        if hwnd and win32gui.IsWindow(hwnd):
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=8)
        data_root = output_dir / "sample-data"
        if data_root.exists() and data_root.resolve().parent == output_dir.resolve():
            shutil.rmtree(data_root)


def verify(executable: Path, output_dir: Path) -> dict:
    executable = executable.resolve()
    output_dir = output_dir.resolve()
    if not executable.is_file():
        raise FileNotFoundError(executable)
    output_dir.mkdir(parents=True, exist_ok=True)

    desktop_name = f"KeepSyncPackage_{uuid.uuid4().hex}"
    desktop = win32service.CreateDesktop(desktop_name, 0, win32con.MAXIMUM_ALLOWED, None)
    startup = win32process.STARTUPINFO()
    startup.lpDesktop = f"Winsta0\\{desktop_name}"
    command = subprocess.list2cmdline(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--child",
            "--executable",
            str(executable),
            "--output-dir",
            str(output_dir),
        ]
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
            str(ROOT),
            startup,
        )
        thread.Close()
        thread = None
        wait_result = win32event.WaitForSingleObject(process, 90000)
        if wait_result != win32con.WAIT_OBJECT_0:
            win32process.TerminateProcess(process, 2)
            raise RuntimeError("Packaged verification timed out.")
        exit_code = win32process.GetExitCodeProcess(process)
        if exit_code != 0:
            error_file = output_dir / "verification-error.txt"
            detail = error_file.read_text(encoding="utf-8") if error_file.is_file() else ""
            raise RuntimeError(f"Packaged verification failed with exit code {exit_code}.\n{detail}")
    finally:
        if thread is not None:
            thread.Close()
        if process is not None:
            process.Close()
        desktop.CloseDesktop()

    return json.loads((output_dir / "verification.json").read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        result = (
            _verify_child(args.executable.resolve(), args.output_dir.resolve())
            if args.child
            else verify(args.executable, args.output_dir)
        )
        print(json.dumps(result, indent=2))
        return 0
    except Exception:
        if args.child:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            (args.output_dir / "verification-error.txt").write_text(
                traceback.format_exc(), encoding="utf-8"
            )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
