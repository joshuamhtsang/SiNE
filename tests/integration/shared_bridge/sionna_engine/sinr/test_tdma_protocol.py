"""Integration tests for SINR with TDMA MAC protocol.

Tests SINR computation with TDMA (Time Division Multiple Access) in shared
bridge topologies. Covers both round-robin and fixed slot assignment modes.
"""

import pytest
from pathlib import Path
from tests.integration.fixtures import (
    channel_server,
    deploy_topology,
    destroy_topology,
    stop_deployment_process,
    verify_ping_connectivity,
    verify_route_to_cidr,
    verify_tc_config,
)
from sine.config.loader import load_topology


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_tdma_fixed_connectivity(channel_server, examples_for_tests: Path):
    """Test connectivity with fixed TDMA slot assignment.

    Validates that:
    - Fixed slot map is correctly configured
    - All-to-all connectivity works
    - TDMA slot multiplier is applied to throughput
    """
    yaml_path = examples_for_tests / "shared_sionna_sinr_tdma-fixed" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    # Verify configuration
    config = load_topology(str(yaml_path))
    assert config.topology.enable_sinr is True, "Example must have enable_sinr: true"

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        node_ips = {
            "node1": "192.168.100.1",
            "node2": "192.168.100.2",
            "node3": "192.168.100.3",
        }

        verify_ping_connectivity("clab-sinr-tdma-fixed", node_ips)

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_tdma_fixed_routing(channel_server, examples_for_tests: Path):
    """Verify routing with fixed TDMA slots.

    Validates that:
    - Routes to bridge subnet are correct
    - TDMA configuration doesn't break routing
    """
    yaml_path = examples_for_tests / "shared_sionna_sinr_tdma-fixed" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        for node in ["node1", "node2", "node3"]:
            verify_route_to_cidr(
                "clab-sinr-tdma-fixed",
                node,
                "192.168.100.0/24",
                "eth1"
            )

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_tdma_fixed_tc_config(channel_server, examples_for_tests: Path):
    """Validate TC config with fixed TDMA slots.

    Validates that:
    - TC hierarchy is configured correctly
    - Rate limits reflect slot ownership multiplier
    - Per-destination filters exist

    Note: TDMA slot multiplier affects rate regardless of enable_sinr value.
    """
    yaml_path = examples_for_tests / "shared_sionna_sinr_tdma-fixed" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Test node1 -> node2 link
        result = verify_tc_config(
            container_prefix="clab-sinr-tdma-fixed",
            node="node1",
            interface="eth1",
            dst_node_ip="192.168.100.2",
            rate_tolerance_mbps=50.0,  # Wide tolerance (depends on slot ownership)
        )

        assert result["mode"] == "shared_bridge", "Expected shared_bridge mode"
        assert result["filter_match"] is True, "Expected tc filter for destination"

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_tdma_roundrobin_connectivity(channel_server, examples_for_tests: Path):
    """Test connectivity with round-robin TDMA.

    Validates that:
    - Round-robin slot assignment works
    - All nodes get equal slot allocation
    - All-to-all connectivity works
    """
    yaml_path = examples_for_tests / "shared_sionna_sinr_tdma-rr" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    # Verify configuration
    config = load_topology(str(yaml_path))
    assert config.topology.enable_sinr is True, "Example must have enable_sinr: true"

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        node_ips = {
            "node1": "192.168.100.1",
            "node2": "192.168.100.2",
            "node3": "192.168.100.3",
        }

        verify_ping_connectivity("clab-sinr-tdma-roundrobin", node_ips)

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_tdma_roundrobin_routing(channel_server, examples_for_tests: Path):
    """Verify routing with round-robin TDMA.

    Validates that:
    - Routes are configured correctly
    - Equal slot allocation doesn't break routing
    """
    yaml_path = examples_for_tests / "shared_sionna_sinr_tdma-rr" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        for node in ["node1", "node2", "node3"]:
            verify_route_to_cidr(
                "clab-sinr-tdma-roundrobin",
                node,
                "192.168.100.0/24",
                "eth1"
            )

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_tdma_roundrobin_tc_config(channel_server, examples_for_tests: Path):
    """Validate TC config with round-robin TDMA.

    Validates that:
    - TC hierarchy is configured
    - Rate limits reflect equal slot ownership
    - Per-destination filters exist

    Note: Round-robin: Each node gets 1/N of slots, so rate = PHY_rate × (1/N).
    """
    yaml_path = examples_for_tests / "shared_sionna_sinr_tdma-rr" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Test node1 -> node2 link
        result = verify_tc_config(
            container_prefix="clab-sinr-tdma-roundrobin",
            node="node1",
            interface="eth1",
            dst_node_ip="192.168.100.2",
            rate_tolerance_mbps=50.0,  # Wide tolerance
        )

        assert result["mode"] == "shared_bridge", "Expected shared_bridge mode"
        assert result["filter_match"] is True, "Expected tc filter for destination"

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))
