# Changelog

All notable changes to KeepSyncNotes will be documented in this file.

## [v1.6.0] - 2026-06-27

- Added stdlib-only import adapters for ENEX, Standard Notes ZIP, Obsidian vaults, Bear ZIP/textbundle exports, Simplenote JSON/ZIP exports, and OneNote HTML/TXT folders.
- Added a Data tab source selector and import action for non-Keep imports.
- Ensured imported labels are saved to the local label table so they appear in the sidebar.

## [v1.5.0] - 2026-06-27

- Added `.md` label detection for text notes.
- Added a markdown edit/preview toggle with rendered headings, lists, tasks, quotes, code, and inline emphasis.
- Displayed markdown-aware note-card preview text and a Markdown card badge.
- Made dependency installer status output safe for the default Windows console encoding.

## [v1.4.0] - 2026-06-27

- Added attachment metadata with automatic SQLite migration and JSON export/import support.
- Copied Google Takeout attachment files into the local app data folder during folder/JSON imports.
- Displayed attachment summaries on note cards and inline image thumbnails/open buttons in the editor.

## [v1.3.0] - 2026-06-27

- Added `shared_with` note metadata with automatic SQLite migration.
- Preserved sharing/collaborator metadata from Takeout exports, JSON exports, and best-effort live Keep sync conversion.
- Displayed shared-with metadata in note cards and the editor without adding re-sharing behavior.

## [v1.2.0] - 2026-06-27

- Added local date/time reminders with optional location context.
- Added due-reminder polling, note-card reminder labels, and desktop notifications through `plyer` when available.
- Added SQLite reminder columns with automatic migration for existing note databases.

## [v1.1.0] - 2026-06-27

- Added nested checklist item indentation and row reordering controls.
- Added Keep color palette selection, normalized color import/sync handling, and note-card color swatches.
- Documented completed checklist/color/pin support and bumped the app version.

## [v0.1.0] - %Y->- (HEAD -> main, origin/main, origin/HEAD)

- docs: expand README with quick start, usage details, and feature descriptions
- Added: Add comprehensive README
- Changed: Update keepsync_notes.py
- Added: Add files via upload
