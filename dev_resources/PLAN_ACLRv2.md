# Phase 2 ACLR Implementation Plan

## Problem Statement

**Current Behavior**: SINR calculation treats ALL transmitters as interferers regardless of frequency separation. A transmitter on 5.18 GHz will interfere with a receiver on 2.4 GHz, which is physically incorrect.

**Expected Behavior** (for 80 MHz WiFi 6 channels):
- **Co-channel (<40 MHz separation)**: Full interference (0 dB rejection) - channels overlap
- **Adjacent channels (40-120 MHz separation)**: Partial interference with ACLR rejection (20-40 dB)
- **Orthogonal channels (>160 MHz separation)**: Negligible interference (45 dB rejection)

**Root Cause**: The `frequency_hz` field exists in `InterferenceTerm` and `TransmitterInfo` dataclasses but is never used to filter interference. The code was designed for co-channel (same frequency) scenarios only.

**Context**: This implements **Phase 2 of PLAN_SINR.md** - Adjacent-Channel Interference with IEEE 802.11ax-compliant ACLR model.

## Impact on MAC Protocols

### TDMA (Time Division Multiple Access)

**Current behavior (Phase 1.7)**:
- Nodes transmit in assigned time slots (orthogonal in time)
- Only nodes transmitting in the same slot cause interference
- SINR calculation uses slot occupancy probabilities

**With ACLR (Phase 2)**:
- **Major benefit**: Different TDMA networks can use adjacent frequencies with minimal interference
- **Example scenario**:
  - Network A: 5.18 GHz, 5-node TDMA (20% slots each)
  - Network B: 5.20 GHz, 5-node TDMA (20 MHz separation)
  - **Before ACLR**: Full cross-network interference (SINR severely degraded)
  - **After ACLR**: 28 dB rejection → minimal cross-network interference

**Impact on SINR**:
```
SINR_TDMA = Signal / (Noise + Σ(Interference_i × slot_prob_i × ACLR_i))
                                                          ^^^^^^^^ NEW
```

**Use case**: Military MANET with multiple TDMA nets in same area
- Net 1 (convoy): 5.18 GHz
- Net 2 (logistics): 5.20 GHz
- Net 3 (air support): 5.24 GHz
- **ACLR enables frequency reuse** with acceptable interference levels

### CSMA/CA (Carrier Sense Multiple Access with Collision Avoidance)

**Current behavior (Phase 1.5)**:
- Nodes sense carrier before transmitting
- Carrier sense range determines hidden/exposed nodes
- SINR calculation uses transmission probabilities from CSMA model

**With ACLR (Phase 2)**:
- **Critical issue**: Carrier sensing is frequency-specific
- **Hidden nodes on adjacent channels**: Node may transmit on f1 while sensing f2 is clear
- **Exposed nodes on adjacent channels**: Node may defer unnecessarily if sensing f2 shows busy

**Impact on SINR**:
```
SINR_CSMA = Signal / (Noise + Σ(Interference_i × tx_prob_i × ACLR_i))
                                                         ^^^^^^^ NEW
Where tx_prob_i depends on carrier sense on frequency f_i
```

**Key difference from TDMA**:
- **TDMA**: Slots are deterministic, ACLR directly reduces interference
- **CSMA**: Carrier sensing may not detect adjacent-channel transmitters
  - Adjacent-channel interferers (20 MHz away) appear as **hidden nodes** to carrier sense
  - This can **increase** collision probability and **decrease** SINR benefit from ACLR

**Mitigation**:
- Multi-channel CSMA (like WiFi 802.11): Each channel has independent CSMA logic
- Receiver sensitivity check: If interference from adjacent channel is below sensitivity, treat as orthogonal

### Summary Table

| Aspect | TDMA | CSMA |
|--------|------|------|
| **Slot/transmission orthogonality** | Time-orthogonal | Probabilistic (carrier sense) |
| **ACLR benefit** | Direct (28-40 dB rejection) | Partial (hidden nodes on adjacent channels) |
| **Frequency reuse** | Excellent (predictable SINR) | Moderate (collision risk from hidden nodes) |
| **Multi-network coexistence** | Ideal use case | Requires careful frequency planning |
| **Implementation complexity** | Simple (multiply by ACLR) | Complex (carrier sense interaction) |

### Recommendation for Implementation

**Phase 2 ACLR implementation should**:
1. ✅ Apply ACLR to all MAC models (TDMA, CSMA, always-on)
2. ✅ Document that adjacent-channel CSMA nodes may behave as hidden nodes
3. ⚠️ Consider future enhancement: Multi-channel carrier sensing for CSMA

**Current Phase 2 is correct**: Apply ACLR uniformly, MAC model logic handles transmission probabilities separately.

---

## Analysis Summary

From codebase exploration:

1. **Frequency infrastructure exists but unused**:
   - `src/sine/channel/frequency_groups.py` has helper functions:
     - `are_frequencies_orthogonal()` - checks if frequencies don't overlap
     - `are_frequencies_cochannel()` - checks if frequencies overlap
   - **BUT** these are disconnected from SINR calculation

2. **Where changes are needed**:
   - [src/sine/channel/interference_engine.py](src/sine/channel/interference_engine.py#L152) - `compute_interference_at_receiver()` doesn't filter by frequency
   - [src/sine/channel/sinr.py](src/sine/channel/sinr.py#L145-150) - `calculate_sinr()` aggregates all interference without frequency check
   - [src/sine/channel/server.py](src/sine/channel/server.py#L1363-1378) - `/compute/sinr` endpoint doesn't pass receiver frequency for filtering

3. **Parameters collected but unused**:
   - `frequency_hz` in `InterferenceTerm` (stored but never consulted)
   - `frequency_hz` in `TransmitterInfo` (stored but never consulted)
   - Receiver's `frequency_hz` not passed to interference engine

---

## Proposed Solution (Aligned with PLAN_SINR.md Phase 2)

### IEEE 802.11ax ACLR Model

Implement Adjacent-Channel Leakage Ratio (ACLR) based on **IEEE 802.11ax-2021 spectrum mask** (Table 27-20).

**IMPORTANT**: ACLR thresholds must be **bandwidth-dependent** to correctly detect channel overlap.

| Frequency Separation (80 MHz BW) | ACLR (dB) | Interference Reduction | Description |
|----------------------------------|-----------|----------------------|-------------|
| 0-40 MHz (< BW/2) | 0 dB | None (full interference) | Co-channel (overlap) |
| 40-80 MHz (BW/2 to BW) | 20-28 dB | Transition band | Band edge / partial overlap |
| 80-120 MHz (BW to 1.5×BW) | 40 dB | 40 dB reduction | 1st adjacent (non-overlapping) |
| >120 MHz (> 1.5×BW) | 45 dB | 45 dB reduction | Orthogonal (negligible) |

**Implementation**:
```python
def calculate_aclr_db(
    freq_separation_hz: float,
    tx_bandwidth_hz: float = 80e6,
    rx_bandwidth_hz: float = 80e6
) -> float:
    """
    Calculate ACLR based on IEEE 802.11ax-2021 spectral mask.

    Accounts for channel overlap by checking if TX and RX bands overlap.

    Args:
        freq_separation_hz: Absolute frequency separation (center freq)
        tx_bandwidth_hz: Transmitter channel bandwidth (default 80 MHz)
        rx_bandwidth_hz: Receiver channel bandwidth (default 80 MHz)

    Returns:
        ACLR rejection in dB (how much to subtract from interference power)
    """
    freq_sep_mhz = abs(freq_separation_hz) / 1e6
    tx_bw_mhz = tx_bandwidth_hz / 1e6
    rx_bw_mhz = rx_bandwidth_hz / 1e6

    # Check for channel overlap (co-channel interference)
    min_separation_for_nonoverlap = (tx_bw_mhz + rx_bw_mhz) / 2.0

    if freq_sep_mhz < min_separation_for_nonoverlap:
        # Channels overlap → co-channel interference (0 dB ACLR)
        return 0.0

    # Non-overlapping channels: Apply IEEE 802.11ax spectral mask
    # Values based on 802.11ax-2021 Table 27-20 (transmit spectrum mask)
    half_tx_bw = tx_bw_mhz / 2.0

    if freq_sep_mhz < half_tx_bw + 40:
        # Transition band: 40-80 MHz for 80 MHz BW
        # Linear interpolation from -20 to -28 dB
        excess = freq_sep_mhz - half_tx_bw
        return 20.0 + (excess / 40.0) * 8.0
    elif freq_sep_mhz < half_tx_bw + 80:
        # 1st adjacent: 80-120 MHz for 80 MHz BW
        return 40.0
    else:
        # Orthogonal: >120 MHz for 80 MHz BW
        return 45.0
```

**Key difference from original plan**: Co-channel threshold is now **bandwidth-dependent** (BW/2) instead of fixed 10 MHz. For 80 MHz WiFi 6, channels separated by <40 MHz will have spectral overlap and experience full interference.

### Frequency Grouping with Dual Thresholds

Use existing `frequency_groups.py` logic with **bandwidth-dependent** thresholds:

- **ADJACENT_THRESHOLD = 1.5 × bandwidth_hz**: Compute interference with ACLR rejection
  - For 80 MHz WiFi 6: 120 MHz
  - Captures 1st and 2nd adjacent channels where ACLR is meaningful (20-40 dB)
- **ORTHOGONAL_THRESHOLD = 2.0 × bandwidth_hz**: Ignore interference (>45 dB rejection, negligible)
  - For 80 MHz WiFi 6: 160 MHz
  - Beyond this, channels are truly orthogonal with no spectral overlap

**Benefits**:
- Reduce computational complexity: O(G × N_g²) instead of O(N²)
- Skip truly negligible interference (>2× BW separation)
- Focus computation on meaningful interference sources
- Automatically adapts to different channel bandwidths (20, 40, 80, 160 MHz)

---

## Implementation Steps

### Step 1: Add ACLR Function to Interference Engine
1. Create `calculate_aclr_db(freq_separation_hz, tx_bandwidth_hz, rx_bandwidth_hz)` function
2. Implement IEEE 802.11ax ACLR table with bandwidth-dependent thresholds
3. Add channel overlap detection (co-channel if separation < (TX_BW + RX_BW)/2)
4. Add unit tests for ACLR calculation with various bandwidths (20, 40, 80 MHz)

**Files**: [src/sine/channel/interference_engine.py](src/sine/channel/interference_engine.py)

### Step 2: Add Receiver Frequency and Bandwidth Parameters
1. Modify `compute_interference_at_receiver()` signature to accept:
   - `rx_frequency_hz: float`
   - `rx_bandwidth_hz: float`
2. Calculate frequency separation for each interferer
3. Apply ACLR rejection to interference power (using TX and RX bandwidths)
4. Filter out orthogonal interferers (>2× max(TX_BW, RX_BW) separation)
5. Store `frequency_separation_hz` and `aclr_db` in `InterferenceTerm` for debugging

**Implementation**:
```python
# In compute_interference_at_receiver()
for interferer in interferers:
    # Existing path loss calculation...

    # NEW: Calculate ACLR based on frequency separation and bandwidths
    freq_separation = abs(interferer.frequency_hz - rx_frequency_hz)
    aclr_db = calculate_aclr_db(
        freq_separation,
        tx_bandwidth_hz=interferer.bandwidth_hz,
        rx_bandwidth_hz=rx_bandwidth_hz
    )

    # Apply ACLR rejection to interference power
    interference_dbm = (
        interferer.tx_power_dbm
        + interferer.antenna_gain_dbi
        + rx_antenna_gain_dbi
        - path_loss_db
        - aclr_db  # NEW: Subtract ACLR rejection
    )

    # Skip if negligible (>2× max BW → orthogonal, ~45 dB rejection)
    max_bw = max(interferer.bandwidth_hz, rx_bandwidth_hz)
    if freq_separation > 2.0 * max_bw:
        continue  # Skip orthogonal interferers

    interference_terms.append(InterferenceTerm(
        source=interferer.node_name,
        power_dbm=interference_dbm,
        frequency_hz=interferer.frequency_hz,
        frequency_separation_hz=freq_separation,  # NEW: For debugging
        aclr_db=aclr_db,  # NEW: For debugging
    ))
```

**Files**:
- [src/sine/channel/interference_engine.py](src/sine/channel/interference_engine.py#L119-216)
- [src/sine/channel/models.py](src/sine/channel/models.py) (add fields to `InterferenceTerm`)

### Step 3: Update API Endpoint
1. Verify `ComputeSINRRequest` has `rx_frequency_hz` and `rx_bandwidth_hz` fields
2. Pass both parameters to `compute_interference_at_receiver()`
3. Add optional `noise_figure_db` field to receiver config (default: 6.0 dB for WiFi)

**Files**: [src/sine/channel/server.py](src/sine/channel/server.py#L1276-1380)

### Step 4: Add Integration Tests
1. Create test topology with mixed frequencies for 80 MHz channels:
   - 5.18 GHz, 5.20 GHz (20 MHz apart → co-channel, overlap)
   - 5.18 GHz, 5.26 GHz (80 MHz apart → transition band)
   - 5.18 GHz, 5.30 GHz (120 MHz apart → 1st adjacent, 40 dB ACLR)
   - 5.18 GHz, 5.50 GHz (320 MHz apart → orthogonal, filtered out)
2. Test co-channel with overlap (0 dB ACLR, <40 MHz separation)
3. Test transition band (20-28 dB ACLR, 40-80 MHz separation)
4. Test 1st adjacent (40 dB ACLR, 80-120 MHz separation)
5. Test orthogonal (filtered out, >160 MHz separation)
6. Verify SINR values match expected ACLR rejection
7. Test different bandwidths (20, 40, 80 MHz) to verify thresholds scale correctly

**Files**: [tests/integration/test_sinr_frequency_filtering.py](tests/integration/test_sinr_frequency_filtering.py) (new)

### Step 5: (Optional) Add Frequency Grouping in Controller
1. Group nodes by frequency before SINR computation
2. Only compute interference within groups (≤1.5× max_bandwidth separation)
3. Skip cross-group interference (>2.0× max_bandwidth separation)
4. Make grouping thresholds bandwidth-aware (query each node's bandwidth_hz)

**Files**: [src/sine/emulation/controller.py](src/sine/emulation/controller.py)

**Note**: This is an optimization step, can be deferred if premature. Bandwidth-dependent thresholds require tracking bandwidth per node.

---

## Critical Files to Modify

| File | Lines | Changes |
|------|-------|---------|
| [src/sine/channel/interference_engine.py](src/sine/channel/interference_engine.py#L119-216) | 119-216 | Add `rx_frequency_hz` param, `calculate_aclr_db()` function, apply ACLR to interference power |
| [src/sine/channel/models.py](src/sine/channel/models.py) | TBD | Add `frequency_separation_hz` and `aclr_db` to `InterferenceTerm` |
| [src/sine/channel/server.py](src/sine/channel/server.py#L1276-1380) | 1276-1380 | Pass `rx_frequency_hz` to interference engine |
| [src/sine/emulation/controller.py](src/sine/emulation/controller.py) | TBD | Add frequency grouping (optional optimization) |
| [src/sine/channel/frequency_groups.py](src/sine/channel/frequency_groups.py#L36-182) | 36-182 | Use existing grouping functions (reference only) |
| [tests/integration/test_sinr_frequency_filtering.py](tests/integration/test_sinr_frequency_filtering.py) | New file | Add co-channel, adjacent, and orthogonal test cases |

---

## Verification Plan

### Unit Tests
```bash
# Test ACLR calculation function
uv run pytest tests/unit/test_interference_engine.py::test_calculate_aclr_db -v

# Test interference with ACLR rejection
uv run pytest tests/unit/test_interference_engine.py::test_interference_with_aclr -v

# Run all SINR calculator tests (should pass unchanged)
uv run pytest tests/unit/test_sinr.py -v
```

### Integration Tests
```bash
# Run new frequency filtering tests
sudo -v && uv run pytest tests/integration/test_sinr_frequency_filtering.py -v -s -m integration

# Test co-channel with overlap (0 dB ACLR, 20 MHz separation for 80 MHz BW)
sudo -v && uv run pytest tests/integration/test_sinr_frequency_filtering.py::test_cochannel_overlap -v -s

# Test transition band (20-28 dB ACLR, 60 MHz separation)
sudo -v && uv run pytest tests/integration/test_sinr_frequency_filtering.py::test_transition_band_rejection -v -s

# Test 1st adjacent (40 dB ACLR, 100 MHz separation)
sudo -v && uv run pytest tests/integration/test_sinr_frequency_filtering.py::test_first_adjacent_40db_rejection -v -s

# Test orthogonal (45 dB ACLR, filtered out, 200 MHz separation)
sudo -v && uv run pytest tests/integration/test_sinr_frequency_filtering.py::test_orthogonal_no_interference -v -s

# Test bandwidth scaling (verify thresholds work for 20, 40, 80 MHz)
sudo -v && uv run pytest tests/integration/test_sinr_frequency_filtering.py::test_bandwidth_dependent_thresholds -v -s

# Run existing SINR test to ensure no regression
sudo -v && uv run pytest tests/integration/test_mac_throughput.py::test_csma_mcs_uses_sinr -v -s
```

### Manual Validation via API
```bash
# 1. Start channel server
uv run sine channel-server

# 2. Deploy mixed-frequency topology (in another terminal)
sudo $(which uv) run sine deploy examples/sinr_mixed_freq/network.yaml

# 3. Query deployment summary
curl http://localhost:8001/api/emulation/summary | jq '.links[] | {tx_node, rx_node, snr_db, sinr_db, freq_separation_mhz, aclr_db}'

# Expected output (for 80 MHz channels):
# {
#   "tx_node": "node1",
#   "rx_node": "node2",
#   "snr_db": 41.2,
#   "sinr_db": 21.5,       # Reduced by co-channel interference
#   "freq_separation_mhz": 0,
#   "aclr_db": 0,
#   "note": "Same frequency = co-channel"
# }
# {
#   "tx_node": "node3",
#   "rx_node": "node4",
#   "snr_db": 38.7,
#   "sinr_db": 35.0,       # Slightly reduced (channels overlap)
#   "freq_separation_mhz": 20,
#   "aclr_db": 0,
#   "note": "20 MHz < 40 MHz (BW/2) = overlapping channels"
# }
# {
#   "tx_node": "node5",
#   "rx_node": "node6",
#   "snr_db": 40.5,
#   "sinr_db": 36.2,       # Reduced by 1st adjacent interference (40 dB ACLR)
#   "freq_separation_mhz": 100,
#   "aclr_db": 40,
#   "note": "80-120 MHz = 1st adjacent"
# }
# {
#   "tx_node": "node7",
#   "rx_node": "node8",
#   "snr_db": 42.1,
#   "sinr_db": 42.0,       # No reduction (orthogonal, >160 MHz)
#   "freq_separation_mhz": 200,
#   "aclr_db": 45,
#   "note": ">160 MHz (2×BW) = orthogonal, filtered out"
# }
```

---

## Edge Cases and Considerations

### 1. Frequency Separation Calculation
- Use `abs(interferer_freq - rx_freq)` to handle both positive and negative separations
- Convert to MHz for ACLR table lookup

### 2. Orthogonal Threshold (100 MHz)
- Skip orthogonal interferers entirely (no `InterferenceTerm` added)
- Rationale: 45 dB rejection makes interference negligible (~1/30,000 of original power)
- Improves performance by reducing list size

### 3. ACLR Table Boundaries (Updated for 80 MHz BW)
- 0-40 MHz: Co-channel (0 dB) - channels overlap
- 40-80 MHz: Transition band (20-28 dB) - band edge
- 80-120 MHz: 1st adjacent (40 dB) - non-overlapping
- >120 MHz: Orthogonal (45 dB) - negligible interference
- Use `<` for strict boundaries to avoid edge case ambiguity
- **IMPORTANT**: Thresholds scale with bandwidth (BW/2, BW, 1.5×BW, 2×BW)

### 4. Backward Compatibility
- Existing co-channel topologies (all nodes at same frequency) should behave identically
- ACLR = 0 dB for channels with same center frequency → no change to interference power
- Existing tests should pass without modification (co-channel case unchanged)

### 5. Transmitter ACLR Only (Not Receiver Selectivity)
- **SiNE models only TX ACLR** (transmitter spectral mask leakage)
- **Does NOT model RX selectivity** (receiver adjacent-channel rejection)
- Real WiFi chipsets have both:
  - TX ACLR: -28 to -40 dB (modeled by SiNE)
  - RX ACR: -16 to -20 dB additional (NOT modeled)
- **SiNE is conservative**: Real systems have ~16-20 dB better adjacent-channel rejection
- Receiver bandwidth affects thermal noise floor only (already implemented)
- This is acceptable for network emulation - avoids overestimating performance

### 6. Multi-Band Scenarios
- 2.4 GHz and 5 GHz nodes: >2 GHz separation → orthogonal, filtered out
- ISM bands (2.4, 5, 6 GHz): All orthogonal to each other
- Sub-6 GHz cellular (e.g., 700 MHz + 2.6 GHz): Orthogonal

### 7. Performance Impact
- ACLR calculation: ~5 floating-point operations per interferer (negligible)
- Orthogonal filtering: Reduces interference list size by ~50-80% in multi-band scenarios
- Net performance improvement due to fewer items to aggregate

---

## RF Model Limitations and Assumptions

### What SiNE Models

✅ **Transmitter spectral mask** (ACLR per IEEE 802.11ax-2021)
✅ **Bandwidth-dependent channel overlap** detection
✅ **Frequency-dependent interference** rejection
✅ **Path loss and multipath** from Sionna ray tracing
✅ **Thermal noise** based on bandwidth

### What SiNE Does NOT Model

❌ **Receiver selectivity (ACR)**: Real receivers provide ~16-20 dB additional adjacent-channel rejection beyond TX spectral mask. SiNE's model is conservative (worst-case receiver).

❌ **Receiver noise figure (NF)**: Real receivers have NF = 5-7 dB (WiFi) that degrades SNR. Future enhancement: Add optional `noise_figure_db` parameter (default 6 dB).

❌ **Phase noise and frequency offset**: Assumes ideal oscillators with zero phase noise and zero frequency offset. Real oscillators have ±20 ppm frequency error and ~2-3 dB phase noise degradation.

❌ **AGC saturation**: Strong adjacent-channel interferers can cause AGC to reduce gain, degrading SINR by additional 3-6 dB. SiNE assumes infinite dynamic range.

❌ **Per-subcarrier SNR (OFDM)**: ACLR applied uniformly across channel. In real OFDM, edge subcarriers experience higher adjacent-channel interference than center subcarriers.

❌ **Harmonic/spurious emissions**: SiNE does not model 2nd harmonic interference (e.g., 2.4 GHz → 4.8 GHz).

❌ **Spectral mask violations**: Assumes all transmitters meet IEEE 802.11ax compliance. Real non-compliant transmitters may have 5 dB worse ACLR.

### Impact on Accuracy

- **Conservative bias**: SiNE underestimates adjacent-channel rejection by ~16-20 dB (missing RX selectivity)
- **Real performance may be better**: Actual systems will have higher SINR than predicted
- **Severe interference scenarios**: AGC saturation may degrade real performance by 3-6 dB beyond predictions
- **Appropriate for network emulation**: Packet-level abstraction doesn't require symbol-level fidelity

### Recommended Future Enhancements

1. **Add `noise_figure_db` parameter** (default 6 dB for WiFi, 3-5 dB for military radios)
2. **Add `spectral_mask_margin_db` parameter** (default 0 dB for compliant TX, -5 dB for poor TX)
3. **Document AGC limitations** in user guide for severe adjacent-channel scenarios
4. **Consider RX selectivity** as optional enhancement (adds ~16-20 dB to ACLR)

---

## Expected Outcomes

After implementation:
- ✅ Interference from orthogonal frequencies (>2× BW) filtered out
- ✅ Adjacent channel interference reduced by ACLR (20-40 dB)
- ✅ Co-channel interference unchanged (0 dB ACLR for overlapping channels)
- ✅ Bandwidth-dependent thresholds (works with 20, 40, 80, 160 MHz channels)
- ✅ SINR ≈ SNR when all interferers are orthogonal
- ✅ Multi-band topologies work correctly (2.4 GHz + 5 GHz nodes)
- ✅ Existing co-channel tests still pass (no regression)
- ✅ Deployment summary shows frequency separation and ACLR for each link
- ✅ IEEE 802.11ax compliance for WLAN emulation scenarios
- ✅ TDMA networks on adjacent frequencies can coexist with minimal interference
- ✅ CSMA behavior documented for adjacent-channel scenarios (hidden node risk)
- ✅ Conservative model (TX ACLR only) avoids overestimating performance

---

## Summary

**What we're implementing**: Phase 2 of PLAN_SINR.md - Adjacent-Channel Interference with IEEE 802.11ax ACLR model.

**Key insight from analysis**: The frequency_hz field exists throughout the codebase but is never used. We'll activate this infrastructure by:
1. Adding `calculate_aclr_db()` function implementing IEEE 802.11ax spectrum mask with **bandwidth-dependent thresholds**
2. Modifying `compute_interference_at_receiver()` to accept `rx_frequency_hz`, `rx_bandwidth_hz` and apply ACLR
3. Filtering orthogonal interferers (>2× max BW) to improve performance
4. Adding comprehensive tests for co-channel, transition band, adjacent, and orthogonal scenarios
5. Documenting RF model limitations (TX ACLR only, no RX selectivity, conservative model)

**Critical corrections from original plan**:
- **Co-channel threshold**: Now bandwidth-dependent (BW/2 = 40 MHz for 80 MHz WiFi), not fixed 10 MHz
- **Adjacent threshold**: 1.5× BW (120 MHz for 80 MHz WiFi), not fixed 50 MHz
- **Orthogonal threshold**: 2.0× BW (160 MHz for 80 MHz WiFi), not fixed 100 MHz
- **Channel overlap detection**: Explicitly checks if TX and RX bands overlap before applying ACLR

**MAC protocol impact**:
- **TDMA**: Direct benefit - enables multi-network frequency reuse with predictable SINR
- **CSMA**: Partial benefit - adjacent-channel nodes may act as hidden nodes to carrier sense

**RF model limitations**:
- **Conservative**: Models only TX ACLR (~28-40 dB), not RX selectivity (~16-20 dB additional)
- **Real performance may be better**: Missing RX selectivity means actual systems have higher SINR
- **Acceptable for network emulation**: Packet-level abstraction appropriate for netem

**Backward compatibility**: Existing co-channel topologies (all nodes at same frequency) will behave identically since ACLR = 0 dB for overlapping channels.
