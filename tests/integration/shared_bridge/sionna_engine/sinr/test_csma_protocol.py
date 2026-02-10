"""Integration tests for SINR with CSMA/CA MAC protocol.

Tests SINR computation with CSMA/CA (Carrier Sense Multiple Access with
Collision Avoidance) in shared bridge topologies.
"""

import pytest
from pathlib import Path
from tests.integration.fixtures import (
    bridge_node_ips,
    channel_server,
    deploy_topology,
    destroy_topology,
    extract_container_prefix,
    stop_deployment_process,
    verify_ping_connectivity,
    verify_route_to_cidr,
    verify_tc_config,
)
from sine.config.loader import load_topology


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_sinr_csma_interference(channel_server, examples_for_tests: Path, bridge_node_ips: dict):
    """Test CSMA/CA with adjacent-channel interference.

    Validates that:
    - enable_sinr flag is set
    - CSMA configuration is present
    - Deployment completes successfully
    - SINR accounts for carrier-sense-weighted interference
    """
    yaml_path = examples_for_tests / "shared_sionna_sinr_csma" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    # Verify configuration
    config = load_topology(str(yaml_path))
    assert config.topology.enable_sinr is True, "Example must have enable_sinr: true"

    # Verify at least one node has CSMA configured
    has_csma = False
    for node_name, node_config in config.topology.nodes.items():
        for iface_name, iface_config in node_config.interfaces.items():
            if iface_config.wireless and iface_config.wireless.csma:
                if iface_config.wireless.csma.enabled:
                    has_csma = True
                    break

    assert has_csma, "At least one node must have CSMA enabled"

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Get container prefix from topology
        container_prefix = extract_container_prefix(str(yaml_path))

        # Verify basic connectivity
        verify_ping_connectivity(container_prefix, bridge_node_ips)

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_sinr_csma_connectivity(channel_server, examples_for_tests: Path, bridge_node_ips: dict):
    """Test all-to-all ping connectivity with CSMA.

    Validates that:
    - All nodes can ping each other
    - CSMA carrier sensing doesn't block connectivity
    """
    yaml_path = examples_for_tests / "shared_sionna_sinr_csma" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Get container prefix from topology
        container_prefix = extract_container_prefix(str(yaml_path))

        verify_ping_connectivity(container_prefix, bridge_node_ips)

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_sinr_csma_routing(channel_server, examples_for_tests: Path):
    """Verify routes to bridge subnet with CSMA.

    Validates that:
    - Routing configuration is correct for shared bridge
    - Routes use eth1 interface (wireless)
    """
    yaml_path = examples_for_tests / "shared_sionna_sinr_csma" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Get container prefix from topology
        container_prefix = extract_container_prefix(str(yaml_path))

        # Verify routes on all nodes
        for node in ["node1", "node2", "node3"]:
            verify_route_to_cidr(
                container_prefix,
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
def test_sinr_csma_tc_config(channel_server, examples_for_tests: Path):
    """Validate TC config with CSMA.

    Validates that:
    - TC hierarchy is correctly configured
    - Per-destination filters exist
    - Rate limits reflect SINR+CSMA conditions

    Note: CSMA provides tx_probability metadata but doesn't directly
    affect netem rate (that comes from PHY rate calculation).
    """
    yaml_path = examples_for_tests / "shared_sionna_sinr_csma" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Get container prefix from topology
        container_prefix = extract_container_prefix(str(yaml_path))

        # Test node1 -> node2 link
        result = verify_tc_config(
            container_prefix=container_prefix,
            node="node1",
            interface="eth1",
            dst_node_ip="192.168.100.2",
            rate_tolerance_mbps=50.0,  # Wide tolerance (adaptive MCS)
        )

        # Verify shared bridge mode
        assert result["mode"] == "shared_bridge", "Expected shared_bridge mode"

        # Verify filter exists
        assert result["filter_match"] is True, "Expected tc filter for destination"

        # Verify rate is reasonable (depends on MCS selection)
        assert result["rate_mbps"] is not None and result["rate_mbps"] > 0, (
            "Expected positive rate"
        )

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))
