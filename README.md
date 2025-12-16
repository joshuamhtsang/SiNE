# SiNE - Sionna-based Network Emulation

Wireless network emulation using Sionna ray tracing and Containerlab.

## Overview

SiNE creates realistic wireless network emulations by combining:
- **Containerlab**: Deploy Docker containers as network nodes
- **Sionna v1.2.1**: Ray tracing for accurate wireless channel modeling
- **Linux netem**: Apply computed channel conditions (delay, loss, bandwidth)

## Features

- Define wireless networks in YAML format
- Ray-traced channel computation using Sionna
- Automatic netem configuration based on channel conditions
- Support for various modulation schemes (BPSK, QPSK, 16/64/256-QAM)
- Forward error correction (LDPC, Polar, Turbo)
- Configurable indoor scenes with Mitsuba XML
- Mobility support with 100ms update polling

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
# Using UV (recommended) - creates venv and installs dependencies including Sionna v1.2
uv sync

# Development dependencies
uv sync --extra dev
```

## Quick Start

1. **Start the channel server**:
   ```bash
   uv run sine channel-server
   ```

2. **Deploy an emulation**:
   ```bash
   uv run sine deploy examples/two_room_wifi/network.yaml
   ```

3. **Test connectivity** (in separate terminals):
   ```bash
   # Server
   docker exec -it clab-two-room-wifi-server iperf3 -s

   # Client
   docker exec -it clab-two-room-wifi-client iperf3 -c <server-ip>
   ```

4. **Cleanup**:
   ```bash
   ./cleanup.sh
   # or
   uv run sine destroy examples/two_room_wifi/network.yaml
   ```

## Example Topology

```yaml
name: two-room-wifi

topology:
  scene:
    type: default  # Two rooms with doorway

  nodes:
    server:
      kind: linux
      image: alpine:latest
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
      image: alpine:latest
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

## Requirements

- Python 3.12+
- Docker
- Containerlab
- Sionna v1.2.1 (installed automatically via `uv sync`)
- For GPU acceleration: NVIDIA GPU with CUDA support

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
uv run sine info                     # Show system information
```

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

## License

Apache License 2.0
