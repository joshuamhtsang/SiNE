# SiNE Test Suite Refactoring Implementation Plan

**Last Updated:** 2026-01-31 (Post wireless comms engineer review)

## Overview

Refactor the SiNE test suite to organize tests by topology mode (point-to-point vs shared bridge), engine type (Sionna vs fallback), and interference mode (SNR vs SINR). Split examples into user-facing (`for_user/`) and test-specific (`for_tests/`).

**Key Updates from Wireless Comms Review:**
- ✅ **Flat naming for for_tests/** - Grep-friendly structure: `p2p_sionna_snr_vacuum/`
- ✅ **Enhanced pytest markers** - Added slow, very_slow, gpu_memory_8gb/16gb for CI scalability
- ✅ **Strict separation** - two_rooms moved to for_tests/ only (no duplication)
- ✅ **Future test categories** - Documented in Appendix A for later evaluation

**User Preferences Applied:**
- ✅ Move vacuum_20m and manet_triangle_shared to `for_tests/`, create simpler user examples
- ✅ Clean break (no symlinks) - all references updated immediately
- ✅ Incremental migration: Phases 1-4 first (structure + migration), phases 5-6 later (new tests)
- ✅ Extract all inline network.yaml to examples/for_tests/ (no YAML in test code)
- ✅ **Flat naming for for_tests/** - Use `p2p_sionna_snr_vacuum/` style (grep-friendly)
- ✅ **Enhanced pytest markers** - Add slow, very_slow, gpu_memory markers for scalability
- ✅ **two_rooms location** - Keep in for_tests/ only, will update README.md separately

## Current State Summary

**Test Inventory** (318 tests, 31 files):
- `tests/channel/` - 130+ unit tests (SNR, BER, BLER, PER, MCS)
- `tests/protocols/` - 47 tests (SINR, interference, CSMA, TDMA)
- `tests/config/` - Schema validation
- `tests/integration/` - 6 test files, 17 integration tests

**Examples** (12 directories):
- User-facing in README: vacuum_20m, fixed_link, two_rooms, adaptive_mcs_wifi6, manet_triangle_shared, manet_triangle_shared_sinr, sinr_tdma_fixed, mobility, common_data
- Test-specific: csma_mcs_test, sinr_csma, sinr_tdma_roundrobin

**Issues to Fix:**
- Tests scattered across channel/, protocols/, config/, integration/
- No clear categorization by topology mode, engine type, or interference mode
- Some tests create network.yaml inline instead of using examples/
- Examples not separated by purpose (user vs test)
- Fixture duplication in some test files

---

## Phase 1: Directory Structure Setup (1-2 hours)

### Goal
Create new directory structure without breaking existing tests.

### Tasks

**1.1 Create unit test directories:**
```bash
mkdir -p tests/unit/channel
mkdir -p tests/unit/engine
mkdir -p tests/unit/protocols
mkdir -p tests/unit/config
mkdir -p tests/unit/server
```

**1.2 Create integration test directories:**
```bash
mkdir -p tests/integration/point_to_point/sionna_engine/snr
mkdir -p tests/integration/point_to_point/sionna_engine/sinr
mkdir -p tests/integration/point_to_point/fallback_engine/snr
mkdir -p tests/integration/point_to_point/fallback_engine/sinr

mkdir -p tests/integration/shared_bridge/sionna_engine/snr
mkdir -p tests/integration/shared_bridge/sionna_engine/sinr
mkdir -p tests/integration/shared_bridge/fallback_engine/snr
mkdir -p tests/integration/shared_bridge/fallback_engine/sinr

mkdir -p tests/integration/cross_cutting
```

**1.3 Create examples directories:**
```bash
mkdir -p examples/for_user
mkdir -p examples/for_tests
# Flat structure - no subdirectories needed
# Examples will use naming pattern: <topology>_<engine>_<interference>_<name>
```

**1.4 Create new conftest files:**

Create `tests/integration/conftest.py`:
```python
"""Integration test configuration and fixtures."""
import pytest
from pathlib import Path

@pytest.fixture
def examples_for_user(project_root: Path) -> Path:
    """Return examples/for_user directory."""
    return project_root / "examples" / "for_user"

@pytest.fixture
def examples_for_tests(project_root: Path) -> Path:
    """Return examples/for_tests directory (flat structure).

    Examples use naming: <topology>_<engine>_<interference>_<name>
    Example: p2p_fallback_snr_vacuum, shared_sionna_sinr_triangle
    """
    return project_root / "examples" / "for_tests"

@pytest.fixture
def examples_common(project_root: Path) -> Path:
    """Return examples/common_data directory (shared by for_user and for_tests)."""
    return project_root / "examples" / "common_data"
```

**1.5 Update root conftest with pytest markers:**

Add to `tests/conftest.py`:
```python
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "integration: Full deployment tests (require sudo)"
    )
    config.addinivalue_line(
        "markers", "slow: Slow-running tests (>5 seconds)"
    )
    config.addinivalue_line(
        "markers", "very_slow: Very slow tests (>60 seconds)"
    )
    config.addinivalue_line(
        "markers", "sionna: Tests requiring Sionna/GPU"
    )
    config.addinivalue_line(
        "markers", "fallback: Tests using fallback engine"
    )
    config.addinivalue_line(
        "markers", "gpu_memory_8gb: Tests requiring 8GB+ GPU memory"
    )
    config.addinivalue_line(
        "markers", "gpu_memory_16gb: Tests requiring 16GB+ GPU memory"
    )
```

**Usage examples:**
```python
@pytest.mark.slow
def test_moderate_deployment():
    # 5-60 seconds

@pytest.mark.very_slow
@pytest.mark.gpu_memory_8gb
def test_large_scene_ray_tracing():
    # >60 seconds, needs 8GB GPU

# CI/CD selective execution:
# pytest -m "not slow and not very_slow"  # Fast tests only
# pytest -m "slow or very_slow"            # Nightly full suite
```

**1.6 Verify existing tests still pass:**
```bash
uv run pytest tests/ -v
```

---

## Phase 2: Unit Test Migration (2-3 hours)

### Goal
Move unit tests to new structure with updated imports.

### Migration Mapping

**Channel tests → tests/unit/channel/:**
```
tests/channel/test_snr.py                    → tests/unit/channel/test_snr.py
tests/channel/test_modulation.py             → tests/unit/channel/test_modulation.py
tests/channel/test_per_calculator.py         → tests/unit/channel/test_per_calculator.py
tests/channel/test_mcs.py                    → tests/unit/channel/test_mcs.py
tests/channel/test_rx_sensitivity.py         → tests/unit/channel/test_rx_sensitivity.py
tests/channel/test_noise_figure_snr.py       → tests/unit/channel/test_noise_figure_snr.py
```

**Engine tests → tests/unit/engine/:**
```
tests/channel/test_fallback_engine.py        → tests/unit/engine/test_fallback_engine.py
tests/channel/test_sionna_vs_fallback.py     → tests/unit/engine/test_engine_comparison.py
```

**Server tests → tests/unit/server/:**
```
tests/channel/test_server_engine_selection.py → tests/unit/server/test_server_engine_selection.py
```

**Protocol tests → tests/unit/protocols/:**
```
tests/protocols/test_interference_engine.py   → tests/unit/protocols/test_interference_engine.py
tests/protocols/test_sinr.py                  → tests/unit/protocols/test_sinr.py
tests/protocols/test_csma_model.py            → tests/unit/protocols/test_csma_model.py
tests/protocols/test_tdma_model.py            → tests/unit/protocols/test_tdma_model.py
tests/protocols/test_sinr_mac_integration.py  → tests/unit/protocols/test_sinr_mac_integration.py
tests/integration/test_sinr_frequency_filtering.py → tests/unit/protocols/test_aclr_filtering.py
```
Note: `test_sinr_frequency_filtering.py` is marked integration but has no deployment - move to unit tests

**Config tests → tests/unit/config/:**
```
tests/config/test_schema.py                  → tests/unit/config/test_schema.py
tests/config/test_noise_figure.py            → tests/unit/config/test_noise_figure.py
```

### Tasks

**2.1 Move test files:**
```bash
# Move channel tests
mv tests/channel/test_snr.py tests/unit/channel/
mv tests/channel/test_modulation.py tests/unit/channel/
mv tests/channel/test_per_calculator.py tests/unit/channel/
mv tests/channel/test_mcs.py tests/unit/channel/
mv tests/channel/test_rx_sensitivity.py tests/unit/channel/
mv tests/channel/test_noise_figure_snr.py tests/unit/channel/

# Move engine tests
mv tests/channel/test_fallback_engine.py tests/unit/engine/
mv tests/channel/test_sionna_vs_fallback.py tests/unit/engine/test_engine_comparison.py

# Move server tests
mv tests/channel/test_server_engine_selection.py tests/unit/server/

# Move protocol tests
mv tests/protocols/test_interference_engine.py tests/unit/protocols/
mv tests/protocols/test_sinr.py tests/unit/protocols/
mv tests/protocols/test_csma_model.py tests/unit/protocols/
mv tests/protocols/test_tdma_model.py tests/unit/protocols/
mv tests/protocols/test_sinr_mac_integration.py tests/unit/protocols/
mv tests/integration/test_sinr_frequency_filtering.py tests/unit/protocols/test_aclr_filtering.py

# Move config tests
mv tests/config/test_schema.py tests/unit/config/
mv tests/config/test_noise_figure.py tests/unit/config/
```

**2.2 Update imports in moved files:**
- Most imports are absolute (`from sine.channel.snr import ...`) - no changes needed
- Update any relative imports if present
- Update fixture imports if using local fixtures

**2.3 Verify unit tests pass:**
```bash
uv run pytest tests/unit/ -v
```

**2.4 Remove empty old directories:**
```bash
rmdir tests/channel tests/protocols tests/config
```

---

## Phase 3: Examples Migration (1-2 hours)

### Goal
Separate examples into for_user/ and for_tests/, extract inline YAML to files.

### Migration Mapping

**Naming Convention:** `<topology>_<engine>_<interference>_<name>`
- topology: `p2p` or `shared`
- engine: `sionna` or `fallback`
- interference: `snr` or `sinr`

**Move to examples/for_tests/ (test-specific, with flat naming):**
```
examples/vacuum_20m/                  → examples/for_tests/p2p_fallback_snr_vacuum/
examples/two_rooms/                   → examples/for_tests/p2p_sionna_snr_two-rooms/
examples/manet_triangle_shared/       → examples/for_tests/shared_sionna_snr_triangle/
examples/manet_triangle_shared_sinr/  → examples/for_tests/shared_sionna_sinr_triangle/
examples/sinr_csma/                   → examples/for_tests/shared_sionna_sinr_csma/
examples/sinr_tdma_roundrobin/        → examples/for_tests/shared_sionna_sinr_tdma-rr/
examples/sinr_tdma_fixed/             → examples/for_tests/shared_sionna_sinr_tdma-fixed/
examples/csma_mcs_test/               → examples/for_tests/shared_sionna_snr_csma-mcs/
```

**Keep in examples/for_user/ (user-facing):**
```
examples/fixed_link/                      → examples/for_user/fixed_link/ (keep)
examples/adaptive_mcs_wifi6/              → examples/for_user/adaptive_mcs_wifi6/ (keep)
examples/mobility/                        → examples/for_user/mobility/ (keep)
examples/common_data/                     → examples/common_data/ (shared by both for_user and for_tests)
```

**New user examples to create (Phase 3.3):**
```
NEW: examples/for_user/quickstart/        - Ultra-simple 2-node P2P (replaces vacuum_20m for users)
NEW: examples/for_user/indoor/            - Simple indoor example (simpler than two_rooms)
NEW: examples/for_user/manet_basic/       - Simple 3-node MANET (simpler than manet_triangle_shared)
```

**Decision Rationale (2026-01-31):**

After wireless comms engineer review, the following decisions were made:

1. **Flat naming for for_tests/** - Use `p2p_sionna_snr_vacuum/` pattern for grep-ability
2. **Strict separation** - Keep examples in ONE location to avoid duplication
3. **two_rooms location** - Moved to `for_tests/p2p_sionna_snr_two-rooms/`, README.md will be updated separately to reference a different user example
4. **common_data location** - Keep at `examples/common_data/` (shared by both for_user and for_tests)

**Clean separation benefits:**
- ✅ No duplication maintenance burden
- ✅ Clear test coverage: everything in `for_tests/` is tested
- ✅ User examples remain simple and focused
- ✅ Tests don't depend on user-facing examples (better isolation)


### Tasks

**3.1 Move existing examples to for_tests/ (with flat naming):**
```bash
mv examples/vacuum_20m examples/for_tests/p2p_fallback_snr_vacuum
mv examples/two_rooms examples/for_tests/p2p_sionna_snr_two-rooms
mv examples/manet_triangle_shared examples/for_tests/shared_sionna_snr_triangle
mv examples/manet_triangle_shared_sinr examples/for_tests/shared_sionna_sinr_triangle
mv examples/sinr_csma examples/for_tests/shared_sionna_sinr_csma
mv examples/sinr_tdma_roundrobin examples/for_tests/shared_sionna_sinr_tdma-rr
mv examples/sinr_tdma_fixed examples/for_tests/shared_sionna_sinr_tdma-fixed
mv examples/csma_mcs_test examples/for_tests/shared_sionna_snr_csma-mcs
```

**3.2 Move remaining examples to for_user/:**
```bash
mv examples/fixed_link examples/for_user/
mv examples/adaptive_mcs_wifi6 examples/for_user/
mv examples/mobility examples/for_user/
# common_data stays at examples/common_data (shared location)
```

**3.3 Create new simplified user examples:**

Create `examples/for_user/quickstart/network.yaml` - 2-node P2P, minimal config:
- Free-space propagation (vacuum.xml)
- Fixed modulation (64-QAM, no MCS table)
- Clear documentation for first-time users
- Quick deployment (<30 seconds)

Create `examples/for_user/indoor/network.yaml` - 2-node indoor:
- Based on two_rooms but simplified
- Single room, clear LOS/NLOS demonstration

Create `examples/for_user/manet_basic/network.yaml` - 3-node MANET:
- Shared bridge mode
- No SINR (simpler than manet_triangle_shared)
- Clear routing example

**3.4 Extract inline network.yaml from test files:**

Scan all test files for inline YAML creation and extract to examples/for_tests/:
- Search for `yaml.dump()`, `tempfile.NamedTemporaryFile()`, or string-based YAML construction
- Create files with flat naming: `<topology>_<engine>_<interference>_<purpose>/`
- Update test to use file path instead of inline YAML

Example extraction:
```python
# Before (in test file)
yaml_content = """
name: test-topology
topology:
  nodes:
    node1: ...
"""
with tempfile.NamedTemporaryFile() as f:
    f.write(yaml_content.encode())
    deploy_topology(f.name)

# After (in test file)
def test_something(examples_for_tests: Path):
    yaml_path = examples_for_tests / "p2p_fallback_snr_minimal" / "network.yaml"
    deploy_topology(yaml_path)
```

---

## Phase 4: Integration Test Migration (2-3 hours)

### Goal
Move integration tests to categorized structure based on topology/engine/interference mode.

### Migration Mapping

**Point-to-Point + Fallback + SNR:**
```
tests/integration/test_fallback_deployment.py → Split into:
  - tests/integration/point_to_point/fallback_engine/snr/test_fallback_deployment.py
  - tests/integration/point_to_point/fallback_engine/snr/test_fallback_netem_params.py
```

**Shared Bridge + Sionna + SNR:**
```
tests/integration/test_manet_shared_bridge.py → Split into:
  - tests/integration/shared_bridge/sionna_engine/snr/test_manet_connectivity.py
  - tests/integration/shared_bridge/sionna_engine/snr/test_manet_routing.py
  - tests/integration/shared_bridge/sionna_engine/snr/test_manet_tc_config.py
```

**Cross-cutting (affect multiple modes):**
```
tests/integration/test_noise_figure_deployment.py → tests/integration/cross_cutting/test_noise_figure_deployment.py
tests/integration/test_mac_throughput.py          → tests/integration/cross_cutting/test_mac_throughput.py
tests/integration/test_rt_to_netem_phenomena.py   → tests/integration/cross_cutting/test_rt_to_netem_phenomena.py
```

### Tasks

**4.1 Split and move test_fallback_deployment.py:**

Create `tests/integration/point_to_point/fallback_engine/snr/test_fallback_deployment.py`:
- Extract deployment and connectivity tests
- Update imports: `from tests.integration.fixtures import ...`
- Update example paths: `examples_for_tests / "p2p_fallback_snr_vacuum"`
- Remove duplicate fixture definitions (use global conftest.py fixtures)

Create `tests/integration/point_to_point/fallback_engine/snr/test_fallback_netem_params.py`:
- Extract netem parameter validation tests
- Verify delay, loss, rate match expected values

**4.2 Split and move test_manet_shared_bridge.py:**

Create `tests/integration/shared_bridge/sionna_engine/snr/test_manet_connectivity.py`:
- Extract connectivity tests (ping all-to-all)
- Update example path: `examples_for_tests / "shared_sionna_snr_triangle"`

Create `tests/integration/shared_bridge/sionna_engine/snr/test_manet_routing.py`:
- Extract routing table verification tests
- Check routes to bridge CIDR

Create `tests/integration/shared_bridge/sionna_engine/snr/test_manet_tc_config.py`:
- Extract tc flower filter validation tests
- Verify per-destination netem rules

**4.3 Move cross-cutting tests:**
```bash
mv tests/integration/test_noise_figure_deployment.py tests/integration/cross_cutting/
mv tests/integration/test_mac_throughput.py tests/integration/cross_cutting/
mv tests/integration/test_rt_to_netem_phenomena.py tests/integration/cross_cutting/
```

Update imports in moved files:
```python
# Change from:
from .fixtures import channel_server, deploy_topology

# To:
from tests.integration.fixtures import channel_server, deploy_topology
```

Update example paths:
```python
# Change from:
yaml_path = examples_dir / "vacuum_20m" / "network.yaml"

# To (flat naming):
yaml_path = examples_for_tests / "p2p_fallback_snr_vacuum" / "network.yaml"

# Or for two_rooms (now in for_tests):
yaml_path = examples_for_tests / "p2p_sionna_snr_two-rooms" / "network.yaml"
```

**4.4 Keep fixtures.py in place:**
```bash
# NO changes to tests/integration/fixtures.py
# It stays at the same location and is imported by all integration tests
```

**4.5 Verify integration tests pass:**
```bash
UV_PATH=$(which uv) sudo -E pytest tests/integration/point_to_point/ -v -s
UV_PATH=$(which uv) sudo -E pytest tests/integration/shared_bridge/ -v -s
UV_PATH=$(which uv) sudo -E pytest tests/integration/cross_cutting/ -v -s
```

**4.6 Remove old integration test files:**
```bash
rm tests/integration/test_fallback_deployment.py
rm tests/integration/test_manet_shared_bridge.py
# cross_cutting tests already moved
```

---

## Phase 5-6: Future Work (Ongoing)

These phases are for LATER, after phases 1-4 are complete and stable.

### Phase 5: Create New Integration Tests

**Shared Bridge + Sionna + SINR:**
- `test_manet_sinr_interference.py` - Uses `manet_triangle_shared_sinr`, tests SINR computation
- `test_sinr_tdma.py` - Uses `sinr_tdma_*`, tests TDMA slot scheduling
- `test_sinr_csma.py` - Uses `sinr_csma`, tests CSMA/CA with interference

**Point-to-Point + Sionna + SNR:**
- `test_vacuum_deployment.py` - Basic P2P deployment
- `test_adaptive_mcs.py` - MCS selection based on SNR

### Phase 6: Cleanup and Documentation

- Update README.md to reference examples/for_user/ only
- Update CLAUDE.md with new test organization section
- Create tests/README.md documenting test structure
- Add pytest.ini or pyproject.toml configuration for markers

---

## Critical Files to Modify

### Files to Create
1. **tests/integration/conftest.py** - Integration test fixtures (examples_for_user, examples_for_tests, examples_common)
2. **examples/for_user/quickstart/network.yaml** - Simplified user example (optional, Phase 3.3)
3. **examples/for_user/indoor/network.yaml** - Simplified indoor example (optional, Phase 3.3)
4. **examples/for_user/manet_basic/network.yaml** - Simplified MANET example (optional, Phase 3.3)

### Files to Modify
1. **tests/conftest.py** - Add pytest markers (integration, slow, sionna, fallback)
2. **All integration test files** - Update imports and example paths
3. **README.md** - Update to reference examples/for_user/ only
4. **CLAUDE.md** - Add test organization section

### Files to Move
- All unit tests (channel/, protocols/, config/ → unit/)
- All integration tests (integration/ → integration/{category}/)
- All examples (examples/ → examples/for_user/ or examples/for_tests/)

### Files to NOT Modify
- **tests/integration/fixtures.py** - Keep as-is, excellent helper functions
- **src/sine/** - No changes to source code

---

## Verification Steps

After each phase:

**Phase 1:**
```bash
uv run pytest tests/ -v  # All existing tests still pass
ls -la tests/unit/ tests/integration/  # Directories created
ls -la examples/for_user/ examples/for_tests/  # Directories created
```

**Phase 2:**
```bash
uv run pytest tests/unit/ -v  # All unit tests pass in new location
ls tests/channel tests/protocols tests/config  # Old directories removed
```

**Phase 3:**
```bash
ls examples/for_user/  # User examples present
ls examples/for_tests/  # Test examples present
ls examples/  # Old locations removed
```

**Phase 4:**
```bash
UV_PATH=$(which uv) sudo -E pytest tests/integration/ -v -s -m integration
# All integration tests pass in new locations
```

**Final verification:**
```bash
# Run full test suite
uv run pytest tests/unit/ -v
UV_PATH=$(which uv) sudo -E pytest tests/integration/ -v -s -m integration

# Check markers work
uv run pytest -m sionna -v
uv run pytest -m fallback -v

# Verify example paths in README are correct
grep "examples/for_user" README.md
```

---

## Rollback Strategy

Since we're doing a clean break (no symlinks), rollback requires Git:

**If Phase 2 fails:**
```bash
git checkout tests/channel/ tests/protocols/ tests/config/
rm -rf tests/unit/
```

**If Phase 3 fails:**
```bash
git checkout examples/
rm -rf examples/for_user/ examples/for_tests/
```

**If Phase 4 fails:**
```bash
git checkout tests/integration/
rm -rf tests/integration/point_to_point/ tests/integration/shared_bridge/ tests/integration/cross_cutting/
```

**Complete rollback:**
```bash
git reset --hard HEAD  # Nuclear option - reverts everything
```

---

## Success Criteria

Phases 1-4 are complete when:

1. ✅ All 318 existing tests pass in new locations
2. ✅ Directory structure follows proposed organization
3. ✅ Examples separated into for_user/ and for_tests/
4. ✅ No inline YAML in test files (all use examples/for_tests/)
5. ✅ Integration tests use new fixtures (examples_for_user, examples_for_tests)
6. ✅ Old test locations removed (clean break)
7. ✅ CI/CD updated (if applicable)
8. ✅ README.md references examples/for_user/ only
9. ✅ CLAUDE.md documents new test structure

---

## Estimated Timeline

- **Phase 1**: 1-2 hours (directory setup)
- **Phase 2**: 2-3 hours (unit test migration)
- **Phase 3**: 1-2 hours (examples migration + create new user examples + extract inline YAML)
- **Phase 4**: 2-3 hours (integration test migration + split tests)

**Total for phases 1-4**: 6-10 hours of focused work

**Phases 5-6**: Ongoing work (new tests + documentation), 4-6 hours additional

---

## Implementation Order

1. **Phase 1** - Set up structure (safe, no breaking changes)
2. **Phase 2** - Migrate unit tests (low risk, fast tests)
3. **Phase 3** - Reorganize examples (medium risk, affects integration tests)
4. **Phase 4** - Migrate integration tests (higher risk, requires sudo)
5. Verify all tests pass
6. Update CI/CD
7. Commit and push

Then later:
8. **Phase 5** - Add new SINR integration tests
9. **Phase 6** - Final cleanup and documentation

---

## Appendix A: Optional Future Test Categories (Wireless Comms Engineer Recommendations)

These test categories were identified by the wireless comms engineer as potential gaps. **Decision deferred** - evaluate after Phases 1-4 are complete.

### A.1 Channel Validation Tests

**Purpose:** Validate that SiNE's channel computations match theoretical models and industry standards.

**Proposed location:** `tests/unit/channel/validation/`

**Test files:**
1. **test_fspl_vs_theory.py** - Friis equation validation
   - Verify free-space path loss matches theoretical formula
   - Test scenarios: Various distances (1m to 1km), frequencies (2.4 GHz, 5 GHz, 28 GHz)
   - Expected accuracy: Within 0.1 dB of analytical result

2. **test_3gpp_path_loss.py** - 3GPP TR 38.901 compliance
   - Validate against 3GPP path loss models (UMa, UMi, RMa)
   - Test urban macro, urban micro, rural macro scenarios
   - Verify LOS/NLOS transition probabilities

3. **test_itu_indoor_models.py** - ITU-R P.1238 indoor propagation
   - Validate against ITU indoor path loss models
   - Test residential, office, commercial environments
   - Verify frequency-dependent loss coefficients

**Effort estimate:** 4-6 hours (research + implementation)

**Value:** High - ensures SiNE's RF modeling is accurate and trustworthy

### A.2 Frequency Selectivity Validation

**Purpose:** Verify coherence bandwidth computation and ensure delay spread is within valid OFDM range.

**Proposed location:** `tests/unit/channel/test_frequency_selectivity.py`

**Test scenarios:**
- Compute coherence bandwidth: Bc ≈ 1/(2πτ_rms)
- Verify τ_rms < cyclic prefix (800 ns for WiFi 6 short GI)
- Test frequency-flat assumption validity for different environments
- Validate that indoor scenarios (typical τ_rms = 20-300 ns) stay within bounds

**Effort estimate:** 2-3 hours

**Value:** Medium - important for OFDM validity but current AWGN approach is acceptable for typical scenarios

### A.3 FEC Coding Gain Verification

**Purpose:** Validate hardcoded coding gains against Sionna's link-level simulations.

**Proposed location:** `tests/unit/channel/test_fec_coding_gain.py`

**Current assumption:**
- LDPC: +6.5 dB
- Polar: +6.0 dB
- Turbo: +5.5 dB

**Proposed tests:**
- Run Sionna BER simulations with LDPC/Polar/Turbo codes
- Sweep SNR and code rates (1/2, 2/3, 3/4, 5/6)
- Extract coding gain at BER = 10⁻⁵ target
- Compare against hardcoded values
- Document acceptable tolerance (±0.5 dB?)

**Effort estimate:** 6-8 hours (Sionna link-level sim integration)

**Value:** Medium - validates approximations, but current values are industry-typical

### A.4 Link Adaptation Hysteresis

**Purpose:** Verify MCS hysteresis prevents rapid switching at threshold boundaries.

**Proposed location:** `tests/integration/*/adaptive_schemes/test_mcs_hysteresis.py`

**Test scenarios:**
- SNR oscillates around MCS threshold (e.g., 19-21 dB around 20 dB threshold)
- Verify no MCS switching when SNR stays within hysteresis window
- Verify upgrade only when SNR exceeds threshold + hysteresis_db
- Test with mobility scenarios (SNR changes over time)

**Effort estimate:** 3-4 hours

**Value:** High - critical for mobile scenarios to prevent thrashing

### A.5 Multi-band ACLR Validation

**Purpose:** Test ACLR filtering for dual-band scenarios (2.4 GHz + 5 GHz).

**Proposed location:** `tests/unit/protocols/test_multiband_aclr.py`

**Test scenarios:**
- 2.4 GHz interferer, 5 GHz receiver → expect ~45 dB ACLR (orthogonal)
- Adjacent 80 MHz channels at 5 GHz → expect 40 dB ACLR
- Co-channel interference → expect 0 dB ACLR
- Verify IEEE 802.11ax spectral mask correctness

**Effort estimate:** 2-3 hours

**Value:** Medium - important for multi-frequency scenarios

### A.6 Power Control Algorithms

**Purpose:** Test TX power adaptation based on CSI/CQI feedback.

**Proposed location:** `tests/unit/protocols/test_power_control.py`

**Note:** This requires implementing power control first (not currently in SiNE).

**Defer until O-RAN or 3GPP power control features are added.**

### A.7 Antenna Pattern Integration

**Purpose:** Validate Sionna RT antenna patterns produce expected gains.

**Proposed location:** `tests/unit/channel/test_antenna_patterns.py`

**Test scenarios:**
- `iso`: Verify 0 dBi omnidirectional
- `dipole`: Verify 1.76 dBi
- `hw_dipole`: Verify 2.16 dBi
- `tr38901`: Verify 8.0 dBi directional
- Test mutual exclusion with `antenna_gain_dbi` (schema validation)

**Effort estimate:** 2-3 hours

**Value:** High - ensures antenna config is correct and prevents double-counting

### A.8 Channel Reciprocity (TDD Systems)

**Purpose:** Validate uplink/downlink channel symmetry for TDD.

**Proposed location:** `tests/unit/channel/test_reciprocity.py`

**Test scenarios:**
- Compute A→B and B→A channels
- Verify path gains match (within calibration errors)
- Test in multipath environments
- Validate reciprocity holds for Sionna RT

**Effort estimate:** 2-3 hours

**Value:** Low (for now) - mainly useful for MIMO/beamforming where uplink CSI estimates downlink channel

---

## Appendix B: User Decisions (2026-01-31)

### From Initial Planning (15:23)

Flat naming preference for `for_tests/`:
```
<topology_type>_<engine_type>_<interference>_<example_name>

where:
  topology_type: "p2p" or "shared"
  engine_type: "sionna" or "fallback"
  interference: "snr" or "sinr"
```

### From Wireless Comms Review (20:45)

1. **Flat naming** - YES, implement
2. **Missing test categories** - Needs more detail to decide (see Appendix A)
3. **pytest markers** - YES, add slow, very_slow, gpu_memory markers
4. **two_rooms duplication** - Keep in for_tests/ only, will update README.md separately
5. **Progressive user examples numbering** - Not needed right now

---

## User comments (2026-01-31 @ 15:23)

- I would like all the examples in `examples/for_tests/` to have more descriptive names.  For example:

    ~~~
    two_rooms/ ---> p2p_sionna_snr_two-rooms/
    ~~~

    So the name structure is generally:

    ~~~
    <topology_type>_<engine_type>_<interference>_<example_name>
    
    where:

    topology_type: "p2p" or "shared_bridge"
    engine_type: "sionna" or "fallback"
    interference: "snr" or "sinr"
    ~~~