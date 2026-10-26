# yt-sync

A modular, multi-package Python workspace powered by [uv](https://docs.astral.sh/uv/) for robust YouTube playlist synchronization into local audio directories.

---

## Workspace Structure

The project adopts a flat layout (no `src/` folder), divided into three complementary packages:

```text
yt_sync/
├── pyproject.toml              # Workspace root & global pytest configuration
├── uv.lock                     # Universal lockfile
├── yt-sync-core/               # Domain models, yt-dlp wrapper, DiffEngine, and state storage
├── yt-sync-cli/                # Command-line interface with interactive progress
└── yt-sync-web/                # Modern web UI powered by FastAPI and HTMX 2
```

---

## Features

- **Differential Analysis (`DiffEngine`)**: Computes exact diffs between remote playlists and local states without redownloading existing tracks.
- **Unavailable Tracks Recovery**: Tracks that became private or deleted on YouTube are flagged while retaining their last known original title.
- **Atomic State Persistence**: Local state is tracked in `.yt_sync_state.json` via atomic writes (`os.replace`) to avoid corruption.
- **Multiple Interfaces**: Choose between a fast terminal CLI with progress reporting or an interactive web dashboard using HTMX 2.

---

## Installation & Setup

Ensure `uv` is installed on your system.

```bash
# Clone the repository
git clone <repo-url>
cd yt_sync

# Synchronize all packages in the workspace
uv sync --all-packages
```

---

## Testing

Run the full unit and integration test suite across all workspace packages:

```bash
uv run pytest
```

Run tests for a specific package:

```bash
uv run pytest yt-sync-core/tests/
uv run pytest yt-sync-cli/tests/
uv run pytest yt-sync-web/tests/
```

---

## Command Guide & Execution

### 1. Command-Line Interface (CLI)

Run the CLI directly using `uv` with the package module:

```bash
# Display help and usage options
uv run --package yt-sync-cli python -m yt_sync_cli --help

# Run the CLI targeting a destination folder (interactive or with configured state):
uv run --package yt-sync-cli python -m yt_sync_cli /chemin/vers/musiques

# Run initial synchronization with folder and YouTube playlist URL:
uv run --package yt-sync-cli python -m yt_sync_cli /chemin/vers/musiques "https://www.youtube.com/playlist?list=PL..."

# Run differential analysis only (dry-run mode without downloading):
uv run --package yt-sync-cli python -m yt_sync_cli /chemin/vers/musiques "https://www.youtube.com/playlist?list=PL..." --dry-run
```

---

### 2. Web Application (FastAPI / HTMX 2)

#### Run scoped to a target directory:

```bash
uv run --package yt-sync-web python -m yt_sync_web /chemin/vers/musiques
```

Custom host and port can also be specified:

```bash
uv run --package yt-sync-web python -m yt_sync_web /chemin/vers/musiques --host 127.0.0.1 --port 8000
```

Once started, navigate to **`http://127.0.0.1:8000`** in your web browser.

#### (Optional) Run with Uvicorn development reload mode:

```bash
uv run --package yt-sync-web uvicorn yt_sync_web.__main__:app --reload
```
