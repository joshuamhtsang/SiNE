"""
Integration tests for MANET shared bridge TC configuration.

These tests verify that traffic control (tc) is correctly configured with:
- HTB classes for bandwidth limiting
- Netem qdiscs for latency/loss emulation
- Flower filters for per-destination rules

Requirements:
- Channel server running (automatically started by test fixture)
- sudo access for netem configuration
- containerlab installed

Running these tests:
    UV_PATH=$(which uv) sudo -E pytest -s tests/integration/shared_bridge/sionna_engine/snr/test_manet_tc_config.py -v
"""

import asyncio
import logging
import tempfile
from pathlib import Path

import pytest
import yaml

from tests.integration.fixtures import (
    channel_server,
    deploy_topology,
    destroy_topology,
    extract_container_prefix,
    stop_deployment_process,
    verify_tc_config,
)
from sine.emulation.controller import EmulationController

logger = logging.getLogger(__name__)


# Prevent "imported but unused" warnings - these are pytest fixtures
__all__ = ["channel_server"]


@pytest.mark.integration
def test_manet_shared_bridge_tc_config(channel_server, examples_for_tests: Path):
    """
    Test MANET shared bridge TC configuration.

    Expected: Per-destination TC with HTB classes, netem qdiscs, and flower filters.
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

        # Expected parameters (from network.yaml: 64-QAM, 80 MHz, rate-1/2 LDPC)
        # PHY rate = 80 MHz × 6 bits/symbol × 0.5 code_rate × 0.8 efficiency = 192 Mbps
        expected_rate = 192.0
        # Note: Delay may be very small (<0.1ms) and might not show up in netem
        # We'll verify it's present but not check exact value
        expected_loss = 0.0  # High SNR (no packet loss)

        # Verify TC config for node1 → node2
        print("\nVerifying node1 → node2 TC configuration...")
        result = verify_tc_config(
            container_prefix=container_prefix,
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
            container_prefix=container_prefix,
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
            container_prefix=container_prefix,
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


@pytest.mark.integration
def test_shared_bridge_bidirectional_asymmetric_nf(channel_server, examples_for_tests: Path):
    """
    CRITICAL REGRESSION TEST: Verify shared bridge mode with asymmetric noise figures.

    This test ensures that the bidirectional P2P changes don't break shared bridge functionality.

    Topology: 3-node triangle on shared bridge with asymmetric NF (uses inline YAML from for_tests)
    - node1: NF=7 dB (WiFi 6)
    - node2: NF=10 dB (IoT device)
    - node3: NF=5 dB (high-end base station)

    Expected behavior:
    1. Each node has ONE interface (eth1) connected to shared bridge
    2. Per-destination tc flower filters on each interface
    3. Different netem params per destination based on receiver's NF
    4. All 6 directional links (3 nodes × 2 directions) have correct params

    Example: node1:eth1 should have:
    - Packets to node2 (192.168.100.2): Uses node2's NF=10dB → higher loss
    - Packets to node3 (192.168.100.3): Uses node3's NF=5dB → lower loss
    """
    # Use the pre-created test topology file
    yaml_path = examples_for_tests / "shared_sionna_snr_equal-triangle-varied-nf" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    controller = EmulationController(yaml_path)

    try:
        asyncio.run(controller.start())

        # Verify all 6 directional link states exist
        expected_links = [
            ("node1", "node2"),
            ("node1", "node3"),
            ("node2", "node1"),
            ("node2", "node3"),
            ("node3", "node1"),
            ("node3", "node2"),
        ]

        for tx, rx in expected_links:
            link_state = controller._link_states.get((tx, "eth1", rx, "eth1"))
            assert link_state is not None, f"Link state {tx}→{rx} missing"

        # Verify SNR differences based on receiver NF
        # node1→node2 (RX NF=10dB) vs node1→node3 (RX NF=5dB) should differ by 5dB
        snr_12 = controller._link_states[("node1", "eth1", "node2", "eth1")]["rf"]["snr_db"]
        snr_13 = controller._link_states[("node1", "eth1", "node3", "eth1")]["rf"]["snr_db"]

        snr_diff = snr_13 - snr_12  # node3 has better NF → higher SNR
        assert 4.5 < snr_diff < 5.5, (
            f"Expected ~5 dB SNR difference (NF: 10dB vs 5dB), "
            f"got {snr_diff:.1f} dB (to node2: {snr_12:.1f} dB, to node3: {snr_13:.1f} dB)"
        )

        logger.info("✅ Shared bridge bidirectional computation with asymmetric NF verified")

    finally:
        asyncio.run(controller.stop())


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
