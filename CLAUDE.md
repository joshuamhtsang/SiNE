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
  - `topology/` - Containerlab and netem management (requires sudo for nsenter)
  - `scene/` - Scene loading and configuration
  - `emulation/` - Main orchestrator, cleanup, and deployment summary
- `scenes/` - Mitsuba XML scene files (ITU material naming required: `itu_*`)
- `examples/` - Example network topologies
- `docker/` - Dockerfile definitions
- `tests/` - Test suite

## Key Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Package Manager | UV | Modern, fast Python package manager |
| Python Version | 3.12+ | Required for Sionna v1.2.1 compatibility |
| API Framework | FastAPI | Async support, OpenAPI docs |
| Mobility Poll | 100ms | Balance responsiveness vs overhead |
| Rate Limiting | tbf | netem lacks native rate control |
| Sionna API | PathSolver, Scene | Sionna v1.2.1 API (use `Scene()` for empty) |
| PER Formula | BLER for coded | Industry standard |
| Scene Config | Explicit file path | Always require `scene.file` in network.yaml (no "default" option) |
| netem Access | sudo nsenter | Required for container network namespace access |

## Claude and AI Resources

- `CLAUDE_RESOURCES/` - Reference documentation for Containerlab and Sionna

## MCP Server Setup (Optional)

For enhanced documentation access in Claude Code, configure MCP servers in `.mcp.json`:

1. Copy `.mcp.json.example` to `.mcp.json`
2. Edit `.mcp.json` with your paths

```bash
cp .mcp.json.example .mcp.json
# Edit .mcp.json with your paths
```

Note: `.mcp.json` is gitignored since it contains user-specific paths.

### Available MCP Servers

| Server | Purpose |
|--------|---------|
| **sionna-docs** | Sionna RT documentation (local). Source: https://codeberg.org/supermonkey/sionna_mcp_server |
| **context7** | Up-to-date documentation for any library (Pydantic, FastAPI, etc.) |

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
# Create virtual environment and install dependencies (including Sionna v1.2.1)
uv sync

# Start channel server
uv run sine channel-server

# Deploy emulation (prints deployment summary with containers, interfaces, netem params)
uv run sine deploy examples/two_room_wifi/network.yaml

# Validate topology
uv run sine validate examples/two_room_wifi/network.yaml

# Check system info
uv run sine info

# Show running containers
uv run sine status

# Destroy emulation
uv run sine destroy examples/two_room_wifi/network.yaml
```

## Deployment Output

When deploying, SiNE displays a summary showing:
- **Deployed Containers**: Name, image, PID, interfaces, position (x,y,z)
- **Wireless Link Parameters**: Link endpoints, delay (ms), jitter (ms), loss %, rate (Mbps)

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

## Examples

Two example topologies are provided in `examples/`:

| Example | Description | Node Positions |
|---------|-------------|----------------|
| `two_room_wifi/` | Good link quality | Aligned with doorway (~5m, LOS) |
| `two_room_wifi_poor/` | Poor link quality | Opposite corners (~11m, NLOS) |

Both use the same scene file (`scenes/two_room_default.xml`) but with different node positions to demonstrate the effect of propagation conditions on link quality.

## Important Notes

- **Scene Configuration**: Always specify `scene.file` in network.yaml (e.g., `file: scenes/two_room_default.xml`)
- **Sionna Scene Materials**: Must use ITU naming convention (e.g., `itu_concrete`, not `concrete`)
- **netem Configuration**: Requires `sudo` for `nsenter` to access container network namespaces
- **Sionna v1.2.1 API**: Use `Scene()` for empty scenes, `load_scene()` for files
- **Antenna Patterns**: Valid pattern names are `"iso"`, `"dipole"`, `"hw_dipole"`, `"tr38901"` (not `"isotropic"`)
- **Antenna Polarization**: Valid polarization values are `"V"`, `"H"`, `"VH"`, `"cross"`
