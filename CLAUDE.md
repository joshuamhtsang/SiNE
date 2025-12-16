# SiNE - Sionna-based Network Emulation

## Project Overview

SiNE is a wireless network emulation package that combines:
- **Containerlab**: Container-based network topology management
- **Sionna v1.2.1**: Ray tracing and wireless channel simulation (Python 3.12+)
- **Linux netem**: Network emulation (delay, loss, bandwidth)

## Architecture

```
network.yaml -> EmulationController -> Containerlab (Docker containers)
                      |
                      v
              Channel Server (FastAPI) -> netem (tc/qdisc)
                      |
                      v
              Sionna RT (Ray tracing + BER/BLER/PER)
```

## Key Directories

- `src/sine/` - Main package source code
  - `config/` - Topology schema and YAML loader
  - `channel/` - Channel computation (SNR, BER, BLER, PER, FastAPI server)
  - `topology/` - Containerlab and netem management
  - `scene/` - Scene loading and configuration
  - `emulation/` - Main orchestrator and cleanup
- `scenes/` - Mitsuba XML scene files
- `examples/` - Example network topologies
- `docker/` - Dockerfile definitions
- `tests/` - Test suite

## Key Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Package Manager | UV | Modern, fast Python package manager |
| API Framework | FastAPI | Async support, OpenAPI docs |
| Mobility Poll | 100ms | Balance responsiveness vs overhead |
| Rate Limiting | tbf | netem lacks native rate control |
| Sionna API | PathSolver | Sionna v1.2.1 API |
| PER Formula | BLER for coded | Industry standard |
| Default Scene | Mitsuba XML | Sionna requires mesh files |

## Claude and AI Resources

- `CLAUDE_RESOURCES/` - Reference documentation for Containerlab and Sionna

## CLI Tool

This project provides the `sine` CLI tool, defined in `pyproject.toml`:

```toml
[project.scripts]
sine = "sine.cli:main"
```

When you run `uv sync`, it creates `.venv/bin/sine` which calls the `main()` function in `src/sine/cli.py`. The CLI is built with [Click](https://click.palletsprojects.com/).

## Setup

```bash
# Install system dependencies (containerlab, optionally CUDA)
./configure.sh          # Basic setup
./configure.sh --cuda   # With NVIDIA CUDA toolkit for GPU acceleration
```

## Commands

```bash
# Create virtual environment and install dependencies (including Sionna v1.2)
uv sync

# Start channel server
uv run sine channel-server

# Deploy emulation
uv run sine deploy examples/two_room_wifi/network.yaml

# Validate topology
uv run sine validate examples/two_room_wifi/network.yaml

# Check system info
uv run sine info

# Destroy emulation
uv run sine destroy examples/two_room_wifi/network.yaml
```

## Development

```bash
# Install with dev dependencies
uv sync --extra dev

# Run tests
uv run pytest

# Type checking
uv run mypy src/sine

# Linting
uv run ruff check src/sine
```
