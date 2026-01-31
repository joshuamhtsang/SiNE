# Implementation Plan: Spectral Efficiency Calculator

## Overview
Create a utility script `utilities/calc_spectralefficiency.py` that analyzes network.yaml topologies and computes spectral efficiency metrics for each wireless link.

## Requirements

### Input
- Network topology YAML file (e.g., `examples/vacuum_20m/network.yaml`)
- Running channel server at `http://localhost:8000` (required for ray tracing)

### Output (Rich Table in Terminal)
For each wireless link, display:
1. **Shannon Channel Capacity** (theoretical maximum bit/s/Hz)
2. **Effective Data Rate** (practical Mbps from MCS configuration)
3. **Spectral Efficiency** (bit/s/Hz) with categorization:
   - High: 4-6 b/s/Hz (excellent WiFi, high SNR)
   - Medium: 1-4 b/s/Hz (typical WiFi)
   - Low: 0.1-1 b/s/Hz (military/tactical, robust modes)
4. **Shannon Gap** (dB) - Distance from theoretical limit
5. **Link Margin** (dB) - Robustness to fading
6. **BER** (Bit Error Rate)
7. **PER** (Packet Error Rate, assume 1500-byte packets)
8. **Supporting metrics**: SNR, distance, path loss, modulation/coding
9. **Warnings**: Color-coded alerts for unusual conditions

### User Preferences (from questions)
- Output: Rich table (terminal, colored, formatted)
- Computation: Channel server (http://localhost:8000)
- Rate naming: "Effective Rate" (consistent with existing API)

## Implementation Design

### Script Structure

```
utilities/calc_spectralefficiency.py

Functions:
1. main(topology_path: str) -> None
   - Entry point, orchestrates the workflow

2. compute_link_metrics(link, topology, channel_server) -> LinkMetrics
   - Compute all metrics for a single wireless link

3. compute_shannon_capacity(snr_db: float, bandwidth_hz: float) -> dict
   - Shannon capacity: C = BW × log2(1 + SNR_linear)
   - Returns {capacity_bps, spectral_efficiency_bps_hz}

4. compute_shannon_gap(shannon_rate: float, effective_rate: float) -> float
   - Shannon gap: 10 × log₁₀(Shannon / Effective)
   - Quantifies distance from theoretical limit

5. compute_link_margin(snr_db: float, min_snr_db: float | None) -> float | None
   - Link margin: SNR - min_SNR_for_MCS
   - None if fixed MCS (no min_snr_db from MCS table)

6. categorize_spectral_efficiency(spec_eff: float) -> str
   - Categorize as "High", "Medium", or "Low" based on reference values

7. generate_warnings(metrics: LinkMetrics) -> list[str]
   - Generate warning messages for unusual conditions

8. display_results(link_metrics: list[LinkMetrics]) -> None
   - Display results using rich.Table with formatting
```

### Data Structure

```python
@dataclass
class LinkMetrics:
    # Link identification
    endpoint1: str  # "node1:eth1"
    endpoint2: str  # "node2:eth1"
    distance_m: float

    # Channel conditions
    path_loss_db: float
    snr_db: float

    # Shannon theoretical
    shannon_capacity_mbps: float
    shannon_spectral_efficiency: float  # b/s/Hz

    # Effective/practical
    effective_rate_mbps: float
    effective_spectral_efficiency: float  # b/s/Hz
    efficiency_category: str  # "High", "Medium", "Low"

    # Link quality metrics (wireless-comms-engineer recommendations)
    shannon_gap_db: float  # 10 × log₁₀(Shannon / Effective) - distance from theoretical limit
    link_margin_db: float  # SNR - min_SNR_for_MCS - robustness to fading

    # Error rates
    ber: float
    per: float

    # MCS configuration
    modulation: str
    code_rate: float
    fec_type: str
    bandwidth_mhz: float
    min_snr_db: float | None = None  # For MCS table scenarios

    # Warnings
    warnings: list[str] = field(default_factory=list)
```

### Topology Link Discovery

The calculator must support two topology architectures:

**1. Point-to-Point Links (Standard)**
- Explicit links defined in `topology.links`
- Each link specifies endpoints: `[node1:eth1, node2:eth2]`
- Each endpoint has wireless or fixed_netem params

**2. Shared Bridge (MANET)**
- No explicit links (empty `topology.links`)
- Enabled via `topology.shared_bridge`
- All nodes in `shared_bridge.nodes` form a full mesh
- All nodes use the same interface (e.g., `eth1`)

**Link Discovery Algorithm:**

```python
def discover_wireless_links(topology):
    """Discover all wireless links from topology."""
    wireless_links = []

    # Case 1: Shared bridge mode
    if topology.topology.shared_bridge and topology.topology.shared_bridge.enabled:
        nodes = topology.topology.shared_bridge.nodes
        iface_name = topology.topology.shared_bridge.interface_name

        # Generate full mesh of links between all nodes
        for i, node1_name in enumerate(nodes):
            for node2_name in nodes[i+1:]:  # Avoid duplicates
                node1 = topology.topology.nodes.get(node1_name)
                node2 = topology.topology.nodes.get(node2_name)

                if not node1 or not node2:
                    continue

                iface1 = node1.interfaces.get(iface_name)
                iface2 = node2.interfaces.get(iface_name)

                if not iface1 or not iface2:
                    continue

                # Check both are wireless
                if iface1.wireless and iface2.wireless:
                    endpoint1 = f"{node1_name}:{iface_name}"
                    endpoint2 = f"{node2_name}:{iface_name}"
                    wireless_links.append((endpoint1, endpoint2, iface1.wireless, iface2.wireless))

    # Case 2: Explicit point-to-point links
    else:
        for link in topology.topology.links:
            # Parse endpoints (existing logic)
            ep1_parts = link.endpoints[0].split(":")
            ep2_parts = link.endpoints[1].split(":")

            if len(ep1_parts) != 2 or len(ep2_parts) != 2:
                continue

            node1_name, iface1_name = ep1_parts
            node2_name, iface2_name = ep2_parts

            node1 = topology.topology.nodes.get(node1_name)
            node2 = topology.topology.nodes.get(node2_name)

            if not node1 or not node2:
                continue

            iface1 = node1.interfaces.get(iface1_name)
            iface2 = node2.interfaces.get(iface2_name)

            if not iface1 or not iface2:
                continue

            if iface1.wireless and iface2.wireless:
                wireless_links.append((link.endpoints[0], link.endpoints[1], iface1.wireless, iface2.wireless))

    return wireless_links
```

### Computation Pipeline

For each wireless link:
1. **Extract link parameters** from topology YAML
   - TX/RX positions, frequencies, powers, antennas
   - MCS configuration (from MCS table or fixed params)

2. **Compute SNR** via channel server `/compute/single` endpoint
   - Input: TX/RX positions, RF parameters
   - Output: SNR, path loss, received power

3. **Compute Shannon Capacity**
   - `C = BW × log2(1 + 10^(SNR_db/10))` (bits/sec)
   - `Shannon Spec Eff = log2(1 + SNR_linear)` (b/s/Hz)

4. **Compute Effective Rate**
   - If MCS table: Select MCS based on SNR
   - Use `PERCalculator.calculate_effective_rate()`:
     - `Rate = BW × bits_per_symbol × code_rate × efficiency × (1 - PER)`
   - `Effective Spec Eff = Rate / BW` (b/s/Hz)

5. **Compute BER/PER**
   - Use `BERCalculator.theoretical_ber_awgn()` for BER
   - Use `BLERCalculator.approximate_bler()` if FEC enabled
   - Use `PERCalculator.calculate_per()` for PER (1500-byte packets)

6. **Categorize efficiency**
   - High: ≥ 4.0 b/s/Hz
   - Medium: 1.0-4.0 b/s/Hz
   - Low: < 1.0 b/s/Hz

7. **Compute Shannon Gap**
   - `Shannon Gap (dB) = 10 × log₁₀(Shannon_capacity / Effective_rate)`
   - Typical: 3-8 dB (3 dB = 50% efficiency)

8. **Compute Link Margin**
   - If MCS table: `Link Margin (dB) = SNR - min_SNR_for_MCS`
   - Indicates robustness to fading (higher is better)

9. **Generate Warnings**
   - Shannon gap >10 dB: "Very conservative MCS"
   - PER >10%: "High packet loss"
   - SNR <5 dB: "Poor link quality"
   - Link margin <3 dB: "Limited margin for fading"

### Dependencies to Reuse

| Component | File | Usage |
|-----------|------|-------|
| `TopologyLoader` | `src/sine/config/loader.py` | Parse network.yaml |
| `NetworkTopology` | `src/sine/config/schema.py` | Topology data model |
| `SNRCalculator` | `src/sine/channel/snr.py` | SNR computation |
| `BERCalculator` | `src/sine/channel/modulation.py` | BER from modulation |
| `BLERCalculator` | `src/sine/channel/modulation.py` | BLER with FEC gain |
| `PERCalculator` | `src/sine/channel/per_calculator.py` | PER and effective rate |
| `MCSTable` | `src/sine/channel/mcs.py` | Adaptive MCS selection |
| `get_bits_per_symbol()` | `src/sine/channel/modulation.py` | Modulation → bits/symbol |

### Channel Server API Usage

The calculator uses different API endpoints based on topology type:

**For Point-to-Point Links**: `POST /compute/single`

Use this for standard topologies with explicit links (no shared bridge).

**Request**:
```json
{
  "tx_position": [0, 0, 1],
  "rx_position": [20, 0, 1],
  "tx_power_dbm": 20.0,
  "tx_antenna_gain_dbi": 0.0,
  "rx_antenna_gain_dbi": 0.0,
  "frequency_hz": 5.18e9,
  "bandwidth_hz": 80e6,
  "modulation": "64qam",
  "fec_type": "ldpc",
  "fec_code_rate": 0.5
}
```

**Response** (extract these fields):
- `snr_db`: For Shannon capacity
- `path_loss_db`: For display
- `ber`, `per`: Error rates
- `netem_rate_mbps`: Effective rate (key name for channel server API)
- `distance_m`: For display

**For Shared Bridge (MANET) - Phase 1 Implementation**: `POST /compute/single`

Initially, use the same endpoint for simplicity. This computes SNR without interference modeling (conservative approach showing "best case" per-link capacity).

**Future Enhancement - SINR with Interference**: `POST /compute/sinr`

For realistic MANET modeling with simultaneous transmission interference, use:

```json
{
  "receiver": {
    "node_name": "node1",
    "position": [0, 0, 1],
    "antenna_gain_dbi": 3.0,
    "frequency_hz": 5.18e9,
    "bandwidth_hz": 80e6
  },
  "desired_tx": {
    "node_name": "node2",
    "position": [30, 0, 1],
    "tx_power_dbm": 20.0,
    "antenna_gain_dbi": 3.0,
    "frequency_hz": 5.18e9,
    "bandwidth_hz": 80e6
  },
  "interferers": [
    {
      "node_name": "node3",
      "position": [15, 25.98, 1],
      "tx_power_dbm": 20.0,
      "antenna_gain_dbi": 3.0,
      "frequency_hz": 5.18e9,
      "bandwidth_hz": 80e6,
      "is_active": true,
      "tx_probability": 0.3
    }
  ]
}
```

This returns `sinr_db` instead of `snr_db`, accounting for interference from other nodes in the broadcast domain.

### Output Format (Rich Table)

```
╭───────────────────────────────────────────────────────────────────────────────────────╮
│                            Spectral Efficiency Analysis                                │
├────────┬──────┬─────┬─────────┬────────┬──────────┬──────┬──────┬────────┬──────────┤
│ Link   │ Dist │ SNR │ Shannon │ Effec  │ Spec Eff │ Gap  │ Link │ BER /  │ Warnings │
│        │ (m)  │ (dB)│ (Mbps)  │ Rate   │ (b/s/Hz) │ (dB) │ Marg │ PER    │          │
│        │      │     │         │ (Mbps) │          │      │ (dB) │        │          │
├────────┼──────┼─────┼─────────┼────────┼──────────┼──────┼──────┼────────┼──────────┤
│ node1  │ 20.0 │ 39.7│ 1059    │ 192    │ 13.2 /   │ 7.4  │ 19.7 │ 1e-9 / │          │
│ :eth1  │      │     │ (13.2)  │        │ 2.4      │      │      │ 1e-7   │          │
│ ↔      │      │     │         │        │ (Medium) │      │      │        │          │
│ node2  │      │     │         │        │          │      │      │        │          │
│ :eth1  │      │     │         │        │          │      │      │        │          │
├────────┴──────┴─────┴─────────┴────────┴──────────┴──────┴──────┴────────┴──────────┤
│ MCS: 64-QAM, rate-1/2 LDPC | Path Loss: 68.3 dB | Min SNR: 20.0 dB                  │
╰───────────────────────────────────────────────────────────────────────────────────────╯
```

Color coding:
- **High efficiency** (≥4.0): Green
- **Medium efficiency** (1.0-4.0): Yellow
- **Low efficiency** (<1.0): Red
- **Shannon capacity**: Cyan (reference/theoretical)
- **Warnings**: Red text with "⚠" prefix
- **Good link margin** (>10 dB): Green
- **Limited margin** (3-10 dB): Yellow
- **Poor margin** (<3 dB): Red

## Implementation Steps

### 1. Create utilities directory structure
```bash
mkdir -p utilities
touch utilities/__init__.py
```

### 2. Create main script file
File: `utilities/calc_spectralefficiency.py`

### 3. Implement core functions
- `compute_shannon_capacity()`: Shannon formula
- `categorize_spectral_efficiency()`: High/medium/low
- `compute_link_metrics()`: Full pipeline for one link
- `display_results()`: Rich table formatting

### 4. Implement main workflow
- Parse CLI args (topology_path)
- Load topology using `TopologyLoader`
- Discover wireless links (using algorithm above - handles both point-to-point and shared bridge)
- Compute metrics via channel server for each discovered link
- Display results

### 5. Add CLI interface
```python
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Calculate spectral efficiency for wireless links"
    )
    parser.add_argument("topology", help="Path to network.yaml")
    parser.add_argument(
        "--channel-server",
        default="http://localhost:8000",
        help="Channel server URL"
    )
    args = parser.parse_args()
    main(args.topology, args.channel_server)
```

### 6. Add dependency
Update `pyproject.toml`:
```toml
[project]
dependencies = [
    # ... existing deps
    "rich>=13.0.0",  # For terminal table formatting
]
```

## Validation & Testing

### Test with existing examples

```bash
# 1. Start channel server
uv run sine channel-server

# 2. Run calculator on example topologies

# Point-to-point links
uv run python utilities/calc_spectralefficiency.py examples/vacuum_20m/network.yaml
uv run python utilities/calc_spectralefficiency.py examples/adaptive_mcs_wifi6/network.yaml
uv run python utilities/calc_spectralefficiency.py examples/two_rooms/network.yaml

# Shared bridge (MANET) topologies
uv run python utilities/calc_spectralefficiency.py examples/manet_triangle_shared/network.yaml
uv run python utilities/calc_spectralefficiency.py examples/manet_triangle_shared_sinr/network.yaml
```

### Expected results for vacuum_20m

Based on comments in `examples/vacuum_20m/network.yaml`:
- Distance: 20m
- FSPL: ~68.3 dB
- SNR: ~39.7 dB
- Modulation: 64-QAM, rate-1/2 LDPC
- Expected effective rate: ~192 Mbps (80 MHz × 6 bits × 0.5 × 0.8)
- Shannon capacity: 80 MHz × log2(1 + 10^(39.7/10)) = ~1059 Mbps
- Shannon spec eff: 13.2 b/s/Hz (excellent)
- Effective spec eff: 2.4 b/s/Hz (medium - conservative MCS)
- Shannon gap: 10 × log₁₀(1059 / 192) = 7.4 dB (typical)
- Link margin: 39.7 - 20.0 = 19.7 dB (excellent robustness)

### Expected results for manet_triangle_shared

Based on `examples/manet_triangle_shared/network.yaml`:
- **Topology**: 3 nodes in equilateral triangle (30m sides)
- **Shared bridge**: enabled, all nodes on eth1
- **Expected links**: 3 (node1↔node2, node1↔node3, node2↔node3)
- **Distance**: 30m per link
- **Configuration**: All identical (64-QAM, rate-1/2 LDPC, 80 MHz, 5.18 GHz, 20 dBm)
- **FSPL**: ~71.5 dB (30m at 5.18 GHz)
- **Expected SNR**: ~36-37 dB (30m free-space with dipole antenna gains)
- **Expected rate**: ~192 Mbps per link
- **Shannon capacity**: ~910-970 Mbps (high SNR → high theoretical capacity)
- **Shannon spec eff**: ~11.4 b/s/Hz (theoretical)
- **Effective spec eff**: ~2.4 b/s/Hz (same MCS as vacuum_20m)
- **Shannon gap**: ~7.0 dB (typical, conservative MCS)

**Important**: All three links should have identical or very similar metrics since:
- All nodes have same RF params (power, antenna gain, modulation)
- All links are same distance (30m)
- Free-space scene (vacuum.xml) has no multipath differences

**Note on interference**: The current implementation computes SNR for each link in isolation (no simultaneous interference). For SINR with interference modeling, see the SINR enhancement section below.

### Validation checklist

**General Validation:**
- [ ] Shannon capacity always > Effective rate
- [ ] Spectral efficiency matches reference values (CHATGPT doc)
- [ ] High SNR (>30 dB) → High/Medium efficiency
- [ ] Low SNR (<10 dB) → Low efficiency
- [ ] BER/PER decrease as SNR increases
- [ ] Fixed netem links are skipped (wireless only)
- [ ] MCS table examples show correct MCS selection
- [ ] Multi-link topologies display all links
- [ ] Shannon gap in reasonable range (3-10 dB typical)
- [ ] Shannon-to-Effective ratio between 20-80%
- [ ] Spectral efficiency ≤ bits_per_symbol × code_rate × 0.8
- [ ] Noise floor in valid range (-110 to -70 dBm for WiFi)
- [ ] Link margin displayed for MCS table scenarios
- [ ] Warnings generated for unusual conditions

**Shared Bridge (MANET) Validation:**
- [ ] Shared bridge topologies generate full mesh of links (N nodes → N×(N-1)/2 links)
- [ ] Shared bridge uses correct interface name from shared_bridge.interface_name
- [ ] Point-to-point and shared bridge modes both work correctly
- [ ] For manet_triangle_shared: SNR ~36-37 dB (not ~35 dB)
- [ ] For manet_triangle_shared: Shannon capacity ~910-970 Mbps (not ~830 Mbps)
- [ ] For manet_triangle_shared: All 3 links have similar metrics (equilateral triangle)
- [ ] Warning displayed for shared bridge about no interference modeling (Phase 1)
- [ ] All links in shared bridge have same frequency (co-channel scenario)

**Future Phase 2 (SINR Enhancement):**
- [ ] Auto-detect shared bridge and use `/compute/sinr` endpoint
- [ ] Include interferers from other nodes in broadcast domain
- [ ] Set appropriate tx_probability (0.3 for CSMA/CA, 1/N for TDMA)
- [ ] Display SINR instead of SNR for shared bridge links
- [ ] Add warning about aggregate throughput < sum of link capacities

## Critical Files

### Files to Create
- `utilities/__init__.py` (empty)
- `utilities/calc_spectralefficiency.py` (main script)

### Files to Reference (read-only)
- [src/sine/config/loader.py](src/sine/config/loader.py) - TopologyLoader
- [src/sine/config/schema.py](src/sine/config/schema.py) - NetworkTopology
- [src/sine/channel/snr.py](src/sine/channel/snr.py) - SNRCalculator
- [src/sine/channel/modulation.py](src/sine/channel/modulation.py) - BER/BLER
- [src/sine/channel/per_calculator.py](src/sine/channel/per_calculator.py) - PER, effective rate
- [src/sine/channel/mcs.py](src/sine/channel/mcs.py) - MCSTable
- [dev_resources/CHATGPT_typical_values_spectral_efficiency.md](dev_resources/CHATGPT_typical_values_spectral_efficiency.md) - Reference values

## Notes

### Shannon vs Effective Rate
- **Shannon**: Theoretical maximum assuming perfect coding (C = BW × log2(1 + SNR))
- **Effective**: Practical rate with real MCS, overhead, and PER losses
- **Gap**: Indicates how conservative the MCS selection is
  - Large gap (Shannon >> Effective): Conservative, robust
  - Small gap (Shannon ≈ Effective): Aggressive, near-capacity

### Spectral Efficiency Categories
From reference doc and typical values:
- **High (≥4.0 b/s/Hz)**: Excellent WiFi, short-range, high SNR (>20 dB)
- **Medium (1.0-4.0)**: Typical WiFi, good conditions (10-20 dB)
- **Low (<1.0)**: Military/tactical, robust modes, poor conditions (<10 dB)

### Topology Architecture Support
The calculator supports two topology architectures:

**Point-to-Point Links**:
- Standard containerlab format with explicit links
- Each link defined in `topology.links`
- Example: `examples/vacuum_20m/`, `examples/two_rooms/`

**Shared Bridge (MANET)**:
- All nodes share a broadcast domain via Linux bridge
- No explicit links (empty `topology.links`)
- Links auto-generated from `shared_bridge.nodes` (full mesh)
- All nodes use same interface (`shared_bridge.interface_name`)
- Example: `examples/manet_triangle_shared/`, `examples/manet_triangle_shared_sinr/`

**Link Discovery Logic**:
- If `shared_bridge.enabled == True`: Generate full mesh from `shared_bridge.nodes`
- Otherwise: Use explicit links from `topology.links`
- For N nodes in shared bridge, generates N×(N-1)/2 bidirectional links

### Error Handling
- Check channel server is running (connection error → helpful message)
- Skip fixed netem links (only analyze wireless)
- Handle missing MCS tables gracefully
- Validate topology has wireless links before processing
- Handle both point-to-point and shared bridge topologies

### SINR Enhancement for Shared Bridge (Future Phase)

**Current Implementation (Phase 1):**
- Uses `/compute/single` for all links (both point-to-point and shared bridge)
- Computes SNR without interference modeling
- Shows "best case" per-link capacity (no simultaneous transmissions)
- Simpler, faster, good for initial analysis

**Future Enhancement (Phase 2):**
- Auto-detect shared bridge topologies
- Use `/compute/sinr` with interference from other nodes
- Set `tx_probability` based on expected MAC protocol:
  - CSMA/CA: ~0.3 (moderate load)
  - TDMA (N nodes): 1/N (slot duty cycle)
  - Conservative: 1.0 (worst case)
- Returns SINR instead of SNR (accounts for interference)
- More realistic for MANET scenarios with simultaneous transmissions

**Implementation approach for Phase 2:**
```python
def compute_link_metrics(...):
    # Auto-detect topology type
    if is_shared_bridge(topology):
        # Use SINR endpoint with interference
        interferers = get_other_nodes_in_bridge(endpoint1, endpoint2, topology)
        result = call_sinr_endpoint(desired_tx, receiver, interferers, tx_prob=0.3)
        snr_or_sinr = result["sinr_db"]
        metric_label = "SINR"
    else:
        # Use single-link endpoint (no interference)
        result = call_single_endpoint(tx, rx)
        snr_or_sinr = result["snr_db"]
        metric_label = "SNR"
```

**Warnings to add for shared bridge:**
- "⚠ Shared bridge: Rates assume no simultaneous transmissions (SNR-based)"
- "⚠ Actual throughput depends on MAC protocol and channel contention"
- "⚠ Aggregate throughput < sum of link capacities (shared medium)"

## Wireless Comms Engineer Review

**Status**: ✅ **APPROVED WITH RECOMMENDATIONS** (Technical review completed)

### Key Findings
1. **Shannon Capacity Formula**: ✅ Correct (`C = BW × log₂(1 + SNR_linear)`)
2. **Spectral Efficiency Categories**: ✅ Align with industry standards
3. **Expected Values**: ✅ All calculations verified and corrected
4. **BER/BLER/PER Pipeline**: ✅ Follows proper wireless methodology
5. **Validation Checklist**: ✅ Comprehensive
6. **Full Mesh Approach**: ✅ Correct for PHY-focused channel modeling

### Shared Bridge (MANET) Topology Review

**Link Discovery Algorithm**: ✅ **TECHNICALLY SOUND**
- Full mesh generation (N×(N-1)/2 links) is correct for wireless channel modeling
- Each TX-RX pair has unique RF channel (distance, multipath, path loss)
- Broadcast medium is a MAC layer concept, not PHY channel property
- From PHY perspective, all pairwise links must be computed independently

**Expected Values Corrections**:
- Updated SNR: ~35 dB → **~36-37 dB** (corrected link budget)
- Updated Shannon capacity: ~830 Mbps → **~910-970 Mbps** (higher SNR)
- Updated Shannon gap: ~6.4 dB → **~7.0 dB** (recalculated)
- Added missing metrics: FSPL (~71.5 dB), Shannon spec eff (~11.4 b/s/Hz)

**Phase 1 vs Phase 2 Approach**:
- **Phase 1 (Current)**: Use `/compute/single` for all links (SNR-based, no interference)
  - Shows "best case" per-link capacity
  - Simpler implementation
  - Good for initial spectral efficiency analysis
- **Phase 2 (Future)**: Use `/compute/sinr` for shared bridge (SINR-based, with interference)
  - More realistic for simultaneous transmissions
  - Requires tx_probability estimation (MAC protocol dependent)
  - Better models actual MANET behavior

### Implemented Enhancements
1. **Shannon Gap (dB)**: `10 × log₁₀(Shannon / Effective)` - quantifies distance from theoretical limit
2. **Link Margin (dB)**: `SNR - min_SNR_for_MCS` - shows robustness to fading
3. **Warning System**: Color-coded alerts for unusual conditions
4. **Enhanced Validation**: Added checks for Shannon-to-Effective ratio, noise floor sanity check
5. **Shared Bridge Support**: Full mesh link discovery with topology-aware warnings

### Critical Pitfalls Avoided
1. **⚠️ Antenna Gain Double-Counting**: When using Sionna ray tracing, path coefficients ALREADY include antenna pattern gains. The channel server's `snr_db` response must be used directly without adding gains again.
2. **⚠️ Aggregate Throughput Confusion**: Per-link capacities cannot be summed for shared bridge topologies (shared medium). Phase 1 shows instantaneous per-link rates, not aggregate network throughput.
3. **⚠️ SNR vs SINR**: Phase 1 uses SNR (no interference). For realistic MANET modeling with simultaneous transmissions, Phase 2 should use SINR with interference from other nodes.

## Success Criteria

### Phase 1 (Current Implementation)
- Script runs without errors on all example topologies (point-to-point and shared bridge)
- Output matches expected values for vacuum_20m (SNR ~39.7 dB, rate ~192 Mbps)
- Output matches expected values for manet_triangle_shared (SNR ~36-37 dB, rate ~192 Mbps, 3 links)
- Shared bridge topologies generate correct full mesh of links (3 nodes → 3 links)
- Shannon capacity always exceeds effective rate
- Spectral efficiency categories align with reference doc
- Rich table displays clearly formatted results
- Error messages are helpful for common issues (server not running, no wireless links)
- Shannon gap displayed and within typical range (3-10 dB)
- Link margin shown for MCS table scenarios
- Warnings generated appropriately for shared bridge (notes about no interference modeling)

### Phase 2 (Future SINR Enhancement)
- Auto-detect shared bridge topologies
- Use `/compute/sinr` for MANET scenarios with interference modeling
- Set appropriate `tx_probability` based on MAC protocol
- Display SINR instead of SNR for shared bridge links
- Add warnings about aggregate throughput vs. per-link capacity
