"""Optional native file drag-and-drop helpers."""

from typing import Callable


DROP_COPY_ACTION = "copy"

try:
    from tkinterdnd2 import COPY, DND_FILES, TkinterDnD
except Exception:
    COPY = DROP_COPY_ACTION
    DND_FILES = "DND_Files"
    TkinterDnD = None


def enable_file_drop(widget, drop_callback: Callable) -> bool:
    """Register a Tk widget as a native file drop target when TkDND is available."""
    if TkinterDnD is None:
        return False
    try:
        TkinterDnD._require(widget.winfo_toplevel())
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<Drop>>", drop_callback)
    except Exception:
        return False
    return True


def drop_copy_action() -> str:
    return COPY or DROP_COPY_ACTION
