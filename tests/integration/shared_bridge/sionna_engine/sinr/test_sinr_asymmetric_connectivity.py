"""Integration tests for SINR with asymmetric geometry (connectivity test).

Tests connectivity with non-equilateral triangle topology that produces positive
SINR values suitable for reliable packet delivery.
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
)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_sinr_asymmetric_connectivity(channel_server, examples_for_tests: Path):
    """Test connectivity with asymmetric triangle geometry.

    This topology uses a non-equilateral triangle where node3 is moved further
    away (y=50 instead of y=25.98). This creates asymmetric interference paths
    that produce positive SINR values suitable for reliable connectivity.

    Topology:
    - node1: (0, 0, 1)
    - node2: (30, 0, 1)
    - node3: (15, 50, 1)

    Expected SINR:
    - node1↔node2: ~9-10 dB (30m signal, 91.2m interference)
    - node1↔node3: ~-3 to -4 dB (91.2m signal, 30m interference - NEGATIVE SINR)
    - node2↔node3: ~-3 to -4 dB (91.2m signal, 30m interference - NEGATIVE SINR)

    With QPSK modulation:
    - SINR ~9-10 dB: Good connectivity (above 8 dB threshold)
    - SINR < 0 dB: No connectivity (100% packet loss)

    Expected results:
    - node1↔node2: Good connectivity (positive SINR)
    - node3 links: NO CONNECTIVITY (negative SINR, interference >> signal)
    """
    yaml_path = examples_for_tests / "shared_sionna_sinr_asymmetric" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Only test node1↔node2 connectivity (positive SINR ~9-10 dB)
        # node3 links have negative SINR and will NOT work
        import subprocess

        print("\n" + "="*70)
        print("Testing node1↔node2 connectivity (SINR ~9-10 dB)")
        print("="*70 + "\n")

        # Test node1 -> node2
        print("Ping node1 -> node2 (192.168.100.2)...", end=" ")
        cmd = "docker exec clab-manet-asymmetric-sinr-node1 ping -c 5 -W 2 192.168.100.2"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print("✓ SUCCESS")
        else:
            print("✗ FAILED")
            raise AssertionError(
                f"Ping failed: node1 -> node2 (192.168.100.2)\n"
                f"Output: {result.stdout}\n{result.stderr}"
            )

        # Test node2 -> node1
        print("Ping node2 -> node1 (192.168.100.1)...", end=" ")
        cmd = "docker exec clab-manet-asymmetric-sinr-node2 ping -c 5 -W 2 192.168.100.1"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print("✓ SUCCESS")
        else:
            print("✗ FAILED")
            raise AssertionError(
                f"Ping failed: node2 -> node1 (192.168.100.1)\n"
                f"Output: {result.stdout}\n{result.stderr}"
            )

        print("\n" + "="*70)
        print("Connectivity test passed! (node1↔node2 only)")
        print("Note: node3 links have negative SINR and are expected to fail")
        print("="*70 + "\n")

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.very_slow
@pytest.mark.sionna
def test_sinr_asymmetric_throughput(channel_server, examples_for_tests: Path):
    """Test throughput with asymmetric geometry (high-SINR link).

    Tests the node1→node2 link which has good SINR (~8-9 dB) due to
    asymmetric geometry. Interference from node3 is weaker since it's
    further away (52.2m vs 30m signal path).

    Expected throughput:
    - QPSK, rate-0.5 LDPC, 80 MHz BW: ~64 Mbps theoretical
    - With protocol overhead: ~50-64 Mbps
    - With SINR ~8-9 dB: Good packet delivery, minimal loss
    """
    yaml_path = examples_for_tests / "shared_sionna_sinr_asymmetric" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Run throughput test: node1 -> node2 (high-SINR link)
        # Expected: ~50-64 Mbps (QPSK, rate-0.5 LDPC, 80 MHz BW)
        throughput_mbps = run_iperf3_test(
            container_prefix="clab-manet-asymmetric-sinr",
            server_node="node2",
            client_node="node1",
            client_ip="192.168.100.2",
            duration_sec=10,
        )

        # Validate throughput is in reasonable range for QPSK
        # Lower bound: 40 Mbps (allows for some interference/overhead)
        # Upper bound: 80 Mbps (slightly above theoretical max)
        assert 40.0 <= throughput_mbps <= 80.0, (
            f"Throughput {throughput_mbps:.2f} Mbps outside expected range [40, 80] Mbps. "
            f"Expected ~50-64 Mbps for QPSK with SINR ~8-9 dB."
        )

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_sinr_asymmetric_negative_sinr_no_connectivity(channel_server, examples_for_tests: Path):
    """Test that negative-SINR links have NO connectivity (node1↔node3).

    Tests the node1→node3 link which has NEGATIVE SINR (~-3 to -4 dB) because:
    - Signal path: 91.2m (weak signal, path loss ~81.7 dB)
    - Interference path: 30m (strong interference, path loss ~72 dB)

    Expected behavior:
    - SINR < 0 dB: No connectivity (interference stronger than signal)
    - Ping should fail with 100% packet loss
    - This explicitly validates that negative SINR prevents connectivity
    """
    yaml_path = examples_for_tests / "shared_sionna_sinr_asymmetric" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        import subprocess

        print("\n" + "="*70)
        print("Testing node1→node3 connectivity (SINR ~-3 to -4 dB)")
        print("Expected: 100% packet loss (negative SINR)")
        print("="*70 + "\n")

        # Test that ping FAILS from node1 to node3
        print("Ping node1 -> node3 (192.168.100.3)...", end=" ")
        cmd = "docker exec clab-manet-asymmetric-sinr-node1 ping -c 5 -W 2 192.168.100.3"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        if result.returncode != 0:
            print("✓ FAILED AS EXPECTED (negative SINR)")
            print("   100% packet loss confirmed")
        else:
            print("✗ UNEXPECTED SUCCESS")
            raise AssertionError(
                f"Ping unexpectedly succeeded: node1 -> node3 (192.168.100.3)\n"
                f"Expected 100% packet loss due to negative SINR (~-3 to -4 dB)\n"
                f"Output: {result.stdout}\n{result.stderr}"
            )

        # Test that ping FAILS from node3 to node1
        print("Ping node3 -> node1 (192.168.100.1)...", end=" ")
        cmd = "docker exec clab-manet-asymmetric-sinr-node3 ping -c 5 -W 2 192.168.100.1"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        if result.returncode != 0:
            print("✓ FAILED AS EXPECTED (negative SINR)")
            print("   100% packet loss confirmed")
        else:
            print("✗ UNEXPECTED SUCCESS")
            raise AssertionError(
                f"Ping unexpectedly succeeded: node3 -> node1 (192.168.100.1)\n"
                f"Expected 100% packet loss due to negative SINR (~-3 to -4 dB)\n"
                f"Output: {result.stdout}\n{result.stderr}"
            )

        print("\n" + "="*70)
        print("Negative SINR test passed! No connectivity as expected.")
        print("="*70 + "\n")

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))
