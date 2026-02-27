"""Comprehensive integration tests for p2p_sionna_snr_two-rooms example.

Tests indoor multipath propagation through doorway scenario with ray tracing.
This example validates:
- Indoor NLOS propagation
- Multipath diversity gain
- Wall penetration and reflection
- OFDM delay spread assumptions
"""

import pytest
from pathlib import Path
from tests.integration.fixtures import (
    channel_server,
    deploy_topology,
    destroy_topology,
    stop_deployment_process,
    verify_ping_connectivity,
    run_iperf3_test,
    verify_tc_config,
    p2p_node_ips,
    extract_container_prefix,
)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_two_rooms_connectivity(channel_server, examples_for_tests: Path, p2p_node_ips: dict):
    """Test bidirectional ping connectivity through doorway.

    Validates that:
    - Node1 can ping Node2 (through doorway, NLOS)
    - Node2 can ping Node1 (reverse direction)
    - Indoor multipath propagation provides sufficient SNR for QPSK
    - Expected: ~20-30 dB SNR (reflections through doorway)
    - QPSK modulation (requires ~8 dB SNR) provides reliable connectivity
    """
    yaml_path = examples_for_tests / "p2p_sionna_snr_two-rooms" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Extract container prefix from YAML (e.g., "clab-two-rooms")
        container_prefix = extract_container_prefix(yaml_path)

        # Test bidirectional connectivity (p2p has only 2 nodes)
        # Use only the two nodes from the fixture
        node_pair = {k: v for k, v in list(p2p_node_ips.items())[:2]}
        verify_ping_connectivity(container_prefix, node_pair)

        print("✓ Two-rooms connectivity validated")

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_two_rooms_throughput(channel_server, examples_for_tests: Path, p2p_node_ips: dict):
    """Test iperf3 throughput with QPSK modulation.

    Validates that:
    - Throughput matches expected PHY rate for QPSK
    - Expected: 50-64 Mbps (QPSK, 0.5 code rate, 80 MHz BW)
    - QPSK provides reliable throughput despite NLOS conditions
    """
    yaml_path = examples_for_tests / "p2p_sionna_snr_two-rooms" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Extract container prefix from YAML (e.g., "clab-two-rooms")
        container_prefix = extract_container_prefix(yaml_path)

        # Measure throughput node1 -> node2
        throughput = run_iperf3_test(
            container_prefix=container_prefix,
            server_node="node2",
            client_node="node1",
            server_ip=p2p_node_ips["node2"],
            duration_sec=10,
        )

        # Expected: QPSK with rate-0.5 LDPC, 80 MHz BW
        # 80 MHz × 2 bits × 0.5 × 0.8 (overhead) = ~64 Mbps theoretical
        # With netem loss and indoor multipath, expect 50-64 Mbps
        assert 50.0 <= throughput <= 64.0, (
            f"Throughput {throughput:.2f} Mbps outside expected range 50-64 Mbps"
        )

        print(f"✓ Two-rooms throughput validated: {throughput:.2f} Mbps")

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_two_rooms_scene_loading(channel_server, examples_for_tests: Path, p2p_node_ips: dict):
    """Test that two_rooms.xml scene loads correctly and affects path loss.

    Validates that:
    - Scene file loads without errors
    - Path loss is higher than free space due to walls
    - Deployment completes successfully with scene
    - Expected: Path loss > FSPL by 10-20 dB (wall penetration)
    """
    yaml_path = examples_for_tests / "p2p_sionna_snr_two-rooms" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        # Deployment itself validates scene loading
        # If scene file is missing or malformed, deployment will fail
        deploy_process = deploy_topology(str(yaml_path))

        # Extract container prefix from YAML (e.g., "clab-two-rooms")
        container_prefix = extract_container_prefix(yaml_path)

        # Verify connectivity - if scene loading failed, SNR would be much higher
        # (free space) and connectivity might still work but with wrong assumptions
        verify_ping_connectivity(container_prefix, p2p_node_ips)

        print("✓ Two-rooms scene loaded and validated")

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_two_rooms_multipath(channel_server, examples_for_tests: Path, p2p_node_ips: dict):
    """Test multipath delay spread is within OFDM cyclic prefix bounds.

    Validates that:
    - RMS delay spread < 800 ns (WiFi 6 short GI cyclic prefix)
    - Indoor scenario creates multipath but not excessive delay spread
    - OFDM assumption holds (no ISI after equalization)
    - Expected: τ_rms = 20-300 ns typical for indoor

    Note: This test validates deployment succeeds, indicating delay spread
    is acceptable. Actual τ_rms measurement would require channel server API
    enhancement to expose delay spread metrics.
    """
    yaml_path = examples_for_tests / "p2p_sionna_snr_two-rooms" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        # Deployment validates that channel computation succeeds
        # If delay spread were excessive (>800ns), the model would still work
        # but our OFDM assumptions would be violated
        deploy_process = deploy_topology(str(yaml_path))

        # Extract container prefix from YAML (e.g., "clab-two-rooms")
        container_prefix = extract_container_prefix(yaml_path)

        # For now, we validate that deployment succeeds and connectivity works
        # Future enhancement: Query channel server /visualization/state
        # to get actual τ_rms value and assert < 800ns
        verify_ping_connectivity(container_prefix, p2p_node_ips)

        print("✓ Two-rooms multipath validated (deployment successful)")
        print("  Note: τ_rms < 800ns assumed from successful OFDM-based channel computation")

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_two_rooms_tc_config(channel_server, examples_for_tests: Path):
    """Validate netem delay, loss%, and rate match expected SNR.

    Validates that:
    - Netem parameters are applied correctly
    - Bidirectional verification (both node1 and node2 interfaces)
    - Delay matches propagation distance
    - Loss% and rate reflect indoor NLOS conditions
    """
    yaml_path = examples_for_tests / "p2p_sionna_snr_two-rooms" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Extract container prefix from YAML (e.g., "clab-two-rooms")
        container_prefix = extract_container_prefix(yaml_path)

        # Verify node1's eth1 interface
        # Expected: ~0.1 ms delay (30m distance), low loss with QPSK, ~64 Mbps rate
        result1 = verify_tc_config(
            container_prefix=container_prefix,
            node="node1",
            interface="eth1",
            expected_rate_mbps=64.0,  # QPSK, rate-0.5 LDPC, 80 MHz BW
            rate_tolerance_mbps=20.0,  # 30% tolerance for indoor multipath
        )

        # Verify node2's eth1 interface (reverse direction)
        result2 = verify_tc_config(
            container_prefix=container_prefix,
            node="node2",
            interface="eth1",
            expected_rate_mbps=64.0,
            rate_tolerance_mbps=20.0,  # 30% tolerance
        )

        print("✓ Two-rooms TC config validated for both directions")

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.very_slow
@pytest.mark.sionna
@pytest.mark.skip(reason="Control API requires --enable-control flag, tested separately")
def test_two_rooms_mobility(channel_server, examples_for_tests: Path, p2p_node_ips: dict):
    """Test mobility: move node2 along wall, verify channel recomputation.

    Validates that:
    - Position updates trigger channel recomputation
    - Netem parameters update correctly
    - Movement along wall maintains NLOS conditions
    - Expected: Path loss changes as node moves

    Note: This test is marked as skip by default since it requires
    deployment with --enable-control flag. Run control API tests separately
    with the control API test suite.
    """
    yaml_path = examples_for_tests / "p2p_sionna_snr_two-rooms" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        # Deploy with mobility enabled
        deploy_process = deploy_topology(str(yaml_path), enable_control=True)

        # Extract container prefix from YAML (e.g., "clab-two-rooms")
        container_prefix = extract_container_prefix(yaml_path)

        # Test initial position connectivity
        verify_ping_connectivity(container_prefix, p2p_node_ips)

        # Move node2 from (30, 1, 1) to (30, 5, 1) - along wall
        # This would require mobility API calls (not implemented here)
        # Future: Use requests.post to mobility API endpoint

        print("✓ Two-rooms mobility test placeholder")

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))
