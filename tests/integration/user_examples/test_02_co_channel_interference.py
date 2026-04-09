"""Integration tests for examples/for_user/02_co_channel_interference.

Same 3-node mesh as example 01, with enable_sinr: true added.
Validates that co-channel interference kills the outer links while the
node1↔node2 link survives (SINR ~9-10 dB, above QPSK threshold ~8 dB).

Node geometry (vacuum.xml, all at z=1):
  node3 is positioned so that it is equidistant from node1 and node2 but
  further from both, creating a high-interference scenario for outer links.
  node1↔node2 (short link): signal >> interference → SINR ~9 dB
  node1↔node3, node2↔node3 (outer links): SINR ~-3 dB → dead
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
    verify_selective_ping_connectivity,
)

__all__ = ["bridge_node_ips", "channel_server"]


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_interference_surviving_link_connectivity(channel_server, examples_for_user: Path, bridge_node_ips: dict):
    """node1↔node2 bidirectional ping succeeds — SINR ~9-10 dB, above QPSK threshold.

    The close pair (node1↔node2) has sufficient SINR to support QPSK (min ~8 dB).
    """
    yaml_path = examples_for_user / "02_co_channel_interference" / "network.yaml"
    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))
    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))
        container_prefix = extract_container_prefix(str(yaml_path))

        verify_selective_ping_connectivity(
            container_prefix=container_prefix,
            node_ips=bridge_node_ips,
            expected_success=[("node1", "node2"), ("node2", "node1")],
        )
    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_interference_outer_links_dead(channel_server, examples_for_user: Path, bridge_node_ips: dict):
    """Outer links (any pair involving node3) fail — SINR ~-3 dB kills them.

    node1↔node3 and node2↔node3 experience negative SINR due to co-channel
    interference, resulting in 100% packet loss and ping failure.
    node1↔node2 still survives (asserted here too as the control case).
    """
    yaml_path = examples_for_user / "02_co_channel_interference" / "network.yaml"
    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))
    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))
        container_prefix = extract_container_prefix(str(yaml_path))

        verify_selective_ping_connectivity(
            container_prefix=container_prefix,
            node_ips=bridge_node_ips,
            expected_success=[("node1", "node2"), ("node2", "node1")],
            expected_failure=[
                ("node1", "node3"),
                ("node3", "node1"),
                ("node2", "node3"),
                ("node3", "node2"),
            ],
        )
    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.very_slow
@pytest.mark.sionna
def test_interference_throughput_on_surviving_link(channel_server, examples_for_user: Path, bridge_node_ips: dict):
    """node1→node2 throughput in [40, 80] Mbps — interference degrades MCS to ~1.

    SINR ~9 dB forces MCS 1 (QPSK 1/2): 80 MHz × 2 × 0.5 × 0.8 = 64 Mbps PHY rate.
    TCP overhead and residual loss narrow measured throughput to [40, 80] Mbps.
    Compare to example 01's ~480 Mbps on the same link geometry without interference.
    """
    yaml_path = examples_for_user / "02_co_channel_interference" / "network.yaml"
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

        assert 40.0 <= throughput <= 80.0, (
            f"Surviving-link throughput {throughput:.1f} Mbps not in expected range "
            f"[40, 80] Mbps (MCS 1, QPSK 1/2, SINR ~9 dB)"
        )
    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))
