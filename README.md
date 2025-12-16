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
