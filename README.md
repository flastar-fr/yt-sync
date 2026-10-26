# yt-sync

A modular, multi-package Python workspace powered by [uv](https://docs.astral.sh/uv/) for robust YouTube playlist synchronization into local audio directories.

---

## About This Project (100% Vibe Coded Experiment)

This project is an experiment: building a complete, production-ready software solution answering a personal need through **100% vibe coding**, without performing manual code reviews on the generated code.

The goal was to test how far modern agentic workflows can go when guided strictly through engineering constraints and test suites rather than direct code intervention.

You can consider everything (this README included) vibe coded.

### Development Workflow & Methodology
1. **Architectural Scaffolding & Prompt Engineering (Gemini Web UI):**
   - High-level design and phased prompt generation were drafted iteratively in the Gemini web interface.
   - Enforced modern software engineering standards from prompt #1: strict **SOLID** principles, **DRY**, Python 3.12+ type hints, and **Test-Driven Development (TDD)** using the **AAA (Arrange-Act-Assert)** pattern without complex logic in tests.
   - Decoupled business logic into an isolated core package, keeping CLI and web layers strictly dependent on domain outputs.
2. **Autonomous Execution (Antigravity CLI):**
   - Implemented via **Antigravity CLI** in an incremental, atomic-commit workflow.
   - Model allocation strategy:
     - **Flash 3.8 (Low/Medium/High thinking)** for structural scaffolding, setup, and iterative logic.
     - **Sonnet 4.6** for multi-package coordination, test-driven implementations, and FastAPI/HTMX 2 component wiring.
   - Quality gates were validated exclusively through test execution (`uv run pytest` passing 105+ tests with 0 warnings).

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

## Features & Roadmap

### Implemented Features
- [x] **Flat Layout Workspace**: Independent packages orchestrated seamlessly via `uv workspaces`.
- [x] **Differential Analysis (`DiffEngine`)**: Computes exact diffs between remote playlists and local states without redownloading existing tracks.
- [x] **Unavailable Tracks Recovery**: Tracks that became private or deleted on YouTube are flagged while retaining their last known original title.
- [x] **Atomic State Persistence**: Local state is tracked in `.yt_sync_state.json` via atomic writes (`os.replace`) to avoid corruption.
- [x] **Multiple Interfaces**: Fast terminal CLI with progress reporting and interactive web dashboard using HTMX 2 with manual polling.
- [x] **Comprehensive Test Suite**: 100% unit-tested core logic adhering to the AAA pattern (105+ tests, 0 warnings).

### Roadmap (Planned Features)
- [ ] **Audio Loudness Normalization (Equalizer / Volume Leveler)**: Normalize audio levels across downloaded tracks (e.g., EBU R128 / ReplayGain post-processing) so all songs play at a consistent perceived volume.
- [ ] **Configurable Audio Trimming (Intro & Outro Cut)**: Download tracks starting from *n* seconds/minutes or trim long silent/talking intros and outros.

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
uv run --package yt-sync-cli python -m yt_sync_cli /path/to/music_dir

# Run initial synchronization with folder and YouTube playlist URL:
uv run --package yt-sync-cli python -m yt_sync_cli /path/to/music_dir "https://www.youtube.com/playlist?list=PL..."

# Run differential analysis only (dry-run mode without downloading):
uv run --package yt-sync-cli python -m yt_sync_cli /path/to/music_dir "https://www.youtube.com/playlist?list=PL..." --dry-run
```

---

### 2. Web Application (FastAPI / HTMX 2)

#### Run scoped to a target directory:

```bash
uv run --package yt-sync-web python -m yt_sync_web /path/to/music_dir
```

Custom host and port can also be specified:

```bash
uv run --package yt-sync-web python -m yt_sync_web /path/to/music_dir --host 127.0.0.1 --port 8000
```

Once started, navigate to **`[http://127.0.0.1:8000](http://127.0.0.1:8000)`** in your web browser.

#### (Optional) Run with Uvicorn development reload mode:

```bash
uv run --package yt-sync-web uvicorn yt_sync_web.__main__:app --reload
```