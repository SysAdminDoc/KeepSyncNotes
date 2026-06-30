# KeepSyncNotes

![Version](https://img.shields.io/badge/version-1.24.0-blue)
![License](https://img.shields.io/badge/license-MIT-blue)
![Language](https://img.shields.io/badge/language-Python-3776AB)
![Type](https://img.shields.io/badge/type-Desktop%20App-brightgreen)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)

A Google Keep importer and note management desktop app. Import your entire Google Keep library from a Takeout export, then browse, search, tag, and manage your notes locally with a dark-themed CustomTkinter interface and no cloud dependency.

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python keepsync_notes.py
```

Dependencies are pinned in `requirements.txt`; the app never installs packages at runtime.

## Features

- **Google Keep Import** — Import notes from a Google Takeout `.zip` or extracted JSON folder
- **Auto-Import Watcher** — Watch a local folder for new Google Takeout ZIPs or extracted Keep folders
- **Import Conflict Resolution** — Review diffs and keep local, use imported, or merge duplicates during foreground imports
- **Delta-Aware Imports** — Re-import newer exports without duplicating unchanged notes
- **Multi-Source Import** — Import ENEX, Standard Notes ZIP, Obsidian vaults, Bear ZIP, Simplenote exports, and OneNote HTML folders
- **Guarded Bulk Imports** — ZIP and folder imports enforce size/member limits, path traversal checks, extension allowlists, and cancellation
- **Versioned Local Backups** — Automatic DB/attachment snapshots before imports and syncs, plus manual backup restore from the Data tab
- **Diagnostics Panel** — In-app dependency/path/error report backed by a local crash and diagnostics log file
- **Cloud Conflict Planning** — Google Drive and GitHub sync report create/update/delete/conflict counts and preserve remote conflict copies
- **Checklist Notes** — Create nested checklist items, reorder rows, and preserve checked states
- **Keep Colors & Pins** — Preserve Keep note colors, show color swatches in cards, and pin notes to the top
- **Reminders** — Store local date/time reminders, optional location context, and desktop notifications when available
- **Sharing Metadata** — Preserve imported "shared with" collaborator metadata without re-sharing notes
- **Attachments** — Copy imported Keep media locally and show image thumbnails inline
- **OS Keyring Credentials** — Keep, Google Drive, and GitHub sync secrets are stored in the platform credential store with legacy plaintext cleanup
- **Deterministic Dependencies** — Pinned requirements file with no startup or runtime package installation
- **Markdown Preview** — Notes tagged `.md` can switch between editable source and rendered preview
- **Ranked Full-Text Search** — SQLite FTS5 search across titles, bodies, checklist items, and labels
- **Advanced Filters** — Combine label, color, date range, image, checklist, and archive filters with AND/OR logic
- **Saved Searches** — Pin query/filter combinations as reusable virtual folders, including FTS label/checklist hits and archived-note filters
- **Tag & Label System** — Filter notes by the labels synced from Google Keep
- **Note Editor** — Create, edit, and delete notes locally after import
- **Archive & Trash Views** — Mirrors the Google Keep archived and trashed note states
- **Local Storage** — All data stored in a local SQLite database — nothing leaves your machine
- **Dark Theme** — Catppuccin Mocha dark interface throughout

## Usage

### Importing from Google Takeout

1. Go to [Google Takeout](https://takeout.google.com) and export **Keep** data
2. Download the `.zip` archive
3. In KeepSyncNotes, click **Import** and point to the `.zip` or extracted `Takeout/Keep/` folder
4. All notes, labels, and archive states are imported automatically

### Searching Notes

Type in the search bar to filter notes in real time. Searches title and body text.

### Managing Notes

Right-click any note for options: Edit, Archive, Delete, or copy text to clipboard.

## Requirements

- Python 3.10+
- `python -m pip install -r requirements.txt`
- Windows / macOS / Linux

## License

MIT License
