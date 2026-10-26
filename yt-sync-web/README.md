# yt-sync-web

Web dashboard and REST endpoints for `yt-sync` built with FastAPI, Jinja2, and HTMX 2.

---

## Features

- **FastAPI Backend**: Asynchronous endpoints delegating blocking `yt-dlp` operations to background worker threads.
- **HTMX 2 Frontend**: Dynamic partial updates without client-side JavaScript frameworks.
- **Visual Differential Report**: Real-time counters and track breakdowns with suggestions for private or removed tracks.

---

## Development

```bash
# Start development server
uv run --package yt-sync-web uvicorn yt_sync_web.main:app --reload
```

---

## Testing

```bash
uv run pytest yt-sync-web/tests/ -v
```
