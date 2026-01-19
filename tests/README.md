# Test Organization

This directory contains the test suite for SiNE (Sionna-based Network Emulation).

## Directory Structure

```
tests/
├── channel/          # Channel computation component tests
├── protocols/        # Wireless protocol model tests
├── integration/      # End-to-end system tests
└── conftest.py       # Shared pytest fixtures
```

### `channel/` - Channel Computation Components

Unit tests for the foundational channel computation pipeline. These tests validate the mathematical models and algorithms that convert ray tracing results into network emulation parameters.

**Test files:**
- [test_snr.py](channel/test_snr.py) - SNR calculations from link budgets (path loss, antenna gains, noise floor)
- [test_modulation.py](channel/test_modulation.py) - BER/BLER formulas for various modulation schemes (BPSK, QPSK, QAM)
- [test_per_calculator.py](channel/test_per_calculator.py) - Packet Error Rate calculations and netem parameter conversion
- [test_mcs.py](channel/test_mcs.py) - MCS (Modulation and Coding Scheme) selection logic and hysteresis
- [test_rx_sensitivity.py](channel/test_rx_sensitivity.py) - Receiver sensitivity parameter validation and filtering

**Characteristics:**
- Fast execution (no external dependencies)
- Isolated unit tests
- Pure computational validation
- ~130 tests total

**Run channel tests:**
```bash
uv run pytest tests/channel/ -v
```

### `protocols/` - Wireless Protocol Models

Tests for MAC layer protocols and interference modeling. These tests validate the behavior of wireless protocols built on top of the channel computation components.

**Test files:**
- [test_interference_engine.py](protocols/test_interference_engine.py) - Ray tracing-based interference calculations and caching
- [test_sinr.py](protocols/test_sinr.py) - SINR computation with interference from multiple transmitters
- [test_csma_model.py](protocols/test_csma_model.py) - CSMA/CA protocol behavior (carrier sensing, hidden nodes, backoff)
- [test_tdma_model.py](protocols/test_tdma_model.py) - TDMA protocol behavior (slot assignment, throughput)
- [test_sinr_mac_integration.py](protocols/test_sinr_mac_integration.py) - Integration between MAC models and SINR calculations

**Characteristics:**
- May involve ray tracing simulations
- Multi-node scenarios
- Protocol-level validation
- ~47 tests total

**Run protocol tests:**
```bash
uv run pytest tests/protocols/ -v
```

### `integration/` - End-to-End System Tests

Full deployment scenarios that validate the entire SiNE system from topology configuration through containerlab deployment to network emulation.

**Test files:**
- [test_manet_shared_bridge.py](integration/test_manet_shared_bridge.py) - MANET topology with shared broadcast domain
- [test_mac_throughput.py](integration/test_mac_throughput.py) - Throughput validation with MAC layer modeling
- [fixtures.py](integration/fixtures.py) - Shared fixtures and helper functions for integration tests

**Characteristics:**
- Requires Docker and sudo access
- Uses containerlab for container orchestration
- Slower execution (full system deployment)
- End-to-end validation

**Shared fixtures and helpers** (in [integration/fixtures.py](integration/fixtures.py)):
- `channel_server` - Session-scoped fixture that starts/stops the channel server
- `deploy_topology()` - Deploy a topology using sine CLI
- `destroy_topology()` - Cleanup deployed topology
- `run_iperf3_test()` - Run throughput tests between containers
- `test_ping_connectivity()` - Validate all-to-all connectivity
- `configure_ips()` - Configure IP addresses on container interfaces
- `get_uv_path()` - Get path to uv executable

**Run integration tests:**
```bash
# Integration tests require sudo for containerlab/netem
sudo $(which uv) run pytest tests/integration/ -v -s
```

## Running Tests

**All tests:**
```bash
uv run pytest tests/ -v
```

**Specific category:**
```bash
uv run pytest tests/channel/ -v       # Channel components only
uv run pytest tests/protocols/ -v     # Protocol models only
sudo $(which uv) run pytest tests/integration/ -v -s  # Integration tests
```

**Single test file:**
```bash
uv run pytest tests/channel/test_snr.py -v
```

**Single test function:**
```bash
uv run pytest tests/channel/test_snr.py::test_calculate_snr_with_valid_inputs -v
```

**Collect tests without running:**
```bash
uv run pytest --collect-only
```

## Test Development Guidelines

1. **Channel tests** should be pure unit tests with no external dependencies
2. **Protocol tests** can use fixtures but should minimize ray tracing overhead
3. **Integration tests** should clean up containers/networks after execution
4. All tests should use descriptive names following the pattern `test_<scenario>_<expected_behavior>`
5. Use pytest fixtures from [conftest.py](conftest.py) for common setup

## Test Fixtures

### Root-level fixtures ([conftest.py](conftest.py))

Available to all tests via automatic pytest discovery:
- `project_root` - Path to project root directory
- `examples_dir` - Path to examples/ directory
- `scenes_dir` - Path to scenes/ directory
- `fixtures_dir` - Path to tests/fixtures/ directory

### Integration test fixtures ([integration/fixtures.py](integration/fixtures.py))

Import these explicitly in integration tests:
```python
from .fixtures import channel_server, deploy_topology, run_iperf3_test
```

Available fixtures and helpers:
- `channel_server` - Session-scoped pytest fixture (starts/stops channel server)
- `deploy_topology()` - Helper function to deploy topology
- `destroy_topology()` - Helper function to cleanup topology
- `run_iperf3_test()` - Helper function for throughput testing
- `test_ping_connectivity()` - Helper function for connectivity validation
- `configure_ips()` - Helper function for IP configuration
- `get_uv_path()` - Helper function to locate uv executable

## CI/CD Integration

The test suite is designed to run in CI/CD pipelines:
- Channel and protocol tests can run without Docker
- Integration tests require Docker daemon and sudo access
- Use `pytest --collect-only` to verify test discovery

## Adding New Tests

When adding new tests:
1. Choose the appropriate directory based on what you're testing:
   - **Channel computation?** → `tests/channel/`
   - **Protocol behavior?** → `tests/protocols/`
   - **End-to-end system?** → `tests/integration/`
2. Follow existing naming conventions
3. Add fixtures to `conftest.py` if shared across multiple test files
4. Update this README if adding a new test category
