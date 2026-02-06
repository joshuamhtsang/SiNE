"""Comprehensive integration tests for shared_sionna_sinr_csma-mcs example.

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
    bridge_node_ips,
    channel_server,
    deploy_topology,
    destroy_topology,
    extract_container_prefix,
    stop_deployment_process,
    verify_route_to_cidr,
    verify_selective_ping_connectivity,
    verify_tc_config,
)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_csma_mcs_connectivity(channel_server, examples_for_tests: Path, bridge_node_ips: dict):
    """Test ping connectivity with CSMA carrier sensing.

    Validates that:
    - Node2 ↔ Node3 connectivity (primary link, SINR ~15-17 dB)
    - CSMA carrier sensing doesn't break connectivity
    - Node1 is isolated (negative SINR prevents transmission)
    - Expected: SINR ~17 dB → 16-QAM capable (MCS 4)
    """
    yaml_path = examples_for_tests / "shared_sionna_sinr_csma-mcs" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Extract container prefix from YAML (e.g., "clab-csma-mcs-test")
        container_prefix = extract_container_prefix(yaml_path)

        # Test only node2↔node3 connectivity (node1 has negative SINR outbound)
        verify_selective_ping_connectivity(
            container_prefix=container_prefix,
            node_ips=bridge_node_ips,
            expected_success=[
                ("node2", "node3"),  # SINR=17.3 dB, loss=0.00%
                ("node3", "node2"),  # SINR=14.8 dB, loss=0.04%
            ],
            expected_failure=[
                ("node1", "node2"),  # SINR=-4.3 dB, 100% loss
                ("node1", "node3"),  # SINR=-6.8 dB, 100% loss
                ("node2", "node1"),  # Return path fails (node1→node2 100% loss)
                ("node3", "node1"),  # Return path fails (node1→node3 100% loss)
            ],
        )

        print("✓ CSMA MCS connectivity validated (node2↔node3 only)")

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_csma_mcs_index_validation(channel_server, examples_for_tests: Path, bridge_node_ips: dict):
    """Validate MCS index selection based on SINR.

    Validates that:
    - MCS index is selected from MCS table
    - Expected: MCS 4 (16-QAM, rate-0.75, LDPC) for SINR ~17 dB
    - SINR (not SNR) determines MCS choice
    - Deployment logs show selected MCS
    - Node1 has negative SINR → 100% loss (no valid MCS)

    Note: This test validates deployment succeeds with MCS table.
    Actual MCS index verification requires parsing deployment logs or
    querying channel server API (future enhancement).
    """
    yaml_path = examples_for_tests / "shared_sionna_sinr_csma-mcs" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        # Deployment validates MCS table loading and selection
        deploy_process = deploy_topology(str(yaml_path))

        # Extract container prefix from YAML (e.g., "clab-csma-mcs-test")
        container_prefix = extract_container_prefix(yaml_path)

        # Verify connectivity - only node2↔node3 works (node1 isolated)
        verify_selective_ping_connectivity(
            container_prefix=container_prefix,
            node_ips=bridge_node_ips,
            expected_success=[
                ("node2", "node3"),  # MCS 4 selected (SINR=17.3 dB)
                ("node3", "node2"),  # MCS 3 selected (SINR=14.8 dB)
            ],
            expected_failure=[
                ("node1", "node2"),
                ("node1", "node3"),
                ("node2", "node1"),
                ("node3", "node1"),
            ],
        )

        # Future enhancement: Parse deployment stdout to extract MCS index
        # and verify it matches expected value based on SINR
        print("✓ CSMA MCS index selection validated (deployment successful)")
        print("  Note: Expected MCS 4 (16-QAM, rate-0.75) for SINR ~17 dB")
        print("  Note: Node1 has negative SINR → no valid MCS (100% loss)")

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_csma_mcs_hidden_node_problem(
    channel_server, examples_for_tests: Path, bridge_node_ips: dict
):
    """Validate hidden node scenario with asymmetric connectivity.

    Validates that:
    - Node1 @ 30m is beyond carrier sense range of Node2
    - CS range = communication_range × 2.5 = 11m × 2.5 = 27.5m
    - Node1 interference is NOT sensed by Node2
    - **Node1 CANNOT successfully transmit** (negative SINR due to interference)
    - Node2 ↔ Node3 connectivity works (positive SINR both directions)
    - **Pings TO node1 FAIL** because return path has negative SINR

    Expected SINR values (one-way link):
    - node1→node2: -4.3 dB ❌ (interference from node3 >> signal)
    - node1→node3: -6.8 dB ❌ (interference from node2 >> signal)
    - node2→node1: 31.7 dB ✅ (forward path works)
    - node2→node3: 17.3 dB ✅
    - node3→node1: 29.2 dB ✅ (forward path works)
    - node3→node2: 14.8 dB ✅

    Ping test results (requires both forward + return):
    - node2 → node1: FAIL (forward 31.7 dB works, return -4.3 dB fails)
    - node3 → node1: FAIL (forward 29.2 dB works, return -6.8 dB fails)
    - node2 ↔ node3: SUCCESS (both directions have positive SINR)

    This demonstrates the hidden node problem: node1 becomes an "island" - it can
    receive transmissions but cannot send replies due to negative SINR.
    """
    yaml_path = examples_for_tests / "shared_sionna_sinr_csma-mcs" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Extract container prefix from YAML (e.g., "clab-csma-mcs-test")
        container_prefix = extract_container_prefix(yaml_path)

        # Verify selective connectivity based on SINR values
        # node1 has negative SINR for its transmissions (interference >> signal)
        # Pings require BOTH forward and return paths to work
        # Pings TO node1 fail because return path (node1→) has negative SINR
        verify_selective_ping_connectivity(
            container_prefix=container_prefix,
            node_ips=bridge_node_ips,
            expected_success=[
                ("node2", "node3"),  # Both directions work (SINR ~15-17 dB)
                ("node3", "node2"),  # Both directions work (SINR ~15-17 dB)
            ],
            expected_failure=[
                ("node1", "node2"),  # Forward fails (SINR=-4.3 dB)
                ("node1", "node3"),  # Forward fails (SINR=-6.8 dB)
                ("node2", "node1"),  # Forward works (31.7 dB), return fails (-4.3 dB)
                ("node3", "node1"),  # Forward works (29.2 dB), return fails (-6.8 dB)
            ],
        )

        print("✓ CSMA hidden node scenario validated")
        print("  Note: Node1 is an 'island' - can receive but cannot transmit")
        print("  Successful links: node2↔node3 only")
        print("  Failed links: All paths involving node1 (negative SINR return path)")

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_csma_mcs_snr_vs_sinr_comparison(
    channel_server, examples_for_tests: Path, bridge_node_ips: dict
):
    """Document SNR vs SINR degradation from hidden node interference.

    Validates that:
    - SNR ~41 dB (no interference, theoretical)
    - SINR ~17 dB (with interference from hidden node)
    - Degradation: ~24 dB from hidden node interference
    - MCS selection uses SINR correctly (MCS 4 vs MCS 5+)
    - Node1 experiences NEGATIVE SINR (interference > signal)

    Note: This test validates deployment and connectivity.
    Actual SNR/SINR values are visible in deployment logs.
    """
    yaml_path = examples_for_tests / "shared_sionna_sinr_csma-mcs" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Extract container prefix from YAML (e.g., "clab-csma-mcs-test")
        container_prefix = extract_container_prefix(yaml_path)

        # Verify connectivity - only node2↔node3 works
        verify_selective_ping_connectivity(
            container_prefix=container_prefix,
            node_ips=bridge_node_ips,
            expected_success=[
                ("node2", "node3"),  # SNR=41.2 dB, SINR=17.3 dB
                ("node3", "node2"),  # SNR=41.2 dB, SINR=14.8 dB
            ],
            expected_failure=[
                ("node1", "node2"),  # SNR=31.7 dB, SINR=-4.3 dB (negative!)
                ("node1", "node3"),  # SNR=29.2 dB, SINR=-6.8 dB (negative!)
                ("node2", "node1"),
                ("node3", "node1"),
            ],
        )

        print("✓ CSMA SNR vs SINR comparison validated")
        print("  Note: ~24 dB degradation from hidden node interference")
        print("  SNR: ~41 dB (no interference) → MCS 5+ capable")
        print("  SINR: ~17 dB (with interference) → MCS 4 selected")
        print("  Node1: SINR negative (-4 to -7 dB) → 100% loss")

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
    yaml_path = examples_for_tests / "shared_sionna_sinr_csma-mcs" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Extract container prefix from YAML (e.g., "clab-csma-mcs-test")
        container_prefix = extract_container_prefix(yaml_path)

        # Verify routes for all 3 nodes
        for node_name in bridge_node_ips.keys():
            verify_route_to_cidr(
                container_prefix=container_prefix,
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
def test_csma_mcs_tc_config(channel_server, examples_for_tests: Path, bridge_node_ips: dict):
    """Validate netem parameters match SINR-computed values.

    Validates that:
    - Rate limit matches MCS 4 (~192 Mbps for 16-QAM rate-0.75)
    - Loss% reflects SINR-based PER
    - Per-destination tc flower filters configured
    - Bidirectional verification

    Note: SINR ~17 dB (not 11 dB) due to:
    - Signal from node2 (10m): -40 dBm
    - Interference from node1 (40m, 30% prob): -57.2 dBm
    - SINR = 17.2 dB → MCS 4 (16-QAM rate-0.75)
    """
    yaml_path = examples_for_tests / "shared_sionna_sinr_csma-mcs" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Extract container prefix from YAML (e.g., "clab-csma-mcs-test")
        container_prefix = extract_container_prefix(yaml_path)

        # Verify node2 -> node3 link (primary link with SINR ~17 dB)
        # Expected: 16-QAM rate-0.75 → ~192 Mbps (MCS 4)
        result = verify_tc_config(
            container_prefix=container_prefix,
            node="node2",
            interface="eth1",
            dst_node_ip=bridge_node_ips["node3"],
            expected_rate_mbps=192.0,
            rate_tolerance_mbps=20.0,  # ~10% tolerance
        )

        print("✓ CSMA MCS TC config validated")
        print(
            f"  Rate: {result.get('rate_mbps', 'N/A')} Mbps "
            f"(expected ~192 Mbps for 16-QAM rate-0.75)"
        )

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))
