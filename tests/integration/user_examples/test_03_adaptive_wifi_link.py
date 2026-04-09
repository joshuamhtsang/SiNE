"""Integration tests for examples/for_user/03_adaptive_wifi_link.

P2P link in free space (vacuum.xml) at 20m separation.
Validates that adaptive MCS selects the highest modulation scheme at short
range and delivers near-maximum PHY throughput.

Node IPs: node1=192.168.1.1, node2=192.168.1.2
Expected SNR ~36 dB at 20m → MCS 10 (1024-QAM 3/4) → ~480 Mbps.
"""

import pytest
from pathlib import Path

from tests.integration.fixtures import (
    channel_server,
    deploy_topology,
    destroy_topology,
    extract_container_prefix,
    run_iperf3_test,
    stop_deployment_process,
    verify_ping_connectivity,
)

__all__ = ["channel_server"]

_NODE_IPS = {"node1": "10.0.0.1", "node2": "10.0.0.2"}


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_adaptive_link_connectivity(channel_server, examples_for_user: Path):
    """Bidirectional ping succeeds at 20m free-space — SNR ~36 dB >> any threshold."""
    yaml_path = examples_for_user / "03_adaptive_wifi_link" / "network.yaml"
    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))
    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))
        container_prefix = extract_container_prefix(str(yaml_path))
        verify_ping_connectivity(container_prefix, _NODE_IPS)
    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.very_slow
@pytest.mark.sionna
def test_adaptive_link_high_mcs_throughput(channel_server, examples_for_user: Path):
    """node1→node2 throughput in [400, 533] Mbps — adaptive MCS selects MCS 10.

    Rate basis: 80 MHz × 10 bits/symbol × 0.75 code_rate × 0.8 efficiency = 480 Mbps
    Allow 83–111% for TCP overhead and measurement variance → [400, 533] Mbps.
    """
    yaml_path = examples_for_user / "03_adaptive_wifi_link" / "network.yaml"
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
            server_ip=_NODE_IPS["node1"],
            duration_sec=10,
        )

        assert 400.0 <= throughput <= 533.0, (
            f"Throughput {throughput:.1f} Mbps not in expected range "
            f"[400, 533] Mbps (MCS 10, 1024-QAM 3/4, 80 MHz)"
        )
    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))
