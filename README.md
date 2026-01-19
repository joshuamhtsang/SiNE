# SiNE - Sionna-based Network Emulation

Wireless network emulation using Sionna ray tracing and Containerlab.

## Overview

SiNE (pronouced "SHEE-na") stands for {Si}onna {N}etwork {E}mulation and it lets you build emulated wireless networks with Docker containers as nodes, allowing you to easily deploy user-space applications on each node of the network. SiNE  achieves this by integrating:
- **Containerlab**: Deploy Docker containers connected by the Linux networking stack, using primitives like veth links and bridges
- **Nvidia Sionna v1.2.1**: Ray tracing for accurate wireless channel modeling in a scene
- **Linux netem**: Apply computed channel conditions (delay, jitter, loss, bandwidth) to the emulated wireless links

**How it works**: SiNE parses a `network.yaml` network description file and uses the metadata to:
- Create a virtual network of connected containers (each representing a node) using Containerlab
- Compute the wireless channel conditions of the links between the nodes with Nvidia Sionna ray tracing capabilities
- Emulate the wireless channel conditions by applying the apprpriate netem parameters to the links:

```python
delay_ms = propagation_delay       # From strongest path computed in Sionna RT
jitter_ms = delay_spread           # RMS delay spread from multipath (Sionna RT)
loss_percent = PER × 100           # From BER/BLER calculation (AWGN formulas)
rate_mbps = modulation_based_rate  # BW × bits_per_symbol × code_rate × efficiency × (1-PER)
```

## Features

- Define wireless networks in YAML format with per-interface configuration
- **Two link types**: Wireless (ray-traced) or Fixed netem (direct parameters)
- **Two MANET modes**: Point-to-point links (default) or Shared bridge (true broadcast medium)
- Ray-traced channel computation using Sionna v1.2.1
- Automatic netem configuration based on channel conditions
- Support for various modulation schemes (BPSK, QPSK, 16/64/256/1024-QAM)
- Forward error correction (LDPC, Polar, Turbo)
- Adaptive MCS selection (WiFi 6 style)
- Configurable indoor scenes with Mitsuba XML (ITU material naming)
- Mobility support with 100ms update polling
- Deployment summary showing containers, interfaces, and netem parameters

### MANET Modeling

SiNE supports two approaches for MANET (Mobile Ad-hoc Network) topologies:

1. **Point-to-Point Links (Default)**: Each wireless link is a separate veth pair with independent netem. Simple and efficient, but not a true broadcast medium.

2. **Shared Bridge (NEW!)**: All MANET nodes connect to a container-namespace bridge with per-destination netem using HTB + flower filters. This provides:
   - ✅ **True broadcast medium** - packets visible to all nodes
   - ✅ **Single interface per node** - realistic MANET architecture
   - ✅ **Per-destination channel conditions** - accurate distance-based emulation
   - ✅ **MANET routing protocol support** - OLSR, BATMAN-adv, Babel, etc.
   - ✅ **Container-managed lifecycle** - automatic creation/cleanup via Containerlab

See [examples/manet_triangle_shared/](examples/manet_triangle_shared/) for a complete shared bridge example and [MANET Support](#manet-mobile-ad-hoc-network-support) section below for detailed comparison.

## Requirements

- Python 3.12+
- Docker
- Containerlab (installed via `./configure.sh`)
- Sionna v1.2.1 (installed automatically via `uv sync`)
- Linux kernel 4.2+ (for tc flower filters in shared bridge mode)
- For GPU acceleration: NVIDIA GPU with CUDA support (use `./configure.sh --cuda`)
- sudo access (required for netem to access container network namespaces)

**Verify prerequisites:**
```bash
docker --version        # Docker must be installed and running
python3 --version       # Must be 3.12 or higher
```

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

This quick start deploys a simple two-node wireless network with 20 meters of free-space separation using the `vacuum_20m` example. You'll run iperf3 to measure throughput over the emulated wireless link.

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         SiNE Emulation System                       │
└─────────────────────────────────────────────────────────────────────┘

┌──────────────────────┐      ┌──────────────────────────────────────┐
│  Channel Server      │      │  EmulationController                 │
│  (sine channel-server)│      │  (sine deploy)                       │
│  (Port 8000)         │      │                                      │
│                      │      │  • Load topology                     │
│  • Sionna RT Engine  │◄─────│  • Deploy containers                 │
│  • Ray Tracing       │ HTTP │  • Query Channel Server to calculate │
│  • SNR/BER/PER calc  │      │    netem parameters                  │
└──────────────────────┘      │  • Apply netem to links              │
                              │  • Position updates                  │
                              └──────────┬───────────────────────────┘
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
                    │  │   eth1   │  │  │   eth1   │     │
                    │  └─────┬────┘  │  └────┬─────┘     │
                    │        │       │       │           │
                    │        │ netem │       │ netem     │
                    │        │ (tc)  │       │ (tc)      │
                    │        │       │       │           │
                    │    • delay     │   • delay         │
                    │    • jitter    │   • jitter        │
                    │    • loss      │   • loss          │
                    │    • rate      │   • rate          │
                    └────────┼───────┴───────┼───────────┘
                             │               │
                             │ veth pair     │ veth pair
                             ▼               ▼
                    ┌────────────────────────────────────┐
                    │        Linux Bridge (br-xxx)       │
                    │  (created by Containerlab)         │
                    └────────────────────────────────────┘
                             ▲
                             │
                    (wireless link emulation)

Legend:
  ◄──► : HTTP communication
  ───  : Network links / veth pairs
  netem: Linux network emulation (delay, jitter, loss, rate)
```

### Step-by-Step Setup

1. **Start the channel server** Responsible for computing the link characteristics (delay, bandwidth, packet loss % etc.):
   ```bash
   uv run sine channel-server
   ```

2. **Deploy an emulation** (in a separate terminal):
   ```bash
   # Note: Requires sudo for netem (network emulation) configuration
   # Use full path to uv to avoid "command not found" with sudo
   sudo $(which uv) run sine deploy examples/vacuum_20m/network.yaml
   ```

   **Why sudo?** Network emulation requires sudo to use `nsenter` to access container network namespaces and configure traffic control (tc) with netem. Without sudo, containers will be created but links will operate at full bandwidth (~10+ Gbps) without any wireless channel emulation.

   **Alternative**: Configure passwordless sudo (see "Sudo Configuration" section below) to run without `sudo` prefix.

3. **Test connectivity** (IP addresses are automatically configured from the topology YAML):
   ```bash
   # iperf3 server on node 1
   docker exec -it clab-vacuum-20m-node1 iperf3 -s
   # iperf3 client on node 2
   docker exec -it clab-vacuum-20m-node2 iperf3 -c 192.168.1.1
   ```

   **Expected output** (throughput limited by emulated wireless channel):
   ```
   [ ID] Interval           Transfer     Bitrate         Retr
   [  5]   0.00-10.00  sec   224 MBytes   188 Mbits/sec   0    sender
   [  5]   0.00-10.04  sec   224 MBytes   187 Mbits/sec        receiver
   ```

   The ~188 Mbps throughput reflects the emulated 80 MHz WiFi6 channel with 64-QAM modulation and rate-1/2 LDPC coding. Without netem (i.e., without sudo), you would see 10+ Gbps.

   **Troubleshooting**: If iperf3 shows 10+ Gbps instead of ~188 Mbps, netem is not configured. Run the check script to diagnose:
   ```bash
   ./examples/vacuum_20m/check_netem.sh
   ```

4. **Cleanup**:
   ```bash
   uv run sine destroy examples/vacuum_20m/network.yaml
   ```

## Workflow: Creating Your Own Network

To create and run your own custom emulated network:

### 1. Create a Scene File (Optional)

Define the physical environment for ray tracing. Scene files use Mitsuba XML format (required by Sionna's ray tracing engine).

- Use an existing scene from `scenes/` or create your own
- Materials must use ITU naming convention (e.g., `itu_concrete`, `itu_glass`)
- If omitted, use `scenes/vacuum.xml` for free-space propagation
- For fixed netem links only, no scene file is required

See `scenes/generate_room.py` for programmatic scene generation.

### 2. Create a Network Topology (`network.yaml`)

Define your network topology specifying:
- **Nodes**: Use `alpine:latest` with `exec` field to install packages (e.g., `apk add --no-cache iproute2 iputils iperf3`)
- **Interfaces**: Each node defines interfaces with either `wireless` or `fixed_netem` parameters
- **Interface type**: `wireless` (ray-traced) or `fixed_netem` (direct parameters)
- **Links**: Connections between node interfaces
- **Scene**: Path to your Mitsuba XML scene file (for wireless links)

See `examples/` for reference topologies.

### 3. Deploy the Emulation

```bash
# Terminal 1: Start the channel server (computes wireless link parameters)
uv run sine channel-server

# Terminal 2: Deploy containers and apply network emulation
sudo $(which uv) run sine deploy path/to/network.yaml
```

### 4. Run Applications and Tests

Execute your applications, performance tests, or mobility scripts:

```bash
# Run commands inside containers
docker exec -it clab-<topology>-<node> <command>

# Use mobility API to move nodes (updates channel conditions in real-time)
curl -X POST http://localhost:8001/api/mobility/update \
     -H "Content-Type: application/json" \
     -d '{"node": "node1", "x": 5.0, "y": 3.0, "z": 1.0}'
```

Note: IP addresses are automatically configured from the topology YAML. No manual IP assignment is needed.

### 5. Cleanup

```bash
uv run sine destroy path/to/network.yaml
```

## Mobility - Moving Nodes During Emulation

SiNE supports real-time node mobility with automatic channel recomputation. As nodes move, link parameters (delay, jitter, loss, rate) are updated based on new positions.

### What Mobility Does

Mobility scripts **update virtual positions in 3D space** and trigger automatic channel recomputation:

1. **Send HTTP POST requests** to Mobility API server (port 8001) with new `(x, y, z)` coordinates
2. **Trigger Sionna ray tracing** to recompute wireless channel at new positions
3. **Update netem parameters** on container interfaces based on new link conditions
4. **Containers stay in place** - only the emulated wireless link behavior changes

**Key point**: The Docker containers themselves don't move. Only their virtual positions in the ray-traced scene change, which affects the computed path loss, SNR, and resulting netem parameters (delay, jitter, loss%, rate).

### Observable Effects

As nodes move closer together:
- Path loss **decreases** → SNR **increases** → Throughput **increases** (visible in iperf3)
- Packet loss **decreases**, delay may change based on multipath

As nodes move apart:
- Path loss **increases** → SNR **decreases** → Throughput **decreases**
- Packet loss may **increase**, potentially triggering MCS downgrade (if using adaptive MCS)

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

2. **Deploy emulation with mobility API** (Terminal 2):
   ```bash
   sudo $(which uv) run sine deploy --enable-mobility examples/two_rooms/network.yaml
   ```

   The `--enable-mobility` flag starts both the emulation and the mobility API server on port 8001.

3. **Run mobility script** (Terminal 3):
   ```bash
   # Move node2 from (20, 0, 1) to (300, 0, 1) at 3 m/s (takes ~93 seconds)
   uv run python examples/mobility/linear_movement.py node2 30.0 1.0 1.0 30.0 40.0 1.0 1.0

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

## Testing

SiNE includes unit tests and integration tests. Tests are run using pytest.

### Running Tests

```bash
# Install test dependencies
uv sync --extra dev

# Run all unit tests (fast, no sudo required)
uv run pytest tests/unit/ -s

# Run all integration tests (requires sudo for container deployment)
uv run pytest tests/integration/ -s

# Run all tests
uv run pytest -s
```

**Note**: Integration tests require `sudo` for container deployment and netem configuration. The `-s` flag provides verbose output including print statements.

## Example Topologies

Topologies are described in YAML files. Example topologies are provided:

| Example | Description | Link Type | Scene | README |
|---------|-------------|-----------|-------|--------|
| `vacuum_20m/` | Baseline free-space wireless (2 nodes, 20m) | wireless | `vacuum.xml` | [README](examples/vacuum_20m/README.md) |
| `fixed_link/` | Fixed netem parameters (no RF) | fixed_netem | (none) | [README](examples/fixed_link/README.md) |
| `wifi6_adaptive/` | Adaptive MCS selection (WiFi 6) | wireless | `vacuum.xml` | [README](examples/wifi6_adaptive/README.md) |
| `two_rooms/` | Indoor multipath (2 rooms with doorway) | wireless | `two_rooms.xml` | [README](examples/two_rooms/README.md) |
| `manet_triangle_shared/` | 3-node MANET with shared bridge | wireless (shared) | `vacuum.xml` | [README](examples/manet_triangle_shared/README.md) |
| `mobility/` | Movement scripts and API examples | N/A (scripts) | N/A | [README](examples/mobility/README.md) |

The examples demonstrate:
- **Free-space propagation** (`vacuum_20m/`)
- **Indoor multipath** (`two_rooms/`)
- **Adaptive modulation** (`wifi6_adaptive/`)
- **MANET broadcast domains** (`manet_triangle_shared/`) - **True broadcast medium using container-namespace bridge**
- **Fixed link emulation** (`fixed_link/`)
- **Node mobility** (`mobility/`)

### Interface Configuration

Each node defines its interfaces with either `wireless` or `fixed_netem` parameters:

```yaml
nodes:
  node1:
    kind: linux
    image: alpine:latest
    interfaces:
      eth1:
        wireless:                    # Option 1: Ray-traced wireless
          position: {x: 0, y: 0, z: 1}
          frequency_ghz: 5.18
          bandwidth_mhz: 80
          # ... other RF params

  node2:
    interfaces:
      eth1:
        fixed_netem:                 # Option 2: Direct netem values
          delay_ms: 10.0
          jitter_ms: 1.0
          loss_percent: 0.5
          rate_mbps: 100.0

topology:
  links:
    - endpoints: [node1:eth1, node2:eth1]
```

**Key points:**
- Each interface must have exactly one of `wireless` or `fixed_netem`
- Both endpoints of a link must be the same type
- Scene file only required for wireless links

### Sudo Configuration (Optional)

To avoid entering your password every time you deploy, configure passwordless sudo:

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

## CLI Commands

Available commands (run with `uv run sine <command>`):

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

## Real-Time Network Visualization

![video](./images/two_rooms_live.webm)

Monitor your running emulation in real-time with `scenes/viewer_live.ipynb`:

```bash
# 1. Start the channel server (if not already running)
uv run sine channel-server

# 2. Deploy an emulation
sudo $(which uv) run sine deploy examples/two_rooms/network.yaml

# 3. Open the live viewer in Jupyter Notebook (browser-based)
uv run --with jupyter jupyter notebook scenes/viewer_live.ipynb
```

**Important**: Run in standard Jupyter Notebook (browser), not VS Code's Jupyter extension. The 3D preview widget requires a browser environment.

### Features

The live viewer provides:

**Cached Channel Metrics** (instant retrieval):
- **RMS Delay Spread (τ_rms)**: Indicates inter-symbol interference severity
- **Coherence Bandwidth (Bc)**: Determines if channel is frequency-flat or frequency-selective
- **Rician K-factor**: LOS/NLOS power ratio for channel classification
- **Propagation Paths**: Strongest 5 paths per link with interaction types (reflection, refraction, diffraction)
- **Power Coverage**: Percentage of total channel power captured by shown paths

**3D Scene Visualization**:
- **Cell 5**: One-time snapshot with 3D scene preview showing devices and propagation paths
- **Cells 7-8**: Animated movie creation capturing channel state over time

### Usage Examples

**One-time snapshot**:
```python
# Cell 5: Render current state with 3D preview (clips at z=2.0m for indoor scenes)
await render_snapshot(show_3d=True, clip_at=2.0)
```

**Animation movie** (for mobility scenarios):
```python
# Cell 8: Create 30-second movie with 1-second intervals
movie = await create_channel_movie(
    t_monitor=30.0,      # Monitor for 30 seconds
    delta_t=1.0,         # Capture frame every 1 second
    clip_at=2.0,         # Clip scene at z=2.0m
    num_samples=16,      # Render quality (lower=faster)
    resolution=(800, 600)
)
display(movie)
```

### How It Works

- **Channel server caches paths** when computing netem parameters during deployment
- **Notebook queries `/api/visualization/state`** to fetch cached data (instant)
- **Paths re-computed in notebook** from cached positions to get Sionna `Paths` object for 3D preview
- **Movie mode captures frames** over time by polling server and rendering each frame with `scene.render()`

**Performance**: Snapshot rendering has ~100-500ms overhead (acceptable for visualization). Movie creation takes approximately `t_monitor + num_frames × render_time` where render_time ≈ 1-2 seconds per frame with num_samples=16.

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

A: Netem is configured **per-interface**, not per-link. SiNE applies netem to each interface that participates in a wireless link. Importantly, netem only affects **egress (outbound) traffic** - packets leaving the interface.

**Which interfaces get netem?**
- **Point-to-point topologies**: Typically `eth1` on both nodes
- **MANET topologies**: All interfaces involved in wireless links (e.g., `eth1`, `eth2`, `eth3`, etc.)
- **General rule**: For each link endpoint `node:ethN`, netem is applied to `ethN` on that node

**Q: How does SiNE handle bidirectional wireless links?**

A: SiNE applies netem to **both** sides of each wireless link. For a simple point-to-point link:

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

For MANET topologies with multiple interfaces per node, each interface involved in a link gets its own netem configuration based on that link's channel conditions.

Both endpoints of a link receive the same parameters (symmetric link). When link conditions change, SiNE updates netem on both endpoints.

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

A: Yes! SiNE supports MANET topologies using **two modes**:

#### Mode 1: Point-to-Point Links (Default)

Each wireless link is a separate veth pair with independent netem configuration.

Example 3-node triangle:
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

**Configuration:**
```yaml
nodes:
  node1:
    interfaces:
      eth1:
        wireless: { ... }  # Link to node2
      eth2:
        wireless: { ... }  # Link to node3

links:
  - endpoints: [node1:eth1, node2:eth1]
  - endpoints: [node1:eth2, node3:eth1]
  - endpoints: [node2:eth2, node3:eth1]
```

**Characteristics:**
- ✅ Simple implementation
- ✅ Easy to debug
- ✅ Independent channel conditions per link
- ❌ Not a true broadcast medium
- ❌ No shared channel contention
- ❌ Multiple interfaces per node

**Use case:** Simple testing, quick prototyping, or large topologies where O(1) per-link overhead is preferred over O(N²) per-destination filters.

#### Mode 2: Shared Bridge (True Broadcast Medium) **NEW!**

All nodes share a **container-namespace Linux bridge** - a bridge hosted inside a lightweight container that is automatically managed by Containerlab. This provides a true broadcast medium where each MANET radio node has just one interface, enabling realistic MANET protocol operation.

**Key innovation:** Per-destination netem using HTB + tc flower filters allows distance-based channel emulation on a shared broadcast medium.

Example 3-node triangle:
```
                ┌──────────────┐
                │ bridge-host  │ ← Container hosting the bridge
                │  (Alpine)    │
                └──────┬───────┘
                       │
                   manet-br0 (bridge)
                       ╬
       ┌───────────────┼───────────────┐
       │               │               │
 Node1:eth1      Node2:eth1      Node3:eth1
```

**Configuration:**
```yaml
topology:
  shared_bridge:
    enabled: true
    name: manet-br0
    nodes: [node1, node2, node3]
    interface_name: eth1
  scene:
    file: scenes/vacuum.xml

nodes:
  node1:
    kind: linux
    image: alpine:latest
    interfaces:
      eth1:
        ip_address: 192.168.100.1  # Required for shared bridge
        wireless:
          position: {x: 0, y: 0, z: 1}
          frequency_ghz: 5.18
          bandwidth_mhz: 80
          # ... other wireless params
```

**Characteristics:**
- ✅ True broadcast medium (packets visible to all nodes)
- ✅ Single interface per node (realistic)
- ✅ Per-destination channel conditions using tc flower filters
- ✅ Supports MANET routing protocols (OLSR, BATMAN-adv, Babel)
- ✅ O(1) packet classification (flower filters)
- ⚠️ Requires Linux kernel 4.2+ (for flower filters)
- ⚠️ More complex TC configuration (HTB + netem + filters)

**Deploy:**
```bash
# Start channel server
uv run sine channel-server

# Deploy shared bridge topology (in another terminal)
sudo $(which uv) run sine deploy examples/manet_triangle_shared/network.yaml
```

**Validation tests:**
```bash
cd examples/manet_triangle_shared
./run_all_tests.sh  # Run all validation tests
```

**How it works:**

**Container-Namespace Bridge Architecture:**

1. **Bridge Host Container**: A lightweight Alpine container (`bridge-host`) hosts the bridge in its network namespace
2. **Automatic Creation**: Containerlab automatically creates the bridge when deploying (no manual `ip link add` needed)
3. **Automatic Cleanup**: Bridge is destroyed when running `containerlab destroy`
4. **Per-Destination Netem**: Each node's interface gets HTB + flower filter configuration

**TC Configuration (per node):**
```
Root HTB qdisc (handle 1:, default 99)
  └── Parent class (1:1)
       ├── Class 1:10 → Netem → flower filter (dst_ip 192.168.100.2)
       ├── Class 1:20 → Netem → flower filter (dst_ip 192.168.100.3)
       └── Class 1:99 → Netem (default, for broadcast)
```

- Unicast packets match destination IP and get per-dest netem
- Broadcast/multicast packets use default class (minimal delay)
- All nodes share the same Linux bridge (true broadcast)

See [examples/manet_triangle_shared/TESTING.md](examples/manet_triangle_shared/TESTING.md) for detailed testing guide.

**Q: Which mode should I use?**

| Use Case | Mode | Reason |
|----------|------|--------|
| Simple MANET testing | Point-to-point | Easier setup, no kernel requirements |
| MANET routing protocols (OLSR, BATMAN-adv) | **Shared bridge** | True broadcast needed for protocol discovery |
| Large topologies (10+ nodes) | Point-to-point | Lower overhead (O(1) vs O(N²)) |
| Hidden node scenarios | **Shared bridge** | Broadcast medium captures RF behavior |
| Quick prototyping | Point-to-point | Simpler configuration |

**Q: How do I troubleshoot shared bridge TC filters?**

See the [TC Filter Troubleshooting Guide](#tc-filter-troubleshooting) below.

## Troubleshooting

### "Permission denied" when running sine deploy

**Cause**: netem requires sudo to access container network namespaces.

**Solution**: Run with sudo using full path to uv:
```bash
sudo $(which uv) run sine deploy <topology.yaml>
```

Or configure passwordless sudo (see "Sudo Configuration" section above).

### Channel server not responding / Connection refused

**Cause**: Channel server not running or wrong port.

**Solution**:
1. Start the channel server in a separate terminal:
   ```bash
   uv run sine channel-server
   ```
2. Verify it's running: `curl http://localhost:8000/health`
3. Check the `channel_server` URL in your network.yaml matches

### Container not found / "No such container"

**Cause**: Containers not deployed or wrong name.

**Solution**:
1. Check running containers: `uv run sine status`
2. Container names follow pattern: `clab-<topology-name>-<node-name>`
3. If no containers, deploy first: `sudo $(which uv) run sine deploy <topology.yaml>`

### "No route to host" when pinging between containers

**Cause**: IP addresses not configured on container interfaces.

**Solution**: Assign IP addresses after deployment:
```bash
docker exec -it clab-<topology>-node1 ip addr add 18.0.0.1/24 dev eth1
docker exec -it clab-<topology>-node2 ip addr add 18.0.0.2/24 dev eth1
```

### iperf3 shows 10+ Gbps instead of expected wireless rate

**Cause**: netem not applied (deployment ran without sudo).

**Solution**:
1. Destroy the current deployment: `uv run sine destroy <topology.yaml>`
2. Redeploy with sudo: `sudo $(which uv) run sine deploy <topology.yaml>`
3. Verify netem: `./CLAUDE_RESOURCES/check_netem.sh`

### Scene file not found

**Cause**: Invalid path to Mitsuba XML scene file.

**Solution**:
1. Check the `scene.file` path in your network.yaml
2. Paths are relative to where you run the command
3. Use `scenes/vacuum.xml` for free-space propagation testing

### TC Filter Troubleshooting

For shared bridge mode (HTB + flower filters).

#### Flower filters not supported

**Symptom**: Error during deployment: "Unknown filter 'flower'"

**Cause**: Linux kernel < 4.2 (flower filters require 4.2+)

**Solution**:
```bash
# Check kernel version
uname -r  # Must be >= 4.2

# Upgrade kernel if needed (Ubuntu/Debian)
sudo apt update && sudo apt upgrade linux-generic
```

#### TC configuration missing / HTB not found

**Symptom**: `tc qdisc show` returns no HTB qdisc

**Cause**: Deployment failed or netem configuration error

**Solution**:
```bash
# Check deployment logs
sudo $(which uv) run sine deploy examples/manet_triangle_shared/network.yaml 2>&1 | grep -i error

# Verify containers are running
docker ps | grep manet-triangle-shared

# Redeploy if needed
sudo $(which uv) run sine destroy examples/manet_triangle_shared/network.yaml
sudo $(which uv) run sine deploy examples/manet_triangle_shared/network.yaml
```

#### Flower filters matching 0 packets

**Symptom**: `tc -s filter show dev eth1` shows 0 packets matched

**Cause**: Incorrect destination IPs in filters or no traffic

**Solution**:
```bash
# 1. Verify IP addresses on interfaces
docker exec clab-manet-triangle-shared-node1 ip addr show eth1
# Should show: 192.168.100.1/24

# 2. Check filter configuration matches IPs
docker exec clab-manet-triangle-shared-node1 tc filter show dev eth1
# Should show: dst_ip 192.168.100.2, dst_ip 192.168.100.3

# 3. Generate traffic
docker exec clab-manet-triangle-shared-node1 ping -c 10 192.168.100.2

# 4. Check filter stats again
docker exec clab-manet-triangle-shared-node1 tc -s filter show dev eth1
# Packet counts should increment
```

#### Ping shows unexpected RTT

**Symptom**: RTT doesn't match configured delay × 2

**Cause**: Asymmetric delays or processing overhead

**Solution**:
```bash
# Check configured delay for destination
docker exec clab-manet-triangle-shared-node1 tc qdisc show dev eth1 | grep netem

# Expected RTT = 2 × one-way delay (forward + reverse)
# Allow ±20% tolerance for processing overhead

# Debug: check both directions
docker exec clab-manet-triangle-shared-node1 ping -c 10 192.168.100.2
docker exec clab-manet-triangle-shared-node2 ping -c 10 192.168.100.1
# RTTs should be similar
```

#### Per-destination netem not working

**Symptom**: All destinations have same delay/loss

**Cause**: Flower filters not classifying packets correctly

**Solution**:
```bash
# Run comprehensive tests
cd examples/manet_triangle_shared
./test_tc_config.sh      # Verify TC configuration
./test_filter_stats.sh   # Verify packet classification

# Manual debug: watch filter stats in real-time
watch -n 1 'docker exec clab-manet-triangle-shared-node1 tc -s filter show dev eth1'

# Generate traffic to specific destinations
docker exec clab-manet-triangle-shared-node1 ping -c 100 192.168.100.2 &
docker exec clab-manet-triangle-shared-node1 ping -c 100 192.168.100.3 &
# Filter counts for each dst_ip should increment independently
```

#### Kernel 4.2+ requirement issues

**Symptom**: Flower filters fail on older kernels

**Alternatives if kernel upgrade not possible**:
1. Use point-to-point mode instead (examples/manet_triangle)
2. Use u32 filters (slower, O(N) classification):
   ```bash
   tc filter add dev eth1 protocol ip parent 1:0 prio 1 u32 \
      match ip dst 192.168.100.2 flowid 1:10
   ```

**Check if flower is supported**:
```bash
tc filter add dev lo flower help 2>&1 | grep -q "flower" && echo "Supported" || echo "Not supported"
```

## License

Apache License 2.0
