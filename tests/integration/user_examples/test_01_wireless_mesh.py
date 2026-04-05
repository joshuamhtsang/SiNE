"""Integration tests for examples/for_user/01_wireless_mesh.

Validates a 3-node WiFi mesh in free space (vacuum.xml):
- All-to-all ping connectivity (no interference, SNR >> threshold)
- Short-link (30m) throughput at MCS 10 (1024-QAM 3/4, 80 MHz)
- Geometry drives rate: 30m link is measurably faster than 91m link
"""

import pytest
from pathlib import Path

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

# Prevent "imported but unused" warnings — these are pytest fixtures
__all__ = ["bridge_node_ips", "channel_server"]


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_wireless_mesh_all_connectivity(channel_server, examples_for_user: Path, bridge_node_ips: dict):
    """All 6 ping directions succeed — no interference, SNR >> any MCS threshold.

    Node geometry (vacuum.xml):
      node1 at (0,0,1), node2 at (30,0,1), node3 at (15,25.98,1)
      node1↔node2: 30m, node1↔node3: 30m, node2↔node3: 30m
    Expected SNR ~36 dB at 30m → MCS 10 (min 35 dB) → reliable connectivity.
    """
    yaml_path = examples_for_user / "01_wireless_mesh" / "network.yaml"
    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))
    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))
        container_prefix = extract_container_prefix(str(yaml_path))
        verify_ping_connectivity(container_prefix, bridge_node_ips)
    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.very_slow
@pytest.mark.sionna
def test_wireless_mesh_short_link_throughput(channel_server, examples_for_user: Path, bridge_node_ips: dict):
    """node1→node2 (30m) throughput in [400, 533] Mbps — MCS 10, 1024-QAM 3/4.

    Rate basis: 80 MHz × 10 bits/symbol × 0.75 code_rate × 0.8 efficiency = 480 Mbps
    Allow 83–111% to account for TCP overhead and measurement variance → [400, 533].
    """
    yaml_path = examples_for_user / "01_wireless_mesh" / "network.yaml"
    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))
    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))
        container_prefix = extract_container_prefix(str(yaml_path))

        throughput = run_iperf3_test(
            container_prefix=container_prefix,
            server_node="node1",
            client_node="node2",
            server_ip=bridge_node_ips["node1"],
            duration_sec=10,
        )

        assert 400.0 <= throughput <= 533.0, (
            f"Short-link throughput {throughput:.1f} Mbps not in expected range "
            f"[400, 533] Mbps (MCS 10, 1024-QAM 3/4, 80 MHz)"
        )
    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.very_slow
@pytest.mark.sionna
def test_wireless_mesh_geometry_drives_rate(channel_server, examples_for_user: Path, bridge_node_ips: dict):
    """Geometry alone causes rate difference: 30m link is ≥1.2× faster than 91m link.

    node1↔node2: 30m → ~480 Mbps (MCS 10, SNR ~36 dB)
    node1↔node3: 91m → ~320 Mbps (MCS 7, SNR ~26 dB)
    No manual config difference — geometry drives MCS selection automatically.
    """
    yaml_path = examples_for_user / "01_wireless_mesh" / "network.yaml"
    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))
    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))
        container_prefix = extract_container_prefix(str(yaml_path))

        short_tput = run_iperf3_test(
            container_prefix=container_prefix,
            server_node="node1",
            client_node="node2",
            server_ip=bridge_node_ips["node1"],
            duration_sec=10,
        )

        long_tput = run_iperf3_test(
            container_prefix=container_prefix,
            server_node="node1",
            client_node="node3",
            server_ip=bridge_node_ips["node1"],
            duration_sec=10,
        )

        ratio = short_tput / long_tput
        assert ratio >= 1.2, (
            f"Geometry-driven rate difference too small: "
            f"30m={short_tput:.1f} Mbps, 91m={long_tput:.1f} Mbps (ratio={ratio:.2f}, need ≥1.2)"
        )
    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))
