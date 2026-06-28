# Changelog

All notable changes to KeepSyncNotes will be documented in this file.

## [v1.16.0] - 2026-06-28

- Added versioned local ZIP backups containing the SQLite database, manifest, and attachment files.
- Created automatic pre-change backups before imports, Keep sync, Drive sync, and GitHub sync.
- Added Data-tab controls for manual backup creation and in-app restore with a pre-restore safety backup.

## [v1.15.0] - 2026-06-28

- Added ZIP import safety guards for member counts, uncompressed size, path traversal, and extension allowlists.
- Replaced Takeout ZIP `extractall` with per-member safe extraction.
- Added cancellable progress handling for manual Takeout and external-source imports.

## [v1.14.0] - 2026-06-28

- Added pinned `requirements.txt` for deterministic dependency installation.
- Removed startup and feature-level runtime package installation paths.
- Updated setup docs and tests to guard against reintroducing runtime installers.

## [v1.13.0] - 2026-06-28

- Moved Keep master tokens, Google Drive OAuth tokens, and GitHub PATs into the OS keyring.
- Added one-time migration and cleanup for legacy SQLite Keep tokens and Google Drive token JSON files.
- Removed the CLI path that saved Keep master tokens to `master_token.txt`.

## [v1.12.1] - 2026-06-28

- Fixed saved searches so FTS matches from labels and checklist items remain visible.
- Fixed filter-only saved searches so archived-note filters include archived notes.
- Added regression coverage for saved-search FTS and archived-filter behavior.

## [v1.12.0] - 2026-06-28

- Added saved searches backed by local settings storage.
- Added a sidebar Saved Searches section that opens saved query/filter combinations as virtual folders.
- Added a Save action beside advanced filters for persisting the current search state.

## [v1.11.0] - 2026-06-27

- Added an advanced filters dialog with AND/OR matching.
- Added label, color, date range, image, checklist, and archived-note predicates.
- Routed all-notes text search through FTS while preserving filter support.

## [v1.10.0] - 2026-06-27

- Added SQLite FTS5 indexing for note titles, body text, checklist item text, and labels.
- Added ranked FTS search with LIKE fallback when FTS5 is unavailable.
- Kept the FTS index synchronized on note saves, trash, and permanent deletes.

## [v1.9.0] - 2026-06-27

- Added delta-aware import summaries for foreground Takeout and external-source imports.
- Reported unchanged/local-kept skips separately from imported notes.
- Reused duplicate detection so re-imported exports add only new or changed notes.

## [v1.8.0] - 2026-06-27

- Added foreground import conflict resolution with a unified diff and Keep Local, Use Imported, and Merge choices.
- Added duplicate detection for imported notes by title.
- Added noninteractive conflict handling for background imports by skipping identical duplicates and saving differing duplicates as conflict-marked copies.

## [v1.7.0] - 2026-06-27

- Added a configurable Google Takeout auto-import watcher for dropped ZIP exports and extracted Keep folders.
- Added background polling with processed-file signatures so stable exports are imported once.
- Reused the shared importer/save path for manual Takeout imports and watcher imports.

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
