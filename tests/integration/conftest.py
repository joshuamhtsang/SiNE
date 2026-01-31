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
