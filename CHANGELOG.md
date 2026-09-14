# Changelog

Notable KeepSync Notes changes are recorded here. The full commit history retains the details from earlier releases.

## [v1.56.1] - 2026-09-13

- Reworked the README around a version-free marketing hero and two verified product screenshots.
- Replaced the opaque text-heavy icon with a transparent note relay identity and a complete size set.
- Added a one-file Windows release build, private-desktop capture tooling, and regression coverage for the README visuals and packaged entry point.

## [v1.56.0] - 2026-08-09

- Closed the actionable roadmap and synchronized project metadata.

## [v1.55.0] - 2026-06-30

- Added optional local semantic search through fastembed and lancedb.

## [v1.54.0] - 2026-06-30

- Added optional Tesseract OCR for text stored in image attachments.

## [v1.53.0] - 2026-06-30

- Added Windows clipboard history import through WinRT.

## [v1.52.0] - 2026-06-30

- Added daily review mode for resurfacing older notes.

## [v1.51.0] - 2026-06-30

- Added a system tray with quick capture, show, hide, and quit actions.

## [v1.50.0] - 2026-06-30

- Added the Catppuccin Latte light theme and an in-app theme selector.

## [v1.49.0] - 2026-06-30

- Added pop-out note windows for side-by-side editing.

## [v1.48.0] - 2026-06-30

- Added password-protected AES-256-GCM backups with PBKDF2 key derivation.

## v1.47.0 through v1.41.0

- Added Markdown vault and PDF book exports with attachment and checklist support.
- Brought local voice recording, Whisper transcription, image drag and drop, clipboard paste, and image attachment tools into the editor.
- Added Markdown editing controls, tag relationships, and hierarchical folders.
- Split the app shell, editor, and shared components into focused modules.

## v1.40.0 through v1.33.0

- Separated app metadata, bootstrap code, settings, cloud providers, and modal behavior from the compatibility entry point.
- Added consistent focus handling for dialogs and dedicated tests for the new module boundaries.

## v1.32.0 through v1.24.0

- Kept Takeout as the default import path while documenting the limits of unofficial Keep access.
- Replaced destructive confirmation dialogs with undo and automatic safety backups.
- Added import fidelity reports, platform data paths, SQLite FTS5, saved searches, and advanced filters.
- Moved storage, import logic, credentials, diagnostics, and note operations into dedicated modules.

## v1.23.0 through v1.14.0

- Added local backup and restore with database and attachment manifests.
- Guarded ZIP and folder imports against traversal, oversized archives, hidden files, and unsupported content.
- Added cloud sync planning with base hashes, conflict copies, and dry-run counts.
- Pinned runtime dependencies and removed package installation from app startup.

## v1.13.0 through v1.6.0

- Moved Keep, Google Drive, and GitHub secrets into the operating system keyring.
- Added multi-source import for ENEX, Standard Notes, Obsidian, Bear, Simplenote, and OneNote exports.
- Added Takeout folder watching, conflict review, delta-aware re-imports, and saved search support.

## v1.5.0 through v0.1.0

- Added Markdown previews, Takeout attachments, sharing metadata, reminders, nested checklists, and Keep color preservation.
- Published the first desktop importer and local note manager on 2026-04-13.
