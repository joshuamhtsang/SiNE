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
jitter_ms = delay_spread           # RMS delay spread from multipath
loss_percent = PER × 100           # From BER/BLER calculation
rate_mbps = modulation_based_rate  # Based on MCS, bandwidth, code rate
```

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

Deploy a simple two-node wireless network (20m separation, free space):

```bash
# Terminal 1: Start channel server
uv run sine channel-server

# Terminal 2: Deploy emulation
sudo $(which uv) run sine deploy examples/vacuum_20m/network.yaml

# Terminal 3: Test throughput
docker exec -it clab-vacuum-20m-node1 iperf3 -s
# In another terminal:
docker exec -it clab-vacuum-20m-node2 iperf3 -c 192.168.1.1

# Expected: ~188 Mbps (emulated 80 MHz WiFi6 with 64-QAM, LDPC rate-1/2)

# Cleanup
uv run sine destroy examples/vacuum_20m/network.yaml
```

**Why sudo?** Network emulation requires sudo to access container network namespaces via `nsenter` and configure `tc` with netem. Without sudo, links operate at full bandwidth (~10+ Gbps) without wireless emulation.

**Troubleshooting:** If iperf3 shows 10+ Gbps, run `./examples/vacuum_20m/check_netem.sh` to diagnose.

## Creating Your Own Network

### 1. Create a Scene File (Optional)

Define the physical environment for ray tracing using Mitsuba XML format:

- Use existing scenes from `scenes/` or create your own
- Materials must use ITU naming (e.g., `itu_concrete`, `itu_glass`)
- For free-space propagation, use `scenes/vacuum.xml`
- For fixed netem links only, no scene file is required

Generate scenes programmatically:
```bash
uv run python scenes/generate_room.py -o scenes/my_scene.xml --room1-size 10,8,3
```

### 2. Create Network Topology (`network.yaml`)

Define nodes, interfaces, and links:

```yaml
nodes:
  node1:
    kind: linux
    image: alpine:latest
    exec:
      - apk add --no-cache iproute2 iputils iperf3
    interfaces:
      eth1:
        ip_address: 192.168.1.1
        wireless:
          position: {x: 0, y: 0, z: 1}
          frequency_ghz: 5.18
          bandwidth_mhz: 80
          mcs_table: path/to/mcs_table.csv  # Or fixed modulation/fec
          rf_power_dbm: 20.0
          antenna_gain_dbi: 2.15

  node2:
    kind: linux
    image: alpine:latest
    interfaces:
      eth1:
        ip_address: 192.168.1.2
        wireless:
          position: {x: 20, y: 0, z: 1}
          # ... same wireless params

topology:
  scene:
    file: scenes/vacuum.xml
  links:
    - endpoints: [node1:eth1, node2:eth1]
```

**Key points:**
- Each interface must have either `wireless` or `fixed_netem` parameters
- Both endpoints of a link must be the same type
- Scene file required for wireless links only

See `examples/` for reference topologies.

### 3. Deploy and Test

```bash
# Start channel server
uv run sine channel-server

# Deploy emulation
sudo $(which uv) run sine deploy path/to/network.yaml

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
      mcs_table: examples/wifi6_adaptive/data/wifi6_mcs.csv
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

See [examples/adaptive_mcs_wifi6/](examples/adaptive_mcs_wifi6/) for complete example.

### SINR and Interference Modeling

SiNE computes Signal-to-Interference-plus-Noise Ratio (SINR) for multi-node scenarios with:

- **Co-channel interference**: Same frequency, full interference
- **Adjacent-channel interference**: ACLR filtering based on IEEE 802.11ax-2021 spectral mask
- **MAC protocol support**: TDMA and CSMA/CA with configurable transmission probabilities

```yaml
# Example: TDMA with interference
interferers:
  - node_name: node3
    tx_probability: 0.2  # Transmits 20% of time (1/5 slots)
    is_active: true
    frequency_ghz: 5.28  # Adjacent channel
```

**ACLR filtering:**
- 0-40 MHz separation (< BW/2): 0 dB (co-channel)
- 40-80 MHz: 20-28 dB (transition band)
- 80-120 MHz: 40 dB (1st adjacent)
- >120 MHz: 45 dB (orthogonal)

See examples:
- [examples/manet_triangle_shared_sinr/](examples/manet_triangle_shared_sinr/) - MANET with interference
- [examples/sinr_tdma_roundrobin/](examples/sinr_tdma_roundrobin/) - TDMA scheduling
- [examples/sinr_csma/](examples/sinr_csma/) - CSMA/CA with interference

### MANET Support

Two modes for Mobile Ad-hoc Networks:

**1. Point-to-Point Links (Default)**
- Each link is a separate veth pair with independent netem
- Simple, efficient, easy to debug
- Multiple interfaces per node

**2. Shared Bridge (True Broadcast Medium)**
- All nodes share a container-namespace Linux bridge
- Per-destination netem using HTB + tc flower filters
- Single interface per node (realistic)
- Supports MANET routing protocols (OLSR, BATMAN-adv, Babel)

```yaml
topology:
  shared_bridge:
    enabled: true
    name: manet-br0
    nodes: [node1, node2, node3]
    interface_name: eth1
```

See [examples/manet_triangle_shared/](examples/manet_triangle_shared/) for complete example.

### Node Mobility

Real-time position updates with automatic channel recomputation:

```bash
# Deploy with mobility API
sudo $(which uv) run sine deploy --enable-mobility examples/two_rooms/network.yaml

# Update node position via API
curl -X POST http://localhost:8001/api/mobility/update \
     -H "Content-Type: application/json" \
     -d '{"node": "node2", "x": 10.0, "y": 5.0, "z": 1.5}'

# Or use mobility scripts
uv run python examples/mobility/linear_movement.py node2 30.0 1.0 1.0 30.0 40.0 1.0 1.0
```

See [examples/mobility/README.md](examples/mobility/README.md) for details.

### Real-Time Visualization

Monitor running emulations with live channel metrics and 3D visualization:

```bash
# 1. Start channel server
uv run sine channel-server

# 2. Deploy emulation
sudo $(which uv) run sine deploy examples/two_rooms/network.yaml

# 3. Open live viewer (browser-based Jupyter)
uv run --with jupyter jupyter notebook scenes/viewer_live.ipynb
```

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

| Example | Description | Features |
|---------|-------------|----------|
| [vacuum_20m/](examples/vacuum_20m/) | Baseline free-space (2 nodes, 20m) | Basic wireless |
| [fixed_link/](examples/fixed_link/) | Fixed netem parameters | No RF, direct params |
| [two_rooms/](examples/two_rooms/) | Indoor multipath | 2 rooms with doorway |
| [adaptive_mcs_wifi6/](examples/adaptive_mcs_wifi6/) | WiFi 6 MCS selection | SNR-based adaptive MCS |
| [manet_triangle_shared/](examples/manet_triangle_shared/) | 3-node MANET | Shared bridge, broadcast |
| [manet_triangle_shared_sinr/](examples/manet_triangle_shared_sinr/) | 3-node MANET with SINR | Interference modeling |
| [sinr_tdma_roundrobin/](examples/sinr_tdma_roundrobin/) | Round-robin TDMA | Equal slot allocation |
| [sinr_csma/](examples/sinr_csma/) | CSMA with SINR | Carrier sensing, MCS |
| [mobility/](examples/mobility/) | Movement scripts | Dynamic position updates |

## Channel Server API

REST API for channel computation (port 8000):

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check with GPU status |
| `/scene/load` | POST | Load ray tracing scene |
| `/compute/single` | POST | Compute channel for single link |
| `/compute/batch` | POST | Compute channels for multiple links |
| `/compute/sinr` | POST | Compute SINR with interference |
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
uv run pytest tests/integration/ -s

# Run all tests
uv run pytest -s
```

## Troubleshooting

### iperf3 shows 10+ Gbps instead of expected wireless rate

**Cause:** netem not applied (deployment ran without sudo)

**Solution:**
```bash
uv run sine destroy <topology.yaml>
sudo $(which uv) run sine deploy <topology.yaml>
```

### Channel server not responding

**Solution:**
```bash
# Start channel server in separate terminal
uv run sine channel-server

# Verify it's running
curl http://localhost:8000/health
```

### "Permission denied" when running sine deploy

**Solution:** Run with sudo:
```bash
sudo $(which uv) run sine deploy <topology.yaml>
```

Or configure passwordless sudo:
```bash
sudo tee /etc/sudoers.d/sine <<EOF
$USER ALL=(ALL) NOPASSWD: /usr/bin/nsenter
$USER ALL=(ALL) NOPASSWD: /usr/sbin/tc
EOF
sudo chmod 0440 /etc/sudoers.d/sine
```

### Shared bridge TC filter issues

For shared bridge mode troubleshooting (flower filters, HTB, per-destination netem), see:
- [examples/manet_triangle_shared/TESTING.md](examples/manet_triangle_shared/TESTING.md)
- Test scripts in `examples/manet_triangle_shared/`

## License

Apache License 2.0. See [LICENSE](./LICENSE) for details.
