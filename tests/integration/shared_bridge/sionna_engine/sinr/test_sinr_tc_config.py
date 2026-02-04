"""Integration tests for SINR TC configuration.

Tests that traffic control (tc) parameters are correctly configured for SINR
scenarios with shared bridge topology.
"""

import pytest
from pathlib import Path
from tests.integration.fixtures import (
    channel_server,
    deploy_topology,
    destroy_topology,
    stop_deployment_process,
    verify_tc_config,
)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_sinr_triangle_tc_config(channel_server, examples_for_tests: Path):
    """Validate TC config with SINR-based parameters.

    Validates that:
    - HTB+netem hierarchy is configured (shared bridge mode)
    - Per-destination filters exist for each destination IP
    - Rate limits reflect SINR-computed channel conditions
    - Loss rates account for interference (SINR, not just SNR)

    Note: Expected rate is 192 Mbps (64-QAM, rate-0.5 LDPC, 80 MHz BW).
    With SINR, the rate should be similar to SNR case if SINR is high enough.
    """
    yaml_path = examples_for_tests / "shared_sionna_sinr_triangle" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Test node1 -> node2 link
        result = verify_tc_config(
            container_prefix="clab-manet-triangle-shared-sinr",
            node="node1",
            interface="eth1",
            dst_node_ip="192.168.100.2",
            expected_rate_mbps=192.0,  # 64-QAM, rate-0.5 LDPC
            expected_loss_percent=0.0,  # High SINR scenario
            rate_tolerance_mbps=10.0,  # Allow some variation
            loss_tolerance_percent=0.5,  # Small tolerance
        )

        # Verify shared bridge mode is detected
        assert result["mode"] == "shared_bridge", "Expected shared_bridge mode for SINR topology"

        # Verify filter exists for destination
        assert result["filter_match"] is True, "Expected tc filter for destination IP"

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_sinr_triangle_multiple_destinations(channel_server, examples_for_tests: Path):
    """Verify TC config for multiple destination IPs.

    Validates that:
    - Each destination has its own tc filter and HTB class
    - Rate limits are computed independently for each link
    - All-to-all links are correctly configured
    """
    yaml_path = examples_for_tests / "shared_sionna_sinr_triangle" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Test node1 -> node2 link
        result_12 = verify_tc_config(
            container_prefix="clab-manet-triangle-shared-sinr",
            node="node1",
            interface="eth1",
            dst_node_ip="192.168.100.2",
            rate_tolerance_mbps=10.0,
        )
        assert result_12["filter_match"] is True, "Expected filter for node1->node2"

        # Test node1 -> node3 link
        result_13 = verify_tc_config(
            container_prefix="clab-manet-triangle-shared-sinr",
            node="node1",
            interface="eth1",
            dst_node_ip="192.168.100.3",
            rate_tolerance_mbps=10.0,
        )
        assert result_13["filter_match"] is True, "Expected filter for node1->node3"

        # Verify different HTB class IDs
        assert result_12["htb_classid"] != result_13["htb_classid"], (
            "Each destination should have unique HTB class"
        )

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))
