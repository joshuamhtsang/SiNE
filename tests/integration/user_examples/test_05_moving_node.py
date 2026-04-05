"""Integration tests for examples/for_user/05_moving_node.

P2P link with runtime mobility (two_rooms.xml scene). The AP is fixed in room 1
aligned with the doorway (x=10, y=20, z=2.5). The client starts in room 2 at the
south side, far from the doorway (x=30, y=5, z=1), then moves to doorway alignment
(x=30, y=20, z=1) via the control API.

All tests deploy with enable_control=True (port 8002).
Node IPs: ap=10.0.1.1, client=10.0.1.2
"""

import time
import pytest
from pathlib import Path

from tests.integration.fixtures import (
    channel_server,
    control_api_get,
    control_api_post,
    deploy_topology,
    destroy_topology,
    extract_container_prefix,
    run_iperf3_test,
    stop_deployment_process,
    verify_ping_connectivity,
)

__all__ = ["channel_server"]

_CONTROL_API_URL = "http://localhost:8002"
_NODE_IPS = {"ap": "10.0.1.1", "client": "10.0.1.2"}

# Client starting position (y=5, far from doorway)
_START_POS = {"x": 30.0, "y": 5.0, "z": 1.0}

# Doorway-aligned position (y=20, same as AP)
_DOORWAY_POS = {"x": 30.0, "y": 20.0, "z": 1.0}


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_moving_node_initial_connectivity(channel_server, examples_for_user: Path):
    """Bidirectional ping succeeds at starting position — link is weak but alive.

    Client starts at (30, 5, 1): oblique NLOS through wall, far from doorway.
    Sionna finds reflections / diffraction paths that keep SNR above QPSK threshold.
    """
    yaml_path = examples_for_user / "05_moving_node" / "network.yaml"
    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))
    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path), enable_control=True)
        container_prefix = extract_container_prefix(str(yaml_path))
        verify_ping_connectivity(container_prefix, _NODE_IPS)
    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_moving_node_position_update_accepted(channel_server, examples_for_user: Path):
    """POST /api/control/update returns HTTP 200 and GET reflects updated position.

    Moves client from starting position to doorway alignment (y=5 → y=20) and
    verifies the control API stores and returns the new position.
    """
    yaml_path = examples_for_user / "05_moving_node" / "network.yaml"
    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))
    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path), enable_control=True)

        # Move client to doorway-aligned position
        resp = control_api_post(
            _CONTROL_API_URL,
            "/api/control/update",
            {"node": "client", **_DOORWAY_POS},
        )
        assert resp["status"] == "success", f"Unexpected response: {resp}"
        assert resp["node"] == "client"

        # GET should reflect the update
        pos_resp = control_api_get(_CONTROL_API_URL, "/api/control/position/client")
        assert pos_resp["position"]["y"] == pytest.approx(20.0), (
            f"Expected y=20.0 after update, got {pos_resp['position']['y']}"
        )
    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.very_slow
@pytest.mark.sionna
def test_moving_node_throughput_improves_at_doorway(channel_server, examples_for_user: Path):
    """Moving client to doorway alignment improves throughput by ≥1.5×.

    Start: client at (30, 5, 1) — oblique NLOS, lower SNR.
    Move:  client to (30, 20, 1) — doorway LOS path appears, SNR improves.
    Assert: doorway_tput > start_tput × 1.5
    """
    yaml_path = examples_for_user / "05_moving_node" / "network.yaml"
    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))
    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path), enable_control=True)
        container_prefix = extract_container_prefix(str(yaml_path))

        # Measure throughput at starting position (y=5, far from doorway)
        start_tput = run_iperf3_test(
            container_prefix=container_prefix,
            server_node="ap",
            client_node="client",
            server_ip=_NODE_IPS["ap"],
            duration_sec=10,
        )

        # Move client to doorway-aligned position (y=20)
        resp = control_api_post(
            _CONTROL_API_URL,
            "/api/control/update",
            {"node": "client", **_DOORWAY_POS},
        )
        assert resp["status"] == "success", f"Position update failed: {resp}"

        # Wait for channel recomputation and netem to be applied
        time.sleep(1.0)

        # Measure throughput at doorway position
        doorway_tput = run_iperf3_test(
            container_prefix=container_prefix,
            server_node="ap",
            client_node="client",
            server_ip=_NODE_IPS["ap"],
            duration_sec=10,
        )

        assert doorway_tput > start_tput * 1.5, (
            f"Throughput did not improve sufficiently when moving to doorway: "
            f"start={start_tput:.1f} Mbps, doorway={doorway_tput:.1f} Mbps "
            f"(ratio={doorway_tput / start_tput:.2f}, need ≥1.5)"
        )
    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))
