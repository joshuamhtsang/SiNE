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
| Mobility Poll | 100ms | Balance responsiveness vs overhead |
| Rate Limiting | tbf | netem lacks native rate control |
| Sionna API | PathSolver, Scene | Sionna v1.2.1 API (use `Scene()` for empty) |
| PER Formula | BLER for coded | Industry standard |
| Scene Config | Explicit file path | Required for wireless links, optional for fixed_netem links |
| Interface Config | Per-interface on node | Each interface has either `wireless` or `fixed_netem` params |
| netem Access | sudo nsenter | Required for container network namespace access |
| Container Naming | `clab-<lab>-<node>` | Follows containerlab convention for consistency |
| SINR Computation | ACLR-filtered | IEEE 802.11ax-2021 spectral mask for frequency-selective interference |
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
# Use full path to avoid "uv: command not found" error with sudo
sudo $(which uv) run sine deploy examples/vacuum_20m/network.yaml

# Deploy with mobility API enabled (for dynamic position updates)
sudo $(which uv) run sine deploy --enable-mobility examples/vacuum_20m/network.yaml

# Validate topology
uv run sine validate examples/vacuum_20m/network.yaml

# Render scene to image (does NOT require channel server)
uv run sine render examples/vacuum_20m/network.yaml -o scene.png

# Check system info
uv run sine info

# Show running containers
uv run sine status

# Destroy emulation
uv run sine destroy examples/vacuum_20m/network.yaml

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

### Basic Examples

| Example | Description | Link Type | Scene |
|---------|-------------|-----------|-------|
| `vacuum_20m/` | Baseline free-space wireless (2 nodes, 20m) | wireless | `vacuum.xml` |
| `fixed_link/` | Fixed netem parameters (no RF) | fixed_netem | (none) |
| `two_rooms/` | Indoor multipath (2 rooms with doorway) | wireless | `two_rooms.xml` |

### Adaptive MCS Examples

| Example | Description | MAC Protocol | Features |
|---------|-------------|--------------|----------|
| `adaptive_mcs_wifi6/` | WiFi 6 MCS selection (2 nodes) | N/A | SNR-based adaptive modulation |
| `csma_mcs_test/` | CSMA/CA with adaptive MCS | CSMA/CA | Carrier sensing, MCS adaptation |
| `sinr_csma/` | CSMA with SINR (3+ nodes) | CSMA/CA | Interference-aware MCS |

### SINR/Interference Examples

| Example | Description | MAC Protocol | Interference Model |
|---------|-------------|--------------|-------------------|
| `manet_triangle_shared/` | 3-node MANET, shared bridge | N/A | Point-to-point links |
| `manet_triangle_shared_sinr/` | 3-node MANET with SINR | N/A | Co-channel interference |
| `sinr_tdma_roundrobin/` | Round-robin TDMA (equal slots) | TDMA | Probability-weighted (20% each) |
| `sinr_tdma_fixed/` | Fixed TDMA schedule | TDMA | Per-node slot assignments |

### Mobility Examples

| Example | Description | Features |
|---------|-------------|----------|
| `mobility/` | Movement scripts and API examples | Dynamic position updates, API endpoints |

The examples demonstrate:
- **Free-space propagation** (`vacuum_20m/`)
- **Indoor multipath** (`two_rooms/`)
- **Adaptive modulation** (`adaptive_mcs_wifi6/`, `csma_mcs_test/`)
- **MANET broadcast domains** (`manet_triangle_shared/`)
- **Fixed link emulation** (`fixed_link/`)
- **Node mobility** (`mobility/`)
- **SINR computation** (`manet_triangle_shared_sinr/`, `sinr_csma/`, `sinr_tdma_*`)
- **MAC protocols** (CSMA/CA, TDMA)

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

Computes Signal-to-Interference-plus-Noise Ratio for multi-node scenarios with ACLR filtering:

**Request**:
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
      "frequency_hz": 5.28e9,
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
  "sinr_db": 24.5,
  "snr_db": 28.3,
  "signal_power_dbm": -65.2,
  "noise_power_dbm": -93.5,
  "interference_power_dbm": -89.8,
  "interference_terms": [
    {
      "node_name": "node3",
      "power_dbm": -89.8,
      "path_loss_db": 72.0,
      "frequency_separation_hz": 100e6,
      "aclr_db": 40.0
    }
  ]
}
```

**ACLR Filtering**: Automatically applies IEEE 802.11ax spectral mask based on frequency separation and bandwidth.

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
- Noise_floor: Thermal noise = -174 dBm/Hz + 10*log10(bandwidth)
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
                    BER (from modulation)    SINR (with ACLR)
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
- Multi-node scenarios automatically compute SINR with IEEE 802.11ax-2021 ACLR filtering
- Orthogonal channels (>120 MHz separation for 80 MHz BW) are automatically filtered

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
sudo $(which uv) run sine deploy examples/two_rooms/network.yaml

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

1. **Scene Generator Script** (`scenes/generate_room.py`) - Generate two-room layouts:
   ```bash
   # Default 5x4x2.5m rooms
   uv run python scenes/generate_room.py -o scenes/my_scene.xml

   # Custom sizes
   uv run python scenes/generate_room.py -o scenes/large.xml \
       --room1-size 10,8,3 --room2-size 10,8,3 --door-width 1.5

   # See all options
   uv run python scenes/generate_room.py --help
   ```

2. **Blender + Mitsuba add-on** - Model interactively, export to XML

3. **Hand-edit XML** - For simple modifications or custom geometries

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

**Before** (manet_triangle_shared/network.yaml):
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

## FAQ - Frequently Asked Questions

### How does netem work with wireless links?

**Q: Is netem set per-link or per-interface?**

A: Netem is configured **per-interface**. In SiNE, we apply netem to the `eth1` interface on each container node. Netem only affects **egress (outbound) traffic** - packets leaving the interface.

**Q: Does netem affect both directions of traffic?**

A: Netem only affects **outbound** traffic on the interface where it's configured. For bidirectional wireless links, SiNE applies netem to `eth1` on **both** nodes:

```
Node1 → Node2: Affected by netem on Node1's eth1 (egress)
Node2 → Node1: Affected by netem on Node2's eth1 (egress)
```

This means:
- Packets leaving Node1 experience Node1's netem (delay, jitter, loss, rate)
- Packets leaving Node2 experience Node2's netem (delay, jitter, loss, rate)
- Incoming packets are NOT affected by the receiving node's netem

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

A: Yes. When channel conditions are recomputed (due to mobility, initial deployment, etc.), SiNE updates netem on **both** endpoints of each link. Both interfaces receive the same parameters (symmetric link). The update happens atomically for each interface but sequentially between interfaces.

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

### Interface Mapping for MANET

For topologies with 3+ nodes, SiNE tracks which interface connects to which peer via `ContainerlabManager._interface_mapping`. This allows the controller to apply the correct netem parameters to each interface based on the link endpoint.

### MANET Examples

- **Shared bridge**: `examples/manet_triangle_shared/` (broadcast domain with per-destination tc filters)
- **Shared bridge + SINR**: `examples/manet_triangle_shared_sinr/` (with interference modeling)

### Shared Bridge Model (Implemented)

The shared bridge model provides a true broadcast medium:
- Single interface per node (like real MANETs)
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

See `examples/fixed_link/network.yaml` for a complete fixed netem example.

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
          mcs_table: examples/wifi6_adaptive/data/wifi6_mcs.csv
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

See `examples/adaptive_mcs_wifi6/` for a complete example with deployment and throughput testing instructions.

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

SiNE supports modeling interference for different Medium Access Control (MAC) protocols through transmission probability parameters.

### TDMA (Time Division Multiple Access)

For TDMA networks, each node transmits during assigned time slots. Interference is weighted by the probability that each interferer is transmitting when the receiver is listening.

**Configuration**:
```yaml
# In topology YAML or via API
interferers:
  - node_name: node2
    tx_probability: 0.2  # Transmits 20% of the time (1 out of 5 slots)
    is_active: true
```

**Examples**:
- `sinr_tdma_roundrobin/`: 5-node round-robin TDMA (each node gets 20% of slots)
- `sinr_tdma_fixed/`: Custom TDMA schedule with different slot allocations

**SINR Formula**:
```
SINR = Signal / (Noise + Σ(Interference_i × tx_probability_i))
```

### CSMA/CA (Carrier Sense Multiple Access with Collision Avoidance)

For CSMA/CA networks (e.g., WiFi), nodes sense the channel before transmitting. Transmission probability depends on network load and contention.

**Configuration**:
```yaml
interferers:
  - node_name: node2
    tx_probability: 0.3  # Estimated channel occupancy
    is_active: true
```

**Examples**:
- `csma_mcs_test/`: CSMA/CA with adaptive MCS
- `sinr_csma/`: Multi-node CSMA with interference-aware MCS

**Considerations**:
- Hidden node problem: Adjacent-channel interferers may not be detected by carrier sensing
- Transmission probability varies with load and number of contending nodes
- Typical values: 0.1-0.4 for moderate load, 0.5+ for heavy congestion

### Active/Inactive Nodes

Nodes can be dynamically enabled/disabled in interference calculations:

```yaml
interferers:
  - node_name: node3
    is_active: false  # Powered off or out of range
```

This allows modeling:
- Node failures or power-saving modes
- Dynamic network topologies
- Duty-cycled sensor networks
