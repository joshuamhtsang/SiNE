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
     jitter_ms = delay_spread           # RMS delay spread from multipath (Sionna RT)
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

### Example Usage

```python
# In Claude Code conversation, invoke an agent via Task tool:
# For RF/wireless questions:
Task(subagent_type="wireless-comms-engineer",
     prompt="Validate the SNR calculation in this link budget...")

# For Linux networking questions:
Task(subagent_type="linux-networking-specialist",
     prompt="Debug why netem is not applying to containerlab interfaces...")
```

## CLI Tool

This project provides the `sine` CLI tool, defined in `pyproject.toml`:

```toml
[project.scripts]
sine = "sine.cli:main"
```

When you run `uv sync`, it creates `.venv/bin/sine` which calls the `main()` function in `src/sine/cli.py`. The CLI is built with [Click](https://click.palletsprojects.com/).

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

| Example | Description | Link Type | Scene |
|---------|-------------|-----------|-------|
| `vacuum_20m/` | Baseline free-space wireless | wireless | `vacuum.xml` (empty) |
| `manet_triangle/` | 3-node MANET mesh | wireless | `vacuum.xml` (empty) |
| `fixed_link/` | Fixed netem parameters | fixed_netem | (none) |
| `wifi6_adaptive/` | Adaptive MCS selection (WiFi 6) | wireless | `vacuum.xml` (empty) |

The examples demonstrate wireless propagation, multi-node topologies, and fixed link emulation.

## Channel Server API

The channel server (`uv run sine channel-server`) exposes REST endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check with GPU status |
| `/scene/load` | POST | Load ray tracing scene |
| `/compute/single` | POST | Compute channel for single link |
| `/compute/batch` | POST | Compute channels for multiple links |
| `/debug/paths` | POST | Get detailed path info for debugging |

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

### 6. Netem Parameter Conversion

The final PER is converted to netem parameters:

| Parameter | Calculation |
|-----------|-------------|
| **delay_ms** | Propagation delay from strongest path (distance/c) |
| **jitter_ms** | Delay spread from multipath (τ_max - τ_min) |
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
                              BER (from modulation)
                                         ↓
                              BLER (with FEC gain)
                                         ↓
                              PER (packet errors)
                                         ↓
                    Netem Params (delay, jitter, loss%, rate)
```

### Relationship Between Channel Metrics and Netem Parameters

**Important:** SiNE operates as **network emulation** (application-layer testing), not **PHY simulation** (waveform-level). Enhanced channel metrics like RMS delay spread (τ_rms), coherence bandwidth (Bc), and Rician K-factor are **diagnostic only** for visualization and debugging.

**These metrics do NOT directly influence netem configuration** - the netem parameters already account for or abstract physical channel effects:

| Physical Effect | How It's Captured/Abstracted in Netem |
|----------------|----------------------------------------|
| **Delay spread (τ_rms)** | Directly used for `jitter_ms` parameter (packet timing variation) |
| **Frequency selectivity (Bc)** | Not directly captured; SiNE uses AWGN BER formulas (frequency-flat assumption) |
| **K-factor (LOS/NLOS)** | Indirectly via SNR (LOS has lower path loss → higher SNR → lower loss%) |
| **Coherence time (Tc)** | May inform visualization update interval, not netem params |

**Note on BER Calculation:** SiNE uses theoretical AWGN (frequency-flat) BER formulas based purely on SNR and modulation scheme. ISI and frequency selectivity are NOT modeled in the BER calculation - only the RMS delay spread is used for jitter. This is appropriate for network emulation where packet-level behavior matters more than symbol-level distortion.

**Use diagnostic metrics to:**
- Understand **why** certain netem parameters were chosen (e.g., high jitter from large delay spread)
- Validate that netem parameters make sense given channel conditions
- Determine appropriate visualization update rates for mobility scenarios
- Debug link quality issues by understanding the underlying RF propagation
- Identify when poor SNR (not ISI) is causing high packet loss

**Example:** If visualization shows high loss_percent with τ_rms = 50 ns, this does NOT mean ISI is causing the loss. The τ_rms contributes to jitter_ms (packet timing variation), while loss_percent comes from low SNR. If SNR is low due to high path loss, increase TX power, improve antenna gains, or reduce distance. The delay spread itself does not directly cause packet loss in SiNE's abstraction model.

## Important Notes

- **Interface Configuration**: Define per-interface on each node using `interfaces.<iface>.wireless` or `interfaces.<iface>.fixed_netem`
- **Link Endpoints**: Must use `node:interface` format (e.g., `endpoints: [node1:eth1, node2:eth1]`)
- **Link Type Consistency**: Both endpoints of a link must be same type (both wireless OR both fixed_netem)
- **Scene Configuration**: Required for wireless links (specify `scene.file`), optional for fixed_netem-only topologies
- **Sionna Scene Materials**: Must use ITU naming convention (e.g., `itu_concrete`, not `concrete`)
- **netem Configuration**: Requires `sudo` for `nsenter` to access container network namespaces
- **Sionna v1.2.1 API**: Use `Scene()` for empty scenes, `load_scene()` for files
- **Antenna Patterns**: Valid pattern names are `"iso"`, `"dipole"`, `"hw_dipole"`, `"tr38901"` (not `"isotropic"`)
- **Antenna Polarization**: Valid polarization values are `"V"`, `"H"`, `"VH"`, `"cross"`
- **Scene Loading**: Use `load_scene(file, merge_shapes=False)` to keep individual surfaces separate for inspection; default merges same-material surfaces for performance
- **Render Command**: Does NOT require channel server - uses local SionnaEngine directly

## Scene Visualization

### Interactive Viewer (`scenes/viewer.ipynb`)

The Jupyter notebook provides:
- Lists all scene objects with IDs, center positions, bounding boxes, and materials
- Adds axis markers (TX at origin, RX at 1m along each axis) for orientation
- Supports clipping planes to see interior (`scene.preview(clip_at=2.0)`)
- Alt+click in preview to get coordinates of any point

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

### Why does Containerlab use a Linux bridge?

**Q: How are containers connected in Containerlab?**

A: Containerlab connects containers via a **Linux bridge**, not direct veth pairs:

```
Direct veth (NOT how it works):
Node1:eth1 ════════════════════ Node2:eth1
         single veth pair

Containerlab architecture (ACTUAL):
Node1:eth1 ══════╗          ╔══════ Node2:eth1
                 ║          ║
            ┌────╨──────────╨────┐
            │    Linux Bridge    │
            └────────────────────┘
```

**Q: What are the implications of the bridge architecture?**

**Pros:**
- **Scalability**: Easy to add more nodes to the same network segment
- **Flexibility**: Supports complex topologies (mesh, star, etc.)
- **Isolation**: Bridge provides network namespace separation
- **Monitoring**: Can attach tcpdump to the bridge for debugging
- **Standard tooling**: Works with standard Linux networking tools

**Cons:**
- **Extra hop**: Packets traverse the bridge (minimal latency impact, ~microseconds)
- **Bridge overhead**: Small CPU overhead for bridge processing
- **MAC learning**: Bridge maintains MAC address table (negligible for small topologies)
- **Not point-to-point**: Technically a shared medium, though with only 2 nodes it behaves like point-to-point

**Q: Does the bridge affect netem accuracy?**

A: The bridge adds negligible latency (~1-10 microseconds) compared to the wireless delays being emulated (typically 0.1-10+ milliseconds). For wireless network emulation purposes, this overhead is insignificant.

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

### MANET Example

See `examples/manet_triangle/network.yaml` for a 3-node MANET topology:

```bash
# Deploy MANET example
sudo $(which uv) run sine deploy examples/manet_triangle/network.yaml

# Verify all 3 links have netem configured
./CLAUDE_RESOURCES/check_netem.sh
```

### Shared Bridge Model (Future Enhancement)

A more realistic MANET implementation would use a shared broadcast medium:

```
All nodes share a single Linux bridge (broadcast domain)
            ╔═══════════════════════════════╗
Node1:eth1 ═╣                               ╠═ Node2:eth1
            ║       Shared Bridge           ║
Node3:eth1 ═╣   (single broadcast domain)   ╠═ Node4:eth1
            ╚═══════════════════════════════╝
```

**Key differences from point-to-point:**
- Single interface per node (like real MANETs)
- All nodes "hear" all transmissions (broadcast medium)
- Requires per-destination filtering for netem (complex)
- Hidden node problem can be modeled

**Implementation approach:**
1. Create single bridge connecting all wireless nodes
2. Use eBPF/tc filters to apply per-destination netem rules
3. Broadcast packets see worst-case channel to any receiver

This is not yet implemented but could be added for applications requiring true broadcast semantics.

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

See `examples/wifi6_adaptive/` for a complete adaptive MCS example:

```bash
# Start channel server
uv run sine channel-server

# Deploy (in another terminal)
sudo $(which uv) run sine deploy examples/wifi6_adaptive/network.yaml

# Test throughput
docker exec -it clab-wifi6-adaptive-node1 ip addr add 192.168.1.1/24 dev eth1
docker exec -it clab-wifi6-adaptive-node2 ip addr add 192.168.1.2/24 dev eth1
docker exec -it clab-wifi6-adaptive-node1 iperf3 -s &
docker exec -it clab-wifi6-adaptive-node2 iperf3 -c 192.168.1.1

# Cleanup
sudo $(which uv) run sine destroy examples/wifi6_adaptive/network.yaml
```

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
