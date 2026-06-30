"""Reusable note card and status UI components."""

from datetime import datetime
from typing import Callable, Dict, Iterable

import customtkinter as ctk
from PIL import Image, ImageDraw

from keepsync_models import Note, NoteType, SyncStatus, keep_color_hex, normalize_keep_color
from keepsync_theme import COLORS


def _default_note_uses_markdown(labels: Iterable[str]) -> bool:
    return any(str(label or "").strip().lower() == ".md" for label in labels or [])


def _default_markdown_preview_text(markdown_text: str, limit: int = 150) -> str:
    text = " ".join((markdown_text or "").split())
    return text[:limit] + ("..." if len(text) > limit else "")


def _default_format_reminder_datetime(value: datetime) -> str:
    return value.astimezone().strftime("%Y-%m-%d %H:%M") if value else ""


note_uses_markdown = _default_note_uses_markdown
markdown_preview_text = _default_markdown_preview_text
format_reminder_datetime = _default_format_reminder_datetime


def configure_note_card_helpers(
    note_uses_markdown_func: Callable[[Iterable[str]], bool] = None,
    markdown_preview_text_func: Callable[[str], str] = None,
    format_reminder_datetime_func: Callable[[datetime], str] = None,
) -> None:
    global note_uses_markdown, markdown_preview_text, format_reminder_datetime
    if note_uses_markdown_func is not None:
        note_uses_markdown = note_uses_markdown_func
    if markdown_preview_text_func is not None:
        markdown_preview_text = markdown_preview_text_func
    if format_reminder_datetime_func is not None:
        format_reminder_datetime = format_reminder_datetime_func


class IconManager:
    """Generate and cache icons for the application"""

    _cache: Dict[str, ctk.CTkImage] = {}

    @classmethod
    def get_icon(cls, name: str, size: int = 20, color: str = None) -> ctk.CTkImage:
        """Get or create an icon"""
        cache_key = f"{name}_{size}_{color}"
        if cache_key not in cls._cache:
            cls._cache[cache_key] = cls._create_icon(name, size, color or COLORS["text_secondary"])
        return cls._cache[cache_key]

    @classmethod
    def _create_icon(cls, name: str, size: int, color: str) -> ctk.CTkImage:
        """Create an icon image"""
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Parse color
        if color.startswith("#"):
            r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
        else:
            r, g, b = 148, 163, 184  # Default

        icon_color = (r, g, b, 255)

        # Draw icons based on name
        if name == "search":
            draw.ellipse([3, 3, size-7, size-7], outline=icon_color, width=2)
            draw.line([size-8, size-8, size-3, size-3], fill=icon_color, width=2)
        elif name == "plus":
            mid = size // 2
            draw.line([mid, 4, mid, size-4], fill=icon_color, width=2)
            draw.line([4, mid, size-4, mid], fill=icon_color, width=2)
        elif name == "pin":
            draw.polygon([(size//2, 2), (size-4, size//2), (size//2, size-2), (4, size//2)],
                        fill=icon_color)
        elif name == "trash":
            draw.rectangle([5, 5, size-5, 7], fill=icon_color)
            draw.rectangle([6, 8, size-6, size-3], outline=icon_color, width=1)
        elif name == "archive":
            draw.rectangle([3, 3, size-3, 8], fill=icon_color)
            draw.rectangle([5, 9, size-5, size-3], outline=icon_color, width=1)
        elif name == "sync":
            draw.arc([3, 3, size-3, size-3], 0, 270, fill=icon_color, width=2)
            draw.polygon([(size-5, size//2-3), (size-5, size//2+3), (size-2, size//2)], fill=icon_color)
        elif name == "settings":
            draw.ellipse([size//2-4, size//2-4, size//2+4, size//2+4], outline=icon_color, width=2)
            for angle in range(0, 360, 45):
                import math
                x1 = size//2 + int(6 * math.cos(math.radians(angle)))
                y1 = size//2 + int(6 * math.sin(math.radians(angle)))
                x2 = size//2 + int(9 * math.cos(math.radians(angle)))
                y2 = size//2 + int(9 * math.sin(math.radians(angle)))
                draw.line([x1, y1, x2, y2], fill=icon_color, width=2)
        elif name == "label":
            draw.polygon([(4, size//2), (10, 4), (size-3, 4), (size-3, size-4), (10, size-4)],
                        outline=icon_color, width=1)
        elif name == "check":
            draw.line([4, size//2, size//2-2, size-5], fill=icon_color, width=2)
            draw.line([size//2-2, size-5, size-3, 5], fill=icon_color, width=2)
        elif name == "close":
            draw.line([5, 5, size-5, size-5], fill=icon_color, width=2)
            draw.line([5, size-5, size-5, 5], fill=icon_color, width=2)
        elif name == "edit":
            draw.polygon([(4, size-4), (4, size-8), (size-8, 4), (size-4, 4)],
                        outline=icon_color, width=1)
        elif name == "cloud":
            draw.ellipse([3, size//2-2, size//2, size-3], outline=icon_color, width=1)
            draw.ellipse([size//2-3, size//2-4, size-3, size-3], outline=icon_color, width=1)
            draw.ellipse([size//3, 4, size-size//3, size//2+2], outline=icon_color, width=1)
        elif name == "local":
            draw.rectangle([4, 6, size-4, size-4], outline=icon_color, width=1)
            draw.line([size//2, 6, size//2, size-4], fill=icon_color, width=1)
            draw.line([4, size//2+1, size-4, size//2+1], fill=icon_color, width=1)
        elif name == "checklist":
            y_positions = [5, size//2, size-5]
            for y in y_positions:
                draw.rectangle([4, y-2, 8, y+2], outline=icon_color, width=1)
                draw.line([11, y, size-4, y], fill=icon_color, width=1)
        elif name == "note":
            draw.rectangle([4, 3, size-4, size-3], outline=icon_color, width=1)
            for y in [7, 11, 15]:
                if y < size - 5:
                    draw.line([7, y, size-7, y], fill=icon_color, width=1)
        elif name == "export":
            draw.rectangle([5, 8, size-5, size-3], outline=icon_color, width=1)
            draw.line([size//2, 3, size//2, 12], fill=icon_color, width=2)
            draw.polygon([(size//2-3, 6), (size//2+3, 6), (size//2, 2)], fill=icon_color)
        elif name == "import":
            draw.rectangle([5, 8, size-5, size-3], outline=icon_color, width=1)
            draw.line([size//2, 3, size//2, 12], fill=icon_color, width=2)
            draw.polygon([(size//2-3, 9), (size//2+3, 9), (size//2, 13)], fill=icon_color)
        else:
            # Default circle
            draw.ellipse([4, 4, size-4, size-4], outline=icon_color, width=2)

        return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))


class SyncStatusBadge(ctk.CTkFrame):
    """Badge showing sync status"""

    STATUS_CONFIG = {
        SyncStatus.LOCAL_ONLY: ("Local", COLORS["sync_local"], "local"),
        SyncStatus.SYNCED: ("Synced", COLORS["sync_synced"], "cloud"),
        SyncStatus.PENDING_PUSH: ("Pending", COLORS["sync_pending"], "sync"),
        SyncStatus.PENDING_PULL: ("Update", COLORS["sync_pending"], "sync"),
        SyncStatus.CONFLICT: ("Conflict", COLORS["accent_red"], "close"),
        SyncStatus.DELETED_REMOTE: ("Unlinked", COLORS["text_muted"], "local"),
        SyncStatus.ERROR: ("Error", COLORS["sync_error"], "close"),
    }

    def __init__(self, parent, status: SyncStatus = SyncStatus.LOCAL_ONLY, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)

        self.status = status
        text, color, icon_name = self.STATUS_CONFIG.get(status, ("Unknown", COLORS["text_muted"], "cloud"))

        self.icon = ctk.CTkLabel(
            self,
            text="",
            image=IconManager.get_icon(icon_name, 14, color),
            width=14
        )
        self.icon.pack(side="left", padx=(0, 4))

        self.label = ctk.CTkLabel(
            self,
            text=text,
            font=ctk.CTkFont(size=11),
            text_color=color
        )
        self.label.pack(side="left")

    def update_status(self, status: SyncStatus):
        """Update displayed status"""
        self.status = status
        text, color, icon_name = self.STATUS_CONFIG.get(status, ("Unknown", COLORS["text_muted"], "cloud"))
        self.icon.configure(image=IconManager.get_icon(icon_name, 14, color))
        self.label.configure(text=text, text_color=color)


class NoteCard(ctk.CTkFrame):
    """Card displaying a note preview"""

    def __init__(self, parent, note: Note, on_click: Callable, on_pin: Callable,
                 on_delete: Callable, on_archive: Callable, **kwargs):
        super().__init__(
            parent,
            fg_color=COLORS["bg_medium"],
            corner_radius=12,
            border_width=1,
            border_color=COLORS["border"],
            **kwargs
        )

        self.note = note
        self.on_click = on_click
        self.on_pin = on_pin
        self.on_delete = on_delete
        self.on_archive = on_archive

        self._is_hovered = False
        self._build_ui()
        self._bind_events()

    def _build_ui(self):
        if normalize_keep_color(self.note.color):
            color_strip = ctk.CTkFrame(
                self,
                fg_color=keep_color_hex(self.note.color),
                height=5,
                corner_radius=2
            )
            color_strip.pack(fill="x", padx=1, pady=(1, 0))

        # Main content area
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True, padx=12, pady=10)

        # Header with title and pin
        header = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, 6))

        # Pin indicator
        if self.note.pinned:
            pin_icon = ctk.CTkLabel(
                header,
                text="",
                image=IconManager.get_icon("pin", 16, COLORS["accent_yellow"]),
                width=16
            )
            pin_icon.pack(side="left", padx=(0, 6))

        # Title
        title_text = self.note.title if self.note.title else "Untitled"
        self.title_label = ctk.CTkLabel(
            header,
            text=title_text[:50] + ("..." if len(title_text) > 50 else ""),
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLORS["text_primary"],
            anchor="w"
        )
        self.title_label.pack(side="left", fill="x", expand=True)

        # Note type icon
        icon_name = "checklist" if self.note.note_type == NoteType.CHECKLIST else "note"
        type_icon = ctk.CTkLabel(
            header,
            text="",
            image=IconManager.get_icon(icon_name, 16, COLORS["text_muted"]),
            width=16
        )
        type_icon.pack(side="right")

        # Content preview
        if self.note.note_type == NoteType.CHECKLIST:
            preview_text = "\n".join([
                f"{'  ' * min(item.indent, 3)}{'[x]' if item.checked else '[ ]'} {item.text}"
                for item in self.note.checklist_items[:3]
            ])
            if len(self.note.checklist_items) > 3:
                preview_text += f"\n  +{len(self.note.checklist_items) - 3} more..."
        else:
            if note_uses_markdown(self.note.labels):
                preview_text = markdown_preview_text(self.note.content)
            else:
                preview_text = self.note.content[:150]
                if len(self.note.content) > 150:
                    preview_text += "..."

        if preview_text:
            self.preview_label = ctk.CTkLabel(
                self.content_frame,
                text=preview_text,
                font=ctk.CTkFont(size=12),
                text_color=COLORS["text_secondary"],
                anchor="nw",
                justify="left",
                wraplength=250
            )
            self.preview_label.pack(fill="x", pady=(0, 8))

        if self.note.reminder_at:
            reminder_text = f"Reminder: {format_reminder_datetime(self.note.reminder_at)}"
            if self.note.reminder_location:
                reminder_text += f" @ {self.note.reminder_location}"
            self.reminder_label = ctk.CTkLabel(
                self.content_frame,
                text=reminder_text,
                font=ctk.CTkFont(size=11),
                text_color=COLORS["accent_yellow"],
                anchor="w",
                wraplength=250
            )
            self.reminder_label.pack(fill="x", pady=(0, 8))

        if self.note.shared_with:
            shared_text = "Shared with " + ", ".join(self.note.shared_with[:2])
            if len(self.note.shared_with) > 2:
                shared_text += f" +{len(self.note.shared_with) - 2}"
            self.shared_label = ctk.CTkLabel(
                self.content_frame,
                text=shared_text,
                font=ctk.CTkFont(size=11),
                text_color=COLORS["accent_cyan"],
                anchor="w",
                wraplength=250
            )
            self.shared_label.pack(fill="x", pady=(0, 8))

        if self.note.attachments:
            image_count = sum(1 for attachment in self.note.attachments if attachment.is_image)
            other_count = len(self.note.attachments) - image_count
            parts = []
            if image_count:
                parts.append(f"{image_count} image{'s' if image_count != 1 else ''}")
            if other_count:
                parts.append(f"{other_count} file{'s' if other_count != 1 else ''}")
            self.attachments_label = ctk.CTkLabel(
                self.content_frame,
                text="Attachments: " + ", ".join(parts),
                font=ctk.CTkFont(size=11),
                text_color=COLORS["accent_blue"],
                anchor="w",
                wraplength=250
            )
            self.attachments_label.pack(fill="x", pady=(0, 8))

        if note_uses_markdown(self.note.labels):
            self.markdown_label = ctk.CTkLabel(
                self.content_frame,
                text="Markdown",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=COLORS["accent_cyan"],
                anchor="w"
            )
            self.markdown_label.pack(fill="x", pady=(0, 8))

        # Footer with labels and sync status
        footer = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        footer.pack(fill="x")

        # Labels
        if self.note.labels:
            labels_frame = ctk.CTkFrame(footer, fg_color="transparent")
            labels_frame.pack(side="left", fill="x", expand=True)

            for label in self.note.labels[:3]:
                label_badge = ctk.CTkLabel(
                    labels_frame,
                    text=label,
                    font=ctk.CTkFont(size=10),
                    text_color=COLORS["accent_purple"],
                    fg_color=COLORS["bg_dark"],
                    corner_radius=4,
                    padx=6,
                    pady=2
                )
                label_badge.pack(side="left", padx=(0, 4))

        # Sync status
        self.sync_badge = SyncStatusBadge(footer, self.note.sync_status)
        self.sync_badge.pack(side="right")

        # Action buttons (hidden until hover)
        self.actions_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_light"], corner_radius=8)

        pin_text = "Unpin" if self.note.pinned else "Pin"
        self.pin_btn = ctk.CTkButton(
            self.actions_frame,
            text=pin_text,
            font=ctk.CTkFont(size=11),
            width=50,
            height=26,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_secondary"],
            command=lambda: self.on_pin(self.note)
        )
        self.pin_btn.pack(side="left", padx=2, pady=2)

        self.archive_btn = ctk.CTkButton(
            self.actions_frame,
            text="Archive",
            font=ctk.CTkFont(size=11),
            width=60,
            height=26,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_secondary"],
            command=lambda: self.on_archive(self.note)
        )
        self.archive_btn.pack(side="left", padx=2, pady=2)

        self.delete_btn = ctk.CTkButton(
            self.actions_frame,
            text="Delete",
            font=ctk.CTkFont(size=11),
            width=50,
            height=26,
            fg_color="transparent",
            hover_color=COLORS["accent_red"],
            text_color=COLORS["accent_red"],
            command=lambda: self.on_delete(self.note)
        )
        self.delete_btn.pack(side="left", padx=2, pady=2)

    def _bind_events(self):
        # Click to open
        for widget in [self, self.content_frame, self.title_label]:
            widget.bind("<Button-1>", lambda e: self.on_click(self.note))

        if hasattr(self, 'preview_label'):
            self.preview_label.bind("<Button-1>", lambda e: self.on_click(self.note))

        # Hover effects
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, event):
        self._is_hovered = True
        self.configure(border_color=COLORS["accent_blue"])
        self.actions_frame.place(relx=1.0, rely=0, anchor="ne", x=-8, y=8)

    def _on_leave(self, event):
        self._is_hovered = False
        self.configure(border_color=COLORS["border"])
        self.actions_frame.place_forget()
