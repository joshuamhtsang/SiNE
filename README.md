# SiNE - Sionna-based Network Emulation

Wireless network emulation using Sionna ray tracing and Containerlab.

## Overview

SiNE (pronounced "SHEE-na") stands for **Si**onna **N**etwork **E**mulation. Build emulated wireless networks with Docker containers as nodes, allowing you to deploy user-space applications on each node.

**Integration:**
- **Containerlab**: Container deployment and network topology management
- **Nvidia Sionna v1.2.1**: Ray tracing for wireless channel modeling
- **Linux netem**: Apply computed channel conditions (delay, jitter, loss, bandwidth)

**How it works:**
1. Parse `network.yaml` topology file
2. Deploy containers using Containerlab
3. Compute wireless channel conditions using Sionna ray tracing
4. Apply netem parameters to emulate wireless links

```python
delay_ms = propagation_delay       # From strongest path (Sionna RT)
jitter_ms = 0.0                    # Set to 0 (requires MAC/queue modeling, not PHY)
loss_percent = PER × 100           # From BER/BLER calculation
rate_mbps = modulation_based_rate  # Based on MCS, bandwidth, code rate
```

**Note:** BER/BLER calculation uses theoretical AWGN formulas (not Sionna link-level simulation) for speed and deterministic results. Coding gains are applied as SNR offsets (LDPC: +6.5 dB, Polar: +6.0 dB, Turbo: +5.5 dB). This approach is valid for OFDM systems like WiFi 6 where the cyclic prefix absorbs delay spread. Jitter is set to 0 because RMS delay spread (20-300 ns) is absorbed by the OFDM cyclic prefix (800-3200 ns) and does not cause packet-level timing variation. Real jitter (0.1-10 ms) comes from MAC layer effects (CSMA/CA backoff, retransmissions, queueing) which require separate MAC/queue modeling. See [CLAUDE.md](CLAUDE.md) for details.

## Features

- YAML-based network topology configuration
- **Two link types**: Wireless (ray-traced) or Fixed netem (direct parameters)
- **Two MANET modes**: Point-to-point links or Shared bridge (true broadcast medium)
- Ray-traced channel computation with Sionna v1.2.1
- Automatic netem configuration based on channel conditions
- Modulation schemes: BPSK, QPSK, 16/64/256/1024-QAM
- Forward error correction: LDPC, Polar, Turbo
- **Adaptive MCS selection** (WiFi 6 style, SNR-based)
- **SINR computation** with co-channel and adjacent-channel interference
- **ACLR filtering** (IEEE 802.11ax-2021 spectral mask)
- **MAC protocol support**: TDMA, CSMA/CA with configurable transmission probabilities
- Indoor/outdoor scenes with Mitsuba XML (ITU material naming)
- Real-time mobility support with 100ms update polling
- Live visualization with Jupyter notebooks

## Requirements

- Python 3.12+
- Docker
- Containerlab (installed via `./configure.sh`)
- Sionna v1.2.1 (installed automatically via `uv sync`)
- Linux kernel 4.2+ (for tc flower filters in shared bridge mode)
- sudo access (required for netem)
- Optional: NVIDIA GPU with CUDA (use `./configure.sh --cuda`)

## Installation

### 1. System Dependencies

```bash
# Basic setup (installs Containerlab)
./configure.sh

# With GPU support (installs NVIDIA CUDA Toolkit)
./configure.sh --cuda
```

### 2. Python Dependencies

```bash
# Install dependencies (creates venv, installs Sionna v1.2.1)
uv sync

# Development dependencies
uv sync --extra dev
```

## Quick Start

Deploy a simple two-node wireless network with adaptive MCS (WiFi 6):

```bash
# Terminal 1: Start channel server
uv run sine channel-server

# Terminal 2: Deploy emulation
UV_PATH=$(which uv) sudo -E $(which uv) run sine deploy examples/for_user/01_wireless_mesh/network.yaml

# Terminal 3: Test throughput
docker exec -d clab-wireless-mesh-01-node2 iperf3 -s
docker exec clab-wireless-mesh-01-node1 iperf3 -c 192.168.100.2 -t 5

# Expected: ~480 Mbps (30m link, MCS 10)

# Cleanup
UV_PATH=$(which uv) sudo -E $(which uv) run sine destroy examples/for_user/01_wireless_mesh/network.yaml
```

**Why sudo?** Network emulation requires sudo to access container network namespaces via `nsenter` and configure `tc` with netem. Without sudo, links operate at full bandwidth (~10+ Gbps) without wireless emulation.

## Creating Your Own Network

### 1. Create a Scene File (Optional)

Define the physical environment for ray tracing using Mitsuba XML format:

- Use existing scenes from `scenes/` or create your own
- Materials must use ITU naming (e.g., `itu_concrete`, `itu_glass`)
- For free-space propagation, use `scenes/vacuum.xml`
- For fixed netem links only, no scene file is required

### 2. Create Network Topology (`network.yaml`)

Define nodes, interfaces, and links:

```yaml
name: my-network

topology:
  enable_sinr: false

  scene:
    file: scenes/vacuum.xml

  nodes:
    node1:
      kind: linux
      image: alpine:latest
      exec:
        - apk add --no-cache iproute2 iputils iperf3
      interfaces:
        eth1:
          ip_address: 192.168.1.1/24
          wireless:
            position:
              x: 0
              y: 0
              z: 1
            frequency_ghz: 5.18
            bandwidth_mhz: 80
            rf_power_dbm: 20.0
            rx_sensitivity_dbm: -80.0
            antenna_pattern: hw_dipole
            polarization: V
            mcs_table: examples/common_data/wifi6_mcs.csv
            mcs_hysteresis_db: 2.0

    node2:
      kind: linux
      image: alpine:latest
      exec:
        - apk add --no-cache iproute2 iputils iperf3
      interfaces:
        eth1:
          ip_address: 192.168.1.2/24
          wireless:
            position:
              x: 20
              y: 0
              z: 1
            frequency_ghz: 5.18
            bandwidth_mhz: 80
            rf_power_dbm: 20.0
            rx_sensitivity_dbm: -80.0
            antenna_pattern: hw_dipole
            polarization: V
            mcs_table: examples/common_data/wifi6_mcs.csv
            mcs_hysteresis_db: 2.0

  links:
    - endpoints: [node1:eth1, node2:eth1]
```

**Key points:**
- Set `enable_sinr: true` for multi-node interference modeling (SINR), or `false` for SNR-only mode
- Each interface must have either `wireless` or `fixed_netem` parameters
- Both endpoints of a link must be the same type
- Scene file required for wireless links only
- Antenna config: Specify **either** `antenna_pattern` (for Sionna RT patterns like `iso`/`hw_dipole`) **or** `antenna_gain_dbi` (for custom gain values), never both. When using `antenna_gain_dbi`, Sionna automatically uses the `iso` pattern (0 dBi) and adds your explicit gain during SNR calculation to prevent double-counting.
- MCS config: Specify **either** `mcs_table` (for adaptive MCS) **or** fixed `modulation`/`fec_type`/`fec_code_rate` parameters

See `examples/for_user/` for reference topologies.

### 3. Deploy and Test

```bash
# Start channel server
uv run sine channel-server

# Deploy emulation
UV_PATH=$(which uv) sudo -E $(which uv) run sine deploy path/to/network.yaml

# Run your applications
docker exec -it clab-<topology>-<node> <command>

# Cleanup
uv run sine destroy path/to/network.yaml
```

## Advanced Features

### Adaptive MCS Selection

Automatically select optimal modulation and coding based on SNR (WiFi 6 style):

```yaml
interfaces:
  eth1:
    wireless:
      mcs_table: examples/common_data/wifi6_mcs.csv
      mcs_hysteresis_db: 2.0  # Prevent rapid switching
      # ... other params
```

MCS table format:
```csv
mcs_index,modulation,code_rate,min_snr_db,fec_type,bandwidth_mhz
0,bpsk,0.5,5.0,ldpc,80
1,qpsk,0.5,8.0,ldpc,80
# ... up to 1024-QAM
```

See [examples/for_user/03_adaptive_wifi_link/](examples/for_user/03_adaptive_wifi_link/) for complete example.

### SINR and Interference Modeling

SiNE computes Signal-to-Interference-plus-Noise Ratio (SINR) for multi-node scenarios. When `enable_sinr: true` is set, SiNE automatically models co-channel interference from all other active nodes in the topology.

**How it works:**
1. Set `enable_sinr: true` at the topology level
2. SiNE identifies all other active nodes as potential interferers for each link
3. Interference power is computed based on path loss and node activity
4. MAC protocols (TDMA, CSMA/CA) control interference probability via transmission scheduling

**Interference features:**
- **Co-channel interference modeling**: Nodes on the same frequency interfere with each other
- **MAC protocol support**: TDMA and CSMA/CA control when nodes transmit, reducing interference impact
- **Per-interface control**: Use `is_active: false` to disable specific radios
- **Throughput modeling**: MAC protocols affect both interference probability and achievable throughput

**Basic SINR configuration:**

```yaml
topology:
  enable_sinr: true

  nodes:
    node1:
      interfaces:
        eth1:
          wireless:
            frequency_ghz: 5.18
            bandwidth_mhz: 80
            rf_power_dbm: 20.0
            antenna_pattern: hw_dipole

    node2:
      interfaces:
        eth1:
          wireless:
            frequency_ghz: 5.18
            bandwidth_mhz: 80
            rf_power_dbm: 20.0
            antenna_pattern: hw_dipole

    node3:
      interfaces:
        eth1:
          wireless:
            frequency_ghz: 5.18
            bandwidth_mhz: 80
            rf_power_dbm: 20.0
            antenna_pattern: hw_dipole
            is_active: true
```

In this co-channel scenario, SiNE automatically determines:
- For link node1↔node2: node3 is an interferer (same frequency)
- For link node1↔node3: node2 is an interferer (same frequency)
- For link node2↔node3: node1 is an interferer (same frequency)

**MAC protocol integration:**

MAC protocols control **when** nodes transmit, which affects both interference probability and network throughput.

**TDMA (Time Division Multiple Access):**

Nodes transmit in assigned time slots, reducing interference by avoiding simultaneous transmissions:

```yaml
nodes:
  node1:
    interfaces:
      eth1:
        wireless:
          frequency_ghz: 5.18
          tdma:
            enabled: true
            slot_probability: 0.2  # Transmits 20% of the time
```

- **Interference impact**: Interference weighted by `slot_probability` (20% transmission → 20% interference contribution)
- **Throughput impact**: Node's achievable throughput is PHY rate × slot_probability
- **Benefit**: Coordinated scheduling reduces collisions and interference

**CSMA/CA (Carrier Sense Multiple Access with Collision Avoidance):**

Nodes sense the channel before transmitting, avoiding simultaneous transmissions on busy channels:

```yaml
nodes:
  node1:
    interfaces:
      eth1:
        wireless:
          frequency_ghz: 5.18
          csma:
            enabled: true
            traffic_load: 0.3  # 30% duty cycle
            carrier_sense_range_multiplier: 2.5
```

- **Interference impact**: Transmission probability based on carrier sensing and network load
- **Throughput impact**: Contention and backoff reduce achievable throughput
- **Benefit**: Distributed coordination, no centralized scheduling needed

**No MAC protocol (worst-case):**

Without TDMA or CSMA/CA configuration, SiNE assumes worst-case interference (100% transmission probability). This represents scenarios where nodes transmit continuously (e.g., beacon-heavy networks, saturated channels).

See [02_co_channel_interference/](examples/for_user/02_co_channel_interference/) for a complete example — same 3-node mesh as Example 1 with `enable_sinr: true` added.

### MANET Support

Two modes for Mobile Ad-hoc Networks:

**1. Point-to-Point Links (Default)**
- Each link is a separate veth pair with independent netem
- Simple, efficient, easy to debug
- Multiple interfaces per node

**2. Shared Bridge (True Broadcast Medium)**
- All nodes share a container-namespace Linux bridge
- Per-destination netem using HTB + tc flower filters
- Supports multiple interfaces per node (e.g., dual-band 2.4 GHz + 5 GHz)
- Supports MANET routing protocols (OLSR, BATMAN-adv, Babel)

```yaml
topology:
  shared_bridge:
    enabled: true
    name: manet-br0
    nodes: [node1, node2, node3]
    self_isolation_db: 30.0  # Coupling isolation between co-located radios (optional)
```

See [01_wireless_mesh/](examples/for_user/01_wireless_mesh/) (SNR only) and [02_co_channel_interference/](examples/for_user/02_co_channel_interference/) (with SINR) for complete shared bridge examples.

### Node Mobility

SiNE supports real-time position updates with automatic channel recomputation. See [CLAUDE.md](CLAUDE.md) for detailed mobility API documentation and examples.

### Real-Time Visualization

Monitor running emulations with live channel metrics and 3D visualization:

```bash
# 1. Start channel server
uv run sine channel-server

# 2. Deploy emulation (Example 5 is ideal — indoor scene + mobility)
UV_PATH=$(which uv) sudo -E $(which uv) run sine deploy --enable-control examples/for_user/05_moving_node/network.yaml

# 3. Open live viewer (browser-based Jupyter)
uv run --with jupyter jupyter notebook scenes/viewer_live.ipynb
```

Due to the nature of Jupyter notebooks, it's easier to make a copy of the notebook [viewer_live.ipynb](./scenes/viewer_live.ipynb) before running.

**Features:**
- RMS delay spread, coherence bandwidth, K-factor
- 3D scene preview with propagation paths
- Real-time updates for mobility scenarios

**Important:** Run in standard Jupyter Notebook (browser), not VS Code's Jupyter extension.

## CLI Commands

```bash
uv run sine deploy <topology.yaml>          # Deploy emulation
uv run sine destroy <topology.yaml>         # Destroy emulation
uv run sine status                          # Show running containers
uv run sine channel-server                  # Start channel server
uv run sine validate <topology.yaml>        # Validate topology
uv run sine render <topology.yaml> -o img   # Render scene
uv run sine info                            # System information
```

## Example Topologies

### User Examples (`examples/for_user/`)

The examples form a progression — each isolating one SiNE capability. Examples 1→2 add co-channel interference to the same mesh geometry. Examples 3→4 move the same P2P geometry indoors to show how Sionna models wall attenuation.

| Example | Description | Scene | Key Feature |
|---------|-------------|-------|-------------|
| [01_wireless_mesh/](examples/for_user/01_wireless_mesh/) | 3-node WiFi mesh (SNR only) | Free space | Geometry drives MCS: 30m → 480 Mbps, 91m → 320 Mbps |
| [02_co_channel_interference/](examples/for_user/02_co_channel_interference/) | **Same mesh as 01** + `enable_sinr: true` | Free space | Outer links die at −3 dB SINR; surviving link drops to ~50 Mbps |
| [03_adaptive_wifi_link/](examples/for_user/03_adaptive_wifi_link/) | P2P link, free space | Free space | 1024-QAM at 20m; degrades gracefully with distance |
| [04_through_the_wall/](examples/for_user/04_through_the_wall/) | **Same geometry as 03**, indoors | Two rooms | Same link, concrete wall added — SNR drops 15-20 dB, MCS adapts |
| [05_moving_node/](examples/for_user/05_moving_node/) | Real-time node mobility | Two rooms | Throughput changes live as client walks through doorway |

## Channel Server API

REST API for channel computation (port 8000):

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check with GPU status |
| `/scene/load` | POST | Load ray tracing scene |
| `/compute/link` | POST | Compute channel for single link |
| `/compute/links_snr` | POST | Compute channels for multiple links (SNR only, O(N)) |
| `/compute/links_sinr` | POST | Compute channels with interference (O(N²)) |
| `/compute/interference` | POST | Compute SINR with explicit TX/RX/interferers |
| `/visualization/state` | GET | Cached scene/path data for live viewer |
| `/debug/paths` | POST | Get detailed path info for debugging |

Example SINR request:
```json
{
  "receiver": {"node_name": "node1", "position": [0, 0, 1], ...},
  "desired_tx": {"node_name": "node2", "position": [20, 0, 1], ...},
  "interferers": [
    {
      "node_name": "node3",
      "position": [10, 17.3, 1],
      "tx_probability": 0.2,
      "frequency_hz": 5.28e9,
      "is_active": true
    }
  ]
}
```

## Testing

```bash
# Install test dependencies
uv sync --extra dev

# Run unit tests (fast, no sudo)
uv run pytest tests/unit/ -s

# Run integration tests (requires sudo)
UV_PATH=$(which uv) sudo -E $(which uv) run pytest tests/integration/ -s

# Run all tests (integration tests require sudo)
UV_PATH=$(which uv) sudo -E $(which uv) run pytest -s
```

## Debugging and Inspection

### Inspecting the Generated Containerlab Topology

When you deploy a network, SiNE generates a pure containerlab YAML file that can be inspected:

**File**: `.sine_clab_topology.yaml` (in the same directory as your `network.yaml`)

This file contains the topology after stripping all SiNE-specific wireless and netem parameters. It shows exactly what gets passed to the `containerlab deploy` command.

**Lifecycle**:
- ✅ Created during `sine deploy`
- ✅ Available throughout the emulation session
- ❌ Deleted during `sine destroy`

**What's in this file**:
- Pure containerlab format (standard `kind`, `image`, `cmd`, etc.)
- Link endpoints in containerlab format: `endpoints: ["node1:eth1", "node2:eth1"]`
- No wireless parameters (position, frequency, RF power, antenna config, MCS)
- No fixed_netem parameters (delay, jitter, loss, rate)

**When to inspect**:
- Verify container configuration before deployment
- Debug containerlab deployment issues
- Understand the exact topology containerlab is creating
- Confirm interface naming matches expectations

**Example**:
```bash
# Deploy network
UV_PATH=$(which uv) sudo -E $(which uv) run sine deploy examples/for_user/01_wireless_mesh/network.yaml

# Inspect generated containerlab topology
cat examples/for_user/01_wireless_mesh/.sine_clab_topology.yaml

# File will exist until you destroy
UV_PATH=$(which uv) sudo -E $(which uv) run sine destroy examples/for_user/01_wireless_mesh/network.yaml
```

## 🤝 Collaboration

If you’re interested in collaborating on SiNE, please open an issue to reach out
or start a discussion describing your idea!

## License

Apache License 2.0. See [LICENSE](./LICENSE) for details.
