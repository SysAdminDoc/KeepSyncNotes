# Product capture notes

The marketing screenshots come from the real CustomTkinter application on Windows at DPI-aware scale. The capture helper creates a named private desktop, points the app at a temporary data directory, seeds four sample notes, turns off background sync and tray startup, then captures the rendered windows without touching the active display.

Every sample note carries the visible `Sample workspace` label. The final README uses the library and editor view plus the Data settings view. Earlier blank offscreen attempts are retained as rejected capture evidence.

Run the same capture again with:

```powershell
.\.venv\Scripts\python tools\capture_marketing.py --output-dir assets\concepts\2026-09-13-marketing\captures\final-source
```
