"""
Integration tests for MANET shared bridge topology.

These tests deploy the manet_triangle_shared example and validate:
1. All nodes can reach each other (connectivity)
2. iperf3 throughput matches expected rates

Requirements:
- Channel server running (automatically started by test fixture)
- sudo access for netem configuration (passwordless or pre-authenticated)
- containerlab installed
- iperf3 installed in container images

Running these tests:
    # Authenticate sudo before running
    sudo -v && uv run pytest tests/integration/test_manet_shared_bridge.py -v -m integration
"""

import logging
from pathlib import Path

import pytest

# Import shared fixtures and helpers
from .fixtures import (
    channel_server,
    deploy_topology,
    destroy_topology,
    run_iperf3_test,
    stop_deployment_process,
    verify_ping_connectivity,
    verify_route_to_cidr,
    verify_tc_config,
)

logger = logging.getLogger(__name__)


# Prevent "imported but unused" warnings - these are pytest fixtures
__all__ = ["channel_server"]


# =============================================================================
# Test Functions
# =============================================================================


@pytest.mark.integration
@pytest.mark.slow
def test_manet_shared_bridge_connectivity(channel_server, examples_dir: Path):
    """
    Test MANET shared bridge connectivity.

    Expected: All nodes can ping each other (all-to-all connectivity).
    """
    yaml_path = examples_dir / "manet_triangle_shared" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    # Cleanup any existing deployment first
    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        # Deploy (returns background process)
        deploy_process = deploy_topology(str(yaml_path))

        # Test connectivity (IPs already configured by deployment)
        node_ips = {
            "node1": "192.168.100.1",
            "node2": "192.168.100.2",
            "node3": "192.168.100.3",
        }

        verify_ping_connectivity("clab-manet-triangle-shared", node_ips)

    finally:
        # Stop deployment process
        stop_deployment_process(deploy_process)
        # Cleanup containers
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
def test_manet_shared_bridge_throughput(channel_server, examples_dir: Path):
    """
    Test MANET shared bridge throughput.

    Expected: Throughput matches configured rate (~192 Mbps for 64-QAM, 80 MHz, rate-1/2).
    PHY rate = 80 MHz × 6 bits/symbol × 0.5 code_rate × 0.8 efficiency = 192 Mbps
    """
    yaml_path = examples_dir / "manet_triangle_shared" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    # Cleanup any existing deployment first
    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        # Deploy (returns background process)
        deploy_process = deploy_topology(str(yaml_path))

        # Run iperf3 test (using the shared bridge IPs already configured)
        throughput = run_iperf3_test(
            container_prefix="clab-manet-triangle-shared",
            server_node="node1",
            client_node="node2",
            client_ip="192.168.100.1",  # Use existing bridge IP
            duration_sec=15,
        )

        # Validate: 93-100% of ~192 Mbps (64-QAM, 80 MHz, rate-1/2)
        # Allow for protocol overhead and measurement variance
        # Relaxed from 95% to account for TCP overhead and timing variance
        assert 178.5 <= throughput <= 192, (
            f"Throughput {throughput:.1f} Mbps not in expected range "
            f"[178.5-192 Mbps] (93-100% of PHY rate)"
        )

    finally:
        # Stop deployment process
        stop_deployment_process(deploy_process)
        # Cleanup containers
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
def test_manet_shared_bridge_bidirectional_throughput(channel_server, examples_dir: Path):
    """
    Test bidirectional throughput in MANET shared bridge.

    Expected: Both directions achieve similar throughput (symmetric links).
    """
    yaml_path = examples_dir / "manet_triangle_shared" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    # Cleanup any existing deployment first
    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        # Deploy (returns background process)
        deploy_process = deploy_topology(str(yaml_path))

        # Test node1 → node2
        throughput_1_to_2 = run_iperf3_test(
            container_prefix="clab-manet-triangle-shared",
            server_node="node1",
            client_node="node2",
            client_ip="192.168.100.1",
            duration_sec=15,
        )

        # Test node2 → node1
        throughput_2_to_1 = run_iperf3_test(
            container_prefix="clab-manet-triangle-shared",
            server_node="node2",
            client_node="node1",
            client_ip="192.168.100.2",
            duration_sec=15,
        )

        # Both directions should be within 10% of each other
        ratio = max(throughput_1_to_2, throughput_2_to_1) / min(throughput_1_to_2, throughput_2_to_1)
        assert ratio <= 1.1, (
            f"Bidirectional throughput asymmetry too high: "
            f"{throughput_1_to_2:.1f} Mbps vs {throughput_2_to_1:.1f} Mbps (ratio: {ratio:.2f})"
        )

        logger.info(
            f"Bidirectional throughput test passed: "
            f"node1→node2: {throughput_1_to_2:.1f} Mbps, "
            f"node2→node1: {throughput_2_to_1:.1f} Mbps"
        )

    finally:
        # Stop deployment process
        stop_deployment_process(deploy_process)
        # Cleanup containers
        destroy_topology(str(yaml_path))


@pytest.mark.integration
def test_manet_shared_bridge_routing(channel_server, examples_dir: Path):
    """
    Test MANET shared bridge routing configuration.

    Expected: All nodes have routes to the bridge subnet (192.168.100.0/24) on eth1.
    """
    yaml_path = examples_dir / "manet_triangle_shared" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    # Cleanup any existing deployment first
    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        # Deploy (returns background process)
        deploy_process = deploy_topology(str(yaml_path))

        # Verify routing for all nodes
        for node in ["node1", "node2", "node3"]:
            verify_route_to_cidr(
                "clab-manet-triangle-shared",
                node,
                "192.168.100.0/24",
                "eth1"
            )
            logger.info(f"✓ {node}: Route to 192.168.100.0/24 verified on eth1")

        print("\n" + "="*70)
        print("All routing verification tests passed!")
        print("="*70 + "\n")

    finally:
        # Stop deployment process
        stop_deployment_process(deploy_process)
        # Cleanup containers
        destroy_topology(str(yaml_path))


@pytest.mark.integration
def test_manet_shared_bridge_tc_config(channel_server, examples_dir: Path):
    """
    Test MANET shared bridge TC configuration.

    Expected: Per-destination TC with HTB classes, netem qdiscs, and flower filters.
    """
    yaml_path = examples_dir / "manet_triangle_shared" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    # Cleanup any existing deployment first
    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        # Deploy (returns background process)
        deploy_process = deploy_topology(str(yaml_path))

        # Expected parameters (from network.yaml: 64-QAM, 80 MHz, rate-1/2 LDPC)
        # PHY rate = 80 MHz × 6 bits/symbol × 0.5 code_rate × 0.8 efficiency = 192 Mbps
        expected_rate = 192.0
        # Note: Delay may be very small (<0.1ms) and might not show up in netem
        # We'll verify it's present but not check exact value
        expected_loss = 0.0  # High SNR (no packet loss)

        # Verify TC config for node1 → node2
        print("\nVerifying node1 → node2 TC configuration...")
        result = verify_tc_config(
            container_prefix="clab-manet-triangle-shared",
            node="node1",
            interface="eth1",
            dst_node_ip="192.168.100.2",
            expected_rate_mbps=expected_rate,
            expected_loss_percent=expected_loss,
            rate_tolerance_mbps=2.0,  # Allow 2 Mbps tolerance
            loss_tolerance_percent=0.1,
        )
        assert result["mode"] == "shared_bridge"
        assert result["filter_match"] is True
        # Delay and jitter may be 0 or very small for short distances - just verify they exist
        assert result["delay_ms"] is not None
        assert result["jitter_ms"] is not None
        logger.info(f"✓ node1 → node2: mode={result['mode']}, rate={result['rate_mbps']:.1f}Mbps, "
                   f"delay={result['delay_ms']:.3f}ms, jitter={result['jitter_ms']:.3f}ms, "
                   f"loss={result['loss_percent']:.2f}%, classid={result['htb_classid']}")

        # Verify TC config for node1 → node3
        print("\nVerifying node1 → node3 TC configuration...")
        result = verify_tc_config(
            container_prefix="clab-manet-triangle-shared",
            node="node1",
            interface="eth1",
            dst_node_ip="192.168.100.3",
            expected_rate_mbps=expected_rate,
            expected_loss_percent=expected_loss,
            rate_tolerance_mbps=2.0,
            loss_tolerance_percent=0.1,
        )
        assert result["mode"] == "shared_bridge"
        assert result["filter_match"] is True
        assert result["delay_ms"] is not None
        assert result["jitter_ms"] is not None
        logger.info(f"✓ node1 → node3: mode={result['mode']}, rate={result['rate_mbps']:.1f}Mbps, "
                   f"delay={result['delay_ms']:.3f}ms, jitter={result['jitter_ms']:.3f}ms, "
                   f"loss={result['loss_percent']:.2f}%, classid={result['htb_classid']}")

        # Verify TC config for node2 → node1
        print("\nVerifying node2 → node1 TC configuration...")
        result = verify_tc_config(
            container_prefix="clab-manet-triangle-shared",
            node="node2",
            interface="eth1",
            dst_node_ip="192.168.100.1",
            expected_rate_mbps=expected_rate,
            expected_loss_percent=expected_loss,
            rate_tolerance_mbps=2.0,
            loss_tolerance_percent=0.1,
        )
        assert result["mode"] == "shared_bridge"
        assert result["filter_match"] is True
        assert result["delay_ms"] is not None
        assert result["jitter_ms"] is not None
        logger.info(f"✓ node2 → node1: mode={result['mode']}, rate={result['rate_mbps']:.1f}Mbps, "
                   f"delay={result['delay_ms']:.3f}ms, jitter={result['jitter_ms']:.3f}ms, "
                   f"loss={result['loss_percent']:.2f}%, classid={result['htb_classid']}")

        print("\n" + "="*70)
        print("All TC configuration verification tests passed!")
        print("="*70 + "\n")

    finally:
        # Stop deployment process
        stop_deployment_process(deploy_process)
        # Cleanup containers
        destroy_topology(str(yaml_path))


if __name__ == "__main__":
    # Run tests via pytest for proper fixture handling
    import sys

    logging.basicConfig(level=logging.INFO)

    print("=" * 80)
    print("Running MANET shared bridge tests via pytest...")
    print("=" * 80)
    print("\nUsage: sudo -v && uv run pytest tests/integration/test_manet_shared_bridge.py -v -s")
    print("\nNote: Cannot run test functions directly - they require pytest fixtures.")
    print("=" * 80)

    sys.exit(1)
