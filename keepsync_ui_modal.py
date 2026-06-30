"""Modal dialog focus helpers."""

from typing import Any, Callable, Optional


def configure_modal_dialog(
    dialog: Any,
    parent: Any,
    initial_focus: Optional[Any] = None,
    on_close: Optional[Callable[[], None]] = None,
    escape_handler: Optional[Callable[[], None]] = None,
):
    """Apply consistent modal focus, Escape handling, and focus return."""
    return_focus = None
    try:
        return_focus = parent.focus_get()
    except Exception:
        return_focus = None

    try:
        dialog.transient(parent)
    except Exception:
        pass
    try:
        dialog.grab_set()
    except Exception:
        pass

    original_destroy = dialog.destroy

    def destroy_with_focus(*args, **kwargs):
        try:
            return original_destroy(*args, **kwargs)
        finally:
            try:
                if return_focus is not None and return_focus.winfo_exists():
                    return_focus.focus_set()
            except Exception:
                pass

    dialog.destroy = destroy_with_focus

    def close_dialog(_event=None):
        if on_close:
            on_close()
        else:
            dialog.destroy()
        return "break"

    def escape_dialog(_event=None):
        if escape_handler:
            escape_handler()
        elif on_close:
            on_close()
        else:
            dialog.destroy()
        return "break"

    try:
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)
    except Exception:
        pass
    try:
        dialog.bind("<Escape>", escape_dialog)
    except Exception:
        pass

    def focus_initial():
        target = initial_focus or dialog
        try:
            target.focus_set()
        except Exception:
            pass
        try:
            target.focus_force()
        except Exception:
            pass

    try:
        dialog.after(50, focus_initial)
    except Exception:
        focus_initial()
