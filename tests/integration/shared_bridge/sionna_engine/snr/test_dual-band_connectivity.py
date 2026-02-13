"""
Integration tests for dual-band shared bridge deployment.

These tests verify that a topology with multiple wireless interfaces per node
(dual-band: 5 GHz + 2.4 GHz) deploys correctly with:
1. All 4 interface pairs get link states (2 nodes x 2 ifaces = 4 directional links per band)
2. Per-destination TC filters on each interface
3. Different rates for different bands (80 MHz vs 20 MHz bandwidth)
4. Ping connectivity on both bands

Requirements:
- Channel server running (automatically started by test fixture)
- sudo access for netem configuration
- containerlab installed

Running these tests:
    UV_PATH=$(which uv) sudo -E $(which uv) run pytest -s tests/integration/shared_bridge/sionna_engine/snr/test_dual-band_connectivity.py -v
"""

import asyncio
import logging
from pathlib import Path

import pytest

from sine.emulation.controller import EmulationController
from tests.integration.fixtures import (
    channel_server,
    deploy_topology,
    destroy_topology,
    extract_container_prefix,
    stop_deployment_process,
    verify_ping_connectivity,
    verify_tc_config,
)

logger = logging.getLogger(__name__)


# Prevent "imported but unused" warnings - these are pytest fixtures
__all__ = ["channel_server"]


@pytest.mark.integration
def test_dual_band_link_states(channel_server, examples_for_tests: Path):
    """
    Test dual-band shared bridge link state computation.

    Topology: 2 nodes, each with eth1 (5.18 GHz, 80 MHz) and eth2 (2.4 GHz, 20 MHz).
    All 4 wireless interfaces are on the shared bridge.

    Expected:
    - 8 directional link states (4 cross-node pairs x 2 directions):
      node1:eth1 -> node2:eth1 (5 GHz same-band)
      node1:eth1 -> node2:eth2 (5 GHz -> 2.4 GHz cross-band)
      node1:eth2 -> node2:eth1 (2.4 GHz -> 5 GHz cross-band)
      node1:eth2 -> node2:eth2 (2.4 GHz same-band)
      ... and 4 reverse directions
    - Same-band links have good SNR (low loss)
    - Cross-band links have high ACLR isolation (high loss or capped)
    - 5 GHz band has higher rate (80 MHz BW) than 2.4 GHz (20 MHz BW)
    """
    yaml_path = examples_for_tests / "shared_sionna_snr_dual-band" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    controller = EmulationController(yaml_path)

    try:
        asyncio.run(controller.start())

        # Verify all 8 directional link states exist (4-tuple keys)
        # Cross-node links (not same-node self-isolation)
        expected_cross_node = [
            ("node1", "eth1", "node2", "eth1"),  # 5 GHz -> 5 GHz
            ("node1", "eth1", "node2", "eth2"),  # 5 GHz -> 2.4 GHz
            ("node1", "eth2", "node2", "eth1"),  # 2.4 GHz -> 5 GHz
            ("node1", "eth2", "node2", "eth2"),  # 2.4 GHz -> 2.4 GHz
            ("node2", "eth1", "node1", "eth1"),  # reverse
            ("node2", "eth1", "node1", "eth2"),  # reverse
            ("node2", "eth2", "node1", "eth1"),  # reverse
            ("node2", "eth2", "node1", "eth2"),  # reverse
        ]

        for key in expected_cross_node:
            state = controller._link_states.get(key)
            assert state is not None, (
                f"Missing link state for {key[0]}:{key[1]} -> {key[2]}:{key[3]}"
            )

        # Same-node self-isolation links (from _apply_same_node_isolation)
        expected_same_node = [
            ("node1", "eth1", "node1", "eth2"),
            ("node1", "eth2", "node1", "eth1"),
            ("node2", "eth1", "node2", "eth2"),
            ("node2", "eth2", "node2", "eth1"),
        ]

        for key in expected_same_node:
            state = controller._link_states.get(key)
            assert state is not None, (
                f"Missing self-isolation link state for "
                f"{key[0]}:{key[1]} -> {key[2]}:{key[3]}"
            )
            assert state["rf"].get("self_isolation") is True, (
                f"Expected self_isolation=True for same-node link "
                f"{key[0]}:{key[1]} -> {key[2]}:{key[3]}"
            )

        # Verify same-band links have reasonable SNR
        snr_5g = controller._link_states[
            ("node1", "eth1", "node2", "eth1")
        ]["rf"]["snr_db"]
        snr_24g = controller._link_states[
            ("node1", "eth2", "node2", "eth2")
        ]["rf"]["snr_db"]

        assert snr_5g is not None and snr_5g > 10, (
            f"5 GHz same-band SNR too low: {snr_5g} dB"
        )
        assert snr_24g is not None and snr_24g > 10, (
            f"2.4 GHz same-band SNR too low: {snr_24g} dB"
        )

        # 5 GHz link should have higher rate than 2.4 GHz link
        # (80 MHz BW vs 20 MHz BW, same modulation)
        rate_5g = controller._link_states[
            ("node1", "eth1", "node2", "eth1")
        ]["netem"].rate_mbps
        rate_24g = controller._link_states[
            ("node1", "eth2", "node2", "eth2")
        ]["netem"].rate_mbps

        # 5 GHz: 80 MHz × 6 bits × 0.5 × 0.8 = 192 Mbps
        # 2.4 GHz: 20 MHz × 6 bits × 0.5 × 0.8 = 48 Mbps
        assert rate_5g > rate_24g, (
            f"Expected 5 GHz rate ({rate_5g}) > 2.4 GHz rate ({rate_24g})"
        )
        assert 185 < rate_5g < 200, (
            f"5 GHz rate {rate_5g} Mbps not near expected 192 Mbps"
        )
        assert 44 < rate_24g < 52, (
            f"2.4 GHz rate {rate_24g} Mbps not near expected 48 Mbps"
        )

        # Log summary
        total_states = len(controller._link_states)
        logger.info(
            f"Dual-band link states verified: {total_states} total "
            f"({len(expected_cross_node)} cross-node + "
            f"{len(expected_same_node)} self-isolation)"
        )
        logger.info(f"5 GHz SNR: {snr_5g:.1f} dB, rate: {rate_5g:.1f} Mbps")
        logger.info(f"2.4 GHz SNR: {snr_24g:.1f} dB, rate: {rate_24g:.1f} Mbps")

    finally:
        asyncio.run(controller.stop())


@pytest.mark.integration
@pytest.mark.slow
def test_dual_band_tc_config(channel_server, examples_for_tests: Path):
    """
    Test dual-band TC configuration with per-destination filters.

    Each interface should have flower filters for destinations on both bands.
    node1:eth1 should have filters for node2's 5 GHz IP (192.168.100.2)
    and node2's 2.4 GHz IP (192.168.200.2).
    """
    yaml_path = examples_for_tests / "shared_sionna_snr_dual-band" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))
        container_prefix = extract_container_prefix(str(yaml_path))

        # node1:eth1 -> node2:eth1 (5 GHz same-band, should have ~192 Mbps)
        print("\nVerifying node1:eth1 -> node2 (5 GHz IP 192.168.100.2)...")
        result = verify_tc_config(
            container_prefix=container_prefix,
            node="node1",
            interface="eth1",
            dst_node_ip="192.168.100.2",
            expected_rate_mbps=192.0,
            rate_tolerance_mbps=5.0,
        )
        assert result["mode"] == "shared_bridge"
        assert result["filter_match"] is True
        logger.info(
            f"node1:eth1 -> 192.168.100.2: "
            f"rate={result['rate_mbps']:.1f} Mbps"
        )

        # node1:eth2 -> node2:eth2 (2.4 GHz same-band, should have ~48 Mbps)
        print("\nVerifying node1:eth2 -> node2 (2.4 GHz IP 192.168.200.2)...")
        result = verify_tc_config(
            container_prefix=container_prefix,
            node="node1",
            interface="eth2",
            dst_node_ip="192.168.200.2",
            expected_rate_mbps=48.0,
            rate_tolerance_mbps=5.0,
        )
        assert result["mode"] == "shared_bridge"
        assert result["filter_match"] is True
        logger.info(
            f"node1:eth2 -> 192.168.200.2: "
            f"rate={result['rate_mbps']:.1f} Mbps"
        )

        print("\n" + "=" * 70)
        print("Dual-band TC configuration tests passed!")
        print("=" * 70 + "\n")

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
def test_dual_band_ping_connectivity(channel_server, examples_for_tests: Path):
    """
    Test dual-band ping connectivity on both subnets.

    Expected: Nodes can ping each other on both the 5 GHz subnet
    (192.168.100.x) and 2.4 GHz subnet (192.168.200.x).
    """
    yaml_path = examples_for_tests / "shared_sionna_snr_dual-band" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))
        container_prefix = extract_container_prefix(str(yaml_path))

        # Test 5 GHz band connectivity (eth1: 192.168.100.x)
        print("\nTesting 5 GHz band connectivity...")
        band_5g_ips = {
            "node1": "192.168.100.1",
            "node2": "192.168.100.2",
        }
        verify_ping_connectivity(container_prefix, band_5g_ips)

        # Test 2.4 GHz band connectivity (eth2: 192.168.200.x)
        print("\nTesting 2.4 GHz band connectivity...")
        band_24g_ips = {
            "node1": "192.168.200.1",
            "node2": "192.168.200.2",
        }
        verify_ping_connectivity(container_prefix, band_24g_ips)

        print("\n" + "=" * 70)
        print("Dual-band ping connectivity tests passed!")
        print("=" * 70 + "\n")

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
