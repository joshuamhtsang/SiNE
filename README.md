# SiNE - Sionna-based Network Emulation

Wireless network emulation using Sionna ray tracing and Containerlab.

## Overview

SiNE creates realistic wireless network emulations by combining:
- **Containerlab**: Deploy Docker containers as network nodes
- **Sionna v1.2.1**: Ray tracing for accurate wireless channel modeling
- **Linux netem**: Apply computed channel conditions (delay, loss, bandwidth)

## Features

- Define wireless networks in YAML format
- Ray-traced channel computation using Sionna v1.2.1
- Automatic netem configuration based on channel conditions
- Support for various modulation schemes (BPSK, QPSK, 16/64/256-QAM)
- Forward error correction (LDPC, Polar, Turbo)
- Configurable indoor scenes with Mitsuba XML (ITU material naming)
- Mobility support with 100ms update polling
- Deployment summary showing containers, interfaces, and netem parameters

## Installation

### 1. System Dependencies

Run the configure script to install system-level dependencies:

```bash
# Basic setup (installs Containerlab)
./configure.sh

# With GPU support (also installs NVIDIA CUDA Toolkit)
./configure.sh --cuda
```

### 2. Python Dependencies

```bash
# Using UV (recommended) - creates venv and installs dependencies including Sionna v1.2.1
uv sync

# Development dependencies
uv sync --extra dev
```

**Note**: Requires Python 3.12+ for Sionna v1.2.1 compatibility.

## Quick Start

1. **Build the node image** (includes iperf3, tcpdump, etc.):
   ```bash
   docker build -t sine-node:latest docker/node/
   ```

2. **Start the channel server**:
   ```bash
   uv run sine channel-server
   ```

3. **Deploy an emulation** (in a separate terminal):
   ```bash
   uv run sine deploy examples/two_room_wifi/network.yaml
   ```

4. **Test connectivity** (in separate terminals):
   ```bash
   # Server
   docker exec -it clab-two-room-wifi-server iperf3 -s

   # Client
   docker exec -it clab-two-room-wifi-client iperf3 -c <server-ip>
   ```

5. **Cleanup**:
   ```bash
   uv run sine destroy examples/two_room_wifi/network.yaml
   ```

## Example Topology

```yaml
name: two-room-wifi

topology:
  scene:
    file: scenes/two_room_default.xml  # Mitsuba XML scene file

  nodes:
    server:
      kind: linux
      image: sine-node:latest
      wireless:
        rf_power_dbm: 23.0
        frequency_ghz: 5.18
        bandwidth_mhz: 80
        modulation: 64qam
        fec_type: ldpc
        position:
          x: 2.5
          y: 2.0
          z: 1.5

    client:
      kind: linux
      image: sine-node:latest
      wireless:
        rf_power_dbm: 18.0
        frequency_ghz: 5.18
        bandwidth_mhz: 80
        modulation: 64qam
        fec_type: ldpc
        position:
          x: 7.5
          y: 2.0
          z: 1.0

  wireless_links:
    - endpoints: [server, client]
```

## Examples

Two example topologies are provided:

- **`examples/two_room_wifi/`** - Good link quality: nodes aligned with doorway (~5m separation, line-of-sight)
- **`examples/two_room_wifi_poor/`** - Poor link quality: uses larger rooms (10m x 8m each), nodes in opposite corners (~22m separation, no line-of-sight)

## Requirements

- Python 3.12+
- Docker
- Containerlab (installed via `./configure.sh`)
- Sionna v1.2.1 (installed automatically via `uv sync`)
- For GPU acceleration: NVIDIA GPU with CUDA support (use `./configure.sh --cuda`)
- sudo access (required for netem to access container network namespaces)

## CLI Tool

This project provides the `sine` command-line tool. It's defined as a Python entry point in `pyproject.toml`:

```toml
[project.scripts]
sine = "sine.cli:main"
```

When you run `uv sync`, the installer creates `.venv/bin/sine` - a wrapper that imports and runs the `main()` function from [src/sine/cli.py](src/sine/cli.py). The CLI is built using [Click](https://click.palletsprojects.com/).

### Available Commands

```bash
uv run sine deploy <topology.yaml>   # Deploy emulation
uv run sine destroy <topology.yaml>  # Destroy emulation
uv run sine status                   # Show running containers
uv run sine channel-server           # Start channel computation server
uv run sine validate <topology.yaml> # Validate topology file
uv run sine render <topology.yaml> -o scene.png  # Render scene to image
uv run sine info                     # Show system information
```

### Render Command

Render scenes with nodes and propagation paths using Sionna's ray-traced rendering:

```bash
# Basic render
uv run sine render examples/two_room_wifi/network.yaml -o scene.png

# High resolution with custom camera
uv run sine render examples/two_room_wifi/network.yaml -o scene.png \
    --resolution 1920x1080 --camera-position 5,-3,6 --look-at 5,2,1

# Cut away ceiling to see interior
uv run sine render examples/two_room_wifi/network.yaml -o scene.png \
    --clip-at 2.0 --camera-position 5,2,10 --look-at 5,2,1
```

Options: `--resolution WxH`, `--num-samples N`, `--camera-position X,Y,Z`, `--look-at X,Y,Z`, `--fov degrees`, `--clip-at Z`, `--no-paths`, `--no-devices`

### Interactive Scene Viewer

For interactive 3D scene exploration, use the Jupyter notebook in `scenes/viewer.ipynb`:

```bash
# Run with Jupyter (install temporarily)
uv run --with jupyter jupyter notebook scenes/viewer.ipynb
```

The viewer notebook provides:
- **Object listing**: Shows all scene surfaces with their IDs, positions, and sizes
- **Axis markers**: Visual origin and axis indicators using TX/RX devices
- **Path visualization**: Add devices and view propagation paths
- **Clipping**: Cut away ceiling/walls to see interior

Controls: Mouse left (rotate), scroll (zoom), mouse right (pan), Alt+click (pick coordinates)

**Note**: Use `load_scene(file, merge_shapes=False)` to keep individual surfaces separate for inspection. The default `merge_shapes=True` combines surfaces with the same material for better performance.

## Architecture

```
+-------------------+     +------------------------+     +------------------+
|   network.yaml    | --> |  Emulation Controller  | --> |   Containerlab   |
| (Topology + RF)   |     |   (Orchestrator)       |     |  (Docker nodes)  |
+-------------------+     +------------------------+     +------------------+
                                    |                            |
                                    v                            v
                          +------------------------+     +------------------+
                          | Channel Computation    |     |   Linux netem    |
                          | Server (FastAPI)       | --> | (tc/qdisc)       |
                          +------------------------+     +------------------+
                                    |
                                    v
                          +------------------------+
                          |    Sionna RT Engine    |
                          | (Ray tracing + BER)    |
                          +------------------------+
```

## Channel Server API

The channel server exposes a REST API for channel computation:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check with GPU status |
| `/scene/load` | POST | Load ray tracing scene |
| `/compute/single` | POST | Compute channel for single link |
| `/compute/batch` | POST | Compute channels for multiple links |
| `/debug/paths` | POST | Get detailed path info for debugging |

### Debug Endpoint: `/debug/paths`

Get detailed ray tracing path information for debugging, including interaction types (reflection, refraction) and vertices (bounce points).

```bash
# 1. Load scene first
curl -X POST http://localhost:8000/scene/load \
  -H "Content-Type: application/json" \
  -d '{"scene_file": "scenes/two_room_large.xml", "frequency_hz": 5.18e9}'

# 2. Get path details
curl -X POST http://localhost:8000/debug/paths \
  -H "Content-Type: application/json" \
  -d '{
    "tx_position": {"x": 1.0, "y": 0.5, "z": 1.5},
    "rx_position": {"x": 19.0, "y": 7.5, "z": 1.0}
  }'
```

Response includes:
- `distance_m`: Direct line distance between TX and RX
- `num_paths`: Number of valid propagation paths found
- `paths`: List of paths with delay, power, interaction types, and vertices
- `strongest_path`: Path with highest received power
- `shortest_path`: Path with lowest delay (fastest arrival)

## Deployment Output

After successful deployment, SiNE displays a summary:

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                          Deployed Containers                              ┃
┣━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┫
┃ Container          ┃ Image         ┃ PID    ┃ Interfaces  ┃ Position      ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━┩
│ clab-...-server    │ alpine:latest │ 12345  │ eth1        │ (2.5, 2.0, 1.5)│
│ clab-...-client    │ alpine:latest │ 12346  │ eth1        │ (7.5, 2.0, 1.0)│
└────────────────────┴───────────────┴────────┴─────────────┴───────────────┘

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                    Wireless Link Parameters (netem)                       ┃
┣━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━┫
┃ Link                  ┃ Delay     ┃ Jitter    ┃ Loss %   ┃ Rate           ┃
┡━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│ server <-> client     │ 0.50 ms   │ 0.10 ms   │ 0.01%    │ 150.0 Mbps     │
└───────────────────────┴───────────┴───────────┴──────────┴────────────────┘
```

## License

Apache License 2.0
