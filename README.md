# KeepSyncNotes

![License](https://img.shields.io/badge/license-MIT-blue)
![Language](https://img.shields.io/badge/language-Python-3776AB)
![Type](https://img.shields.io/badge/type-Desktop%20App-brightgreen)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)

A Google Keep importer and note management desktop app. Import your entire Google Keep library from a Takeout export, then browse, search, tag, and manage your notes locally — with a dark-themed PyQt6 interface and no cloud dependency.

## Quick Start

```bash
python keepsync_notes.py
```

Dependencies auto-install on first run. No manual `pip install` needed.

## Features

- **Google Keep Import** — Import notes from a Google Takeout `.zip` or extracted JSON folder
- **Full-Text Search** — Instant search across all note titles and content
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

- Python 3.8+
- Windows / macOS / Linux

## License

MIT License
