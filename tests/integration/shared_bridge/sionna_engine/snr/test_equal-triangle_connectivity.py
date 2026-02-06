"""
Integration tests for MANET shared bridge connectivity.

These tests deploy the manet_triangle_shared example and validate:
1. All nodes can reach each other (ping connectivity)
2. iperf3 throughput matches expected rates
3. Bidirectional throughput symmetry

Requirements:
- Channel server running (automatically started by test fixture)
- sudo access for netem configuration (passwordless or pre-authenticated)
- containerlab installed
- iperf3 installed in container images

Running these tests:
    UV_PATH=$(which uv) sudo -E pytest -s tests/integration/shared_bridge/sionna_engine/snr/test_manet_connectivity.py -v
"""

import logging
from pathlib import Path

import pytest

# Import shared fixtures and helpers
from tests.integration.fixtures import (
    bridge_node_ips,
    channel_server,
    deploy_topology,
    destroy_topology,
    extract_container_prefix,
    run_iperf3_test,
    stop_deployment_process,
    verify_ping_connectivity,
)

logger = logging.getLogger(__name__)


# Prevent "imported but unused" warnings - these are pytest fixtures
__all__ = ["bridge_node_ips", "channel_server"]


@pytest.mark.integration
@pytest.mark.slow
def test_manet_shared_bridge_connectivity(channel_server, examples_for_tests: Path, bridge_node_ips: dict):
    """
    Test MANET shared bridge connectivity.

    Expected: All nodes can ping each other (all-to-all connectivity).
    """
    yaml_path = examples_for_tests / "shared_sionna_snr_equal-triangle" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    # Cleanup any existing deployment first
    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        # Deploy (returns background process)
        deploy_process = deploy_topology(str(yaml_path))

        # Get container prefix from topology
        container_prefix = extract_container_prefix(str(yaml_path))

        verify_ping_connectivity(container_prefix, bridge_node_ips)

    finally:
        # Stop deployment process
        stop_deployment_process(deploy_process)
        # Cleanup containers
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
def test_manet_shared_bridge_throughput(channel_server, examples_for_tests: Path, bridge_node_ips: dict):
    """
    Test MANET shared bridge throughput.

    Expected: Throughput matches configured rate (~192 Mbps for 64-QAM, 80 MHz, rate-1/2).
    PHY rate = 80 MHz × 6 bits/symbol × 0.5 code_rate × 0.8 efficiency = 192 Mbps
    """
    yaml_path = examples_for_tests / "shared_sionna_snr_equal-triangle" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    # Cleanup any existing deployment first
    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        # Deploy (returns background process)
        deploy_process = deploy_topology(str(yaml_path))

        # Get container prefix from topology
        container_prefix = extract_container_prefix(str(yaml_path))

        # Run iperf3 test (using the shared bridge IPs already configured)
        throughput = run_iperf3_test(
            container_prefix=container_prefix,
            server_node="node1",
            client_node="node2",
            client_ip=bridge_node_ips["node1"],
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
def test_manet_shared_bridge_bidirectional_throughput(channel_server, examples_for_tests: Path, bridge_node_ips: dict):
    """
    Test bidirectional throughput in MANET shared bridge.

    Expected: Both directions achieve similar throughput (symmetric links).
    """
    yaml_path = examples_for_tests / "shared_sionna_snr_equal-triangle" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    # Cleanup any existing deployment first
    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        # Deploy (returns background process)
        deploy_process = deploy_topology(str(yaml_path))

        # Get container prefix from topology
        container_prefix = extract_container_prefix(str(yaml_path))

        # Test node1 → node2
        throughput_1_to_2 = run_iperf3_test(
            container_prefix=container_prefix,
            server_node="node1",
            client_node="node2",
            client_ip=bridge_node_ips["node1"]
        )

        # Test node2 → node1
        throughput_2_to_1 = run_iperf3_test(
            container_prefix=container_prefix,
            server_node="node2",
            client_node="node1",
            client_ip=bridge_node_ips["node2"]
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


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
