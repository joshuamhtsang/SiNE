# Implementation Plan: Test Assertions Review & Noise Figure Configuration

## Executive Summary

**Task 1**: Review test assertions after antenna configuration strict mutual exclusion changes
**Task 2**: Make noise figure a configurable parameter in network.yaml (currently hardcoded to 7.0 dB)

**Result**: All test assertions are correct. Noise figure configuration requires updates to 5 files + 3 new test files (~400-500 lines total).

---

## Task 1: Test Assertions Review ✅

### Findings: ALL TESTS ARE CORRECT

The wireless communications engineer agent reviewed all 7 test files and confirmed:

**✅ Schema validation tests** ([tests/config/test_schema.py](tests/config/test_schema.py)):
- Lines 8-16: Mutual exclusion test (both antenna_pattern + antenna_gain_dbi → error) ✅
- Lines 19-25: Neither specified test → error ✅
- Lines 28-36: antenna_pattern only → valid ✅
- Lines 39-47: antenna_gain_dbi only → valid ✅
- Lines 69-78: All pattern types (iso/dipole/hw_dipole/tr38901) → valid ✅
- Lines 81-106: Antenna gain range [-10, +30] dBi boundary tests ✅

**Technical correctness**:
- Mutual exclusion prevents double-counting antenna gain (would cause 2-4 dB SNR errors)
- Antenna gain range [-10, +30] dBi is physically realistic:
  - Lower bound: Lossy chip antennas (-10 dBi)
  - Upper bound: Large parabolic dishes (+30 dBi)
- All Sionna RT antenna pattern gains are correct (iso=0.0, dipole=1.76, hw_dipole=2.16, tr38901=8.0 dBi)

**Other test files** (also reviewed and correct):
- [tests/channel/test_sionna_vs_fallback.py](tests/channel/test_sionna_vs_fallback.py) - Engine comparison tests ✅
- [tests/channel/test_rx_sensitivity.py](tests/channel/test_rx_sensitivity.py) - RX sensitivity tests ✅
- [tests/protocols/test_interference_engine.py](tests/protocols/test_interference_engine.py) - Uses antenna_gain_dbi correctly ✅
- [tests/integration/test_sinr_frequency_filtering.py](tests/integration/test_sinr_frequency_filtering.py) - SINR tests ✅
- [tests/integration/test_rt_to_netem_phenomena.py](tests/integration/test_rt_to_netem_phenomena.py) - API-level tests ✅
- [tests/benchmark_interference.py](tests/benchmark_interference.py) - Performance benchmark ✅

**Conclusion**: No changes needed to existing tests.

---

## Task 2: Noise Figure Configuration

### Current State

**Hardcoded locations**:
1. [src/sine/channel/snr.py:40](src/sine/channel/snr.py#L40) - SNRCalculator default parameter: `noise_figure_db: float = 7.0`
2. [src/sine/channel/sinr.py:521](src/sine/channel/sinr.py#L521) - calculate_thermal_noise() default: `noise_figure_db: float = 7.0`
3. [src/sine/channel/server.py:581](src/sine/channel/server.py#L581) - estimate_communication_range() default: `noise_figure_db: float = 7.0`

**Formula**: `Noise_floor_dBm = -174 + 10*log10(BW_Hz) + noise_figure_db`

**Typical values**:
- WiFi 6 receivers: 6-8 dB (7.0 dB is standard) ← current default
- 5G base stations: 3-5 dB (lower NF)
- High-performance SDRs: 2-4 dB (very low NF)
- Low-cost IoT radios: 8-12 dB (higher NF)

### Design Decisions

**1. Schema Structure**: Per-interface parameter with optional node-level fallback

```yaml
nodes:
  node1:
    noise_figure_db: 7.0  # Optional node-level default for all interfaces
    interfaces:
      eth1:
        wireless:
          noise_figure_db: 6.0  # Optional per-interface override
          # If omitted, uses node-level (7.0) or global default (7.0)
```

**Benefits**:
- Flexibility: Different NF per interface (heterogeneous radios)
- Simplicity: Set once at node level for homogeneous deployments
- Backward compatible: Existing YAMLs work without changes

**2. Default Value**: 7.0 dB (WiFi 6 standard)

**Rationale**:
- SiNE targets WiFi 6/OFDM emulation (per CLAUDE.md)
- Typical WiFi 6 consumer receivers: 6-8 dB NF
- Current hardcoded value is 7.0 dB → no behavior change

**3. Validation**: Range [0.0, 20.0] dB

```python
noise_figure_db: float = Field(
    default=7.0,
    ge=0.0,   # Theoretical ideal (for testing)
    le=20.0,  # Extremely poor/broken receiver
    description="Receiver noise figure in dB"
)
```

**4. Backward Compatibility**: Fully backward compatible (additive change)

- Existing network.yaml files work as-is (default=7.0 dB)
- No breaking changes
- Optional parameter with sensible default

### Implementation Plan

#### Files to Modify (5 files)

**1. [src/sine/config/schema.py](src/sine/config/schema.py)** - Schema definition (~30 lines)

Add two fields:

```python
class Node(BaseModel):
    """Node configuration."""
    kind: str
    image: str | None = None
    noise_figure_db: float = Field(
        default=7.0,
        ge=0.0,
        le=20.0,
        description="Default receiver noise figure for all interfaces (dB)"
    )
    interfaces: dict[str, InterfaceConfig] = Field(default_factory=dict)
    # ... other fields

class WirelessParams(BaseModel):
    """Wireless interface parameters."""
    position: Position
    rf_power_dbm: float = Field(ge=-30, le=40)
    noise_figure_db: float = Field(
        default=7.0,  # Default if not specified
        ge=0.0,
        le=20.0,
        description="Receiver noise figure in dB (overrides node-level default)"
    )
    # ... other fields
```

**Location**: Around line 100-200 (Node and WirelessParams classes)

**2. [src/sine/channel/sinr.py](src/sine/channel/sinr.py)** - Add NF to SINRCalculator (~15 lines)

```python
class SINRCalculator:
    def __init__(
        self,
        rx_sensitivity_dbm: float = -80.0,
        apply_capture_effect: bool = False,
        capture_threshold_db: float = 6.0,
        noise_figure_db: float = 7.0,  # ADD THIS
    ):
        self.rx_sensitivity_dbm = rx_sensitivity_dbm
        self.apply_capture_effect = apply_capture_effect
        self.capture_threshold_db = capture_threshold_db
        self.noise_figure_db = noise_figure_db  # ADD THIS
```

**Note**: `calculate_thermal_noise()` already accepts `noise_figure_db` parameter (line 521), so just need to plumb it through.

**3. [src/sine/channel/server.py](src/sine/channel/server.py)** - API request models + endpoints (~60 lines)

Add `noise_figure_db` field to request models:

```python
class LinkRequest(BaseModel):
    """Single link computation request."""
    # ... existing fields
    noise_figure_db: float = Field(
        default=7.0,
        ge=0.0,
        le=20.0,
        description="Receiver noise figure in dB"
    )

class ReceiverInfo(BaseModel):
    """Receiver configuration for SINR calculation."""
    # ... existing fields
    noise_figure_db: float = Field(
        default=7.0,
        ge=0.0,
        le=20.0,
        description="Receiver noise figure in dB"
    )
```

Update endpoint implementations to pass `noise_figure_db`:
- Line ~734-749: Batch endpoint SNRCalculator instantiation
- Line ~660: Batch endpoint SINRCalculator instantiation
- Line ~955: Single endpoint SNRCalculator instantiation
- Line ~1471-1475: SINR endpoint SINRCalculator instantiation

**4. [src/sine/emulation/controller.py](src/sine/emulation/controller.py)** - Pass NF to API (~20 lines)

Extract `noise_figure_db` from WirelessParams and include in API requests:

```python
# Extract from topology
link_request = LinkRequest(
    tx_node=link.tx_node,
    rx_node=link.rx_node,
    # ... other fields
    noise_figure_db=link.wireless_params.noise_figure_db,
)
```

**5. [CLAUDE.md](CLAUDE.md)** - Documentation (~50 lines)

Update "Channel Computation Pipeline" section with noise figure info:

```markdown
### 2. SNR Calculation

Signal-to-Noise Ratio is computed from the link budget:

SNR (dB) = TX_power + TX_gain + RX_gain - Path_loss - Noise_floor

Where:
- Noise_floor = -174 dBm/Hz + 10*log10(bandwidth) + noise_figure_db
- noise_figure_db: Configurable per interface (default: 7.0 dB for WiFi 6)
  - WiFi 6: 6-8 dB
  - 5G base station: 3-5 dB
  - High-end SDR: 2-4 dB
  - Cheap IoT radio: 8-12 dB
```

Add to network.yaml schema section:

```yaml
wireless:
  noise_figure_db: 7.0  # Optional, defaults to 7.0 dB (WiFi 6)
```

#### Test Files to Create (3 files)

**1. [tests/config/test_noise_figure.py](tests/config/test_noise_figure.py)** - Schema validation (~120 lines)

Test cases:
- `test_default_noise_figure()` - Verify default is 7.0 dB
- `test_custom_noise_figure_wifi6()` - Test 6.0 dB (high-performance WiFi)
- `test_custom_noise_figure_5g_bs()` - Test 4.0 dB (base station)
- `test_custom_noise_figure_cheap_iot()` - Test 10.0 dB (cheap radio)
- `test_noise_figure_validation_too_low()` - Test negative NF rejected
- `test_noise_figure_validation_too_high()` - Test >20 dB rejected
- `test_noise_figure_at_boundary_low()` - Test 0.0 dB boundary
- `test_noise_figure_at_boundary_high()` - Test 20.0 dB boundary

**2. [tests/channel/test_noise_figure_snr.py](tests/channel/test_noise_figure_snr.py)** - SNR calculation (~100 lines)

Test cases:
- `test_noise_floor_calculation()` - Verify noise floor changes with NF
  - NF=7 dB: noise_floor = -174 + 79 + 7 = -88 dBm (80 MHz)
  - NF=4 dB: noise_floor = -174 + 79 + 4 = -91 dBm (3 dB better)
- `test_snr_scales_with_noise_figure()` - Verify SNR decreases when NF increases
  - Fixed link: 20 dBm TX, 68 dB path loss → -48 dBm RX
  - NF=7 dB: SNR = -48 - (-88) = 40 dB
  - NF=10 dB: SNR = -48 - (-85) = 37 dB (3 dB worse)

**3. [tests/integration/test_noise_figure_deployment.py](tests/integration/test_noise_figure_deployment.py)** - Full deployment (~80 lines)

Test cases:
- `test_vacuum_20m_default_noise_figure()` - Deploy with default NF (7 dB)
- `test_vacuum_20m_custom_noise_figure()` - Deploy with custom NF (4 dB), verify SNR is 3 dB higher
- `test_heterogeneous_noise_figures()` - Different NF per node (WiFi + LoRa)

**Note**: Integration tests require sudo for netem configuration.

### Example Configuration

```yaml
# Example 1: Default noise figure (WiFi 6)
nodes:
  node1:
    interfaces:
      eth1:
        wireless:
          # noise_figure_db omitted, defaults to 7.0 dB
          rf_power_dbm: 20.0
          frequency_ghz: 5.18
          bandwidth_mhz: 80

# Example 2: Custom noise figure (5G base station)
nodes:
  node1:
    noise_figure_db: 4.0  # Node-level default (5G BS)
    interfaces:
      eth1:
        wireless:
          # Uses node-level 4.0 dB
          rf_power_dbm: 30.0
          frequency_ghz: 3.5
          bandwidth_mhz: 100

# Example 3: Heterogeneous radios (WiFi + LoRa)
nodes:
  node1:
    interfaces:
      eth1:
        wireless:
          noise_figure_db: 7.0  # WiFi interface
          rf_power_dbm: 20.0
          frequency_ghz: 5.18
      eth2:
        wireless:
          noise_figure_db: 6.0  # LoRa interface (better NF)
          rf_power_dbm: 14.0
          frequency_ghz: 0.915
```

### Verification Steps

After implementation:

1. **Schema validation**:
   ```bash
   uv run pytest -s tests/config/test_noise_figure.py
   ```

2. **SNR calculation**:
   ```bash
   uv run pytest -s tests/channel/test_noise_figure_snr.py
   ```

3. **Integration tests** (requires sudo):
   ```bash
   UV_PATH=$(which uv) sudo -E $(which uv) run pytest -s tests/integration/test_noise_figure_deployment.py
   ```

4. **Verify existing topologies still work**:
   ```bash
   uv run sine validate examples/vacuum_20m/network.yaml
   uv run sine validate examples/adaptive_mcs_wifi6/network.yaml
   uv run sine validate examples/manet_triangle_shared_sinr/network.yaml
   ```

5. **Test custom noise figure**:
   - Create a test topology with `noise_figure_db: 4.0` (5G BS)
   - Deploy and verify SNR is 3 dB higher than default (7.0 dB)

---

## Summary

### Task 1: Test Assertions ✅
- **Status**: All tests are correct
- **Action**: None required

### Task 2: Noise Figure Configuration 📝
- **Status**: Design complete, ready for implementation
- **Scope**: 5 files to modify + 3 test files to create
- **Effort**: ~400-500 lines of code
- **Time estimate**: 4-6 hours
- **Risk**: LOW (additive change, full backward compatibility)
- **Breaking changes**: NONE

### Critical Files

**Schema**:
- [src/sine/config/schema.py](src/sine/config/schema.py) - Add noise_figure_db fields to Node and WirelessParams

**Channel computation**:
- [src/sine/channel/snr.py](src/sine/channel/snr.py) - Already accepts noise_figure_db ✅
- [src/sine/channel/sinr.py](src/sine/channel/sinr.py) - Add to SINRCalculator.__init__
- [src/sine/channel/server.py](src/sine/channel/server.py) - Update API request models

**Deployment**:
- [src/sine/emulation/controller.py](src/sine/emulation/controller.py) - Extract and pass noise_figure_db to API

**Documentation**:
- [CLAUDE.md](CLAUDE.md) - Update channel computation pipeline section
