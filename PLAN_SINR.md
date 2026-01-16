# SINR Implementation Plan for SiNE

## Executive Summary

This plan implements Signal-to-Interference-plus-Noise Ratio (SINR) support for SiNE's wireless channel computation, enabling realistic multi-node interference modeling for MANET topologies. The implementation extends the current SNR-only pipeline with:

**IMPORTANT - Revised after wireless communications engineer review**: This plan has been updated to fix critical technical issues identified in expert review. Key changes:
- ❌ **RadioMapSolver removed** → ✅ **PathSolver-only approach** (Phase 0 added for validation)
- ❌ **ACLR 20/40/60 dB** → ✅ **IEEE 802.11ax spec: 28/40/45 dB**
- ❌ **1 Hz update rate** → ✅ **10 Hz (100ms) for MANET timescales**
- ❌ **10 kbps threshold** → ✅ **100 kbps (avoid false positives)**
- ✅ **Added**: Antenna gains in interference, rx_sensitivity check, capture effect, CSMA/CA statistical model
- ✅ **Added**: TDMA statistical model for military MANET radios (Phase 1.6)

**Updated Timeline**: 7.5 weeks (vs original 4 weeks) to include:
- Phase 0: PathSolver validation
- Phase 1.5: CSMA/CA model (WiFi MANETs)
- Phase 1.6: TDMA model (military MANETs)

---

## Features

- **Multi-transmitter interference**: Calculate how simultaneous transmissions affect each link
- **Adjacent-channel interference**: Model partial interference from nearby frequencies using ACLR
- **Dynamic transmission states**: Track which nodes are actively transmitting (Phase 3)
- **Per-node frequency assignment**: Support centralized radio planning with different frequencies

**Key Insight**: Use Sionna's `PathSolver` iteratively for each interferer to compute interference power at receiver positions. This provides accurate per-link interference calculation without the overhead of RadioMapSolver's grid-based approach.

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
  P_signal = P_tx + G_tx + G_rx - PL_signal (dBm)
  P_noise_linear = 10^(N_dBm / 10)
  P_interference_linear = Σ(10^(I_i / 10))
  I_i = P_tx_i + G_tx_i + G_rx - PL_i - ACLR(Δf_i) (dBm, for each interferer i)

Note: Interference includes both TX and RX antenna gains, just like signal path.
```

### Adjacent-Channel Leakage Ratio (ACLR)

Based on IEEE 802.11ax-2021 spectrum mask specifications:

| Frequency Separation | ACLR (dB) | Interference Level | Standard Requirement |
|----------------------|-----------|-------------------|---------------------|
| 0-10 MHz (co-channel) | 0 dB | Full interference | 0 dBr |
| 10-20 MHz (1st adjacent) | 28 dB | -28 dB reduction | ≥28 dBr |
| 20-30 MHz (1st adjacent) | 28 dB | -28 dB reduction | ≥28 dBr |
| 30-50 MHz (2nd adjacent) | 40 dB | -40 dB reduction | ≥40 dBr |
| >50 MHz (orthogonal) | 45 dB | Negligible | ~40-45 dBr typical |

**Note**: Previous plan used overly optimistic 20 dB for adjacent channels. IEEE 802.11ax requires ≥28 dB rejection for first adjacent channel.

**Example**: Node1 at 5.18 GHz receives:
- Node2 at 5.18 GHz (co-channel): Full interference power
- Node3 at 5.20 GHz (20 MHz away): Interference reduced by 28 dB (not 20 dB)

### Multi-Transmitter Ray Tracing Approach

**PathSolver-Only Approach** (RadioMapSolver NOT needed):

1. **PathSolver for signal**: Compute detailed CIR for desired TX→RX link
   - Extract path loss, delay, delay spread
   - Used for signal power and netem parameters (delay, jitter)

2. **PathSolver for each interferer**: Iteratively compute interference from each peer
   - For each interferer node: compute Interferer→RX path
   - Extract received interference power (including TX/RX antenna gains)
   - Apply ACLR based on frequency separation
   - Aggregate interference in linear domain

**Why PathSolver-only?**
- RadioMapSolver computes 2D/3D coverage grids (thousands of points), not point-to-point links
- RadioMapSolver doesn't separate individual interference sources
- PathSolver is designed for link-level computation and gives all needed information
- For N nodes: N² PathSolver calls (but only within frequency groups, with caching)

### Receiver Sensitivity and Physical Layer Considerations

**NEW - Missing from original plan**:

1. **Receiver Sensitivity Floor**
   ```python
   # Before computing SINR, check if signal is detectable
   if signal_power_dbm < rx_sensitivity_dbm:
       # Link is below noise floor, unusable regardless of SINR
       return LinkResult(unusable=True, ber=0.5, per=1.0)

   # Also filter interference below sensitivity
   interference_terms = [
       I_dbm for I_dbm in raw_interference
       if I_dbm > rx_sensitivity_dbm  # Ignore sub-sensitivity interference
   ]
   ```
   Default: `rx_sensitivity_dbm = -80.0` for WiFi 6

2. **Capture Effect** (Optional enhancement)
   ```python
   # If signal is X dB stronger than interference, suppress interference
   CAPTURE_THRESHOLD_DB = 6.0  # WiFi typical: 4-6 dB

   def apply_capture_effect(signal_dbm, interference_list):
       return [
           I_dbm for I_dbm in interference_list
           if signal_dbm - I_dbm < CAPTURE_THRESHOLD_DB
       ]
   ```

3. **Regime Detection** (Diagnostic logging)
   ```python
   if total_interference_dbm < noise_dbm - 10:
       regime = "noise-limited"  # SNR matters, SINR ≈ SNR
   elif total_interference_dbm > noise_dbm + 10:
       regime = "interference-limited"  # SIR matters, SINR ≈ SIR
   else:
       regime = "mixed"

   logger.info(f"Link {tx}→{rx}: {regime}, SINR={sinr_db:.1f} dB")
   ```

4. **Frequency-Selective Fading** (Future work)
   - Current plan: Wideband average SINR (acceptable for Phase 1-2)
   - Future: Per-subcarrier SINR for OFDM (more accurate for WiFi 6)
   - Document limitation in README

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

# Grouping with dual thresholds:
ADJACENT_THRESHOLD = 50e6   # 50 MHz - compute interference with ACLR
ORTHOGONAL_THRESHOLD = 100e6  # 100 MHz - ignore (negligible)

groups = [
    FrequencyGroup([node1, node2, node3]),  # 5.18-5.20 GHz
    FrequencyGroup([node4, node5])          # 5.50-5.52 GHz
]
```

**Benefits**:
- Compute interference for nodes within ADJACENT_THRESHOLD (with ACLR)
- Ignore interference for nodes >ORTHOGONAL_THRESHOLD apart (truly negligible)
- Complexity: O(G × N_g²) instead of O(N²) where G = num groups, N_g = nodes per group
- Typical MANET: 3-5 frequency groups, 5-10 nodes per group

**Note**: Using 50 MHz threshold accounts for 2nd adjacent channels with 40 dB rejection (not negligible). 100 MHz ensures >45 dB rejection.

## Implementation Phases

### Phase 0: PathSolver-Based Interference Engine (NEW - Critical Validation)

**Goal**: Validate core interference engine using PathSolver before adding SINR complexity

**Why Phase 0?** The original plan proposed RadioMapSolver, but this is the wrong tool (designed for coverage grids, not link-level computation). Phase 0 validates the correct PathSolver-based approach.

**New Components**:

1. **`src/sine/channel/interference_engine.py`** (NEW)
   ```python
   class InterferenceEngine:
       """Compute interference from multiple transmitters using PathSolver."""

       def __init__(self, path_solver):
           self.path_solver = path_solver
           self._path_cache = {}  # Cache for static topologies

       def compute_interference_at_receiver(
           self,
           rx_position: tuple[float, float, float],
           interferers: list[TransmitterInfo],
           active_states: dict[str, bool]
       ) -> list[InterferenceTerm]:
           """
           Compute interference from all active interferers at RX position.

           Returns list of InterferenceTerm with:
           - source: interferer node name
           - power_dbm: interference power (including TX/RX gains, path loss)
           - frequency_hz: interferer frequency
           """
           interference_list = []

           for interferer in interferers:
               if not active_states.get(interferer.node_name, True):
                   continue  # Skip inactive interferers

               # Compute path from interferer to receiver
               paths = self.path_solver(interferer.position, rx_position)

               # Extract path loss from Sionna paths
               path_loss_db = compute_path_loss(paths)

               # Compute interference power: P_tx + G_tx + G_rx - PL
               interference_dbm = (
                   interferer.tx_power_dbm
                   + interferer.antenna_gain_dbi
                   + rx_antenna_gain_dbi  # RX gain towards interferer
                   - path_loss_db
               )

               interference_list.append(InterferenceTerm(
                   source=interferer.node_name,
                   power_dbm=interference_dbm,
                   frequency_hz=interferer.frequency_hz
               ))

           return interference_list
   ```

**Testing**:
- Unit test: 2-node free-space, verify interference power matches Friis equation (±0.5 dB)
- Integration test: 3-node equilateral triangle, verify interference aggregation
- Performance benchmark: Measure time for N=5, 10, 20 nodes (target: <500ms for 10 nodes)
- Validation: Compare against theoretical link budget calculations

**Success Criteria**:
- ✓ PathSolver-based interference matches theoretical values within 0.5 dB
- ✓ 10-node MANET computes all interference in <500 ms (static positions)
- ✓ Antenna gain inclusion verified (check both TX and RX gains applied)
- ✓ Path caching works for static topologies

**Timeline**: Week 1 (5 days)

---

### Phase 1: Same-Frequency Interference (Static TX States)

**Goal**: Basic SINR for co-channel interference, assuming all nodes transmit simultaneously

**Note on "all transmitting" assumption**: This is a **conservative worst-case** for testing, NOT realistic for CSMA/CA MANETs. Real MANETs typically have 1-2 nodes transmitting simultaneously. Document this clearly as pessimistic upper bound. Move to Phase 3 (realistic states) quickly.

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

2. **`src/sine/channel/interference_engine.py`** (MODIFIED from Phase 0)
   ```python
   class InterferenceEngine:
       def compute_interference_for_frequency_group(
           transmitters: list[TransmitterInfo],
           rx_positions: dict[str, tuple],
           active_tx_states: dict[str, bool]
       ) -> dict[str, InterferenceResult]
       # Note: Uses PathSolver iteratively, NOT RadioMapSolver
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
   - Add `rx_sensitivity_dbm: float` field (default: -80 dBm for WiFi 6)
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

---

### Phase 1.5: CSMA/CA Statistical Model (NEW - Realistic MAC Behavior)

**Goal**: Compute realistic SINR accounting for WiFi CSMA/CA behavior without full MAC simulation

**Why Phase 1.5?** Phase 1's "all nodes transmitting simultaneously" assumption is overly pessimistic for WiFi MANETs. Real WiFi uses CSMA/CA (Carrier Sense Multiple Access with Collision Avoidance) to achieve temporal separation - nodes defer transmission when they sense the medium is busy. This phase adds a lightweight statistical model to capture spatial reuse and hidden node effects.

**Key Insight**: WiFi doesn't use strict TDMA, but CSMA/CA achieves **statistical time-domain separation**:
- Nodes within carrier sense range defer (don't transmit simultaneously)
- Nodes beyond carrier sense range are "hidden nodes" (potential collisions)
- Typical carrier sense range: 2.5× communication range

**Approach**: Binary carrier sensing model with per-interferer TX probability

```python
# Simplified CSMA/CA model
class CSMAModel:
    """
    Statistical CSMA/CA model for WiFi MANET SINR computation.

    Captures spatial reuse and hidden node problem without event simulation.
    """

    def __init__(
        self,
        carrier_sense_range_multiplier: float = 2.5,  # WiFi typical
        default_traffic_load: float = 0.3  # 30% duty cycle
    ):
        self.cs_multiplier = carrier_sense_range_multiplier
        self.traffic_load = default_traffic_load

    def compute_interference_probability(
        self,
        tx_node: str,
        rx_node: str,
        interferer_node: str,
        positions: dict[str, tuple[float, float, float]],
        communication_range: float
    ) -> float:
        """
        Compute probability that interferer is transmitting when tx_node transmits.

        Returns:
            0.0 if interferer within carrier sense range (defers due to CSMA)
            traffic_load if interferer beyond carrier sense range (hidden node)
        """
        tx_pos = positions[tx_node]
        interferer_pos = positions[interferer_node]

        # Distance from interferer to TX node
        dist_to_tx = compute_distance(interferer_pos, tx_pos)

        # Carrier sense range
        cs_range = communication_range * self.cs_multiplier

        if dist_to_tx < cs_range:
            # Interferer can sense TX node, defers transmission (CSMA/CA)
            return 0.0
        else:
            # Hidden node: interferer cannot sense TX, may transmit
            # Probability = traffic load (duty cycle)
            return self.traffic_load
```

**Expected Interference Calculation**:
```python
# For each link TX→RX, compute expected interference
expected_interference_linear = sum(
    Pr[interferer_i TX] × 10^(I_i / 10)
    for interferer_i in potential_interferers
)

SINR = signal_power / (noise_power + expected_interference_linear)
```

**New Components**:

1. **`src/sine/channel/csma_model.py`** (NEW)
   ```python
   class CSMAModel:
       def compute_interference_probabilities(
           tx_node: str,
           rx_node: str,
           all_positions: dict[str, tuple],
           communication_range: float,
           traffic_load: float = 0.3
       ) -> dict[str, float]
       # Returns: {interferer_name: Pr[TX]}

   def compute_carrier_sense_range(
       communication_range: float,
       cs_multiplier: float = 2.5
   ) -> float:
       """Typical WiFi: CS range = 2.5× communication range"""
       return communication_range * cs_multiplier
   ```

**Modified Components**:

2. **`src/sine/channel/sinr.py`** (MODIFIED)
   ```python
   class SINRCalculator:
       def calculate_sinr_with_csma(
           signal_power_dbm: float,
           interference_terms: list[InterferenceTerm],
           interference_probs: dict[str, float]  # NEW: per-interferer TX probability
       ) -> tuple[float, dict]:
           """
           Calculate SINR with CSMA/CA statistical model.

           Expected interference = sum(Pr[TX_i] × I_i)
           """
           # Aggregate expected interference (not worst-case)
           expected_interference_linear = sum(
               prob * 10**(term.power_dbm / 10)
               for term, prob in zip(interference_terms, interference_probs.values())
           )

           noise_linear = 10**(noise_dbm / 10)
           sinr_db = signal_power_dbm - 10 * log10(
               noise_linear + expected_interference_linear
           )

           return sinr_db, {
               "interference_model": "csma",
               "num_interferers": len(interference_terms),
               "num_hidden_nodes": sum(1 for p in interference_probs.values() if p > 0),
               "expected_interference_dbm": 10 * log10(expected_interference_linear)
           }
   ```

3. **`src/sine/config/schema.py`** (MODIFIED)
   ```python
   class CSMAConfig(BaseModel):
       """CSMA/CA statistical model configuration."""
       enabled: bool = True  # Enable CSMA model (disable for worst-case all-TX)
       carrier_sense_range_multiplier: float = 2.5  # CS range / communication range
       traffic_load: float = 0.3  # Default traffic duty cycle (30%)

   class WirelessParams(BaseModel):
       # ... existing wireless params ...
       csma: CSMAConfig = CSMAConfig()  # NEW: CSMA configuration
   ```

**Testing**:

1. **Unit test: CSMA reduces interference vs all-TX**
   ```python
   def test_csma_spatial_reuse():
       # 4-node linear: A --- B --- C --- D (50m spacing)
       # Link A→B, interferers C (adjacent), D (hidden)

       # All-TX model (worst case)
       sinr_all_tx = compute_sinr(model="all_tx")

       # CSMA model (CS range = 125m, traffic_load = 0.3)
       sinr_csma = compute_sinr(
           model="csma",
           cs_multiplier=2.5,
           traffic_load=0.3
       )

       # Expected: C within CS range (Pr[TX]=0), D hidden (Pr[TX]=0.3)
       # CSMA should have significantly higher SINR
       assert sinr_csma > sinr_all_tx + 5.0  # At least 5 dB improvement
   ```

2. **Integration test: Hidden node scenario**
   ```python
   def test_hidden_node_topology():
       # 3-node hidden node: A ----- B ----- C (150m spacing)
       # A and C are hidden from each other (>CS range)

       positions = {
           "A": (0, 0, 1),
           "B": (150, 0, 1),
           "C": (300, 0, 1)
       }

       # Link A→B with interferer C
       result = compute_sinr_csma(tx="A", rx="B", interferers=["C"])

       # Expected: C is hidden node (300m > CS range 187.5m)
       assert result["num_hidden_nodes"] == 1
       assert result["interference_probs"]["C"] == 0.3  # traffic_load
   ```

3. **System test: Throughput validation**
   ```bash
   # Deploy with CSMA model
   sudo $(which uv) run sine deploy examples/sinr_csma/network.yaml

   # Measure iperf3 throughput
   docker exec clab-sinr-csma-node1 iperf3 -c 192.168.100.2 -t 10

   # Expected: ~80-90% of rate_mbps (accounting for 30% interference duty cycle)
   # Compare with all-TX model (would show ~40-50% due to pessimistic SINR)
   ```

**Configuration Example** (`examples/sinr_csma/network.yaml`):
```yaml
topology:
  enable_sinr: true

  nodes:
    node1:
      interfaces:
        eth1:
          wireless:
            position: {x: 0, y: 0, z: 1}
            frequency_ghz: 5.18
            csma:
              enabled: true                          # Enable CSMA model
              carrier_sense_range_multiplier: 2.5    # WiFi typical
              traffic_load: 0.3                       # 30% duty cycle

    node2:
      interfaces:
        eth1:
          wireless:
            position: {x: 100, y: 0, z: 1}
            frequency_ghz: 5.18
            csma:
              enabled: true
              traffic_load: 0.3

    node3:
      interfaces:
        eth1:
          wireless:
            position: {x: 500, y: 0, z: 1}  # Hidden node scenario
            frequency_ghz: 5.18
            csma:
              enabled: true
              traffic_load: 0.3
```

**Expected Output**:
```
Deployment Summary:
  Link: node1→node2 [wireless, CSMA model]
    SNR: 35.2 dB | SINR: 32.1 dB | Hidden nodes: 1/2 interferers
    Expected interference: -5.2 dBm (vs -2.3 dBm all-TX)
    Delay: 0.10 ms | Jitter: 0.00 ms | Loss: 0.01% | Rate: 480 Mbps
```

**Benefits**:
- ✅ Realistic SINR for WiFi MANETs (not worst-case)
- ✅ Captures spatial reuse (distant nodes transmit concurrently)
- ✅ Models hidden node problem (collisions beyond CS range)
- ✅ Lightweight (~100 lines, no event simulation)
- ✅ Configurable per-topology (traffic_load, CS range)

**Limitations** (acceptable for network emulation):
- ❌ Simplified backoff model (binary CS, no exponential backoff)
- ❌ No RTS/CTS modeling (common to disable in MANETs)
- ❌ Fixed traffic load (Phase 3B auto-detection provides dynamic)

**Success Criteria**:
- ✓ CSMA SINR > all-TX SINR by ≥3 dB (spatial reuse benefit)
- ✓ Hidden nodes correctly identified (>CS range)
- ✓ iperf3 throughput within 10% of analytical model
- ✓ Configurable CS range and traffic load work as expected

**Timeline**: 2-3 days (lightweight implementation)

---

### Phase 1.6: TDMA Statistical Model (NEW - Military MANET Support)

**Goal**: Compute realistic SINR for military MANET radios using TDMA-based MAC

**Why Phase 1.6?** Military waveforms (WNW, MPU5, SINCGARS) use scheduled TDMA access, fundamentally different from WiFi CSMA/CA. Phase 1.5's carrier sensing model doesn't apply to time-slotted protocols where slots are pre-assigned, not sensed.

**Key Insight**: Military radios use **deterministic time slots** for channel access, not WiFi's **probabilistic carrier sensing**. This means:
- **No carrier sense range** concept (orthogonal time slots prevent collisions)
- **Deterministic interference** when slot assignments are known (Pr[collision] = 0 or 1)
- **Throughput depends on slot ownership** (fraction of TDMA frame allocated to node)

**Comparison: TDMA vs CSMA**

| Feature | CSMA Model (Phase 1.5) | TDMA Model (Phase 1.6) |
|---------|------------------------|------------------------|
| **Access method** | Random backoff with carrier sensing | Scheduled time slots |
| **Interference basis** | Spatial separation (carrier sense range) | Temporal separation (slot assignments) |
| **Collision probability** | Statistical (hidden node problem) | Deterministic (zero if orthogonal slots) |
| **TX probability** | 0 (within CS range) or traffic_load (hidden) | 1.0 (if node owns slot) or 0.0 (otherwise) |
| **Typical use case** | WiFi 6 (802.11ax) MANETs | Military radios (WNW, MPU5, SINCGARS) |

**TDMA Slot Assignment Modes**

The TDMA model supports four slot assignment strategies:

1. **FIXED**: Pre-assigned slots per node
   - **Interference**: Deterministic (zero if orthogonal, 100% if collision)
   - **Use case**: Centralized scheduler, known topology
   - **Example**: Node1 owns slots [0, 5], Node2 owns [1, 6] → no collisions

2. **ROUND_ROBIN**: Cyclic slot allocation
   - **Interference**: Zero (each node gets sequential slots)
   - **Use case**: Equal-priority nodes, simple scheduling
   - **Example**: 3 nodes, 10 slots → Node1: [0,3,6,9], Node2: [1,4,7], Node3: [2,5,8]

3. **RANDOM**: Probabilistic slot allocation
   - **Interference**: Statistical (collision probability = slot_probability²)
   - **Use case**: Distributed coordination without central scheduler
   - **Example**: Each node has 30% slot probability → ~9% collision rate

4. **DISTRIBUTED**: DAMA-style distributed coordination
   - **Interference**: Statistical with reduced collisions (coordination overhead)
   - **Use case**: Adaptive slot allocation with demand assignment
   - **Example**: Like RANDOM but with 50% collision reduction from coordination

**New Components**:

1. **`src/sine/channel/tdma_model.py`** (NEW, ~150 lines)
   ```python
   from dataclasses import dataclass
   from enum import Enum
   from typing import Dict, List, Optional

   class SlotAssignmentMode(str, Enum):
       """TDMA slot assignment strategies."""
       FIXED = "fixed"              # Pre-assigned slots per node
       ROUND_ROBIN = "round_robin"  # Cyclic slot allocation
       RANDOM = "random"            # Probabilistic slot allocation
       DISTRIBUTED = "distributed"  # DAMA-style distributed coordination

   @dataclass
   class TDMAConfig:
       """TDMA frame configuration."""
       frame_duration_ms: float = 10.0       # TDMA frame duration (10ms typical)
       num_slots: int = 10                   # Number of slots per frame
       slot_assignment_mode: SlotAssignmentMode = SlotAssignmentMode.ROUND_ROBIN

       # For FIXED mode: explicit slot assignments
       fixed_slot_map: Optional[Dict[str, List[int]]] = None
       # Example: {"node1": [0, 5], "node2": [1, 6], "node3": [2, 7]}

       # For RANDOM/DISTRIBUTED modes: per-node slot probability
       slot_probability: float = 0.1  # Default: each node owns 10% of slots

   class TDMAModel:
       """
       Statistical TDMA model for military MANET SINR computation.

       Captures scheduled access behavior without discrete-event simulation.
       """

       def compute_interference_probability(
           self,
           tx_node: str,
           rx_node: str,
           interferer_node: str,
           current_slot: Optional[int] = None,
           all_nodes: Optional[List[str]] = None,
       ) -> float:
           """
           Compute probability that interferer is transmitting when tx_node transmits.

           In TDMA:
           - If slot assignments are known (FIXED): deterministic (0.0 or 1.0)
           - If slot assignments are probabilistic: statistical (slot_probability)

           Returns:
               Probability that interferer transmits when tx_node transmits
           """
           # Implementation varies by slot_assignment_mode
           # FIXED: Check if both own same slot (0.0 or 1.0)
           # ROUND_ROBIN: No collisions (0.0)
           # RANDOM: Statistical (slot_probability)
           # DISTRIBUTED: Statistical with coordination (slot_probability * 0.5)

       def get_throughput_multiplier(self, node_name: str) -> float:
           """
           Get throughput scaling factor for node based on slot ownership.

           Returns:
               Fraction of time node can transmit (0.0 to 1.0)
           """
           # FIXED: num_owned_slots / num_slots
           # ROUND_ROBIN: 1 / num_nodes
           # RANDOM/DISTRIBUTED: slot_probability
   ```

**Modified Components**:

2. **`src/sine/channel/sinr.py`** (MODIFIED)
   ```python
   class SINRCalculator:
       # ... existing CSMA method ...

       def calculate_sinr_with_tdma(
           self,
           signal_power_dbm: float,
           noise_dbm: float,
           interference_terms: List[InterferenceTerm],
           interference_probs: Dict[str, float],  # From TDMAModel
       ) -> tuple[float, dict]:
           """
           Calculate SINR with TDMA statistical model.

           Expected interference = sum(Pr[TX_i] × I_i) where Pr[TX_i] from slot assignment.
           """
           # Aggregate expected interference (probabilistic or deterministic)
           expected_interference_linear = sum(
               prob * (10 ** (term.power_dbm / 10))
               for term, prob in zip(interference_terms, interference_probs.values())
           )

           noise_linear = 10 ** (noise_dbm / 10)
           sinr_db = signal_power_dbm - 10 * math.log10(
               noise_linear + expected_interference_linear
           )

           # Count deterministic vs probabilistic interferers
           num_deterministic = sum(1 for p in interference_probs.values() if p in [0.0, 1.0])
           num_probabilistic = len(interference_probs) - num_deterministic

           return sinr_db, {
               "interference_model": "tdma",
               "num_interferers": len(interference_terms),
               "num_deterministic_interferers": num_deterministic,
               "num_probabilistic_interferers": num_probabilistic,
               "expected_interference_dbm": 10 * math.log10(expected_interference_linear),
           }
   ```

3. **`src/sine/config/schema.py`** (MODIFIED)
   ```python
   class TDMAConfig(BaseModel):
       """TDMA statistical model configuration."""
       enabled: bool = False  # Enable TDMA model

       frame_duration_ms: float = 10.0  # TDMA frame duration (military: 10ms)
       num_slots: int = 10              # Number of slots per frame

       slot_assignment_mode: Literal["fixed", "round_robin", "random", "distributed"] = "round_robin"

       # For FIXED mode: map node names to slot indices
       fixed_slot_map: Optional[Dict[str, List[int]]] = None

       # For RANDOM/DISTRIBUTED modes: slot ownership probability
       slot_probability: float = 0.1  # Default: 10% duty cycle

   class WirelessParams(BaseModel):
       # ... existing fields ...

       # MAC layer models (mutually exclusive)
       csma: Optional[CSMAConfig] = None   # WiFi CSMA/CA model
       tdma: Optional[TDMAConfig] = None   # Military TDMA model

       @validator('tdma')
       def validate_mac_models_exclusive(cls, v, values):
           """Ensure only one MAC model is enabled."""
           if v and v.enabled and values.get('csma') and values['csma'].enabled:
               raise ValueError("Cannot enable both CSMA and TDMA models")
           return v
   ```

**Configuration Examples**

**Example 1: Fixed TDMA (Pre-assigned orthogonal slots)**

```yaml
# examples/sinr_tdma_fixed/network.yaml
topology:
  enable_sinr: true

  nodes:
    node1:
      interfaces:
        eth1:
          wireless:
            position: {x: 0, y: 0, z: 1}
            frequency_ghz: 5.18
            bandwidth_mhz: 20
            rf_power_dbm: 20
            tdma:
              enabled: true
              slot_assignment_mode: fixed
              frame_duration_ms: 10.0
              num_slots: 10
              fixed_slot_map:
                node1: [0, 5]    # Node1 owns slots 0 and 5 (20% of frame)
                node2: [1, 6]    # Node2 owns slots 1 and 6 (20% of frame)
                node3: [2, 7]    # Node3 owns slots 2 and 7 (20% of frame)

    node2:
      interfaces:
        eth1:
          wireless:
            position: {x: 100, y: 0, z: 1}
            frequency_ghz: 5.18
            bandwidth_mhz: 20
            rf_power_dbm: 20
            tdma:
              enabled: true
              slot_assignment_mode: fixed
              # (same config as node1)

    node3:
      interfaces:
        eth1:
          wireless:
            position: {x: 50, y: 86.6, z: 1}
            frequency_ghz: 5.18
            bandwidth_mhz: 20
            rf_power_dbm: 20
            tdma:
              enabled: true
              slot_assignment_mode: fixed
              # (same config as node1)

links:
  - endpoints: [node1:eth1, node2:eth1]
  - endpoints: [node1:eth1, node3:eth1]
  - endpoints: [node2:eth1, node3:eth1]
```

**Expected Output**:
```
Deployment Summary:
  Link: node1→node2 [wireless, TDMA fixed]
    SNR: 35.2 dB | SINR: 35.2 dB | Interferers: 0/2 deterministic (orthogonal slots)
    Expected interference: -inf dBm (zero collision probability)
    Delay: 0.33 ms | Jitter: 0.00 ms | Loss: 0.00% | Rate: 96 Mbps
    Throughput: 19.2 Mbps (20% slot ownership)
```

**Note**: SINR = SNR because orthogonal slots have zero interference. Throughput is 20% of rate (2 slots out of 10).

---

**Example 2: Round-Robin TDMA**

```yaml
# examples/sinr_tdma_roundrobin/network.yaml
topology:
  enable_sinr: true

  nodes:
    node1:
      interfaces:
        eth1:
          wireless:
            tdma:
              enabled: true
              slot_assignment_mode: round_robin
              num_slots: 12  # 3 nodes × 4 slots each

    node2:
      interfaces:
        eth1:
          wireless:
            tdma:
              enabled: true
              slot_assignment_mode: round_robin
              num_slots: 12

    node3:
      interfaces:
        eth1:
          wireless:
            tdma:
              enabled: true
              slot_assignment_mode: round_robin
              num_slots: 12
```

**Slot allocation (automatic)**:
- Node1: [0, 3, 6, 9] (33.3% of frame)
- Node2: [1, 4, 7, 10] (33.3% of frame)
- Node3: [2, 5, 8, 11] (33.3% of frame)

**Expected**: Zero interference (cyclic slots), SINR = SNR, throughput = 33.3% of rate

---

**Example 3: Random TDMA (Statistical slots)**

```yaml
# examples/sinr_tdma_random/network.yaml
topology:
  enable_sinr: true

  nodes:
    node1:
      interfaces:
        eth1:
          wireless:
            tdma:
              enabled: true
              slot_assignment_mode: random
              slot_probability: 0.3  # 30% duty cycle (~3 slots per 10-slot frame)
              num_slots: 10
```

**Expected interference**: Probabilistic collisions
- 2 nodes: Pr[collision] = 0.3 × 0.3 = 9%
- 3 nodes: Each interferer has 30% chance → statistical SINR degradation

**Use case**: Distributed coordination without centralized scheduler (like Aloha with slotting)

---

**Example 4: Distributed TDMA (DAMA-style)**

```yaml
topology:
  enable_sinr: true

  nodes:
    node1:
      interfaces:
        eth1:
          wireless:
            tdma:
              enabled: true
              slot_assignment_mode: distributed
              slot_probability: 0.3  # 30% duty cycle
              num_slots: 10
```

**Difference from RANDOM**: Coordination reduces collisions by ~50%
- Pr[collision] ≈ 0.3 × 0.3 × 0.5 = 4.5% (vs 9% for random)

**Use case**: Demand-Assigned Multiple Access (DAMA) with distributed signaling

---

**Testing**:

1. **Unit test: TDMA orthogonality**
   ```python
   def test_tdma_fixed_orthogonal_slots():
       # 3-node linear: fixed slots [0,5], [1,6], [2,7]
       sinr = compute_sinr_tdma(
           slot_assignment_mode="fixed",
           fixed_slot_map={"A": [0, 5], "B": [1, 6], "C": [2, 7]}
       )

       # Expected: SINR = SNR (zero interference)
       assert abs(sinr - snr) < 0.1
   ```

2. **Integration test: TDMA vs CSMA comparison**
   ```python
   def test_tdma_vs_csma():
       # Same 3-node topology

       # CSMA model (statistical hidden nodes)
       sinr_csma = compute_sinr(model="csma", traffic_load=0.3)

       # TDMA model (orthogonal slots)
       sinr_tdma = compute_sinr(model="tdma", slot_assignment="fixed")

       # Expected: TDMA higher (no collisions with orthogonal slots)
       assert sinr_tdma > sinr_csma + 3.0  # At least 3 dB better
   ```

3. **System test: Throughput validation**
   ```bash
   # Deploy with TDMA model
   sudo $(which uv) run sine deploy examples/sinr_tdma_fixed/network.yaml

   # Measure iperf3 throughput
   docker exec clab-sinr-tdma-node1 iperf3 -c 192.168.100.2 -t 10

   # Expected: ~20% of rate_mbps (2 slots out of 10)
   # Compare with CSMA model (~80-90% due to spatial reuse)
   ```

**Benefits**:
- ✅ Realistic SINR for military TDMA-based MANETs
- ✅ Deterministic interference with known slot assignments
- ✅ Captures slot ownership impact on throughput
- ✅ Lightweight (~150 lines, no discrete-event simulation)
- ✅ Configurable per-topology (fixed/round-robin/random/distributed)

**Limitations** (acceptable for network emulation):
- ❌ Simplified slot assignment (no dynamic reallocation)
- ❌ No guard intervals or slot synchronization overhead modeled
- ❌ Fixed frame duration (Phase 3 could add dynamic frame sizing)
- ❌ No frequency hopping (SINCGARS-style, could be future work)

**Success Criteria**:
- ✓ TDMA SINR = SNR for orthogonal slots (FIXED/ROUND_ROBIN modes)
- ✓ TDMA SINR > CSMA SINR by ≥3 dB (no hidden node problem)
- ✓ Throughput matches slot ownership fraction (±5%)
- ✓ Configurable slot assignment modes work as expected

**Implementation Complexity**: ~4.5 days (1 week)

**Timeline**: Week 4 (after Phase 1.5 CSMA model)

---

### TDMA Throughput Reduction: Design Rationale

**Important**: TDMA **intentionally reduces throughput** compared to CSMA/CA because nodes can only transmit during their assigned time slots. This is a fundamental trade-off in MAC layer design.

#### Throughput Comparison

**CSMA/CA (WiFi)**:
```
Theoretical PHY rate: 480 Mbps (80 MHz, 64-QAM, rate-2/3 LDPC)
Achievable throughput: ~400-450 Mbps (80-90% efficiency)
Reason: High spatial reuse - distant nodes transmit concurrently
```

**TDMA (Fixed Slots)**:
```
Theoretical PHY rate: 480 Mbps (same PHY layer as CSMA)
Slot ownership: 2/10 slots = 20%
Achievable throughput: ~96 Mbps (20% of theoretical)
Reason: Node only transmits 20% of the time (2 slots out of 10)
```

**Result**: WiFi is ~4-5× faster for same PHY parameters!

#### Why Military Radios Accept Lower Throughput

Despite lower raw throughput, military systems prioritize **determinism and reliability**:

| Requirement | CSMA/CA (WiFi) | TDMA (Military) | Winner |
|-------------|----------------|-----------------|--------|
| **Guaranteed QoS** | Best-effort (~30% duty cycle, statistical) | Guaranteed slots (deterministic) | TDMA ✓ |
| **Latency variance** | High (random backoff, 0-100ms) | Low (predictable slot timing, ±1ms) | TDMA ✓ |
| **Hidden node problem** | Unpredictable packet loss | No collisions (orthogonal slots) | TDMA ✓ |
| **Fairness** | Proximity-based (closer nodes get more airtime) | Equal slots per node | TDMA ✓ |
| **Anti-jam resilience** | Jammer causes denial of service (all defer) | Can use unjammed slots | TDMA ✓ |
| **Raw throughput** | ~400 Mbps (80% spatial reuse) | ~96 Mbps (20% slot ownership) | CSMA ✓ |

**Military priority**: Voice/command traffic needs **predictable** 20 Mbps, not **statistical** 400 Mbps.

In combat scenarios:
- "Your transmission will arrive in slot 5" (TDMA) > "Your transmission might arrive in 10-100ms" (CSMA)
- "Zero collisions guaranteed" (TDMA) > "9% collision rate statistically" (CSMA hidden nodes)

#### Throughput Calculation in SiNE

The TDMA model applies a throughput multiplier based on slot ownership:

```python
class TDMAModel:
    def get_throughput_multiplier(self, node_name: str) -> float:
        """
        Get throughput scaling factor based on slot ownership.

        Returns:
            Fraction of time node can transmit (0.0 to 1.0)
        """
        if self.config.slot_assignment_mode == SlotAssignmentMode.FIXED:
            num_owned_slots = len(self.config.fixed_slot_map.get(node_name, []))
            return num_owned_slots / self.config.num_slots
            # Example: 2 slots / 10 total = 0.2 (20%)

        elif self.config.slot_assignment_mode == SlotAssignmentMode.ROUND_ROBIN:
            # Each node gets equal share
            num_nodes = len(self.config.fixed_slot_map)  # Or from topology
            return 1.0 / num_nodes
            # Example: 3 nodes → 33.3% per node

        elif self.config.slot_assignment_mode in [SlotAssignmentMode.RANDOM,
                                                    SlotAssignmentMode.DISTRIBUTED]:
            # Statistical slot allocation
            return self.config.slot_probability
            # Example: 0.3 → 30% throughput
```

**Applied to netem**:
```python
# In controller.py
effective_rate_mbps = base_phy_rate_mbps * tdma_model.get_throughput_multiplier(node_name)

# Example:
# base_phy_rate_mbps = 480 Mbps (PHY layer, same as WiFi)
# throughput_multiplier = 0.2 (20% slot ownership)
# effective_rate_mbps = 480 × 0.2 = 96 Mbps ← Applied to netem rate limit
```

#### Real-World Example: 3-Node Military MANET

**Configuration**:
```yaml
tdma:
  frame_duration_ms: 10.0
  num_slots: 10
  slot_assignment_mode: fixed
  fixed_slot_map:
    node1: [0, 5]  # 2 slots → 20% of frame (2ms per 10ms)
    node2: [1, 6]  # 2 slots → 20%
    node3: [2, 7]  # 2 slots → 20%
```

**PHY Layer** (same as WiFi for comparison):
- Bandwidth: 80 MHz
- Modulation: 64-QAM
- FEC: LDPC rate-2/3
- **Theoretical PHY rate**: 480 Mbps

**MAC Layer (TDMA)**:
- Node1 owns slots [0, 5] → transmits 2ms out of 10ms
- **Effective throughput**: 480 Mbps × 0.2 = **96 Mbps**

**iperf3 measurement**:
```bash
docker exec clab-tdma-node1 iperf3 -c 192.168.100.2 -t 10
# Expected: ~90-95 Mbps (95-99% of 96 Mbps theoretical)
# Protocol overhead accounts for 1-5% loss
```

Compare to **CSMA/CA with same PHY**:
```bash
docker exec clab-csma-node1 iperf3 -c 192.168.100.2 -t 10
# Expected: ~400-450 Mbps (80-90% of 480 Mbps theoretical)
# Spatial reuse allows concurrent transmissions
```

**CSMA is ~4× faster**, but TDMA provides **zero collisions** and **deterministic latency**.

#### Throughput Validation Tests

**Test 1: TDMA Fixed Slots (20% ownership)**
```python
def test_tdma_throughput_matches_slot_ownership():
    """Verify TDMA throughput equals slot ownership fraction."""
    # Deploy 3-node TDMA with fixed slots
    config = TDMAConfig(
        slot_assignment_mode="fixed",
        num_slots=10,
        fixed_slot_map={
            "node1": [0, 5],  # 20% ownership
            "node2": [1, 6],  # 20%
            "node3": [2, 7],  # 20%
        }
    )

    # PHY rate: 480 Mbps (80 MHz, 64-QAM, rate-2/3)
    # Expected rate: 480 × 0.2 = 96 Mbps

    # Run iperf3
    throughput_mbps = run_iperf3("node1", "node2", duration_sec=30)

    # Expected: 90-96 Mbps (95-100% of theoretical)
    assert 90 <= throughput_mbps <= 96, \
        f"TDMA throughput {throughput_mbps} Mbps not within 90-96 Mbps range"

    # Verify throughput is ~20% of PHY rate (±5%)
    expected = 96
    tolerance = 5  # Mbps
    assert abs(throughput_mbps - expected) < tolerance
```

**Test 2: TDMA Round-Robin (33.3% ownership)**
```python
def test_tdma_round_robin_throughput():
    """Verify round-robin gives equal throughput per node."""
    config = TDMAConfig(
        slot_assignment_mode="round_robin",
        num_slots=12,  # 3 nodes × 4 slots each
    )

    # PHY rate: 480 Mbps
    # Expected per node: 480 × (4/12) = 160 Mbps

    throughput_mbps = run_iperf3("node1", "node2", duration_sec=30)

    # Expected: 152-160 Mbps (95-100% of theoretical)
    assert 152 <= throughput_mbps <= 160
```

**Test 3: CSMA vs TDMA Throughput Comparison**
```python
def test_csma_vs_tdma_throughput():
    """Verify CSMA achieves higher throughput than TDMA for same PHY."""
    # Same PHY for both: 80 MHz, 64-QAM, rate-2/3 → 480 Mbps theoretical

    # CSMA deployment
    csma_throughput = run_iperf3_with_config("examples/sinr_csma/network.yaml")
    # Expected: 400-450 Mbps (80-90% spatial reuse)

    # TDMA deployment (20% slots)
    tdma_throughput = run_iperf3_with_config("examples/sinr_tdma_fixed/network.yaml")
    # Expected: 90-96 Mbps (20% slot ownership)

    # CSMA should be 4-5× faster
    ratio = csma_throughput / tdma_throughput
    assert 4.0 <= ratio <= 5.0, \
        f"CSMA/TDMA ratio {ratio:.1f} not in expected 4-5× range"

    # Both should achieve >95% of their respective theoretical max
    assert csma_throughput > 400  # >95% of 420 Mbps (480 × 0.88)
    assert tdma_throughput > 90   # >95% of 96 Mbps
```

**Test 4: TDMA Throughput Matches netem Rate Limit**
```python
def test_tdma_netem_rate_applied():
    """Verify netem rate limit matches TDMA slot ownership."""
    # Deploy TDMA topology
    deploy("examples/sinr_tdma_fixed/network.yaml")

    # Query netem configuration
    netem_info = get_netem_info("clab-tdma-node1", "eth1")

    # Expected rate limit: 96 Mbps (480 Mbps × 0.2)
    expected_rate_kbps = 96 * 1000
    actual_rate_kbps = netem_info["rate_kbps"]

    # Verify within ±5%
    tolerance = expected_rate_kbps * 0.05
    assert abs(actual_rate_kbps - expected_rate_kbps) < tolerance, \
        f"netem rate {actual_rate_kbps} kbps != expected {expected_rate_kbps} kbps"

    # Verify iperf3 respects netem rate
    throughput_mbps = run_iperf3("node1", "node2", duration_sec=30)
    assert throughput_mbps <= 96  # Cannot exceed netem rate limit
```

**Test 5: SINR vs Throughput (TDMA Orthogonal Slots)**
```python
def test_tdma_orthogonal_slots_sinr_equals_snr():
    """Verify orthogonal TDMA slots have SINR = SNR (zero interference)."""
    # Deploy TDMA with orthogonal slots
    result = deploy_and_measure("examples/sinr_tdma_fixed/network.yaml")

    # Expected: SINR = SNR (no interference from orthogonal slots)
    for link in result["links"]:
        sinr_db = link["sinr_db"]
        snr_db = link["snr_db"]

        # SINR should equal SNR (±0.5 dB tolerance)
        assert abs(sinr_db - snr_db) < 0.5, \
            f"Link {link['name']}: SINR {sinr_db} != SNR {snr_db} (expected equal)"

        # Throughput should match slot ownership (not degraded by interference)
        throughput_mbps = link["throughput_mbps"]
        expected_throughput = link["phy_rate_mbps"] * 0.2  # 20% slots

        assert abs(throughput_mbps - expected_throughput) < 5  # ±5 Mbps tolerance
```

#### Integration Test Script

**`tests/integration/test_mac_throughput.py`**:
```python
#!/usr/bin/env python3
"""
Integration tests for CSMA and TDMA MAC layer throughput validation.

Verifies that:
1. TDMA throughput matches slot ownership fraction
2. CSMA throughput achieves high spatial reuse (80-90%)
3. netem rate limits are correctly applied
4. SINR calculations match expected MAC behavior
"""

import subprocess
import re
import pytest


def deploy_topology(yaml_path: str):
    """Deploy topology using sine CLI."""
    cmd = ["sudo", "uv", "run", "sine", "deploy", yaml_path]
    subprocess.run(cmd, check=True, capture_output=True)


def destroy_topology(yaml_path: str):
    """Destroy topology."""
    cmd = ["sudo", "uv", "run", "sine", "destroy", yaml_path]
    subprocess.run(cmd, check=True, capture_output=True)


def run_iperf3(container_src: str, ip_dst: str, duration_sec: int = 30) -> float:
    """Run iperf3 and return throughput in Mbps."""
    # Start iperf3 server on destination (background)
    cmd_server = ["docker", "exec", "-d", container_src.replace("node1", "node2"),
                  "iperf3", "-s"]
    subprocess.run(cmd_server, check=True)

    # Run iperf3 client
    cmd_client = [
        "docker", "exec", container_src,
        "iperf3", "-c", ip_dst, "-t", str(duration_sec), "-J"
    ]
    result = subprocess.run(cmd_client, check=True, capture_output=True, text=True)

    # Parse JSON output for throughput
    import json
    data = json.loads(result.stdout)
    throughput_bps = data["end"]["sum_received"]["bits_per_second"]
    throughput_mbps = throughput_bps / 1e6

    return throughput_mbps


@pytest.fixture
def tdma_topology():
    """Deploy and cleanup TDMA topology."""
    yaml_path = "examples/sinr_tdma_fixed/network.yaml"
    deploy_topology(yaml_path)
    yield
    destroy_topology(yaml_path)


@pytest.fixture
def csma_topology():
    """Deploy and cleanup CSMA topology."""
    yaml_path = "examples/sinr_csma/network.yaml"
    deploy_topology(yaml_path)
    yield
    destroy_topology(yaml_path)


def test_tdma_throughput_20_percent(tdma_topology):
    """Test TDMA with 20% slot ownership achieves expected throughput."""
    # Expected: 96 Mbps (480 Mbps PHY × 0.2 slots)
    throughput = run_iperf3("clab-sinr-tdma-fixed-node1", "192.168.100.2", 30)

    assert 90 <= throughput <= 96, \
        f"TDMA throughput {throughput:.1f} Mbps outside 90-96 Mbps range"


def test_csma_throughput_spatial_reuse(csma_topology):
    """Test CSMA achieves high throughput via spatial reuse."""
    # Expected: 400-450 Mbps (480 Mbps PHY × 0.8-0.9 spatial reuse)
    throughput = run_iperf3("clab-sinr-csma-node1", "192.168.100.2", 30)

    assert 400 <= throughput <= 450, \
        f"CSMA throughput {throughput:.1f} Mbps outside 400-450 Mbps range"


def test_csma_vs_tdma_ratio():
    """Test CSMA is 4-5× faster than TDMA for same PHY."""
    # Deploy both topologies sequentially
    deploy_topology("examples/sinr_csma/network.yaml")
    csma_throughput = run_iperf3("clab-sinr-csma-node1", "192.168.100.2", 30)
    destroy_topology("examples/sinr_csma/network.yaml")

    deploy_topology("examples/sinr_tdma_fixed/network.yaml")
    tdma_throughput = run_iperf3("clab-sinr-tdma-fixed-node1", "192.168.100.2", 30)
    destroy_topology("examples/sinr_tdma_fixed/network.yaml")

    ratio = csma_throughput / tdma_throughput
    assert 4.0 <= ratio <= 5.0, \
        f"CSMA/TDMA ratio {ratio:.1f} not in expected 4-5× range"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

**Usage**:
```bash
# Run throughput validation tests
uv run pytest tests/integration/test_mac_throughput.py -v

# Expected output:
# test_tdma_throughput_20_percent PASSED (throughput: 94.2 Mbps)
# test_csma_throughput_spatial_reuse PASSED (throughput: 423.7 Mbps)
# test_csma_vs_tdma_ratio PASSED (ratio: 4.5×)
```

---

### Phase 2: Adjacent-Channel Interference

**Goal**: Model partial interference from nearby frequencies with ACLR rejection

**New Components**:

1. **ACLR calculation** in `SINRCalculator`
   - IEEE 802.11ax-compliant ACLR model (0, 28, 40, 45 dB)
   - Configurable per-topology for non-WiFi systems

   ```python
   def calculate_aclr_wifi6(delta_f_mhz: float, bw_mhz: float = 20) -> float:
       """Calculate ACLR per IEEE 802.11ax-2021 spectrum mask."""
       abs_delta = abs(delta_f_mhz)

       if abs_delta < 0.5 * bw_mhz:
           return 0.0  # Co-channel
       elif abs_delta < 1.5 * bw_mhz:
           return 28.0  # First adjacent (802.11ax spec: ≥28 dBr)
       elif abs_delta < 2.5 * bw_mhz:
           return 40.0  # Second adjacent
       else:
           return 45.0  # Orthogonal (realistic, not 60 dB)
   ```

**Modified Components**:

2. **`src/sine/channel/interference_engine.py`** (MODIFIED)
   - Multi-frequency support (PathSolver with ACLR per interferer)
   - ACLR application to interference terms before aggregation

3. **Optional: Capture effect** (Enhancement)
   ```python
   def apply_capture_effect(
       signal_power_dbm: float,
       interference_list: list[float],
       capture_threshold_db: float = 6.0
   ) -> list[float]:
       """
       Apply capture effect: ignore interference weaker than signal by threshold.
       WiFi typical capture threshold: 4-6 dB.
       """
       filtered = [
           I_dbm for I_dbm in interference_list
           if signal_power_dbm - I_dbm < capture_threshold_db
       ]
       return filtered
   ```

4. **Regime detection** (Diagnostic)
   ```python
   # Log whether link is noise-limited or interference-limited
   if total_interference_dbm < noise_dbm - 10:
       regime = "noise-limited"
   elif total_interference_dbm > noise_dbm + 10:
       regime = "interference-limited"
   else:
       regime = "mixed"
   ```

5. **`src/sine/emulation/controller.py`** (MODIFIED)
   - Process multiple frequency groups
   - Cross-group interference calculation (with ACLR)
   - Path caching for static topologies (performance optimization)

**Testing**:
- Unit tests: ACLR for various Δf values
- Integration: 3-node mixed-frequency (`examples/sinr_adjacent/`)
  - Node1: 5.18 GHz, Node2: 5.20 GHz (adjacent, 28 dB rejection per 802.11ax)
  - Node3: 5.26 GHz (2nd adjacent, 40 dB rejection)
- Validation: Graded interference based on frequency separation
- Optional: Test capture effect (strong signal suppresses weak interference)

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

**Goal**: Automatically track which nodes are transmitting and update SINR dynamically

This phase implements three complementary approaches for detecting transmission states:
- **3A: Manual API Control** (baseline, always available)
- **3B: Rate-Based Auto-Detection** (optional, for autonomous operation)
- **3C: Application-Layer Signaling** (advanced, for MANET protocol integration)

---

#### Phase 3A: Manual API Control (Baseline)

**Goal**: External control of transmission states for controlled experiments

**New Components**:

1. **Transmission state API** in `server.py`
   ```python
   class TransmissionStateUpdate(BaseModel):
       states: dict[str, bool]  # {node_name: is_transmitting}

   @app.post("/api/transmission/state")
   async def update_transmission_state(request: TransmissionStateUpdate):
       """Manually set transmission states for specific nodes."""
       updated_nodes = []
       for node_name, is_tx in request.states.items():
           if _transmission_states.get(node_name) != is_tx:
               _transmission_states[node_name] = is_tx
               updated_nodes.append(node_name)

       if updated_nodes:
           await _recompute_sinr_for_affected_links(updated_nodes)

       return {"status": "ok", "updated": updated_nodes}

   @app.get("/api/transmission/state")
   async def get_transmission_state():
       """Get current transmission states for all nodes."""
       return {"states": _transmission_states}
   ```

2. **Rate limiting** (`src/sine/topology/netem_scheduler.py`)
   ```python
   class NetemUpdateScheduler:
       """Rate-limit netem updates to prevent thrashing."""

       def __init__(self, min_interval_sec=0.1, sinr_hysteresis_db=2.0):
           # Changed: 100ms interval (not 1 sec) to match MANET protocol timescales
           # Changed: 2 dB hysteresis (not 3 dB) for better responsiveness
           self.min_interval_sec = min_interval_sec
           self.sinr_hysteresis_db = sinr_hysteresis_db
           self._last_update: dict[tuple[str, str], float] = {}
           self._last_sinr: dict[tuple[str, str], float] = {}

       def should_update(self, tx_node: str, rx_node: str, new_sinr_db: float) -> bool:
           """Check if netem should be updated for this link."""
           link_key = (tx_node, rx_node)
           now = time.time()

           # Check time interval (100ms = 10 Hz max update rate)
           last_time = self._last_update.get(link_key, 0)
           if now - last_time < self.min_interval_sec:
               return False

           # Check SINR hysteresis
           last_sinr = self._last_sinr.get(link_key)
           if last_sinr is not None:
               sinr_delta = abs(new_sinr_db - last_sinr)
               if sinr_delta < self.sinr_hysteresis_db:
                   return False

           # Update allowed
           self._last_update[link_key] = now
           self._last_sinr[link_key] = new_sinr_db
           return True
   ```

**Modified Components**:

3. **`src/sine/channel/interference_engine.py`** (MODIFIED)
   ```python
   def compute_interference_for_frequency_group(
       self,
       transmitters: list[TransmitterInfo],
       rx_positions: dict[str, tuple],
       active_tx_states: dict[str, bool]  # NEW parameter
   ):
       """Compute interference only from active transmitters."""
       # Filter to only active transmitters
       active_transmitters = [
           tx for tx in transmitters
           if active_tx_states.get(tx.node_name, True)  # Default: transmitting
       ]

       if not active_transmitters:
           logger.warning("No active transmitters in frequency group")
           return {}

       # ... rest of RadioMapSolver computation with active_transmitters only
   ```

4. **`src/sine/emulation/controller.py`** (MODIFIED)
   ```python
   async def _recompute_sinr_for_affected_links(
       self, changed_nodes: list[str]
   ) -> None:
       """Incrementally recompute SINR for links affected by state change."""
       # Identify affected links (where changed_node is TX or neighbor of RX)
       affected_links = []
       for tx_node, rx_node in self._all_links:
           if tx_node in changed_nodes or rx_node in changed_nodes:
               affected_links.append((tx_node, rx_node))

       logger.info(f"State change affects {len(affected_links)} links")

       # Recompute SINR for affected links only
       for tx_node, rx_node in affected_links:
           result = await self._compute_sinr_for_link(
               tx_node, rx_node, self._current_tx_states
           )

           # Check rate limiting before applying netem
           if self.netem_scheduler.should_update(tx_node, rx_node, result.sinr_db):
               await self._apply_netem_update(tx_node, rx_node, result)
   ```

**Testing**:
- Unit tests: State update API, rate limiting, hysteresis
- Integration: Toggle node TX states, verify SINR updates
- Stress: Rapid state changes (>10 Hz), verify no thrashing

**Usage Example**:
```bash
# Deploy with dynamic state API enabled
sudo $(which uv) run sine deploy examples/sinr_dynamic/network.yaml

# Check current states
curl http://localhost:8000/api/transmission/state

# Node2 stops transmitting
curl -X POST http://localhost:8000/api/transmission/state \
  -H "Content-Type: application/json" \
  -d '{"states": {"node2": false}}'

# SINR for node1→node3 improves (one less interferer)
# Netem updates automatically (rate-limited to 10 Hz / 100ms, 2 dB hysteresis)

# Resume node2 transmission
curl -X POST http://localhost:8000/api/transmission/state \
  -d '{"states": {"node2": true}}'
```

---

#### Phase 3B: Rate-Based Auto-Detection (Optional)

**Goal**: Automatically detect transmission state from interface traffic rates

This eliminates manual intervention for autonomous MANET operation.

**New Components**:

1. **Traffic monitor** (`src/sine/channel/transmission_detector.py`, NEW)
   ```python
   class RateBasedTransmissionDetector:
       """Detect transmission state from interface traffic rate."""

       def __init__(
           self,
           clab_manager: ContainerlabManager,
           tx_threshold_kbps: float = 100.0,  # Changed: 100 kbps (not 10 kbps)
           poll_interval_sec: float = 0.1,
       ):
           # Note: 10 kbps is too low - WiFi control frames generate ~10-50 kbps
           # when idle. 100 kbps threshold = meaningful data traffic.
           self.clab_manager = clab_manager
           self.threshold_kbps = tx_threshold_kbps
           self.poll_interval = poll_interval_sec
           self._prev_tx_bytes: dict[str, int] = {}
           self._current_states: dict[str, bool] = {}
           self._state_change_callbacks: list[Callable] = []

       def register_callback(self, callback: Callable[[dict[str, bool]], None]):
           """Register callback for state changes."""
           self._state_change_callbacks.append(callback)

       async def start_monitoring(self, nodes: list[str], interface: str = "eth1"):
           """Start monitoring interface statistics."""
           logger.info(f"Starting transmission detection for {len(nodes)} nodes")

           while True:
               changed_states = {}

               for node_name in nodes:
                   # Read TX byte counter from container
                   current_bytes = await self._get_tx_bytes(node_name, interface)
                   prev_bytes = self._prev_tx_bytes.get(node_name, current_bytes)

                   # Calculate rate over poll interval
                   bytes_delta = current_bytes - prev_bytes
                   rate_kbps = (bytes_delta / self.poll_interval) * 8 / 1000

                   # Determine new state
                   is_transmitting = rate_kbps > self.threshold_kbps
                   prev_state = self._current_states.get(node_name)

                   # Detect state change
                   if prev_state is None or is_transmitting != prev_state:
                       self._current_states[node_name] = is_transmitting
                       changed_states[node_name] = is_transmitting
                       logger.debug(
                           f"{node_name}: {'TX' if is_transmitting else 'IDLE'} "
                           f"({rate_kbps:.1f} kbps)"
                       )

                   self._prev_tx_bytes[node_name] = current_bytes

               # Notify callbacks of state changes
               if changed_states:
                   for callback in self._state_change_callbacks:
                       await callback(changed_states)

               await asyncio.sleep(self.poll_interval)

       async def _get_tx_bytes(self, node_name: str, interface: str) -> int:
           """Get TX byte counter from container interface."""
           container = self.clab_manager.get_container_info(node_name)
           cmd = f"cat /sys/class/net/{interface}/statistics/tx_bytes"

           result = subprocess.run(
               ["sudo", "nsenter", "-t", str(container.pid), "-n", "sh", "-c", cmd],
               capture_output=True,
               text=True,
           )

           return int(result.stdout.strip())
   ```

**Modified Components**:

2. **`src/sine/emulation/controller.py`** (MODIFIED)
   ```python
   async def start(self):
       """Start emulation with optional auto-detection."""
       # ... existing deployment code ...

       # Start auto-detection if enabled
       if self.config.topology.transmission_state.enable_auto_detection:
           self.tx_detector = RateBasedTransmissionDetector(
               self.clab_manager,
               tx_threshold_kbps=self.config.topology.transmission_state.tx_threshold_kbps,
           )

           # Register callback for state changes
           self.tx_detector.register_callback(self._on_transmission_state_change)

           # Start monitoring in background
           nodes = list(self.config.topology.nodes.keys())
           asyncio.create_task(
               self.tx_detector.start_monitoring(nodes, interface_name="eth1")
           )
           logger.info("Transmission auto-detection started")

   async def _on_transmission_state_change(self, changed_states: dict[str, bool]):
       """Callback when transmission states change."""
       logger.info(f"Auto-detected state change: {changed_states}")

       # Update internal state
       self._current_tx_states.update(changed_states)

       # Recompute SINR for affected links
       await self._recompute_sinr_for_affected_links(list(changed_states.keys()))
   ```

**Configuration Schema**:
```yaml
topology:
  transmission_state:
    enable_auto_detection: bool = false  # Enable rate-based detection
    tx_threshold_kbps: float = 100.0     # Rate threshold (100 kbps, not 10)
    poll_interval_sec: float = 0.1       # Polling frequency (100ms)
```

**Alternative: Packet-rate based detection** (more robust):
```python
# Option: Use packet rate instead of byte rate
tx_packets_per_sec = (current_packets - prev_packets) / poll_interval
is_transmitting = tx_packets_per_sec > 10  # >10 pps = active
```

**Testing**:
- Unit tests: Byte counter reading, rate calculation, state detection
- Integration: Generate traffic with iperf, verify auto-detection
- Validation: Compare auto-detected states vs actual traffic patterns

**Usage Example**:
```bash
# Deploy with auto-detection enabled
sudo $(which uv) run sine deploy examples/sinr_auto/network.yaml

# topology.transmission_state.enable_auto_detection: true

# Start traffic on node1
docker exec clab-sinr-auto-node1 iperf3 -c 192.168.100.2 -t 10 &

# SiNE automatically detects node1 transmitting
# SINR for node2→node3 degrades (interference from node1)
# When iperf finishes, node1 detected as idle
# SINR for node2→node3 improves back
```

**Pros**:
- Fully automatic, no manual intervention
- Works with any traffic source (routing protocols, apps, tests)
- Robust to packet bursts (rate averaging)

**Cons**:
- 100ms detection latency
- Requires defining "transmitting" threshold (configurable)
- Doesn't capture MAC-layer scheduling details

---

#### Phase 3C: Application-Layer Signaling (Advanced)

**Goal**: Explicit signaling from MANET routing protocols for accurate transmission windows

This is most accurate for scheduled access protocols (TDMA, polling, etc.).

**Integration Approach**:

MANET routing daemons (OLSR, BATMAN, Babel) or custom applications explicitly signal transmission windows:

```python
# Example: OLSR daemon integration
import requests

class SiNETransmissionSignaler:
    """Signal transmission state to SiNE channel server."""

    def __init__(self, node_name: str, channel_server_url: str = "http://localhost:8000"):
        self.node_name = node_name
        self.server_url = channel_server_url

    def start_transmission(self):
        """Signal that this node is about to transmit."""
        try:
            requests.post(
                f"{self.server_url}/api/transmission/state",
                json={"states": {self.node_name: True}},
                timeout=0.1,
            )
        except Exception as e:
            logger.debug(f"Failed to signal TX start: {e}")

    def stop_transmission(self):
        """Signal that this node finished transmitting."""
        try:
            requests.post(
                f"{self.server_url}/api/transmission/state",
                json={"states": {self.node_name: False}},
                timeout=0.1,
            )
        except Exception as e:
            logger.debug(f"Failed to signal TX stop: {e}")

# Usage in OLSR route update
def broadcast_hello():
    signaler.start_transmission()
    send_hello_packet()
    signaler.stop_transmission()
```

**Docker Image Integration**:

Include signaler library in `docker/sine-node/Dockerfile`:
```dockerfile
FROM alpine:latest

# Install Python for signaling
RUN apk add --no-cache python3 py3-requests

# Copy SiNE signaler library
COPY sine_signaler.py /usr/local/lib/python3.12/site-packages/
```

**Configuration**:
```yaml
topology:
  transmission_state:
    enable_app_signaling: bool = true
    fallback_to_auto_detection: bool = true  # Use rate-based if no signals
```

**Testing**:
- Integration: Modified OLSR daemon with signaling
- Validation: Compare signaled states vs actual packet transmission
- Timing: Measure signaling latency (<1ms)

**Usage Example**:
```bash
# Deploy with app signaling
sudo $(which uv) run sine deploy examples/sinr_olsr/network.yaml

# Inside container, OLSR daemon uses signaler
docker exec clab-sinr-olsr-node1 cat /etc/olsrd/olsrd.conf
# ... plugin "sine_signaler.so" enabled

# OLSR broadcasts use explicit TX windows
# SINR computed with precise interference timing
```

**Pros**:
- Most accurate (protocol knows exactly when transmitting)
- Low overhead (only API call on TX start/stop)
- Works perfectly with scheduled protocols (TDMA, polling)

**Cons**:
- Requires application/protocol modification
- Not transparent
- Doesn't work for arbitrary traffic (need auto-detection fallback)

---

### Phase 3 Summary: Hybrid Approach

**Recommended Configuration**:

```yaml
topology:
  enable_sinr: true

  transmission_state:
    # Phase 3A: Manual API (always available)
    default_all_transmitting: bool = false  # Start with all idle

    # Phase 3B: Auto-detection (optional)
    enable_auto_detection: bool = true      # Enable for autonomous operation
    tx_threshold_kbps: float = 100.0        # 100 kbps threshold (not 10 kbps)
    poll_interval_sec: float = 0.1

    # Phase 3C: App signaling (advanced)
    enable_app_signaling: bool = false      # Enable if apps support it
    fallback_to_auto_detection: bool = true  # Fall back if no signals
```

**Decision Logic**:
1. If app sends explicit signal → use signaled state (most accurate)
2. Else if auto-detection enabled → use rate-based state
3. Else → use manual API state (default: all transmitting if not set)

**Implementation Priority**:
1. **Phase 3A** (Week 4): Manual API - baseline functionality
2. **Phase 3B** (Week 5): Auto-detection - autonomous operation
3. **Phase 3C** (Future): App signaling - when MANET protocols integrated

## Critical Files

### Phase 0: PathSolver Engine

| File | Type | Purpose |
|------|------|---------|
| [src/sine/channel/interference_engine.py](src/sine/channel/interference_engine.py) | NEW | Multi-TX interference using PathSolver (NOT RadioMapSolver) |
| [tests/test_interference_engine.py](tests/test_interference_engine.py) | NEW | Validate PathSolver approach vs theory |

### Phase 1: Same-Frequency SINR

| File | Type | Purpose |
|------|------|---------|
| [src/sine/channel/sinr.py](src/sine/channel/sinr.py) | NEW | SINR calculation with interference aggregation |
| [src/sine/channel/interference_engine.py](src/sine/channel/interference_engine.py) | MODIFIED | Add active TX state filtering |
| [src/sine/channel/frequency_groups.py](src/sine/channel/frequency_groups.py) | NEW | Frequency grouping utilities |
| [src/sine/channel/server.py](src/sine/channel/server.py) | MODIFIED | Add `/compute/sinr` endpoint |
| [src/sine/emulation/controller.py](src/sine/emulation/controller.py) | MODIFIED | SINR-aware link orchestration |
| [src/sine/config/schema.py](src/sine/config/schema.py) | MODIFIED | Add `enable_sinr`, `rx_sensitivity_dbm` fields |

### Phase 1.5: CSMA/CA Model

| File | Type | Purpose |
|------|------|---------|
| [src/sine/channel/csma_model.py](src/sine/channel/csma_model.py) | NEW | CSMA/CA statistical model (carrier sense, hidden nodes) |
| [src/sine/channel/sinr.py](src/sine/channel/sinr.py) | MODIFIED | Add `calculate_sinr_with_csma()` method |
| [src/sine/config/schema.py](src/sine/config/schema.py) | MODIFIED | Add `CSMAConfig` class |
| [tests/test_csma_model.py](tests/test_csma_model.py) | NEW | Unit tests for CSMA vs all-TX comparison |
| [examples/sinr_csma/](examples/sinr_csma/) | NEW | Example topology with CSMA model |

### Phase 1.6: TDMA Model

| File | Type | Purpose |
|------|------|---------|
| [src/sine/channel/tdma_model.py](src/sine/channel/tdma_model.py) | NEW | TDMA statistical model (fixed/round-robin/random/distributed slots) |
| [src/sine/channel/sinr.py](src/sine/channel/sinr.py) | MODIFIED | Add `calculate_sinr_with_tdma()` method |
| [src/sine/config/schema.py](src/sine/config/schema.py) | MODIFIED | Add `TDMAConfig` class with slot assignment modes |
| [tests/test_tdma_model.py](tests/test_tdma_model.py) | NEW | Unit tests for TDMA vs CSMA/all-TX comparison |
| [tests/integration/test_mac_throughput.py](tests/integration/test_mac_throughput.py) | NEW | Integration tests for CSMA/TDMA throughput validation (iperf3) |
| [examples/sinr_tdma_fixed/](examples/sinr_tdma_fixed/) | NEW | Example topology with TDMA fixed slot assignment |
| [examples/sinr_tdma_roundrobin/](examples/sinr_tdma_roundrobin/) | NEW | Example topology with TDMA round-robin |

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

  # ACLR configuration (optional, IEEE 802.11ax defaults)
  aclr_config:
    co_channel_db: 0.0
    adjacent_db: 28.0          # Changed: 28 dB per 802.11ax spec (not 20 dB)
    second_adjacent_db: 40.0
    orthogonal_db: 45.0        # Changed: 45 dB realistic (not 60 dB)

  # Receiver sensitivity (optional, WiFi 6 default)
  rx_sensitivity_dbm: -80.0    # NEW: Minimum detectable signal

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
- PathSolver integration (NOT RadioMapSolver)
- Multi-TX interference computation
- Interference aggregation (linear domain)
- Antenna gain inclusion (TX and RX)
- Validation against Friis equation (free space)

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

## Implementation Order (Revised with Phase 0, 1.5, and 1.6)

### Week 1: Phase 0 - Core Interference Engine Validation
1. Create `InterferenceEngine` class using PathSolver (interference_engine.py)
2. Implement per-interferer path computation with antenna gains
3. Unit tests: 2-node free-space vs Friis equation (±0.5 dB)
4. Integration test: 3-node triangle, verify aggregation
5. Performance benchmark: N=5, 10, 20 nodes (<500ms target)

**Critical**: Validates PathSolver approach before building SINR complexity

### Week 2: Phase 1 Core Infrastructure
6. Create `SINRCalculator` class (sinr.py)
7. Add rx_sensitivity check (reject links below -80 dBm)
8. Create `FrequencyGroup` utilities (frequency_groups.py)
9. Unit tests for SINR calculation

### Week 3: Phase 1 Integration
10. Add `/compute/sinr` endpoint to channel server
11. Modify controller for SINR orchestration
12. Add `enable_sinr`, `rx_sensitivity_dbm` config fields
13. Integration test for 3-node same-frequency (all-TX worst-case)

### Week 3.5: Phase 1.5 - CSMA/CA Statistical Model (NEW)
14. Create `CSMAModel` class (csma_model.py)
15. Add `calculate_sinr_with_csma()` to SINRCalculator
16. Add `CSMAConfig` to schema
17. Unit tests: CSMA vs all-TX (≥5 dB improvement expected)
18. Integration test: Hidden node scenario (3-node linear)
19. Create `examples/sinr_csma/` topology

**Critical**: Realistic WiFi MANET behavior (replaces pessimistic all-TX assumption)

### Week 4: Phase 1.6 - TDMA Statistical Model (NEW)
20. Create `TDMAModel` class (tdma_model.py)
21. Add `calculate_sinr_with_tdma()` to SINRCalculator
22. Add `TDMAConfig` to schema with slot assignment modes
23. Unit tests: TDMA orthogonality, vs CSMA comparison (≥3 dB improvement)
24. Integration tests: Fixed slots, round-robin, random, distributed modes
25. Create `examples/sinr_tdma_fixed/` and `examples/sinr_tdma_roundrobin/` topologies
26. Throughput validation tests (slot ownership fraction)

**Critical**: Realistic military MANET behavior (TDMA-based MAC)

### Week 5: Phase 2 Adjacent-Channel
27. Implement IEEE 802.11ax ACLR calculation (28/40/45 dB)
28. Multi-frequency support in InterferenceEngine
29. Frequency grouping in controller (dual thresholds: 50 MHz, 100 MHz)
30. Optional: Capture effect (6 dB threshold)
31. Integration test for mixed-frequency

### Week 6: Phase 3A Manual API Control
32. State storage + API endpoint
33. Rate limiting scheduler (100ms / 10 Hz, 2 dB hysteresis)
34. State change event handling
35. Stress testing (rapid toggles)

### Week 7: Phase 3B Auto-Detection
36. Traffic monitor (100 kbps threshold, not 10 kbps)
37. Callback integration
38. Integration test with iperf
39. Optional: Packet-rate detection alternative

### Week 7.5: Integration and Validation (NEW)
40. End-to-end testing: CSMA + TDMA + ACLR + dynamic states
41. Performance tuning: Path caching, TF batching
42. Documentation: Update README with CSMA and TDMA model explanations
43. Example refinement: Ensure all examples work with both MAC models
44. Comparative analysis: CSMA vs TDMA performance characteristics

## Performance Optimization

**Critical for N² PathSolver calls**:

### 1. Path Caching (Static Topologies)
```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_cached_paths(tx_pos: tuple, rx_pos: tuple) -> Paths:
    """Cache PathSolver results for static node positions."""
    return path_solver(tx_pos, rx_pos)

# Clear cache when nodes move
def on_node_move(node_name):
    get_cached_paths.cache_clear()
```

### 2. Incremental Updates (Mobility)
```python
# When one node moves, only recompute paths involving that node
def on_node_move(moved_node):
    affected_links = [
        (tx, rx) for tx, rx in all_links
        if tx == moved_node or rx == moved_node
    ]
    # Recompute only affected links, not all N²
```

### 3. TensorFlow Batching (Parallel Paths)
```python
# Batch PathSolver calls for GPU acceleration
all_tx_positions = tf.stack([tx_pos_1, tx_pos_2, ...])
all_rx_positions = tf.stack([rx_pos_1, rx_pos_2, ...])
batch_paths = path_solver(all_tx_positions, all_rx_positions)
```

### 4. Lazy Evaluation (Phase 3B)
```python
# Only compute SINR for links with active traffic
if not has_traffic(tx_node, rx_node):
    skip_sinr_computation()
```

**Expected Performance**:
- Static 10-node MANET: <500ms initial computation, cached thereafter
- Mobile 10-node MANET: ~50ms per node move (incremental)
- 20-node MANET: ~2-3s initial (acceptable for emulation startup)

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| PathSolver N² calls too slow | High | Cache paths for static topologies; use TF batching |
| Interference computation overhead | Medium | Frequency grouping (only compute within 50 MHz); parallel paths |
| Netem update thrashing | Medium | Rate limiting + hysteresis (100ms / 10 Hz, 2 dB) |
| ACLR model inaccurate for non-WiFi | Low | Make ACLR configurable per-topology (already in schema) |
| Backward compatibility breaks | High | Feature flag: `enable_sinr=false` by default |
| Antenna gain missing in interference | Medium | Explicit inclusion in formula (Phase 0 validation) |

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
- **Per-subcarrier SINR**: OFDM-aware frequency-selective fading
- **Enhanced CSMA model**: Exponential backoff, RTS/CTS, frame aggregation

---

## Appendix: Wireless Communications Engineer Review Summary

**Review Date**: 2026-01-16
**Reviewer**: Claude wireless-comms-engineer agent (agentId: ace9446)
**Overall Assessment**: 75% sound, proceed with critical fixes

### Critical Issues Fixed

1. **RadioMapSolver → PathSolver** (CRITICAL)
   - **Issue**: RadioMapSolver designed for coverage grids, not link-level SINR
   - **Fix**: Use PathSolver iteratively for each interferer
   - **Impact**: Added Phase 0 for validation

2. **ACLR Values Incorrect** (IMPORTANT)
   - **Issue**: 20/40/60 dB not aligned with IEEE 802.11ax spec
   - **Fix**: Use 28/40/45 dB per standard
   - **Impact**: More realistic adjacent-channel suppression

3. **Missing Antenna Gains in Interference** (IMPORTANT)
   - **Issue**: Interference formula didn't include TX/RX gains
   - **Fix**: `I_i = P_tx_i + G_tx_i + G_rx - PL_i - ACLR`
   - **Impact**: Correct interference power calculation

4. **Update Rate Too Slow** (IMPORTANT)
   - **Issue**: 1 Hz too slow for MANET protocols
   - **Fix**: 10 Hz (100ms) to match routing timescales
   - **Impact**: Better responsiveness to state changes

5. **Auto-Detection Threshold Too Low** (MINOR)
   - **Issue**: 10 kbps triggers on WiFi control frames
   - **Fix**: 100 kbps for meaningful data traffic
   - **Impact**: Fewer false positives

### Physical Layer Enhancements Added

- **Receiver sensitivity floor** (-80 dBm)
- **Capture effect** (6 dB threshold, optional)
- **Regime detection** (noise vs interference limited)

### Performance Optimizations Added

- **Path caching** for static topologies
- **Incremental updates** for mobility
- **TensorFlow batching** for parallel computation
- **Lazy evaluation** with auto-detection

### Timeline Impact

- **Original**: 4 weeks (Phases 1-3)
- **Revised**: 6.5 weeks (Phases 0, 1, 1.5, 2, 3A, 3B)
- **Justification**:
  - Phase 0 critical for validating PathSolver approach
  - Phase 1.5 adds realistic WiFi MAC behavior (CSMA/CA statistical model)

### Validation Strategy

**Phase 0 Success Criteria**:
- PathSolver interference matches Friis equation ±0.5 dB
- 10-node MANET: <500ms computation time
- Antenna gains verified in interference terms

**Risk Mitigation**:
- Phase 0 prevents discovering fundamental issues in later phases
- Extra 2 weeks investment saves potential rework

### Recommended Go/No-Go Decision

✅ **PROCEED** with revised plan including Phase 0 validation

---

### Follow-Up Review: CSMA/CA MAC Modeling (2026-01-16)

**User observation**: "WiFi standards avoid [collisions] through use of TDMA i.e. avoid collision through time, not frequency."

**Agent clarification**:
- WiFi uses **CSMA/CA** (not strict TDMA), achieving statistical time-domain separation
- "All nodes transmitting" assumption in Phase 1 is overly pessimistic for WiFi MANETs
- Real WiFi: Nodes defer when medium is sensed busy (carrier sense range ≈ 2.5× communication range)

**Recommendation**: **Add Phase 1.5: CSMA/CA Statistical Model**

**Rationale**:
- ✅ Captures spatial reuse (distant nodes transmit concurrently)
- ✅ Models hidden node problem (nodes beyond CS range can collide)
- ✅ Lightweight (~100 lines, no event simulation)
- ✅ Appropriate for network emulation (not PHY simulation)

**Implementation**:
- Binary carrier sensing: `Pr[interferer TX] = 0` if within CS range, else `traffic_load`
- Expected interference: `sum(Pr[TX_i] × I_i)` instead of worst-case
- Configurable: `carrier_sense_range_multiplier` (default 2.5), `traffic_load` (default 0.3)

**Impact**:
- +0.5 weeks to timeline (2-3 days)
- Significantly more realistic SINR values (5-10 dB improvement over all-TX)
- Better netem parameters for deployment

**Validation**:
- CSMA SINR > all-TX SINR by ≥5 dB (spatial reuse benefit)
- Hidden nodes correctly identified
- iperf3 throughput within 10% of analytical model
