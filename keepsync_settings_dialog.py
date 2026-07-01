"""Settings dialog and settings-backed import/export workflows."""

import json
import threading
import uuid
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, Callable, List, Optional

import customtkinter as ctk

import keepsync_diagnostics as diagnostics_state
from keepsync_backups import LocalBackupManager
from keepsync_cloud_sync import CloudSyncManager
from keepsync_diagnostics import log_diagnostic_exception
from keepsync_import_reports import IMPORT_SUCCESS_STATUSES, import_summary_lines
from keepsync_import_safety import ImportCancelled
from keepsync_importers import MultiSourceImporter, extract_shared_with, import_takeout_attachments
from keepsync_markdown_export import export_markdown_vault
from keepsync_encrypted_backup import (
    create_encrypted_backup,
    read_backup_header,
    restore_encrypted_backup,
)
from keepsync_pdf_export import export_pdf_book
from keepsync_models import ChecklistItem, Note, NoteType, SyncStatus, normalize_keep_color
from keepsync_note_ops import notes_equivalent
from keepsync_paths import get_google_drive_credentials_path
from keepsync_storage import DatabaseManager
from keepsync_theme import COLORS, get_theme_name, set_theme
from keepsync_ui_dialogs import (
    DiagnosticsDialog,
    ImportConflictDialog,
    ImportProgressDialog,
    TakeoutInstructionsDialog,
    TokenGeneratorDialog,
)
from keepsync_ui_modal import configure_modal_dialog


class SettingsDialog(ctk.CTkToplevel):
    """Settings dialog for Google Keep connection and app settings"""

    def __init__(
        self,
        parent,
        db: DatabaseManager,
        sync_engine: Any,
        cloud_sync: CloudSyncManager = None,
        app_name: str = "KeepSync Notes",
        app_version: str = "",
        db_version: int = 1,
        gkeepapi_available: bool = True,
        web_scraper_factory: Optional[Callable[[], Any]] = None,
    ):
        super().__init__(parent)

        self.app = parent
        self.db = db
        self.sync_engine = sync_engine
        self.cloud_sync = cloud_sync
        self.app_name = app_name
        self.app_version = app_version
        self.db_version = db_version
        self.gkeepapi_available = gkeepapi_available
        self.web_scraper_factory = web_scraper_factory

        self.title("Settings")
        self.geometry("550x700")
        self.configure(fg_color=COLORS["bg_dark"])

        # Center on parent
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._load_settings()
        configure_modal_dialog(self, parent, initial_focus=self.tabview)

    def _build_ui(self):
        # Create tabview for different settings sections
        self.tabview = ctk.CTkTabview(self, fg_color=COLORS["bg_dark"])
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)

        # Add tabs
        self.tabview.add("☁️ Cloud Sync")
        self.tabview.add("🔄 Google Keep")
        self.tabview.add("📦 Data")

        # Build each tab
        self._build_cloud_sync_tab()
        self._build_keep_tab()
        self._build_data_tab()

        # Close button
        close_btn = ctk.CTkButton(
            self,
            text="Close",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=44,
            fg_color=COLORS["accent_blue"],
            hover_color=COLORS["accent_blue_hover"],
            text_color=COLORS["bg_darkest"],
            command=self.destroy
        )
        close_btn.pack(fill="x", padx=20, pady=(0, 15))

    def _build_cloud_sync_tab(self):
        """Build the Cloud Sync settings tab"""
        tab = self.tabview.tab("☁️ Cloud Sync")

        # Scroll frame
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        # Header
        ctk.CTkLabel(
            scroll,
            text="Cloud Backup",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(anchor="w", pady=(10, 5))

        ctk.CTkLabel(
            scroll,
            text="Sync your notes to Google Drive or GitHub for backup",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w", pady=(0, 15))

        # Current status
        status_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_medium"], corner_radius=10)
        status_frame.pack(fill="x", pady=(0, 15))

        self.cloud_status_label = ctk.CTkLabel(
            status_frame,
            text="Not connected to any cloud service",
            font=ctk.CTkFont(size=13),
            text_color=COLORS["text_muted"]
        )
        self.cloud_status_label.pack(pady=15)

        # === GitHub Section ===
        github_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_medium"], corner_radius=12)
        github_frame.pack(fill="x", pady=(0, 15))

        github_header = ctk.CTkFrame(github_frame, fg_color="transparent")
        github_header.pack(fill="x", padx=16, pady=(16, 8))

        ctk.CTkLabel(
            github_header,
            text="🐙 GitHub Sync",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(side="left")

        ctk.CTkLabel(
            github_header,
            text="Recommended",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["accent_green"]
        ).pack(side="right")

        ctk.CTkLabel(
            github_frame,
            text="Store notes in a private GitHub repository with version history",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_muted"]
        ).pack(anchor="w", padx=16, pady=(0, 10))

        # GitHub Token
        ctk.CTkLabel(
            github_frame,
            text="Personal Access Token",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w", padx=16, pady=(0, 4))

        self.github_token_entry = ctk.CTkEntry(
            github_frame,
            placeholder_text="Leave blank to reuse saved keyring token",
            font=ctk.CTkFont(size=12),
            height=38,
            fg_color=COLORS["bg_dark"],
            border_color=COLORS["border"],
            show="•"
        )
        self.github_token_entry.pack(fill="x", padx=16)

        # GitHub Repo
        ctk.CTkLabel(
            github_frame,
            text="Repository Name",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w", padx=16, pady=(10, 4))

        self.github_repo_entry = ctk.CTkEntry(
            github_frame,
            placeholder_text="my-notes-backup",
            font=ctk.CTkFont(size=12),
            height=38,
            fg_color=COLORS["bg_dark"],
            border_color=COLORS["border"]
        )
        self.github_repo_entry.pack(fill="x", padx=16)

        # Help link
        help_btn = ctk.CTkButton(
            github_frame,
            text="📖 How to get a GitHub token",
            font=ctk.CTkFont(size=11),
            height=28,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["accent_blue"],
            anchor="w",
            command=lambda: webbrowser.open("https://github.com/settings/tokens/new?description=KeepSync%20Notes&scopes=repo")
        )
        help_btn.pack(anchor="w", padx=12, pady=(4, 0))

        # Connect button
        self.github_connect_btn = ctk.CTkButton(
            github_frame,
            text="Connect to GitHub",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=40,
            fg_color=COLORS["accent_green"],
            hover_color=COLORS["accent_green_hover"],
            text_color=COLORS["bg_darkest"],
            command=self._connect_github
        )
        self.github_connect_btn.pack(fill="x", padx=16, pady=(10, 16))

        # === Google Drive Section ===
        gdrive_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_medium"], corner_radius=12)
        gdrive_frame.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(
            gdrive_frame,
            text="📁 Google Drive Sync",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(anchor="w", padx=16, pady=(16, 8))

        ctk.CTkLabel(
            gdrive_frame,
            text="Store notes in a Google Drive folder\nRequires OAuth setup (more complex)",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_muted"],
            justify="left"
        ).pack(anchor="w", padx=16, pady=(0, 10))

        self.gdrive_connect_btn = ctk.CTkButton(
            gdrive_frame,
            text="Connect to Google Drive",
            font=ctk.CTkFont(size=13),
            height=40,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_primary"],
            command=self._connect_gdrive
        )
        self.gdrive_connect_btn.pack(fill="x", padx=16, pady=(0, 8))

        gdrive_help = ctk.CTkButton(
            gdrive_frame,
            text="📖 Google Drive setup instructions",
            font=ctk.CTkFont(size=11),
            height=28,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["accent_blue"],
            anchor="w",
            command=self._show_gdrive_instructions
        )
        gdrive_help.pack(anchor="w", padx=12, pady=(0, 16))

        # === Auto-sync Settings ===
        autosync_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_medium"], corner_radius=12)
        autosync_frame.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(
            autosync_frame,
            text="⏱️ Auto-Sync Settings",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(anchor="w", padx=16, pady=(16, 8))

        self.cloud_autosync_var = ctk.BooleanVar(value=True)
        autosync_check = ctk.CTkCheckBox(
            autosync_frame,
            text="Enable automatic cloud sync",
            variable=self.cloud_autosync_var,
            font=ctk.CTkFont(size=13),
            text_color=COLORS["text_secondary"],
            fg_color=COLORS["accent_green"],
            hover_color=COLORS["accent_green_hover"],
            command=self._save_autosync_settings
        )
        autosync_check.pack(anchor="w", padx=16, pady=(0, 8))

        interval_frame = ctk.CTkFrame(autosync_frame, fg_color="transparent")
        interval_frame.pack(fill="x", padx=16, pady=(0, 16))

        ctk.CTkLabel(
            interval_frame,
            text="Sync interval:",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"]
        ).pack(side="left")

        self.cloud_sync_interval = ctk.CTkEntry(
            interval_frame,
            width=60,
            height=32,
            font=ctk.CTkFont(size=13),
            fg_color=COLORS["bg_dark"],
            border_color=COLORS["border"]
        )
        self.cloud_sync_interval.pack(side="left", padx=(8, 4))
        self.cloud_sync_interval.insert(0, "15")

        ctk.CTkLabel(
            interval_frame,
            text="minutes",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"]
        ).pack(side="left")

        # Disconnect button
        self.cloud_disconnect_btn = ctk.CTkButton(
            scroll,
            text="Disconnect from Cloud",
            font=ctk.CTkFont(size=13),
            height=40,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["accent_red"],
            border_width=1,
            border_color=COLORS["accent_red"],
            command=self._disconnect_cloud
        )
        # Initially hidden, shown when connected

    def _build_keep_tab(self):
        """Build the Google Keep import tab"""
        tab = self.tabview.tab("🔄 Google Keep")

        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        # Header
        ctk.CTkLabel(
            scroll,
            text="Import from Google Keep",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(anchor="w", pady=(10, 5))

        ctk.CTkLabel(
            scroll,
            text="One-time import to migrate your notes from Google Keep",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w", pady=(0, 15))

        # Takeout import (primary)
        takeout_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_medium"], corner_radius=12)
        takeout_frame.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(
            takeout_frame,
            text="📦 Google Takeout Import",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(anchor="w", padx=16, pady=(16, 4))

        ctk.CTkLabel(
            takeout_frame,
            text="Recommended",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["accent_green"]
        ).pack(anchor="w", padx=16, pady=(0, 8))

        takeout_btn = ctk.CTkButton(
            takeout_frame,
            text="Import from Takeout Folder",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=40,
            fg_color=COLORS["accent_green"],
            hover_color=COLORS["accent_green_hover"],
            text_color=COLORS["bg_darkest"],
            command=self._import_takeout_folder
        )
        takeout_btn.pack(fill="x", padx=16, pady=(0, 8))

        takeout_help = ctk.CTkButton(
            takeout_frame,
            text="📖 How to export from Google Takeout",
            font=ctk.CTkFont(size=11),
            height=28,
            fg_color="transparent",
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["accent_blue"],
            anchor="w",
            command=lambda: TakeoutInstructionsDialog(self)
        )
        takeout_help.pack(anchor="w", padx=12, pady=(0, 16))

        # Browser import (alternative)
        browser_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_medium"], corner_radius=12)
        browser_frame.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(
            browser_frame,
            text="🌐 Browser Session Import",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(anchor="w", padx=16, pady=(16, 8))

        ctk.CTkLabel(
            browser_frame,
            text="Extract notes using your browser's Google login\n(Close browser before using)",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_muted"],
            justify="left"
        ).pack(anchor="w", padx=16, pady=(0, 10))

        browser_btn = ctk.CTkButton(
            browser_frame,
            text="Import from Browser",
            font=ctk.CTkFont(size=13),
            height=40,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_primary"],
            command=self._import_from_browser
        )
        browser_btn.pack(fill="x", padx=16, pady=(0, 16))

        # Legacy gkeepapi (hidden, mostly broken)
        legacy_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_medium"], corner_radius=12)
        legacy_frame.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(
            legacy_frame,
            text="🔑 API Token Method",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLORS["text_muted"]
        ).pack(anchor="w", padx=16, pady=(16, 4))

        ctk.CTkLabel(
            legacy_frame,
            text="⚠️ Often blocked by Google - use Takeout instead",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["accent_yellow"]
        ).pack(anchor="w", padx=16, pady=(0, 16))

    def _build_data_tab(self):
        """Build the Data Management tab"""
        tab = self.tabview.tab("📦 Data")

        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        # Header
        ctk.CTkLabel(
            scroll,
            text="Data Management",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(anchor="w", pady=(10, 15))

        # Theme
        theme_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_medium"], corner_radius=12)
        theme_frame.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(
            theme_frame,
            text="Appearance",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(anchor="w", padx=16, pady=(16, 8))

        self.theme_var = ctk.StringVar(value=self.db.get_setting("theme", "dark"))
        theme_row = ctk.CTkFrame(theme_frame, fg_color="transparent")
        theme_row.pack(fill="x", padx=16, pady=(0, 16))

        ctk.CTkLabel(
            theme_row,
            text="Theme:",
            font=ctk.CTkFont(size=13),
            text_color=COLORS["text_secondary"]
        ).pack(side="left")

        theme_menu = ctk.CTkOptionMenu(
            theme_row,
            values=["Dark (Catppuccin Mocha)", "Light (Catppuccin Latte)"],
            variable=self.theme_var,
            font=ctk.CTkFont(size=12),
            fg_color=COLORS["bg_light"],
            button_color=COLORS["bg_hover"],
            button_hover_color=COLORS["accent_blue"],
            dropdown_fg_color=COLORS["bg_medium"],
            dropdown_hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_primary"],
            height=36,
            command=self._on_theme_change,
        )
        theme_menu.pack(side="left", padx=(12, 0))
        current = self.db.get_setting("theme", "dark")
        theme_menu.set("Light (Catppuccin Latte)" if current == "light" else "Dark (Catppuccin Mocha)")

        # Export/Import
        data_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_medium"], corner_radius=12)
        data_frame.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(
            data_frame,
            text="Export & Import",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(anchor="w", padx=16, pady=(16, 10))

        btn_frame = ctk.CTkFrame(data_frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=(0, 16))

        export_btn = ctk.CTkButton(
            btn_frame,
            text="Export Notes",
            font=ctk.CTkFont(size=13),
            height=40,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_primary"],
            command=self._export_notes
        )
        export_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))

        import_btn = ctk.CTkButton(
            btn_frame,
            text="Import JSON",
            font=ctk.CTkFont(size=13),
            height=40,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_primary"],
            command=self._import_notes
        )
        import_btn.pack(side="left", fill="x", expand=True)

        export_row2 = ctk.CTkFrame(data_frame, fg_color="transparent")
        export_row2.pack(fill="x", padx=16, pady=(0, 16))

        vault_export_btn = ctk.CTkButton(
            export_row2,
            text="Export Markdown Vault",
            font=ctk.CTkFont(size=13),
            height=40,
            fg_color=COLORS["accent_blue"],
            hover_color=COLORS["accent_blue_hover"],
            text_color=COLORS["bg_darkest"],
            command=self._export_markdown_vault
        )
        vault_export_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))

        pdf_export_btn = ctk.CTkButton(
            export_row2,
            text="Export PDF Book",
            font=ctk.CTkFont(size=13),
            height=40,
            fg_color=COLORS["accent_blue"],
            hover_color=COLORS["accent_blue_hover"],
            text_color=COLORS["bg_darkest"],
            command=self._export_pdf_book
        )
        pdf_export_btn.pack(side="left", fill="x", expand=True)

        source_frame = ctk.CTkFrame(data_frame, fg_color="transparent")
        source_frame.pack(fill="x", padx=16, pady=(0, 16))

        self.external_source_var = ctk.StringVar(value="Evernote / Apple Notes ENEX")
        source_menu = ctk.CTkOptionMenu(
            source_frame,
            values=[
                "Evernote / Apple Notes ENEX",
                "Standard Notes ZIP",
                "Obsidian Vault",
                "Bear ZIP",
                "Simplenote Export",
                "OneNote HTML Folder",
            ],
            variable=self.external_source_var,
            font=ctk.CTkFont(size=12),
            fg_color=COLORS["bg_light"],
            button_color=COLORS["bg_hover"],
            button_hover_color=COLORS["accent_blue"],
            dropdown_fg_color=COLORS["bg_medium"],
            dropdown_hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_primary"],
            height=36
        )
        source_menu.pack(side="left", fill="x", expand=True, padx=(0, 8))

        external_btn = ctk.CTkButton(
            source_frame,
            text="Import Source",
            font=ctk.CTkFont(size=13),
            height=36,
            fg_color=COLORS["accent_blue"],
            hover_color=COLORS["accent_blue_hover"],
            text_color=COLORS["bg_darkest"],
            command=self._import_external_source
        )
        external_btn.pack(side="left")

        watcher_frame = ctk.CTkFrame(data_frame, fg_color=COLORS["bg_dark"], corner_radius=8)
        watcher_frame.pack(fill="x", padx=16, pady=(0, 16))

        self.takeout_watch_enabled_var = ctk.BooleanVar(value=False)
        watcher_check = ctk.CTkCheckBox(
            watcher_frame,
            text="Auto-import Google Takeout drops",
            variable=self.takeout_watch_enabled_var,
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"],
            fg_color=COLORS["accent_green"],
            hover_color=COLORS["accent_green_hover"],
            command=self._save_takeout_watch_settings
        )
        watcher_check.pack(anchor="w", padx=12, pady=(12, 8))

        watcher_inputs = ctk.CTkFrame(watcher_frame, fg_color="transparent")
        watcher_inputs.pack(fill="x", padx=12, pady=(0, 12))

        self.takeout_watch_entry = ctk.CTkEntry(
            watcher_inputs,
            placeholder_text="Watched folder",
            font=ctk.CTkFont(size=12),
            height=32,
            fg_color=COLORS["bg_medium"],
            border_color=COLORS["border"]
        )
        self.takeout_watch_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.takeout_watch_entry.bind("<FocusOut>", lambda _event: self._save_takeout_watch_settings())

        browse_watch_btn = ctk.CTkButton(
            watcher_inputs,
            text="Browse",
            font=ctk.CTkFont(size=12),
            width=74,
            height=32,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_primary"],
            command=self._select_takeout_watch_folder
        )
        browse_watch_btn.pack(side="left")

        backup_frame = ctk.CTkFrame(data_frame, fg_color=COLORS["bg_dark"], corner_radius=8)
        backup_frame.pack(fill="x", padx=16, pady=(0, 16))

        ctk.CTkLabel(
            backup_frame,
            text="Local Backups",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(anchor="w", padx=12, pady=(12, 4))

        ctk.CTkLabel(
            backup_frame,
            text="Backups include the SQLite database and local attachments.",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_muted"]
        ).pack(anchor="w", padx=12, pady=(0, 10))

        backup_buttons = ctk.CTkFrame(backup_frame, fg_color="transparent")
        backup_buttons.pack(fill="x", padx=12, pady=(0, 12))

        ctk.CTkButton(
            backup_buttons,
            text="Create Backup",
            font=ctk.CTkFont(size=12),
            height=34,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_primary"],
            command=self._create_local_backup
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            backup_buttons,
            text="Restore Backup",
            font=ctk.CTkFont(size=12),
            height=34,
            fg_color=COLORS["accent_yellow"],
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["bg_darkest"],
            command=self._restore_local_backup
        ).pack(side="left", fill="x", expand=True)

        enc_frame = ctk.CTkFrame(data_frame, fg_color=COLORS["bg_dark"], corner_radius=8)
        enc_frame.pack(fill="x", padx=16, pady=(0, 16))

        ctk.CTkLabel(
            enc_frame,
            text="Encrypted Backup",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(anchor="w", padx=12, pady=(12, 4))

        ctk.CTkLabel(
            enc_frame,
            text="AES-256-GCM encrypted SQLite dump with a password.",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_muted"]
        ).pack(anchor="w", padx=12, pady=(0, 10))

        enc_buttons = ctk.CTkFrame(enc_frame, fg_color="transparent")
        enc_buttons.pack(fill="x", padx=12, pady=(0, 12))

        ctk.CTkButton(
            enc_buttons,
            text="Create Encrypted Backup",
            font=ctk.CTkFont(size=12),
            height=34,
            fg_color=COLORS["accent_green"],
            hover_color=COLORS["accent_green_hover"],
            text_color=COLORS["bg_darkest"],
            command=self._create_encrypted_backup
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            enc_buttons,
            text="Restore Encrypted",
            font=ctk.CTkFont(size=12),
            height=34,
            fg_color=COLORS["accent_yellow"],
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["bg_darkest"],
            command=self._restore_encrypted_backup
        ).pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            data_frame,
            text="Open Diagnostics",
            font=ctk.CTkFont(size=13),
            height=36,
            fg_color=COLORS["bg_light"],
            hover_color=COLORS["bg_hover"],
            text_color=COLORS["text_primary"],
            command=self._open_diagnostics
        ).pack(fill="x", padx=16, pady=(0, 16))

        # Database info
        info_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_medium"], corner_radius=12)
        info_frame.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(
            info_frame,
            text="Database Location",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(anchor="w", padx=16, pady=(16, 8))

        db_path = str(Path(self.db.db_path))
        ctk.CTkLabel(
            info_frame,
            text=db_path,
            font=ctk.CTkFont(size=11, family="Consolas"),
            text_color=COLORS["text_muted"]
        ).pack(anchor="w", padx=16, pady=(0, 16))

        # gkeepapi status
        if not self.gkeepapi_available:
            warning_frame = ctk.CTkFrame(scroll, fg_color=COLORS["bg_medium"], corner_radius=12)
            warning_frame.pack(fill="x", pady=(0, 15))

            ctk.CTkLabel(
                warning_frame,
                text="ℹ️ gkeepapi not installed",
                font=ctk.CTkFont(size=14),
                text_color=COLORS["text_muted"]
            ).pack(anchor="w", padx=16, pady=(12, 4))

            ctk.CTkLabel(
                warning_frame,
                text="Google Keep API sync disabled. Use Takeout import instead.",
                font=ctk.CTkFont(size=11),
                text_color=COLORS["text_muted"]
            ).pack(anchor="w", padx=16, pady=(0, 12))

    def _load_settings(self):
        """Load saved settings"""
        # Load cloud sync settings
        auto_sync = self.db.get_setting("cloud_auto_sync", True)
        self.cloud_autosync_var.set(auto_sync)

        interval = self.db.get_setting("cloud_sync_interval", 15)
        self.cloud_sync_interval.delete(0, "end")
        self.cloud_sync_interval.insert(0, str(interval))

        # Load GitHub repo name if saved
        github_repo = self.db.get_setting("github_repo", "")
        if github_repo:
            self.github_repo_entry.insert(0, github_repo)

        self.takeout_watch_enabled_var.set(self.db.get_setting("takeout_watch_enabled", False))
        self.takeout_watch_entry.delete(0, "end")
        self.takeout_watch_entry.insert(0, self.db.get_setting("takeout_watch_folder", ""))

        # Update cloud status
        self._update_cloud_status()

    def _update_cloud_status(self):
        """Update the cloud connection status display"""
        if self.cloud_sync and self.cloud_sync.is_connected():
            status = self.cloud_sync.get_status()
            provider = status.get("provider", "Unknown")
            last_sync = status.get("last_sync")

            if last_sync:
                sync_time = datetime.fromisoformat(last_sync).strftime("%Y-%m-%d %H:%M")
                status_text = f"✓ Connected to {provider}\nLast sync: {sync_time}"
            else:
                status_text = f"✓ Connected to {provider}"

            self.cloud_status_label.configure(
                text=status_text,
                text_color=COLORS["accent_green"]
            )
            self.cloud_disconnect_btn.pack(fill="x", pady=(0, 15))
        else:
            self.cloud_status_label.configure(
                text="Not connected to any cloud service",
                text_color=COLORS["text_muted"]
            )

    def _connect_github(self):
        """Connect to GitHub"""
        if not self.cloud_sync:
            messagebox.showerror("Error", "Cloud sync not available")
            return

        token = self.github_token_entry.get().strip()
        repo = self.github_repo_entry.get().strip()

        if not repo:
            repo = "keepsync-notes-backup"
            self.github_repo_entry.insert(0, repo)

        self.github_connect_btn.configure(state="disabled", text="Connecting...")
        self.update()

        success, message = self.cloud_sync.connect_github(token, repo)

        self.github_connect_btn.configure(state="normal", text="Connect to GitHub")

        if success:
            self._update_cloud_status()
            self._save_autosync_settings()
            messagebox.showinfo("Success", f"{message}\n\nYour notes will now sync to GitHub.")

            # Do initial sync
            if messagebox.askyesno("Initial Sync", "Would you like to sync your notes now?"):
                self.cloud_sync.sync()
        else:
            messagebox.showerror("Connection Failed", message)

    def _connect_gdrive(self):
        """Connect to Google Drive"""
        if not self.cloud_sync:
            messagebox.showerror("Error", "Cloud sync not available")
            return

        self.gdrive_connect_btn.configure(state="disabled", text="Connecting...")
        self.update()

        success, message = self.cloud_sync.connect_gdrive()

        self.gdrive_connect_btn.configure(state="normal", text="Connect to Google Drive")

        if success:
            self._update_cloud_status()
            self._save_autosync_settings()
            messagebox.showinfo("Success", message)

            if messagebox.askyesno("Initial Sync", "Would you like to sync your notes now?"):
                self.cloud_sync.sync()
        else:
            messagebox.showerror("Connection Failed", message)

    def _disconnect_cloud(self):
        """Disconnect from cloud provider"""
        if not self.cloud_sync:
            return

        if messagebox.askyesno("Confirm", "Disconnect from cloud sync?\n\nYour notes will remain stored locally."):
            self.cloud_sync.disconnect()
            self._update_cloud_status()

    def _save_autosync_settings(self):
        """Save auto-sync settings"""
        self.db.set_setting("cloud_auto_sync", self.cloud_autosync_var.get())
        try:
            interval = int(self.cloud_sync_interval.get())
            self.db.set_setting("cloud_sync_interval", interval)
        except ValueError:
            pass

    def _select_takeout_watch_folder(self):
        folder = filedialog.askdirectory(title="Select Takeout watch folder")
        if not folder:
            return
        self.takeout_watch_entry.delete(0, "end")
        self.takeout_watch_entry.insert(0, folder)
        self._save_takeout_watch_settings()

    def _save_takeout_watch_settings(self):
        self.db.set_setting("takeout_watch_enabled", self.takeout_watch_enabled_var.get())
        self.db.set_setting("takeout_watch_folder", self.takeout_watch_entry.get().strip())
        if hasattr(self.app, "_schedule_takeout_watch_check"):
            if self.app._takeout_watch_after_id:
                self.app.after_cancel(self.app._takeout_watch_after_id)
                self.app._takeout_watch_after_id = None
            self.app._schedule_takeout_watch_check(delay_ms=1000)

    def _create_local_backup(self):
        try:
            backup_path = LocalBackupManager(self.db, self.app_name, self.app_version).create_backup("manual")
            messagebox.showinfo("Backup Created", f"Created local backup:\n{backup_path}")
        except Exception as e:
            messagebox.showerror("Backup Failed", str(e))

    def _restore_local_backup(self):
        manager = LocalBackupManager(self.db, self.app_name, self.app_version)
        selected = filedialog.askopenfilename(
            title="Select KeepSync backup",
            initialdir=str(manager.backups_dir),
            filetypes=[
                ("KeepSync backups", "*.zip"),
                ("All files", "*.*"),
            ],
        )
        if not selected:
            return
        try:
            safety_backup = self.app.restore_local_backup(Path(selected))
            self.db = self.app.db
            self.sync_engine = self.app.sync_engine
            self.cloud_sync = self.app.cloud_sync
            messagebox.showinfo(
                "Restore Complete",
                f"Restored backup:\n{selected}\n\nPre-restore safety backup:\n{safety_backup}"
            )
            self.destroy()
        except Exception as e:
            messagebox.showerror("Restore Failed", str(e))

    def _on_theme_change(self, value: str):
        theme = "light" if "Latte" in value else "dark"
        self.db.set_setting("theme", theme)
        set_theme(theme)
        messagebox.showinfo("Theme Changed", "Restart the app to apply the new theme.")

    def _create_encrypted_backup(self):
        password = self._ask_password("Set Backup Password", "Enter a password to encrypt the backup:")
        if not password:
            return
        filepath = filedialog.asksaveasfilename(
            title="Save Encrypted Backup",
            defaultextension=".ksenc",
            filetypes=[("KeepSync encrypted backups", "*.ksenc"), ("All files", "*.*")],
        )
        if not filepath:
            return

        def worker():
            try:
                result = create_encrypted_backup(self.db.db_path, Path(filepath), password)
                message = (
                    f"Encrypted backup created:\n{result.output_path}\n\n"
                    f"Notes: {result.notes_count}\n"
                    f"Size: {result.size_bytes:,} bytes\n\n"
                    f"Keep your password safe — the backup cannot be recovered without it."
                )
                self.after(0, lambda: messagebox.showinfo("Encrypted Backup Created", message))
            except Exception as e:
                log_diagnostic_exception("encrypted backup create", e)
                self.after(0, lambda message=str(e): messagebox.showerror("Encrypted Backup Failed", message))

        threading.Thread(target=worker, daemon=True).start()

    def _restore_encrypted_backup(self):
        selected = filedialog.askopenfilename(
            title="Select encrypted backup",
            filetypes=[("KeepSync encrypted backups", "*.ksenc"), ("All files", "*.*")],
        )
        if not selected:
            return

        header = read_backup_header(Path(selected))
        if not header:
            messagebox.showerror("Invalid File", "The selected file is not a valid KeepSync encrypted backup.")
            return

        password = self._ask_password(
            "Enter Backup Password",
            f"Backup from: {header.get('created', 'unknown')}\nEnter the password used to create this backup:",
        )
        if not password:
            return

        def worker():
            try:
                count = restore_encrypted_backup(Path(selected), password, self.db.db_path)
                self.after(0, lambda: self._on_encrypted_restore_complete(selected, count))
            except ValueError as e:
                self.after(0, lambda message=str(e): messagebox.showerror("Restore Failed", message))
            except Exception as e:
                log_diagnostic_exception("encrypted backup restore", e)
                self.after(0, lambda message=str(e): messagebox.showerror("Restore Failed", message))

        threading.Thread(target=worker, daemon=True).start()

    def _on_encrypted_restore_complete(self, path: str, count: int):
        if hasattr(self.app, "restore_local_backup"):
            self.db = DatabaseManager(self.db.db_path)
            self.app.db = self.db
            self.app.sync_engine.db = self.db
            self.app.editor.db = self.db
            self.app._refresh_notes_list()
            self.app._refresh_labels()
        messagebox.showinfo(
            "Restore Complete",
            f"Restored encrypted backup:\n{path}\n\nNotes restored: {count}",
        )
        self.destroy()

    def _ask_password(self, title: str, prompt: str) -> str:
        dialog = ctk.CTkInputDialog(text=prompt, title=title)
        return (dialog.get_input() or "").strip()

    def _open_diagnostics(self):
        diagnostics = getattr(self.app, "diagnostics", None) or diagnostics_state.DIAGNOSTICS
        if not diagnostics:
            messagebox.showerror("Diagnostics Unavailable", "Diagnostics manager is not initialized.")
            return
        db_path = Path(self.db.db_path)
        DiagnosticsDialog(self, diagnostics, db_path, db_path.parent / "attachments")

    def _show_gdrive_instructions(self):
        """Show Google Drive setup instructions"""
        credentials_path = get_google_drive_credentials_path()
        instructions = f"""Google Drive Setup Instructions

1. Go to console.cloud.google.com

2. Create a new project (or select existing)

3. Enable the Google Drive API:
   - Go to "APIs & Services" → "Library"
   - Search for "Google Drive API"
   - Click "Enable"

4. Create OAuth credentials:
   - Go to "APIs & Services" → "Credentials"
   - Click "Create Credentials" → "OAuth client ID"
   - Select "Desktop app"
   - Download the JSON file

5. Save the JSON file as:
   {credentials_path}

6. Click "Connect to Google Drive" again

The first time you connect, a browser window will open
for you to authorize the app."""

        messagebox.showinfo("Google Drive Setup", instructions)

    def _connect_keep(self):
        """Connect to Google Keep (legacy)"""
        messagebox.showinfo(
            "Google Keep Sync",
            "Google Keep API sync is no longer reliable.\n\n"
            "Please use the Takeout import method instead:\n"
            "1. Go to takeout.google.com\n"
            "2. Export your Keep notes\n"
            "3. Use 'Import from Takeout Folder'"
        )

    def _disconnect_keep(self):
        """Disconnect from Google Keep"""
        if messagebox.askyesno("Confirm", "Disconnect from Google Keep?"):
            self.sync_engine.logout()

    def _get_master_token(self):
        """Open master token generator"""
        TokenGeneratorDialog(self, "")

    def _save_imported_note(self, note: Note) -> bool:
        return self._save_imported_note_status(note) in IMPORT_SUCCESS_STATUSES

    def _save_imported_note_status(self, note: Note) -> str:
        if not note:
            return "failed"
        conflict = self.db.find_import_conflict(note)
        if conflict:
            if notes_equivalent(conflict, note):
                return "skipped"
            action = ImportConflictDialog(self, conflict, note).result
            if action == "local":
                return "skipped"
            if action == "imported":
                note.id = conflict.id
                note.created_at = conflict.created_at
                note.keep_id = conflict.keep_id
                result = self.db.save_imported_note(note, conflict_policy="replace")
                return "conflict_replace" if result == "imported" else result
            if action == "merge":
                result = self.db.save_imported_note(note, conflict_policy="merge")
                return "conflict_merge" if result == "imported" else result
        return self.db.save_imported_note(note, conflict_policy="copy")

    def _show_import_summary(self, source: str, notes: List[Note], statuses: List[str]):
        messagebox.showinfo("Import Complete", "\n".join(import_summary_lines(source, notes, statuses)))

    def _export_notes(self):
        """Export notes to JSON"""
        filepath = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if filepath:
            notes = self.db.get_all_notes(include_trashed=True, include_archived=True)
            data = {
                "version": self.db_version,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "notes": [note.to_dict() for note in notes],
                "labels": [label.to_dict() for label in self.db.get_all_labels()]
            }
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2)
            messagebox.showinfo("Export Complete", f"Exported {len(notes)} notes to {filepath}")

    def _export_markdown_vault(self):
        """Export all notes as an Obsidian-compatible Markdown vault."""
        folder = filedialog.askdirectory(title="Select Markdown vault folder")
        if not folder:
            return
        target_dir = Path(folder)

        def worker():
            try:
                notes = self.db.get_all_notes(include_trashed=True, include_archived=True)
                result = export_markdown_vault(notes, target_dir)
                message = (
                    f"Exported {result.notes_exported} notes to:\n{result.output_dir}\n\n"
                    f"Copied {result.attachments_copied} attachments."
                )
                if result.attachments_missing:
                    message += f"\nMissing attachments skipped: {result.attachments_missing}"
                self.after(0, lambda: messagebox.showinfo("Markdown Export Complete", message))
            except Exception as e:
                log_diagnostic_exception("markdown vault export", e)
                self.after(0, lambda message=str(e): messagebox.showerror("Markdown Export Failed", message))

        threading.Thread(target=worker, daemon=True).start()

    def _export_pdf_book(self):
        """Export all notes as a single PDF book."""
        filepath = filedialog.asksaveasfilename(
            title="Save PDF Book",
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if not filepath:
            return
        output_path = Path(filepath)

        def worker():
            try:
                notes = self.db.get_all_notes(include_trashed=False, include_archived=True)
                result = export_pdf_book(notes, output_path, title=self.app_name)
                message = f"Exported {result.notes_exported} notes ({result.pages} pages) to:\n{result.output_path}"
                self.after(0, lambda: messagebox.showinfo("PDF Export Complete", message))
            except Exception as e:
                log_diagnostic_exception("pdf book export", e)
                self.after(0, lambda message=str(e): messagebox.showerror("PDF Export Failed", message))

        threading.Thread(target=worker, daemon=True).start()

    def _run_import_with_progress(
        self,
        title: str,
        source_name: str,
        import_func: Callable[[MultiSourceImporter], List[Note]],
        empty_message: str,
    ):
        progress_dialog = ImportProgressDialog(self, title)

        def progress(message: str, current: int, total: int):
            self.after(0, lambda: progress_dialog.set_progress(message, current, total))

        def complete(notes: List[Note]):
            progress_dialog.destroy()
            if not notes:
                messagebox.showerror("No Notes Found", empty_message)
                return
            statuses = [self._save_imported_note_status(note) for note in notes]
            self._show_import_summary(source_name, notes, statuses)

        def failed(message: str):
            progress_dialog.destroy()
            messagebox.showerror("Import Failed", message)

        def cancelled():
            progress_dialog.destroy()
            messagebox.showinfo("Import Cancelled", "Import cancelled before all files were processed.")

        def worker():
            try:
                LocalBackupManager(self.db, self.app_name, self.app_version).create_backup(f"before {source_name} import")
                importer = MultiSourceImporter(
                    self.db,
                    progress_callback=progress,
                    cancel_check=progress_dialog.is_cancelled,
                )
                notes = import_func(importer)
                self.after(0, lambda: complete(notes))
            except ImportCancelled:
                self.after(0, cancelled)
            except Exception as e:
                log_diagnostic_exception(f"{source_name} import", e)
                self.after(0, lambda message=str(e): failed(message))

        threading.Thread(target=worker, daemon=True).start()

    def _import_external_source(self):
        """Import notes from another note app export."""
        source_type = self.external_source_var.get()
        folder_sources = {"Obsidian Vault", "OneNote HTML Folder"}

        if source_type in folder_sources:
            selected = filedialog.askdirectory(title=f"Select {source_type}")
        else:
            selected = filedialog.askopenfilename(
                title=f"Select {source_type}",
                filetypes=[
                    ("Supported exports", "*.enex *.zip *.json"),
                    ("ENEX files", "*.enex"),
                    ("ZIP files", "*.zip"),
                    ("JSON files", "*.json"),
                    ("All files", "*.*"),
                ],
            )

        if not selected:
            return

        selected_path = Path(selected)
        self._run_import_with_progress(
            f"Importing {source_type}",
            source_type,
            lambda importer: importer.import_external(source_type, selected_path),
            f"No notes were found in the selected {source_type} export.",
        )

    def _import_notes(self):
        """Import notes from JSON"""
        filepath = filedialog.askopenfilename(
            filetypes=[
                ("JSON files", "*.json"),
                ("Google Takeout", "*.json"),
                ("All files", "*.*")
            ]
        )
        if filepath:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)

                LocalBackupManager(self.db, self.app_name, self.app_version).create_backup("before json import")
                imported = 0

                # Check if this is a Google Takeout export
                if isinstance(data, dict) and "textContent" in data:
                    # Single Google Keep note from Takeout
                    note = self._parse_takeout_note(data, Path(filepath).parent)
                    if self._save_imported_note(note):
                        imported = 1
                elif isinstance(data, list):
                    # Multiple notes or Takeout folder
                    for item in data:
                        if isinstance(item, dict):
                            if "textContent" in item or "title" in item:
                                # Takeout format
                                note = self._parse_takeout_note(item, Path(filepath).parent)
                            else:
                                # Our export format
                                note = Note.from_dict(item)

                            if note:
                                note.id = str(uuid.uuid4())
                                note.keep_id = None
                                note.sync_status = SyncStatus.LOCAL_ONLY
                                if self._save_imported_note(note):
                                    imported += 1
                elif isinstance(data, dict) and "notes" in data:
                    # Our export format
                    for note_data in data.get("notes", []):
                        note = Note.from_dict(note_data)
                        note.id = str(uuid.uuid4())
                        note.keep_id = None
                        note.sync_status = SyncStatus.LOCAL_ONLY
                        if self._save_imported_note(note):
                            imported += 1

                messagebox.showinfo("Import Complete", f"Imported {imported} notes")
            except Exception as e:
                log_diagnostic_exception("JSON import", e)
                messagebox.showerror("Import Failed", str(e))

    def _parse_takeout_note(self, data: dict, base_path: Optional[Path] = None) -> Optional[Note]:
        """Parse a Google Takeout Keep note format"""
        try:
            note_id = str(uuid.uuid4())
            title = data.get("title", "")
            content = data.get("textContent", "")

            # Check for checklist
            checklist_items = []
            if "listContent" in data:
                for item in data["listContent"]:
                    checklist_items.append(ChecklistItem(
                        text=item.get("text", ""),
                        checked=item.get("isChecked", False)
                    ))

            # Parse labels
            labels = []
            if "labels" in data:
                labels = [l.get("name", "") for l in data["labels"] if l.get("name")]

            attachments_root = Path(self.db.db_path).parent / "attachments"
            attachments = import_takeout_attachments(data, base_path, attachments_root, note_id)

            return Note(
                id=note_id,
                title=title,
                content=content,
                note_type=NoteType.CHECKLIST if checklist_items else NoteType.NOTE,
                checklist_items=checklist_items,
                labels=labels,
                attachments=attachments,
                pinned=data.get("isPinned", False),
                archived=data.get("isArchived", False),
                trashed=data.get("isTrashed", False),
                color=normalize_keep_color(data.get("color", "")),
                shared_with=extract_shared_with(data),
                sync_status=SyncStatus.LOCAL_ONLY,
            )
        except Exception:
            return None

    def _import_from_browser(self):
        """Import notes using browser cookies"""
        if not self.web_scraper_factory:
            messagebox.showerror("Browser Import Unavailable", "Browser import is not configured.")
            return

        # Show progress
        progress_dialog = ctk.CTkToplevel(self)
        progress_dialog.title("Importing from Browser")
        progress_dialog.geometry("400x200")
        progress_dialog.configure(fg_color=COLORS["bg_dark"])
        progress_dialog.transient(self)
        progress_dialog.grab_set()

        status_label = ctk.CTkLabel(
            progress_dialog,
            text="Checking browser for Google cookies...",
            font=ctk.CTkFont(size=13),
            text_color=COLORS["text_primary"]
        )
        status_label.pack(pady=(40, 20))

        progress_bar = ctk.CTkProgressBar(progress_dialog, mode="indeterminate")
        progress_bar.pack(fill="x", padx=40)
        progress_bar.start()
        configure_modal_dialog(progress_dialog, self, initial_focus=progress_dialog)

        def do_import():
            scraper = self.web_scraper_factory()

            # Update status
            self.after(0, lambda: status_label.configure(text="Authenticating via browser cookies..."))

            success, message = scraper.authenticate_from_browser()

            if not success:
                self.after(0, lambda: self._browser_import_failed(progress_dialog, message))
                return

            self.after(0, lambda: status_label.configure(text="Fetching notes from Google Keep..."))

            try:
                LocalBackupManager(self.db, self.app_name, self.app_version).create_backup("before browser import")
            except Exception as e:
                log_diagnostic_exception("browser import backup", e)
                self.after(0, lambda message=str(e): self._browser_import_failed(progress_dialog, f"Backup failed before browser import: {message}"))
                return

            imported, errors = scraper.import_notes_to_db(self.db)

            self.after(0, lambda: self._browser_import_complete(progress_dialog, imported, errors, message))

        threading.Thread(target=do_import, daemon=True).start()

    def _browser_import_failed(self, dialog, message: str):
        """Handle browser import failure"""
        dialog.destroy()

        # Offer Google Takeout as alternative
        result = messagebox.askyesno(
            "Browser Import Failed",
            f"{message}\n\n"
            "Would you like instructions for importing via Google Takeout instead?\n"
            "(This is the most reliable method)"
        )

        if result:
            TakeoutInstructionsDialog(self)

    def _browser_import_complete(self, dialog, imported: int, errors: int, auth_message: str):
        """Handle browser import completion"""
        dialog.destroy()

        if imported > 0:
            messagebox.showinfo(
                "Import Complete",
                f"Successfully imported {imported} notes!\n\n"
                f"Authentication: {auth_message}\n"
                f"Errors: {errors}"
            )
        else:
            # Offer Takeout instructions
            result = messagebox.askyesno(
                "No Notes Imported",
                "Could not extract notes from Google Keep page.\n\n"
                "This can happen if Google changed their page structure.\n\n"
                "Would you like instructions for importing via Google Takeout?\n"
                "(This is the most reliable method)"
            )

            if result:
                TakeoutInstructionsDialog(self)

    def _import_takeout_folder(self):
        """Import all notes from a Google Takeout Keep folder"""
        folder = filedialog.askdirectory(
            title="Select Google Takeout Keep Folder"
        )

        if not folder:
            return

        folder_path = Path(folder)
        self._run_import_with_progress(
            "Importing Google Takeout",
            "Google Takeout",
            lambda importer: importer.import_takeout_path(folder_path),
            "No JSON files found in the selected folder.\n\n"
            "Make sure you:\n"
            "1. Extracted the ZIP file from Google Takeout\n"
            "2. Selected the 'Keep' folder or the Takeout ZIP",
        )
