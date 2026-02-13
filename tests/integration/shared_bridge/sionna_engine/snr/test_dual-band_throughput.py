"""Throughput tests for shared_sionna_snr_dual-band example.

Tests iperf3 TCP throughput on both frequency bands of a dual-band topology.
Validates that each band achieves the expected PHY rate:
- 5 GHz (eth1, 80 MHz): 64-QAM, rate-0.5 LDPC → ~192 Mbps
- 2.4 GHz (eth2, 20 MHz): 64-QAM, rate-0.5 LDPC → ~48 Mbps
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
def test_dual_band_throughput_5ghz(channel_server, examples_for_tests: Path):
    """Test iperf3 throughput on 5 GHz band (eth1).

    PHY rate: 80 MHz × 6 bits × 0.5 × 0.8 (overhead) = 192 Mbps
    Expected measured: 170-200 Mbps (TCP overhead, netem shaping)
    """
    yaml_path = examples_for_tests / "shared_sionna_snr_dual-band" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))
        container_prefix = extract_container_prefix(yaml_path)

        # Measure throughput on 5 GHz subnet (192.168.100.x via eth1)
        throughput = run_iperf3_test(
            container_prefix=container_prefix,
            server_node="node2",
            client_node="node1",
            server_ip="192.168.100.2",
            duration_sec=10,
        )

        # 64-QAM, rate-0.5, 80 MHz → 192 Mbps PHY
        # Allow for TCP overhead and measurement variance
        assert 170.0 <= throughput <= 200.0, (
            f"5 GHz throughput {throughput:.2f} Mbps outside expected range "
            f"170-200 Mbps (PHY rate 192 Mbps)"
        )

        print(f"✓ 5 GHz band throughput validated: {throughput:.2f} Mbps")

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_dual_band_throughput_24ghz(channel_server, examples_for_tests: Path):
    """Test iperf3 throughput on 2.4 GHz band (eth2).

    PHY rate: 20 MHz × 6 bits × 0.5 × 0.8 (overhead) = 48 Mbps
    Expected measured: 40-52 Mbps (TCP overhead, netem shaping)
    """
    yaml_path = examples_for_tests / "shared_sionna_snr_dual-band" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))
        container_prefix = extract_container_prefix(yaml_path)

        # Measure throughput on 2.4 GHz subnet (192.168.200.x via eth2)
        throughput = run_iperf3_test(
            container_prefix=container_prefix,
            server_node="node2",
            client_node="node1",
            server_ip="192.168.200.2",
            duration_sec=10,
        )

        # 64-QAM, rate-0.5, 20 MHz → 48 Mbps PHY
        # Allow for TCP overhead and measurement variance
        assert 40.0 <= throughput <= 52.0, (
            f"2.4 GHz throughput {throughput:.2f} Mbps outside expected range "
            f"40-52 Mbps (PHY rate 48 Mbps)"
        )

        print(f"✓ 2.4 GHz band throughput validated: {throughput:.2f} Mbps")

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_dual_band_throughput_both_bands_bidirectional(
    channel_server, examples_for_tests: Path
):
    """Test bidirectional throughput on both bands in a single deployment.

    Validates:
    - Both bands work within a single deployment
    - 5 GHz rate >> 2.4 GHz rate (4:1 ratio from 80 vs 20 MHz BW)
    - Each direction is symmetric on both bands
    """
    yaml_path = examples_for_tests / "shared_sionna_snr_dual-band" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))
        container_prefix = extract_container_prefix(yaml_path)

        # --- 5 GHz band (eth1: 192.168.100.x) ---
        print("\n--- 5 GHz band throughput ---")

        throughput_5g_fwd = run_iperf3_test(
            container_prefix=container_prefix,
            server_node="node2",
            client_node="node1",
            server_ip="192.168.100.2",
            duration_sec=8,
        )
        print(f"  node1→node2 (5 GHz): {throughput_5g_fwd:.2f} Mbps")

        throughput_5g_rev = run_iperf3_test(
            container_prefix=container_prefix,
            server_node="node1",
            client_node="node2",
            server_ip="192.168.100.1",
            duration_sec=8,
        )
        print(f"  node2→node1 (5 GHz): {throughput_5g_rev:.2f} Mbps")

        # --- 2.4 GHz band (eth2: 192.168.200.x) ---
        print("\n--- 2.4 GHz band throughput ---")

        throughput_24g_fwd = run_iperf3_test(
            container_prefix=container_prefix,
            server_node="node2",
            client_node="node1",
            server_ip="192.168.200.2",
            duration_sec=8,
        )
        print(f"  node1→node2 (2.4 GHz): {throughput_24g_fwd:.2f} Mbps")

        throughput_24g_rev = run_iperf3_test(
            container_prefix=container_prefix,
            server_node="node1",
            client_node="node2",
            server_ip="192.168.200.1",
            duration_sec=8,
        )
        print(f"  node2→node1 (2.4 GHz): {throughput_24g_rev:.2f} Mbps")

        # --- Assertions ---

        # 5 GHz band: 170-200 Mbps
        for label, tp in [("fwd", throughput_5g_fwd), ("rev", throughput_5g_rev)]:
            assert 170.0 <= tp <= 200.0, (
                f"5 GHz {label} throughput {tp:.2f} Mbps outside 170-200 Mbps"
            )

        # 2.4 GHz band: 40-52 Mbps
        for label, tp in [("fwd", throughput_24g_fwd), ("rev", throughput_24g_rev)]:
            assert 40.0 <= tp <= 52.0, (
                f"2.4 GHz {label} throughput {tp:.2f} Mbps outside 40-52 Mbps"
            )

        # Bidirectional symmetry: each band within 10%
        ratio_5g = max(throughput_5g_fwd, throughput_5g_rev) / min(
            throughput_5g_fwd, throughput_5g_rev
        )
        assert ratio_5g <= 1.1, (
            f"5 GHz bidirectional asymmetry too high: "
            f"{throughput_5g_fwd:.1f} vs {throughput_5g_rev:.1f} Mbps "
            f"(ratio {ratio_5g:.2f})"
        )

        ratio_24g = max(throughput_24g_fwd, throughput_24g_rev) / min(
            throughput_24g_fwd, throughput_24g_rev
        )
        assert ratio_24g <= 1.1, (
            f"2.4 GHz bidirectional asymmetry too high: "
            f"{throughput_24g_fwd:.1f} vs {throughput_24g_rev:.1f} Mbps "
            f"(ratio {ratio_24g:.2f})"
        )

        # Band ratio: 5 GHz should be ~4x 2.4 GHz (80/20 MHz BW ratio)
        mean_5g = (throughput_5g_fwd + throughput_5g_rev) / 2
        mean_24g = (throughput_24g_fwd + throughput_24g_rev) / 2
        band_ratio = mean_5g / mean_24g

        assert 3.0 <= band_ratio <= 5.0, (
            f"Band ratio {band_ratio:.2f} outside expected 3.0-5.0 "
            f"(5 GHz: {mean_5g:.1f} Mbps, 2.4 GHz: {mean_24g:.1f} Mbps)"
        )

        print(f"\n✓ Both bands validated:")
        print(f"  5 GHz mean: {mean_5g:.2f} Mbps")
        print(f"  2.4 GHz mean: {mean_24g:.2f} Mbps")
        print(f"  Band ratio: {band_ratio:.2f}x (expected ~4x)")

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))
