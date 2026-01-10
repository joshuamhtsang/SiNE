# SiNE - Sionna-based Network Emulation

Wireless network emulation using Sionna ray tracing and Containerlab.

## Overview

SiNE (pronouced "SHEE-na") lets you build emulated wireless networks with Docker containers as nodes, allowing you to easily deploy user-space applications on each node of the network. SiNE  achieves this by integrating:
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
- Ray-traced channel computation using Sionna v1.2.1
- Automatic netem configuration based on channel conditions
- Support for various modulation schemes (BPSK, QPSK, 16/64/256-QAM)
- Forward error correction (LDPC, Polar, Turbo)
- Configurable indoor scenes with Mitsuba XML (ITU material naming)
- Mobility support with 100ms update polling
- Deployment summary showing containers, interfaces, and netem parameters

## Requirements

- Python 3.12+
- Docker
- Containerlab (installed via `./configure.sh`)
- Sionna v1.2.1 (installed automatically via `uv sync`)
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
   docker exec -it clab-vacuum-20m-node1 ip addr add 18.0.0.1/24 dev eth1
   docker exec -it clab-vacuum-20m-node2 ip addr add 18.0.0.2/24 dev eth1
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
   ## IPv4 method
   # iperf3 server on node 1
   docker exec -it clab-vacuum-20m-node1 iperf3 -s
   # iperf3 client on node 2
   docker exec -it clab-vacuum-20m-node2 iperf3 -c 18.0.0.1

   ## OR IPv6 method
   # iperf3 server on node 1
   docker exec -it clab-vacuum-20m-node1 iperf3 -s
   # iperf3 client on node 2 (one-liner using node1's link-local address)
   docker exec -it clab-vacuum-20m-node2 iperf3 -c $(docker exec clab-vacuum-20m-node1 ip -6 addr show dev eth1 | grep fe80 | awk '{print $2}' | cut -d'/' -f1)%eth1
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

6. **Cleanup**:
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

### 2. Build Node Container Images

Build Docker images containing the software your nodes will run:

```bash
# Use the provided base image (includes iperf3, tcpdump, etc.)
docker build -t sine-node:latest docker/node/

# Or build your own custom image
docker build -t my-app:latest ./my-app/
```

### 3. Create a Network Topology (`network.yaml`)

Define your network topology specifying:
- **Nodes**: Container image, interfaces, and their configurations
- **Interface type**: `wireless` (ray-traced) or `fixed_netem` (direct parameters)
- **Links**: Connections between node interfaces
- **Scene**: Path to your Mitsuba XML scene file (for wireless links)

See `examples/` for reference topologies.

### 4. Deploy the Emulation

```bash
# Terminal 1: Start the channel server (computes wireless link parameters)
uv run sine channel-server

# Terminal 2: Deploy containers and apply network emulation
sudo $(which uv) run sine deploy path/to/network.yaml
```

### 5. Configure IP Addresses (Optional)

Containers start with no IP addresses. Assign them manually:

```bash
docker exec -it clab-<topology>-<node> ip addr add <ip>/<mask> dev eth1
```

### 6. Run Applications and Tests

Execute your applications, performance tests, or mobility scripts:

```bash
# Run commands inside containers
docker exec -it clab-<topology>-<node> <command>

# Use mobility API to move nodes (updates channel conditions in real-time)
curl -X POST http://localhost:8001/api/mobility/update \
     -H "Content-Type: application/json" \
     -d '{"node": "node1", "x": 5.0, "y": 3.0, "z": 1.0}'
```

### 7. Cleanup

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
   sudo $(which uv) run sine deploy --enable-mobility examples/vacuum_20m/network.yaml
   ```

   The `--enable-mobility` flag starts both the emulation and the mobility API server on port 8001.

3. **Run mobility script** (Terminal 3):
   ```bash
   # Move node2 from (20, 0, 1) to (300, 0, 1) at 3 m/s (takes ~93 seconds)
   uv run python examples/mobility/linear_movement.py node2 20.0 0.0 1.0 300.0 0.0 1.0 3.0

   # OR waypoint-based movement
   uv run python examples/mobility/waypoint_movement.py
   ```

4. **Monitor throughput** (Terminal 4 - optional):
   ```bash
   # Configure IP addresses first
   docker exec -it clab-vacuum-20m-node1 ip addr add 18.0.0.1/24 dev eth1
   docker exec -it clab-vacuum-20m-node2 ip addr add 18.0.0.2/24 dev eth1

   # Start iperf3 server on node1
   docker exec -it clab-vacuum-20m-node1 iperf3 -s

   # In another terminal, run continuous iperf3 tests
   while true; do docker exec clab-vacuum-20m-node2 iperf3 -c 18.0.0.1 -t 2; sleep 1; done
   ```

   You should see throughput decrease significantly as node2 moves from 20m to 300m away from node1.

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

## Example Topologies

Topologies are described in YAML files. Example topologies are provided:

| Example | Description | Link Type |
|---------|-------------|-----------|
| `vacuum_20m/` | Baseline free-space wireless (20m apart) | wireless |
| `manet_triangle/` | 3-node MANET mesh topology | wireless |
| `fixed_link/` | Fixed netem parameters (no ray tracing) | fixed_netem |

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

### Real-Time Network Visualization

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

The live viewer provides:

**Cached Channel Metrics** (instant retrieval, no computation):
- **RMS Delay Spread (τ_rms)**: Indicates inter-symbol interference severity
- **Coherence Bandwidth (Bc)**: Determines if channel is frequency-flat or frequency-selective
- **Rician K-factor**: LOS/NLOS power ratio for channel classification
- **Propagation Paths**: Strongest 5 paths per link with interaction types (reflection, refraction, diffraction)
- **Power Coverage**: Percentage of total channel power captured by shown paths

**3D Scene Preview with Paths**:
- **Cell 5**: One-time snapshot with 3D visualization and propagation paths
- **Cell 7**: Continuous auto-refresh loop (updates every 1 second) for mobility scenarios

**Usage**:

```python
# In the notebook:

# Option A: Single snapshot with 3D preview
await render_snapshot(show_3d=True, clip_at=2.0)

# Option B: Text-only (faster, no 3D rendering)
await render_text_only()

# Option C: Continuous monitoring for mobility (auto-refresh every 1s)
# Uncomment in Cell 7:
await continuous_monitoring(update_interval_sec=1.0, max_iterations=60)
```

**How It Works**:
- The channel server **caches paths** when computing netem parameters during deployment
- The notebook queries `/api/visualization/state` to fetch cached data (instant, no ray tracing)
- Paths are re-computed in the notebook from cached positions to generate the Sionna `Paths` object for 3D preview
- Small overhead (~100-500ms) acceptable for snapshot/infrequent visualization

**Note**: Path lines are visible in the 3D preview when using `scene.preview(paths=paths)`. The cached data from the channel server provides device positions and channel metrics, while the notebook re-runs `PathSolver` to get the `Paths` object needed for visualization.

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

**Q: How do I specify which interface connects to which peer?**

A: Use the `node:interface` format in endpoints (required):

```yaml
nodes:
  node1:
    interfaces:
      eth1:
        wireless: { ... }  # Config for link to node2
      eth2:
        wireless: { ... }  # Config for link to node3

links:
  - endpoints: [node1:eth1, node2:eth1]  # netem applied to node1:eth1 and node2:eth1
  - endpoints: [node1:eth2, node3:eth1]  # netem applied to node1:eth2 and node3:eth1
```

**Netem application in MANET:**
- Each interface (`eth1`, `eth2`, etc.) gets netem configured independently
- Channel conditions are computed per-link based on distance and scene geometry
- A node with 2 links has netem on 2 interfaces (e.g., `eth1` and `eth2`)

SiNE validates that:
- No interface is used by multiple links
- All interfaces referenced in links are configured on the node
- Both endpoints of a link have the same type (wireless or fixed_netem)

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

## License

Apache License 2.0
