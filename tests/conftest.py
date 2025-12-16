"""Pytest configuration and fixtures for SiNE tests."""

import pytest
from pathlib import Path


@pytest.fixture
def project_root() -> Path:
    """Return the project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture
def examples_dir(project_root: Path) -> Path:
    """Return the examples directory."""
    return project_root / "examples"


@pytest.fixture
def scenes_dir(project_root: Path) -> Path:
    """Return the scenes directory."""
    return project_root / "scenes"


@pytest.fixture
def sample_topology_path(examples_dir: Path) -> Path:
    """Return path to sample topology file."""
    return examples_dir / "two_room_wifi" / "network.yaml"


@pytest.fixture
def default_scene_path(scenes_dir: Path) -> Path:
    """Return path to default scene file."""
    return scenes_dir / "two_room_default.xml"
