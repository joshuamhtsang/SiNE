# SiNE - Sionna-based Network Emulation

## Project Overview

SiNE is a wireless network emulation package that combines:
- **Containerlab**: Container-based network topology management (REQUIRED dependency)
- **Sionna v1.2.1**: Ray tracing and wireless channel simulation (Python 3.12+)
- **Linux netem**: Network emulation (delay, loss, bandwidth)

### Containerlab Integration Details

SiNE uses containerlab as a core component for deploying the network topology:

1. **Topology Conversion** (`ContainerlabManager.generate_clab_topology()`):
   - SiNE topology YAML extends containerlab format with wireless/fixed_netem parameters
   - Strips interface params to create pure containerlab YAML
   - Links become standard veth links: `endpoints: ["node1:eth1", "node2:eth1"]`
   - Output: `.sine_clab_topology.yaml` file

#### Generated Containerlab Topology File

**File**: `.sine_clab_topology.yaml`
**Location**: Same directory as input `network.yaml`
**Lifecycle**:
- Created during `sine deploy` (before containerlab command execution)
- Persists throughout emulation session
- Deleted automatically during `sine destroy`

**Purpose**: Pure containerlab format topology with all SiNE-specific parameters removed:
- Strips `wireless` parameters: position, frequency, RF power, antenna config, MCS settings
- Strips `fixed_netem` parameters: delay_ms, jitter_ms, loss_percent, rate_mbps
- Keeps standard containerlab fields: kind, image, cmd, binds, env, exec
- Preserves link endpoint format: `endpoints: ["node1:eth1", "node2:eth1"]`

**Inspection**: Users can inspect this file during emulation to verify the containerlab topology or debug deployment issues. The file is available as long as the emulation is running.

2. **Container Deployment**:
   - Executes `containerlab deploy -t .sine_clab_topology.yaml`
   - Creates Docker containers with naming pattern: `clab-<lab_name>-<node_name>`
   - Creates veth pairs connecting containers (eth1, eth2, etc.)
   - eth0 reserved for management interface

3. **Container Discovery**:
   - Discovers containers using Docker API or subprocess fallback
   - Extracts container ID, name, PID, and network interfaces
   - Stores info for later netem configuration

4. **Channel Application**:
   - **Wireless links**: Uses Sionna ray tracing to compute channel conditions (SNR, BER, BLER)
   - **Fixed links**: Uses directly specified netem parameters
   - SiNE abstracts the outputs of Sionna RT and link-level simulation into netem parameters:
     ```python
     delay_ms = propagation_delay       # From strongest path computed in Sionna RT
     jitter_ms = 0.0                    # Set to 0 (requires MAC/queue modeling, not PHY)
     loss_percent = PER × 100           # From BER/BLER calculation (AWGN formulas)
     rate_mbps = modulation_based_rate  # BW × bits_per_symbol × code_rate × efficiency × (1-PER)
     ```
   - Applies netem to containerlab-created veth interfaces using `nsenter` (requires sudo)
   - Bidirectional: applies same params to both TX and RX interfaces

5. **Cleanup**:
   - Executes `containerlab destroy -t .sine_clab_topology.yaml --cleanup`
   - Removes containers, networks, and temp files

**Key Point**: Containerlab is NOT optional - it's the foundation for container and network management. SiNE adds the wireless/fixed channel model layer on top.

## Architecture

```
network.yaml -> EmulationController -> Containerlab (Docker containers + veth links)
   (with RF)          |                       |
                      |                       v
                      |                  (eth1, eth2, ... interfaces)
                      v                       |
              Channel Server (FastAPI) -----> netem (tc/qdisc on veth)
                      |
                      v
              Sionna RT (Ray tracing + BER/BLER/PER)
```

**Deployment Flow**:
1. Parse `network.yaml` (contains containerlab params + wireless params)
2. Generate `.sine_clab_topology.yaml` (pure containerlab format, wireless params stripped)
3. `containerlab deploy` → creates containers and veth pairs
4. Discover container PIDs and interface names
5. Compute channel conditions via Sionna ray tracing
6. Apply netem to veth interfaces using `sudo nsenter -t <pid> -n tc ...`

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
| Container Deployment | Containerlab | Industry-standard container network orchestration; handles topology, containers, veth links |
| Topology Format | Containerlab-compatible YAML | SiNE extends containerlab format with wireless parameters; generates pure containerlab YAML for deployment |
| API Framework | FastAPI | Async support, OpenAPI docs |
| Control Poll | 100ms | Balance responsiveness vs overhead |
| Rate Limiting | tbf | netem lacks native rate control |
| Sionna API | PathSolver, Scene | Sionna v1.2.1 API (use `Scene()` for empty) |
| PER Formula | BLER for coded | Industry standard |
| Scene Config | Explicit file path | Required for wireless links, optional for fixed_netem links |
| Interface Config | Per-interface on node | Each interface has either `wireless` or `fixed_netem` params |
| netem Access | sudo nsenter | Required for container network namespace access |
| Container Naming | `clab-<lab>-<node>` | Follows containerlab convention for consistency |
| SINR Computation | Co-channel + multi-frequency | Interference modeling with MAC protocol integration; ACLR filtering for adjacent channels |
| Interference Model | Linear power summation | Sum interference powers in linear domain (watts) before SINR calculation |
| TDMA Support | Probability-weighted | Interference scaled by transmission probability (slot duty cycle) |
| Antenna Config | antenna_pattern XOR antenna_gain_dbi | Mutual exclusion prevents double-counting Sionna RT pattern gains |

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

## Claude Code Specialized Agents

SiNE includes specialized Claude Code agents for domain-specific expertise. These agents can be invoked via the Task tool when working on related topics.

### Available Agents

| Agent | File | Use Cases |
|-------|------|-----------|
| **wireless-comms-engineer** | `.claude/agents/wireless-comms-engineer.md` | RF link budgets, BER/PER/BLER analysis, Sionna RT validation, MCS table design, coding gain verification, MIMO/beamforming, O-RAN/SON |
| **linux-networking-specialist** | `.claude/agents/linux-networking-specialist.md` | netem/tc debugging, MANET routing protocols (OLSR, BATMAN, AODV, Babel), SDN/OpenFlow (ONOS, OVS, P4), containerlab integration, network namespace operations |

### When to Use Each Agent

**wireless-comms-engineer**:
- Validating channel computation pipeline (SNR, BER, BLER, PER)
- Reviewing MCS tables and thresholds
- Analyzing link budget calculations
- Debugging RF-related issues (antenna gains, path loss, coding gains)
- Designing adaptive modulation schemes
- O-RAN and 3GPP resource management

**linux-networking-specialist**:
- Debugging netem configuration issues
- Implementing MANET routing protocols in containers
- Integrating SDN controllers (ONOS, ODL)
- Troubleshooting veth pairs, bridges, and network namespaces
- Optimizing container network performance
- Setting up per-destination traffic control with tc filters
- Wireless network emulation with IEEE 802.11s mesh


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
# CRITICAL: MUST use full pattern - UV_PATH=$(which uv) sudo -E $(which uv) run ...
UV_PATH=$(which uv) sudo -E $(which uv) run sine deploy examples/for_user/adaptive_mcs_wifi6/network.yaml

# Deploy with control API enabled (for dynamic position updates and runtime control)
UV_PATH=$(which uv) sudo -E $(which uv) run sine deploy --enable-control examples/for_tests/p2p_sionna_snr_two-rooms/network.yaml

# Validate topology
uv run sine validate examples/for_user/adaptive_mcs_wifi6/network.yaml

# Render scene to image (does NOT require channel server)
uv run sine render examples/for_tests/p2p_sionna_snr_two-rooms/network.yaml -o scene.png

# Check system info
uv run sine info

# Show running containers
uv run sine status

# Destroy emulation
UV_PATH=$(which uv) sudo -E $(which uv) run sine destroy examples/for_user/adaptive_mcs_wifi6/network.yaml

# Interactive scene viewer (Jupyter notebook)
uv run --with jupyter jupyter notebook scenes/viewer.ipynb
```

## Deployment Output

When deploying, SiNE displays a summary showing:
- **Deployed Containers**: Name, image, PID, interfaces, positions per interface
- **Link Parameters**: Link endpoints, type (wireless/fixed), delay (ms), jitter (ms), loss %, rate (Mbps)

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

Example topologies are provided in `examples/`:

### User Examples (`examples/for_user/`)

| Example | Description | Link Type | Scene |
|---------|-------------|-----------|-------|
| `adaptive_mcs_wifi6/` | WiFi 6 MCS selection (2 nodes) | wireless | `vacuum.xml` |
| `fixed_link/` | Fixed netem parameters (no RF) | fixed_netem | (none) |
| `mobility/` | Movement scripts and API examples | wireless | Various |

### Test Examples (Integration Testing)

Available in `examples/for_tests/` with flat naming pattern:

| Example | Description | MAC Protocol | Features |
|---------|-------------|--------------|----------|
| `p2p_fallback_snr_vacuum/` | Free-space (2 nodes, 20m) | N/A | Baseline, fallback engine |
| `p2p_sionna_snr_two-rooms/` | Indoor multipath | N/A | 2 rooms with doorway |
| `shared_sionna_sinr_csma-mcs/` | CSMA/CA with adaptive MCS | CSMA/CA | Carrier sensing, SINR, MCS adaptation |

### SINR/Interference Test Examples

| Example | Description | MAC Protocol | Interference Model |
|---------|-------------|--------------|-------------------|
| `shared_sionna_snr_equal-triangle/` | 3-node MANET, shared bridge | N/A | SNR only (no interference) |
| `shared_sionna_sinr_equal-triangle/` | 3-node MANET with SINR | N/A | Co-channel interference |
| `shared_sionna_sinr_asym-triangle/` | Asymmetric 3-node MANET | N/A | Variable link quality, SINR |
| `shared_sionna_sinr_tdma-rr/` | Round-robin TDMA (equal slots) | TDMA | Probability-weighted (20% each) |
| `shared_sionna_sinr_tdma-fixed/` | Fixed TDMA schedule | TDMA | Per-node slot assignments |
| `shared_sionna_snr_dual-band/` | Dual-band (2.4 GHz + 5 GHz) | N/A | Multi-interface per node |

The examples demonstrate:
- **Free-space propagation** (`p2p_fallback_snr_vacuum/`)
- **Indoor multipath** (`p2p_sionna_snr_two-rooms/`)
- **Adaptive modulation** (`for_user/adaptive_mcs_wifi6/`, `for_tests/shared_sionna_sinr_csma-mcs/`)
- **MANET broadcast domains** (`shared_sionna_snr_equal-triangle/`)
- **Fixed link emulation** (`for_user/fixed_link/`)
- **Node mobility** (`for_user/mobility/`)
- **SINR computation** (`shared_sionna_sinr_*`)
- **MAC protocols** (CSMA/CA, TDMA)
- **Multi-radio nodes** (`shared_sionna_snr_dual-band/`)

## Channel Server API

The channel server (`uv run sine channel-server`) exposes REST endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check with GPU status |
| `/scene/load` | POST | Load ray tracing scene |
| `/compute/single` | POST | Compute channel for single link |
| `/compute/batch` | POST | Compute channels for multiple links |
| `/compute/sinr` | POST | Compute SINR with interference from multiple transmitters |
| `/debug/paths` | POST | Get detailed path info for debugging |

### SINR Endpoint: `POST /compute/sinr`

Computes Signal-to-Interference-plus-Noise Ratio for multi-node scenarios with co-channel interference and MAC protocol integration.

**Request** (co-channel scenario):
```json
{
  "receiver": {
    "node_name": "node1",
    "position": [0, 0, 1],
    "antenna_gain_dbi": 2.15,
    "frequency_hz": 5.18e9,
    "bandwidth_hz": 80e6
  },
  "desired_tx": {
    "node_name": "node2",
    "position": [20, 0, 1],
    "tx_power_dbm": 20.0,
    "antenna_gain_dbi": 2.15,
    "frequency_hz": 5.18e9,
    "bandwidth_hz": 80e6
  },
  "interferers": [
    {
      "node_name": "node3",
      "position": [10, 17.3, 1],
      "tx_power_dbm": 20.0,
      "antenna_gain_dbi": 2.15,
      "frequency_hz": 5.18e9,
      "bandwidth_hz": 80e6,
      "is_active": true,
      "tx_probability": 0.2
    }
  ]
}
```

**Response**:
```json
{
  "sinr_db": 22.3,
  "snr_db": 28.3,
  "signal_power_dbm": -65.2,
  "noise_power_dbm": -93.5,
  "interference_power_dbm": -87.5,
  "interference_terms": [
    {
      "node_name": "node3",
      "power_dbm": -87.5,
      "path_loss_db": 68.0,
      "frequency_separation_hz": 0,
      "aclr_db": 0.0
    }
  ]
}
```

**Key features**:
- **Co-channel interference**: Same frequency (5.18 GHz) for all nodes
- **MAC protocol integration**: `tx_probability` weights interference (20% transmission duty cycle)
- **ACLR filtering**: Automatically applied for multi-frequency scenarios (adjacent-channel interference)

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

## Channel Computation Pipeline

For wireless links, SiNE computes channel conditions through a multi-stage pipeline that converts ray tracing results into netem parameters.

### 1. Channel Impulse Response (CIR)

The channel server uses Sionna's `PathSolver` to compute the CIR:

```python
# In src/sine/channel/sionna_engine.py
paths = self.path_solver(tx_pos, rx_pos)
a, tau = paths.cir()  # Complex amplitudes and delays
```

- `a`: Complex path amplitudes (magnitude and phase per path)
- `tau`: Path delays in seconds
- Multiple paths represent multipath propagation (LOS + reflections)

### 2. SNR Calculation

Signal-to-Noise Ratio is computed from the link budget (`src/sine/channel/snr.py`):

```
SNR (dB) = TX_power + TX_gain + RX_gain - Path_loss - Noise_floor

Where:
- TX_power: Transmit power in dBm (e.g., 20 dBm)
- TX_gain, RX_gain: Antenna gains in dBi
- Path_loss: From ray tracing (sum of path powers)
- Noise_floor: -174 dBm/Hz + 10*log10(bandwidth) + noise_figure_db
- noise_figure_db: Configurable per interface (default: 7.0 dB for WiFi 6)
  - WiFi 6: 6-8 dB
  - 5G base station: 3-5 dB
  - High-end SDR: 2-4 dB
  - Cheap IoT radio: 8-12 dB
```

### 3. BER Calculation

Bit Error Rate is computed using theoretical AWGN formulas (`src/sine/channel/modulation.py`):

| Modulation | BER Formula |
|------------|-------------|
| BPSK | Q(√(2·SNR)) |
| QPSK | Q(√(2·SNR)) |
| 16-QAM | (3/8)·erfc(√(SNR/5)) |
| 64-QAM | (7/24)·erfc(√(SNR/21)) |
| 256-QAM | (15/64)·erfc(√(SNR/85)) |
| 1024-QAM | WiFi 6 (802.11ax) support |

### 4. BLER Calculation (for coded systems)

Block Error Rate accounts for FEC coding gains:

```python
# Coding gain applied to SNR before BER calculation
coding_gain = {
    "ldpc": 7.0,   # dB gain at typical code rates
    "polar": 6.5,
    "turbo": 6.0,
    "none": 0.0
}

effective_snr = snr_db + coding_gain[fec_type]
bler = 1 - (1 - ber_coded)^block_size
```

### 5. PER Calculation

Packet Error Rate is derived from BER or BLER (`src/sine/channel/per_calculator.py`):

```python
# For uncoded systems: PER from BER
per = 1 - (1 - ber)^(packet_size_bits)

# For coded systems: PER ≈ BLER (block = packet assumption)
per = bler
```

### 6. SINR Calculation (Multi-Node Scenarios)

Signal-to-Interference-plus-Noise Ratio accounts for interference from other active transmitters:

```
SINR (dB) = 10·log10(Signal_power / (Noise_power + Total_interference_power))

Where:
- Signal_power: From desired transmitter (TX power + gains - path loss)
- Noise_power: Thermal noise floor
- Total_interference_power: Sum of interference from all other active transmitters
```

**Adjacent-Channel Leakage Ratio (ACLR)**: For multi-frequency scenarios, SiNE applies IEEE 802.11ax-2021 spectral mask filtering:

| Frequency Separation (80 MHz BW) | ACLR (dB) | Description |
|----------------------------------|-----------|-------------|
| 0-40 MHz (< BW/2) | 0 dB | Co-channel (channels overlap) |
| 40-80 MHz | 20-28 dB | Transition band (linear interpolation) |
| 80-120 MHz | 40 dB | 1st adjacent channel |
| >120 MHz | 45 dB | Orthogonal (filtered out) |

**Benefits**:
- Multi-frequency MANET topologies with frequency diversity
- Dual-band scenarios (2.4 GHz + 5 GHz) with zero cross-band interference
- Adjacent-channel coexistence modeling
- TDMA networks on adjacent frequencies with reduced interference

**TDMA Support**: For time-division scenarios, interference is weighted by transmission probability:
```
SINR_TDMA = Signal / (Noise + Σ(Interference_i × slot_probability_i))
```

**Antenna Gains in SINR**: Both signal and interference calculations include configured antenna gains. When using Sionna RT antenna patterns (iso, hw_dipole, etc.), the pattern gains are embedded in the path coefficients. When using explicit `antenna_gain_dbi`, the gain value is applied to both transmit and receive paths. This ensures SINR computations accurately reflect the antenna configuration.

**Example Impact**: With `hw_dipole` antennas (2.16 dBi gain each):
- Signal path gain: +2.16 dBi (TX) + 2.16 dBi (RX) = +4.32 dB
- Interference path gain: +2.16 dBi (interferer TX) + 2.16 dBi (receiver RX) = +4.32 dB
- Net effect: Antenna gains affect both signal and interference equally in symmetric scenarios

### 7. Netem Parameter Conversion

The final PER (or SINR for multi-node scenarios) is converted to netem parameters:

| Parameter | Calculation |
|-----------|-------------|
| **delay_ms** | Propagation delay from strongest path (distance/c) |
| **jitter_ms** | Set to 0.0 (requires MAC/queue modeling, not PHY delay spread) |
| **loss_percent** | PER × 100 (packet loss probability) |
| **rate_mbps** | Shannon capacity or modulation-based rate |

### Data Rate Calculation

The achievable data rate is computed from modulation and bandwidth:

```
Rate (Mbps) = bandwidth_hz × bits_per_symbol × code_rate × (1 - overhead)

Example (80 MHz, 64-QAM, rate-1/2 LDPC):
= 80e6 × 6 × 0.5 × 0.8 = 192 Mbps
```

### Pipeline Summary

```
Ray Tracing → CIR (paths) → Path Loss → SNR
                                         ↓
                              ┌──────────┴──────────┐
                              │                     │
                         Single-Link           Multi-Node
                              │                     │
                              ↓                     ↓
                    BER (from modulation)    SINR (interference)
                              │                     │
                              ↓                     ↓
                    BLER (with FEC gain)   BER (from SINR)
                              │                     │
                              ↓                     ↓
                        PER (packet errors)    BLER/PER
                              │                     │
                              └──────────┬──────────┘
                                         ↓
                    Netem Params (delay, jitter, loss%, rate)
```

### Physical Phenomena: What SiNE Captures vs. What It Doesn't

**Important:** SiNE is designed for **WiFi 6/OFDM network emulation**, not PHY waveform simulation. The channel model reflects how OFDM receivers process multipath signals.

#### ✅ Correctly Captured (for OFDM/WiFi 6)

| Phenomenon | How SiNE Captures It | Physical Basis |
|------------|---------------------|----------------|
| **Multipath diversity gain** | Incoherent power summation (Σ\|aᵢ\|²) | OFDM receiver coherently combines paths per subcarrier, then averages across 234+ subcarriers → diversity gain (0-3 dB typical) |
| **Geometry-based path loss** | Ray tracing with reflections/diffractions | Accurate modeling of LOS/NLOS transitions, wall penetration, multipath propagation |
| **Delay spread → coherence bandwidth** | Computed but diagnostic only (τ_rms) | For WiFi 6: τ_rms (20-300 ns) << cyclic prefix (800-3200 ns) → no ISI |
| **SNR-based packet loss** | AWGN BER formulas → PER → loss_percent | Valid for OFDM with proper cyclic prefix (no ISI after equalization) |
| **Frequency selectivity (multi-freq)** | ACLR filtering for SINR computation | IEEE 802.11ax spectral mask prevents cross-channel interference |
| **LOS vs. NLOS propagation** | K-factor, dominant path type | Ray tracing identifies LOS/NLOS conditions, affects SNR |

**Why incoherent summation is correct:**
- OFDM performs FFT → per-subcarrier channel: H(f) = Σ aᵢ·e^(-j2πfτᵢ)
- Each subcarrier is equalized independently
- Averaging across subcarriers → E[\|H(f)\|²] ≈ Σ\|aᵢ\|²
- Valid when τ_rms << cyclic prefix (20-300 ns << 800-3200 ns) ✅

#### ⚠️ Limitations (What's NOT Captured)

| Missing Phenomenon | Why Not Captured | Impact |
|-------------------|------------------|--------|
| **Jitter (packet timing variation)** | Currently set to 0.0 | Real jitter requires MAC/queue modeling (CSMA/CA backoff, retransmissions, queueing) - 0.1-10 ms typical |
| **Fast fading (time-varying)** | Static channel per computation | No Doppler, Rayleigh, or Rician fading over time unless positions change |
| **ISI (inter-symbol interference)** | AWGN BER formulas only | Not needed for OFDM - cyclic prefix absorbs delay spread |
| **MAC layer effects** | No MAC protocol modeling | No CSMA/CA contention, no HARQ retransmissions, no frame aggregation |
| **Per-subcarrier fading nulls** | Averaged across subcarriers | OFDM frequency diversity smooths out nulls |
| **Coherent combining effects** | Incoherent summation | Narrowband single-carrier would need coherent sum (not WiFi 6) |

#### 📊 Valid Operating Range

SiNE's OFDM-based channel model is valid when:

| Parameter | Valid Range | Typical Indoor | Notes |
|-----------|-------------|----------------|-------|
| **Delay spread (τ_rms)** | < 800 ns | 20-300 ns | WiFi 6 short GI cyclic prefix |
| **Bandwidth** | 20-160 MHz | 80 MHz | Typical OFDM channel bandwidths |
| **Coherence bandwidth (Bc)** | > 312.5 kHz | 1-10 MHz | Bc ≈ 1/(2πτ_rms) > subcarrier spacing |
| **Environment** | Indoor/urban | N/A | τ_rms typically stays within valid range |

**When SiNE's model would be invalid:**
- Narrowband single-carrier systems (GPS, FSK/PSK) - would need coherent summation
- Extreme delay spread (τ_rms > 800 ns) - would exceed cyclic prefix
- Systems without OFDM - AWGN assumptions may not hold

#### 🔧 What Requires Additional Modeling

To model phenomena beyond SiNE's current scope:

| Desired Phenomenon | Implementation Approach |
|-------------------|------------------------|
| **Jitter** | Implement MAC/queue simulator with CSMA/CA, retransmission logic |
| **Fast fading** | Add stochastic perturbations to SNR based on Doppler/velocity |
| **HARQ retransmissions** | MAC layer with ARQ/HARQ state machine |
| **CSMA/CA contention** | Carrier sense and exponential backoff logic |
| **Frame aggregation** | A-MPDU/A-MSDU with variable frame sizes |

### Multi-Radio Node Assumptions

**Co-located radios** (multiple interfaces on same node):
- All interfaces share the same position (node position)
- Antenna spatial separation (5-50 cm typical) NOT modeled
- Impact: Negligible for link distances >1m (spatial separation << link distance)
- Antenna coupling (20-40 dB isolation) NOT modeled
  - Real hardware: TX from one radio couples into RX of co-located radio
  - SiNE: Only path loss + ACLR filtering separate co-located radios
  - Conservative: May slightly overestimate interference for adjacent-band radios

**Per-interface control** enables:
- Band-specific power management (disable 2.4 GHz, keep 5 GHz)
- Cognitive radio dynamic spectrum access
- Radio-specific failure modeling
- Listen-only monitoring nodes (RX active, TX disabled via `is_active: false`)

**Example multi-radio scenarios:**
```yaml
nodes:
  dual_band_ap:
    interfaces:
      eth1:
        wireless:
          is_active: true
          frequency_ghz: 5.18
          position: {x: 0, y: 0, z: 2.5}  # Same position as eth2
      eth2:
        wireless:
          is_active: false  # 2.4 GHz disabled for power saving
          frequency_ghz: 2.4
          position: {x: 0, y: 0, z: 2.5}  # Same position as eth1
```

**Physical assumptions:**
- Both interfaces at same node position → path loss identical
- Frequency separation (2.4 GHz vs 5.18 GHz = 2.78 GHz) → ACLR ≈ 45 dB
- No antenna coupling modeled → actual hardware would have 20-40 dB isolation
- Net effect: Conservative (may overestimate cross-band interference by 5-25 dB)

### Relationship Between Channel Metrics and Netem Parameters

**Important:** SiNE operates as **network emulation** (application-layer testing), not **PHY simulation** (waveform-level). Enhanced channel metrics like RMS delay spread (τ_rms), coherence bandwidth (Bc), and Rician K-factor are **diagnostic only** for visualization and debugging.

**These metrics do NOT directly influence netem configuration** - the netem parameters already account for or abstract physical channel effects:

| Physical Effect | How It's Captured/Abstracted in Netem |
|----------------|----------------------------------------|
| **Delay spread (τ_rms)** | Not used for netem (diagnostic only). Real jitter requires MAC/queue modeling. |
| **Frequency selectivity (Bc)** | Not directly captured; SiNE uses AWGN BER formulas (frequency-flat assumption) |
| **K-factor (LOS/NLOS)** | Indirectly via SNR (LOS has lower path loss → higher SNR → lower loss%) |
| **Coherence time (Tc)** | May inform visualization update interval, not netem params |

**Note on BER Calculation:**

SiNE uses **theoretical AWGN (frequency-flat) BER formulas** based purely on SNR and modulation scheme, NOT Sionna's link-level simulation capabilities (bit generation → mapping → channel → demapping). This provides:

- **Speed**: Instant computation (microseconds) vs Monte Carlo simulation (seconds)
- **Deterministic**: No random variation from finite simulation runs
- **Scalability**: Compute thousands of links per second for large topologies

**BER Formulas** ([src/sine/channel/modulation.py:73-113](src/sine/channel/modulation.py#L73-L113)):
- **BPSK/QPSK**: `BER = 0.5 × erfc(√(Eb/N0))`
- **M-QAM**: Symbol error rate → BER via Gray coding approximation

**BLER Approximation** (for coded systems, [modulation.py:185-233](src/sine/channel/modulation.py#L185-L233)):
- Applies coding gain offset to SNR: `effective_snr = snr_db + coding_gain`
- Coding gains (approximate, at BER ≈ 10⁻⁵):
  - LDPC: +6.5 dB
  - Polar: +6.0 dB
  - Turbo: +5.5 dB
- Then calculates BER at effective SNR

**Note**: A `SionnaBERCalculator` class exists ([modulation.py:270-348](src/sine/channel/modulation.py#L270-L348)) that implements full link-level simulation (bits → symbols → AWGN → demapping → error counting), but it is **not used** in the main channel computation pipeline.

**Validity**: Theoretical formulas are appropriate for OFDM systems (WiFi 6) where the cyclic prefix absorbs delay spread and prevents ISI at the packet level. Valid when τ_rms < 800 ns (short GI), which is typical for indoor environments (20-300 ns).

**Limitations**:
- Does not capture frequency selectivity within OFDM bandwidth (assumes frequency-flat fading)
- Coding gains are approximations (real LDPC/Polar performance varies with block length, code rate, decoder iterations)
- No modeling of interleaving, puncturing, or other practical FEC implementation details

**Use diagnostic metrics to:**
- Understand **why** certain netem parameters were chosen (e.g., low SNR causing high packet loss)
- Validate that netem parameters make sense given channel conditions
- Determine appropriate visualization update rates for mobility scenarios
- Debug link quality issues by understanding the underlying RF propagation
- Verify delay spread is within OFDM cyclic prefix bounds (τ_rms < 800 ns for WiFi 6)

**Example:** If visualization shows high loss_percent with τ_rms = 50 ns, the delay spread is NOT causing the loss. The τ_rms is absorbed by OFDM cyclic prefix (800-3200 ns). The loss_percent comes from low SNR. If SNR is low due to high path loss, increase TX power, improve antenna gains, or reduce distance.

## Important Notes

### Configuration Requirements
- **Interface Configuration**: Define per-interface using `interfaces.<iface>.wireless` or `interfaces.<iface>.fixed_netem`
- **Link Endpoints**: Must use `node:interface` format (e.g., `endpoints: [node1:eth1, node2:eth1]`)
- **Link Type Consistency**: Both endpoints must be same type (both wireless OR both fixed_netem)
- **Scene Configuration**: Required for wireless links; optional for fixed_netem-only topologies
- **netem**: Requires `sudo` for container network namespace access

### Sionna-Specific
- **Scene Materials**: Must use ITU naming (e.g., `itu_concrete`, not `concrete`)
- **Antenna Patterns**: `"iso"`, `"dipole"`, `"hw_dipole"`, `"tr38901"`
- **Antenna Polarization**: `"V"`, `"H"`, `"VH"`, `"cross"`

### SINR/Interference
- **Requires `topology.enable_sinr: true`** in network.yaml (explicit opt-in, see [SINR Configuration](#sinr-configuration))
- When enabled, models co-channel interference from active nodes on the same frequency
- MAC protocols (TDMA, CSMA/CA) control interference probability via transmission scheduling
- ACLR filtering automatically applied for multi-frequency scenarios (adjacent-channel interference)

## Scene Visualization

### Interactive Viewer (`scenes/viewer.ipynb`)

The Jupyter notebook provides:
- Lists all scene objects with IDs, center positions, bounding boxes, and materials
- Adds axis markers (TX at origin, RX at 1m along each axis) for orientation
- Supports clipping planes to see interior (`scene.preview(clip_at=2.0)`)
- Alt+click in preview to get coordinates of any point

### Real-Time Network Visualization (`scenes/viewer_live.ipynb`)

Monitor running emulations in real-time with cached channel metrics and 3D path visualization:

```bash
# 1. Start channel server
uv run sine channel-server

# 2. Deploy emulation
UV_PATH=$(which uv) sudo -E $(which uv) run sine deploy examples/for_tests/p2p_sionna_snr_two-rooms/network.yaml

# 3. Open live viewer (browser-based Jupyter)
uv run --with jupyter jupyter notebook scenes/viewer_live.ipynb
```

**Features**:
- **Cached channel metrics**: RMS delay spread, coherence bandwidth, K-factor, propagation paths
- **3D scene preview**: Device positions and propagation path lines
- **Wireless channel analysis**: Frequency selectivity, LOS/NLOS classification, ISI assessment
- **Auto-refresh mode**: Continuous monitoring for mobility scenarios (1-second updates)

**Usage in notebook**:
```python
# Cell 5: Single snapshot with 3D visualization
await render_snapshot(show_3d=True, clip_at=2.0)

# Cell 6: Text-only (faster)
await render_text_only()

# Cell 7: Continuous auto-refresh (uncomment to enable)
await continuous_monitoring(update_interval_sec=1.0, max_iterations=60)
```

**How it works**:
- Channel server caches paths when computing netem parameters
- Notebook queries `/api/visualization/state` for cached data (instant)
- Paths are re-computed in notebook to get Sionna `Paths` object for 3D preview
- Small overhead (~100-500ms) acceptable for snapshot visualization

**Important**: Run in standard Jupyter Notebook (browser), not VS Code's Jupyter extension. The 3D preview requires a browser environment.

### Render Command (`sine render`)

Static rendering to image file:
```bash
uv run sine render <topology.yaml> -o output.png [options]
```

Options: `--camera-position X,Y,Z`, `--look-at X,Y,Z`, `--clip-at Z`, `--resolution WxH`, `--num-samples N`, `--fov degrees`, `--no-paths`, `--no-devices`

### Creating Scene Files

Mitsuba XML scenes can be created with:

1. **Blender + Mitsuba add-on** - Model interactively, export to XML

2. **Hand-edit XML** - For simple modifications or custom geometries (see `scenes/vacuum.xml` and `scenes/two_rooms.xml` for examples)

Key requirement: Material names must use `itu_` prefix (e.g., `itu_concrete`, `itu_glass`)

## Migration Guides

### Antenna Configuration (Breaking Change in v2.0)

**BREAKING CHANGE**: `antenna_pattern` and `antenna_gain_dbi` are now mutually exclusive in wireless interface configurations.

#### Why This Change?

Sionna RT antenna patterns (iso, dipole, hw_dipole, tr38901) have built-in directional gains that are automatically included in path loss calculations. Specifying both `antenna_pattern` and `antenna_gain_dbi` caused confusion about which value was actually used and could lead to incorrect expectations about link performance.

#### BEFORE (v1.x)

```yaml
wireless:
  antenna_pattern: hw_dipole
  antenna_gain_dbi: 2.15  # IGNORED by Sionna RT!
```

Both fields were allowed, but `antenna_gain_dbi` was ignored when using Sionna RT, making configurations misleading.

#### AFTER (v2.0)

Choose ONE based on your use case:

**Option A: Use Sionna RT pattern (recommended for most scenarios)**
```yaml
wireless:
  antenna_pattern: hw_dipole  # Gain = 2.16 dBi (from Sionna's antenna pattern model)
  polarization: V
```

Use this when:
- Using standard antenna types (omnidirectional, dipole, etc.)
- Want directional radiation pattern modeling in Sionna RT
- Following WiFi 6 / 802.11ax typical configurations

**Option B: Use explicit gain (for custom antennas)**
```yaml
wireless:
  antenna_gain_dbi: 3.0  # Custom omnidirectional antenna with 3 dBi gain
  polarization: V
```

Use this when:
- Using custom antenna with specific gain not matching standard patterns
- Testing with specific gain values
- Using FSPL fallback mode (non-Sionna scenarios)

#### Antenna Pattern Gain Reference

| Pattern | Gain (dBi) | Description |
|---------|-----------|-------------|
| `iso` | 0.0 | Isotropic (ideal omnidirectional) |
| `dipole` | 1.76 | Short dipole |
| `hw_dipole` | 2.16 | Half-wavelength dipole (typical WiFi) |
| `tr38901` | 8.0 | 3GPP directional antenna (cellular) |

Values from Sionna RT v1.2.1 measurements.

#### Error Messages

If you specify both fields:
```
ValueError: Cannot specify both 'antenna_pattern' (hw_dipole) and 'antenna_gain_dbi' (2.15 dBi).
Choose ONE:
  - 'antenna_pattern' for Sionna RT (gain embedded in path coefficients)
  - 'antenna_gain_dbi' for explicit gain (custom antenna)
Using both causes double-counting of antenna gain.
```

If you specify neither:
```
ValueError: Wireless interface requires exactly one of:
  - 'antenna_pattern': Sionna RT pattern (iso/dipole/hw_dipole/tr38901)
  - 'antenna_gain_dbi': Explicit gain value (custom/fallback mode)
Specify one, but not both.
```

#### Migration Steps

1. **Review your topology**: Identify which antenna type you're using
2. **Standard antenna (iso/dipole/hw_dipole/tr38901)**:
   - Keep `antenna_pattern` field
   - Remove `antenna_gain_dbi` line entirely
3. **Custom antenna gain**:
   - Keep `antenna_gain_dbi` field
   - Remove `antenna_pattern` line entirely
4. **Validate**: Run `uv run sine validate <your_topology.yaml>`

#### Example Migration

**Before** (old network.yaml format):
```yaml
wireless:
  antenna_pattern: dipole
  polarization: V
  antenna_gain_dbi: 3.0  # Actually used dipole's 1.76 dBi, not 3.0!
```

**After** (choose closest match):
```yaml
wireless:
  antenna_pattern: hw_dipole  # 2.16 dBi, closest to intended 3.0 dBi
  polarization: V
```

Or use explicit gain if 3.0 dBi is critical:
```yaml
wireless:
  antenna_gain_dbi: 3.0  # Explicit 3.0 dBi custom antenna
  polarization: V
```

### SINR Flag Migration (v2.0)

**BREAKING CHANGE**: SINR computation now requires explicit `enable_sinr: true` flag.

#### Why This Change?

Previously, SINR (interference modeling) was implicitly enabled when MAC models (CSMA/TDMA) were configured. This coupling was not intuitive and limited flexibility. The new approach separates concerns: SINR computation is an explicit choice via `enable_sinr`, while MAC models only provide interference probability weights (`tx_probability`).

#### BEFORE (v1.x - implicit SINR via MAC model)

```yaml
nodes:
  node1:
    interfaces:
      eth1:
        wireless:
          csma:
            enabled: true  # Implicitly enabled SINR
```

SINR was automatically computed when CSMA or TDMA was configured.

#### AFTER (v2.0 - explicit flag)

```yaml
topology:
  enable_sinr: true  # Explicit SINR computation

nodes:
  node1:
    interfaces:
      eth1:
        wireless:
          csma:
            enabled: true  # Provides tx_probability only
```

**Key changes**:
- Add `topology.enable_sinr: true` to enable interference modeling
- MAC models (CSMA/TDMA) now only provide `tx_probability` weights
- TDMA slot multiplier affects throughput regardless of `enable_sinr` value

#### Migration Steps

1. Add `topology.enable_sinr: true` to all topologies using SINR/interference
2. Run `uv run sine validate <topology.yaml>` to verify
3. Test deployment to confirm SINR is computed

#### Examples Affected

All SINR examples have been updated:
- `shared_sionna_sinr_equal-triangle/`
- `shared_sionna_sinr_asym-triangle/`
- `shared_sionna_sinr_csma/`
- `shared_sionna_sinr_csma-mcs/`
- `shared_sionna_sinr_tdma-rr/`
- `shared_sionna_sinr_tdma-fixed/`

#### Warning Message

If you configure a MAC model without `enable_sinr: true`, you'll see:

```
WARNING: MAC model (CSMA/TDMA) configured with enable_sinr=false.
Interference modeling: DISABLED (SNR computed, not SINR).
Throughput effects: ENABLED (TDMA slot multiplier, CSMA metadata).
Set 'topology.enable_sinr: true' to enable interference modeling.
```

This is valid - it allows testing TDMA capacity sharing without interference complexity.

## FAQ - Frequently Asked Questions

### How does netem work with wireless links?

**Q: Is netem set per-link or per-interface?**

A: Netem is configured **per-interface**. In SiNE, we apply netem to the `eth1` interface on each container node. Netem only affects **egress (outbound) traffic** - packets leaving the interface.

**Q: Does netem affect both directions of traffic?**

A: Netem only affects **outbound** traffic on the interface where it's configured. For **point-to-point (P2P) wireless links**, SiNE computes channel conditions independently for each direction using the **receiver's noise figure**:

```
Node1 → Node2: Netem on Node1's eth1 (computed using Node2's RX noise figure)
Node2 → Node1: Netem on Node2's eth1 (computed using Node1's RX noise figure)
```

This means:
- Packets leaving Node1 experience Node1's netem (computed with Node2's NF)
- Packets leaving Node2 experience Node2's netem (computed with Node1's NF)
- For nodes with different noise figures, each direction will have different SNR, loss%, and rate
- Delay is symmetric (same geometric path), but loss and rate can be asymmetric
- Incoming packets are NOT affected by the receiving node's netem

**For shared bridge mode**, per-destination tc flower filters apply different netem parameters to packets based on destination IP address, which already implements bidirectional computation correctly.

**Q: If both interfaces have rate limits, what's the effective throughput?**

A: Each direction is independently limited by its own interface's netem. For symmetric configuration (same params on both sides):
- **TCP throughput**: Limited to the rate limit (e.g., 192 Mbps), with round-trip delay = 2× one-way delay (for ACKs)
- **UDP throughput**: Each direction independently limited to the configured rate

The link is effectively bottlenecked by the egress netem on the sending side for each direction.

### Containerlab Bridge Architecture

**Q: How are containers connected?**

A: Containerlab uses a **Linux bridge** to connect containers (not direct veth pairs). This provides scalability and flexibility for complex topologies. The bridge adds negligible latency (~1-10 μs) compared to wireless delays being emulated (0.1-10+ ms), making the overhead insignificant for network emulation purposes.

### Channel updates and netem synchronization

**Q: When link conditions change, does SiNE update netem on both nodes?**

A: Yes. When channel conditions are recomputed (due to mobility, initial deployment, etc.), SiNE updates netem on **both** endpoints of each link.

**For P2P links**: Each direction is computed independently with the correct receiver's noise figure, so the two interfaces may receive different parameters (asymmetric for heterogeneous receivers). The update happens atomically for each interface but sequentially between interfaces.

**For shared bridge mode**: All directional links are recomputed, and per-destination tc filters are updated with the new parameters for each destination.

## MANET Support

SiNE supports Mobile Ad-hoc Network (MANET) topologies using a **point-to-point link model**.

### Point-to-Point Model (Current Implementation)

Each wireless link is a separate veth pair with independent netem configuration:

```
           node1 (0,0,1)
            /  \
         eth1  eth2         ← Each node has multiple interfaces
          /      \
       eth1      eth1
        /          \
     node2 -------- node3
   (10,0,1)  eth2   (5,8.66,1)
```

**Key characteristics:**
- Each node has N-1 interfaces for N nodes in a fully-connected mesh
- Interface mapping: `ContainerlabManager` tracks `(node, peer) → interface`
- Independent channel computation per link (based on distance, scene geometry)
- Netem applied per-interface based on specific link's channel conditions

**Pros:**
- Simple implementation using existing containerlab link model
- Each link can have different channel conditions (accurate for directional scenarios)
- Easy to understand and debug
- Works well for testing MANET routing protocols

**Cons:**
- Not a true broadcast medium (no shared channel contention)
- Hidden node problem not naturally modeled
- Multiple interfaces per node (real MANETs typically use single interface)

### Interface Configuration Format

Each node defines its interfaces with either `wireless` or `fixed_netem` parameters:

```yaml
nodes:
  node1:
    kind: linux
    image: alpine:latest
    interfaces:
      eth1:
        wireless:
          position: {x: 0, y: 0, z: 1}
          frequency_ghz: 5.18
          # ... other wireless params
      eth2:
        wireless:
          position: {x: 0, y: 0, z: 1}
          # ... wireless params for another link

links:
  - endpoints: [node1:eth1, node2:eth1]
  - endpoints: [node1:eth2, node3:eth1]
```

Benefits:
- **Explicit**: No auto-assignment magic, topology is self-documenting
- **Predictable**: You know exactly which interface connects to which peer
- **Readable**: IP configuration matches interface names in the YAML
- **Conflict detection**: Schema validates that no interface is used twice
- **Type safety**: Each interface must have exactly one of `wireless` or `fixed_netem`

### Noise Figure Configuration

The receiver noise figure can be configured at both node and interface levels:

**Node-level default (optional)**:
```yaml
nodes:
  node1:
    noise_figure_db: 6.0  # Default for all interfaces on this node
    interfaces:
      eth1:
        wireless:
          # Uses node-level default (6.0 dB)
          position: {x: 0, y: 0, z: 1}
          # ... other params
```

**Interface-level override (recommended)**:
```yaml
nodes:
  node1:
    interfaces:
      eth1:
        wireless:
          noise_figure_db: 7.0  # Per-interface value
          position: {x: 0, y: 0, z: 1}
          # ... other params
```

**Typical values**:
- **WiFi 6 (consumer)**: 6-8 dB (default: 7.0 dB)
- **5G base station**: 3-5 dB
- **High-performance SDR**: 2-4 dB
- **Low-cost IoT radio**: 8-12 dB

**Validation**: Range [0.0, 20.0] dB

**Impact on channel**:
- Noise figure increases the thermal noise floor
- Higher NF → lower SNR → higher packet loss
- 3 dB increase in NF = 3 dB decrease in SNR

**Important: Bidirectional computation for P2P links**:
- Each direction uses its **receiver's** noise figure
- Link from node1→node2 uses node2's NF (receiver)
- Link from node2→node1 uses node1's NF (receiver)
- This results in **asymmetric SNR and loss rates** for heterogeneous receivers
- Example: WiFi node (7 dB NF) ↔ IoT node (10 dB NF) will have ~3 dB SNR difference between directions

**Example: Heterogeneous network**:
```yaml
nodes:
  wifi_node:
    interfaces:
      eth1:
        wireless:
          noise_figure_db: 7.0  # WiFi 6 typical
          # ... other params
  iot_node:
    interfaces:
      eth1:
        wireless:
          noise_figure_db: 10.0  # Cheap IoT radio
          # ... other params
```

### Interface Mapping for MANET

For topologies with 3+ nodes, SiNE tracks which interface connects to which peer via `ContainerlabManager._interface_mapping`. This allows the controller to apply the correct netem parameters to each interface based on the link endpoint.

### MANET Examples

- **Shared bridge (SNR)**: `examples/for_tests/shared_sionna_snr_equal-triangle/` (broadcast domain with per-destination tc filters)
- **Shared bridge (SINR)**: `examples/for_tests/shared_sionna_sinr_equal-triangle/` (with interference modeling)
- **Multi-radio**: `examples/for_tests/shared_sionna_snr_dual-band/` (dual-band 2.4 GHz + 5 GHz per node)

### Shared Bridge Model (Implemented)

The shared bridge model provides a true broadcast medium:
- Supports multiple interfaces per node (e.g., dual-band radios) as of Feb 2026
- All nodes "hear" all transmissions
- Per-destination tc flower filters apply channel-specific netem rules
- Supports hidden node modeling

### Routing Configuration for Shared Bridge

For shared bridge topologies, SiNE automatically configures routing so that traffic to the bridge subnet uses the correct interface (eth1) rather than the default Docker route (eth0). This ensures packets traverse the bridge where netem and tc filters are applied.

## Fixed Netem Links

SiNE supports **fixed netem links** for non-wireless link emulation where you specify netem parameters directly instead of computing them via ray tracing.

### When to Use Fixed Netem

- Simulating wired links with specific characteristics
- Testing applications with known/fixed link parameters
- Quick prototyping without setting up a scene file
- Mixed topologies with wireless and wired segments

### Configuration

```yaml
nodes:
  node1:
    kind: linux
    image: alpine:latest
    interfaces:
      eth1:
        fixed_netem:
          delay_ms: 10.0          # One-way delay
          jitter_ms: 1.0          # Delay variation
          loss_percent: 0.1       # Packet loss probability
          rate_mbps: 100.0        # Bandwidth limit
          correlation_percent: 25.0  # Loss correlation (optional, default: 25)

  node2:
    kind: linux
    image: alpine:latest
    interfaces:
      eth1:
        fixed_netem:
          delay_ms: 10.0          # Same params for symmetric link
          jitter_ms: 1.0
          loss_percent: 0.1
          rate_mbps: 100.0

topology:
  # No scene needed for fixed-only topologies
  links:
    - endpoints: [node1:eth1, node2:eth1]
```

### Key Points

- **No channel server required**: Fixed links don't use ray tracing
- **No scene file required**: Scene is optional for topologies with only fixed links
- **Per-endpoint params**: Each side can have different netem values (asymmetric links)
- **Mixed not allowed**: A single link cannot have one wireless and one fixed_netem endpoint

### Example

See `examples/for_user/fixed_link/network.yaml` for a complete fixed netem example.

## Adaptive MCS Selection

SiNE supports **adaptive MCS (Modulation and Coding Scheme) selection** similar to WiFi 6 (802.11ax). The system automatically selects the optimal modulation and coding based on current SNR conditions.

### How It Works

1. **MCS Table**: A CSV file defines available MCS options with SNR thresholds
2. **SNR-Based Selection**: After ray tracing computes SNR, the highest MCS where SNR ≥ min_snr_db is selected
3. **Hysteresis**: Prevents rapid MCS switching by requiring extra SNR margin to upgrade

### MCS Table Format

```csv
mcs_index,modulation,code_rate,min_snr_db,fec_type,bandwidth_mhz
0,bpsk,0.5,5.0,ldpc,80
1,qpsk,0.5,8.0,ldpc,80
2,qpsk,0.75,11.0,ldpc,80
3,16qam,0.5,14.0,ldpc,80
4,16qam,0.75,17.0,ldpc,80
5,64qam,0.667,20.0,ldpc,80
6,64qam,0.75,23.0,ldpc,80
7,64qam,0.833,26.0,ldpc,80
8,256qam,0.75,29.0,ldpc,80
9,256qam,0.833,32.0,ldpc,80
10,1024qam,0.75,35.0,ldpc,80
11,1024qam,0.833,38.0,ldpc,80
```

**Required columns:**
- `mcs_index`: MCS index (integer, must be unique)
- `modulation`: bpsk, qpsk, 16qam, 64qam, 256qam, 1024qam
- `code_rate`: FEC code rate (0.0 to 1.0)
- `min_snr_db`: Minimum SNR threshold for this MCS

**Optional columns:**
- `fec_type`: FEC type (ldpc, polar, turbo, none) - defaults to ldpc
- `bandwidth_mhz`: Channel bandwidth - for documentation/reference

### Configuration

Wireless interfaces must specify **either** an MCS table **or** fixed modulation/FEC parameters:

**Option 1: Adaptive MCS (recommended)**
```yaml
nodes:
  node1:
    interfaces:
      eth1:
        wireless:
          mcs_table: examples/common_data/wifi6_mcs.csv
          mcs_hysteresis_db: 2.0    # Optional, default: 2.0 dB
          rf_power_dbm: 20.0
          frequency_ghz: 5.18
          bandwidth_mhz: 80
          # ... other params
```

**Option 2: Fixed modulation/FEC**
```yaml
nodes:
  node1:
    interfaces:
      eth1:
        wireless:
          modulation: 64qam
          fec_type: ldpc
          fec_code_rate: 0.5
          rf_power_dbm: 20.0
          frequency_ghz: 5.18
          bandwidth_mhz: 80
          # ... other params
```

**Important**: If neither `mcs_table` nor explicit `modulation`/`fec_type`/`fec_code_rate` are provided, validation will fail. There are no defaults.

### Hysteresis Behavior

Hysteresis prevents rapid MCS switching when SNR fluctuates near thresholds:

- **Upgrade**: To move to a higher MCS, SNR must exceed threshold by `mcs_hysteresis_db`
- **Downgrade**: Immediate when SNR drops below current MCS threshold
- **Per-link tracking**: Each link maintains its current MCS index

Example with 2 dB hysteresis:
- Currently at MCS 5 (min_snr=20 dB), MCS 6 threshold is 23 dB
- To upgrade to MCS 6: SNR must be ≥ 25 dB (23 + 2)
- To stay at MCS 5: SNR can be 20-24.99 dB
- To downgrade: SNR < 20 dB

### Deployment Output

When using adaptive MCS, the deployment summary shows selected MCS info:

```
Link Parameters:
  node1:eth1 ↔ node2:eth1 [wireless]
    MCS: 11 (1024qam, rate-0.833, ldpc)
    Delay: 0.07 ms | Jitter: 0.00 ms | Loss: 0.00% | Rate: 532.5 Mbps
```

### Example

See `examples/for_user/adaptive_mcs_wifi6/` for a complete example with deployment and throughput testing instructions.

### Data Rate Calculation with MCS

With adaptive MCS, the data rate is computed from the selected MCS entry:

```
Rate (Mbps) = bandwidth_mhz × bits_per_symbol × code_rate × efficiency

Example (MCS 11: 80 MHz, 1024-QAM, rate-5/6):
= 80 × 10 × 0.833 × 0.8 = 533 Mbps
```

Where:
- `bits_per_symbol`: From modulation (bpsk=1, qpsk=2, 16qam=4, 64qam=6, 256qam=8, 1024qam=10)
- `code_rate`: FEC code rate from MCS table
- `efficiency`: 0.8 (accounts for protocol overhead)

## MAC Protocol Support

SiNE supports modeling interference for different Medium Access Control (MAC) protocols. MAC configuration is specified per-interface in the wireless parameters and affects both throughput (slot ownership) and interference probability when SINR is enabled.

### TDMA (Time Division Multiple Access)

For TDMA networks, each node transmits during assigned time slots. When `enable_sinr: true`, interference is weighted by the probability that each interferer is transmitting when the receiver is listening.

**Configuration** (per-interface):
```yaml
topology:
  enable_sinr: true  # Enable interference modeling

nodes:
  node1:
    interfaces:
      eth1:
        wireless:
          frequency_ghz: 5.18
          bandwidth_mhz: 80
          rf_power_dbm: 20.0
          antenna_pattern: hw_dipole
          modulation: 64qam
          fec_type: ldpc
          fec_code_rate: 0.667

          tdma:
            enabled: true
            frame_duration_ms: 10.0
            num_slots: 10
            slot_assignment_mode: fixed
            fixed_slot_map:
              node1: [0, 1, 2]  # Owns 30% of slots
              node2: [3, 4, 5]
              node3: [6, 7, 8, 9]
```

**How it works**:
- SiNE automatically calculates `tx_probability` from slot ownership (e.g., 3/10 slots = 0.3)
- Throughput is scaled by slot ownership regardless of `enable_sinr` setting
- When SINR enabled: Interference weighted by `tx_probability`

**Examples**:
- `shared_sionna_sinr_tdma-rr/`: Round-robin TDMA (equal slot allocation)
- `shared_sionna_sinr_tdma-fixed/`: Custom TDMA schedule with different slot allocations

**SINR Formula**:
```
SINR = Signal / (Noise + Σ(Interference_i × tx_probability_i))
```

### CSMA/CA (Carrier Sense Multiple Access with Collision Avoidance)

For CSMA/CA networks (e.g., WiFi), nodes sense the channel before transmitting. Transmission probability depends on network load, contention, and carrier sensing.

**Configuration** (per-interface):
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
          antenna_pattern: iso
          mcs_table: examples/common_data/wifi6_mcs.csv

          csma:
            enabled: true
            carrier_sense_range_multiplier: 2.5  # CS range = 2.5× comm range
            traffic_load: 0.3                    # 30% duty cycle
            communication_range_snr_threshold_db: 40.4
```

**How it works**:
- SiNE calculates `tx_probability` based on traffic load and carrier sensing
- Hidden node problem modeled: Nodes outside CS range contribute full interference
- Carrier sense range computed from communication range and multiplier

**Examples**:
- `examples/for_tests/shared_sionna_sinr_csma-mcs/`: CSMA/CA with adaptive MCS (SINR mode, hidden node test)
- `examples/for_tests/shared_sionna_sinr_csma/`: CSMA with SINR (SINR mode)

**Considerations**:
- Hidden node problem: Adjacent-channel interferers may not be detected by carrier sensing
- Transmission probability varies with load and number of contending nodes
- Typical values: 0.1-0.4 for moderate load, 0.5+ for heavy congestion

### Active/Inactive Nodes

Individual wireless interfaces can be enabled/disabled for interference calculations:

**Configuration** (per-interface):
```yaml
nodes:
  node1:
    interfaces:
      eth1:
        wireless:
          is_active: true   # Participates in interference (default)
          frequency_ghz: 5.18

  node2:
    interfaces:
      eth1:
        wireless:
          is_active: false  # Excluded from interference calculations
          frequency_ghz: 5.18

  dual_band_node:
    interfaces:
      eth1:
        wireless:
          is_active: true   # 5 GHz active
          frequency_ghz: 5.18
      eth2:
        wireless:
          is_active: false  # 2.4 GHz disabled
          frequency_ghz: 2.4
```

**Use cases**:
- Node failures or power-saving modes
- Dynamic network topologies
- Duty-cycled sensor networks
- Band-specific power management
- Listen-only monitoring nodes (RX active, TX disabled)

## SINR Configuration

SiNE supports explicit SINR (Signal-to-Interference-plus-Noise Ratio) computation via the `enable_sinr` flag.

**Configuration**:
```yaml
topology:
  enable_sinr: true  # Enable interference modeling
  scene:
    file: scenes/vacuum.xml
```

**Behavior**:
| enable_sinr | MAC model | Interference (SINR) | MAC Throughput Effects |
|-------------|-----------|---------------------|------------------------|
| false | None | ❌ No | ❌ No (full PHY rate) |
| false | CSMA | ❌ No | ✅ Metadata available |
| false | TDMA | ❌ No | ✅ **Slot multiplier applied** |
| true | None | ✅ Yes (tx_prob=1.0) | ❌ No (full PHY rate) |
| true | CSMA | ✅ Yes (carrier sense) | ✅ Metadata available |
| true | TDMA | ✅ Yes (slot-weighted) | ✅ **Slot multiplier applied** |

**MAC Model Independence**: MAC models affect throughput regardless of `enable_sinr`:
- **TDMA**: Slot ownership multiplier always applied (e.g., 3/10 slots → 0.3× PHY rate)
- **CSMA**: Contention metadata available (for future capacity modeling)
- **enable_sinr**: Only controls whether interference affects SNR calculation

**Worst-case scenario** (`enable_sinr: true`, no MAC model):
- All interferers assumed to transmit continuously (`tx_probability = 1.0`)
- Conservative assumption for interference analysis
- Use case: Beacon-heavy networks, continuous transmitters

**TDMA without SINR** (`enable_sinr: false`, TDMA configured):
- SNR computed (no interference modeling)
- Throughput scaled by slot ownership (e.g., 20% of slots → 0.2× PHY rate)
- Use case: Testing TDMA capacity sharing without interference complexity

**Active states** (per-interface control):
```yaml
nodes:
  node1:
    interfaces:
      eth1:
        wireless:
          is_active: true   # Default: participates in interference
          frequency_ghz: 5.18
  node2:
    interfaces:
      eth1:
        wireless:
          is_active: false  # Excluded from interference calculations
          frequency_ghz: 5.18
  dual_band_node:
    interfaces:
      eth1:
        wireless:
          is_active: true   # 5 GHz active
          frequency_ghz: 5.18
      eth2:
        wireless:
          is_active: false  # 2.4 GHz disabled
          frequency_ghz: 2.4
```

Use `is_active: false` to simulate:
- Powered-off radios
- Sleep modes (radio-specific)
- Hardware failures
- Disabled frequency bands
- Selective multi-radio operation
- Listen-only monitoring nodes (RX active, TX disabled)

## Node Mobility

SiNE supports real-time position updates with automatic channel recomputation, enabling dynamic wireless network scenarios.

### Mobility Architecture

**Polling-based updates:**
- Control API runs on port 8002 (separate from channel server on port 8000)
- Position updates trigger channel recomputation via channel server
- Netem parameters updated on both endpoints of affected links
- Default poll interval: 100ms (configurable via `control_poll_ms` in topology YAML)

**Channel recomputation:**
- Uses same pipeline as initial deployment (ray tracing → SNR → BER/BLER → PER → netem)
- Only affected links are recomputed (not entire topology)
- Bidirectional: both TX and RX netem updated for each link

### Enabling Mobility

**Deploy with control API:**
```bash
# Start channel server
uv run sine channel-server

# Deploy with control API enabled
UV_PATH=$(which uv) sudo -E $(which uv) run sine deploy --enable-control examples/for_tests/p2p_sionna_snr_two-rooms/network.yaml

# Control API now running on http://localhost:8002
```

### Control API Endpoints (Mobility)

**Update node position:**
```bash
curl -X POST http://localhost:8002/api/control/update \
     -H "Content-Type: application/json" \
     -d '{
       "node": "node2",
       "x": 10.0,
       "y": 5.0,
       "z": 1.5
     }'
```

**Get current positions:**
```bash
curl http://localhost:8002/api/control/position/node2
```

**Response:**
```json
{
  "node1": {"x": 0.0, "y": 0.0, "z": 1.0},
  "node2": {"x": 10.0, "y": 5.0, "z": 1.5}
}
```

### Mobility Scripts

SiNE includes movement scripts in `examples/for_user/mobility/`:

**Linear movement:**
```bash
# Move node2 from (30,1,1) to (30,40,1) over 10 seconds
uv run python examples/for_user/mobility/linear_movement.py \
    node2 30.0 1.0 1.0 30.0 40.0 1.0 10.0
```

**Circular path:**
```bash
# Move node2 in a circle around origin
uv run python examples/for_user/mobility/circular_movement.py \
    node2 5.0 1.0 10.0
# Arguments: <node> <radius> <height> <duration_sec>
```

**Random walk:**
```bash
# Random walk within bounds
uv run python examples/for_user/mobility/random_walk.py \
    node2 0.0 0.0 20.0 20.0 30.0
# Arguments: <node> <min_x> <min_y> <max_x> <max_y> <duration_sec>
```

### Mobility Configuration

**Topology YAML:**
```yaml
topology:
  control_poll_ms: 100  # Control API polling interval (default: 100ms)
  channel_server: "http://localhost:8000"
```

**Poll interval considerations:**
- **100ms (default)**: Good balance for walking/vehicle speeds
- **50ms**: High-speed scenarios (UAVs, fast vehicles)
- **200-500ms**: Slow-moving nodes, reduced overhead

### Use Cases

**Walking pedestrians:**
- Speed: 1-2 m/s
- Poll interval: 100-200ms (moves 10-40cm between updates)
- Example: Indoor navigation, crowd mobility

**Vehicular networks:**
- Speed: 10-30 m/s (36-108 km/h)
- Poll interval: 50-100ms (moves 0.5-3m between updates)
- Example: V2V communication, convoy scenarios

**UAV/drone networks:**
- Speed: 5-20 m/s
- Poll interval: 50ms (moves 0.25-1m between updates)
- Example: Aerial mesh networks, search patterns

**Robotic swarms:**
- Speed: 0.5-5 m/s
- Poll interval: 100-200ms
- Example: Warehouse automation, formation control

### Visualization with Mobility

Use the live viewer to monitor moving nodes in real-time:

```bash
# 1. Deploy with control API
UV_PATH=$(which uv) sudo -E $(which uv) run sine deploy --enable-control examples/for_tests/p2p_sionna_snr_two-rooms/network.yaml

# 2. Start mobility script
uv run python examples/for_user/mobility/linear_movement.py node2 0.0 0.0 1.0 20.0 0.0 1.0 30.0 &

# 3. Open live viewer
uv run --with jupyter jupyter notebook scenes/viewer_live.ipynb

# 4. In notebook, run continuous monitoring (Cell 7)
await continuous_monitoring(update_interval_sec=1.0, max_iterations=60)
```

The viewer shows:
- Updated node positions in 3D scene
- Real-time channel metrics (SNR, delay spread, K-factor)
- Propagation paths (recomputed as nodes move)

### Performance Considerations

**Channel computation overhead:**
- Ray tracing: ~10-100ms per link (GPU: ~10-30ms, CPU: ~50-100ms)
- For N-node mesh: O(N²) link updates per position change
- Recommend: Use shared bridge mode for large topologies (single interface per node)

**Netem update latency:**
- Netem reconfiguration: ~1-5ms per interface
- Negligible compared to channel computation time
- Applied immediately after computation

**Example timing (3-node mesh, GPU):**
- Single node moves → 2 links affected
- Ray tracing: 2 × 15ms = 30ms
- Netem updates: 2 × 2ms = 4ms
- Total: ~34ms (well within 100ms poll interval)

### Limitations

- **No interpolation:** Channel updated only at poll intervals (discrete updates)
- **No prediction:** No extrapolation of movement trajectories
- **Synchronous updates:** All affected links recomputed before next poll
- **No handover modeling:** Link-layer handover protocols not modeled

For continuous channel variation, reduce poll interval or implement custom interpolation in mobility scripts.

### Example: Walking Through Doorway

```python
# examples/for_user/mobility/doorway_crossing.py
import requests
import time

API_URL = "http://localhost:8002/api/control/update"

# Start in room 1 (LOS blocked)
positions = [
    (0.0, 0.0, 1.0),    # Room 1
    (2.5, 1.5, 1.0),    # Approaching doorway
    (5.0, 2.5, 1.0),    # In doorway (LOS established)
    (7.5, 2.5, 1.0),    # Through doorway
    (10.0, 2.5, 1.0),   # Room 2 (LOS maintained)
]

for x, y, z in positions:
    requests.post(API_URL, json={"node": "node2", "x": x, "y": y, "z": z})
    print(f"Moved to ({x}, {y}, {z})")
    time.sleep(2.0)  # Wait for channel update
```

Expected behavior:
- Rooms 1 and 2: NLOS, higher path loss, lower SNR
- Doorway: LOS path appears, path loss drops, SNR increases
- Throughput increases as node crosses doorway (MCS adapts to higher SNR)

## Test Organization

SiNE's test suite is organized by test type and functionality. See [tests/README.md](tests/README.md) for comprehensive documentation.

### Directory Structure

```
tests/
├── unit/                          # Unit tests (fast, no external dependencies)
│   ├── channel/                   # Channel computation tests
│   ├── engine/                    # Engine comparison tests
│   ├── protocols/                 # Protocol logic tests
│   ├── config/                    # Configuration validation tests
│   └── server/                    # Server logic tests
├── integration/                   # Integration tests (require sudo)
│   ├── point_to_point/            # P2P topology tests
│   │   ├── sionna_engine/snr/     # Sionna P2P SNR tests
│   │   ├── sionna_engine/sinr/    # Sionna P2P SINR tests
│   │   └── fallback_engine/snr/   # Fallback P2P tests
│   ├── shared_bridge/             # MANET tests
│   │   └── sionna_engine/snr/     # MANET SNR tests
│   ├── cross_cutting/             # Tests affecting multiple modes
│   ├── fixtures.py                # Shared integration test fixtures
│   └── conftest.py                # Integration-specific pytest config
└── conftest.py                    # Root pytest configuration
```

### Test Categories

**Unit Tests** (`tests/unit/`):
- Channel computation (SNR, BER, BLER, PER, MCS)
- Engine comparison (Sionna vs Fallback)
- Protocol logic (SINR, interference, CSMA, TDMA)
- Configuration validation
- Fast execution, no external dependencies

**Integration Tests** (`tests/integration/`):
- Full deployment with containerlab + netem
- Organized by topology/engine/interference mode
- Requires sudo for netem and container namespace access
- Uses examples from `examples/for_tests/`

### Running Tests

```bash
# Unit tests (no sudo)
uv run pytest tests/unit/ -v

# Integration tests (requires sudo)
UV_PATH=$(which uv) sudo -E $(which uv) run pytest tests/integration/ -v -s

# Specific category
uv run pytest tests/unit/channel/ -v
UV_PATH=$(which uv) sudo -E $(which uv) run pytest tests/integration/point_to_point/ -v -s
```

### Pytest Markers

Use markers to selectively run tests:

| Marker | Description |
|--------|-------------|
| `integration` | Full deployment tests (require sudo) |
| `slow` | Tests taking 5-60 seconds |
| `very_slow` | Tests taking >60 seconds |
| `sionna` | Tests requiring Sionna/GPU |
| `fallback` | Tests using fallback engine |
| `gpu_memory_8gb` | Tests requiring 8GB+ GPU memory |
| `gpu_memory_16gb` | Tests requiring 16GB+ GPU memory |

**Examples:**
```bash
# Fast tests only
uv run pytest -m "not slow and not very_slow" -v

# Sionna tests only
uv run pytest -m sionna -v

# Skip GPU tests
uv run pytest -m "not sionna" -v
```

### Test Fixtures

**Root fixtures** ([tests/conftest.py](tests/conftest.py)):
- `project_root` - Path to project root
- `examples_dir` - Path to examples/ (deprecated, use specific fixtures)
- `scenes_dir` - Path to scenes/

**Integration fixtures** ([tests/integration/conftest.py](tests/integration/conftest.py)):
- `examples_for_user` - Path to examples/for_user/
- `examples_for_tests` - Path to examples/for_tests/
- `examples_common` - Path to examples/common_data/

**Integration helpers** ([tests/integration/fixtures.py](tests/integration/fixtures.py)):
- `channel_server` - Session-scoped fixture (starts/stops server)
- `deploy_topology()` - Deploy topology helper
- `destroy_topology()` - Cleanup helper
- `run_iperf3_test()` - Throughput testing helper

### Test Examples Organization

Integration tests use `examples/for_tests/` with flat naming:

**Naming pattern:** `<topology>_<engine>_<interference>_<name>`

Examples:
- `p2p_fallback_snr_vacuum/` - Point-to-point, fallback, SNR, free space
- `p2p_sionna_snr_two-rooms/` - Point-to-point, Sionna, SNR, indoor
- `shared_sionna_snr_equal-triangle/` - Shared bridge, Sionna, SNR, 3-node
- `shared_sionna_sinr_equal-triangle/` - Shared bridge, Sionna, SINR, interference

**Benefits:**
- Grep-friendly: `grep -r "p2p_sionna" tests/`
- Self-documenting names
- No nested directory navigation

### Test Examples Organization (Phase 5 Refactoring - 2026-02-03)

**Flat Naming Pattern**: `examples/for_tests/` uses self-documenting flat structure:

```
<topology>_<engine>_<interference>_<description>
```

**Examples**:
- `p2p_fallback_snr_vacuum/` - Point-to-point, fallback engine, SNR, free space
- `p2p_sionna_snr_two-rooms/` - Point-to-point, Sionna, SNR, indoor
- `shared_sionna_snr_equal-triangle/` - Shared bridge, Sionna, SNR, 3-node
- `shared_sionna_sinr_equal-triangle/` - Shared bridge, Sionna, SINR, equilateral triangle
- `shared_sionna_sinr_asym-triangle/` - Shared bridge, Sionna, SINR, asymmetric triangle
- `shared_sionna_snr_dual-band/` - Shared bridge, dual-band (2.4 GHz + 5 GHz) per node

**Benefits**:
- Grep-friendly: `grep -r "p2p_sionna" examples/for_tests/`
- Self-documenting: topology, engine, and interference mode in directory name
- No nested navigation

**Deleted Directories** (Phase 5):
- `tests/e2e/` - Removed (unused placeholder)
- `tests/performance/` - Removed (unused placeholder)
- `tests/regression/` - Removed (unused placeholder)

### When to Write Each Type

- **Unit test**: Testing a single function/class in isolation
- **Integration test**: Testing full deployment with containerlab + netem
- **Marked test**: Add appropriate pytest markers for CI/CD filtering

### Test Development Guidelines

1. **Choose the right location:**
   - Channel computation? → `tests/unit/channel/`
   - Protocol behavior? → `tests/unit/protocols/`
   - Full deployment? → `tests/integration/<topology>/<engine>/<interference>/`

2. **Import and use fixtures:**
   ```python
   from tests.integration.fixtures import (
       channel_server,
       deploy_topology,
       destroy_topology,
   )

   @pytest.mark.integration
   def test_deployment(channel_server, examples_for_tests: Path):
       """The channel_server fixture ensures the server is running."""
       yaml_path = examples_for_tests / "p2p_fallback_snr_vacuum" / "network.yaml"
       ...
   ```

   **Important:** Include `channel_server` as a test parameter to ensure the channel server is started before your test runs. This is a session-scoped fixture that starts once and is shared across all integration tests.

3. **Mark appropriately:**
   ```python
   @pytest.mark.integration
   @pytest.mark.slow
   def test_my_deployment(channel_server, examples_for_tests: Path):
       ...
   ```

4. **Clean up in integration tests:**
   ```python
   @pytest.mark.integration
   def test_deployment(channel_server, examples_for_tests: Path):
       yaml_path = examples_for_tests / "p2p_fallback_snr_vacuum" / "network.yaml"
       try:
           deploy_topology(yaml_path)
           # ... test logic
       finally:
           destroy_topology(yaml_path)
   ```

### API Testing with FastAPI TestClient

```python
from fastapi.testclient import TestClient
from sine.channel.server import app

client = TestClient(app)
response = client.post("/compute/single", json={...})
assert response.status_code == 200
```

**Batch endpoint requirements:**
- Must include `scene` config (even if empty: `{"scene_file": ""}`)
- Each link can have different positions/params
- All links should use same `engine_type`

## Common Debugging Patterns

### Channel Server Not Responding
1. Check if server is running: `curl http://localhost:8000/health`
2. Check logs for Sionna import errors (GPU/CUDA issues)
3. Verify port not in use: `lsof -i :8000`

### Integration Test Failures
1. Check containers are cleaned up: `sudo docker ps -a | grep clab`
2. Manually destroy if needed: `sudo containerlab destroy -t <yaml> --cleanup`
3. Verify sudo permissions work: `sudo tc qdisc show`
4. Check UV_PATH is set correctly when using sudo

### Path Loss / SNR Unexpected Values
1. Verify frequency and distance are correct
2. Check antenna gains are not double-counted (Sionna: embedded, Fallback: added)
3. Confirm `from_sionna` flag matches engine type
4. For FSPL: Expected ~72 dB at 20m, 5.18 GHz (+ indoor loss if configured)

### Engine Selection Issues
- `engine_type="auto"`: Uses Sionna if available, else fallback
- `engine_type="sionna"`: Returns 503 if GPU unavailable
- `engine_type="fallback"`: Always works, no GPU needed
- `--force-fallback`: Server-wide mode, rejects explicit Sionna requests

### SINR Not Being Computed
1. Verify `topology.enable_sinr: true` is set
2. Check deployment logs for "SINR mode" confirmation
3. Verify at least 3+ nodes (need interferers)
4. Check logs for `tx_probability` values
5. For worst-case (no MAC model): expect `tx_probability=1.0`

### SINR vs SNR Values
- **SINR < SNR**: Interference present (expected)
- **SINR ≈ SNR**: No/low interference (check `is_active` states)
- **SINR = SNR**: `enable_sinr=false` (SNR-only mode)

### TDMA Throughput Not Applied
1. Verify TDMA configured with `enabled: true`
2. Check `fixed_slot_map` or `slot_probability` is set correctly
3. Verify slot ownership fraction (e.g., 3/10 slots = 0.3)
4. Check logs for rate multiplier application
5. Note: Throughput scaling applies regardless of `enable_sinr` value

## File Structure Quick Reference

### Channel Computation
- `src/sine/channel/sionna_engine.py`: SionnaEngine + FallbackEngine classes
- `src/sine/channel/server.py`: FastAPI endpoints, engine selection logic
- `src/sine/channel/snr.py`: SNR calculation, FSPL formulas
- `src/sine/channel/modulation.py`: BER/BLER calculation
- `src/sine/channel/per_calculator.py`: Packet error rate computation

### Configuration & Schema
- `src/sine/config/schema.py`: Network topology YAML schema validation
- `src/sine/config/loader.py`: YAML loading and parsing

### Deployment
- `src/sine/emulation/controller.py`: Main deployment orchestrator
- `src/sine/topology/manager.py`: ContainerlabManager - Containerlab integration
- `src/sine/topology/netem.py`: Network emulation configuration (point-to-point)
- `src/sine/topology/shared_netem.py`: Shared bridge netem configuration

### Tests
- `tests/unit/channel/`: Unit tests for channel computation
- `tests/unit/protocols/`: Unit tests for MAC protocols (SINR, TDMA, CSMA)
- `tests/integration/`: Full deployment tests (require sudo)
- `tests/conftest.py`: Shared fixtures (project_root, examples_dir, etc.)
