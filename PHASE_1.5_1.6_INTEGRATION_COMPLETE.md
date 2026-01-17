# Phase 1.5 and 1.6 Integration Completion Summary

**Date**: 2026-01-16
**Status**: ✅ Integration Complete - Ready for Testing

## Overview

Successfully integrated CSMA/CA and TDMA statistical MAC models into the SiNE emulation pipeline. The integration enables interference-aware SINR computation with automatic throughput adjustment based on MAC layer behavior.

## Changes Made

### 1. EmulationController Integration ✅

**File**: `src/sine/emulation/controller.py`

**Changes**:
- Extract MAC model configuration (CSMA or TDMA) from `WirelessParams` in topology YAML
- Pass MAC model parameters to channel server in batch requests
- Apply TDMA throughput multiplier to netem rate after channel computation
- Log MAC model type and parameters for debugging

**Key Code Sections**:
```python
# Lines 533-552: Extract MAC model from wireless interface config
mac_model = None
if wireless1.csma and wireless1.csma.enabled:
    mac_model = {
        "type": "csma",
        "carrier_sense_range_multiplier": wireless1.csma.carrier_sense_range_multiplier,
        "traffic_load": wireless1.csma.traffic_load,
    }
elif wireless1.tdma and wireless1.tdma.enabled:
    mac_model = {
        "type": "tdma",
        "frame_duration_ms": wireless1.tdma.frame_duration_ms,
        "num_slots": wireless1.tdma.num_slots,
        "slot_assignment_mode": wireless1.tdma.slot_assignment_mode,
        "fixed_slot_map": wireless1.tdma.fixed_slot_map,
        "slot_probability": wireless1.tdma.slot_probability,
    }

if mac_model:
    request["mac_model"] = mac_model
```

```python
# Lines 577-590: Apply TDMA throughput multiplier
for result in results.get("results", []):
    if result.get("mac_model_type") == "tdma" and "throughput_multiplier" in result:
        throughput_multiplier = result["throughput_multiplier"]
        original_rate = result["netem_rate_mbps"]
        result["netem_rate_mbps"] = original_rate * throughput_multiplier
```

### 2. Channel Server Integration ✅

**File**: `src/sine/channel/server.py`

**New Imports**:
```python
from sine.channel.csma_model import CSMAModel
from sine.channel.tdma_model import TDMAModel, TDMASlotConfig, SlotAssignmentMode
```

**New Models**:
- `MACModel` (Pydantic): Request model for CSMA/TDMA configuration
- Updated `WirelessLinkRequest`: Added `mac_model` field
- Updated `ChannelResponse`: Added MAC metadata fields:
  - `mac_model_type`: "csma", "tdma", or None
  - `sinr_db`: SINR value when using MAC models
  - `hidden_nodes`: Number of hidden nodes (CSMA only)
  - `throughput_multiplier`: Slot ownership fraction (TDMA only)

**New Function**: `_compute_batch_with_mac_model()` (lines 483-704)
- Instantiates CSMA or TDMA model based on configuration
- Collects all node positions and RF parameters from batch
- Computes interference probabilities using MAC model
- Computes actual interference power using InterferenceEngine
- Calls SINR calculator with MAC-aware interference probabilities
- Returns SINR and MAC-specific metadata

**Modified Endpoint**: `POST /compute/batch` (lines 751-855)
- Detects if any link uses MAC models
- Branches to MAC model computation path if MAC model present
- Falls back to original SNR-only computation if no MAC model

### 3. Integration Test Suite ✅

**File**: `tests/integration/test_mac_throughput.py` (NEW)

**Test Functions**:
1. `test_csma_throughput_spatial_reuse()`
   - Deploys `examples/sinr_csma_example.yaml`
   - Configures IPs and runs iperf3
   - Validates throughput is 400-450 Mbps (80-90% spatial reuse)

2. `test_tdma_fixed_throughput_matches_slot_ownership()`
   - Deploys `examples/sinr_tdma_fixed/network.yaml`
   - Validates throughput is 90-96 Mbps (20% slot ownership)

3. `test_tdma_roundrobin_throughput()`
   - Deploys `examples/sinr_tdma_roundrobin/network.yaml`
   - Validates throughput is 152-160 Mbps (33.3% slot ownership)

4. `test_csma_vs_tdma_ratio()`
   - Compares CSMA vs TDMA throughput
   - Validates CSMA is 4-5× faster than TDMA

**Helper Functions**:
- `deploy_topology()`: Deploy via `sine deploy`
- `destroy_topology()`: Cleanup via `sine destroy`
- `configure_ips()`: Set up IP addresses on container interfaces
- `run_iperf3_test()`: Run iperf3 and parse JSON output

## How It Works

### Request Flow

1. **Topology YAML** → `EmulationController._update_all_links()`
   - Extracts CSMA or TDMA config from `wireless.csma` or `wireless.tdma`
   - Builds batch request with `mac_model` field

2. **Batch Request** → `POST /compute/batch`
   - Channel server detects MAC model presence
   - Routes to `_compute_batch_with_mac_model()` if MAC model present

3. **MAC Model Computation**:
   - Instantiates `CSMAModel` or `TDMAModel`
   - Computes interference probabilities per link:
     - **CSMA**: Binary carrier sense (0.0 within CS range, traffic_load beyond)
     - **TDMA**: Deterministic or probabilistic based on slot assignment mode
   - Computes actual interference power using `InterferenceEngine`
   - Combines interference power with MAC probabilities
   - Calls `SINRCalculator.calculate_sinr()` with weighted interference

4. **Response Processing** → `EmulationController`
   - Receives `ChannelResponse` with SINR and MAC metadata
   - For TDMA: Applies throughput multiplier to netem rate
   - Applies netem configuration to container interfaces

### CSMA vs TDMA Behavior

| Feature | CSMA | TDMA |
|---------|------|------|
| **Interference Probability** | `Pr[TX] = 0.0` (within CS range)<br>`Pr[TX] = traffic_load` (hidden nodes) | `Pr[TX] = 0.0` (orthogonal slots)<br>`Pr[TX] = 1.0` (collision)<br>`Pr[TX] = slot_prob` (random/distributed) |
| **Throughput Multiplier** | N/A (full PHY rate with spatial reuse) | `num_owned_slots / total_slots` |
| **SINR Improvement** | +3-5 dB vs all-TX assumption | Depends on slot orthogonality |
| **Hidden Nodes** | Detected and counted | N/A |
| **Metadata Returned** | `hidden_nodes` count | `throughput_multiplier` fraction |

## Testing

### Unit Tests (Already Complete)
- ✅ `tests/test_csma_model.py` - CSMA carrier sense and hidden node logic
- ✅ `tests/test_tdma_model.py` - TDMA slot assignment modes
- ✅ `tests/test_sinr.py` - SINR calculation with interference

### Integration Tests (NEW)
Run with pytest:
```bash
# Run all integration tests
pytest tests/integration/test_mac_throughput.py -v -s

# Run specific test
pytest tests/integration/test_mac_throughput.py::test_csma_throughput_spatial_reuse -v -s
```

**Requirements**:
- sudo access (for netem configuration)
- containerlab installed
- iperf3 available in container images (alpine base image should include it)

**Manual Testing**:
```bash
# Start channel server
uv run sine channel-server

# Deploy CSMA example
sudo $(which uv) run sine deploy examples/sinr_csma_example.yaml

# Deploy TDMA fixed example
sudo $(which uv) run sine deploy examples/sinr_tdma_fixed/network.yaml

# Check deployment summary for SINR, hidden nodes, throughput multiplier
```

## Expected Results

### CSMA Example (3-node WiFi 6 MANET)

**Topology**: Equilateral triangle, 100m sides, vacuum scene

**Expected Output**:
```
Link Parameters:
  node1 (eth1) <-> node2 (eth1) [wireless, CSMA model]
    SNR: 35.2 dB | SINR: 32.1 dB | Hidden nodes: 0/2 interferers
    Expected interference: -5.2 dBm (vs -2.3 dBm all-TX)
    Delay: 0.33 ms | Jitter: 0.00 ms | Loss: 0.01% | Rate: 480 Mbps
```

**iperf3 Throughput**: 400-450 Mbps (80-90% spatial reuse efficiency)

### TDMA Fixed Slots Example (3-node military MANET)

**Topology**: Same as CSMA, but with TDMA slot assignment

**Expected Output**:
```
Link Parameters:
  node1 (eth1) <-> node2 (eth1) [wireless, TDMA fixed]
    SNR: 35.2 dB | SINR: 35.2 dB | Interferers: 0/2 deterministic (orthogonal slots)
    Expected interference: -inf dBm (zero collision probability)
    Delay: 0.33 ms | Jitter: 0.00 ms | Loss: 0.00% | Rate: 96 Mbps
    Throughput: 96 Mbps (20% slot ownership, 2/10 slots)
    Slot assignment: node1=[0,5], node2=[1,6], node3=[2,7]
```

**iperf3 Throughput**: 90-96 Mbps (95-99% of 96 Mbps, matches slot ownership)

### TDMA Round-Robin Example

**Expected Output**:
```
Link Parameters:
  node1 (eth1) <-> node2 (eth1) [wireless, TDMA round-robin]
    SNR: 35.2 dB | SINR: 35.2 dB | Interferers: 0/2 deterministic (orthogonal slots)
    Delay: 0.33 ms | Jitter: 0.00 ms | Loss: 0.00% | Rate: 160 Mbps
    Throughput: 160 Mbps (33.3% slot ownership, 10/3 slots per node)
```

**iperf3 Throughput**: 152-160 Mbps (95-100% of 160 Mbps)

### CSMA vs TDMA Ratio

**Expected**: CSMA throughput / TDMA throughput ≈ 4.5×

This validates that CSMA spatial reuse provides significant throughput advantage over TDMA deterministic scheduling for the same PHY configuration.

## Next Steps (Optional Enhancements)

### 1. Update Deployment Summary Display (Low Priority)

**File**: `src/sine/emulation/controller.py` - `get_deployment_summary()`

**Add**:
- Display SINR alongside SNR for MAC model links
- Show hidden node count for CSMA links
- Show slot ownership and throughput multiplier for TDMA links

**Example Format**:
```
Link Parameters:
  node1 (eth1) <-> node2 (eth1) [wireless, CSMA model]
    SNR: 35.2 dB | SINR: 32.1 dB
    Hidden nodes: 0/2 interferers
    Delay: 0.33 ms | Loss: 0.01% | Rate: 480 Mbps
```

### 2. Improve Communication Range Estimation (Medium Priority)

**File**: `src/sine/channel/server.py` - `_compute_batch_with_mac_model()`

**Current**: Fixed 100m communication range for CSMA (line 616)

**Enhancement**: Estimate from path loss and SNR threshold:
```python
# Estimate communication range from link SNR
# Assume link is viable when SNR > min_snr_threshold (e.g., 10 dB)
# Use inverse path loss model to estimate distance
min_snr_threshold_db = 10.0
communication_range = estimate_range_from_path_loss(
    path_loss_db=path_result.path_loss_db,
    snr_db=snr_db,
    min_snr_db=min_snr_threshold_db,
    frequency_hz=link.frequency_hz,
)
```

### 3. Add Adaptive MCS with MAC Models (Medium Priority)

**Current**: MAC models work with fixed modulation only

**Enhancement**: Use SINR (instead of SNR) for MCS selection when MAC model present

**Change**: In `compute_channel_for_link()`, pass SINR to MCS selector:
```python
if link.mcs_table_path:
    effective_snr = sinr_db if mac_model else snr_db
    mcs = mcs_table.select_mcs(effective_snr, link_id)
```

### 4. Per-Frequency Interference Groups (Phase 2)

**Current**: All nodes treated as co-channel interferers

**Enhancement**: Use `group_nodes_by_frequency()` to only compute interference from nodes on same frequency:
```python
freq_groups = group_nodes_by_frequency(links)
interferer_nodes = [
    n for n in freq_groups[link.frequency_hz]
    if n not in (link.tx_node, link.rx_node)
]
```

## Files Modified

### Modified Files
- `src/sine/emulation/controller.py` - MAC model extraction and throughput multiplier application
- `src/sine/channel/server.py` - MAC model request/response models and batch computation

### New Files
- `tests/integration/test_mac_throughput.py` - iperf3 validation tests

### Unchanged (Already Complete)
- `src/sine/channel/csma_model.py` - CSMA/CA statistical model (Phase 1.5)
- `src/sine/channel/tdma_model.py` - TDMA statistical model (Phase 1.6)
- `src/sine/channel/sinr.py` - SINR calculator with CSMA/TDMA methods
- `src/sine/config/schema.py` - CSMAConfig and TDMAConfig classes
- `tests/test_csma_model.py` - Unit tests for CSMA model
- `tests/test_tdma_model.py` - Unit tests for TDMA model
- `tests/test_sinr.py` - Unit tests for SINR calculation
- `examples/sinr_csma_example.yaml` - CSMA WiFi 6 example
- `examples/sinr_tdma_fixed/network.yaml` - TDMA fixed slots example
- `examples/sinr_tdma_roundrobin/network.yaml` - TDMA round-robin example

## References

- [PLAN_SINR.md](PLAN_SINR.md) - Full SINR implementation plan
- [PHASE_1.5_1.6_COMPLETE.md](PHASE_1.5_1.6_COMPLETE.md) - Core models completion summary
- [CSMA_VS_TDMA_CONFIGS.md](CSMA_VS_TDMA_CONFIGS.md) - Configuration quick reference

## Validation Checklist

Before merging:

- [x] EmulationController extracts MAC model from topology YAML
- [x] EmulationController passes MAC model to channel server
- [x] EmulationController applies TDMA throughput multiplier
- [x] Channel server instantiates CSMA/TDMA models
- [x] Channel server computes interference probabilities
- [x] Channel server computes actual interference power
- [x] Channel server calls SINR calculator
- [x] Channel server returns MAC metadata (hidden_nodes, throughput_multiplier)
- [x] Integration tests written for CSMA, TDMA fixed, TDMA round-robin
- [ ] Integration tests pass with iperf3 (requires sudo, pending execution)
- [ ] Deployment summary displays MAC metadata (optional enhancement)

## Known Limitations

1. **Communication Range Estimation**: Currently uses fixed 100m for CSMA carrier sense range. Should be estimated from link budget.

2. **No Adaptive MCS with MAC Models**: MCS selection uses SNR, not SINR. SINR should be used when MAC model is present.

3. **No Per-Frequency Grouping**: All nodes treated as co-channel interferers regardless of frequency. Phase 2 will add frequency group filtering.

4. **Simplified Interference Model**: Uses statistical probabilities rather than full MAC event simulation. This is by design (Phase 1 simplification).

## Conclusion

The CSMA and TDMA MAC models are now fully integrated into the SiNE emulation pipeline. The integration enables:

✅ **Realistic SINR computation** with MAC-aware interference probabilities
✅ **Automatic throughput adjustment** for TDMA slot ownership
✅ **Hidden node detection** for CSMA spatial reuse analysis
✅ **Ready for iperf3 validation** with integration test suite

Next: Run integration tests and validate actual throughput measurements match theoretical predictions.
