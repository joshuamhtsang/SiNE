"""Integration tests for asym-triangle TC configuration.

Tests that traffic control (tc) parameters reflect the asymmetric link
quality: node1→node2 (good SINR ~9-10 dB) should have a high rate limit,
while node1→node3 (negative SINR ~-3 to -4 dB) should have a very low rate.
"""

import pytest
from pathlib import Path
from tests.integration.fixtures import (
    channel_server,
    deploy_topology,
    destroy_topology,
    extract_container_prefix,
    stop_deployment_process,
    verify_tc_config,
)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_sinr_asym_triangle_tc_config_good_link(channel_server, examples_for_tests: Path):
    """Validate TC config for the good-SINR link (node1→node2).

    node1→node2 is a 30m link with SINR ~9-10 dB.  With QPSK rate-0.5 LDPC
    at 80 MHz the theoretical throughput is ~64 Mbps.  The TC rate limit
    should reflect this: 30–100 Mbps is the acceptable range.

    Validates:
    - shared_bridge mode is detected (HTB hierarchy present)
    - Flower filter exists for node2's IP
    - Rate limit is in the plausible range for good SINR (30–100 Mbps)
    - Loss is low (< 20%) for good SINR
    """
    yaml_path = examples_for_tests / "shared_sionna_sinr_asym-triangle" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        container_prefix = extract_container_prefix(str(yaml_path))

        # node2's IP is 192.168.100.2
        result = verify_tc_config(
            container_prefix=container_prefix,
            node="node1",
            interface="eth1",
            dst_node_ip="192.168.100.2",
        )

        assert result["mode"] == "shared_bridge", (
            "Expected shared_bridge mode for SINR topology"
        )
        assert result["filter_match"] is True, (
            "Expected tc flower filter for node2 destination IP"
        )

        # Rate should reflect QPSK/LDPC at +9-10 dB SINR: ~50-64 Mbps theoretical
        # Wide range to accommodate SINR variation
        assert result["rate_mbps"] is not None, "Expected a rate value from TC config"
        assert 30.0 <= result["rate_mbps"] <= 100.0, (
            f"Rate {result['rate_mbps']:.2f} Mbps outside expected range [30, 100] Mbps "
            f"for node1→node2 (SINR ~9-10 dB, QPSK rate-0.5 LDPC, 80 MHz)"
        )

        # Loss should be low for a good-SINR link
        if result["loss_percent"] is not None:
            assert result["loss_percent"] < 20.0, (
                f"Loss {result['loss_percent']:.2f}% is too high for good-SINR link "
                f"(node1→node2, SINR ~9-10 dB)"
            )

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_sinr_asym_triangle_tc_config_bad_link(channel_server, examples_for_tests: Path):
    """Validate TC config for the bad-SINR link (node1→node3).

    node1→node3 is a 91.2m link with SINR ~-3 to -4 dB.  Negative SINR
    means the interference power exceeds the signal power.  The TC rate
    limit should be very low (< 5 Mbps), reflecting near-total packet loss.

    Validates:
    - shared_bridge mode is detected
    - Flower filter exists for node3's IP (filter is always installed,
      regardless of link quality)
    - Rate limit is very low (< 5 Mbps) for negative SINR
    """
    yaml_path = examples_for_tests / "shared_sionna_sinr_asym-triangle" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        container_prefix = extract_container_prefix(str(yaml_path))

        # node3's IP is 192.168.100.3
        result = verify_tc_config(
            container_prefix=container_prefix,
            node="node1",
            interface="eth1",
            dst_node_ip="192.168.100.3",
        )

        assert result["mode"] == "shared_bridge", (
            "Expected shared_bridge mode for SINR topology"
        )
        assert result["filter_match"] is True, (
            "Expected tc flower filter for node3 destination IP even for bad link"
        )

        # Rate should be very low: negative SINR means near-total packet loss
        assert result["rate_mbps"] is not None, "Expected a rate value from TC config"
        assert result["rate_mbps"] < 5.0, (
            f"Rate {result['rate_mbps']:.2f} Mbps is too high for bad-SINR link "
            f"(node1→node3, SINR ~-3 to -4 dB). Expected < 5 Mbps."
        )

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_sinr_asym_triangle_multiple_destinations(channel_server, examples_for_tests: Path):
    """Verify that node1 has distinct HTB classes for node2 and node3.

    The asymmetric topology is the clearest test of per-destination TC
    configuration: node2 (good SINR) and node3 (bad SINR) should have
    independent HTB class IDs with dramatically different rate limits.

    Validates:
    - Both destinations have tc filters and HTB class IDs
    - The two class IDs are distinct (independent rate limiters)
    - node2's rate is higher than node3's rate (asymmetric SINR)
    """
    yaml_path = examples_for_tests / "shared_sionna_sinr_asym-triangle" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        container_prefix = extract_container_prefix(str(yaml_path))

        result_node2 = verify_tc_config(
            container_prefix=container_prefix,
            node="node1",
            interface="eth1",
            dst_node_ip="192.168.100.2",
            rate_tolerance_mbps=100.0,
        )
        assert result_node2["filter_match"] is True, (
            "Expected filter for node1→node2"
        )

        result_node3 = verify_tc_config(
            container_prefix=container_prefix,
            node="node1",
            interface="eth1",
            dst_node_ip="192.168.100.3",
            rate_tolerance_mbps=100.0,
        )
        assert result_node3["filter_match"] is True, (
            "Expected filter for node1→node3"
        )

        # Each destination must have its own HTB class
        assert result_node2["htb_classid"] != result_node3["htb_classid"], (
            "node2 and node3 destinations must have distinct HTB class IDs; "
            f"both got {result_node2['htb_classid']}"
        )

        # Good-SINR link must have higher rate than bad-SINR link
        assert result_node2["rate_mbps"] is not None, "Expected rate for node2 class"
        assert result_node3["rate_mbps"] is not None, "Expected rate for node3 class"
        assert result_node2["rate_mbps"] > result_node3["rate_mbps"], (
            f"node2 rate ({result_node2['rate_mbps']:.2f} Mbps) should be higher than "
            f"node3 rate ({result_node3['rate_mbps']:.2f} Mbps) due to asymmetric SINR"
        )

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))
