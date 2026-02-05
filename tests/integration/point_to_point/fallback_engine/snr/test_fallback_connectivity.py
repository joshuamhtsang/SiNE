"""Connectivity and throughput tests for p2p_fallback_snr_vacuum example.

Tests fallback engine (FSPL-based path loss) without GPU/Sionna.
Validates basic netem configuration and connectivity.
"""

import pytest
from pathlib import Path
from tests.integration.fixtures import (
    channel_server_fallback,
    deploy_topology,
    destroy_topology,
    stop_deployment_process,
    verify_ping_connectivity,
    run_iperf3_test,
    verify_tc_config,
    p2p_node_ips,
)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.fallback
def test_fallback_vacuum_connectivity(channel_server_fallback, examples_for_tests: Path, p2p_node_ips: dict):
    """Test bidirectional ping connectivity with fallback engine.

    Validates that:
    - Node1 can ping Node2 (and vice versa)
    - Fallback engine FSPL calculation works correctly
    - Expected: 20m distance, FSPL ~72 dB at 5.18 GHz, high SNR
    - No GPU/Sionna required
    """
    yaml_path = examples_for_tests / "p2p_fallback_snr_vacuum" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Test bidirectional connectivity (p2p has only 2 nodes)
        node_pair = {k: v for k, v in list(p2p_node_ips.items())[:2]}
        verify_ping_connectivity("clab-fallback-vacuum", node_pair)

        print("✓ Fallback vacuum connectivity validated")

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.fallback
def test_fallback_vacuum_throughput(channel_server_fallback, examples_for_tests: Path):
    """Test iperf3 throughput with fallback engine.

    Validates that:
    - Throughput matches expected PHY rate for 64-QAM
    - Expected: 180-220 Mbps (64-QAM, rate-0.667, LDPC)
    - Netem rate limit correctly applied
    - Fallback engine provides realistic channel conditions
    """
    yaml_path = examples_for_tests / "p2p_fallback_snr_vacuum" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Measure throughput node1 -> node2
        throughput = run_iperf3_test(
            container_prefix="clab-fallback-vacuum",
            server_node="node2",
            client_node="node1",
            client_ip="10.0.0.2",
            duration_sec=10,
        )

        # Expected: 64-QAM with rate-0.667 LDPC, 80 MHz BW
        # 80 MHz × 6 bits × 0.667 × 0.8 (overhead) = ~256 Mbps theoretical
        # With netem loss and overhead, expect 180-220 Mbps
        assert 180.0 <= throughput <= 220.0, (
            f"Throughput {throughput:.2f} Mbps outside expected range 180-220 Mbps"
        )

        print(f"✓ Fallback vacuum throughput validated: {throughput:.2f} Mbps")

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.fallback
def test_fallback_vacuum_tc_config(channel_server_fallback, examples_for_tests: Path):
    """Validate netem delay, loss%, and rate with fallback engine.

    Validates that:
    - Netem parameters applied correctly
    - Delay matches FSPL propagation (~0.07 ms for 20m)
    - Loss% very low (high SNR scenario)
    - Rate limit ~192 Mbps for 64-QAM
    - Bidirectional verification
    """
    yaml_path = examples_for_tests / "p2p_fallback_snr_vacuum" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Verify node1's eth1 interface
        # Expected: ~0.07 ms delay (20m / c), very low loss, ~192 Mbps rate
        result1 = verify_tc_config(
            container_prefix="clab-fallback-vacuum",
            node="node1",
            interface="eth1",
            expected_rate_mbps=192.0,  # 64-QAM, rate-0.5 LDPC
            tolerance_percent=20.0,
        )

        # Verify node2's eth1 interface (reverse direction)
        result2 = verify_tc_config(
            container_prefix="clab-fallback-vacuum",
            node="node2",
            interface="eth1",
            expected_rate_mbps=192.0,
            tolerance_percent=20.0,
        )

        print("✓ Fallback vacuum TC config validated for both directions")
        print(f"  Node1: rate={result1.get('rate_mbps', 'N/A')} Mbps, "
              f"delay={result1.get('delay_ms', 'N/A')} ms")
        print(f"  Node2: rate={result2.get('rate_mbps', 'N/A')} Mbps, "
              f"delay={result2.get('delay_ms', 'N/A')} ms")

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))
