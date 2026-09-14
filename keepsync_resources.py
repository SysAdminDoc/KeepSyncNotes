"""Runtime paths and window branding for source and packaged builds."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional


def resource_path(filename: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / filename


def apply_window_icon(window) -> Optional[str]:
    """Apply the packaged app icon and return an error message on failure."""
    try:
        if sys.platform == "win32":
            window.iconbitmap(default=str(resource_path("icon.ico")))
        else:
            import tkinter as tk

            icon = tk.PhotoImage(file=str(resource_path("icon.png")))
            window.iconphoto(True, icon)
            window._keepsync_window_icon = icon
        return None
    except Exception as exc:
        return str(exc)
