# yt-sync-core

Core domain library and engine for the `yt-sync` workspace.

---

## Features

- **Pydantic v2 Models**: Immutable snapshots (`TrackSnapshot`), statuses (`TrackStatus`), and synchronization state (`SyncState`).
- **Atomic State Manager**: Manages read/write operations for the hidden `.yt_sync_state.json` file with atomic replacement.
- **yt-dlp Wrapper (`PlaylistExtractor`)**: Handles flat metadata extraction and targeted downloading.
- **Pure Differential Engine (`DiffEngine`)**: Classifies tracks into four deterministic categories:
  - `already_downloaded`: Present locally and still available on YouTube.
  - `new_tracks`: New or previously failed tracks ready for download.
  - `removed_tracks`: Present locally but removed from the remote playlist.
  - `unavailable_tracks`: Remote tracks marked as private or deleted, maintaining original title from local state.

---

## Development & Testing

Run unit tests for core:

```bash
uv run pytest yt-sync-core/tests/ -v
```
