"""Note editor panel widget."""

from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, Callable, List, Optional
import threading
import uuid
import webbrowser

import customtkinter as ctk
from PIL import Image, ImageGrab

from keepsync_attachment_editing import (
    IMAGE_FILETYPES,
    copy_image_attachments,
    copy_image_attachment,
    parse_drop_file_paths,
    save_clipboard_image_attachment,
)
from keepsync_audio_recording import (
    AudioRecorder,
    AudioRecordingError,
    AudioTranscriptionError,
    append_audio_transcript,
    transcribe_audio_file,
)
from keepsync_dragdrop import drop_copy_action, enable_file_drop
from keepsync_models import (
    Attachment,
    ChecklistItem,
    KEEP_COLOR_PALETTE,
    Note,
    NoteType,
    SyncStatus,
    clamp_checklist_indent,
    normalize_keep_color,
)
from keepsync_markdown_editing import format_markdown_selection
from keepsync_note_text import (
    format_reminder_datetime,
    markdown_preview_blocks,
    note_uses_markdown,
    parse_reminder_datetime,
)
from keepsync_storage import DatabaseManager
from keepsync_theme import COLORS
from keepsync_ui_components import IconManager, SyncStatusBadge


class NoteEditor(ctk.CTkFrame):
    """Full note editor panel"""

    def __init__(self, parent, db: DatabaseManager, sync_engine: Any,
                 on_save: Callable, on_close: Callable, **kwargs):
        super().__init__(parent, fg_color=COLORS["bg_dark"], **kwargs)

        self.db = db
        self.sync_engine = sync_engine
        self.on_save_callback = on_save
        self.on_close_callback = on_close
        self.current_note: Optional[Note] = None
        self.is_modified = False
        self.selected_color = ""
        self._image_drop_enabled = False
        self._image_drop_target_ids = set()
        self.audio_recorder: Optional[AudioRecorder] = None

        self._build_ui()

    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent", height=50)
        header.pack(fill="x", padx=16, pady=(12, 0))
        header.pack_propagate(False)

        # Close button
        self.close_btn = ctk.CTkButton(
            header,
            text="",
            image=IconManager.get_icon("close", 20, COLORS["text_secondary"]),
            width=36,
            height=36,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            command=self._handle_close
        )
        self.close_btn.pack(side="left")

        # Title
        self.header_title = ctk.CTkLabel(
            header,
            text="New Note",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text_primary"]
        )
        self.header_title.pack(side="left", padx=12)

        # Sync status
        self.sync_badge = SyncStatusBadge(header, SyncStatus.LOCAL_ONLY)
        self.sync_badge.pack(side="left", padx=8)

        # Actions
        actions_frame = ctk.CTkFrame(header, fg_color="transparent")
        actions_frame.pack(side="right")

        self.pin_btn = ctk.CTkButton(
            actions_frame,
            text="",
            image=IconManager.get_icon("pin", 18, COLORS["text_secondary"]),
            width=36,
            height=36,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            command=self._toggle_pin
        )
        self.pin_btn.pack(side="left", padx=2)

        self.save_btn = ctk.CTkButton(
            actions_frame,
            text="Save",
            font=ctk.CTkFont(size=13, weight="bold"),
            width=80,
            height=36,
            fg_color=COLORS["accent_green"],
            hover_color=COLORS["accent_green_hover"],
            text_color=COLORS["bg_darkest"],
            command=self._save_note
        )
        self.save_btn.pack(side="left", padx=(8, 0))

        # Divider
        divider = ctk.CTkFrame(self, fg_color=COLORS["divider"], height=1)
        divider.pack(fill="x", pady=12)

        # Editor content
        editor_frame = ctk.CTkFrame(self, fg_color="transparent")
        editor_frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        # Title input
        self.title_entry = ctk.CTkEntry(
            editor_frame,
            placeholder_text="Title",
            font=ctk.CTkFont(size=20, weight="bold"),
            height=45,
            fg_color="transparent",
            border_width=0,
            text_color=COLORS["text_primary"],
            placeholder_text_color=COLORS["text_muted"]
        )
        self.title_entry.pack(fill="x", pady=(0, 8))
        self.title_entry.bind("<KeyRelease>", self._on_modify)

        # Note type selector
        type_frame = ctk.CTkFrame(editor_frame, fg_color="transparent")
        type_frame.pack(fill="x", pady=(0, 12))

        self.note_type_var = ctk.StringVar(value="note")

        self.note_radio = ctk.CTkRadioButton(
            type_frame,
            text="Text Note",
            variable=self.note_type_var,
            value="note",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"],
            fg_color=COLORS["accent_blue"],
            hover_color=COLORS["accent_blue_hover"],
            command=self._on_type_change
        )
        self.note_radio.pack(side="left", padx=(0, 16))

        self.checklist_radio = ctk.CTkRadioButton(
            type_frame,
            text="Checklist",
            variable=self.note_type_var,
            value="checklist",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"],
            fg_color=COLORS["accent_blue"],
            hover_color=COLORS["accent_blue_hover"],
            command=self._on_type_change
        )
        self.checklist_radio.pack(side="left")

        # Color selector
        color_section = ctk.CTkFrame(editor_frame, fg_color="transparent")
        color_section.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            color_section,
            text="Color",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["text_secondary"]
        ).pack(side="left", padx=(0, 10))

        self.color_buttons = {}
        for color_key, (color_name, color_hex) in KEEP_COLOR_PALETTE.items():
            button = ctk.CTkButton(
                color_section,
                text="",
                width=24,
                height=24,
                fg_color=color_hex,
                hover_color=color_hex,
                border_width=2,
                border_color=COLORS["border"],
                corner_radius=12,
                command=lambda c=color_key: self._select_color(c)
            )
            button.pack(side="left", padx=(0, 5))
            self.color_buttons[color_key] = button

        # Content area (switchable between text and checklist)
        self.content_container = ctk.CTkFrame(editor_frame, fg_color="transparent")
        self.content_container.pack(fill="both", expand=True)

        # Text editor
        self.text_frame = ctk.CTkFrame(self.content_container, fg_color="transparent")

        self.markdown_mode_var = ctk.StringVar(value="Edit")
        self.markdown_controls = ctk.CTkFrame(self.text_frame, fg_color="transparent")
        ctk.CTkLabel(
            self.markdown_controls,
            text="Markdown",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["accent_cyan"]
        ).pack(side="left", padx=(0, 10))

        self.markdown_toolbar = ctk.CTkFrame(self.markdown_controls, fg_color="transparent")
        self.markdown_toolbar.pack(side="left")
        for label, style in (("B", "bold"), ("I", "italic"), ("Code", "code"), ("Link", "link"), ("Task", "task")):
            button = ctk.CTkButton(
                self.markdown_toolbar,
                text=label,
                width=48 if len(label) > 1 else 30,
                height=28,
                font=ctk.CTkFont(size=11, weight="bold" if style == "bold" else "normal"),
                fg_color=COLORS["bg_medium"],
                hover_color=COLORS["bg_hover"],
                text_color=COLORS["text_primary"],
                command=lambda item=style: self._apply_markdown_format(item)
            )
            button.pack(side="left", padx=(0, 4))

        self.markdown_toggle = ctk.CTkSegmentedButton(
            self.markdown_controls,
            values=["Edit", "Preview"],
            variable=self.markdown_mode_var,
            command=self._set_markdown_mode,
            selected_color=COLORS["accent_blue"],
            selected_hover_color=COLORS["accent_blue_hover"],
            unselected_color=COLORS["bg_medium"],
            unselected_hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_primary"],
            height=30
        )
        self.markdown_toggle.pack(side="right")

        self.content_text = ctk.CTkTextbox(
            self.text_frame,
            font=ctk.CTkFont(size=14),
            fg_color=COLORS["bg_medium"],
            border_width=1,
            border_color=COLORS["border"],
            text_color=COLORS["text_primary"],
            corner_radius=8
        )
        self.content_text.pack(fill="both", expand=True)
        self.content_text.bind("<KeyRelease>", self._on_modify)

        self.markdown_preview = ctk.CTkTextbox(
            self.text_frame,
            font=ctk.CTkFont(size=14),
            fg_color=COLORS["bg_medium"],
            border_width=1,
            border_color=COLORS["border"],
            text_color=COLORS["text_primary"],
            corner_radius=8,
            wrap="word"
        )
        self._configure_markdown_preview_tags()

        # Checklist editor
        self.checklist_frame = ctk.CTkFrame(self.content_container, fg_color="transparent")

        self.checklist_scroll = ctk.CTkScrollableFrame(
            self.checklist_frame,
            fg_color=COLORS["bg_medium"],
            corner_radius=8
        )
        self.checklist_scroll.pack(fill="both", expand=True)

        self.add_item_btn = ctk.CTkButton(
            self.checklist_frame,
            text="+ Add Item",
            font=ctk.CTkFont(size=13),
            height=36,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["accent_blue"],
            anchor="w",
            command=self._add_checklist_item
        )
        self.add_item_btn.pack(fill="x", pady=(8, 0))

        # Labels section
        labels_section = ctk.CTkFrame(editor_frame, fg_color="transparent")
        labels_section.pack(fill="x", pady=(12, 0))

        labels_header = ctk.CTkLabel(
            labels_section,
            text="Labels",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["text_secondary"]
        )
        labels_header.pack(anchor="w")

        self.labels_frame = ctk.CTkFrame(labels_section, fg_color="transparent")
        self.labels_frame.pack(fill="x", pady=(4, 0))

        self.label_entry = ctk.CTkEntry(
            self.labels_frame,
            placeholder_text="Add label...",
            font=ctk.CTkFont(size=12),
            width=150,
            height=30,
            fg_color=COLORS["bg_medium"],
            border_width=1,
            border_color=COLORS["border"]
        )
        self.label_entry.pack(side="left")
        self.label_entry.bind("<Return>", self._add_label)

        self.labels_display = ctk.CTkFrame(self.labels_frame, fg_color="transparent")
        self.labels_display.pack(side="left", fill="x", expand=True, padx=(8, 0))

        # Reminder section
        reminder_section = ctk.CTkFrame(editor_frame, fg_color="transparent")
        reminder_section.pack(fill="x", pady=(12, 0))

        ctk.CTkLabel(
            reminder_section,
            text="Reminder",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w")

        reminder_inputs = ctk.CTkFrame(reminder_section, fg_color="transparent")
        reminder_inputs.pack(fill="x", pady=(4, 0))

        self.reminder_entry = ctk.CTkEntry(
            reminder_inputs,
            placeholder_text="YYYY-MM-DD HH:MM",
            font=ctk.CTkFont(size=12),
            width=150,
            height=30,
            fg_color=COLORS["bg_medium"],
            border_width=1,
            border_color=COLORS["border"]
        )
        self.reminder_entry.pack(side="left")
        self.reminder_entry.bind("<KeyRelease>", self._on_modify)

        self.reminder_location_entry = ctk.CTkEntry(
            reminder_inputs,
            placeholder_text="Optional location",
            font=ctk.CTkFont(size=12),
            height=30,
            fg_color=COLORS["bg_medium"],
            border_width=1,
            border_color=COLORS["border"]
        )
        self.reminder_location_entry.pack(side="left", fill="x", expand=True, padx=(8, 0))
        self.reminder_location_entry.bind("<KeyRelease>", self._on_modify)

        self.clear_reminder_btn = ctk.CTkButton(
            reminder_inputs,
            text="Clear",
            font=ctk.CTkFont(size=12),
            width=58,
            height=30,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_secondary"],
            command=self._clear_reminder
        )
        self.clear_reminder_btn.pack(side="left", padx=(8, 0))

        shared_section = ctk.CTkFrame(editor_frame, fg_color="transparent")
        shared_section.pack(fill="x", pady=(12, 0))

        ctk.CTkLabel(
            shared_section,
            text="Shared With",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w")

        self.shared_display = ctk.CTkLabel(
            shared_section,
            text="Not shared",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_muted"],
            anchor="w",
            justify="left",
            wraplength=520
        )
        self.shared_display.pack(fill="x", pady=(4, 0))

        attachments_section = ctk.CTkFrame(editor_frame, fg_color="transparent")
        attachments_section.pack(fill="x", pady=(12, 0))

        attachments_header = ctk.CTkFrame(attachments_section, fg_color="transparent")
        attachments_header.pack(fill="x")

        ctk.CTkLabel(
            attachments_header,
            text="Attachments",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["text_secondary"]
        ).pack(side="left")

        self.add_image_btn = ctk.CTkButton(
            attachments_header,
            text="Add Image",
            font=ctk.CTkFont(size=12),
            width=86,
            height=28,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["accent_blue"],
            command=self._add_image_attachment
        )
        self.add_image_btn.pack(side="right", padx=(8, 0))

        self.paste_image_btn = ctk.CTkButton(
            attachments_header,
            text="Paste Image",
            font=ctk.CTkFont(size=12),
            width=92,
            height=28,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["accent_blue"],
            command=self._paste_image_attachment
        )
        self.paste_image_btn.pack(side="right")

        self.record_audio_btn = ctk.CTkButton(
            attachments_header,
            text="Record Audio",
            font=ctk.CTkFont(size=12),
            width=104,
            height=28,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["accent_cyan"],
            command=self._toggle_audio_recording
        )
        self.record_audio_btn.pack(side="right", padx=(0, 8))

        self.audio_status_label = ctk.CTkLabel(
            attachments_section,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_muted"],
            anchor="w"
        )
        self.audio_status_label.pack(fill="x", pady=(4, 0))

        self.attachments_frame = ctk.CTkFrame(attachments_section, fg_color="transparent")
        self.attachments_frame.pack(fill="x", pady=(4, 0))
        self.attachment_images = []
        self._register_image_drop_targets(
            self,
            editor_frame,
            self.content_container,
            self.text_frame,
            self.content_text,
            self._content_text_widget(),
            self.checklist_frame,
            attachments_section,
            attachments_header,
            self.attachments_frame,
        )

        # Advanced options (collapsible)
        self.advanced_frame = ctk.CTkFrame(editor_frame, fg_color="transparent")
        self.advanced_frame.pack(fill="x", pady=(12, 0))

        # Unlink from Keep button (only shown for synced notes)
        self.unlink_btn = ctk.CTkButton(
            self.advanced_frame,
            text="Unlink from Google Keep",
            font=ctk.CTkFont(size=12),
            height=32,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["accent_red"],
            border_width=1,
            border_color=COLORS["accent_red"],
            command=self._unlink_from_keep
        )

        # Initialize with text editor
        self.text_frame.pack(fill="both", expand=True)
        self.checklist_items_widgets: List[ctk.CTkFrame] = []

    def load_note(self, note: Optional[Note] = None):
        """Load a note into the editor"""
        if note:
            self.current_note = note
            self.header_title.configure(text="Edit Note")

            self.title_entry.delete(0, "end")
            self.title_entry.insert(0, note.title)

            self.note_type_var.set(note.note_type.value)
            self._on_type_change()

            if note.note_type == NoteType.CHECKLIST:
                self._load_checklist_items(note.checklist_items)
            else:
                self.content_text.delete("1.0", "end")
                self.content_text.insert("1.0", note.content)

            self.selected_color = normalize_keep_color(note.color)
            self._refresh_color_buttons()

            self.reminder_entry.delete(0, "end")
            self.reminder_entry.insert(0, format_reminder_datetime(note.reminder_at))
            self.reminder_location_entry.delete(0, "end")
            self.reminder_location_entry.insert(0, note.reminder_location)
            self._load_shared_with(note.shared_with)
            self._load_attachments(note.attachments)

            self._load_labels(note.labels)
            self.sync_badge.update_status(note.sync_status)

            # Show/hide unlink button
            if note.keep_id:
                self.unlink_btn.pack(side="left")
            else:
                self.unlink_btn.pack_forget()

            # Update pin button
            pin_color = COLORS["accent_yellow"] if note.pinned else COLORS["text_secondary"]
            self.pin_btn.configure(image=IconManager.get_icon("pin", 18, pin_color))
        else:
            self.current_note = Note(
                id=str(uuid.uuid4()),
                title="",
                content="",
                sync_status=SyncStatus.LOCAL_ONLY
            )
            self.header_title.configure(text="New Note")

            self.title_entry.delete(0, "end")
            self.content_text.delete("1.0", "end")
            self.note_type_var.set("note")
            self._on_type_change()
            self.selected_color = ""
            self._refresh_color_buttons()
            self._clear_checklist_items()
            self._load_labels([])
            self._clear_reminder(mark_modified=False)
            self._load_shared_with([])
            self._load_attachments([])
            self.sync_badge.update_status(SyncStatus.LOCAL_ONLY)
            self.unlink_btn.pack_forget()
            self.pin_btn.configure(image=IconManager.get_icon("pin", 18, COLORS["text_secondary"]))

        self.is_modified = False

    def _on_modify(self, event=None):
        """Mark note as modified"""
        self.is_modified = True

    def _register_image_drop_targets(self, *widgets):
        """Register widgets as native file drop targets when the optional bridge is available."""
        for widget in widgets:
            if not widget:
                continue
            target_id = str(widget)
            if target_id in self._image_drop_target_ids:
                continue
            if enable_file_drop(widget, self._handle_image_drop):
                self._image_drop_target_ids.add(target_id)
                self._image_drop_enabled = True

    def _register_image_drop_tree(self, widget):
        """Register a widget and its current children as image drop targets."""
        self._register_image_drop_targets(widget)
        try:
            children = widget.winfo_children()
        except Exception:
            return
        for child in children:
            self._register_image_drop_tree(child)

    def _content_text_widget(self):
        return getattr(self.content_text, "_textbox", self.content_text)

    def _apply_markdown_format(self, style: str):
        """Apply markdown formatting to the current selection or insert placeholder text."""
        if self.markdown_mode_var.get() == "Preview":
            self.markdown_mode_var.set("Edit")
            self._refresh_markdown_controls()

        widget = self._content_text_widget()
        try:
            start = widget.index("sel.first")
            end = widget.index("sel.last")
            selected = widget.get(start, end)
        except Exception:
            start = widget.index("insert")
            end = start
            selected = ""

        replacement = format_markdown_selection(selected, style)
        if selected:
            widget.delete(start, end)
        widget.insert(start, replacement)
        try:
            widget.tag_remove("sel", "1.0", "end")
            widget.tag_add("sel", start, f"{start}+{len(replacement)}c")
            widget.mark_set("insert", f"{start}+{len(replacement)}c")
        except Exception:
            pass
        self._on_modify()
        if self.markdown_mode_var.get() == "Preview":
            self._render_markdown_preview()

    def _markdown_preview_widget(self):
        return getattr(self.markdown_preview, "_textbox", self.markdown_preview)

    def _configure_markdown_preview_tags(self):
        widget = self._markdown_preview_widget()
        widget.tag_configure("paragraph", foreground=COLORS["text_primary"], font=("Segoe UI", 13), spacing3=4)
        widget.tag_configure("heading_1", foreground=COLORS["text_primary"], font=("Segoe UI", 22, "bold"), spacing1=8, spacing3=6)
        widget.tag_configure("heading_2", foreground=COLORS["text_primary"], font=("Segoe UI", 18, "bold"), spacing1=8, spacing3=5)
        widget.tag_configure("heading_3", foreground=COLORS["text_primary"], font=("Segoe UI", 15, "bold"), spacing1=6, spacing3=4)
        widget.tag_configure("list_item", foreground=COLORS["text_primary"], lmargin1=18, lmargin2=30, spacing3=3)
        widget.tag_configure("task", foreground=COLORS["text_primary"], lmargin1=18, lmargin2=30, spacing3=3)
        widget.tag_configure("quote", foreground=COLORS["text_secondary"], lmargin1=18, lmargin2=18, spacing1=4, spacing3=4)
        widget.tag_configure("code_block", foreground=COLORS["accent_cyan"], background=COLORS["bg_darkest"], font=("Consolas", 12), lmargin1=12, lmargin2=12, spacing1=3, spacing3=3)
        widget.tag_configure("bold", font=("Segoe UI", 13, "bold"))
        widget.tag_configure("italic", font=("Segoe UI", 13, "italic"))
        widget.tag_configure("inline_code", foreground=COLORS["accent_cyan"], background=COLORS["bg_darkest"], font=("Consolas", 12))

    def _markdown_enabled(self) -> bool:
        return (
            self.current_note is not None
            and self.note_type_var.get() == NoteType.NOTE.value
            and note_uses_markdown(self.current_note.labels)
        )

    def _set_markdown_mode(self, value: str):
        self.markdown_mode_var.set(value)
        self._refresh_markdown_controls()

    def _refresh_markdown_controls(self):
        if not hasattr(self, "markdown_controls"):
            return

        self.markdown_controls.pack_forget()
        self.content_text.pack_forget()
        self.markdown_preview.pack_forget()

        if not self._markdown_enabled():
            self.markdown_mode_var.set("Edit")
            self.content_text.pack(fill="both", expand=True)
            return

        self.markdown_controls.pack(fill="x", pady=(0, 8))
        if self.markdown_mode_var.get() == "Preview":
            self._render_markdown_preview()
            self.markdown_preview.pack(fill="both", expand=True)
        else:
            self.content_text.pack(fill="both", expand=True)

    def _render_markdown_preview(self):
        widget = self._markdown_preview_widget()
        widget.configure(state="normal")
        widget.delete("1.0", "end")

        for block in markdown_preview_blocks(self.content_text.get("1.0", "end-1c")):
            segments = block["segments"]
            if not segments:
                widget.insert("end", "\n")
                continue

            line_style = block["style"]
            for segment in segments:
                text = segment["text"]
                if not text:
                    continue
                start = widget.index("end-1c")
                widget.insert("end", text)
                end = widget.index("end-1c")
                widget.tag_add(line_style, start, end)
                if segment["style"] != "plain":
                    widget.tag_add(segment["style"], start, end)
            widget.insert("end", "\n")

        widget.configure(state="disabled")

    def _select_color(self, color: str):
        """Select a Keep color for the note."""
        self.selected_color = normalize_keep_color(color)
        self._refresh_color_buttons()
        self._on_modify()

    def _refresh_color_buttons(self):
        """Update color selector button borders."""
        if not hasattr(self, "color_buttons"):
            return
        for color_key, button in self.color_buttons.items():
            is_selected = color_key == self.selected_color
            button.configure(
                border_color=COLORS["text_primary"] if is_selected else COLORS["border"],
                border_width=3 if is_selected else 2
            )

    def _clear_reminder(self, mark_modified: bool = True):
        """Clear reminder inputs."""
        self.reminder_entry.delete(0, "end")
        self.reminder_location_entry.delete(0, "end")
        if mark_modified:
            self._on_modify()

    def _load_shared_with(self, shared_with: List[str]):
        """Display imported sharing metadata."""
        if shared_with:
            self.shared_display.configure(
                text=", ".join(shared_with),
                text_color=COLORS["accent_cyan"]
            )
        else:
            self.shared_display.configure(
                text="Not shared",
                text_color=COLORS["text_muted"]
            )

    def _load_attachments(self, attachments: List[Attachment]):
        """Render imported attachments in the editor."""
        for widget in self.attachments_frame.winfo_children():
            widget.destroy()
        self.attachment_images.clear()

        if not attachments:
            ctk.CTkLabel(
                self.attachments_frame,
                text="No attachments - drop images here or use Add/Paste",
                font=ctk.CTkFont(size=12),
                text_color=COLORS["text_muted"],
                anchor="w"
            ).pack(anchor="w")
            self._register_image_drop_tree(self.attachments_frame)
            return

        for attachment in attachments:
            row = ctk.CTkFrame(self.attachments_frame, fg_color=COLORS["bg_medium"], corner_radius=8)
            row.pack(fill="x", pady=(0, 6))

            if attachment.is_image and attachment.exists:
                try:
                    image = Image.open(attachment.stored_path)
                    image.thumbnail((180, 120))
                    ctk_image = ctk.CTkImage(light_image=image.copy(), dark_image=image.copy(), size=image.size)
                    self.attachment_images.append(ctk_image)
                    preview = ctk.CTkLabel(row, text="", image=ctk_image)
                    preview.pack(side="left", padx=8, pady=8)
                except Exception:
                    pass

            details = ctk.CTkFrame(row, fg_color="transparent")
            details.pack(side="left", fill="x", expand=True, padx=8, pady=8)

            ctk.CTkLabel(
                details,
                text=attachment.filename,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=COLORS["text_primary"],
                anchor="w"
            ).pack(fill="x")

            ctk.CTkLabel(
                details,
                text=attachment.mime_type,
                font=ctk.CTkFont(size=11),
                text_color=COLORS["text_muted"],
                anchor="w"
            ).pack(fill="x")

            open_btn = ctk.CTkButton(
                row,
                text="Open",
                font=ctk.CTkFont(size=12),
                width=58,
                height=30,
                fg_color="transparent",
                hover_color=COLORS["bg_hover"],
                text_color=COLORS["accent_blue"],
                command=lambda item=attachment: self._open_attachment(item)
            )
            open_btn.pack(side="right", padx=8)

        self._register_image_drop_tree(self.attachments_frame)

    def _open_attachment(self, attachment: Attachment):
        """Open an attachment with the system default handler."""
        target = attachment.stored_path
        try:
            path = Path(target)
            if path.exists():
                webbrowser.open(path.resolve().as_uri())
                return
        except (OSError, ValueError):
            pass
        if target:
            webbrowser.open(target)

    def _add_image_attachment(self):
        """Copy an image file into the note attachment store."""
        if not self.current_note:
            return
        path = filedialog.askopenfilename(title="Add Image", filetypes=IMAGE_FILETYPES)
        if not path:
            return
        try:
            attachment = copy_image_attachment(Path(path), self.db.db_path, self.current_note.id)
        except Exception as e:
            messagebox.showerror("Add Image Failed", str(e))
            return
        self.current_note.attachments.append(attachment)
        self._load_attachments(self.current_note.attachments)
        self._on_modify()

    def _paste_image_attachment(self):
        """Paste a clipboard image into the note attachment store."""
        if not self.current_note:
            return
        try:
            clipboard = ImageGrab.grabclipboard()
            if isinstance(clipboard, Image.Image):
                attachment = save_clipboard_image_attachment(clipboard, self.db.db_path, self.current_note.id)
            elif isinstance(clipboard, list) and clipboard:
                attachment = copy_image_attachment(Path(clipboard[0]), self.db.db_path, self.current_note.id)
            else:
                messagebox.showinfo("No Image", "Clipboard does not contain an image.")
                return
        except Exception as e:
            messagebox.showerror("Paste Image Failed", str(e))
            return
        self.current_note.attachments.append(attachment)
        self._load_attachments(self.current_note.attachments)
        self._on_modify()

    def _handle_image_drop(self, event):
        """Copy dropped image files into the note attachment store."""
        if not self.current_note:
            return drop_copy_action()

        paths = parse_drop_file_paths(getattr(event, "data", ""), splitlist=self.tk.splitlist)
        if not paths:
            messagebox.showinfo("No Image", "Drop image files to attach them.")
            return drop_copy_action()

        result = copy_image_attachments(paths, self.db.db_path, self.current_note.id)
        if result.attachments:
            self.current_note.attachments.extend(result.attachments)
            self._load_attachments(self.current_note.attachments)
            self._on_modify()

        if result.failed_paths and not result.attachments:
            first_path, first_error = result.failed_paths[0]
            messagebox.showerror(
                "Drop Image Failed",
                f"No images were attached.\n{first_path.name}: {first_error}"
            )
        elif not result.attachments:
            messagebox.showinfo("No Image", "Drop image files to attach them.")
        elif result.skipped_paths or result.failed_paths:
            lines = [f"Attached {len(result.attachments)} image file(s)."]
            if result.skipped_paths:
                lines.append(f"Skipped {len(result.skipped_paths)} non-image file(s).")
            if result.failed_paths:
                lines.append(f"Failed {len(result.failed_paths)} image file(s).")
            messagebox.showwarning("Some Files Skipped", "\n".join(lines))

        return drop_copy_action()

    def _toggle_audio_recording(self):
        """Start or stop inline voice note recording."""
        if self.audio_recorder and self.audio_recorder.is_recording:
            self._stop_audio_recording()
        else:
            self._start_audio_recording()

    def _start_audio_recording(self):
        if not self.current_note:
            return
        try:
            self.audio_recorder = AudioRecorder()
            self.audio_recorder.start()
        except AudioRecordingError as e:
            self.audio_recorder = None
            messagebox.showerror("Audio Recording Failed", str(e))
            return

        self.record_audio_btn.configure(
            text="Stop Audio",
            fg_color=COLORS["accent_red"],
            hover_color=COLORS["accent_red"],
            text_color=COLORS["text_primary"],
        )
        self._set_audio_status("Recording voice note...")

    def _stop_audio_recording(self):
        if not self.current_note or not self.audio_recorder:
            return
        recorder = self.audio_recorder
        self.audio_recorder = None
        try:
            attachment = recorder.stop_to_attachment(self.db.db_path, self.current_note.id)
        except AudioRecordingError as e:
            self._reset_audio_record_button()
            messagebox.showerror("Audio Recording Failed", str(e))
            return

        self._reset_audio_record_button()
        self.current_note.attachments.append(attachment)
        self._load_attachments(self.current_note.attachments)
        self._on_modify()
        self._set_audio_status("Audio saved. Transcribing...")
        self._transcribe_audio_attachment(attachment)

    def _reset_audio_record_button(self):
        self.record_audio_btn.configure(
            text="Record Audio",
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["accent_cyan"],
        )

    def _set_audio_status(self, text: str, error: bool = False):
        self.audio_status_label.configure(
            text=text,
            text_color=COLORS["accent_red"] if error else COLORS["text_muted"],
        )

    def _transcribe_audio_attachment(self, attachment: Attachment):
        thread = threading.Thread(
            target=self._transcribe_audio_worker,
            args=(attachment,),
            daemon=True,
        )
        thread.start()

    def _transcribe_audio_worker(self, attachment: Attachment):
        try:
            transcript = transcribe_audio_file(Path(attachment.stored_path))
        except AudioTranscriptionError as e:
            self._after_safe(lambda: self._set_audio_status(str(e), error=True))
            return
        self._after_safe(lambda: self._apply_audio_transcript(transcript))

    def _after_safe(self, callback: Callable):
        try:
            self.after(0, callback)
        except Exception:
            pass

    def _apply_audio_transcript(self, transcript: str):
        text = transcript.strip()
        if not text:
            self._set_audio_status("Audio saved. No speech detected.")
            return

        if self.note_type_var.get() == "checklist":
            self._add_checklist_item(f"Audio transcript: {text}", focus=False)
        else:
            updated = append_audio_transcript(self.content_text.get("1.0", "end-1c"), text)
            self.content_text.delete("1.0", "end")
            self.content_text.insert("1.0", updated)
            if self.markdown_mode_var.get() == "Preview":
                self._render_markdown_preview()
            self._on_modify()
        self._set_audio_status("Audio transcribed into the note.")

    def _on_type_change(self):
        """Switch between text and checklist editor"""
        if self.note_type_var.get() == "checklist":
            self.text_frame.pack_forget()
            self.checklist_frame.pack(fill="both", expand=True)
        else:
            self.checklist_frame.pack_forget()
            self.text_frame.pack(fill="both", expand=True)
        self._refresh_markdown_controls()
        self._on_modify()

    def _toggle_pin(self):
        """Toggle note pinned status"""
        if self.current_note:
            self.current_note.pinned = not self.current_note.pinned
            pin_color = COLORS["accent_yellow"] if self.current_note.pinned else COLORS["text_secondary"]
            self.pin_btn.configure(image=IconManager.get_icon("pin", 18, pin_color))
            self._on_modify()

    def _add_checklist_item(
        self,
        text: str = "",
        checked: bool = False,
        item_id: Optional[str] = None,
        indent: int = 0,
        focus: bool = True
    ):
        """Add a checklist item widget."""
        item_frame = ctk.CTkFrame(self.checklist_scroll, fg_color="transparent")
        item_frame.item_id = item_id or str(uuid.uuid4())
        item_frame.indent = clamp_checklist_indent(indent)

        drag_handle = ctk.CTkLabel(
            item_frame,
            text="::",
            width=22,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLORS["text_muted"]
        )
        drag_handle.pack(side="left", padx=(4, 4))
        drag_handle.bind("<ButtonPress-1>", lambda e, frame=item_frame: self._start_checklist_drag(frame))
        drag_handle.bind("<ButtonRelease-1>", lambda e, frame=item_frame: self._finish_checklist_drag(frame, e))

        check_var = ctk.BooleanVar(value=checked)
        checkbox = ctk.CTkCheckBox(
            item_frame,
            text="",
            variable=check_var,
            width=24,
            height=24,
            fg_color=COLORS["accent_green"],
            hover_color=COLORS["accent_green_hover"],
            border_color=COLORS["border_light"],
            command=self._on_modify
        )
        checkbox.pack(side="left", padx=(0, 8))

        entry = ctk.CTkEntry(
            item_frame,
            placeholder_text="List item",
            font=ctk.CTkFont(size=13),
            fg_color="transparent",
            border_width=0,
            text_color=COLORS["text_primary"]
        )
        entry.pack(side="left", fill="x", expand=True)
        entry.insert(0, text)
        entry.bind("<KeyRelease>", self._on_modify)
        entry.bind("<Return>", lambda e: self._add_checklist_item())

        for label, delta in (("<", -1), (">", 1)):
            indent_btn = ctk.CTkButton(
                item_frame,
                text=label,
                width=24,
                height=24,
                fg_color="transparent",
                hover_color=COLORS["bg_hover"],
                text_color=COLORS["text_muted"],
                command=lambda d=delta, frame=item_frame: self._adjust_checklist_indent(frame, d)
            )
            indent_btn.pack(side="right", padx=(2, 0))

        down_btn = ctk.CTkButton(
            item_frame,
            text="Dn",
            width=32,
            height=24,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_muted"],
            command=lambda: self._move_checklist_item(item_frame, 1)
        )
        down_btn.pack(side="right", padx=(2, 0))

        up_btn = ctk.CTkButton(
            item_frame,
            text="Up",
            width=32,
            height=24,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_muted"],
            command=lambda: self._move_checklist_item(item_frame, -1)
        )
        up_btn.pack(side="right", padx=(2, 0))

        delete_btn = ctk.CTkButton(
            item_frame,
            text="x",
            width=24,
            height=24,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_muted"],
            command=lambda: self._remove_checklist_item(item_frame)
        )
        delete_btn.pack(side="right", padx=(4, 4))

        item_frame.check_var = check_var
        item_frame.entry = entry
        self.checklist_items_widgets.append(item_frame)
        self._repack_checklist_items()

        if focus:
            entry.focus_set()
        self._on_modify()

    def _repack_checklist_items(self):
        """Pack checklist rows in stored order with visual indentation."""
        for widget in self.checklist_items_widgets:
            widget.pack_forget()
            widget.pack(fill="x", pady=2, padx=(4 + widget.indent * 24, 4))

    def _move_checklist_item(self, item_frame, delta: int):
        """Move a checklist item up or down."""
        try:
            index = self.checklist_items_widgets.index(item_frame)
        except ValueError:
            return
        new_index = max(0, min(len(self.checklist_items_widgets) - 1, index + delta))
        if new_index == index:
            return
        self.checklist_items_widgets.pop(index)
        self.checklist_items_widgets.insert(new_index, item_frame)
        self._repack_checklist_items()
        self._on_modify()

    def _adjust_checklist_indent(self, item_frame, delta: int):
        """Indent or outdent a checklist item."""
        item_frame.indent = max(0, min(4, item_frame.indent + delta))
        self._repack_checklist_items()
        self._on_modify()

    def _start_checklist_drag(self, item_frame):
        """Record which checklist row is being dragged."""
        self._dragging_checklist_item = item_frame
        item_frame.configure(fg_color=COLORS["bg_light"])

    def _finish_checklist_drag(self, item_frame, event):
        """Drop a dragged checklist row near the row under the pointer."""
        if getattr(self, "_dragging_checklist_item", None) is not item_frame:
            return

        others = [widget for widget in self.checklist_items_widgets if widget is not item_frame]
        insert_at = len(others)
        for index, widget in enumerate(others):
            midpoint = widget.winfo_rooty() + (widget.winfo_height() / 2)
            if event.y_root < midpoint:
                insert_at = index
                break

        self.checklist_items_widgets = others
        self.checklist_items_widgets.insert(insert_at, item_frame)
        item_frame.configure(fg_color="transparent")
        self._dragging_checklist_item = None
        self._repack_checklist_items()
        self._on_modify()

    def _remove_checklist_item(self, item_frame):
        """Remove a checklist item widget."""
        item_frame.destroy()
        if item_frame in self.checklist_items_widgets:
            self.checklist_items_widgets.remove(item_frame)
        self._on_modify()

    def _clear_checklist_items(self):
        """Clear all checklist item widgets."""
        for widget in self.checklist_items_widgets:
            widget.destroy()
        self.checklist_items_widgets.clear()

    def _load_checklist_items(self, items: List[ChecklistItem]):
        """Load checklist items into widgets."""
        self._clear_checklist_items()
        for item in items:
            self._add_checklist_item(item.text, item.checked, item.id, item.indent, focus=False)

    def _add_label(self, event=None):
        """Add a label to the note"""
        label_text = self.label_entry.get().strip()
        if label_text and self.current_note:
            if label_text not in self.current_note.labels:
                self.current_note.labels.append(label_text)
                self._load_labels(self.current_note.labels)
                self._on_modify()
            self.label_entry.delete(0, "end")

    def _remove_label(self, label: str):
        """Remove a label from the note"""
        if self.current_note and label in self.current_note.labels:
            self.current_note.labels.remove(label)
            self._load_labels(self.current_note.labels)
            self._on_modify()

    def _load_labels(self, labels: List[str]):
        """Load labels into display"""
        for widget in self.labels_display.winfo_children():
            widget.destroy()

        for label in labels:
            label_frame = ctk.CTkFrame(
                self.labels_display,
                fg_color=COLORS["accent_purple"],
                corner_radius=12
            )
            label_frame.pack(side="left", padx=(0, 4))

            label_text = ctk.CTkLabel(
                label_frame,
                text=label,
                font=ctk.CTkFont(size=11),
                text_color=COLORS["bg_darkest"]
            )
            label_text.pack(side="left", padx=(8, 4), pady=4)

            remove_btn = ctk.CTkButton(
                label_frame,
                text="×",
                width=16,
                height=16,
                fg_color="transparent",
                hover_color=COLORS["accent_purple"],
                text_color=COLORS["bg_darkest"],
                command=lambda l=label: self._remove_label(l)
            )
            remove_btn.pack(side="left", padx=(0, 4))

        self._refresh_markdown_controls()

    def _save_note(self):
        """Save the current note"""
        if not self.current_note:
            return

        # Update note data
        self.current_note.title = self.title_entry.get()
        self.current_note.note_type = NoteType(self.note_type_var.get())
        self.current_note.color = self.selected_color
        previous_reminder = self.current_note.reminder_at

        try:
            self.current_note.reminder_at = parse_reminder_datetime(self.reminder_entry.get())
        except ValueError as e:
            messagebox.showerror("Invalid Reminder", str(e))
            return

        self.current_note.reminder_location = self.reminder_location_entry.get().strip()
        if self.current_note.reminder_at != previous_reminder:
            self.current_note.reminder_notified = False

        if self.current_note.note_type == NoteType.CHECKLIST:
            self.current_note.checklist_items = [
                ChecklistItem(
                    id=widget.item_id,
                    text=widget.entry.get(),
                    checked=widget.check_var.get(),
                    indent=widget.indent
                )
                for widget in self.checklist_items_widgets
                if widget.entry.get().strip()
            ]
            self.current_note.content = ""
        else:
            self.current_note.content = self.content_text.get("1.0", "end-1c")
            self.current_note.checklist_items = []

        self.current_note.local_modified = datetime.now(timezone.utc)

        # Update sync status if linked to Keep
        if self.current_note.keep_id:
            self.current_note.sync_status = SyncStatus.PENDING_PUSH

        # Save to database
        if self.db.save_note(self.current_note):
            self.is_modified = False
            self.sync_badge.update_status(self.current_note.sync_status)
            self.on_save_callback(self.current_note)

    def _unlink_from_keep(self):
        """Unlink the note from Google Keep"""
        if not self.current_note or not self.current_note.keep_id:
            return

        result = messagebox.askyesnocancel(
            "Unlink from Google Keep",
            "Do you want to delete this note from Google Keep?\n\n"
            "• Yes: Delete from Keep, keep locally\n"
            "• No: Just unlink (keep in both places)\n"
            "• Cancel: Don't unlink"
        )

        if result is None:  # Cancel
            return

        if self.sync_engine.unlink_note(self.current_note.id, delete_from_keep=result):
            self.current_note.keep_id = None
            self.current_note.sync_status = SyncStatus.LOCAL_ONLY
            self.sync_badge.update_status(SyncStatus.LOCAL_ONLY)
            self.unlink_btn.pack_forget()
            self.on_save_callback(self.current_note)

    def _handle_close(self):
        """Handle close with unsaved changes check"""
        if self.audio_recorder and self.audio_recorder.is_recording:
            self._stop_audio_recording()

        if self.is_modified:
            result = messagebox.askyesnocancel(
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save before closing?"
            )
            if result is None:  # Cancel
                return
            if result:  # Yes
                self._save_note()

        self.on_close_callback()
