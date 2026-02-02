# SiNE Test Suite

This directory contains the test suite for SiNE (Sionna-based Network Emulation), organized by test type and functionality.

## Directory Structure

```
tests/
├── unit/                          # Unit tests (fast, no external dependencies)
│   ├── channel/                   # Channel computation tests
│   ├── engine/                    # Engine comparison tests
│   ├── protocols/                 # Protocol logic tests
│   ├── config/                    # Configuration validation tests
│   └── server/                    # Server logic tests
├── integration/                   # Integration tests (require sudo and containers)
│   ├── point_to_point/            # P2P topology tests
│   │   ├── sionna_engine/
│   │   │   ├── snr/               # SNR-only tests
│   │   │   └── sinr/              # SINR with interference tests
│   │   └── fallback_engine/
│   │       ├── snr/               # Fallback engine SNR tests
│   │       └── sinr/              # Fallback engine SINR tests
│   ├── shared_bridge/             # Shared bridge (MANET) tests
│   │   ├── sionna_engine/
│   │   │   ├── snr/               # MANET without interference
│   │   │   └── sinr/              # MANET with interference
│   │   └── fallback_engine/
│   │       ├── snr/
│   │       └── sinr/
│   ├── cross_cutting/             # Tests affecting multiple modes
│   ├── fixtures.py                # Shared integration test fixtures
│   └── conftest.py                # Integration-specific pytest config
└── conftest.py                    # Root pytest configuration and fixtures
```

## Test Categories

### Unit Tests (`tests/unit/`)

Fast, isolated tests with no external dependencies. Test individual components and functions.

**Channel Tests** (`unit/channel/`):
- `test_snr.py` - SNR calculations from link budgets
- `test_modulation.py` - BER/BLER formulas for modulation schemes
- `test_per_calculator.py` - Packet Error Rate calculations
- `test_mcs.py` - MCS selection logic and hysteresis
- `test_rx_sensitivity.py` - Receiver sensitivity validation
- `test_noise_figure_snr.py` - Noise figure impact on SNR

**Engine Tests** (`unit/engine/`):
- `test_fallback_engine.py` - Fallback engine logic
- `test_engine_comparison.py` - Sionna vs Fallback validation

**Protocol Tests** (`unit/protocols/`):
- `test_interference_engine.py` - Interference calculations
- `test_sinr.py` - SINR computation
- `test_csma_model.py` - CSMA/CA protocol logic
- `test_tdma_model.py` - TDMA protocol logic
- `test_sinr_mac_integration.py` - MAC + SINR integration
- `test_aclr_filtering.py` - ACLR frequency filtering

**Config Tests** (`unit/config/`):
- `test_schema.py` - Topology schema validation
- `test_noise_figure.py` - Noise figure configuration

**Server Tests** (`unit/server/`):
- `test_server_engine_selection.py` - Engine selection logic

**Running unit tests:**
```bash
# All unit tests
uv run pytest tests/unit/ -v

# Specific category
uv run pytest tests/unit/channel/ -v
uv run pytest tests/unit/protocols/ -v
```

### Integration Tests (`tests/integration/`)

Full deployment tests that validate the entire SiNE system with containerlab + netem. **Requires sudo access.**

**Organization:** Tests are organized by:
1. **Topology mode**: Point-to-point or Shared bridge
2. **Engine type**: Sionna or Fallback
3. **Interference mode**: SNR (no interference) or SINR (with interference)

**Point-to-Point Tests** (`integration/point_to_point/`):
- `fallback_engine/snr/test_fallback_deployment.py` - Basic fallback deployment
- `fallback_engine/snr/test_fallback_netem_params.py` - Netem parameter validation

**Shared Bridge Tests** (`integration/shared_bridge/`):
- `sionna_engine/snr/test_manet_connectivity.py` - MANET connectivity tests
- `sionna_engine/snr/test_manet_routing.py` - Routing table validation
- `sionna_engine/snr/test_manet_tc_config.py` - TC flower filter validation

**Cross-Cutting Tests** (`integration/cross_cutting/`):

Tests that affect multiple modes or demonstrate phenomena across topologies:
- `test_noise_figure_deployment.py` - Noise figure configuration and impact
- `test_mac_throughput.py` - MAC protocol throughput validation
- `test_rt_to_netem_phenomena.py` - Ray tracing phenomena (multipath, delay spread, LOS/NLOS)

**Running integration tests:**
```bash
# All integration tests (requires sudo)
UV_PATH=$(which uv) sudo -E uv run pytest tests/integration/ -v -s

# Specific category
UV_PATH=$(which uv) sudo -E uv run pytest tests/integration/point_to_point/ -v -s
UV_PATH=$(which uv) sudo -E uv run pytest tests/integration/shared_bridge/ -v -s
UV_PATH=$(which uv) sudo -E uv run pytest tests/integration/cross_cutting/ -v -s
```

**Why sudo?** Integration tests require sudo for:
- Container network namespace access (via `nsenter`)
- Netem configuration (via `tc` tool)
- Per-destination traffic control (tc flower filters for shared bridge)

## Pytest Markers

Use markers to selectively run tests:

| Marker | Description | Usage |
|--------|-------------|-------|
| `integration` | Full deployment tests (require sudo) | `pytest -m integration` |
| `slow` | Tests taking 5-60 seconds | `pytest -m slow` |
| `very_slow` | Tests taking >60 seconds | `pytest -m very_slow` |
| `sionna` | Tests requiring Sionna/GPU | `pytest -m sionna` |
| `fallback` | Tests using fallback engine | `pytest -m fallback` |
| `gpu_memory_8gb` | Tests requiring 8GB+ GPU memory | `pytest -m gpu_memory_8gb` |
| `gpu_memory_16gb` | Tests requiring 16GB+ GPU memory | `pytest -m gpu_memory_16gb` |

**Examples:**
```bash
# Fast tests only (exclude slow)
uv run pytest -m "not slow and not very_slow" -v

# Integration tests only
UV_PATH=$(which uv) sudo -E uv run pytest -m integration -v -s

# Sionna tests (require GPU)
uv run pytest -m sionna -v

# Fallback tests (no GPU needed)
uv run pytest -m fallback -v
```

## Test Fixtures

### Root-level Fixtures ([conftest.py](conftest.py))

Available to all tests via automatic pytest discovery:
- `project_root` - Path to project root directory
- `examples_dir` - Path to examples/ directory (deprecated, use specific fixtures)
- `scenes_dir` - Path to scenes/ directory

### Integration Fixtures ([integration/conftest.py](integration/conftest.py))

Available to all integration tests:
- `examples_for_user` - Path to examples/for_user/ directory
- `examples_for_tests` - Path to examples/for_tests/ directory
- `examples_common` - Path to examples/common_data/ directory

### Integration Helper Functions ([integration/fixtures.py](integration/fixtures.py))

Import these explicitly in integration tests:
```python
from tests.integration.fixtures import channel_server, deploy_topology, run_iperf3_test
```

Available fixtures and helpers:
- `channel_server` - Session-scoped pytest fixture (starts/stops channel server)
- `deploy_topology()` - Deploy a topology using sine CLI
- `destroy_topology()` - Cleanup deployed topology
- `run_iperf3_test()` - Run throughput tests between containers
- `test_ping_connectivity()` - Validate all-to-all connectivity
- `configure_ips()` - Configure IP addresses on container interfaces
- `get_uv_path()` - Get path to uv executable

## Running Tests

**All tests:**
```bash
# Unit tests (no sudo)
uv run pytest tests/unit/ -v

# Integration tests (requires sudo)
UV_PATH=$(which uv) sudo -E uv run pytest tests/integration/ -v -s

# All tests (unit + integration)
uv run pytest tests/unit/ -v && \
  UV_PATH=$(which uv) sudo -E uv run pytest tests/integration/ -v -s
```

**Single test file:**
```bash
uv run pytest tests/unit/channel/test_snr.py -v
```

**Single test function:**
```bash
uv run pytest tests/unit/channel/test_snr.py::test_calculate_snr_with_valid_inputs -v
```

**Collect tests without running:**
```bash
uv run pytest --collect-only
```

## Test Development Guidelines

1. **Choose the right location:**
   - Pure computational logic? → `tests/unit/`
   - Full system deployment? → `tests/integration/`
   - For integration tests, use the topology/engine/interference hierarchy

2. **Use descriptive names:** Follow the pattern `test_<scenario>_<expected_behavior>`

3. **Use fixtures:** Import from `conftest.py` or `integration/fixtures.py`

4. **Mark appropriately:** Add pytest markers (`@pytest.mark.slow`, `@pytest.mark.integration`, etc.)

5. **Clean up:** Integration tests must clean up containers/networks in `finally` blocks

6. **Use examples from for_tests/:** Integration tests should reference `examples/for_tests/` examples

## Examples Organization

Integration tests use examples from `examples/for_tests/` with a flat naming convention:

**Naming pattern:** `<topology>_<engine>_<interference>_<name>`

Where:
- `topology`: `p2p` or `shared`
- `engine`: `sionna` or `fallback`
- `interference`: `snr` or `sinr`
- `name`: Descriptive name (e.g., `vacuum`, `triangle`, `csma`)

**Examples:**
- `p2p_fallback_snr_vacuum/` - Point-to-point, fallback engine, SNR-only, free space
- `p2p_sionna_snr_two-rooms/` - Point-to-point, Sionna, SNR-only, indoor scene
- `shared_sionna_sinr_triangle/` - Shared bridge, Sionna, SINR, 3-node triangle
- `shared_sionna_snr_csma-mcs/` - Shared bridge, Sionna, SNR, CSMA with MCS

**Benefits:**
- Easy to search with grep (e.g., `grep -r "p2p_sionna" tests/`)
- Self-documenting (name tells you topology, engine, and interference mode)
- No nested directories to navigate

## CI/CD Integration

The test suite is designed for CI/CD pipelines:

**Fast feedback:**
```bash
# Run only fast unit tests (< 5 seconds)
uv run pytest tests/unit/ -m "not slow" -v
```

**Nightly full suite:**
```bash
# Run all tests including slow ones
uv run pytest tests/unit/ -v
UV_PATH=$(which uv) sudo -E uv run pytest tests/integration/ -v -s
```

**GPU-aware testing:**
```bash
# Skip GPU tests in CPU-only environments
uv run pytest -m "not sionna" -v
```

## Adding New Tests

1. **Choose the appropriate directory:**
   - Channel computation? → `tests/unit/channel/`
   - Protocol behavior? → `tests/unit/protocols/`
   - Full deployment? → `tests/integration/<topology>/<engine>/<interference>/`

2. **Create or use example topology:**
   - For integration tests, use existing examples from `examples/for_tests/`
   - If needed, create new example with flat naming: `<topology>_<engine>_<interference>_<name>/`

3. **Add pytest markers:**
   ```python
   @pytest.mark.integration
   @pytest.mark.slow
   def test_my_deployment():
       ...
   ```

4. **Use fixtures:**
   ```python
   def test_something(examples_for_tests: Path):
       yaml_path = examples_for_tests / "p2p_fallback_snr_vacuum" / "network.yaml"
       ...
   ```

5. **Clean up in integration tests:**
   ```python
   def test_deployment(examples_for_tests: Path):
       yaml_path = examples_for_tests / "p2p_fallback_snr_vacuum" / "network.yaml"
       try:
           deploy_topology(yaml_path)
           # ... test logic
       finally:
           destroy_topology(yaml_path)
   ```

6. **Update this README** if adding a new test category or major functionality

## Test Statistics

**Current test inventory** (as of 2026-01-31):
- **Unit tests**: ~270 tests across 15 files
  - Channel: 130+ tests (SNR, BER, BLER, PER, MCS, noise figure)
  - Protocols: 47 tests (SINR, interference, CSMA, TDMA)
  - Config: Schema validation tests
  - Engine: Comparison and fallback tests
  - Server: Engine selection tests

- **Integration tests**: 26 tests across 11 files
  - Point-to-point fallback: 5 tests (deployment, netem params, auto mode)
  - Shared bridge SNR: 6 tests (connectivity, routing, tc config)
  - Cross-cutting: 15 tests (noise figure, MAC throughput, RT phenomena)

**Test coverage:**
- ✅ P2P with fallback engine
- ✅ Shared bridge with Sionna
- ✅ Noise figure configuration
- ✅ MAC protocol throughput
- ✅ Ray tracing phenomena (multipath, delay spread, LOS/NLOS)
- ⬜ P2P with Sionna (Phase 5 - future work)
- ⬜ SINR interference tests (Phase 5 - future work)
- ⬜ Adaptive MCS integration tests (Phase 5 - future work)

See [dev_resources/PLAN_2026-01-31_tests-refactor.md](../dev_resources/PLAN_2026-01-31_tests-refactor.md) for the full refactoring plan and future work.
