# Main CustomTkinter application shell.

from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, Dict, List, Optional
import json
import threading
import time
import uuid

import customtkinter as ctk

from keepsync_app_info import APP_NAME, APP_VERSION, DB_VERSION
from keepsync_backups import LocalBackupManager
from keepsync_cloud_sync import CloudSyncManager
from keepsync_daily_review import pick_review_notes, review_summary
from keepsync_credentials import KEYRING_AVAILABLE
from keepsync_diagnostics import (
    DiagnosticsManager,
    log_diagnostic_event,
    log_diagnostic_exception,
    set_diagnostics_manager,
)
from keepsync_folders import (
    folder_display_name,
    folder_path_depth,
    folder_paths_from_labels,
    normalize_folder_path,
    note_matches_folder,
)
from keepsync_import_reports import IMPORT_SUCCESS_STATUSES, import_summary_lines
from keepsync_importers import MultiSourceImporter
from keepsync_import_safety import (
    MAX_IMPORT_FOLDER_BYTES,
    MAX_IMPORT_FOLDER_FILES,
    MAX_IMPORT_TEXT_MEMBER_BYTES,
    MAX_IMPORT_ZIP_MEMBERS,
    MAX_IMPORT_ZIP_UNCOMPRESSED_BYTES,
    ImportCancelled,
    ImportSafetyError,
    guarded_import_files,
    validate_zip_members,
)
from keepsync_keep_sync import GKEEPAPI_AVAILABLE, KeepSyncEngine, KeepWebScraper
from keepsync_models import Label, Note, NoteType, SyncStatus
from keepsync_note_editor import NoteEditor
from keepsync_note_ops import (
    advanced_filters_active,
    default_advanced_filters,
    note_matches_advanced_filters,
)
from keepsync_paths import get_app_data_dir
from keepsync_settings_dialog import SettingsDialog
from keepsync_storage import DatabaseManager
from keepsync_tag_graph import build_tag_graph, tag_graph_summary_lines
from keepsync_theme import COLORS, set_theme
from keepsync_tray import TRAY_AVAILABLE, SystemTray
from keepsync_ui_components import IconManager, NoteCard
from keepsync_ui_dialogs import (
    AdvancedFilterDialog,
    ImportConflictDialog,
    TakeoutInstructionsDialog,
    TokenGeneratorDialog,
)
from keepsync_ui_modal import configure_modal_dialog

try:
    from plyer import notification as desktop_notification
    DESKTOP_NOTIFICATIONS_AVAILABLE = True
except ImportError:
    desktop_notification = None
    DESKTOP_NOTIFICATIONS_AVAILABLE = False


class KeepSyncNotesApp(ctk.CTk):
    """Main application window"""

    def __init__(self):
        super().__init__()

        # Configure window
        self.title(APP_NAME)
        self.geometry("1200x800")
        self.minsize(900, 600)
        self.configure(fg_color=COLORS["bg_darkest"])

        # Set up data directory
        self.data_dir = get_app_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.diagnostics = DiagnosticsManager(
            self.data_dir,
            APP_NAME,
            APP_VERSION,
            {
                "keyring_available": KEYRING_AVAILABLE,
                "gkeepapi_available": GKEEPAPI_AVAILABLE,
                "desktop_notifications_available": DESKTOP_NOTIFICATIONS_AVAILABLE,
            },
        )
        set_diagnostics_manager(self.diagnostics)
        self.diagnostics.install_hooks()
        self.diagnostics.log_event("info", f"Started {APP_NAME} v{APP_VERSION}")

        # Initialize database and sync engine
        self.db = DatabaseManager(str(self.data_dir / "notes.db"))
        self.sync_engine = KeepSyncEngine(self.db)
        self.sync_engine.add_sync_callback(self._on_sync_status_change)

        # Initialize cloud sync manager
        self.cloud_sync = CloudSyncManager(self.db, APP_NAME, APP_VERSION, DB_VERSION)
        self.cloud_sync.add_callback(self._on_cloud_sync_status_change)

        # Apply saved theme before building UI
        saved_theme = self.db.get_setting("theme", "dark")
        if saved_theme != "dark":
            set_theme(saved_theme)

        # State
        self.current_filter = "all"  # all, archived, trash, label:<name>
        self.search_query = ""
        self.advanced_filters = default_advanced_filters()
        self.pending_delete_undo_note_id: Optional[str] = None
        self.saved_searches = self.db.get_setting("saved_searches", [])
        if not isinstance(self.saved_searches, list):
            self.saved_searches = []
        self.selected_note: Optional[Note] = None
        self._reminder_after_id = None
        self._takeout_watch_after_id = None
        self._takeout_watch_in_progress = False

        # Build UI
        self._build_ui()

        # Try auto-login to Keep
        self.after(1000, self._try_auto_connect)

        # Try to restore cloud sync
        self.after(1500, self._try_restore_cloud_sync)

        # Load notes
        self._refresh_notes_list()
        self._schedule_reminder_check(delay_ms=1000)
        self._schedule_takeout_watch_check(delay_ms=5000)

        # Start auto-sync if enabled
        if self.db.get_setting("auto_sync", True):
            interval = self.db.get_setting("sync_interval", 5)
            self.sync_engine.start_auto_sync(interval)

        # System tray
        self._tray: Optional[SystemTray] = None
        if TRAY_AVAILABLE and self.db.get_setting("system_tray", True):
            self._start_tray()

    def _build_ui(self):
        """Build the main UI"""
        # Main container with sidebar and content
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True)

        # Configure grid
        self.main_container.grid_columnconfigure(0, weight=0, minsize=240)  # Sidebar
        self.main_container.grid_columnconfigure(1, weight=1, minsize=300)  # Notes list
        self.main_container.grid_columnconfigure(2, weight=2, minsize=400)  # Editor
        self.main_container.grid_rowconfigure(0, weight=1)

        # Sidebar
        self._build_sidebar()

        # Notes list
        self._build_notes_list()

        # Editor panel (initially hidden)
        self._build_editor()

    def _build_sidebar(self):
        """Build the sidebar with navigation"""
        sidebar = ctk.CTkFrame(
            self.main_container,
            fg_color=COLORS["bg_dark"],
            corner_radius=0
        )
        sidebar.grid(row=0, column=0, sticky="nsew")

        # Logo/Title
        logo_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        logo_frame.pack(fill="x", padx=16, pady=20)

        title = ctk.CTkLabel(
            logo_frame,
            text="KeepSync",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=COLORS["accent_green"]
        )
        title.pack(anchor="w")

        subtitle = ctk.CTkLabel(
            logo_frame,
            text="Notes",
            font=ctk.CTkFont(size=14),
            text_color=COLORS["text_muted"]
        )
        subtitle.pack(anchor="w")

        # New Note button
        new_btn = ctk.CTkButton(
            sidebar,
            text="New Note",
            image=IconManager.get_icon("plus", 18, COLORS["bg_darkest"]),
            font=ctk.CTkFont(size=14, weight="bold"),
            height=44,
            fg_color=COLORS["accent_green"],
            hover_color=COLORS["accent_green_hover"],
            text_color=COLORS["bg_darkest"],
            corner_radius=10,
            command=self._new_note
        )
        new_btn.pack(fill="x", padx=16, pady=(0, 20))

        # Navigation items
        nav_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        nav_frame.pack(fill="x", padx=8)

        self.nav_buttons = {}
        nav_items = [
            ("all", "All Notes", "note"),
            ("archived", "Archive", "archive"),
            ("trash", "Trash", "trash"),
        ]

        for key, text, icon in nav_items:
            btn = ctk.CTkButton(
                nav_frame,
                text=text,
                image=IconManager.get_icon(icon, 18, COLORS["text_secondary"]),
                font=ctk.CTkFont(size=13),
                height=40,
                fg_color="transparent",
                hover_color=COLORS["bg_hover"],
                text_color=COLORS["text_secondary"],
                anchor="w",
                command=lambda k=key: self._set_filter(k)
            )
            btn.pack(fill="x", pady=2)
            self.nav_buttons[key] = btn

        tag_graph_btn = ctk.CTkButton(
            nav_frame,
            text="Tag Graph",
            image=IconManager.get_icon("label", 18, COLORS["accent_purple"]),
            font=ctk.CTkFont(size=13),
            height=40,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_secondary"],
            anchor="w",
            command=self._open_tag_graph
        )
        tag_graph_btn.pack(fill="x", pady=2)

        review_btn = ctk.CTkButton(
            nav_frame,
            text="Daily Review",
            image=IconManager.get_icon("sync", 18, COLORS["accent_cyan"]),
            font=ctk.CTkFont(size=13),
            height=40,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_secondary"],
            anchor="w",
            command=self._open_daily_review
        )
        review_btn.pack(fill="x", pady=2)

        # Folders section
        folders_header = ctk.CTkFrame(sidebar, fg_color="transparent")
        folders_header.pack(fill="x", padx=16, pady=(20, 8))

        ctk.CTkLabel(
            folders_header,
            text="FOLDERS",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLORS["text_muted"]
        ).pack(side="left")

        add_folder_btn = ctk.CTkButton(
            folders_header,
            text="+",
            width=24,
            height=24,
            font=ctk.CTkFont(size=14),
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_muted"],
            command=self._add_folder_dialog
        )
        add_folder_btn.pack(side="right")

        self.folders_frame = ctk.CTkScrollableFrame(
            sidebar,
            fg_color="transparent",
            height=150
        )
        self.folders_frame.pack(fill="x", padx=8)

        # Labels section
        labels_header = ctk.CTkFrame(sidebar, fg_color="transparent")
        labels_header.pack(fill="x", padx=16, pady=(20, 8))

        ctk.CTkLabel(
            labels_header,
            text="LABELS",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLORS["text_muted"]
        ).pack(side="left")

        add_label_btn = ctk.CTkButton(
            labels_header,
            text="+",
            width=24,
            height=24,
            font=ctk.CTkFont(size=14),
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_muted"],
            command=self._add_label_dialog
        )
        add_label_btn.pack(side="right")

        self.labels_frame = ctk.CTkScrollableFrame(
            sidebar,
            fg_color="transparent",
            height=200
        )
        self.labels_frame.pack(fill="x", padx=8)

        ctk.CTkLabel(
            sidebar,
            text="SAVED SEARCHES",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLORS["text_muted"]
        ).pack(anchor="w", padx=16, pady=(16, 8))

        self.saved_searches_frame = ctk.CTkScrollableFrame(
            sidebar,
            fg_color="transparent",
            height=120
        )
        self.saved_searches_frame.pack(fill="x", padx=8)

        # Sync status section
        sync_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        sync_frame.pack(fill="x", side="bottom", padx=16, pady=16)

        self.sync_status_label = ctk.CTkLabel(
            sync_frame,
            text="Offline",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_muted"]
        )
        self.sync_status_label.pack(side="left")

        self.undo_delete_btn = ctk.CTkButton(
            sync_frame,
            text="Undo",
            width=54,
            height=28,
            font=ctk.CTkFont(size=12),
            fg_color=COLORS["accent_blue"],
            hover_color=COLORS["accent_blue_hover"],
            command=self._undo_delete_note
        )
        self.undo_delete_btn.pack(side="left", padx=(8, 0))
        self.undo_delete_btn.pack_forget()

        self.sync_btn = ctk.CTkButton(
            sync_frame,
            text="",
            image=IconManager.get_icon("sync", 18, COLORS["text_secondary"]),
            width=36,
            height=36,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            command=self._cloud_sync_now
        )
        self.sync_btn.pack(side="right")

        settings_btn = ctk.CTkButton(
            sync_frame,
            text="",
            image=IconManager.get_icon("settings", 18, COLORS["text_secondary"]),
            width=36,
            height=36,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            command=self._open_settings
        )
        settings_btn.pack(side="right", padx=(0, 4))

        # Set initial nav state
        self._update_nav_state()
        self._refresh_folders()
        self._refresh_labels()
        self._refresh_saved_searches()

    def _build_notes_list(self):
        """Build the notes list panel"""
        list_panel = ctk.CTkFrame(
            self.main_container,
            fg_color=COLORS["bg_darkest"],
            corner_radius=0
        )
        list_panel.grid(row=0, column=1, sticky="nsew")

        # Search bar
        search_frame = ctk.CTkFrame(list_panel, fg_color="transparent")
        search_frame.pack(fill="x", padx=16, pady=16)

        self.search_entry = ctk.CTkEntry(
            search_frame,
            placeholder_text="Search notes...",
            font=ctk.CTkFont(size=13),
            height=40,
            fg_color=COLORS["bg_medium"],
            border_width=1,
            border_color=COLORS["border"],
            corner_radius=10
        )
        self.search_entry.pack(fill="x")
        self.search_entry.bind("<KeyRelease>", self._on_search)

        filter_row = ctk.CTkFrame(list_panel, fg_color="transparent")
        filter_row.pack(fill="x", padx=16, pady=(0, 8))

        self.filter_summary_label = ctk.CTkLabel(
            filter_row,
            text="No filters",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_muted"],
            anchor="w"
        )
        self.filter_summary_label.pack(side="left", fill="x", expand=True)

        filter_btn = ctk.CTkButton(
            filter_row,
            text="Filters",
            font=ctk.CTkFont(size=12),
            width=74,
            height=30,
            fg_color=COLORS["bg_medium"],
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_primary"],
            command=self._open_advanced_filters
        )
        filter_btn.pack(side="right")

        save_search_btn = ctk.CTkButton(
            filter_row,
            text="Save",
            font=ctk.CTkFont(size=12),
            width=58,
            height=30,
            fg_color=COLORS["bg_medium"],
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_primary"],
            command=self._save_current_search
        )
        save_search_btn.pack(side="right", padx=(0, 8))

        # Notes count
        self.notes_count_label = ctk.CTkLabel(
            list_panel,
            text="0 notes",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_muted"]
        )
        self.notes_count_label.pack(anchor="w", padx=16, pady=(0, 8))

        # Notes scroll area
        self.notes_scroll = ctk.CTkScrollableFrame(
            list_panel,
            fg_color="transparent"
        )
        self.notes_scroll.pack(fill="both", expand=True, padx=8)

        self.note_cards: List[NoteCard] = []

    def _build_editor(self):
        """Build the editor panel"""
        self.editor_panel = ctk.CTkFrame(
            self.main_container,
            fg_color=COLORS["bg_dark"],
            corner_radius=0
        )
        self.editor_panel.grid(row=0, column=2, sticky="nsew")

        # Empty state
        self.empty_state = ctk.CTkFrame(self.editor_panel, fg_color="transparent")
        self.empty_state.pack(fill="both", expand=True)

        empty_icon = ctk.CTkLabel(
            self.empty_state,
            text="",
            image=IconManager.get_icon("note", 64, COLORS["text_muted"])
        )
        empty_icon.pack(pady=(100, 16))

        empty_text = ctk.CTkLabel(
            self.empty_state,
            text="Select a note to view or edit",
            font=ctk.CTkFont(size=14),
            text_color=COLORS["text_muted"]
        )
        empty_text.pack()

        empty_hint = ctk.CTkLabel(
            self.empty_state,
            text="or create a new one",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_disabled"]
        )
        empty_hint.pack(pady=(4, 0))

        # Editor (initially hidden)
        self.editor = NoteEditor(
            self.editor_panel,
            self.db,
            self.sync_engine,
            on_save=self._on_note_saved,
            on_close=self._close_editor,
            on_popout=self._open_note_window,
        )

        self._detached_windows: List[ctk.CTkToplevel] = []

    def _set_filter(self, filter_key: str):
        """Set the current filter and refresh notes"""
        self.current_filter = filter_key
        self._update_nav_state()
        self._refresh_folders()
        self._refresh_saved_searches()
        self._refresh_notes_list()

    def _update_nav_state(self):
        """Update navigation button states"""
        for key, btn in self.nav_buttons.items():
            if key == self.current_filter:
                btn.configure(
                    fg_color=COLORS["bg_light"],
                    text_color=COLORS["text_primary"]
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=COLORS["text_secondary"]
                )

    def _get_filtered_notes_for_current_view(self) -> List[Note]:
        """Return notes for the active sidebar/search/filter state."""
        advanced_active = advanced_filters_active(self.advanced_filters)
        include_archived = bool(self.advanced_filters.get("is_archived"))
        used_indexed_search = False

        if self.current_filter == "all" and self.search_query:
            notes = self.db.search_notes(self.search_query, include_archived=include_archived)
            used_indexed_search = True
        elif self.current_filter == "all":
            notes = self.db.get_all_notes(include_archived=include_archived)
        elif self.current_filter == "archived":
            notes = self.db.get_all_notes(include_archived=True)
            notes = [n for n in notes if n.archived]
        elif self.current_filter == "trash":
            notes = self.db.get_all_notes(include_trashed=True)
            notes = [n for n in notes if n.trashed]
        elif self.current_filter.startswith("label:"):
            label = self.current_filter[6:]
            notes = self.db.get_notes_by_label(label)
        elif self.current_filter.startswith("folder:"):
            folder_path = self.current_filter[7:]
            notes = [
                note
                for note in self.db.get_all_notes(include_archived=include_archived)
                if note_matches_folder(note, folder_path)
            ]
        elif self.current_filter.startswith("saved:") and self.search_query:
            notes = self.db.search_notes(self.search_query, include_archived=include_archived)
            used_indexed_search = True
        elif self.current_filter.startswith("saved:"):
            notes = self.db.get_all_notes(include_archived=include_archived)
        else:
            notes = self.db.get_all_notes()

        if self.search_query and not (self.current_filter == "all") and not used_indexed_search:
            query_lower = self.search_query.lower()
            notes = [n for n in notes if
                     query_lower in n.title.lower() or
                     query_lower in n.content.lower()]

        if advanced_active:
            notes = [note for note in notes if note_matches_advanced_filters(note, self.advanced_filters)]
        return notes

    def _refresh_notes_list(self):
        """Refresh the notes list based on current filter"""
        # Clear existing cards
        for card in self.note_cards:
            card.destroy()
        self.note_cards.clear()

        notes = self._get_filtered_notes_for_current_view()
        self._update_filter_summary()

        # Update count
        self.notes_count_label.configure(text=f"{len(notes)} note{'s' if len(notes) != 1 else ''}")

        # Create cards
        for note in notes:
            card = NoteCard(
                self.notes_scroll,
                note,
                on_click=self._open_note,
                on_pin=self._toggle_pin,
                on_delete=self._delete_note,
                on_archive=self._archive_note
            )
            card.pack(fill="x", pady=4, padx=4)
            self.note_cards.append(card)

    def _refresh_folders(self):
        """Refresh the hierarchical folders list in the sidebar."""
        if not hasattr(self, "folders_frame"):
            return
        for widget in self.folders_frame.winfo_children():
            widget.destroy()

        labels = [label.name for label in self.db.get_all_labels()]
        explicit_folders = self.db.get_setting("folders", [])
        if not isinstance(explicit_folders, list):
            explicit_folders = []

        for folder_path in folder_paths_from_labels(labels, explicit_folders):
            depth = folder_path_depth(folder_path)
            text = f"{'  ' * depth}{folder_display_name(folder_path)}"
            filter_key = f"folder:{folder_path}"
            btn = ctk.CTkButton(
                self.folders_frame,
                text=text,
                image=IconManager.get_icon("archive", 16, COLORS["accent_blue"]),
                font=ctk.CTkFont(size=12),
                height=34,
                fg_color=COLORS["bg_light"] if self.current_filter == filter_key else "transparent",
                hover_color=COLORS["bg_hover"],
                text_color=COLORS["text_primary"] if self.current_filter == filter_key else COLORS["text_secondary"],
                anchor="w",
                command=lambda path=folder_path: self._set_filter(f"folder:{path}")
            )
            btn.pack(fill="x", pady=1)

    def _refresh_labels(self):
        """Refresh the labels list in sidebar"""
        for widget in self.labels_frame.winfo_children():
            widget.destroy()

        labels = self.db.get_all_labels()
        for label in labels:
            btn = ctk.CTkButton(
                self.labels_frame,
                text=label.name,
                image=IconManager.get_icon("label", 16, COLORS["accent_purple"]),
                font=ctk.CTkFont(size=12),
                height=36,
                fg_color="transparent",
                hover_color=COLORS["bg_hover"],
                text_color=COLORS["text_secondary"],
                anchor="w",
                command=lambda l=label.name: self._set_filter(f"label:{l}")
            )
            btn.pack(fill="x", pady=1)
        self._refresh_folders()

    def _refresh_saved_searches(self):
        if not hasattr(self, "saved_searches_frame"):
            return
        for widget in self.saved_searches_frame.winfo_children():
            widget.destroy()
        for saved in self.saved_searches:
            btn = ctk.CTkButton(
                self.saved_searches_frame,
                text=saved.get("name", "Saved search"),
                image=IconManager.get_icon("search", 16, COLORS["accent_cyan"]),
                font=ctk.CTkFont(size=12),
                height=34,
                fg_color=COLORS["bg_light"] if self.current_filter == f"saved:{saved.get('id')}" else "transparent",
                hover_color=COLORS["bg_hover"],
                text_color=COLORS["text_secondary"],
                anchor="w",
                command=lambda item=saved: self._open_saved_search(item)
            )
            btn.pack(fill="x", pady=1)

    def _on_search(self, event=None):
        """Handle search input"""
        self.search_query = self.search_entry.get()
        self._refresh_notes_list()

    def _open_advanced_filters(self):
        AdvancedFilterDialog(self, self.advanced_filters, self._apply_advanced_filters)

    def _open_tag_graph(self):
        graph = build_tag_graph(self.db.get_all_notes(include_archived=True))
        dialog = ctk.CTkToplevel(self)
        dialog.title("Tag Graph")
        dialog.geometry("520x560")
        dialog.configure(fg_color=COLORS["bg_dark"])

        frame = ctk.CTkFrame(dialog, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            frame,
            text="Tag Graph",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(anchor="w", pady=(0, 12))

        text_box = ctk.CTkTextbox(
            frame,
            font=ctk.CTkFont(size=13),
            fg_color=COLORS["bg_medium"],
            border_width=1,
            border_color=COLORS["border"],
            text_color=COLORS["text_primary"],
            wrap="word"
        )
        text_box.pack(fill="both", expand=True)
        text_box.insert("1.0", "\n".join(tag_graph_summary_lines(graph)))
        text_box.configure(state="disabled")

        close_btn = ctk.CTkButton(
            frame,
            text="Close",
            height=36,
            fg_color=COLORS["accent_green"],
            hover_color=COLORS["accent_green_hover"],
            text_color=COLORS["bg_darkest"],
            command=dialog.destroy
        )
        close_btn.pack(anchor="e", pady=(12, 0))
        configure_modal_dialog(dialog, self, initial_focus=close_btn)

    def _open_daily_review(self):
        all_notes = self.db.get_all_notes(include_archived=True)
        review_notes = pick_review_notes(all_notes, count=3, min_age_days=7)

        dialog = ctk.CTkToplevel(self)
        dialog.title("Daily Review")
        dialog.geometry("520x560")
        dialog.configure(fg_color=COLORS["bg_dark"])

        frame = ctk.CTkFrame(dialog, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            frame,
            text="Daily Review",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(anchor="w", pady=(0, 4))

        ctk.CTkLabel(
            frame,
            text="Rediscover old notes from your collection",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_muted"]
        ).pack(anchor="w", pady=(0, 16))

        if not review_notes:
            ctk.CTkLabel(
                frame,
                text="No notes old enough for review yet.\nNotes need to be at least 7 days old.",
                font=ctk.CTkFont(size=13),
                text_color=COLORS["text_secondary"],
                justify="center",
            ).pack(expand=True)
        else:
            for note in review_notes:
                card = ctk.CTkFrame(frame, fg_color=COLORS["bg_medium"], corner_radius=10)
                card.pack(fill="x", pady=6)

                title = note.title.strip() or "Untitled"
                ctk.CTkLabel(
                    card,
                    text=title,
                    font=ctk.CTkFont(size=14, weight="bold"),
                    text_color=COLORS["text_primary"],
                    anchor="w",
                ).pack(fill="x", padx=12, pady=(12, 2))

                age = (datetime.now(timezone.utc) - note.created_at).days if note.created_at else 0
                meta = f"{age} days ago"
                if note.labels:
                    meta += f" | {', '.join(note.labels)}"
                ctk.CTkLabel(
                    card,
                    text=meta,
                    font=ctk.CTkFont(size=11),
                    text_color=COLORS["text_muted"],
                    anchor="w",
                ).pack(fill="x", padx=12, pady=(0, 4))

                preview = (note.content or "").strip()[:200]
                if note.checklist_items:
                    items = [item.text for item in note.checklist_items if item.text.strip()]
                    preview = ", ".join(items[:4])
                if preview:
                    ctk.CTkLabel(
                        card,
                        text=preview,
                        font=ctk.CTkFont(size=12),
                        text_color=COLORS["text_secondary"],
                        anchor="w",
                        wraplength=440,
                        justify="left",
                    ).pack(fill="x", padx=12, pady=(0, 4))

                open_btn = ctk.CTkButton(
                    card,
                    text="Open",
                    font=ctk.CTkFont(size=12),
                    width=60,
                    height=28,
                    fg_color=COLORS["accent_blue"],
                    hover_color=COLORS["accent_blue_hover"],
                    text_color=COLORS["bg_darkest"],
                    command=lambda n=note: (dialog.destroy(), self._open_note(n)),
                )
                open_btn.pack(anchor="e", padx=12, pady=(0, 12))

        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.pack(fill="x", pady=(12, 0))

        if review_notes:
            shuffle_btn = ctk.CTkButton(
                btn_row,
                text="Shuffle",
                height=36,
                fg_color=COLORS["accent_cyan"],
                hover_color=COLORS["bg_hover"],
                text_color=COLORS["bg_darkest"],
                command=lambda: (dialog.destroy(), self._open_daily_review()),
            )
            shuffle_btn.pack(side="left")

        close_btn = ctk.CTkButton(
            btn_row,
            text="Close",
            height=36,
            fg_color=COLORS["accent_green"],
            hover_color=COLORS["accent_green_hover"],
            text_color=COLORS["bg_darkest"],
            command=dialog.destroy,
        )
        close_btn.pack(side="right")
        configure_modal_dialog(dialog, self, initial_focus=close_btn)

    def _apply_advanced_filters(self, filters: Dict[str, Any]):
        self.advanced_filters = dict(default_advanced_filters())
        self.advanced_filters.update(filters or {})
        self._refresh_notes_list()

    def _save_current_search(self):
        if not self.search_query and not advanced_filters_active(self.advanced_filters):
            self.sync_status_label.configure(text="No search to save", text_color=COLORS["text_muted"])
            return
        dialog = ctk.CTkInputDialog(text="Saved search name:", title="Save Search")
        name = dialog.get_input()
        if not name:
            return
        saved = {
            "id": str(uuid.uuid4()),
            "name": name.strip(),
            "query": self.search_query,
            "filters": dict(self.advanced_filters),
        }
        self.saved_searches.append(saved)
        self.db.set_setting("saved_searches", self.saved_searches)
        self._refresh_saved_searches()
        self.sync_status_label.configure(text="Saved search", text_color=COLORS["accent_green"])

    def _open_saved_search(self, saved: Dict[str, Any]):
        self.current_filter = f"saved:{saved.get('id')}"
        self.search_query = saved.get("query", "")
        self.search_entry.delete(0, "end")
        if self.search_query:
            self.search_entry.insert(0, self.search_query)
        self.advanced_filters = dict(default_advanced_filters())
        self.advanced_filters.update(saved.get("filters") or {})
        self._update_nav_state()
        self._refresh_folders()
        self._refresh_saved_searches()
        self._refresh_notes_list()

    def _update_filter_summary(self):
        if not hasattr(self, "filter_summary_label"):
            return
        parts = []
        if self.current_filter.startswith("folder:"):
            parts.append(f"folder:{self.current_filter[7:]}")
        if not advanced_filters_active(self.advanced_filters):
            if parts:
                self.filter_summary_label.configure(text=" | ".join(parts[:4]), text_color=COLORS["accent_blue"])
                return
            self.filter_summary_label.configure(text="No filters", text_color=COLORS["text_muted"])
            return
        parts.insert(0, self.advanced_filters.get("mode", "AND"))
        if self.advanced_filters.get("label"):
            parts.append(f"label:{self.advanced_filters['label']}")
        if self.advanced_filters.get("color"):
            parts.append(f"color:{self.advanced_filters['color']}")
        if self.advanced_filters.get("date_from") or self.advanced_filters.get("date_to"):
            parts.append(f"{self.advanced_filters.get('date_from') or '*'}..{self.advanced_filters.get('date_to') or '*'}")
        for key, label in (("has_image", "image"), ("has_checklist", "checklist"), ("is_archived", "archived")):
            if self.advanced_filters.get(key):
                parts.append(label)
        self.filter_summary_label.configure(text=" | ".join(parts[:4]), text_color=COLORS["accent_blue"])

    def _new_note(self):
        """Create a new note"""
        self.empty_state.pack_forget()
        self.editor.pack(fill="both", expand=True)
        self.editor.load_note(None)

    def _open_note(self, note: Note):
        """Open a note in the editor"""
        self.selected_note = note
        self.empty_state.pack_forget()
        self.editor.pack(fill="both", expand=True)
        self.editor.load_note(note)

    def _open_note_window(self, note: Note):
        """Open a note in a detached window for side-by-side editing."""
        self._close_editor()

        window = ctk.CTkToplevel(self)
        window.title(note.title.strip() or "Untitled")
        window.geometry("700x650")
        window.configure(fg_color=COLORS["bg_dark"])

        def on_save(saved_note: Note):
            self._refresh_notes_list()
            self._refresh_labels()

        def on_close():
            self._detached_windows = [w for w in self._detached_windows if w is not window]
            window.destroy()

        editor = NoteEditor(
            window,
            self.db,
            self.sync_engine,
            on_save=on_save,
            on_close=on_close,
        )
        editor.pack(fill="both", expand=True)
        editor.load_note(note)

        window.protocol("WM_DELETE_WINDOW", lambda: self._close_detached(editor, window))
        self._detached_windows.append(window)

    def _close_detached(self, editor: NoteEditor, window: ctk.CTkToplevel):
        if editor.is_modified:
            result = messagebox.askyesnocancel("Unsaved Changes", "Save changes before closing?")
            if result is None:
                return
            if result:
                editor._save_note()
        self._detached_windows = [w for w in self._detached_windows if w is not window]
        window.destroy()

    def _close_editor(self):
        """Close the editor and show empty state"""
        self.editor.pack_forget()
        self.empty_state.pack(fill="both", expand=True)
        self.selected_note = None

    def _on_note_saved(self, note: Note):
        """Handle note save"""
        self._refresh_notes_list()
        self._refresh_labels()

    def _toggle_pin(self, note: Note):
        """Toggle note pinned status"""
        note.pinned = not note.pinned
        note.local_modified = datetime.now(timezone.utc)
        if note.keep_id:
            note.sync_status = SyncStatus.PENDING_PUSH
        self.db.save_note(note)
        self._refresh_notes_list()

    def _archive_note(self, note: Note):
        """Archive a note"""
        note.archived = True
        note.local_modified = datetime.now(timezone.utc)
        if note.keep_id:
            note.sync_status = SyncStatus.PENDING_PUSH
        self.db.save_note(note)
        self._refresh_notes_list()

    def _delete_note(self, note: Note):
        """Delete a note (move to trash)"""
        if note.trashed:
            try:
                LocalBackupManager(self.db, APP_NAME, APP_VERSION).create_backup("before permanent delete")
            except Exception as e:
                log_diagnostic_exception("permanent delete backup", e)
            if self.db.delete_note(note.id, permanent=True):
                self._clear_delete_undo()
                self.sync_status_label.configure(text="Deleted permanently", text_color=COLORS["accent_red"])
        else:
            if self.db.delete_note(note.id):
                self.pending_delete_undo_note_id = note.id
                self.undo_delete_btn.pack(side="left", padx=(8, 0))
                self.sync_status_label.configure(text="Moved to trash", text_color=COLORS["accent_yellow"])

        if self.selected_note and self.selected_note.id == note.id:
            self._close_editor()
        self._refresh_notes_list()

    def _clear_delete_undo(self):
        self.pending_delete_undo_note_id = None
        if hasattr(self, "undo_delete_btn"):
            self.undo_delete_btn.pack_forget()

    def _undo_delete_note(self):
        note_id = self.pending_delete_undo_note_id
        if not note_id:
            self._clear_delete_undo()
            return
        if self.db.restore_note(note_id):
            self._clear_delete_undo()
            self.sync_status_label.configure(text="Restored note", text_color=COLORS["accent_green"])
            self._refresh_notes_list()
            self._refresh_labels()
        else:
            self.sync_status_label.configure(text="Restore failed", text_color=COLORS["accent_red"])

    def _add_label_dialog(self):
        """Show dialog to add a new label"""
        dialog = ctk.CTkInputDialog(
            text="Enter label name:",
            title="New Label"
        )
        label_name = dialog.get_input()
        if label_name:
            label = Label(id=str(uuid.uuid4()), name=label_name)
            self.db.save_label(label)
            self._refresh_labels()

    def _add_folder_dialog(self):
        """Show dialog to add a folder path."""
        dialog = ctk.CTkInputDialog(
            text="Enter folder path:",
            title="New Folder"
        )
        folder_path = normalize_folder_path(dialog.get_input())
        if not folder_path:
            return
        folders = self.db.get_setting("folders", [])
        if not isinstance(folders, list):
            folders = []
        if folder_path not in folders:
            folders.append(folder_path)
            self.db.set_setting("folders", folder_paths_from_labels([], folders))
        self._refresh_folders()

    def _manual_sync(self):
        """Trigger manual sync"""
        if not self.sync_engine.is_authenticated:
            messagebox.showinfo("Not Connected",
                              "Connect to Google Keep in Settings to enable sync.")
            return

        self.sync_btn.configure(state="disabled")
        self.sync_status_label.configure(text="Syncing...")

        def do_sync():
            success, message, stats = self.sync_engine.sync()
            self.after(0, lambda: self._on_sync_complete(success, message, stats))

        threading.Thread(target=do_sync, daemon=True).start()

    def _on_sync_complete(self, success: bool, message: str, stats: dict):
        """Handle sync completion"""
        self.sync_btn.configure(state="normal")
        if success:
            self.sync_status_label.configure(
                text=f"Synced ↓{stats.get('pulled', 0)} ↑{stats.get('pushed', 0)}",
                text_color=COLORS["accent_green"]
            )
        else:
            log_diagnostic_event("error", f"Keep sync failed: {message}")
            self.sync_status_label.configure(
                text="Sync error",
                text_color=COLORS["accent_red"]
            )
        self._refresh_notes_list()

    def _on_sync_status_change(self, status: str, message: str):
        """Handle sync status changes from background sync"""
        def update():
            if status == "syncing":
                self.sync_status_label.configure(text="Syncing...", text_color=COLORS["accent_yellow"])
            elif status == "synced":
                self.sync_status_label.configure(text=message, text_color=COLORS["accent_green"])
                self._refresh_notes_list()
            elif status == "error":
                log_diagnostic_event("error", f"Keep sync status error: {message}")
                self.sync_status_label.configure(text="Error", text_color=COLORS["accent_red"])
            elif status == "connected":
                self.sync_status_label.configure(text="Connected", text_color=COLORS["accent_green"])
            elif status == "disconnected":
                self.sync_status_label.configure(text="Offline", text_color=COLORS["text_muted"])

        self.after(0, update)

    def _try_auto_connect(self):
        """Try to auto-connect to Keep on startup"""
        if self.sync_engine.try_auto_login():
            self.sync_status_label.configure(text="Connected", text_color=COLORS["accent_green"])
            # Initial sync
            self._manual_sync()

    def _open_settings(self):
        """Open settings dialog"""
        SettingsDialog(
            self,
            self.db,
            self.sync_engine,
            self.cloud_sync,
            app_name=APP_NAME,
            app_version=APP_VERSION,
            db_version=DB_VERSION,
            gkeepapi_available=GKEEPAPI_AVAILABLE,
            web_scraper_factory=KeepWebScraper,
        )

    def restore_local_backup(self, backup_path: Path) -> Path:
        """Restore a local backup and rebind app services to the restored database."""
        if self._reminder_after_id:
            self.after_cancel(self._reminder_after_id)
            self._reminder_after_id = None
        if self._takeout_watch_after_id:
            self.after_cancel(self._takeout_watch_after_id)
            self._takeout_watch_after_id = None

        self.sync_engine.stop_auto_sync()
        self.cloud_sync.stop_auto_sync()

        manager = LocalBackupManager(self.db, APP_NAME, APP_VERSION)
        safety_backup = manager.create_backup("pre-restore")
        manager.restore_backup(Path(backup_path))

        self.db = DatabaseManager(str(self.data_dir / "notes.db"))
        self.sync_engine = KeepSyncEngine(self.db)
        self.sync_engine.add_sync_callback(self._on_sync_status_change)
        self.cloud_sync = CloudSyncManager(self.db, APP_NAME, APP_VERSION, DB_VERSION)
        self.cloud_sync.add_callback(self._on_cloud_sync_status_change)
        self.editor.db = self.db
        self.editor.sync_engine = self.sync_engine

        self.saved_searches = self.db.get_setting("saved_searches", [])
        if not isinstance(self.saved_searches, list):
            self.saved_searches = []
        self.selected_note = None
        self._close_editor()
        self._refresh_labels()
        self._refresh_saved_searches()
        self._refresh_notes_list()
        self._update_cloud_status_display()
        self._schedule_reminder_check(delay_ms=1000)
        self._schedule_takeout_watch_check(delay_ms=5000)
        if self.db.get_setting("auto_sync", True):
            interval = self.db.get_setting("sync_interval", 5)
            self.sync_engine.start_auto_sync(interval)
        return safety_backup

    def _try_restore_cloud_sync(self):
        """Try to restore cloud sync connection"""
        provider = self.db.get_setting("cloud_provider")

        if provider == "gdrive":
            # Google Drive can auto-reconnect via saved token
            try:
                success, _ = self.cloud_sync.connect_gdrive()
                if success:
                    self._update_cloud_status_display()
                    if self.db.get_setting("cloud_auto_sync", True):
                        interval = self.db.get_setting("cloud_sync_interval", 15)
                        self.cloud_sync.start_auto_sync(interval)
            except:
                pass
        elif provider == "github":
            repo = self.db.get_setting("github_repo", "")
            if repo:
                try:
                    success, _ = self.cloud_sync.connect_github(None, repo)
                    if success:
                        self._update_cloud_status_display()
                        if self.db.get_setting("cloud_auto_sync", True):
                            interval = self.db.get_setting("cloud_sync_interval", 15)
                            self.cloud_sync.start_auto_sync(interval)
                except:
                    pass

    def _on_cloud_sync_status_change(self, status: str, message: str):
        """Handle cloud sync status changes"""
        def update():
            self._update_cloud_status_display()
            if status == "synced":
                self._refresh_notes_list()
        self.after(0, update)

    def _update_cloud_status_display(self):
        """Update the cloud sync status in the sidebar"""
        if self.cloud_sync.is_connected():
            status = self.cloud_sync.get_status()
            provider = status.get("provider", "Cloud")
            self.sync_status_label.configure(
                text=f"☁️ {provider}",
                text_color=COLORS["accent_green"]
            )
        else:
            if self.sync_engine.is_authenticated:
                self.sync_status_label.configure(text="Connected", text_color=COLORS["accent_green"])
            else:
                self.sync_status_label.configure(text="Local only", text_color=COLORS["text_muted"])

    def _cloud_sync_now(self):
        """Manually trigger cloud sync"""
        if self.cloud_sync.is_connected():
            self.sync_status_label.configure(text="Syncing...", text_color=COLORS["accent_yellow"])

            def do_sync():
                success, message, stats = self.cloud_sync.sync()
                self.after(0, lambda: self._on_cloud_sync_complete(success, message, stats))

            threading.Thread(target=do_sync, daemon=True).start()
        else:
            self._manual_sync()  # Fall back to Keep sync

    def _on_cloud_sync_complete(self, success: bool, message: str, stats: dict):
        """Handle cloud sync completion"""
        if success:
            pulled = stats.get("downloaded", 0)
            pushed = stats.get("uploaded", 0)
            self.sync_status_label.configure(
                text=f"☁️ ↑{pushed} ↓{pulled}",
                text_color=COLORS["accent_green"]
            )
        else:
            log_diagnostic_event("error", f"Cloud sync failed: {message}")
            self.sync_status_label.configure(text="Sync error", text_color=COLORS["accent_red"])
        self._refresh_notes_list()

    def _schedule_reminder_check(self, delay_ms: int = 60000):
        """Schedule the next due-reminder check."""
        self._reminder_after_id = self.after(delay_ms, self._check_due_reminders)

    def _check_due_reminders(self):
        """Notify for due reminders."""
        try:
            due_notes = self.db.get_due_reminders()
            for note in due_notes:
                self._notify_reminder(note)
                self.db.mark_reminder_notified(note.id)
            if due_notes:
                self._refresh_notes_list()
        finally:
            self._schedule_reminder_check()

    def _schedule_takeout_watch_check(self, delay_ms: int = 60000):
        """Schedule the watched Takeout folder poll."""
        self._takeout_watch_after_id = self.after(delay_ms, self._check_takeout_watch_folder)

    def _takeout_watch_enabled(self) -> bool:
        folder = self.db.get_setting("takeout_watch_folder", "")
        return bool(self.db.get_setting("takeout_watch_enabled", False) and folder and Path(folder).exists())

    def _takeout_candidate_signature(self, path: Path) -> str:
        if path.is_file():
            stat = path.stat()
            return f"file:{stat.st_size}:{stat.st_mtime_ns}"

        json_files = MultiSourceImporter(self.db)._takeout_json_files(path)
        if not json_files:
            return ""
        size = 0
        latest = 0
        for json_file in json_files:
            stat = json_file.stat()
            size += stat.st_size
            latest = max(latest, stat.st_mtime_ns)
        return f"folder:{len(json_files)}:{size}:{latest}"

    def _takeout_watch_candidates(self, folder: Path) -> List[Path]:
        candidates = []
        for child in folder.iterdir():
            if child.name.startswith("."):
                continue
            try:
                if time.time() - child.stat().st_mtime < 10:
                    continue
            except OSError:
                continue
            if child.is_file() and child.suffix.lower() == ".zip":
                candidates.append(child)
            elif child.is_dir() and MultiSourceImporter(self.db)._takeout_json_files(child):
                candidates.append(child)
        return sorted(candidates, key=lambda item: item.name.lower())

    def _check_takeout_watch_folder(self):
        """Import new Takeout ZIPs/folders from the configured watch folder."""
        if self._takeout_watch_in_progress or not self._takeout_watch_enabled():
            self._schedule_takeout_watch_check()
            return

        watch_folder = Path(self.db.get_setting("takeout_watch_folder", ""))
        processed = self.db.get_setting("takeout_processed_imports", {})
        if not isinstance(processed, dict):
            processed = {}

        pending = []
        for candidate in self._takeout_watch_candidates(watch_folder):
            try:
                signature = self._takeout_candidate_signature(candidate)
            except OSError:
                continue
            key = str(candidate.resolve())
            if signature and processed.get(key) != signature:
                pending.append((candidate, key, signature))

        if not pending:
            self._schedule_takeout_watch_check()
            return

        self._takeout_watch_in_progress = True
        self.sync_status_label.configure(text="Auto-importing...", text_color=COLORS["accent_yellow"])

        def do_import():
            importer = MultiSourceImporter(self.db)
            imported = 0
            errors = 0
            updated_processed = dict(processed)

            try:
                LocalBackupManager(self.db, APP_NAME, APP_VERSION).create_backup("before auto takeout import")
            except Exception as e:
                self.db.log_sync("auto_import", "backup", "error", str(e))
                errors += 1
                self.db.set_setting("takeout_processed_imports", updated_processed)
                self.after(0, lambda: self._on_takeout_watch_complete(imported, errors))
                return

            for path, key, signature in pending:
                try:
                    notes = importer.import_takeout_path(path)
                    imported += importer.save_notes(notes)
                    updated_processed[key] = signature
                except Exception as e:
                    errors += 1
                    self.db.log_sync("auto_import", key, "error", str(e))

            self.db.set_setting("takeout_processed_imports", updated_processed)
            self.after(0, lambda: self._on_takeout_watch_complete(imported, errors))

        threading.Thread(target=do_import, daemon=True).start()

    def _on_takeout_watch_complete(self, imported: int, errors: int):
        self._takeout_watch_in_progress = False
        if imported:
            self.sync_status_label.configure(text=f"Auto-imported {imported}", text_color=COLORS["accent_green"])
            self._refresh_notes_list()
            self._refresh_labels()
        elif errors:
            self.sync_status_label.configure(text="Auto-import error", text_color=COLORS["accent_red"])
        self._schedule_takeout_watch_check()

    def _notify_reminder(self, note: Note):
        """Show a desktop reminder notification when possible."""
        title = note.title or "Untitled"
        message = note.content[:160] if note.content else ""
        if note.note_type == NoteType.CHECKLIST and note.checklist_items:
            remaining = [item.text for item in note.checklist_items if not item.checked]
            message = ", ".join(remaining[:3]) or "Checklist complete"
        if note.reminder_location:
            message = f"{message}\nLocation: {note.reminder_location}" if message else f"Location: {note.reminder_location}"

        notified = False
        if DESKTOP_NOTIFICATIONS_AVAILABLE:
            try:
                desktop_notification.notify(
                    title=f"{APP_NAME}: {title}",
                    message=message or "Reminder due",
                    app_name=APP_NAME,
                    timeout=10
                )
                notified = True
            except Exception as e:
                self.db.log_sync("reminder", note.id, "error", str(e))

        self.sync_status_label.configure(
            text=f"Reminder: {title[:24]}",
            text_color=COLORS["accent_yellow"]
        )
        if not notified:
            self.bell()

    def _start_tray(self):
        self._tray = SystemTray(
            app_name=APP_NAME,
            on_new_note=lambda: self.after(0, self._new_note),
            on_show=lambda: self.after(0, self._show_from_tray),
            on_quit=lambda: self.after(0, self.on_closing),
        )
        self._tray.start()

    def _show_from_tray(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def on_closing(self):
        """Handle window close"""
        if self._reminder_after_id:
            self.after_cancel(self._reminder_after_id)
        if self._takeout_watch_after_id:
            self.after_cancel(self._takeout_watch_after_id)
        for window in list(self._detached_windows):
            try:
                window.destroy()
            except Exception:
                pass
        self._detached_windows.clear()
        if self._tray:
            self._tray.stop()
            self._tray = None
        self.sync_engine.stop_auto_sync()
        self.cloud_sync.stop_auto_sync()
        self.db.close()
        self.destroy()
