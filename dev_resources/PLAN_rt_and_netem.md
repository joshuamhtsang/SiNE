# Plan: Integration Tests for Ray Tracing → Netem Physical Phenomena

**STATUS: Updated with wireless comms engineer review findings**

## Critical Correction: Incoherent Sum is NOT a Bug

**Previous assessment was WRONG.** The incoherent summation is actually **CORRECT** for WiFi 6/OFDM systems that SiNE targets. The real bug is the delay spread → jitter mapping.

See "Wireless Comms Engineer Review" section at the end for detailed analysis.

---

## Understanding: What SiNE Actually Captures

Based on code analysis of the channel computation pipeline, here's what Sionna RT multipath data **does** and **does not** influence in SiNE's netem parameters:

### Channel Computation Pipeline

```
Sionna RT → paths.cir() → (a, tau)
    ↓
1. Path Loss Calculation (sionna_engine.py:299-301)
   path_powers = |a_i|² for all paths
   total_path_gain = Σ(path_powers)  # INCOHERENT SUM!
   path_loss_db = -10·log10(total_path_gain)

   ✅ CURRENT: Incoherent sum (adds powers, not amplitudes)
   ✅ CORRECT FOR: WiFi 6/OFDM systems (τ_rms << cyclic prefix)
   ✅ EFFECT: More paths → more power → lower path_loss_db (diversity gain)
   ⚠️ NOTE: Would be incorrect for narrowband single-carrier systems

2. Delay Spread Calculation (sionna_engine.py:315-317)
   mean_delay = weighted_average(tau, weights=path_powers)
   delay_variance = weighted_average((tau - mean_delay)², weights=path_powers)
   delay_spread_ns = sqrt(delay_variance)

   ✅ CAPTURES: RMS delay spread (multipath timing dispersion)
   ❌ CRITICAL BUG: jitter_ms = delay_spread_ns / 1e6 (server.py:946)
      → Maps 20-300 ns (PHY delay spread) to 0.0002-0.0003 ms (jitter)
      → Real WiFi jitter is 0.1-10 ms from MAC/queueing
      → ERROR FACTOR: 1000-10000x underestimate!

3. SNR → BER (AWGN formulas, modulation.py)
   BER depends ONLY on SNR (not delay spread)
   ❌ DOES NOT CAPTURE: ISI, frequency selectivity

4. PER Calculation
   loss_percent = PER × 100
   ✅ AFFECTED BY: Path loss (via SNR)
   ❌ NOT AFFECTED BY: Delay spread (no ISI modeling)
```

### Summary: What Multipath Actually Affects

| Phenomenon | Captured in CIR? | Affects Netem? | How? |
|------------|------------------|----------------|------|
| **Path loss (incoherent sum)** | ✅ Yes | ✅ Yes | SNR → BER → PER → `loss_percent` (correct for OFDM) |
| **Multipath diversity gain** | ✅ Yes | ✅ Yes | OFDM with CP absorbs paths → incoherent sum justified |
| **Per-subcarrier fading** | ⚠️ Averaged | ⚠️ Averaged | Frequency diversity across 234+ subcarriers |
| **Delay spread (τ_rms)** | ✅ Yes | ❌ WRONGLY | Maps to `jitter_ms` (INCORRECT - should be MAC/queue) |
| **ISI / frequency selectivity** | ❌ No | ❌ No | Not in AWGN BER formulas |
| **Fast fading (time-varying)** | ❌ No | ❌ No | Static channel per computation |

### Critical Finding

**Multipath affects netem in ONE way only:**

1. **`loss_percent`** - Via **incoherent** power sum affecting SNR (not via ISI)
   - ✅ **CORRECT FOR OFDM**: Uses Σ|a_i|² (appropriate for WiFi 6 with frequency diversity)
   - Result: Multipath provides **diversity gain** (0-3 dB typical)
   - Valid when τ_rms << cyclic prefix (20-300 ns << 800-3200 ns)

**Important:** The AWGN BER formulas (`modulation.py`) use only SNR, so **packet loss is purely SNR-driven**, not ISI-driven. This is appropriate for OFDM systems where the cyclic prefix prevents ISI.

**Jitter:** Now set to 0.0 (was incorrectly mapped from delay spread). Real jitter requires MAC/queue modeling.

---

## CRITICAL BUG: Delay Spread → Jitter Mapping (server.py:946)

### The Real Issue

**Current code (server.py:946):**
```python
jitter_ms = path_result.delay_spread_ns / 1e6
```

**Why this is WRONG:**

Delay spread is in **NANOSECONDS** (20-300 ns typical indoor):
- Affects frequency selectivity (coherence bandwidth)
- Absorbed by OFDM cyclic prefix (800-3200 ns)
- Does NOT create packet-level timing variation

Jitter is in **MILLISECONDS** (0.1-10 ms typical):
- Caused by MAC scheduling, retransmissions, queueing
- Three orders of magnitude larger than delay spread
- Emergent property, not a PHY primitive

**Example:**
For WiFi 6 with 300 ns RMS delay spread:
```
Current code: jitter_ms = 300 / 1e6 = 0.0003 ms = 0.3 μs
Reality: jitter_ms = 0.1-10 ms (from MAC/queueing)

Error factor: 1000-10000x UNDERESTIMATE
```

**What Actually Causes Jitter in WiFi:**
1. CSMA/CA backoff (microseconds to milliseconds)
2. HARQ retransmissions (frame duration multiples)
3. MCS adaptation (frame duration changes)
4. Queue dynamics (buffer drain rate variability)
5. Frame aggregation (A-MPDU variability)

**Recommended Fixes:**

Option 1: Remove jitter (most honest)
```python
jitter_ms = 0.0  # Jitter requires MAC/queue modeling
```

Option 2: Fixed conservative estimate
```python
jitter_ms = 1.0  # Typical WiFi jitter for reference
```

Option 3: Model from MAC parameters
```python
jitter_ms = estimate_mac_jitter(
    contention_window=31,  # WiFi 6 CWmin
    frame_duration_us=200,
    retransmission_probability=per,
)
```

---

## Incoherent vs Coherent Summation: NOT A BUG

### The Non-Issue

**Current code (sionna_engine.py:299-301):**
```python
path_powers = np.abs(a_np) ** 2  # Individual path powers
total_path_gain = np.sum(path_powers)  # Incoherent sum
```

**This is CORRECT for WiFi 6/OFDM systems.**

Why incoherent summation is justified for OFDM:
1. OFDM receiver performs per-subcarrier coherent combining automatically
2. Channel frequency response: H(f) = Σ aᵢ·e^(-j2πfτᵢ) for each subcarrier
3. Averaging across 234+ subcarriers (80 MHz) approximates E[|H(f)|²] ≈ Σ|aᵢ|²
4. Valid when τ_rms << cyclic prefix (20-300 ns << 800-3200 ns)

### When Would Coherent Summation Be Needed?

**Only for narrowband single-carrier systems:**
- GPS (1.023 MHz DSSS)
- Narrowband FSK/PSK
- Legacy systems without OFDM
- Bandwidth << coherence bandwidth

**For these, you'd compute:**
```python
total_amplitude = np.sum(a_np)  # Coherent sum (phase matters)
total_path_gain = np.abs(total_amplitude) ** 2
```

### Impact on SiNE Results

**Current behavior (incoherent) for WiFi 6/OFDM:**
- ✅ Multipath provides diversity gain (0-3 dB typical)
- ✅ OFDM cyclic prefix prevents ISI and fading nulls at packet level
- ✅ SNR accurately reflects OFDM receiver performance
- ✅ Loss% is realistic for equalized OFDM systems

**Physical Reality Check:**
For WiFi 6 at 80 MHz:
```
Symbol duration: 12.8 μs
Cyclic prefix: 0.8-3.2 μs
Typical indoor RMS delay spread: 20-300 ns

Key relationship:
τ_rms (20-300 ns) << CP (800-3200 ns) << T_symbol (12,800 ns)
```

This confirms incoherent summation is the correct abstraction.

### Recommendation

**No fix needed for incoherent summation** - it's correct for WiFi 6/OFDM.

**Optional future enhancement**: Add `coherent_combining` parameter for narrowband single-carrier scenarios (low priority).

---

## Proposed Integration Tests

### Test Philosophy

Create tests that demonstrate the physical phenomena SiNE **does capture** via Sionna RT, and clarify what it **does not** (per CHATGPT_sionnart_to_linkchars.md).

### Test Suite Structure

```
tests/integration/test_rt_to_netem_phenomena.py
├── Captured Phenomena (what Sionna RT → netem does model for OFDM)
│   ├── test_multipath_diversity_gain_for_ofdm
│   ├── test_delay_spread_within_cyclic_prefix
│   ├── test_los_vs_nlos_loss_difference
│   └── test_ofdm_cyclic_prefix_prevents_isi_fading
│
└── Not Captured (what requires additional modeling)
    └── test_static_channel_no_fast_fading
```

### Detailed Test Designs

#### 1. `test_multipath_diversity_gain_for_ofdm`

**Goal**: Validate that SiNE's incoherent summation correctly models OFDM diversity gain from multipath.

**Setup**:
- Two-room scene with doorway (guaranteed multipath)
- TX and RX positioned to get strong LOS + reflections
- Compare path_loss_db to free-space scenario at same distance

**Expected** (correct OFDM behavior):
- Multiple paths (e.g., -60 dBm LOS + -65 dBm reflection)
- Incoherent sum: total_power = |a1|² + |a2|² ≥ |a1|²
- Result: **Diversity gain (0-3 dB typical) - CORRECT for OFDM**
- SNR better with multipath due to frequency diversity across subcarriers

**Validation**:
```python
assert num_paths >= 2
diversity_gain_db = fspl_db - path_loss_db
assert 0 <= diversity_gain_db <= 3.0  # Realistic OFDM diversity gain
assert path_loss_db < fspl_db  # Multipath helps (as it should for OFDM)
```

**Note**: This test validates the **correct behavior** for OFDM systems. The incoherent summation accurately reflects how OFDM receivers with cyclic prefix and equalization benefit from multipath through frequency diversity. For narrowband single-carrier systems, coherent summation would be needed instead (not applicable to SiNE's WiFi 6 scope).

---

#### 2. `test_delay_spread_within_cyclic_prefix`

**Goal**: Verify that delay spread remains within WiFi 6 cyclic prefix bounds (validates OFDM assumptions).

**Setup**:
- Multiple scenarios with increasing multipath complexity:
  - Scenario A: Free-space (vacuum.xml), 20m → minimal delay spread
  - Scenario B: Two-room scene, 20m → moderate delay spread
  - Scenario C: (If exists) Complex indoor → higher delay spread

**Expected**:
- All scenarios: delay_spread_ns < 800 ns (WiFi 6 short GI cyclic prefix)
- If delay_spread exceeds 800 ns, validation warning should be triggered

**Validation**:
```python
assert scenario_a.delay_spread_ns < 10  # Nearly zero for LOS
assert scenario_b.delay_spread_ns > 0   # Non-zero with multipath
assert scenario_b.delay_spread_ns < 800 # Within short GI CP

# Verify coherence bandwidth > subcarrier spacing
coherence_bw_mhz = 1000 / (2 * np.pi * scenario_b.delay_spread_ns) if scenario_b.delay_spread_ns > 0 else float('inf')
subcarrier_spacing_mhz = 80 / 234  # WiFi 6 80 MHz: ~0.342 MHz
assert coherence_bw_mhz > subcarrier_spacing_mhz  # Frequency-flat per subcarrier
```

**Note**: This test validates the OFDM operating assumptions are met. Replaces the incorrect "jitter from delay spread" test.

---

#### 3. `test_los_vs_nlos_loss_difference`

**Goal**: Demonstrate LOS vs NLOS path loss difference captured by ray tracing.

**Setup**:
- LOS: Direct line-of-sight (vacuum or open room)
- NLOS: Blocked by wall (two-room scene with nodes in separate rooms)
- Same distance (e.g., 10m) for both

**Expected**:
- LOS: Lower path_loss_db, higher SNR, lower loss%
- NLOS: Higher path_loss_db (wall penetration + diffraction), lower SNR, higher loss%

**Validation**:
```python
assert nlos_loss_db > los_loss_db + 10  # Wall adds 10+ dB loss
assert nlos_loss_percent > los_loss_percent
```

---

#### 4. `test_ofdm_cyclic_prefix_prevents_isi_fading`

**Goal**: Demonstrate that OFDM's incoherent summation correctly models resilience to multipath fading at the packet level.

**Setup**:
- Position TX/RX to create two paths with varying phase relationships
- Example: 10m direct + 10.5m reflection (various path differences at 5.18 GHz)
- In narrowband single-carrier, this could cause deep fades

**Expected** (correct OFDM behavior):
- Phase relationships vary between paths (computed from delay difference)
- Path_loss_db shows diversity gain (multipath helps, no deep fades)
- Diversity gain bounded: 0-3 dB typical

**Validation**:
```python
# Calculate phase difference for reference
delta_tau = max_delay_ns - min_delay_ns
wavelength_m = 3e8 / frequency_hz
phase_diff_deg = (delta_tau * 1e-9 * frequency_hz * 360) % 360

# With OFDM, multipath provides diversity gain (no nulls at packet level)
diversity_gain_db = fspl_db - path_loss_db
assert 0 <= diversity_gain_db <= 3.0  # Realistic OFDM diversity gain
assert path_loss_db < fspl_db  # Multipath helps (correct for OFDM)
```

**Note**: This test validates that OFDM with cyclic prefix prevents destructive interference at the packet level. The frequency diversity across subcarriers means that even if some subcarriers experience fading nulls, the overall packet benefits from multipath. This is a **feature** of OFDM, not a bug.

---

#### 5. `test_static_channel_no_fast_fading`

**Goal**: Demonstrate that repeated channel computations at same positions give **identical** results (no time-varying fading).

**Setup**:
- Compute channel for same TX/RX position 10 times
- No mobility, no scene changes

**Expected**:
- All 10 computations return identical netem params
- Variance in loss_percent = 0

**Validation**:
```python
results = [compute_channel(tx_pos, rx_pos) for _ in range(10)]
loss_values = [r.loss_percent for r in results]
assert np.std(loss_values) < 1e-6  # Numerically zero variance
```

**Why this test matters**: Clarifies that fast fading (Rayleigh/Rician) is **not captured** unless you add stochastic perturbations on top of Sionna RT.

---

## Implementation Plan

### Phase 1: Core RT→Netem Tests
1. Implement test fixtures for common scenes (vacuum, two_rooms)
2. Add helper function to compute free-space baseline
3. Implement tests 1-4:
   - Test 1: Multipath diversity gain for OFDM
   - Test 2: Delay spread within cyclic prefix
   - Test 3: LOS vs NLOS loss difference
   - Test 4: OFDM cyclic prefix prevents ISI/fading

### Phase 2: Validation Tests
4. Implement test 5 (static channel - no fast fading)

---

## Files to Modify/Create

### New Test Files
- `tests/integration/test_rt_to_netem_phenomena.py` (main test suite with 5 core tests)

### Fixtures/Helpers
- `tests/integration/conftest.py` - Add fixtures for:
  - Channel server startup
  - Common scene loading (vacuum, two_rooms)
  - Free-space baseline calculator

### Documentation
- Update `CLAUDE.md` with "Physical Phenomena Captured" section
- Add table mapping RT outputs to netem params
- Link to integration tests as validation examples

---

## Expected Outcomes

### What Tests Will Prove

✅ **Multipath uses incoherent sum** - provides diversity gain (0-3 dB) - **CORRECT for OFDM**
✅ **OFDM resilience to fading** - cyclic prefix prevents ISI and packet-level fading nulls
✅ **Delay spread within cyclic prefix** - validates OFDM operating assumptions (τ_rms < 800 ns)
✅ **LOS vs NLOS captured** via path loss difference (geometry-based propagation)
✅ **AWGN BER formulas appropriate** - valid for OFDM with CP > delay spread (no ISI)
❌ **Jitter NOT from delay spread** - jitter set to 0.0 (requires MAC/queue modeling)
❌ **Fast fading NOT captured** - static channel (no Doppler/time variation)

### What Users Will Learn

- SiNE models **WiFi 6/OFDM systems** accurately with incoherent summation for frequency diversity
- Multipath **helps** OFDM performance through diversity gain (not a limitation)
- Packet loss is **SNR-driven** (appropriate for OFDM - no ISI after equalization)
- **Jitter requires MAC modeling** (CSMA/CA, retransmissions, queueing) - not captured by delay spread
- Delay spread validation ensures operation within **valid OFDM regime** (τ_rms < 800 ns)
- Fast fading requires **additional stochastic modeling** on top of deterministic ray tracing

---

## Verification

### Test Success Criteria

1. All 5 core tests pass with expected results
2. Tests document what SiNE captures vs. what requires extra modeling

### Documentation Updates

- `README.md`: Add "Physical Phenomena Captured" section
- `CLAUDE.md`: Reference integration tests as validation
- Test docstrings: Explain **why** each test validates specific phenomena

---

## Questions for User

1. **Scene availability**: Do you have a two-room scene with controllable TX/RX positions? Or should I generate one with specific geometry to ensure multipath?

User answer: look for the scene XML file there is: [scene file](./../scenes/two_rooms.xml) and it is used in the example [network.yaml](../examples/two_rooms/network.yaml). 

2. **Test coverage**: Any other phenomena from `CHATGPT_sionnart_to_linkchars.md` you want explicitly tested?

3. **Deployment requirement**: Should tests use mock channel server responses, or require actual Sionna RT (GPU)?

---

## Direct Answers to Original Questions

### 1. Does SiNE use multiple paths in any useful way that impacts BER, packet loss, jitter, or data rate?

**Yes, but in specific ways:**

**⚠️ Packet Loss (via SNR, but with limitation):**
- Multiple paths affect packet loss through **incoherent power summation** (NOT coherent)
- Code: [sionna_engine.py:299-301](src/sine/channel/sionna_engine.py#L299-L301)
  ```python
  path_powers = np.abs(a_np) ** 2  # Power from each path
  total_path_gain = np.sum(path_powers)  # INCOHERENT sum (adds powers, not amplitudes)
  path_loss_db = -10 * np.log10(total_path_gain)
  ```
- **Critical issue**: This ignores phase relationships!
  - ❌ No constructive interference (can't exceed single strongest path in reality)
  - ❌ No destructive interference (no fading nulls)
  - ⚠️ **Optimistic**: More paths always = better SNR (unrealistic for narrowband)

**What it SHOULD do (coherent summation):**
```python
total_amplitude = np.sum(a_np, axis=-1)  # Sum complex amplitudes FIRST
total_path_gain = np.abs(total_amplitude) ** 2  # THEN compute power
```
This would capture realistic fading (both constructive and destructive interference).

**✅ Jitter:**
- RMS delay spread from multipath **directly** maps to jitter_ms
- Code: [sionna_engine.py:315-317](src/sine/channel/sionna_engine.py#L315-L317)
  ```python
  mean_delay = np.average(valid_taus, weights=valid_powers)
  delay_variance = np.average((valid_taus - mean_delay) ** 2, weights=valid_powers)
  delay_spread_ns = float(np.sqrt(delay_variance) * 1e9)
  ```
- Then: [server.py:946](src/sine/channel/server.py#L946)
  ```python
  jitter_ms = path_result.delay_spread_ns / 1e6
  ```

**❌ BER (NOT affected by multipath structure):**
- BER depends **only on SNR**, not delay spread or number of paths
- SiNE uses AWGN BER formulas in [modulation.py](src/sine/channel/modulation.py) that take only SNR as input
- **No ISI modeling** - frequency-flat channel assumption

**✅ Data Rate (indirectly via SNR):**
- Multipath affects SNR → affects MCS selection → affects rate_mbps
- But delay spread itself doesn't limit rate (no ISI/frequency selectivity modeling)

---

### 2. Full Pipeline Explanation

**Complete flow from Sionna RT to netem:**

```
1. Sionna Ray Tracing
   paths = path_solver(scene)
   a, tau = paths.cir()  # Complex amplitudes + delays

2. Path Loss (Coherent Sum)
   path_powers = |a_i|² for each path
   total_gain = Σ(path_powers)
   path_loss_db = -10·log10(total_gain)

   → CAPTURES: Constructive/destructive interference
   → AFFECTS: SNR

3. Delay Spread (RMS)
   mean_delay = weighted_avg(tau)
   τ_rms = sqrt(weighted_variance(tau))

   → CAPTURES: Multipath timing dispersion
   → AFFECTS: jitter_ms

4. SNR Calculation
   SNR = TX_power - path_loss_db - noise_floor

   → USES: Path loss from step 2
   → IGNORES: Delay spread (AWGN assumption)

5. BER from SNR (AWGN formulas)
   BER = Q(√SNR) for BPSK
   BER = erfc(...) for QAM

   → DEPENDS ON: SNR only
   → IGNORES: Delay spread, ISI

6. PER from BER/BLER
   PER = 1 - (1 - BER)^packet_bits

   → CONVERTS: Bit errors to packet errors

7. Netem Parameters
   delay_ms = min_delay_ns / 1e6
   jitter_ms = delay_spread_ns / 1e6
   loss_percent = PER × 100
   rate_mbps = BW × bits/symbol × code_rate × (1 - PER)
```

**Key Insight**: Multipath affects netem through **two independent paths**:
- Path loss (coherent sum) → SNR → BER → **loss_percent**
- Delay spread (RMS) → **jitter_ms**

But **jitter does NOT cause packet loss** in SiNE's model - loss is purely SNR-driven.

---

### 3. Relation to CHATGPT_sionnart_to_linkchars.md

Your document is **accurate** - SiNE captures exactly what it says:

**✅ Captured (Section 1 of your doc):**
- Large-scale path loss - Yes (coherent sum)
- Multipath structure - Yes (delay spread → jitter)
- Deterministic fast fading - **Partially** (if you recompute for each position, but static per computation)
- Shadowing (deterministic) - Yes (LOS/NLOS transitions)

**⚠️ Indirectly Captured (Section 2):**
- Packet loss - Via SNR, not ISI (you noted this correctly)
- Jitter - Emergent from delay spread, but **no retransmissions** modeled
- Data rate - From MCS, not actual Shannon capacity

**❌ Not Captured (Section 3):**
- ISI / frequency selectivity - Correct, AWGN BER only
- Random small-scale fading - Correct, static channel
- Interference - Now captured via SINR endpoint!
- MAC effects - Correct, no contention modeling

**Your "practical recipe" (Section 6) is spot-on:**
> Ray trace → SINR → Add stochastic micro-fading → Map SINR → MCS → Add HARQ → Add queue

SiNE does steps 1-4 (ray trace → SINR → MCS → map to netem). It does **not** add stochastic fading, HARQ retries, or queueing - those would require additional modeling layers.

---

## Wireless Comms Engineer Review

**Review Date:** Based on agent analysis of PLAN and CHATGPT documents

### Summary of Findings

| Issue | Original PLAN Assessment | CHATGPT Assessment | Engineer Verdict |
|-------|--------------------------|-------------------|------------------|
| **Incoherent summation** | ❌ BUG - should be coherent | ✅ CORRECT for OFDM | ✅ **CORRECT** for WiFi 6/OFDM |
| **Delay spread → jitter** | ⚠️ Documents limitation | ❌ WRONG - must fix | ❌ **CRITICAL BUG** - fix immediately |
| **AWGN BER formulas** | ✅ Appropriate for netem | ✅ Appropriate for OFDM | ✅ **CORRECT** choice |
| **ISI modeling** | ❌ Not needed | ❌ Not needed | ✅ **Not needed** for OFDM |
| **Integration tests** | Well designed | N/A | ⚠️ **Need context fixes** |

### Key Insight: The Wrong Bug Was Identified

The PLAN document correctly analyzed the channel pipeline but **misidentified the critical issue**:

**❌ WRONGLY IDENTIFIED AS BUG:**
- Incoherent summation (Σ|aᵢ|²) at sionna_engine.py:299-301
- **Reality:** This is the CORRECT approach for WiFi 6/OFDM systems
- **Reason:** OFDM with cyclic prefix justifies incoherent summation as abstraction

**✅ ACTUAL CRITICAL BUG:**
- Delay spread → jitter mapping at server.py:946
- **Issue:** Maps PHY delay spread (20-300 ns) to packet jitter (should be 0.1-10 ms)
- **Error factor:** 1000-10000x underestimate
- **Root cause:** Confuses PHY timing (nanoseconds) with MAC/queue timing (milliseconds)

### Why Incoherent Summation is Correct for OFDM

**Physical basis:**
1. OFDM receiver performs FFT → per-subcarrier channel: H(f) = Σ aᵢ·e^(-j2πfτᵢ)
2. Each subcarrier is equalized independently (coherent combining per subcarrier)
3. Averaging across 234+ subcarriers (80 MHz WiFi 6) → E[|H(f)|²] ≈ Σ|aᵢ|²
4. Cyclic prefix (0.8-3.2 μs) >> delay spread (20-300 ns) prevents ISI

**Valid operating range:**
- Delay spread τ_rms < 800 ns (WiFi 6 short GI cyclic prefix)
- Bandwidth 20-160 MHz (typical OFDM)
- Environment: Indoor/urban (τ_rms typically 20-300 ns)

**When this would be wrong:**
- Narrowband single-carrier systems (GPS, FSK/PSK)
- Bandwidth << coherence bandwidth
- τ_rms > cyclic prefix (extreme scenarios)

### Why Delay Spread → Jitter Mapping is Wrong

**What delay spread actually represents:**
- Multipath timing dispersion in nanoseconds
- Affects coherence bandwidth: Bc ≈ 1/(2πτ_rms)
- For OFDM: absorbed by cyclic prefix (no packet-level impact)

**What jitter actually represents:**
- Packet timing variation in milliseconds
- Caused by MAC layer: CSMA/CA backoff, retransmissions, queueing
- Three orders of magnitude larger than delay spread

**Physical reality check:**
```
WiFi 6 with 300 ns delay spread:
- Current code: jitter_ms = 0.0003 ms (0.3 μs)
- Actual WiFi jitter: 0.1-10 ms
- Discrepancy: 300-33000x too small
```

### Priority Fixes

**1. CRITICAL - Fix Delay Spread → Jitter Mapping (server.py:946)**

Current (WRONG):
```python
jitter_ms = path_result.delay_spread_ns / 1e6
```

Option 1 - Remove jitter (most honest):
```python
jitter_ms = 0.0  # Jitter requires MAC/queue modeling
```

Option 2 - Fixed conservative estimate:
```python
jitter_ms = 1.0  # Typical WiFi jitter
```

Option 3 - Model from MAC parameters:
```python
jitter_ms = estimate_mac_jitter(
    contention_window=31,
    frame_duration_us=200,
    retransmission_probability=per,
)
```

**2. HIGH - Document OFDM Assumptions (sionna_engine.py:299-301)**

Add explanatory comment:
```python
# For OFDM systems (WiFi 6, LTE), incoherent summation is correct:
# - Each subcarrier coherently combines paths (H(f) = Σ aᵢ·e^(-j2πfτᵢ))
# - Averaging across subcarriers approximates Σ|aᵢ|²
# - Valid when τ_rms << cyclic_prefix (20-300 ns << 800-3200 ns)
# For narrowband single-carrier, would use: total_amplitude = np.sum(a_np); total_gain = |total_amplitude|²
path_powers = np.abs(a_np) ** 2
total_path_gain = np.sum(path_powers)
```

**3. MEDIUM - Update CLAUDE.md Documentation**

Add section clarifying:
- What OFDM captures (diversity gain, frequency selectivity)
- What requires MAC modeling (jitter, retransmissions)
- Valid operating range (τ_rms < 800 ns)

**4. MEDIUM - Revise Integration Tests**

Test name changes to match OFDM reality:
- Test 1: `test_multipath_incoherent_sum_always_improves_snr` → `test_multipath_diversity_gain_for_ofdm`
- Test 2: `test_multipath_delay_spread_increases_jitter` → **DELETE** (validates wrong behavior)
- Test 4: `test_no_destructive_interference_with_incoherent_sum` → `test_ofdm_cyclic_prefix_prevents_isi_fading`

Add new tests:
- `test_delay_spread_within_cyclic_prefix` - Verify τ_rms < 800 ns
- `test_coherence_bandwidth_vs_channel_bandwidth` - Verify Bc > subcarrier spacing

### Additional Recommended Tests

**Test 7: `test_delay_spread_within_cyclic_prefix`**
```python
# Verify delay spread is within WiFi 6 cyclic prefix bounds
assert delay_spread_ns < 800  # Short GI cyclic prefix
# Flag if invalid: would need long GI (1600 ns) or guard interval
```

**Test 8: `test_coherence_bandwidth_vs_channel_bandwidth`**
```python
# Verify coherence bandwidth > subcarrier spacing (frequency-flat per subcarrier)
coherence_bw_mhz = 1000 / (2 * np.pi * delay_spread_ns)
subcarrier_spacing_mhz = 0.3125  # WiFi 6
assert coherence_bw_mhz > subcarrier_spacing_mhz
```

**Test 9: `test_multipath_diversity_gain_bounds`**
```python
# Verify diversity gain from multipath is 0-3 dB (realistic range)
diversity_gain_db = fspl_db - path_loss_db
assert 0 <= diversity_gain_db <= 3.0
```

### Wireless Comms Principles: Accuracy Check

**✅ Correctly Applied:**
- OFDM channel model (incoherent summation for wideband)
- Link budget (Friis equation, SNR calculation)
- AWGN approximation (valid for OFDM with CP > delay spread)
- FEC coding gains (6-7 dB for LDPC realistic)
- MCS selection (SNR thresholds match WiFi 6 standards)

**❌ Incorrectly Applied:**
- **Delay spread → jitter mapping** - Confuses PHY (nanoseconds) with MAC (milliseconds)
  - This is the ONLY major wireless comms error in the codebase

**⚠️ Missing (Documented Limitations):**
- Time-varying fading (static channel, no Doppler/Rayleigh fading)
- MAC protocols (no CSMA/CA, HARQ, aggregation modeling)
- Note: Interference now added via SINR endpoint (good!)

### Conclusion

The original PLAN document provided excellent technical analysis but drew the wrong conclusion about which issue to fix. The incoherent summation is **not a bug** - it's the correct abstraction for OFDM systems. The real bug is the delay spread → jitter mapping, which underestimates jitter by 3-4 orders of magnitude.

**Fix priority:**
1. **CRITICAL**: Delay spread → jitter mapping (server.py:946)
2. **HIGH**: Document OFDM assumptions and valid range
3. **MEDIUM**: Revise integration tests to match OFDM reality
