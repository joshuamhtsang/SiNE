# SiNE - Sionna-based Network Emulation

Wireless network emulation using Sionna ray tracing and Containerlab.

## Overview

SiNE creates realistic wireless network emulations by combining:
- **Containerlab**: Deploy Docker containers and veth links between nodes
- **Sionna v1.2.1**: Ray tracing for accurate wireless channel modeling
- **Linux netem**: Apply computed channel conditions (delay, loss, bandwidth) to containerlab links

**How it works**: SiNE converts your `network.yaml` topology to containerlab format, deploys containers via containerlab, then applies wireless channel emulation on top of the containerlab-created network interfaces using netem.

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

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         SiNE Emulation System                       │
└─────────────────────────────────────────────────────────────────────┘

┌──────────────────────┐      ┌──────────────────────┐
│  Channel Server      │      │  EmulationController │
│  (Port 8000)         │      │  (sine deploy)       │
│                      │      │                      │
│  • Sionna RT Engine  │◄─────│  • Load topology     │
│  • Ray Tracing       │ HTTP │  • Deploy containers │
│  • SNR/BER/PER calc  │      │  • Apply netem       │
└──────────────────────┘      │  • Position updates  │
                              └──────────┬───────────┘
                                         │
                                         │ Containerlab
                                         ▼
                    ┌────────────────────────────────────┐
                    │      Docker Containers (Nodes)     │
                    ├────────────────┬───────────────────┤
                    │   node1        │      node2        │
                    │   (0, 0, 1)    │   (20, 0, 1)      │
                    │                │                   │
                    │  ┌──────────┐  │  ┌──────────┐     │
                    │  │   eth1   │◄─┼─►│   eth1   │     │
                    │  └──────────┘  │  └──────────┘     │
                    │      ▲         │        ▲          │
                    │      │ netem   │        │ netem    │
                    │      │ (tc)    │        │ (tc)     │
                    │      │         │        │          │
                    │  • delay       │    • delay        │
                    │  • jitter      │    • jitter       │
                    │  • loss        │    • loss         │
                    │  • rate limit  │    • rate limit   │
                    └────────────────┴───────────────────┘
                           ▲                   ▲
                           │                   │
                           └───────┬───────────┘
                                   │ veth pair
                          (wireless link emulation)

Legend:
  ◄──► : HTTP communication
  ───  : Network links
  netem: Linux network emulation (delay, jitter, loss, rate)
```

### Step-by-Step Setup

1. **Build the node image**: Used to spin up container(s) representing the nodes (includes iperf3, tcpdump, etc.):
   ```bash
   docker build -t sine-node:latest docker/node/
   ```

2. **Start the channel server** Responsible for computing the link characteristics (delay, bandwidth, packet loss % etc.):
   ```bash
   uv run sine channel-server
   ```

3. **Deploy an emulation** (in a separate terminal):
   ```bash
   # Note: Requires sudo for netem (network emulation) configuration
   # Use full path to uv to avoid "command not found" with sudo
   sudo $(which uv) run sine deploy examples/vacuum_20m/network.yaml
   ```

   **Why sudo?** Network emulation requires sudo to use `nsenter` to access container network namespaces and configure traffic control (tc) with netem. Without sudo, containers will be created but links will operate at full bandwidth (~10+ Gbps) without any wireless channel emulation.

   **Alternative**: Configure passwordless sudo (see "Sudo Configuration" section below) to run without `sudo` prefix.

4. **Configure IP addresses** (containers have no IPs by default):

   **Option A: IPv4 (recommended)**
   ```bash
   # Assign IPv4 addresses to the wireless interfaces
   docker exec -it clab-vacuum-20m-node1 ip addr add 192.168.1.1/24 dev eth1
   docker exec -it clab-vacuum-20m-node2 ip addr add 192.168.1.2/24 dev eth1
   ```

   **Option B: Use IPv6 link-local (auto-configured)**
   ```bash
   # Get node1's IPv6 address
   docker exec -it clab-vacuum-20m-node1 ip -6 addr show dev eth1 | grep fe80
   # Example output: inet6 fe80::a8b9:48ff:fe4a:a1f6/64
   ```

   Note: No performance difference between IPv4 and IPv6 - same underlying veth and netem.

5. **Test connectivity** (in separate terminals):
   ```bash
   # IPv4 method
   docker exec -it clab-vacuum-20m-node1 iperf3 -s
   docker exec -it clab-vacuum-20m-node2 iperf3 -c 192.168.1.1

   # OR IPv6 method (use node1's IPv6 address from step 4, with %eth1 suffix)
   docker exec -it clab-vacuum-20m-node1 iperf3 -s
   docker exec -it clab-vacuum-20m-node2 iperf3 -c fe80::a8b9:48ff:fe4a:a1f6%eth1
   ```

6. **Cleanup**:
   ```bash
   uv run sine destroy examples/vacuum_20m/network.yaml
   ```

## Mobility - Moving Nodes During Emulation

SiNE supports real-time node mobility with automatic channel recomputation. As nodes move, link parameters (delay, jitter, loss, rate) are updated based on new positions.

### Mobility Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                  SiNE Emulation with Mobility Control               │
└─────────────────────────────────────────────────────────────────────┘

┌──────────────────────┐      ┌──────────────────────┐
│  Mobility Scripts    │      │  External Tools      │
│                      │      │                      │
│  • linear_movement   │      │  • curl/HTTP clients │
│  • waypoint_movement │      │  • Custom scripts    │
│  • Custom patterns   │      │  • Web UIs           │
└──────────┬───────────┘      └──────────┬───────────┘
           │                             │
           │ HTTP POST                   │ HTTP POST
           │ /api/mobility/update        │ /api/mobility/update
           │ {node, x, y, z}             │ {node, x, y, z}
           ▼                             ▼
    ┌────────────────────────────────────────────────┐
    │         Mobility API Server (Port 8001)        │
    │                                                │
    │  • Position update endpoints                  │
    │  • EmulationController integration            │
    │  • Automatic channel recomputation trigger    │
    └────────────────────┬───────────────────────────┘
                         │
                         │ update_node_position()
                         ▼
    ┌────────────────────────────────────────────────┐
    │           EmulationController                  │
    │                                                │
    │  • Update config positions                    │
    │  • Trigger _update_all_links()                │
    └──────────┬─────────────────────┬───────────────┘
               │                     │
               │ Batch request       │ Apply netem
               │ with new positions  │ with new params
               ▼                     ▼
┌──────────────────────┐      ┌──────────────────────┐
│  Channel Server      │      │  Docker Containers   │
│  (Port 8000)         │      │                      │
│                      │      │  ┌────────────────┐  │
│  • Recompute paths   │      │  │ node1 @ (x,y,z)│  │
│  • New SNR/BER/PER   │      │  │   eth1 ◄─────┐ │  │
│  • Updated delays    │      │  │   (netem)    │ │  │
└──────────────────────┘      │  └──────────────┘ │  │
                              │         veth pair │  │
                              │  ┌──────────────┐ │  │
                              │  │ node2 @ (x,y,z)│  │
                              │  │   eth1 ◄─────┘ │  │
                              │  │   (netem)      │  │
                              │  └────────────────┘  │
                              └──────────────────────┘

Flow:
  1. Mobility script sends position update (100ms intervals)
  2. Mobility API validates and updates internal config
  3. EmulationController recomputes channels with new positions
  4. Channel Server runs Sionna ray tracing with updated geometry
  5. New channel parameters applied to netem (delay, jitter, loss, rate)
  6. Wireless link behavior reflects new distance/geometry (~100ms total)

Legend:
  ───► : HTTP REST API calls
  ═══► : Internal function calls
  netem: Updated automatically as nodes move
```

### Quick Start with Mobility

1. **Start channel server** (Terminal 1):
   ```bash
   uv run sine channel-server
   ```

2. **Start mobility API server** (Terminal 2):
   ```bash
   sudo $(which uv) run sine mobility-server examples/vacuum_20m/network.yaml
   ```

3. **Run mobility script** (Terminal 3):
   ```bash
   # Linear movement example
   uv run python examples/mobility/linear_movement.py

   # OR waypoint-based movement
   uv run python examples/mobility/waypoint_movement.py
   ```

### Mobility Features

- **Linear Movement**: Move nodes from point A to B at constant velocity
- **Waypoint Paths**: Define complex paths with multiple waypoints and velocities
- **REST API**: Control positions via HTTP requests for external integration
- **Real-time Updates**: Channel conditions recomputed every 100ms (configurable)
- **Automatic netem**: Link parameters updated automatically as nodes move

### Example: Manual Position Update

```bash
# Update node2 position via API
curl -X POST http://localhost:8001/api/mobility/update \
     -H "Content-Type: application/json" \
     -d '{"node": "node2", "x": 10.0, "y": 5.0, "z": 1.5}'
```

See [examples/mobility/README.md](examples/mobility/README.md) for detailed mobility documentation.

## Example Topoplogies

Topologies are described in yaml files. Two example topologies are provided:

- **`examples/two_room_wifi/`** - Good link quality: nodes aligned with doorway (~5m separation, line-of-sight)
- **`examples/two_room_wifi_poor/`** - Poor link quality: uses larger rooms (10m x 8m each), nodes in opposite corners (~22m separation, no line-of-sight)

## Requirements

- Python 3.12+
- Docker
- Containerlab (installed via `./configure.sh`)
- Sionna v1.2.1 (installed automatically via `uv sync`)
- For GPU acceleration: NVIDIA GPU with CUDA support (use `./configure.sh --cuda`)
- sudo access (required for netem to access container network namespaces)

### Sudo Configuration (Optional but Recommended)

To avoid entering your password every time you deploy, you can configure passwordless sudo for the specific commands used by netem:

```bash
# Create a sudoers file for SiNE
sudo tee /etc/sudoers.d/sine <<EOF
# Allow netem configuration without password
$USER ALL=(ALL) NOPASSWD: /usr/bin/nsenter
$USER ALL=(ALL) NOPASSWD: /usr/sbin/tc
EOF

# Set proper permissions
sudo chmod 0440 /etc/sudoers.d/sine
```

This allows `sine deploy` to run without `sudo` while still having the necessary privileges for netem configuration.

## The `sine` CLI Tool

This project provides the `sine` command-line tool. It's defined as a Python entry point in `pyproject.toml`:

```toml
[project.scripts]
sine = "sine.cli:main"
```

The build system uses **Hatchling** as the build backend:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/sine"]  # Tells Hatchling where to find the package
```

When you run `uv sync`, the process works like this:
1. **uv** (the frontend) reads `pyproject.toml`
2. **Hatchling** (the backend) builds the package from `src/sine/`
3. The installer creates `.venv/bin/sine` - a wrapper that imports and runs the `main()` function from [src/sine/cli.py](src/sine/cli.py)

The CLI is built using [Click](https://click.palletsprojects.com/).

### Available Commands in `sine`

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
| (Topology + RF)   |     |   (Orchestrator)       |     |  (Docker nodes   |
+-------------------+     +------------------------+     |   + veth links)  |
                                    |                    +------------------+
                                    |                            |
                                    v                            v
                          +------------------------+     +------------------+
                          | Channel Computation    |     |   Linux netem    |
                          | Server (FastAPI)       | --> | (applied to      |
                          +------------------------+     |  veth interfaces)|
                                    |                    +------------------+
                                    v
                          +------------------------+
                          |    Sionna RT Engine    |
                          | (Ray tracing + BER)    |
                          +------------------------+
```

**Containerlab Integration**: SiNE uses containerlab as a required dependency to deploy the actual network topology. The workflow is:

1. **Parse topology**: Read `network.yaml` with wireless parameters (position, RF power, antenna, etc.)
2. **Generate containerlab config**: Strip wireless params, create `.sine_clab_topology.yaml`
3. **Deploy via containerlab**: Run `containerlab deploy` to create Docker containers and veth links
4. **Apply wireless emulation**: Configure netem on the containerlab-created interfaces based on Sionna ray tracing results

Containerlab handles container lifecycle and network plumbing; SiNE adds the wireless channel model on top.

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

## FAQ - Frequently Asked Questions

### How does netem (network emulation) work?

**Q: Is netem configured per-link or per-interface?**

A: Netem is configured **per-interface**, not per-link. SiNE applies netem to the `eth1` interface on each container. Importantly, netem only affects **egress (outbound) traffic** - packets leaving the interface.

**Q: How does SiNE handle bidirectional wireless links?**

A: SiNE applies netem to **both** sides of each wireless link:

```
Node1 → Node2: Packets leave Node1's eth1, experience Node1's netem
Node2 → Node1: Packets leave Node2's eth1, experience Node2's netem
```

```
┌─────────────┐                              ┌─────────────┐
│   Node1     │                              │   Node2     │
│             │                              │             │
│  eth1       │                              │       eth1  │
│  ┌───────┐  │                              │  ┌───────┐  │
│  │ netem │──┼───► outbound traffic ────────┼─►│       │  │
│  │(egress)│ │     affected here            │  │       │  │
│  └───────┘  │                              │  └───────┘  │
│             │                              │             │
│  ┌───────┐  │                              │  ┌───────┐  │
│  │       │◄─┼─────── outbound traffic ◄────┼──│ netem │  │
│  │       │  │         affected here        │  │(egress)│  │
│  └───────┘  │                              │  └───────┘  │
└─────────────┘                              └─────────────┘
```

Both interfaces receive the same parameters (symmetric link). When link conditions change, SiNE updates netem on both nodes.

**Q: What's the effective throughput with netem on both sides?**

A: Each direction is independently limited. For TCP:
- **Throughput**: Limited to the configured rate (e.g., 192 Mbps)
- **Round-trip delay**: Sum of both directions (request + ACK)
- **Packet loss**: Applied independently in each direction

### Why does Containerlab use a Linux bridge?

**Q: How are containers connected?**

A: Containerlab uses a **Linux bridge** rather than direct veth pairs:

```
Containerlab architecture:
┌─────────┐                              ┌─────────┐
│  Node1  │                              │  Node2  │
│  eth1 ══╪══╗                      ╔════╪══ eth1  │
└─────────┘  ║                      ║    └─────────┘
             ║    ┌────────────┐    ║
             ╚════│Linux Bridge│════╝
                  └────────────┘
```

**Q: What are the pros and cons of this architecture?**

**Pros:**
- Easy to add more nodes to the same network segment
- Supports complex topologies (mesh, star, etc.)
- Network namespace isolation between containers
- Can attach tcpdump to bridge for debugging
- Works with standard Linux networking tools

**Cons:**
- Extra hop through bridge (adds ~1-10 microseconds latency)
- Small CPU overhead for bridge processing
- MAC address table overhead (negligible for small topologies)
- Technically a shared medium rather than point-to-point

**Q: Does the bridge affect emulation accuracy?**

A: The bridge adds negligible latency (~1-10 microseconds) compared to wireless delays (0.1-10+ milliseconds). This overhead is insignificant for wireless emulation.

### MANET (Mobile Ad-hoc Network) Support

**Q: Does SiNE support MANET topologies with 3+ nodes?**

A: Yes! SiNE supports MANET using a **point-to-point link model**. Each wireless link is a separate veth pair with independent netem configuration.

Example 3-node triangle topology:
```
         node1 (0,0,1)
          /  \
       eth1  eth2      ← Each node has multiple interfaces
        /      \
     eth1      eth1
      /          \
   node2 -------- node3
 (10,0,1) eth2   (5,8.66,1)
```

**Q: How does SiNE know which interface to configure for each link?**

A: SiNE builds an interface mapping when generating the containerlab topology:
- `(node1, node2) → eth1` (node1 uses eth1 to reach node2)
- `(node1, node3) → eth2` (node1 uses eth2 to reach node3)
- etc.

This mapping is used by `_find_link_interface()` to apply the correct netem parameters to each interface.

**Q: How do I deploy a MANET example?**

```bash
# Deploy 3-node triangle MANET
sudo $(which uv) run sine deploy examples/manet_triangle/network.yaml

# Verify netem on all interfaces
./CLAUDE_RESOURCES/check_netem.sh
```

**Q: What are the limitations of the point-to-point model?**

**Pros:**
- Simple implementation using containerlab links
- Each link has independent channel conditions
- Easy to debug and understand
- Works well for testing MANET routing protocols

**Cons:**
- Not a true broadcast medium (no shared channel contention)
- Hidden node problem not naturally modeled
- Multiple interfaces per node (real MANETs use single interface)

For applications requiring true broadcast semantics, a shared bridge model could be implemented in the future. See [CLAUDE.md](CLAUDE.md) for technical details.

## License

Apache License 2.0
