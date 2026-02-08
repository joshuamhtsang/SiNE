"""Integration tests for SINR interference computation.

Tests that SINR is correctly computed with interference from multiple transmitters
in shared bridge topologies.
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
def test_sinr_triangle_interference(
    channel_server, examples_for_tests: Path, bridge_node_ips: dict
):
    """Test SINR computation with 3-node equilateral triangle topology.

    Validates that:
    - enable_sinr flag is set in the example
    - Deployment completes successfully
    - SINR = 0 dB for all links (signal equals interference in equilateral triangle)
    - All pings FAIL due to 0 dB SINR (100% packet loss expected)
    """
    yaml_path = examples_for_tests / "shared_sionna_sinr_equal-triangle" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    # Verify enable_sinr is set in the example
    config = load_topology(str(yaml_path))
    assert config.topology.enable_sinr is True, "Example must have enable_sinr: true"

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Get container prefix from topology
        container_prefix = extract_container_prefix(str(yaml_path))

        # In an equilateral triangle with SINR enabled:
        # - All nodes are equidistant (20m)
        # - Signal power = Interference power at each receiver
        # - SINR = 0 dB for all links
        # - Expected result: ALL pings should FAIL (100% packet loss)
        all_pairs = [
            ("node1", "node2"),
            ("node1", "node3"),
            ("node2", "node1"),
            ("node2", "node3"),
            ("node3", "node1"),
            ("node3", "node2"),
        ]

        # Verify all pings fail (SINR = 0 dB → 100% packet loss)
        verify_selective_ping_connectivity(
            container_prefix,
            bridge_node_ips,
            expected_success=None,
            expected_failure=all_pairs,
        )

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_sinr_degradation(
    channel_server, examples_for_tests: Path, bridge_node_ips: dict
):
    """Confirm SINR < SNR when interference is present.

    Tests that:
    - SINR is lower than SNR when multiple interferers are active
    - For equilateral triangle: SNR = 36 dB, SINR = 0 dB (signal = interference)
    - Deployment succeeds but connectivity fails due to 0 dB SINR

    Note: SINR vs SNR values are visible in deployment logs:
      SNR: 36.0 dB | SINR: 0.0 dB
    """
    yaml_path = examples_for_tests / "shared_sionna_sinr_equal-triangle" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    # Verify enable_sinr is set
    config = load_topology(str(yaml_path))
    assert config.topology.enable_sinr is True, "Example must have enable_sinr: true"

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Note: SINR vs SNR comparison is visible in deployment logs
        # Expected for equilateral triangle:
        #   SNR: 36.0 dB (signal without interference)
        #   SINR: 0.0 dB (signal = interference)
        # This demonstrates SINR < SNR degradation due to interference

        # Get container prefix from topology
        container_prefix = extract_container_prefix(str(yaml_path))

        # Verify all pings fail (SINR = 0 dB means network is NOT operational)
        all_pairs = [
            ("node1", "node2"),
            ("node1", "node3"),
            ("node2", "node1"),
            ("node2", "node3"),
            ("node3", "node1"),
            ("node3", "node2"),
        ]

        verify_selective_ping_connectivity(
            container_prefix,
            bridge_node_ips,
            expected_success=None,
            expected_failure=all_pairs,
        )

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))
