# yt-sync-cli

Command-line interface for `yt-sync`.

---

## Usage

```bash
# Display options
uv run --package yt-sync-cli python -m yt_sync_cli.main --help

# Differential check without downloading
uv run --package yt-sync-cli python -m yt_sync_cli.main /path/to/folder "https://www.youtube.com/playlist?list=PL..." --dry-run

# Run synchronization
uv run --package yt-sync-cli python -m yt_sync_cli.main /path/to/folder "https://www.youtube.com/playlist?list=PL..."
```

---

## Testing

```bash
uv run pytest yt-sync-cli/tests/ -v
```
