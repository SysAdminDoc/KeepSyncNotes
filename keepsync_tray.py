"""System tray icon for KeepSyncNotes."""

import threading
from typing import Callable, Optional

from PIL import Image, ImageDraw

try:
    import pystray
    TRAY_AVAILABLE = True
except ImportError:
    pystray = None
    TRAY_AVAILABLE = False


def _create_tray_icon_image(size: int = 64) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        [4, 4, size - 4, size - 4],
        radius=8,
        fill=(34, 197, 94),
    )
    cx, cy = size // 2, size // 2
    draw.line([(cx, cy - 10), (cx, cy + 10)], fill=(2, 6, 23), width=4)
    draw.line([(cx - 10, cy), (cx + 10, cy)], fill=(2, 6, 23), width=4)
    return img


class SystemTray:
    def __init__(
        self,
        app_name: str,
        on_new_note: Callable,
        on_show: Callable,
        on_quit: Callable,
    ):
        self.app_name = app_name
        self._on_new_note = on_new_note
        self._on_show = on_show
        self._on_quit = on_quit
        self._icon: Optional["pystray.Icon"] = None
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if not TRAY_AVAILABLE or self._icon is not None:
            return

        menu = pystray.Menu(
            pystray.MenuItem("New Note", lambda: self._on_new_note(), default=True),
            pystray.MenuItem("Show Window", lambda: self._on_show()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda: self._on_quit()),
        )
        self._icon = pystray.Icon(
            self.app_name,
            _create_tray_icon_image(),
            self.app_name,
            menu,
        )
        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()

    def stop(self):
        if self._icon is not None:
            self._icon.stop()
            self._icon = None
            self._thread = None
