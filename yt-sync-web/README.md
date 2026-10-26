# yt-sync-web

Folder-scoped web dashboard and REST endpoints for `yt-sync` built with FastAPI, Jinja2, and HTMX 2.

---

## Features

- **Folder-Scoped Startup**: Target directory is passed directly on the command line; local state (`.yt_sync_state.json`) is loaded on startup with zero network calls.
- **Manual Polling (Anti-Quota Burn)**: Remote scans are performed only when the user explicitly clicks "Check for Updates" via HTMX 2 (`hx-post="/refresh"`).
- **Interactive Dashboard**: Real-time status counters (Total, Downloaded, New, Unavailable) and detailed tracklist with status badges.
- **Unavailable Tracks Recovery**: Shows the original archived title for deleted or private tracks with options to mark them as skipped or keep local copies.
- **Background Downloads**: Downloads are executed in worker thread pools (`asyncio.to_thread`) to ensure the FastAPI event loop stays responsive.

---

## Usage

Start the web server targeting a specific folder:

```bash
uv run --package yt-sync-web python -m yt_sync_web /chemin/vers/musiques

# Optional custom host and port:
uv run --package yt-sync-web python -m yt_sync_web /chemin/vers/musiques --host 127.0.0.1 --port 8000
```

Navigate to `http://127.0.0.1:8000` in your web browser.

### (Optional) Development reload mode with Uvicorn:

```bash
uv run --package yt-sync-web uvicorn yt_sync_web.__main__:app --reload
```

---

## Testing

```bash
uv run pytest yt-sync-web/tests/ -v
```
