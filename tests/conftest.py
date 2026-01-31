"""Pytest configuration and fixtures for SiNE tests.

This file provides shared fixtures available to all test files.
Fixtures are automatically discovered by pytest - no imports needed.
"""

import pytest
from pathlib import Path


@pytest.fixture
def project_root() -> Path:
    """Return the project root directory.

    Example:
        def test_something(project_root: Path):
            config_path = project_root / "pyproject.toml"
    """
    return Path(__file__).parent.parent


@pytest.fixture
def examples_dir(project_root: Path) -> Path:
    """Return the examples directory.

    Used by integration tests to locate topology files.

    Example:
        def test_deployment(examples_dir: Path):
            yaml_path = examples_dir / "vacuum_20m" / "network.yaml"
    """
    return project_root / "examples"


@pytest.fixture
def scenes_dir(project_root: Path) -> Path:
    """Return the scenes directory.

    Contains Mitsuba XML scene files for ray tracing.

    Example:
        def test_scene_loading(scenes_dir: Path):
            scene_path = scenes_dir / "vacuum.xml"
    """
    return project_root / "scenes"


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the test fixtures directory.

    Contains test data files like MCS tables, test topologies, etc.

    Example:
        def test_mcs_loading(fixtures_dir: Path):
            mcs_table = fixtures_dir / "mcs_tables" / "wifi6.csv"
    """
    return Path(__file__).parent / "fixtures"


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
