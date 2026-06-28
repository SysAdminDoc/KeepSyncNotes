# Changelog

All notable changes to KeepSyncNotes will be documented in this file.

## [v1.23.0] - 2026-06-28

- Moved the `Label` data model into `keepsync_models.py` with the other note data classes.
- Removed the remaining dataclass dependency from `keepsync_notes.py`.
- Added regression coverage for label round-tripping and app compatibility re-export.

## [v1.22.0] - 2026-06-28

- Extracted local database and attachment backup/restore logic into `keepsync_backups.py`.
- Passed app name and version into backup creation so manifests stay synchronized after version bumps.
- Added direct backup module coverage for manifest metadata and app compatibility re-export.

## [v1.21.0] - 2026-06-28

- Extracted ZIP and folder import safety limits, traversal checks, guarded extraction, and cancellation exceptions into `keepsync_import_safety.py`.
- Kept importers and backup restore wired through the shared safety module.
- Updated import safety tests to patch the live module limit instead of the app re-export.

## [v1.20.0] - 2026-06-28

- Extracted cloud sync hash, base-version, dry-run count, delete, and conflict-copy planning into `keepsync_cloud_plan.py`.
- Kept Google Drive and GitHub provider behavior wired through compatibility imports in `keepsync_notes.py`.
- Updated cloud sync regression tests to exercise the extracted planner module directly.

## [v1.19.0] - 2026-06-28

- Extracted note models, attachment/checklist models, Keep color normalization, and shared metadata helpers into `keepsync_models.py`.
- Kept the existing `keepsync_notes.py` public model names as compatibility re-exports.
- Added direct regression coverage for the extracted model module.

## [v1.18.0] - 2026-06-28

- Added three-way cloud sync planning for Google Drive and GitHub using per-note base hashes.
- Reported dry-run create, update, delete, and conflict counts before applying cloud sync changes.
- Preserved remote conflict copies locally when both sides changed or first-run shared notes diverged.

## [v1.17.0] - 2026-06-28

- Added a file-backed diagnostics manager with unhandled exception and thread crash hooks.
- Added a Data-tab diagnostics panel showing dependency state, database/attachment paths, last exception, and recent log entries.
- Logged handled import, sync, auth, Drive, and GitHub errors to the diagnostics log.

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
