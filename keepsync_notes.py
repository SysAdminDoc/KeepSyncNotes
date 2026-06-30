#!/usr/bin/env python3
"""Compatibility entry point for KeepSync Notes."""

import sys

import customtkinter as ctk

from keepsync_app import (
    DESKTOP_NOTIFICATIONS_AVAILABLE,
    KeepSyncNotesApp,
    desktop_notification,
)
from keepsync_app_info import APP_NAME, APP_VERSION, DB_VERSION
from keepsync_attachment_editing import (
    IMAGE_FILETYPES,
    ImageAttachmentBatchResult,
    copy_image_attachments,
    copy_image_attachment,
    is_supported_image_path,
    note_attachment_dir,
    parse_drop_file_paths,
    save_clipboard_image_attachment,
    unique_attachment_path,
)
from keepsync_dragdrop import drop_copy_action, enable_file_drop
from keepsync_backups import LocalBackupManager
from keepsync_bootstrap import run_bootstrap
from keepsync_cloud_plan import (
    build_cloud_sync_plan,
    cloud_base_versions,
    cloud_plan_counts,
    note_data_hash,
    save_cloud_conflict_copy,
)
from keepsync_cloud_sync import (
    CloudSyncManager,
    CloudSyncProvider,
    GitHubSync,
    GoogleDriveSync,
)
from keepsync_credentials import (
    GDRIVE_OAUTH_TOKEN_CREDENTIAL,
    GITHUB_PAT_CREDENTIAL,
    KEEP_MASTER_TOKEN_CREDENTIAL,
    KEYRING_AVAILABLE,
    KeyringCredentialStore,
    migrate_file_secret,
    migrate_setting_secret,
    store_file_secret,
)
from keepsync_diagnostics import (
    DiagnosticsManager,
    log_diagnostic_event,
    log_diagnostic_exception,
    set_diagnostics_manager,
)
from keepsync_folders import (
    FOLDER_SEPARATOR,
    folder_display_name,
    folder_path_depth,
    folder_paths_from_label,
    folder_paths_from_labels,
    normalize_folder_path,
    note_matches_folder,
)
from keepsync_import_reports import IMPORT_SUCCESS_STATUSES, import_summary_lines
from keepsync_import_safety import (
    MAX_IMPORT_FOLDER_BYTES,
    MAX_IMPORT_FOLDER_FILES,
    MAX_IMPORT_TEXT_MEMBER_BYTES,
    MAX_IMPORT_ZIP_MEMBERS,
    MAX_IMPORT_ZIP_UNCOMPRESSED_BYTES,
    ImportCancelled,
    ImportSafetyError,
    decode_zip_member,
    extract_zip_member_safely,
    guarded_import_files,
    is_hidden_or_system_path,
    safe_zip_member_parts,
    validate_zip_members,
)
from keepsync_importers import (
    HTMLTextExtractor,
    MultiSourceImporter,
    extract_shared_with,
    html_to_text,
    import_takeout_attachments,
    parse_external_datetime,
)
import keepsync_keep_sync as keep_sync_state
from keepsync_keep_sync import (
    GKEEPAPI_AVAILABLE,
    KeepSyncEngine,
    KeepWebScraper,
    extract_token_from_browser,
    get_master_token_cli,
)
from keepsync_models import (
    Attachment,
    ChecklistItem,
    KEEP_COLOR_ALIASES,
    KEEP_COLOR_PALETTE,
    Label,
    Note,
    NoteType,
    SyncStatus,
    clamp_checklist_indent,
    guess_attachment_mime,
    keep_color_hex,
    keep_color_name,
    normalize_keep_color,
    normalize_people,
    sanitize_filename,
)
from keepsync_markdown_editing import MARKDOWN_PLACEHOLDERS, format_markdown_selection
from keepsync_note_editor import NoteEditor
from keepsync_note_ops import (
    advanced_filters_active,
    default_advanced_filters,
    merge_note_conflict,
    normalize_import_labels,
    note_conflict_diff,
    note_matches_advanced_filters,
    note_diff_body,
    notes_equivalent,
    parse_filter_date,
)
from keepsync_note_text import (
    format_reminder_datetime,
    is_markdown_label,
    markdown_preview_blocks,
    markdown_preview_text,
    note_uses_markdown,
    parse_reminder_datetime,
    split_inline_markdown,
)
from keepsync_paths import (
    get_app_data_dir,
    get_google_drive_credentials_path,
    get_google_drive_token_path,
)
from keepsync_settings_dialog import SettingsDialog
from keepsync_storage import DatabaseManager
from keepsync_tag_graph import (
    TagEdge,
    TagGraph,
    TagNode,
    build_tag_graph,
    normalized_note_labels,
    tag_graph_summary_lines,
)
from keepsync_theme import COLORS
from keepsync_ui_components import (
    IconManager,
    NoteCard,
    SyncStatusBadge,
    configure_note_card_helpers,
)
from keepsync_ui_dialogs import (
    AdvancedFilterDialog,
    DiagnosticsDialog,
    ImportConflictDialog,
    ImportProgressDialog,
    TakeoutInstructionsDialog,
    TokenGeneratorDialog,
)
from keepsync_ui_modal import configure_modal_dialog

configure_note_card_helpers(
    note_uses_markdown_func=note_uses_markdown,
    markdown_preview_text_func=markdown_preview_text,
    format_reminder_datetime_func=format_reminder_datetime,
)

SECURE_CREDENTIALS = keep_sync_state.SECURE_CREDENTIALS


def set_secure_credential_store(store):
    """Swap the credential store for tests while preserving app-level compatibility."""
    global SECURE_CREDENTIALS
    keep_sync_state.set_secure_credential_store(store)
    SECURE_CREDENTIALS = keep_sync_state.SECURE_CREDENTIALS


def main(argv=None):
    args = sys.argv if argv is None else argv
    return run_bootstrap(
        args,
        app_factory=KeepSyncNotesApp,
        token_cli=get_master_token_cli,
        app_name=APP_NAME,
        app_version=APP_VERSION,
        set_appearance_mode=ctk.set_appearance_mode,
        set_default_color_theme=ctk.set_default_color_theme,
    )


if __name__ == "__main__":
    sys.exit(main())
