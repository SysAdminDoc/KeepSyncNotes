# KeepSyncNotes Roadmap

Google Keep importer + local note manager (PyQt6, SQLite, Catppuccin Mocha). Currently imports from Takeout and provides browse/search/tag/edit. Roadmap pushes toward Keep feature parity, sync, and multi-source import.

## Planned Features

### Note Feature Parity
- **Checklist/todo items** — first-class todo list rendering, drag to reorder, indent for sub-items
- **Color labels** — full palette matching Keep's 12 colors, color swatch in note card
- **Pinned notes** — pin to top section
- **Reminders** — date/time reminders with optional location (geofence), desktop notifications
- **Sharing metadata** — preserve "shared with X" info from Takeout even if we can't re-share
- **Attachments** — images, audio recordings, drawings exported from Keep; show inline
- **Markdown mode** — optional markdown rendering for notes tagged `.md`

### Import & Sync
- **Google Keep API live sync** — reverse-engineer gkeepapi-style access, sync bidirectionally (write-back to Keep)
- **Multi-source import** — Apple Notes (enex), Evernote (enex), Standard Notes (txt-zip), OneNote, Obsidian vault, Bear (bear-zip), Simplenote
- **Auto-import watcher** — drop a Takeout into a watched folder, auto-ingest new notes
- **Conflict resolution** — if same note exists on import, diff-based merge with user choice
- **Delta import** — re-import a newer Takeout and only add new/changed notes

### Search & Organization
- **Full-text SQLite FTS5** — real ranked search instead of LIKE scan
- **Advanced filters** — AND/OR of label + color + date-range + has-image + has-checklist + is-archived
- **Saved searches** — pin a filter set as a virtual folder in the sidebar
- **Folders on top of labels** — hierarchical organization Keep doesn't offer
- **Tag graph** — visualize notes by shared labels

### Editor
- **Rich-text / Markdown hybrid** — inline formatting toolbar, markdown shortcuts (`**bold**`)
- **Image paste + drag-drop** — inline images, auto-resized to sensible width
- **Audio recording inline** — record voice notes via `sounddevice`, transcribe via local Whisper
- **Global hotkey** — `Ctrl+Alt+N` from anywhere to pop a quick-note capture window

### Export & Portability
- **Export all to Markdown vault** — Obsidian-compatible `notes/YYYY-MM-DD-title.md` with YAML frontmatter
- **Export to PDF book** — compile selected notes into a single PDF
- **Encrypted backup** — AES-GCM SQLite dump with password

### UX
- **Keyboard navigation** — j/k list nav, Enter to open, / to search, everything reachable without mouse
- **Multi-window** — open a note in its own window for side-by-side
- **System tray** — quick-capture from tray, notification center
- **Dark/light theme** — keep Catppuccin as default, add a light Mocha counterpart (Latte)

## Competitive Research
- **Google Keep native** — web + Android + iOS, auto-sync, but no bulk ops and no export beyond Takeout. KeepSyncNotes wins on local + bulk + no cloud.
- **Joplin** — biggest OSS note tool with real sync backends. Reference for encrypted sync design.
- **Obsidian** — markdown-vault king; pairs well as an export target rather than a competitor.
- **Standard Notes** — end-to-end encrypted, subscription-based for rich features. Take the security model as inspiration.
- **TiddlyWiki** — single-file personal wiki; different shape but similar "your data, your file" philosophy.

## Nice-to-Haves
- Local semantic search via `fastembed` + lancedb (already proven in Bookmark Organizer Pro)
- LLM summarization via LlamaLink endpoint for "summarize this week's notes"
- Android companion app (Kotlin/Compose) that reads the same SQLite over Syncthing
- OCR on imported images via Tesseract so handwritten scans are searchable
- Daily review mode: surface 3 random old notes to refresh memory (Anki-style)
- Import from clipboard history (Windows WinRT, macOS NSPasteboard) for captured snippets

## Open-Source Research (Round 2)

### Related OSS Projects
- djsudduth/keep-it-markdown — https://github.com/djsudduth/keep-it-markdown — most feature-rich: bi-directional Keep ↔ markdown sync for Obsidian, Apple Notes, Logseq, Joplin, Notion
- kiwiz/gkeepapi — https://github.com/kiwiz/gkeepapi — the unofficial Keep API every other tool wraps
- ndbeals/keep-exporter — https://github.com/ndbeals/keep-exporter — clean CLI markdown exporter
- vHanda/google-keep-exporter — https://github.com/vHanda/google-keep-exporter — export to markdown
- k4j8/google-keep-takeout — https://github.com/k4j8/google-keep-takeout — uses Google Takeout data (no login required, offline-friendly)
- bhngupta/KeepAPI — https://github.com/bhngupta/KeepAPI — thin Python wrapper example
- usememos/memos — https://github.com/usememos/memos — 58k-star self-hosted Keep replacement; migration destination for power users
- obsidianmd/obsidian-releases — plugin registry for "keep-to-obsidian" sync extensions worth tracking
- Laurent22/joplin — https://github.com/laurent22/joplin — OSS note app with rich sync/import patterns to borrow

### Features to Borrow
- **Bi-directional sync, not just export** (keep-it-markdown) — edit a markdown file locally, push changes back to Keep; this is the "sync" KeepSyncNotes name implies
- **Obsidian / Logseq / Joplin templated export** (keep-it-markdown) — target-aware front-matter, link syntax, attachment folder layout
- **Google Takeout fallback path** (google-keep-takeout) — for users who won't hand over credentials; accept `Takeout.zip`, extract, convert
- **Attachment sync** — download images/voice notes, rewrite links to relative paths in the exported markdown
- **Label → tag mapping** — Keep labels become Obsidian tags / Logseq `#tags` / Joplin tags with a user-editable mapping table
- **Checklist → GFM `- [ ]` task list** conversion — lossless round-trip (matters for bi-directional sync)
- **Pin + color preservation as front-matter** — `pinned: true`, `color: yellow` in YAML; doesn't clutter body text, round-trips on re-import
- **Incremental sync with last-sync timestamp** — avoid re-downloading unchanged notes; store timestamp per note ID
- **Local SQLite cache** (Joplin-style) — offline read/edit, sync queue for when Keep API is reachable
- **2FA/App Password handling with keyring** — gkeepapi needs an app password; use OS keyring (Windows Credential Manager / macOS Keychain) not plain config

### Patterns & Architectures Worth Studying
- keep-it-markdown's **`keep_sync()` loop** — stateless sync primitive; call returns a diff, caller decides what to apply
- Joplin's **three-way merge** on conflicting edits (local + remote + base) — necessary for bi-directional sync; pure-export tools don't need this
- Memos's **import adapters pattern** — one adapter per source (Keep, Notion, Evernote, Obsidian); structured pipeline rather than per-source scripts
- gkeepapi's **auth/session persistence** — master token stored once, session tokens refreshed transparently; avoids re-login on every run
- **Conflict resolution UI** for bi-directional mode — side-by-side diff view, pick-per-note or bulk accept-local/accept-remote
