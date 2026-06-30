# Research - KeepSyncNotes

## Executive Summary
KeepSyncNotes is a local-first Python/CustomTkinter desktop note manager centered on Google Keep Takeout import, SQLite storage, FTS search, note editing, reminders, attachments, and multi-source imports. Its strongest current shape is an offline migration and local archive tool, not a trustworthy multi-device sync tool yet. Highest-value direction: make the existing local archive dependable before adding more note surfaces. Top opportunities: fix saved-search/FTS regressions, move credentials out of SQLite/plain JSON, replace runtime dependency installation with standard packaging, harden ZIP/import limits, add real diagnostics/crash logging, add versioned backup/restore before sync/import, split the 6,900-line app into testable modules, add import fidelity reports, make dialogs/focus accessible, and document cloud-sync conflict semantics honestly.

## Product Map
- Core workflows: import Google Takeout ZIP/folder exports; import ENEX/Standard Notes/Obsidian/Bear/Simplenote/OneNote exports; browse/search/filter/saved-search local notes; edit notes/checklists/labels/colors/reminders; sync/backup through unofficial Keep, Google Drive, or GitHub paths.
- User personas: Keep users leaving Google; archivists wanting local searchable Takeout data; note-app migrants testing Joplin/Obsidian/Standard Notes style flows; privacy-minded users who do not want cloud dependency.
- Platforms and distribution: Python 3.8+ desktop app for Windows/macOS/Linux; currently source-run only with startup pip install; only GitHub release is v1.0.0 with no attached artifact.
- Key integrations and data flows: Google Takeout JSON/media -> SQLite + attachments folder; gkeepapi unofficial Keep sync -> SQLite; Drive/GitHub cloud providers -> JSON backup/sync; local JSON export -> re-import.

## Competitive Landscape
- keep-it-markdown: strong Keep-specific markdown export/import, target-aware Obsidian/Logseq/Joplin/Notion modes, keyring token storage, batch filters, media handling, and warnings about unofficial API risk. Learn its explicit token storage, export templates, duplicate-title handling, and batch/reporting model; avoid its CLI-only UX as the main experience.
- gkeepapi: de facto unofficial Keep client and current dependency. Learn from its warning that the official Google Keep API exists for some Enterprise accounts and that gkeepapi is unsupported by Google; avoid positioning live Keep sync as equally reliable as Takeout.
- Joplin: mature offline-first notes app with import/export, plugin ecosystem, conflict notebooks, note history, OCR, mobile apps, E2EE sync, and documented accessibility topics. Learn conflict/recovery UX and lossless export formats; avoid trying to match the full app ecosystem before Keep import/archive safety is solid.
- Memos: focused self-hosted quick-capture product with Markdown portability, REST/gRPC APIs, small binary deployment, and clear data ownership. Learn its low-friction capture and API/export story; avoid adding server requirements to the default local desktop flow.
- Obsidian Sync: commercial benchmark for sync expectations: E2EE, version history, selective attachment sync, file recovery, shared vaults, and sync activity detail. Learn recovery/version-history expectations; avoid paywalled-team complexity unless local reliability is already excellent.
- Standard Notes: privacy-first competitors make encryption, cross-platform clients, backups, and account recovery central. Learn the trust language and secret-handling bar; avoid storing tokens or backups in plaintext when the app says local/private.
- Google Keep: table-stakes capture includes labels, reminders, colors, sharing metadata, images/audio, archive/trash, and Takeout export. KeepSyncNotes should preserve these states and be transparent where round-trip/live sync cannot.

## Security, Privacy, and Reliability
- Verified risk: `KeepSyncEngine.login` stores `keep_master_token` in the SQLite settings table at `keepsync_notes.py:1708`; `GoogleDriveSync.connect` writes OAuth token JSON under `~/.keepsync_notes` at `keepsync_notes.py:2524`; keyring is a better fit for secrets.
- Verified risk: dependency auto-install runs at import/startup (`keepsync_notes.py:21`, `keepsync_notes.py:104`, `keepsync_notes.py:2502`), and the test run installed optional cloud/auth packages. This makes startup non-deterministic and weakens supply-chain control.
- Verified bug: saved searches can persist FTS-backed queries, but `_refresh_notes_list` re-filters saved-search results by title/body only (`keepsync_notes.py:6447`, `keepsync_notes.py:6452`), dropping checklist/label FTS matches; filter-only archived saved searches also start from non-archived notes.
- Verified risk: Takeout ZIP import extracts whole archives without size/member limits (`keepsync_notes.py:1585`); Python docs call out decompression bombs and filesystem limits as ZIP pitfalls.
- Verified risk: Drive/GitHub sync only imports remote notes missing locally and uses timestamp/file replacement logic (`keepsync_notes.py:2605`, `keepsync_notes.py:2803`), so changed-on-both-sides conflicts lack a base snapshot, visible conflict copy, or restore path.
- Verified risk: many exception paths print, swallow, or only write `sync_log`; there is no user-visible diagnostics panel or crash log file despite sync/import/cloud flows that can fail silently.

## Architecture Assessment
- `keepsync_notes.py` is a 6,900-line all-in-one module mixing dependency bootstrap, models, DB, importers, sync providers, dialogs, editor, and app shell; split into `models`, `storage`, `importers`, `sync`, `ui`, and `packaging` modules before larger sync/export work.
- `DatabaseManager` uses JSON blobs for checklists, labels, shared-with, attachments, and settings. That is pragmatic for the current app, but migration/version handling should be explicit before adding encrypted backup or bidirectional sync.
- `CloudSyncProvider` is a minimal abstract base, but concrete providers do not share conflict/backup/version policies. Introduce a provider contract for dry-run diff, apply, rollback, and conflict reporting.
- Tests cover import adapters, markdown helpers, advanced filters, and FTS, but not UI flow, credential migration, ZIP guardrails, cloud sync conflict cases, backup/restore, saved-search behavior, or packaging.
- Documentation still says dependencies auto-install on first run, while memory/stack conventions require normal `requirements.txt`/venv setup; roadmap should drive packaging cleanup rather than adding more runtime installers.

## Official Google Keep API Evaluation - 2026-06-30
- Google documents the official Keep API as a REST API for enterprise administrators managing Keep notes, including note create/list/delete, attachment download, and permission mutation. The documented use case is enterprise governance/CASB remediation, not personal desktop note sync.
- The REST reference exposes `v1.notes` create/delete/get/list, `v1.media.download`, and `v1.notes.permissions` batch permission methods. It is useful for Workspace-admin workflows, but it does not remove the product risk of presenting live Keep sync as a normal consumer-account feature.
- Google documents authorization through domain-wide delegation with a service account or OAuth client ID for enterprise apps. That requires Workspace administrator approval and domain-level trust, so it is not a good default for personal Gmail users.
- Decision: keep Takeout import as the default safe path, keep Google Drive/GitHub as practical user-controlled sync/backup targets, and treat an official Keep API connector as a future optional Workspace-only feature if a real admin-backed use case appears.

## Rejected Ideas
- Full collaborative multi-user editing: Obsidian/Joplin/Standard Notes prove it is valuable, but it conflicts with this app's local archive/migration shape until conflict/version history exists.
- First-class plugin ecosystem: Joplin shows plugin value, but the current monolith lacks stable internal APIs; revisit after module boundaries are real.
- Web/server rewrite: Memos proves a server can work, but KeepSyncNotes' differentiator is local desktop Takeout handling.
- Live unofficial Keep writeback as the default path: keep-it-markdown and gkeepapi both show it is possible, but unsupported API/auth fragility makes Takeout-first plus explicit risk messaging safer.
- Automated summarization before trust work: KeepSyncNotes needs deterministic import, backups, and privacy controls first.

## Sources
Project:
- https://github.com/SysAdminDoc/KeepSyncNotes

Keep / Keep-specific OSS:
- https://support.google.com/keep/answer/2888240
- https://support.google.com/accounts/answer/3024190
- https://developers.google.com/workspace/keep/api/guides
- https://developers.google.com/workspace/keep/api/reference/rest
- https://github.com/djsudduth/keep-it-markdown
- https://github.com/kiwiz/gkeepapi
- https://github.com/ndbeals/keep-exporter
- https://github.com/vHanda/google-keep-exporter
- https://github.com/k4j8/google-keep-takeout

Note apps and sync benchmarks:
- https://github.com/laurent22/joplin
- https://joplinapp.org/help/apps/conflict/
- https://joplinapp.org/help/apps/import_export/
- https://github.com/usememos/memos
- https://obsidian.md/sync
- https://standardnotes.com/features

Standards, platform, and dependencies:
- https://docs.python.org/3/library/zipfile.html#decompression-pitfalls
- https://sqlite.org/fts5.html
- https://keyring.readthedocs.io/en/latest/
- https://platformdirs.readthedocs.io/en/latest/
- https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html
- https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/

## Open Questions
- Should GitHub sync target only private repositories by default, and should the app block public-repo selection when notes may contain sensitive data?
- Is the intended primary release format source-only, a signed Windows EXE, or cross-platform packaged apps?
