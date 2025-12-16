# SiNE - Sionna-based Network Emulation

## Project Overview

SiNE is a wireless network emulation package that combines:
- **Containerlab**: Container-based network topology management
- **Sionna V1.2**: Ray tracing and wireless channel simulation
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
| Sionna API | PathSolver | New Sionna 1.2+ API |
| PER Formula | BLER for coded | Industry standard |
| Default Scene | Mitsuba XML | Sionna requires mesh files |

## Claude and AI Resources

- `CLAUDE_RESOURCES/` - Reference documentation for Containerlab and Sionna

## Commands

```bash
# Install
uv pip install -e .

# Start channel server
sine channel-server

# Deploy emulation
sine deploy examples/two_room_wifi/network.yaml

# Validate topology
sine validate examples/two_room_wifi/network.yaml

# Check system info
sine info

# Destroy emulation
sine destroy examples/two_room_wifi/network.yaml
```

## Development

```bash
# Install with dev dependencies
uv pip install -e ".[dev]"

# Run tests
pytest

# Type checking
mypy src/sine

# Linting
ruff check src/sine
```
