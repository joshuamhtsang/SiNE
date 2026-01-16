# SINR Implementation Plan for SiNE

## Executive Summary

This plan implements Signal-to-Interference-plus-Noise Ratio (SINR) support for SiNE's wireless channel computation, enabling realistic multi-node interference modeling for MANET topologies. The implementation extends the current SNR-only pipeline with:

- **Multi-transmitter interference**: Calculate how simultaneous transmissions affect each link
- **Adjacent-channel interference**: Model partial interference from nearby frequencies using ACLR
- **Dynamic transmission states**: Track which nodes are actively transmitting (Phase 3)
- **Per-node frequency assignment**: Support centralized radio planning with different frequencies

**Key Insight**: Sionna's `RadioMapSolver` natively computes received signal strength (RSS) from multiple transmitters, which we'll use to calculate interference power at each receiver position.

## Current State Analysis

### Current SNR-Only Pipeline

```
SNR_dB = P_rx - N_dBm
where:
  P_rx = P_tx - path_loss_db  (from Sionna RT)
  N_dBm = thermal noise floor
  NO interference component
```

**Limitation**: Each link computed in isolation. For 3-node MANET with all nodes transmitting:
- Node1→Node2 link ignores interference from Node3's transmission
- Results in optimistic link quality estimates

### Shared Bridge Architecture

The recently implemented shared bridge (`examples/manet_triangle_shared/`) provides:
- All-to-all link computation: N×(N-1) directional links for N nodes
- Per-destination netem via tc flower filters
- Single broadcast domain (realistic MANET)

**Perfect foundation for SINR**: Already computes all links, just needs interference awareness.

## Architecture Design

### SINR Formula

```
SINR_dB = P_signal - 10×log10(P_noise_linear + P_interference_linear)

where:
  P_signal = desired TX→RX received power (from Sionna PathSolver)
  P_noise_linear = 10^(N_dBm / 10)
  P_interference_linear = Σ(10^((P_interferer - ACLR(Δf)) / 10))
```

### Adjacent-Channel Leakage Ratio (ACLR)

Based on WiFi 6 (802.11ax) specifications:

| Frequency Separation | ACLR (dB) | Interference Level |
|----------------------|-----------|-------------------|
| 0-10 MHz (co-channel) | 0 dB | Full interference |
| 10-30 MHz (adjacent) | 20 dB | -20 dB reduction |
| 30-50 MHz (2nd adj) | 40 dB | -40 dB reduction |
| >50 MHz (orthogonal) | 60 dB | Negligible |

**Example**: Node1 at 5.18 GHz receives:
- Node2 at 5.18 GHz (co-channel): Full interference power
- Node3 at 5.20 GHz (20 MHz away): Interference reduced by 20 dB

### Multi-Transmitter Ray Tracing Approach

**Hybrid RadioMapSolver + PathSolver**:

1. **PathSolver** (existing): Compute detailed CIR for TX→RX link
   - Extract path loss, delay, delay spread
   - Used for netem parameters (delay, jitter)

2. **RadioMapSolver** (new): Compute RSS from all transmitters at RX position
   - Get interference power from each peer node
   - Apply ACLR based on frequency separation
   - Aggregate interference in linear domain

**Why hybrid?** RadioMapSolver gives interference but not detailed CIR for jitter calculation. PathSolver gives CIR but only for single TX. We need both.

### Frequency Grouping Strategy

Group nodes by frequency to reduce computational complexity:

```python
# Example: 5 nodes
node_freqs = {
    "node1": 5.18e9,  # Group 1 (co-channel)
    "node2": 5.18e9,  # Group 1
    "node3": 5.20e9,  # Group 1 (adjacent)
    "node4": 5.50e9,  # Group 2 (orthogonal)
    "node5": 5.52e9,  # Group 2 (orthogonal from group 1)
}

# Grouping with 60 MHz threshold:
groups = [
    FrequencyGroup([node1, node2, node3]),  # 5.18-5.20 GHz
    FrequencyGroup([node4, node5])          # 5.50-5.52 GHz
]
```

**Benefits**:
- Only compute interference within groups (nodes >60 MHz apart don't interfere)
- Complexity: O(G × N_g²) instead of O(N²) where G = num groups, N_g = nodes per group
- Typical MANET: 3-5 frequency groups, 5-10 nodes per group

## Implementation Phases

### Phase 1: Same-Frequency Interference (Static TX States)

**Goal**: Basic SINR for co-channel interference, assuming all nodes transmit simultaneously

**New Components**:

1. **`src/sine/channel/sinr.py`** (NEW)
   ```python
   class SINRCalculator:
       def calculate_sinr(
           signal_power_dbm: float,
           interference_terms: list[InterferenceTerm]
       ) -> tuple[float, dict]

       def calculate_aclr(delta_f_mhz: float) -> float
   ```

2. **`src/sine/channel/interference_engine.py`** (NEW)
   ```python
   class InterferenceEngine:
       def compute_interference_for_frequency_group(
           transmitters: list[TransmitterInfo],
           rx_positions: dict[str, tuple]
       ) -> dict[str, InterferenceResult]
   ```

3. **`src/sine/channel/frequency_groups.py`** (NEW)
   ```python
   def group_nodes_by_frequency(
       node_frequencies: dict[str, float],
       adjacent_threshold_hz: float = 20e6
   ) -> list[FrequencyGroup]
   ```

**Modified Components**:

4. **`src/sine/channel/server.py`** (MODIFIED)
   - Add `/compute/sinr` endpoint
   - SINRLinkRequest/SINRResponse models
   - Integration with InterferenceEngine

5. **`src/sine/emulation/controller.py`** (MODIFIED)
   - Add `_update_all_links_with_sinr()` method
   - Frequency grouping logic
   - SINR-aware orchestration

6. **`src/sine/config/schema.py`** (MODIFIED)
   - Add `enable_sinr: bool` field to TopologyConfig
   - Add `TransmissionState` config

**Testing**:
- Unit tests: SINR calculation, ACLR formula, frequency grouping
- Integration: 3-node same-frequency topology (`examples/sinr_basic/`)
- Validation: SINR < SNR, ~5-10 dB reduction with 2 interferers

**Expected Output**:
```
Deployment Summary:
  Link: node1→node2 [wireless]
    SNR: 35.2 dB | SINR: 28.4 dB | Interferers: 1 (node3)
    Delay: 0.10 ms | Jitter: 0.00 ms | Loss: 0.00% | Rate: 450 Mbps
```

### Phase 2: Adjacent-Channel Interference

**Goal**: Model partial interference from nearby frequencies with ACLR rejection

**New Components**:

1. **ACLR calculation** in `SINRCalculator`
   - Piecewise linear ACLR model (0, 20, 40, 60 dB)
   - Configurable per-topology

**Modified Components**:

2. **`src/sine/channel/interference_engine.py`** (MODIFIED)
   - Multi-frequency support in RadioMapSolver
   - ACLR application to interference terms

3. **`src/sine/emulation/controller.py`** (MODIFIED)
   - Process multiple frequency groups
   - Cross-group interference calculation (with ACLR)

**Testing**:
- Unit tests: ACLR for various Δf values
- Integration: 3-node mixed-frequency (`examples/sinr_adjacent/`)
  - Node1: 5.18 GHz, Node2: 5.20 GHz (adjacent, 20 dB rejection)
  - Node3: 5.26 GHz (2nd adjacent, 40 dB rejection)
- Validation: Graded interference based on frequency separation

**Example Configuration** (`examples/sinr_adjacent/network.yaml`):
```yaml
topology:
  enable_sinr: true

  nodes:
    node1:
      interfaces:
        eth1:
          wireless:
            frequency_ghz: 5.18  # Channel 36
    node2:
      interfaces:
        eth1:
          wireless:
            frequency_ghz: 5.20  # Channel 40 (adjacent)
    node3:
      interfaces:
        eth1:
          wireless:
            frequency_ghz: 5.26  # Channel 52 (2nd adjacent)
```

### Phase 3: Dynamic Transmission State Tracking

**Goal**: Track which nodes are transmitting, update SINR dynamically

**New Components**:

1. **Transmission state API** in `server.py`
   ```python
   @app.post("/api/transmission/state")
   async def update_transmission_state(
       request: TransmissionStateUpdate
   )
   ```

2. **Rate limiting** (`src/sine/topology/netem_scheduler.py`)
   ```python
   class NetemUpdateScheduler:
       min_interval_sec = 1.0
       sinr_hysteresis_db = 3.0
   ```

**Modified Components**:

3. **`src/sine/channel/interference_engine.py`** (MODIFIED)
   - Filter inactive transmitters before interference calculation

4. **`src/sine/emulation/controller.py`** (MODIFIED)
   - State change event handling
   - Incremental SINR recomputation for affected links

**Testing**:
- Unit tests: State update API, rate limiting, hysteresis
- Integration: Toggle node TX states, verify SINR updates
- Stress: Rapid state changes (>10 Hz), verify no thrashing

**Usage Example**:
```bash
# Deploy with dynamic state
sudo $(which uv) run sine deploy examples/sinr_dynamic/network.yaml

# Node2 stops transmitting
curl -X POST http://localhost:8000/api/transmission/state \
  -H "Content-Type: application/json" \
  -d '{"states": {"node2": false}}'

# SINR for node1→node3 improves (one less interferer)
# Netem updates automatically (rate-limited to 1 Hz)
```

## Critical Files

### Phase 1: Same-Frequency SINR

| File | Type | Purpose |
|------|------|---------|
| [src/sine/channel/sinr.py](src/sine/channel/sinr.py) | NEW | SINR calculation with interference aggregation |
| [src/sine/channel/interference_engine.py](src/sine/channel/interference_engine.py) | NEW | Multi-TX interference using RadioMapSolver |
| [src/sine/channel/frequency_groups.py](src/sine/channel/frequency_groups.py) | NEW | Frequency grouping utilities |
| [src/sine/channel/server.py](src/sine/channel/server.py) | MODIFIED | Add `/compute/sinr` endpoint |
| [src/sine/emulation/controller.py](src/sine/emulation/controller.py) | MODIFIED | SINR-aware link orchestration |
| [src/sine/config/schema.py](src/sine/config/schema.py) | MODIFIED | Add `enable_sinr` config field |

### Phase 2: Adjacent-Channel

| File | Type | Purpose |
|------|------|---------|
| [src/sine/channel/sinr.py](src/sine/channel/sinr.py) | MODIFIED | Add ACLR calculation |
| [src/sine/channel/interference_engine.py](src/sine/channel/interference_engine.py) | MODIFIED | Multi-frequency support |
| [src/sine/emulation/controller.py](src/sine/emulation/controller.py) | MODIFIED | Multi-frequency group processing |

### Phase 3: Dynamic State

| File | Type | Purpose |
|------|------|---------|
| [src/sine/channel/server.py](src/sine/channel/server.py) | MODIFIED | State API + storage |
| [src/sine/topology/netem_scheduler.py](src/sine/topology/netem_scheduler.py) | NEW | Rate limiting wrapper |
| [src/sine/emulation/controller.py](src/sine/emulation/controller.py) | MODIFIED | State change event handling |

## Configuration Schema Changes

### New Fields in `network.yaml`

```yaml
topology:
  # Enable SINR computation (default: false, use SNR only)
  enable_sinr: bool

  # Transmission state configuration
  transmission_state:
    # Phase 1: All nodes transmit simultaneously (worst-case)
    default_all_transmitting: bool = true

    # Phase 3: Enable dynamic state tracking via API
    enable_dynamic_state: bool = false

  # ACLR configuration (optional, WiFi 6 defaults)
  aclr_config:
    co_channel_db: 0.0
    adjacent_db: 20.0
    second_adjacent_db: 40.0
    orthogonal_db: 60.0

  nodes:
    node1:
      interfaces:
        eth1:
          wireless:
            # Per-node frequency assignment (existing field)
            frequency_ghz: 5.18
            # ... other wireless params
```

## Testing Strategy

### Unit Tests

**`tests/test_sinr_calculator.py`**:
- SINR == SNR when no interferers
- SINR < SNR with co-channel interferer
- SINR reduction ~3 dB for equal-power interferer
- ACLR calculation for various Δf

**`tests/test_interference_engine.py`**:
- RadioMapSolver integration
- Multi-TX RSS extraction
- Interference aggregation (linear domain)

**`tests/test_frequency_groups.py`**:
- Same-frequency nodes in one group
- Orthogonal channels in separate groups
- Adjacent-channel grouping logic

### Integration Tests

**`tests/integration/test_sinr_manet.py`**:
- 3-node same-frequency: SINR ~5-10 dB lower than SNR
- 3-node mixed-frequency: Graded interference by ACLR
- Dynamic state: TX toggle changes SINR

**`examples/sinr_basic/`**:
- 3-node equilateral triangle, all 5.18 GHz
- Verify symmetric SINR (all links ~same quality)

**`examples/sinr_adjacent/`**:
- 3-node with frequencies [5.18, 5.20, 5.26] GHz
- Verify ACLR rejection (20 dB, 40 dB)

**`examples/sinr_dynamic/`**:
- 4-node with state API
- Toggle scripts for TX states

## Verification

### End-to-End Test

```bash
# 1. Start channel server
uv run sine channel-server

# 2. Deploy with SINR enabled
sudo $(which uv) run sine deploy examples/sinr_basic/network.yaml

# Expected deployment summary:
# Link: node1→node2 [wireless]
#   SNR: 35.2 dB | SINR: 28.4 dB | Interferers: 1
#   Delay: 0.10 ms | Loss: 0.05% | Rate: 450 Mbps

# 3. Verify tc configuration shows higher loss than SNR-only
docker exec clab-sinr-basic-node1 tc -s qdisc show dev eth1

# 4. Test connectivity (should work despite interference)
docker exec clab-sinr-basic-node1 ping -c 5 192.168.100.2

# 5. Cleanup
sudo $(which uv) run sine destroy examples/sinr_basic/network.yaml
```

### Success Criteria

**Phase 1**:
- ✓ SINR < SNR for all links with interferers
- ✓ 3-node same-freq shows ~5-10 dB SINR reduction
- ✓ Deployment summary displays both SNR and SINR
- ✓ Netem parameters use SINR (not SNR) for BER/PER calculation
- ✓ Unit + integration tests pass

**Phase 2**:
- ✓ Adjacent-channel shows ~20 dB ACLR rejection
- ✓ Orthogonal channels (>60 MHz) have negligible interference
- ✓ Frequency grouping works correctly
- ✓ Mixed-frequency topology shows graded interference

**Phase 3**:
- ✓ State API updates transmission states
- ✓ SINR recomputation only for affected links
- ✓ Rate limiting prevents thrashing (<1 Hz updates)
- ✓ TX toggle causes expected SINR change
- ✓ Stable under rapid state changes

## Edge Cases

### 1. No Interferers → Graceful Degradation
```python
# Single link, no other nodes
assert abs(result.sinr_db - result.snr_db) < 0.1
```

### 2. All Interferers Orthogonal
```yaml
# node1: 5.18 GHz, node2: 5.50 GHz (320 MHz apart)
# ACLR ≥ 60 dB, interference negligible
assert result.total_interference_dbm < result.signal_power_dbm - 60
```

### 3. Frequency Overlap Validation
```python
def validate_frequency_separation(f1, f2, bw):
    delta = abs(f1 - f2)
    if delta < bw/2: return "overlapping"  # ERROR
    elif delta < bw: return "adjacent"
    else: return "orthogonal"
```

### 4. Zero Active Transmitters
```python
# Phase 3: All nodes set to is_transmitting=false
# Response: Warning + use default params
logger.warning("No active transmitters, using SNR-only mode")
```

## Implementation Order

### Week 1: Phase 1 Core Infrastructure
1. Create `SINRCalculator` class (sinr.py)
2. Create `InterferenceEngine` class (interference_engine.py)
3. Create `FrequencyGroup` utilities (frequency_groups.py)
4. Unit tests for SINR calculation

### Week 2: Phase 1 Integration
5. Add `/compute/sinr` endpoint to channel server
6. Modify controller for SINR orchestration
7. Add `enable_sinr` config field
8. Integration test for 3-node same-frequency

### Week 3: Phase 2 Adjacent-Channel
9. Implement ACLR calculation
10. Multi-frequency support in InterferenceEngine
11. Frequency grouping in controller
12. Integration test for mixed-frequency

### Week 4: Phase 3 Dynamic State (Optional)
13. State storage + API endpoint
14. Rate limiting scheduler
15. State change event handling
16. Stress testing

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| RadioMapSolver performance slow | High | Optimize cell_size, samples_per_tx; cache results |
| Sionna doesn't support multi-freq in single scene | Medium | Use separate scenes per frequency group |
| Netem update thrashing | Medium | Rate limiting + hysteresis (1 Hz, 3 dB) |
| ACLR model inaccurate | Low | Make ACLR configurable per-topology |
| Backward compatibility breaks | High | Feature flag: `enable_sinr=false` by default |

## Backward Compatibility

- `enable_sinr=false` (default): Use existing SNR-only pipeline, no changes
- `enable_sinr=true`: Opt-in to SINR mode
- All existing examples work unchanged
- Deployment summary shows both SNR and SINR when enabled

## Future Enhancements

- **Per-destination ACLR**: Different rejection ratios per node pair
- **Directional antennas**: Spatial interference rejection
- **Frequency hopping**: Time-varying frequency assignments
- **Interference whitening**: Advanced receiver modeling
- **Multi-cell scenarios**: Inter-cell interference for cellular topologies
