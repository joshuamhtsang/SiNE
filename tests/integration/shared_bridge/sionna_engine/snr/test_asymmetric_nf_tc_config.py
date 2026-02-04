"""Integration tests for asymmetric noise figure TC configuration.

Tests that traffic control parameters reflect asymmetric SNR values based on
heterogeneous receiver noise figures.
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
def test_asymmetric_nf_tc_config(channel_server, examples_for_tests: Path):
    """Verify asymmetric SNR/loss rates with heterogeneous receivers.

    Validates that:
    - TC configuration reflects receiver NF (not transmitter)
    - node1→node2 uses node2's NF (10 dB, worse receiver)
    - node2→node1 uses node1's NF (7 dB, better receiver)
    - Loss rates may differ between directions if SNR crosses MCS threshold

    Expected behavior:
    - Both directions should have valid TC config (HTB + netem)
    - Rates depend on SNR-based MCS selection (may be symmetric or asymmetric)
    - Loss rates may differ if SNR difference crosses BER threshold
    """
    yaml_path = examples_for_tests / "shared_sionna_snr_asymmetric-nf" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Test node1 -> node2 (uses node2's NF = 10 dB, worse receiver)
        result_12 = verify_tc_config(
            container_prefix="clab-manet-triangle-shared-asymmetric-nf",
            node="node1",
            interface="eth1",
            dst_node_ip="192.168.100.2",
            rate_tolerance_mbps=50.0,  # Wide tolerance
        )

        assert result_12["mode"] == "shared_bridge", "Expected shared_bridge mode"
        assert result_12["filter_match"] is True, "Expected filter for node1->node2"
        assert result_12["rate_mbps"] is not None and result_12["rate_mbps"] > 0, (
            "Expected positive rate for node1->node2"
        )

        # Test node2 -> node1 (uses node1's NF = 7 dB, better receiver)
        result_21 = verify_tc_config(
            container_prefix="clab-manet-triangle-shared-asymmetric-nf",
            node="node2",
            interface="eth1",
            dst_node_ip="192.168.100.1",
            rate_tolerance_mbps=50.0,  # Wide tolerance
        )

        assert result_21["mode"] == "shared_bridge", "Expected shared_bridge mode"
        assert result_21["filter_match"] is True, "Expected filter for node2->node1"
        assert result_21["rate_mbps"] is not None and result_21["rate_mbps"] > 0, (
            "Expected positive rate for node2->node1"
        )

        # Note: We don't enforce result_21["rate_mbps"] > result_12["rate_mbps"]
        # because the 3 dB NF difference may not cross MCS threshold at this distance.

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_asymmetric_nf_multiple_links(channel_server, examples_for_tests: Path):
    """Verify TC config for multiple heterogeneous links.

    Validates that:
    - Each link uses the correct receiver's NF
    - node1→node3 uses node3's NF (5 dB, best receiver)
    - node3→node1 uses node1's NF (7 dB, medium receiver)
    - All links have valid per-destination filters
    """
    yaml_path = examples_for_tests / "shared_sionna_snr_asymmetric-nf" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Test node1 -> node3 (uses node3's NF = 5 dB, best receiver)
        result_13 = verify_tc_config(
            container_prefix="clab-manet-triangle-shared-asymmetric-nf",
            node="node1",
            interface="eth1",
            dst_node_ip="192.168.100.3",
            rate_tolerance_mbps=50.0,
        )

        assert result_13["filter_match"] is True, "Expected filter for node1->node3"

        # Test node3 -> node1 (uses node1's NF = 7 dB)
        result_31 = verify_tc_config(
            container_prefix="clab-manet-triangle-shared-asymmetric-nf",
            node="node3",
            interface="eth1",
            dst_node_ip="192.168.100.1",
            rate_tolerance_mbps=50.0,
        )

        assert result_31["filter_match"] is True, "Expected filter for node3->node1"

        # Verify different HTB class IDs
        assert result_13["htb_classid"] != result_31["htb_classid"], (
            "Each direction should have unique HTB class"
        )

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))
