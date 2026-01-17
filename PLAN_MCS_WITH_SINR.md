# Implementation Plan: Adaptive MCS with MAC Models

## Overview

Enable adaptive MCS selection to use SINR (Signal-to-Interference-plus-Noise Ratio) instead of SNR when MAC models (CSMA/TDMA) are present. This ensures that MCS selection accounts for interference, leading to more accurate modulation choices and throughput estimates.

## Current State

### How MCS Works Today

1. **Adaptive MCS**: System can dynamically select modulation/coding scheme based on channel quality
2. **MCS Selection**: Uses SNR threshold-based selection from CSV table (e.g., WiFi 6 MCS 0-11)
3. **Hysteresis**: Prevents rapid MCS switching by requiring extra margin to upgrade
4. **Location**: `src/sine/channel/mcs.py::MCSTable.select_mcs(snr_db, link_id)`

### How MAC Models Work Today

1. **MAC Models**: CSMA and TDMA statistical models compute interference probabilities
2. **SINR Computation**: Combines signal power, noise, and MAC-aware interference
3. **Limitation**: SINR is computed but **NOT used for MCS selection** - MCS still selects on SNR
4. **Location**: `src/sine/channel/server.py::_compute_batch_with_mac_model()`

### The Problem

```python
# In _compute_batch_with_mac_model() (line 689-693):
result = compute_channel_for_link(link, path_result)  # MCS selected on SNR here
result.sinr_db = effective_snr  # SINR computed but too late!
```

MCS is selected **before** SINR is available. This means:
- MCS selection ignores interference from other nodes
- May select too high MCS (optimistic) → higher packet loss than expected
- Inefficient spectrum use under interference conditions

## Proposed Solution

### High-Level Approach

**Modify `compute_channel_for_link()` to accept optional SINR parameter:**

```python
def compute_channel_for_link(
    link: WirelessLinkRequest,
    path_result: PathResult,
    effective_metric_db: float | None = None  # New parameter: SINR if MAC model present
) -> ChannelResponse:
```

**Usage:**
- **Without MAC model**: `effective_metric_db=None` → uses SNR (existing behavior)
- **With MAC model**: `effective_metric_db=sinr_db` → uses SINR for MCS selection

### Why This Approach

**Pros:**
- Minimal API change (single optional parameter)
- Backward compatible (existing callers unaffected)
- Clean separation: SINR computation happens before MCS selection
- Reuses all existing MCS selection logic (hysteresis, table lookup)

**Cons Considered:**
- Alternative: Create separate function `compute_channel_for_link_with_sinr()` → rejected (code duplication)
- Alternative: Move MCS selection outside function → rejected (breaks encapsulation)

### Topology Design Decision: Point-to-Point vs Shared Bridge

**Decision: Use point-to-point model** (not shared bridge like `examples/manet_triangle_shared/`)

**Rationale (from wireless communications expert):**
1. **SINR computation is identical** - Ray tracing and CSMA interference probabilities are independent of Linux networking topology
2. **Testing MCS selection logic** - We're validating that MCS uses SINR instead of SNR, not testing MAC protocol correctness
3. **Simpler implementation** - Point-to-point is easier to debug and already working
4. **Sufficient for validation** - Shared bridge adds real packet collisions (MAC layer), but MCS selection happens before that

**What shared bridge would add (not needed here):**
- Real MAC protocol collisions on shared medium
- True broadcast domain behavior
- More complex tc filter configuration
- Better for testing MAC protocol correctness (future work)

**What we're actually testing:**
- MCS selector receives SINR instead of SNR
- Lower MCS chosen when interference degrades SINR
- Throughput estimates match interference conditions

## Implementation Steps

### Step 1: Modify `compute_channel_for_link()` Function

**File:** `src/sine/channel/server.py`

**Changes to function signature** (line 731):
```python
def compute_channel_for_link(
    link: WirelessLinkRequest,
    path_result: PathResult,
    effective_metric_db: float | None = None,
) -> ChannelResponse:
```

**Changes to MCS selection logic** (~line 786):
```python
# Compute SNR first (always needed for logging/debugging)
snr_calc = SNRCalculator(bandwidth_hz=link.bandwidth_hz, noise_figure_db=7.0)
rx_power, snr_db = snr_calc.calculate_link_snr(
    tx_power_dbm=link.tx_power_dbm,
    tx_gain_dbi=link.tx_gain_dbi,
    rx_gain_dbi=link.rx_gain_dbi,
    path_loss_db=path_result.path_loss_db,
    from_sionna=True,
)

# Use SINR if provided (MAC model case), otherwise SNR
metric_for_mcs = effective_metric_db if effective_metric_db is not None else snr_db

if link.mcs_table_path:
    mcs_table = get_or_load_mcs_table(link.mcs_table_path, link.mcs_hysteresis_db)
    link_id = f"{link.tx_node}->{link.rx_node}"
    mcs = mcs_table.select_mcs(metric_for_mcs, link_id)  # <-- Use SINR when available

    modulation = mcs.modulation
    fec_type = mcs.fec_type
    fec_code_rate = mcs.code_rate
    selected_mcs_index = mcs.mcs_index
```

**Changes to BER/BLER/PER calculation** (~line 817):
- **Critical**: Also use `effective_metric_db` for BER/BLER/PER calculation (not just MCS selection)
```python
# Use effective metric for error rate calculation too
ber = BERCalculator.theoretical_ber_awgn(metric_for_mcs, modulation)

if fec_type.lower() != "none":
    bler = BLERCalculator.calculate_bler(
        snr_db=metric_for_mcs,  # Use SINR when available
        modulation=modulation,
        fec_type=fec_type,
        code_rate=fec_code_rate,
        block_size_bits=link.packet_size_bits,
    )
```

**Why use SINR for BER/BLER too:**
- Current code uses SNR for error rates even with MAC models
- SINR is the actual metric affecting bit errors under interference
- Ensures consistent metric used throughout pipeline (MCS → BER → BLER → PER → rate)

### Step 2: Update `_compute_batch_with_mac_model()` to Pass SINR

**File:** `src/sine/channel/server.py`

**Change the call to `compute_channel_for_link()`** (~line 689):
```python
# Before: MCS selected on SNR
# result = compute_channel_for_link(link, path_result)

# After: MCS selected on SINR
result = compute_channel_for_link(
    link,
    path_result,
    effective_metric_db=sinr_result.sinr_db  # Pass SINR for MAC-aware MCS
)
```

**Remove redundant SINR assignment** (lines 692-693):
```python
# These lines can be removed:
# result.snr_db = snr_db
# result.sinr_db = effective_snr

# Because compute_channel_for_link() now handles SINR internally
```

**Add SINR field to ChannelResponse** (if not already returning it):
```python
# Ensure ChannelResponse includes both SNR and SINR for debugging
result.snr_db = snr_db  # Original SNR (without interference)
result.sinr_db = sinr_result.sinr_db  # Effective SINR (with interference)
```

### Step 3: Create Test Topology and Integration Test

**File:** Create `examples/csma_mcs_test/network.yaml` (NEW)

**Simplified 2-link topology** (point-to-point model):

```yaml
name: csma-mcs-test
topology:
  scene:
    file: scenes/vacuum.xml
  links:
    - endpoints: [node1:eth1, node2:eth1]  # Primary link (test MCS selection on this)
    - endpoints: [node1:eth2, node3:eth1]  # Interferer link (causes interference)

nodes:
  node1:
    kind: linux
    image: alpine:latest
    interfaces:
      eth1:
        wireless:
          position: {x: 0, y: 0, z: 1}
          frequency_ghz: 5.18
          bandwidth_mhz: 80
          rf_power_dbm: 20
          mcs_table: examples/wifi6_adaptive/data/wifi6_mcs.csv  # Adaptive MCS
          antenna_pattern: iso
          antenna_polarization: V
          rx_gain_dbi: 0
          tx_gain_dbi: 0
          packet_size_bits: 12000
          csma:
            enabled: true
            carrier_sense_range_multiplier: 2.0
            traffic_load: 0.3  # 30% interference probability
      eth2:
        wireless:
          position: {x: 0, y: 0, z: 1}
          frequency_ghz: 5.18
          bandwidth_mhz: 80
          rf_power_dbm: 20
          mcs_table: examples/wifi6_adaptive/data/wifi6_mcs.csv
          antenna_pattern: iso
          antenna_polarization: V
          rx_gain_dbi: 0
          tx_gain_dbi: 0
          packet_size_bits: 12000
          csma:
            enabled: true
            carrier_sense_range_multiplier: 2.0
            traffic_load: 0.3

  node2:
    kind: linux
    image: alpine:latest
    interfaces:
      eth1:
        wireless:
          position: {x: 10, y: 0, z: 1}  # 10m from node1 (strong signal)
          frequency_ghz: 5.18
          bandwidth_mhz: 80
          rf_power_dbm: 20
          mcs_table: examples/wifi6_adaptive/data/wifi6_mcs.csv
          antenna_pattern: iso
          antenna_polarization: V
          rx_gain_dbi: 0
          tx_gain_dbi: 0
          packet_size_bits: 12000
          csma:
            enabled: true
            carrier_sense_range_multiplier: 2.0
            traffic_load: 0.3

  node3:
    kind: linux
    image: alpine:latest
    interfaces:
      eth1:
        wireless:
          position: {x: 15, y: 0, z: 1}  # 15m from node1 (weaker interferer)
          frequency_ghz: 5.18
          bandwidth_mhz: 80
          rf_power_dbm: 20
          mcs_table: examples/wifi6_adaptive/data/wifi6_mcs.csv
          antenna_pattern: iso
          antenna_polarization: V
          rx_gain_dbi: 0
          tx_gain_dbi: 0
          packet_size_bits: 12000
          csma:
            enabled: true
            carrier_sense_range_multiplier: 2.0
            traffic_load: 0.3
```

**Topology explanation:**
- **2 links total** (simple star, not full mesh)
  - Link 1: node1:eth1 ↔ node2:eth1 (10m, primary link)
  - Link 2: node1:eth2 ↔ node3:eth1 (15m, interferer)
- **Node1 has 2 interfaces** (eth1, eth2)
- **Node2 and Node3 have 1 interface each** (eth1)
- **All nodes co-channel** (5.18 GHz)
- **CSMA enabled** with 30% interference probability from hidden nodes
- **Adaptive MCS** via WiFi 6 MCS table

**Expected behavior:**
- Node3 causes interference to node1↔node2 link
- SINR < SNR for node1↔node2 link
- MCS selection uses SINR → chooses lower (more robust) MCS
- Throughput estimates match interference conditions

**File:** `tests/integration/test_mac_throughput.py` (add new test)

**Add test to verify SINR-based MCS selection:**
```python
def test_csma_mcs_uses_sinr():
    """Verify that MCS selection uses SINR when CSMA model is present."""
    # Deploy topology with CSMA and adaptive MCS
    deploy_topology("examples/csma_mcs_test/network.yaml")

    try:
        # Query channel server for link details
        response = requests.get("http://localhost:8000/api/visualization/state")
        assert response.status_code == 200
        data = response.json()

        # Find node1->node2 link (primary link)
        link = None
        for l in data["links"]:
            if (l["tx_node"] == "node1" and l["rx_node"] == "node2") or \
               (l["tx_node"] == "node2" and l["rx_node"] == "node1"):
                link = l
                break

        assert link is not None, "Could not find node1<->node2 link"

        # Verify SINR < SNR (interference present)
        assert "sinr_db" in link, "SINR not computed (MAC model not used?)"
        assert "snr_db" in link

        # With 30% interference probability, SINR should be slightly lower than SNR
        # May not be dramatic difference, but should be measurable
        interference_degradation_db = link["snr_db"] - link["sinr_db"]
        assert interference_degradation_db >= 0, "SINR should be <= SNR"

        # Verify MCS was selected
        assert "selected_mcs_index" in link

        # Load MCS table to verify selection matches SINR
        mcs_table = load_mcs_table("examples/wifi6_adaptive/data/wifi6_mcs.csv")
        selected_mcs = mcs_table[link["selected_mcs_index"]]

        # MCS min_snr should be <= SINR (valid selection)
        assert selected_mcs["min_snr_db"] <= link["sinr_db"], \
            f"MCS {link['selected_mcs_index']} requires {selected_mcs['min_snr_db']} dB, " \
            f"but SINR is only {link['sinr_db']} dB"

        # If SNR significantly higher than SINR, next higher MCS should be invalid
        # (proves MCS was selected on SINR, not SNR)
        if interference_degradation_db > 2.0:  # Significant interference
            next_mcs_index = link["selected_mcs_index"] + 1
            if next_mcs_index < len(mcs_table):
                next_mcs = mcs_table[next_mcs_index]
                # Next MCS should be invalid for SINR but valid for SNR
                assert next_mcs["min_snr_db"] > link["sinr_db"], \
                    "Expected next MCS to be too aggressive for SINR"
                # This proves MCS selection used SINR, not SNR

        print(f"✓ MCS selection correctly used SINR: {link['sinr_db']:.1f} dB " \
              f"(SNR: {link['snr_db']:.1f} dB, degradation: {interference_degradation_db:.1f} dB)")

    finally:
        destroy_topology("examples/csma_mcs_test/network.yaml")
```

### Step 4: Update Deployment Summary Display (Optional Enhancement)

**File:** `src/sine/emulation/controller.py`

**Modify `get_deployment_summary()`** to show:
- SNR alongside SINR when MAC model present
- Selected MCS index with metric used

**Example output:**
```
Link Parameters:
  node1:eth1 ↔ node2:eth1 [wireless, CSMA]
    SNR: 35.2 dB | SINR: 31.5 dB (interference: -3.7 dB)
    MCS: 10 (selected on SINR, 256qam rate-0.75 ldpc)
    Hidden nodes: 0/2 interferers
    Delay: 0.17 ms | Jitter: 0.00 ms | Loss: 0.01% | Rate: 456 Mbps
```

**Changes** (~line 495):
```python
# Show SNR and SINR when MAC model present
if result.get("mac_model_type"):
    snr_db = result["snr_db"]
    sinr_db = result.get("sinr_db", snr_db)
    interference_db = sinr_db - snr_db
    summary += f"    SNR: {snr_db:.1f} dB | SINR: {sinr_db:.1f} dB (interference: {interference_db:+.1f} dB)\n"
else:
    summary += f"    SNR: {result['snr_db']:.1f} dB\n"

# Show MCS selection details
if result.get("selected_mcs_index") is not None:
    metric_used = "SINR" if result.get("mac_model_type") else "SNR"
    summary += f"    MCS: {result['selected_mcs_index']} (selected on {metric_used}, "
    summary += f"{result['selected_modulation']} rate-{result['selected_code_rate']} {result['selected_fec_type']})\n"
```

## Critical Files

### Files to Modify

1. **`src/sine/channel/server.py`** (lines 731-884)
   - Add `effective_metric_db` parameter to `compute_channel_for_link()`
   - Use SINR for MCS selection when provided
   - Use SINR for BER/BLER/PER calculation when provided
   - Update `_compute_batch_with_mac_model()` to pass SINR

2. **`src/sine/emulation/controller.py`** (lines 495-530, optional)
   - Update deployment summary to show SNR vs SINR
   - Show which metric was used for MCS selection

3. **`examples/csma_mcs_test/network.yaml`** (NEW)
   - Test topology: 2-link star with CSMA + adaptive MCS

4. **`tests/integration/test_mac_throughput.py`** (add new test)
   - Verify SINR used for MCS selection
   - Validate MCS index matches SINR thresholds

### Files to Read (for context)

- `src/sine/channel/mcs.py` - MCS selection logic (no changes needed)
- `src/sine/channel/sinr.py` - SINR calculation (no changes needed)
- `src/sine/channel/csma_model.py` - CSMA interference probabilities (no changes needed)
- `src/sine/channel/tdma_model.py` - TDMA interference probabilities (no changes needed)

## Verification Plan

### Unit Testing

**Existing tests still pass:**
```bash
uv run pytest tests/test_mcs.py -v
uv run pytest tests/test_sinr.py -v
```

**No new unit tests needed** - function signature change is backward compatible.

### Integration Testing

**Manual verification:**

```bash
# 1. Start channel server
uv run sine channel-server

# 2. Deploy CSMA + MCS example (in another terminal)
sudo $(which uv) run sine deploy examples/csma_mcs_test/network.yaml

# 3. Check deployment summary
# Expected: Shows "MCS: X (selected on SINR, ...)"
# Expected: SINR < SNR due to interference

# 4. Verify via visualization endpoint
curl http://localhost:8000/api/visualization/state | jq '.links[0]'

# Expected output structure:
# {
#   "tx_node": "node1",
#   "rx_node": "node2",
#   "snr_db": 35.2,
#   "sinr_db": 31.5,
#   "selected_mcs_index": 10,
#   "mac_model_type": "csma",
#   "hidden_nodes": 0
# }

# 5. Cleanup
sudo $(which uv) run sine destroy examples/csma_mcs_test/network.yaml
```

**Automated integration test:**
```bash
uv run pytest tests/integration/test_mac_throughput.py::test_csma_mcs_uses_sinr -v -s
```

### Backward Compatibility Verification

**Test existing non-MAC MCS workflows still work:**

```bash
# Deploy WiFi 6 adaptive example (no MAC model)
sudo $(which uv) run sine deploy examples/wifi6_adaptive/network.yaml

# Verify: MCS still selected correctly on SNR
# Expected: No SINR field in response (MAC model not used)
```

## Expected Outcomes

### Before (Current Behavior)

**CSMA with Adaptive MCS:**
```
Link: node1:eth1 ↔ node2:eth1
  SNR: 35.2 dB
  SINR: 31.5 dB (computed but ignored)
  MCS: 11 (selected on SNR=35.2 dB) ← Too optimistic!
  Actual PER: 15% (high loss due to interference)
  Expected Rate: 533 Mbps (overly optimistic)
```

### After (With This Enhancement)

**CSMA with Adaptive MCS:**
```
Link: node1:eth1 ↔ node2:eth1
  SNR: 35.2 dB
  SINR: 31.5 dB (used for MCS selection)
  MCS: 10 (selected on SINR=31.5 dB) ← Realistic!
  Actual PER: 1% (matches interference level)
  Expected Rate: 456 Mbps (accurate)
```

**Key improvements:**
- MCS selection matches actual interference conditions
- Packet loss rates match expected values
- Throughput estimates are accurate
- Better spectrum efficiency (avoid overly aggressive MCS under interference)

## Edge Cases and Considerations

### 1. Mixed Topologies (MAC + non-MAC links)

**Scenario:** Some links use MAC model, others don't.

**Behavior:**
- Batch computation branches at MAC model detection
- Links **with** MAC model: Use SINR for MCS
- Links **without** MAC model: Use SNR for MCS
- Correct behavior: Each link uses appropriate metric

### 2. Fixed Modulation with MAC Model

**Scenario:** Link has MAC model but no MCS table (fixed modulation).

**Behavior:**
- `effective_metric_db` passed but `link.mcs_table_path` is None
- MCS selection skipped (fixed modulation used)
- BER/BLER/PER still use SINR (correct!)

### 3. Hysteresis Behavior with SINR

**Scenario:** SINR fluctuates due to interference changes.

**Behavior:**
- Hysteresis still applied (same logic, just different input metric)
- Prevents rapid MCS switching when interference varies
- **No changes needed to hysteresis logic**

### 4. TDMA Zero-Interference Case

**Scenario:** TDMA with orthogonal slots → SINR ≈ SNR.

**Behavior:**
- SINR computed (same value as SNR)
- MCS selection uses SINR (but equals SNR anyway)
- Throughput multiplier still applied (TDMA-specific)
- Correct behavior: No MCS downgrade, but rate reduced by slot ownership

### 5. Single-Link Endpoint (`/compute/single`)

**Scenario:** User calls `/compute/single` directly.

**Behavior:**
- No MAC model in single-link context
- `effective_metric_db=None` (default)
- Uses SNR for MCS selection (existing behavior)
- **No changes needed**

## Known Limitations (Out of Scope)

These are acknowledged but NOT addressed in this enhancement:

1. **Communication Range Estimation**: Still uses fixed 100m for CSMA (should estimate from link budget)
2. **Per-Frequency Grouping**: All nodes treated as co-channel interferers (Phase 2 enhancement)
3. **Simplified Interference Model**: Statistical probabilities, not full MAC event simulation (by design)
4. **Deployment Summary**: Optional display enhancement (can be done later)

## Success Criteria

- [ ] `compute_channel_for_link()` accepts optional `effective_metric_db` parameter
- [ ] When `effective_metric_db` provided, MCS selection uses it instead of SNR
- [ ] When `effective_metric_db` provided, BER/BLER/PER calculations use it instead of SNR
- [ ] `_compute_batch_with_mac_model()` passes SINR to `compute_channel_for_link()`
- [ ] Existing MCS tests still pass (backward compatibility)
- [ ] CSMA + MCS example deploys successfully
- [ ] Deployment summary shows both SNR and SINR when MAC model present
- [ ] Integration test validates SINR used for MCS selection

## Timeline Estimate

**Implementation:** ~2-3 hours
- Step 1 (modify `compute_channel_for_link`): 45 min
- Step 2 (update `_compute_batch_with_mac_model`): 15 min
- Step 3 (create example + test): 45 min
- Step 4 (deployment summary, optional): 30 min
- Verification and testing: 30 min

**Risk Level:** Low
- Backward compatible change
- Well-defined scope
- Existing test coverage validates correctness
