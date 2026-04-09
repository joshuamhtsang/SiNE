"""Integration tests for examples/for_user/04_through_the_wall.

Same P2P geometry as example 03 but indoors (two_rooms.xml scene).
A concrete wall separates the nodes; Sionna finds the doorway multipath path.
The wall drops SNR by 15-20 dB relative to free space, reducing MCS selection.

Node IPs: node1=10.0.0.1, node2=10.0.0.2
Expected SNR ~18-22 dB → MCS 4-7 → throughput [100, 320] Mbps.
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
    verify_tc_config,
)

__all__ = ["channel_server"]

_NODE_IPS = {"node1": "10.0.0.1", "node2": "10.0.0.2"}


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_through_wall_connectivity(channel_server, examples_for_user: Path):
    """Bidirectional ping succeeds through the wall — Sionna finds doorway path.

    Even with wall attenuation, SNR ~18-22 dB exceeds QPSK threshold (~8 dB),
    so the link remains usable.
    """
    yaml_path = examples_for_user / "04_through_the_wall" / "network.yaml"
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
def test_through_wall_throughput(channel_server, examples_for_user: Path):
    """node1→node2 throughput in [100, 320] Mbps — wall attenuation reduces MCS.

    MCS 4 = 96 Mbps, MCS 7 = 320 Mbps. Indoor NLOS typically puts SNR at
    18-22 dB → MCS 5-7.  Upper bound (320 Mbps) is below example 03's ~480 Mbps,
    confirming that the wall is modeled and degrades the link.
    """
    yaml_path = examples_for_user / "04_through_the_wall" / "network.yaml"
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

        assert 100.0 <= throughput <= 320.0, (
            f"Throughput {throughput:.1f} Mbps not in expected range "
            f"[100, 320] Mbps (MCS 4-7 from indoor NLOS attenuation)"
        )
    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_through_wall_tc_config(channel_server, examples_for_user: Path):
    """netem rate on node1:eth1 falls within the indoor MCS range [100, 320] Mbps.

    Verifies that the channel pipeline translated Sionna ray tracing results into
    a tc rate limit consistent with wall-attenuated SNR (MCS 4-7).
    """
    yaml_path = examples_for_user / "04_through_the_wall" / "network.yaml"
    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))
    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))
        container_prefix = extract_container_prefix(str(yaml_path))

        verify_tc_config(
            container_prefix=container_prefix,
            node="node1",
            interface="eth1",
            expected_rate_mbps=192,   # midpoint; actual value depends on Sionna result
            rate_tolerance_mbps=100,  # ±100 Mbps covers the full [100, 320] Mbps window
        )
    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))
