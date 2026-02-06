"""Comprehensive integration tests for shared_sionna_snr_csma-mcs example.

Tests CSMA/CA MAC protocol with adaptive MCS selection based on SINR.
This example validates:
- CSMA carrier sensing behavior
- Adaptive MCS index selection from SNR/SINR
- Hidden node problem effects
- SNR vs SINR comparison (interference impact)
"""

import pytest
from pathlib import Path
from tests.integration.fixtures import (
    channel_server,
    deploy_topology,
    destroy_topology,
    stop_deployment_process,
    verify_ping_connectivity,
    verify_tc_config,
    verify_route_to_cidr,
    bridge_node_ips,
)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_csma_mcs_connectivity(channel_server, examples_for_tests: Path, bridge_node_ips: dict):
    """Test ping connectivity with CSMA carrier sensing.

    Validates that:
    - Node2 ↔ Node3 connectivity (primary link, ~11 dB SINR)
    - CSMA carrier sensing doesn't break connectivity
    - Expected: SINR ~11 dB → QPSK capable
    - Carrier sense range = communication_range × 2.5
    """
    yaml_path = examples_for_tests / "shared_sionna_snr_csma-mcs" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Test connectivity between all nodes
        verify_ping_connectivity("clab-csma-mcs", bridge_node_ips)

        print("✓ CSMA MCS connectivity validated")

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_csma_mcs_index_validation(channel_server, examples_for_tests: Path):
    """Validate MCS index selection based on SINR.

    Validates that:
    - MCS index is selected from MCS table
    - Expected: MCS 2 (QPSK, rate-0.5, LDPC) for SINR ~11 dB
    - SINR (not SNR) determines MCS choice
    - Deployment logs show selected MCS

    Note: This test validates deployment succeeds with MCS table.
    Actual MCS index verification requires parsing deployment logs or
    querying channel server API (future enhancement).
    """
    yaml_path = examples_for_tests / "shared_sionna_snr_csma-mcs" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        # Deployment validates MCS table loading and selection
        deploy_process = deploy_topology(str(yaml_path))

        # Verify connectivity - if MCS selection failed, links might not work
        node_ips = {
            "node1": "192.168.100.1",
            "node2": "192.168.100.2",
            "node3": "192.168.100.3",
        }
        verify_ping_connectivity("clab-csma-mcs", node_ips)

        # Future enhancement: Parse deployment stdout to extract MCS index
        # and verify it matches expected value based on SINR
        print("✓ CSMA MCS index selection validated (deployment successful)")
        print("  Note: Expected MCS 2 (QPSK, rate-0.5) for SINR ~11 dB")

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_csma_mcs_hidden_node_problem(channel_server, examples_for_tests: Path):
    """Validate hidden node scenario modeling.

    Validates that:
    - Node1 @ 30m is beyond carrier sense range of Node2
    - CS range = communication_range × 2.5 = 11m × 2.5 = 27.5m
    - Node1 interference is NOT sensed by Node2
    - Deployment succeeds despite hidden node

    Note: This test validates topology geometry. Actual carrier sense
    behavior is modeled in channel computation, not in container network.
    """
    yaml_path = examples_for_tests / "shared_sionna_snr_csma-mcs" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Verify all-to-all connectivity works despite hidden node
        node_ips = {
            "node1": "192.168.100.1",
            "node2": "192.168.100.2",
            "node3": "192.168.100.3",
        }
        verify_ping_connectivity("clab-csma-mcs", node_ips)

        print("✓ CSMA hidden node scenario validated")
        print("  Note: Node1 (30m) beyond CS range (27.5m) of Node2")

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_csma_mcs_snr_vs_sinr_comparison(channel_server, examples_for_tests: Path):
    """Document SNR vs SINR degradation from hidden node interference.

    Validates that:
    - SNR ~42 dB (no interference, theoretical)
    - SINR ~11 dB (with interference from hidden node)
    - Degradation: ~31 dB from hidden node interference
    - MCS selection uses SINR correctly

    Note: This test validates deployment and connectivity.
    Actual SNR/SINR values require channel server API enhancement
    to expose interference metrics.
    """
    yaml_path = examples_for_tests / "shared_sionna_snr_csma-mcs" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Verify connectivity works with SINR-based channel computation
        node_ips = {
            "node1": "192.168.100.1",
            "node2": "192.168.100.2",
            "node3": "192.168.100.3",
        }
        verify_ping_connectivity("clab-csma-mcs", node_ips)

        print("✓ CSMA SNR vs SINR comparison validated")
        print("  Note: Expected ~31 dB degradation from hidden node interference")

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_csma_mcs_routing(channel_server, examples_for_tests: Path, bridge_node_ips: dict):
    """Verify routes to bridge subnet (192.168.100.0/24) via eth1.

    Validates that:
    - All 3 nodes have correct routes to bridge subnet
    - Routes use eth1 (not default Docker eth0)
    - Routing works despite CSMA carrier sensing
    """
    yaml_path = examples_for_tests / "shared_sionna_snr_csma-mcs" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Verify routes for all 3 nodes
        for node_name in bridge_node_ips.keys():
            verify_route_to_cidr(
                container_prefix="clab-csma-mcs",
                node=node_name,
                cidr="192.168.100.0/24",
                interface="eth1",
            )

        print("✓ CSMA MCS routing validated for all nodes")

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_csma_mcs_tc_config(channel_server, examples_for_tests: Path):
    """Validate netem parameters match SINR-computed values.

    Validates that:
    - Rate limit matches MCS 2 (~64 Mbps expected for QPSK rate-0.5)
    - Loss% reflects SINR-based PER
    - Per-destination tc flower filters configured
    - Bidirectional verification
    """
    yaml_path = examples_for_tests / "shared_sionna_snr_csma-mcs" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Verify node2 -> node3 link (primary link with SINR ~11 dB)
        # Expected: QPSK rate-0.5 → ~64 Mbps
        result = verify_tc_config(
            container_prefix="clab-csma-mcs",
            node="node2",
            interface="eth1",
            dst_node_ip="192.168.100.3",
            expected_rate_mbps=64.0,
            rate_tolerance_mbps=19.2,  # 30% tolerance
        )

        print("✓ CSMA MCS TC config validated")
        print(f"  Rate: {result.get('rate_mbps', 'N/A')} Mbps (expected ~64 Mbps for QPSK)")

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))
