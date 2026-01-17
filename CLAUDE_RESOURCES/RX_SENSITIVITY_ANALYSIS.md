# Receiver Sensitivity (rx_sensitivity_dbm) Analysis

## Executive Summary

The `rx_sensitivity_dbm` parameter is a **fundamental RF link budget parameter** that was missing from the SiNE schema until now. This document explains why it's critical, why it was overlooked, and how it's now properly integrated.

## What is Receiver Sensitivity?

**Receiver sensitivity** is the **minimum signal power** (in dBm) that a receiver can detect and successfully demodulate. It represents the noise floor of the receiver plus the minimum SNR required for the chosen modulation scheme.

### Formula

```
rx_sensitivity_dbm = Noise_floor + SNR_min

Where:
  Noise_floor = -174 dBm/Hz + 10*log10(bandwidth) + NF
  SNR_min = Minimum SNR for target BER with given modulation/FEC
```

### Physical Meaning

- **Signals below sensitivity**: Cannot be detected → link fails completely
- **Signals above sensitivity**: Can be detected → link quality depends on SNR margin

## Why It Matters

### 1. **Link Budget Fundamentals**

Receiver sensitivity is one of the **Friis equation** parameters:

```
Link Budget:
  P_rx (dBm) = P_tx + G_tx - L_path + G_rx

Link Success Criterion:
  P_rx ≥ rx_sensitivity_dbm
```

Without knowing `rx_sensitivity_dbm`, you cannot determine if a link will work.

### 2. **Maximum Range Calculation**

The maximum communication range is directly determined by receiver sensitivity:

```
Max Range = distance where P_rx = rx_sensitivity_dbm

For free space (Sionna RT with antenna patterns):
  FSPL(d) = 20*log10(d) + 20*log10(f) - 147.55 dB (d in m, f in Hz)
  Link budget: L = P_tx - rx_sens (antenna gains already in Sionna path loss)
  d_max = 10^((L - 20*log10(f) + 147.55) / 20)

For FSPL-only calculations (no antenna effects):
  Link budget: L = P_tx + G_tx - rx_sens + G_rx
  d_max = 10^((L - 20*log10(f) + 147.55) / 20)

CRITICAL: Include antenna gains G_tx and G_rx only when using FSPL without Sionna RT.
With Sionna RT (default), antenna pattern gains are already included in path loss.
```

**Example (vacuum_20m scenario):**
- TX power: 20 dBm
- Frequency: 5.18 GHz
- Antenna gain: 0 dBi (isotropic, as configured in vacuum_20m example)
- FSPL at 20m: 72.76 dB
- Received power: 20 - 72.76 = **-52.76 dBm**

| Radio Type | Sensitivity | Link at 20m | Max Range (0 dBi) | Max Range (4.5 dBi each) |
|------------|-------------|-------------|-------------------|--------------------------|
| WiFi 6 (802.11ax) | -80 dBm | ✅ Works (-53 > -80) | **460 m** | 1.3 km |
| WiFi 5 (802.11ac) | -75 dBm | ✅ Works (-53 > -75) | **259 m** | 730 m |
| Cheap IoT | -60 dBm | ✅ Works (-53 > -60) | **46 m** | 130 m |
| Very poor | -40 dBm | ❌ Fails (-53 < -40) | **4.6 m** | 13 m |

**Key insight**: At 20m, even poor receivers work. However, max range is **critically dependent on antenna gains**:
- With 0 dBi antennas (vacuum_20m example): WiFi 6 reaches 460m
- With 4.5 dBi antennas (9 dB total gain): WiFi 6 reaches 1.3 km (2.82× improvement)

### 3. **Interference Filtering (SINR)**

In SINR calculations, interferers **below** receiver sensitivity are correctly ignored:

```python
# From SINRCalculator.calculate_sinr()
filtered_interference = [
    term for term in interference_terms
    if term.power_dbm >= rx_sensitivity_dbm
]
```

**Why this matters:**
- WiFi 6 (-80 dBm): Detects weak interferers → more interference → lower SINR
- WiFi 5 (-75 dBm): Ignores weak interferers → less interference → higher SINR

This is **physically accurate**: less sensitive receivers don't "hear" weak signals.

### 4. **Radio-Specific Values**

Different radio technologies have vastly different sensitivities:

| Technology | Sensitivity | Notes |
|------------|-------------|-------|
| **WiFi 6** (802.11ax) | -82 dBm | IEEE spec: MCS 0, 20 MHz, BPSK 1/2 |
| **WiFi 5** (802.11ac) | -82 dBm | IEEE spec: MCS 0, 20 MHz (same as WiFi 6) |
| **WiFi 4** (802.11n) | -82 dBm | IEEE spec: MCS 0, 20 MHz (same as WiFi 6) |
| **WiFi (conservative)** | -75 to -80 dBm | Real-world with fading margins |
| **5G NR** (base station) | -101 dBm | 3GPP TS 38.104 (high-performance) |
| **5G NR** (UE) | -94.5 dBm | 3GPP TS 38.101 (mobile device) |
| **LoRa** (SF12) | -137 dBm | Semtech SX127x datasheet (extremely sensitive) |
| **Bluetooth** | -82 to -103 dBm | BT 5.0, mode-dependent (LE coded PHY) |
| **Cheap IoT** | -60 to -70 dBm | Low-cost radios (poor sensitivity) |

**Key points:**
- IEEE WiFi specs (802.11ax/ac/n) all specify -82 dBm for lowest MCS
- Conservative values (-75 to -80 dBm) account for real-world fading margins
- Using incorrect sensitivity leads to inaccurate range predictions (off by 2-3×)

## Why Was It Missing?

### Historical Context

Looking at the code history:

1. **SNRCalculator** (Phase 0): Focused on **thermal noise** only, not receiver hardware limits
2. **SINRCalculator** (Phase 1): Introduced `rx_sensitivity_dbm` for interference filtering
3. **Schema** (all phases): **Never exposed** `rx_sensitivity_dbm` to users

### Assumptions Made

The code made these assumptions:
- ✅ Thermal noise floor varies with bandwidth (correct)
- ❌ All receivers use WiFi 6 sensitivity (-80 dBm) (incorrect)
- ❌ Sensitivity is implementation detail, not user-configurable (incorrect)

### Result

- Internal calculations used hardcoded `-80.0 dBm`
- Users couldn't simulate other radio types
- Link budget calculations were WiFi 6-specific

## Implementation

### Schema Changes

Added `rx_sensitivity_dbm` to `WirelessParams`:

```python
class WirelessParams(BaseModel):
    rx_sensitivity_dbm: float = Field(
        default=-80.0,  # WiFi 6 default
        description="Receiver sensitivity in dBm (minimum detectable signal). "
                    "Examples: WiFi 6: -80 dBm, WiFi 5: -75 dBm, LoRa: -137 dBm, 5G: -95 dBm",
        le=0.0,      # Must be negative (power level)
        ge=-150.0,   # Thermal noise floor limit at any bandwidth
    )
```

### YAML Example

```yaml
nodes:
  node1:
    interfaces:
      eth1:
        wireless:
          rf_power_dbm: 20.0
          rx_sensitivity_dbm: -80.0  # NEW: WiFi 6 receiver
          frequency_ghz: 5.18
          bandwidth_mhz: 80
          # ... other params
```

### Usage in Code

```python
# SNR calculation (link budget)
rx_power, snr = calc.calculate_link_snr(...)
if rx_power < rx_sensitivity_dbm:
    # Link fails - signal below receiver sensitivity
    return unusable_link

# SINR calculation (interference filtering)
filtered_interference = [
    term for term in interference_terms
    if term.power_dbm >= rx_sensitivity_dbm
]
```

## Test Coverage

Created comprehensive test suite in `tests/unit/test_rx_sensitivity.py`:

1. **Schema validation** (9 tests):
   - Default value (-80 dBm)
   - Custom values for different radio types
   - Boundary validation (-150 to 0 dBm)

2. **Link budget** (4 tests):
   - Signal above/below sensitivity
   - LoRa extreme sensitivity
   - Sensitivity determines max range

3. **SINR calculations** (6 tests):
   - Signal rejection below sensitivity
   - Interferer filtering
   - Edge cases (exactly at threshold)

4. **Real-world scenarios** (2 tests):
   - vacuum_20m with different radios
   - Urban deployment with interference

**All 21 tests pass.**

## Recommendations

### For New Examples

Always specify `rx_sensitivity_dbm` explicitly:

```yaml
# Good: Explicit sensitivity for WiFi 6
rx_sensitivity_dbm: -80.0

# Good: Explicit sensitivity for LoRa
rx_sensitivity_dbm: -137.0

# Acceptable: Relies on default (WiFi 6)
# rx_sensitivity_dbm: -80.0  (implicit)
```

### For Documentation

Update all examples to show:
1. What radio type is being simulated
2. Why that sensitivity value was chosen
3. How it affects maximum range

### For Future Work

Consider adding:
1. **MCS-dependent sensitivity**: Higher-order modulations require better sensitivity
2. **Automatic sensitivity calculation**: From modulation + FEC + target BER
3. **Sensitivity degradation models**: Interference, temperature, aging effects

## Validation

Validated the updated schema with existing examples:

```bash
$ uv run sine validate examples/vacuum_20m/network.yaml
✓ Topology syntax valid
  Nodes: 2 | Links: 1 (wireless)
  Validation complete
```

Example now explicitly shows `rx_sensitivity_dbm: -80.0` for both nodes.

## Conclusion

**Receiver sensitivity is NOT optional** - it's a fundamental parameter that determines:
- Whether a link will work at all
- Maximum communication range
- Which interferers can be detected
- Accuracy of link budget predictions

The addition of `rx_sensitivity_dbm` to the schema makes SiNE accurate for:
- Different radio technologies (WiFi, LoRa, 5G, custom)
- Realistic range predictions
- Proper interference modeling
- Academic research requiring precise RF modeling

**Important note on antenna gains**: SiNE correctly handles antenna pattern gains when using Sionna RT. The path loss computed by Sionna's PathSolver **already includes** antenna pattern effects, so the SNRCalculator uses `from_sionna=True` mode to avoid double-counting gains. This is validated in unit tests and documented in `src/sine/channel/snr.py` and `src/sine/channel/server.py`.

This parameter should have been present from day one. Better late than never.

## Document Corrections

**Original version errors** (identified by wireless comms engineer review, 2026-01-17):

1. **Max range table** (lines 60-66): Assumed 9 dB antenna gain (4.5 dBi each end) but vacuum_20m uses 0 dBi
   - **Fixed**: Added two columns showing max range with both 0 dBi and 4.5 dBi antennas
   - Error magnitude: 2.82× overestimation (9 dB = 10^(9/20) = 2.82)

2. **FSPL at 20m**: Stated ~68 dB, actual is 72.76 dB
   - **Fixed**: Corrected to 72.76 dB with explicit calculation reference

3. **WiFi sensitivity values**: Listed -75 to -80 dBm, IEEE spec is -82 dBm for all WiFi standards
   - **Fixed**: Updated table to show IEEE spec (-82 dBm) and real-world conservative values separately

4. **Received power at 20m**: Stated -48 dBm, actual is -52.76 dBm (with 0 dBi antennas)
   - **Fixed**: Corrected to -52.76 dBm matching FSPL calculation

**Code implementation**: No errors found. Antenna gain handling is correct (uses `from_sionna=True` to avoid double-counting). All 21 unit tests pass.

---

**Author**: Claude (Anthropic)
**Date**: 2026-01-17 (original), 2026-01-17 (corrections)
**Reviewed by**: Claude Wireless Comms Engineer Agent
**Related Files**:
- [src/sine/config/schema.py](src/sine/config/schema.py#L167-L173) - Schema definition
- [tests/unit/test_rx_sensitivity.py](tests/unit/test_rx_sensitivity.py) - Test suite
- [tests/unit/test_snr.py](tests/unit/test_snr.py#L58-L115) - Antenna gain handling tests
- [examples/vacuum_20m/network.yaml](examples/vacuum_20m/network.yaml) - Updated example
