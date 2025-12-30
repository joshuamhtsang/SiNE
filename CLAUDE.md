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
- `scenes/` - Mitsuba XML scene files (ITU material naming required: `itu_*`) and `viewer.ipynb` for interactive viewing
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
# NOTE: Requires sudo for netem (network emulation) configuration
# Use full path to avoid "uv: command not found" error with sudo
sudo $(which uv) run sine deploy examples/two_room_wifi/network.yaml

# Validate topology
uv run sine validate examples/two_room_wifi/network.yaml

# Render scene to image (does NOT require channel server)
uv run sine render examples/two_room_wifi/network.yaml -o scene.png

# Render with options: custom camera, clip ceiling, high resolution
uv run sine render examples/two_room_wifi/network.yaml -o scene.png \
    --camera-position 5,2,10 --look-at 5,2,1 --clip-at 2.0 --resolution 1920x1080

# Check system info
uv run sine info

# Show running containers
uv run sine status

# Destroy emulation
uv run sine destroy examples/two_room_wifi/network.yaml

# Interactive scene viewer (Jupyter notebook)
uv run --with jupyter jupyter notebook scenes/viewer.ipynb
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

Three example topologies are provided in `examples/`:

| Example | Description | Scene | Node Positions |
|---------|-------------|-------|----------------|
| `vacuum_20m/` | Baseline free-space | `vacuum.xml` (empty) | 20m apart, linear (0,0,1) to (20,0,1) |
| `two_room_wifi/` | Good link quality | `two_room_default.xml` (5m x 4m rooms) | Aligned with doorway (~5m, LOS) |
| `two_room_wifi_poor/` | Poor link quality | `two_room_large.xml` (10m x 8m rooms) | Opposite corners (~22m, NLOS) |

The examples demonstrate the effect of distance and propagation conditions on link quality.

## Channel Server API

The channel server (`uv run sine channel-server`) exposes REST endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check with GPU status |
| `/scene/load` | POST | Load ray tracing scene |
| `/compute/single` | POST | Compute channel for single link |
| `/compute/batch` | POST | Compute channels for multiple links |
| `/debug/paths` | POST | Get detailed path info for debugging |

### Debug Endpoint: `POST /debug/paths`

Returns detailed ray tracing path information including:
- `distance_m`: Direct line distance between TX and RX
- `num_paths`: Number of valid propagation paths
- `paths[]`: Each path includes:
  - `delay_ns`: Propagation delay
  - `power_db`: Received power
  - `interaction_types`: `["specular_reflection", "diffuse_reflection", "refraction"]`
  - `vertices`: 3D coordinates of bounce points `[[x, y, z], ...]`
  - `is_los`: True if line-of-sight (no interactions)
- `strongest_path`: Path with highest power
- `shortest_path`: Path with lowest delay

## Important Notes

- **Scene Configuration**: Always specify `scene.file` in network.yaml (e.g., `file: scenes/two_room_default.xml`)
- **Sionna Scene Materials**: Must use ITU naming convention (e.g., `itu_concrete`, not `concrete`)
- **netem Configuration**: Requires `sudo` for `nsenter` to access container network namespaces
- **Sionna v1.2.1 API**: Use `Scene()` for empty scenes, `load_scene()` for files
- **Antenna Patterns**: Valid pattern names are `"iso"`, `"dipole"`, `"hw_dipole"`, `"tr38901"` (not `"isotropic"`)
- **Antenna Polarization**: Valid polarization values are `"V"`, `"H"`, `"VH"`, `"cross"`
- **Scene Loading**: Use `load_scene(file, merge_shapes=False)` to keep individual surfaces separate for inspection; default merges same-material surfaces for performance
- **Render Command**: Does NOT require channel server - uses local SionnaEngine directly

## Scene Visualization

### Interactive Viewer (`scenes/viewer.ipynb`)

The Jupyter notebook provides:
- Lists all scene objects with IDs, center positions, bounding boxes, and materials
- Adds axis markers (TX at origin, RX at 1m along each axis) for orientation
- Supports clipping planes to see interior (`scene.preview(clip_at=2.0)`)
- Alt+click in preview to get coordinates of any point

### Render Command (`sine render`)

Static rendering to image file:
```bash
uv run sine render <topology.yaml> -o output.png [options]
```

Options: `--camera-position X,Y,Z`, `--look-at X,Y,Z`, `--clip-at Z`, `--resolution WxH`, `--num-samples N`, `--fov degrees`, `--no-paths`, `--no-devices`

### Creating Scene Files

Mitsuba XML scenes can be created with:

1. **Scene Generator Script** (`scenes/generate_room.py`) - Generate two-room layouts:
   ```bash
   # Default 5x4x2.5m rooms
   uv run python scenes/generate_room.py -o scenes/my_scene.xml

   # Custom sizes
   uv run python scenes/generate_room.py -o scenes/large.xml \
       --room1-size 10,8,3 --room2-size 10,8,3 --door-width 1.5

   # See all options
   uv run python scenes/generate_room.py --help
   ```

2. **Blender + Mitsuba add-on** - Model interactively, export to XML

3. **Hand-edit XML** - For simple modifications or custom geometries

Key requirement: Material names must use `itu_` prefix (e.g., `itu_concrete`, `itu_glass`)
