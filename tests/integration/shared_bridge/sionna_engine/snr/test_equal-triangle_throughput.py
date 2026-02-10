"""Throughput tests for shared_sionna_snr_equal-triangle example.

Tests iperf3 throughput measurements for 3-node equilateral triangle topology.
Validates that PHY rates match SNR-computed modulation schemes.
"""

import pytest
from pathlib import Path
from tests.integration.fixtures import (
    channel_server,
    deploy_topology,
    destroy_topology,
    stop_deployment_process,
    run_iperf3_test,
    extract_container_prefix,
)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_equal_triangle_throughput_node1_to_node2(channel_server, examples_for_tests: Path):
    """Test iperf3 throughput from node1 to node2.

    Validates that:
    - Throughput matches SNR-computed PHY rate
    - Expected: 170-220 Mbps (64-QAM, rate-0.667, LDPC)
    - Equilateral triangle geometry provides good SNR
    - PHY rate: 80 MHz × 6 bits × 0.667 × 0.8 (overhead) = ~256 Mbps theoretical
    """
    yaml_path = examples_for_tests / "shared_sionna_snr_equal-triangle" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Extract container prefix from YAML
        container_prefix = extract_container_prefix(yaml_path)

        # Measure throughput node1 -> node2
        throughput = run_iperf3_test(
            container_prefix=container_prefix,
            server_node="node2",
            client_node="node1",
            server_ip="192.168.100.2",
            duration_sec=10,
        )

        # Expected: 64-QAM with rate-0.667 LDPC, 80 MHz BW
        # With netem loss and packet overhead, expect 170-220 Mbps
        assert 170.0 <= throughput <= 220.0, (
            f"Throughput {throughput:.2f} Mbps outside expected range 170-220 Mbps"
        )

        print(f"✓ Node1→Node2 throughput validated: {throughput:.2f} Mbps")

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.very_slow
@pytest.mark.sionna
def test_equal_triangle_throughput_all_pairs(channel_server, examples_for_tests: Path):
    """Test iperf3 throughput for all 3 bidirectional pairs (6 total tests).

    Validates that:
    - All pairs achieve similar throughput (±10%)
    - Symmetric throughput due to equilateral geometry
    - No preferential links (all sides equal length)
    - Expected: 170-220 Mbps for all pairs

    Note: Marked as very_slow since it runs 6 iperf3 tests (60+ seconds total).
    """
    yaml_path = examples_for_tests / "shared_sionna_snr_equal-triangle" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Extract container prefix from YAML
        container_prefix = extract_container_prefix(yaml_path)

        # Test all 6 directional pairs
        pairs = [
            ("node1", "node2", "192.168.100.2"),
            ("node2", "node1", "192.168.100.1"),
            ("node1", "node3", "192.168.100.3"),
            ("node3", "node1", "192.168.100.1"),
            ("node2", "node3", "192.168.100.3"),
            ("node3", "node2", "192.168.100.2"),
        ]

        throughputs = []
        for client_node, server_node, server_ip in pairs:
            throughput = run_iperf3_test(
                container_prefix=container_prefix,
                server_node=server_node,
                client_node=client_node,
                server_ip=server_ip,
                duration_sec=8,  # Shorter duration for 6 tests
            )
            throughputs.append(throughput)
            print(f"  {client_node}→{server_node}: {throughput:.2f} Mbps")

            # Each individual measurement should be in range
            assert 170.0 <= throughput <= 220.0, (
                f"Throughput {throughput:.2f} Mbps outside expected range 170-220 Mbps"
            )

        # Verify symmetric throughput (all within 10% of mean)
        mean_throughput = sum(throughputs) / len(throughputs)
        for throughput in throughputs:
            deviation_percent = abs(throughput - mean_throughput) / mean_throughput * 100
            assert deviation_percent <= 10.0, (
                f"Throughput {throughput:.2f} Mbps deviates {deviation_percent:.1f}% "
                f"from mean {mean_throughput:.2f} Mbps (expected ≤10%)"
            )

        print(f"✓ All pairs throughput validated: {mean_throughput:.2f} Mbps mean")
        print(f"  Min: {min(throughputs):.2f} Mbps, Max: {max(throughputs):.2f} Mbps")

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))
