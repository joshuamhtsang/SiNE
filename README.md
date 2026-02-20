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
sudo $(which uv) run sine deploy examples/for_user/adaptive_mcs_wifi6/network.yaml

# Terminal 3: Test throughput
docker exec -it clab-adaptive-mcs-wifi6-node1 iperf3 -s
# In another terminal:
docker exec -it clab-adaptive-mcs-wifi6-node2 iperf3 -c 192.168.1.1

# Expected: Variable rate based on SNR (typical: 150-500 Mbps depending on selected MCS)

# Cleanup
uv run sine destroy examples/for_user/adaptive_mcs_wifi6/network.yaml
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

See [examples/for_user/adaptive_mcs_wifi6/](examples/for_user/adaptive_mcs_wifi6/) for complete example.

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

**SINR Examples** (see `examples/for_tests/`):
- Basic MANET: `shared_sionna_sinr_equal-triangle/` (equilateral, co-channel)
- Asymmetric MANET: `shared_sionna_sinr_asym-triangle/` (variable link quality)
- Round-robin TDMA: `shared_sionna_sinr_tdma-rr/` (equal slot allocation)
- Fixed TDMA: `shared_sionna_sinr_tdma-fixed/` (custom scheduling)
- CSMA/CA: `shared_sionna_sinr_csma/` (carrier sensing with interference)

**Note**: SINR examples are in `examples/for_tests/` for integration testing. User-friendly versions for `examples/for_user/` are planned for future releases.

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

**Example coming soon** (to be added to `examples/for_user/`).

See test examples in `examples/for_tests/`:
- **SNR only**: `shared_sionna_snr_equal-triangle/` (3-node MANET without interference)
- **SINR enabled**: `shared_sionna_sinr_equal-triangle/` and `shared_sionna_sinr_asym-triangle/` (with interference modeling)
- **Multi-radio**: `shared_sionna_snr_dual-band/` (dual-band 2.4 GHz + 5 GHz per node)

### Node Mobility

SiNE supports real-time position updates with automatic channel recomputation. See [CLAUDE.md](CLAUDE.md) for detailed mobility API documentation and examples.

### Real-Time Visualization

Monitor running emulations with live channel metrics and 3D visualization:

```bash
# 1. Start channel server
uv run sine channel-server

# 2. Deploy emulation
sudo $(which uv) run sine deploy examples/for_tests/p2p_sionna_snr_two-rooms/network.yaml

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

## Utilities

### Spectral Efficiency Calculator

Analyze network topologies and compute spectral efficiency metrics for each wireless link. See [dev_resources/PLAN_calc_spectral_efficiency.md](dev_resources/PLAN_calc_spectral_efficiency.md) for full details.

**Features**:
- Shannon channel capacity (theoretical maximum)
- Effective data rate (practical throughput with MCS)
- Spectral efficiency (bits/s/Hz) with categorization
- Shannon gap (distance from theoretical limit)
- Link margin (robustness to fading)
- BER/PER analysis

**Usage**:
```bash
# 1. Start channel server
uv run sine channel-server

# 2. Run spectral efficiency calculator
uv run python utilities/calc_spectralefficiency.py examples/for_tests/p2p_fallback_snr_vacuum/network.yaml

# Example output:
# ╭────────────────────────────────────────────────────────╮
# │              Spectral Efficiency Analysis              │
# ├──────┬──────┬─────┬─────────┬────────┬─────────┬──────┤
# │ Link │ Dist │ SNR │ Shannon │ Effec  │ Spec    │ Gap  │
# │      │ (m)  │ (dB)│ (Mbps)  │ Rate   │ Eff     │ (dB) │
# │      │      │     │         │ (Mbps) │ (b/s/Hz)│      │
# ├──────┼──────┼─────┼─────────┼────────┼─────────┼──────┤
# │ node1│ 20.0 │ 39.7│ 1059    │ 192    │ 13.2 /  │ 7.4  │
# │ :eth1│      │     │ (13.2)  │        │ 2.4     │      │
# │  ↔   │      │     │         │        │ (Medium)│      │
# │ node2│      │     │         │        │         │      │
# │ :eth1│      │     │         │        │         │      │
# ╰──────┴──────┴─────┴─────────┴────────┴─────────┴──────╯
```

**Supports**:
- Point-to-point wireless links
- Shared bridge (MANET) topologies (generates full mesh)
- Adaptive MCS selection scenarios
- Fixed modulation/coding configurations

## Example Topologies

### User Examples (`examples/for_user/`)

| Example | Description | Features |
|---------|-------------|----------|
| [adaptive_mcs_wifi6/](examples/for_user/adaptive_mcs_wifi6/) | WiFi 6 MCS selection | SNR-based adaptive MCS |
| [fixed_link/](examples/for_user/fixed_link/) | Fixed netem parameters | No RF, direct params |
| [mobility/](examples/for_user/mobility/) | Node mobility | Dynamic position updates, API examples |

### Test Examples (`examples/for_tests/`)

Key integration test examples (see directory for complete list):

| Example | Description | Features |
|---------|-------------|----------|
| [p2p_fallback_snr_vacuum/](examples/for_tests/p2p_fallback_snr_vacuum/) | Baseline free-space (2 nodes, 20m) | Basic wireless, fallback engine |
| [p2p_sionna_snr_two-rooms/](examples/for_tests/p2p_sionna_snr_two-rooms/) | Indoor multipath | 2 rooms with doorway, Sionna RT |
| [shared_sionna_snr_equal-triangle/](examples/for_tests/shared_sionna_snr_equal-triangle/) | 3-node MANET | Shared bridge, broadcast, SNR-only |
| [shared_sionna_sinr_asym-triangle/](examples/for_tests/shared_sionna_sinr_asym-triangle/) | 3-node MANET with SINR | Asymmetric geometry, positive SINR |
| [shared_sionna_snr_dual-band/](examples/for_tests/shared_sionna_snr_dual-band/) | Dual-band per node | 2.4 GHz + 5 GHz, multi-interface |
| [shared_sionna_sinr_tdma-rr/](examples/for_tests/shared_sionna_sinr_tdma-rr/) | Round-robin TDMA | Equal slot allocation, SINR |
| [shared_sionna_sinr_csma/](examples/for_tests/shared_sionna_sinr_csma/) | CSMA with SINR | Carrier sensing, MCS, interference |

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
UV_PATH=$(which uv) sudo -E $(which uv) run pytest tests/integration/ -s

# Run all tests (integration tests require sudo)
UV_PATH=$(which uv) sudo -E $(which uv) run pytest -s
```

## Troubleshooting

### iperf3 shows 10+ Gbps instead of expected wireless rate

**Cause:** netem not applied (deployment ran without sudo)

**Solution:** Run deployment with sudo
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
- [examples/for_tests/shared_sionna_snr_equal-triangle/TESTING.md](examples/for_tests/shared_sionna_snr_equal-triangle/TESTING.md)
- Test scripts in `examples/for_tests/shared_sionna_snr_equal-triangle/`

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
sudo $(which uv) run sine deploy examples/for_tests/p2p_fallback_snr_vacuum/network.yaml

# Inspect generated containerlab topology
cat examples/for_tests/p2p_fallback_snr_vacuum/.sine_clab_topology.yaml

# File will exist until you destroy
uv run sine destroy examples/for_tests/p2p_fallback_snr_vacuum/network.yaml
```

## 🤝 Collaboration

If you’re interested in collaborating on SiNE, please open an issue to reach out
or start a discussion describing your idea!

## License

Apache License 2.0. See [LICENSE](./LICENSE) for details.
