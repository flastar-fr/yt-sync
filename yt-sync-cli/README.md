# yt-sync-cli

Command-line interface for `yt-sync`.

---

## Usage

```bash
# Display options
uv run --package yt-sync-cli python -m yt_sync_cli --help

# Run targeting a destination folder (interactive or with configured state)
uv run --package yt-sync-cli python -m yt_sync_cli /chemin/vers/musiques

# Run with target folder and YouTube playlist URL
uv run --package yt-sync-cli python -m yt_sync_cli /chemin/vers/musiques "https://www.youtube.com/playlist?list=PL..."

# Differential check without downloading (dry-run)
uv run --package yt-sync-cli python -m yt_sync_cli /chemin/vers/musiques "https://www.youtube.com/playlist?list=PL..." --dry-run
```

---

## Testing

```bash
uv run pytest yt-sync-cli/tests/ -v
```
