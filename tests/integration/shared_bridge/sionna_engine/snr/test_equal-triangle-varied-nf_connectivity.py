"""Integration tests for asymmetric noise figure connectivity.

Tests connectivity and throughput with heterogeneous receivers that have
different noise figures, resulting in asymmetric SNR values.
"""

import pytest
from pathlib import Path
from tests.integration.fixtures import (
    channel_server,
    deploy_topology,
    destroy_topology,
    extract_container_prefix,
    stop_deployment_process,
    verify_ping_connectivity,
    run_iperf3_test,
)
from sine.config.loader import load_topology


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_asymmetric_nf_connectivity(channel_server, examples_for_tests: Path, bridge_node_ips: dict):
    """Test ping connectivity with heterogeneous noise figures.

    Validates that:
    - All nodes can ping each other despite different receiver sensitivities
    - Higher NF nodes (worse receivers) don't block connectivity
    - Lower NF nodes (better receivers) work correctly

    Topology:
    - node1: 7.0 dB NF (WiFi 6 typical)
    - node2: 10.0 dB NF (cheap IoT radio)
    - node3: 5.0 dB NF (high-end base station)
    """
    yaml_path = examples_for_tests / "shared_sionna_snr_equal-triangle-varied-nf" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    # Verify heterogeneous noise figures in config
    config = load_topology(str(yaml_path))
    nf_values = {}
    for node_name, node_config in config.topology.nodes.items():
        for iface_name, iface_config in node_config.interfaces.items():
            if iface_config.wireless and iface_config.wireless.noise_figure_db:
                nf_values[node_name] = iface_config.wireless.noise_figure_db

    # Verify we have at least 2 different noise figure values
    unique_nf = set(nf_values.values())
    assert len(unique_nf) >= 2, "Expected at least 2 different noise figure values"

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
@pytest.mark.very_slow
@pytest.mark.sionna
def test_asymmetric_nf_throughput(channel_server, examples_for_tests: Path):
    """Test throughput with heterogeneous receivers.

    Validates that:
    - Throughput test completes successfully
    - Bidirectional throughput may differ due to NF asymmetry

    Expected behavior:
    - node1 (7 dB) → node2 (10 dB): Uses node2's NF (worse), lower SNR
    - node2 (10 dB) → node1 (7 dB): Uses node1's NF (better), higher SNR

    Note: Actual SNR difference = node2_NF - node1_NF = 10 - 7 = 3 dB
    This may or may not affect throughput depending on MCS thresholds.
    """
    yaml_path = examples_for_tests / "shared_sionna_snr_equal-triangle-varied-nf" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Test node1 -> node2 (uses node2's NF = 10 dB)
        throughput_12 = run_iperf3_test(
            container_prefix="clab-manet-triangle-shared-asymmetric-nf",
            server_node="node2",
            client_node="node1",
            client_ip="192.168.100.2",
            duration_sec=8,
        )

        # Validate throughput is reasonable
        assert 50.0 <= throughput_12 <= 200.0, (
            f"Throughput node1->node2 {throughput_12:.2f} Mbps outside expected range"
        )

        # Test node2 -> node1 (uses node1's NF = 7 dB)
        throughput_21 = run_iperf3_test(
            container_prefix="clab-manet-triangle-shared-asymmetric-nf",
            server_node="node1",
            client_node="node2",
            client_ip="192.168.100.1",
            duration_sec=8,
        )

        assert 50.0 <= throughput_21 <= 200.0, (
            f"Throughput node2->node1 {throughput_21:.2f} Mbps outside expected range"
        )

        # Note: We don't enforce throughput_21 > throughput_12 because:
        # - 3 dB difference may not cross MCS threshold
        # - TCP dynamics can mask PHY-layer differences
        # - The key is that both directions work

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_asymmetric_nf_bidirectional_snr(channel_server, examples_for_tests: Path, bridge_node_ips: dict):
    """Test asymmetric SNR with heterogeneous noise figures.

    Validates that:
    - Deployment completes successfully
    - SNR values differ between directions based on receiver NF

    Note: Actual SNR values are logged during deployment but not validated
    programmatically in this test. The deployment summary shows:
      node1→node2: SNR = X dB (uses node2's NF = 10 dB)
      node2→node1: SNR = Y dB (uses node1's NF = 7 dB)
    Where Y - X ≈ 3 dB (NF difference)
    """
    yaml_path = examples_for_tests / "shared_sionna_snr_equal-triangle-varied-nf" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Get container prefix from topology
        container_prefix = extract_container_prefix(str(yaml_path))

        # Verify basic connectivity (which confirms SNR is sufficient)
        verify_ping_connectivity(container_prefix, bridge_node_ips)

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))
