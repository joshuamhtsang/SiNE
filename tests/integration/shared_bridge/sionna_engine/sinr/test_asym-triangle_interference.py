"""Integration tests for asym-triangle SINR interference computation.

Tests that SINR computation is active, that the asymmetric geometry produces
the expected SINR distribution, and that the resulting selective connectivity
(only node1↔node2) is correctly enforced.
"""

from pathlib import Path

import pytest

from tests.integration.fixtures import (
    bridge_node_ips,
    channel_server,
    deploy_topology,
    destroy_topology,
    extract_container_prefix,
    stop_deployment_process,
    verify_selective_ping_connectivity,
)
from sine.config.loader import load_topology


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_sinr_asym_triangle_enable_sinr_flag(examples_for_tests: Path):
    """Guard test: verify enable_sinr is set in the asym-triangle example.

    This is a unit-style check that does not require deployment.
    It ensures the example YAML is correctly configured before the
    heavier deployment tests run.
    """
    yaml_path = examples_for_tests / "shared_sionna_sinr_asym-triangle" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    config = load_topology(str(yaml_path))
    assert config.topology.enable_sinr is True, (
        "shared_sionna_sinr_asym-triangle/network.yaml must have "
        "topology.enable_sinr: true"
    )


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_sinr_asym_triangle_interference_effects(
    channel_server, examples_for_tests: Path, bridge_node_ips: dict
):
    """Verify that SINR produces selective connectivity in the asym-triangle.

    The asymmetric geometry creates two classes of links:
    - node1↔node2 (30m): SINR ~9-10 dB → connectivity SUCCEEDS
    - node1↔node3 (91.2m): SINR ~-3 to -4 dB → connectivity FAILS
    - node2↔node3 (91.2m): SINR ~-3 to -4 dB → connectivity FAILS

    This test uses verify_selective_ping_connectivity() (same pattern as
    equal-triangle tests) to validate both the passing and failing links,
    confirming that the shared helper works correctly with an asymmetric
    topology.
    """
    yaml_path = examples_for_tests / "shared_sionna_sinr_asym-triangle" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        container_prefix = extract_container_prefix(str(yaml_path))

        verify_selective_ping_connectivity(
            container_prefix,
            bridge_node_ips,
            expected_success=[
                ("node1", "node2"),
                ("node2", "node1"),
            ],
            expected_failure=[
                ("node1", "node3"),
                ("node3", "node1"),
                ("node2", "node3"),
                ("node3", "node2"),
            ],
        )

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))
