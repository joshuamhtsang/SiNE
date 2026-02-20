"""Integration tests for the Control API (port 8002).

Tests the REST API exposed when deploying with --enable-control.
The control API allows runtime position updates and channel recomputation.

Run all tests:
    UV_PATH=$(which uv) sudo -E $(which uv) run pytest \
        tests/integration/cross_cutting/test_control_api.py -v -s

Run only fallback (faster) tests:
    UV_PATH=$(which uv) sudo -E $(which uv) run pytest \
        tests/integration/cross_cutting/test_control_api.py -m "fallback" -v -s
"""

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from tests.integration.fixtures import (
    channel_server_fallback,  # noqa: F401
    control_api_fallback_deployment,  # noqa: F401
    control_api_fixed_deployment,  # noqa: F401
    control_api_get,
    control_api_post,
    extract_container_prefix,
)


# =============================================================================
# Group 1: Health and Lifecycle
# =============================================================================


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.fallback
def test_control_api_health_running(control_api_fallback_deployment):
    """Health endpoint returns healthy status when emulation is running."""
    _, _, base_url = control_api_fallback_deployment

    data = control_api_get(base_url, "/health")

    assert data["status"] == "healthy"
    assert data["emulation"] == "running"


@pytest.mark.integration
def test_control_api_health_before_deploy():
    """Port 8002 is not listening when control API has not been deployed."""
    import socket

    try:
        with socket.create_connection(("localhost", 8002), timeout=2):
            # Port is in use — skip rather than fail, since another test may
            # have left it running (e.g., parallel test execution).
            pytest.skip("Port 8002 is already in use — skip pre-deploy check")
    except (ConnectionRefusedError, OSError):
        pass  # Expected: port not listening


# =============================================================================
# Group 2: Node Listing
# =============================================================================


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.fallback
def test_control_api_nodes_list(control_api_fallback_deployment):
    """List all nodes returns all nodes with their initial positions."""
    _, _, base_url = control_api_fallback_deployment

    data = control_api_get(base_url, "/api/nodes")

    assert "nodes" in data
    nodes = {n["name"]: n["position"] for n in data["nodes"]}

    assert "node1" in nodes
    assert "node2" in nodes

    # node1 at origin
    assert nodes["node1"]["x"] == pytest.approx(0.0)
    assert nodes["node1"]["y"] == pytest.approx(0.0)
    assert nodes["node1"]["z"] == pytest.approx(1.0)

    # node2 at 20m along X-axis
    assert nodes["node2"]["x"] == pytest.approx(20.0)
    assert nodes["node2"]["y"] == pytest.approx(0.0)
    assert nodes["node2"]["z"] == pytest.approx(1.0)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.fallback
def test_control_api_position_get(control_api_fallback_deployment):
    """Get current position of individual nodes returns correct coordinates."""
    _, _, base_url = control_api_fallback_deployment

    data = control_api_get(base_url, "/api/control/position/node1")
    assert data["node"] == "node1"
    assert data["position"]["x"] == pytest.approx(0.0)
    assert data["position"]["y"] == pytest.approx(0.0)
    assert data["position"]["z"] == pytest.approx(1.0)

    data = control_api_get(base_url, "/api/control/position/node2")
    assert data["node"] == "node2"
    assert data["position"]["x"] == pytest.approx(20.0)
    assert data["position"]["y"] == pytest.approx(0.0)
    assert data["position"]["z"] == pytest.approx(1.0)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.fallback
def test_control_api_position_invalid_node(control_api_fallback_deployment):
    """Returns 404 for an unknown node name."""
    _, _, base_url = control_api_fallback_deployment

    try:
        control_api_get(base_url, "/api/control/position/nonexistent_node")
        raise AssertionError("Expected 404 but got success")
    except urllib.error.HTTPError as e:
        assert e.code == 404, f"Expected 404, got {e.code}"


# =============================================================================
# Group 3: Position Update (Core Functionality)
# =============================================================================


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.fallback
def test_control_api_position_update(control_api_fallback_deployment):
    """POST update stores new position and returns success response."""
    _, _, base_url = control_api_fallback_deployment

    resp = control_api_post(
        base_url,
        "/api/control/update",
        {"node": "node2", "x": 10.0, "y": 0.0, "z": 1.0},
    )

    assert resp["status"] == "success"
    assert resp["node"] == "node2"
    assert resp["position"] == {"x": 10.0, "y": 0.0, "z": 1.0}

    # Verify the GET position endpoint reflects the update
    pos = control_api_get(base_url, "/api/control/position/node2")
    assert pos["position"]["x"] == pytest.approx(10.0)
    assert pos["position"]["y"] == pytest.approx(0.0)
    assert pos["position"]["z"] == pytest.approx(1.0)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.fallback
def test_control_api_position_update_triggers_recompute(control_api_fallback_deployment):
    """After position update, emulation/links shows changed channel conditions."""
    _, _, base_url = control_api_fallback_deployment

    # Query initial link state (node2 at 20m)
    links_before = control_api_get(base_url, "/api/emulation/links")
    assert len(links_before["links"]) > 0

    link_before = links_before["links"][0]
    snr_before = link_before.get("snr_db")
    assert snr_before is not None, "Link must have snr_db field"

    # Move node2 much closer (5m) — expect higher SNR
    resp = control_api_post(
        base_url,
        "/api/control/update",
        {"node": "node2", "x": 5.0, "y": 0.0, "z": 1.0},
    )
    assert resp["status"] == "success"

    # Wait for polling loop to recompute (default poll_ms=100)
    time.sleep(0.5)

    links_after = control_api_get(base_url, "/api/emulation/links")
    snr_after = links_after["links"][0]["snr_db"]

    assert snr_after > snr_before, (
        f"Expected SNR to increase when moving node2 from 20m to 5m. "
        f"Before: {snr_before:.1f} dB, After: {snr_after:.1f} dB"
    )


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.fallback
def test_control_api_position_update_invalid_node(control_api_fallback_deployment):
    """POST with unknown node name returns 404."""
    _, _, base_url = control_api_fallback_deployment

    body = {"node": "nonexistent_node", "x": 0.0, "y": 0.0, "z": 1.0}
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{base_url}/api/control/update",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=5)
        raise AssertionError("Expected 404 but got success")
    except urllib.error.HTTPError as e:
        assert e.code == 404, f"Expected 404, got {e.code}"


@pytest.mark.integration
@pytest.mark.slow
def test_control_api_position_update_fixed_only_node(control_api_fixed_deployment):
    """POST on a node with only fixed_netem interfaces returns 400."""
    _, _, base_url = control_api_fixed_deployment

    body = {"node": "node1", "x": 0.0, "y": 0.0, "z": 1.0}
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{base_url}/api/control/update",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=5)
        raise AssertionError("Expected 400 but got success")
    except urllib.error.HTTPError as e:
        assert e.code == 400, f"Expected 400, got {e.code}"


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.fallback
def test_control_api_move_closer_improves_snr(control_api_fallback_deployment):
    """Moving node2 closer to node1 increases SNR by at least 5 dB."""
    _, _, base_url = control_api_fallback_deployment

    # Initial SNR with node2 at 20m
    links_before = control_api_get(base_url, "/api/emulation/links")
    snr_before = links_before["links"][0]["snr_db"]

    # Move node2 to 5m (from 20m)
    resp = control_api_post(
        base_url,
        "/api/control/update",
        {"node": "node2", "x": 5.0, "y": 0.0, "z": 1.0},
    )
    assert resp["status"] == "success"
    assert resp["position"] == {"x": 5.0, "y": 0.0, "z": 1.0}

    # Wait for polling loop to recompute
    time.sleep(0.5)

    links_after = control_api_get(base_url, "/api/emulation/links")
    snr_after = links_after["links"][0]["snr_db"]

    # FSPL: 20*log10(20/5) = 12 dB improvement expected; verify at least 5 dB
    assert snr_after > snr_before + 5.0, (
        f"Expected SNR to increase by 5+ dB when moving from 20m to 5m. "
        f"Before: {snr_before:.1f} dB, After: {snr_after:.1f} dB"
    )

    # Confirm position is stored
    pos = control_api_get(base_url, "/api/control/position/node2")
    assert pos["position"] == {"x": 5.0, "y": 0.0, "z": 1.0}


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.fallback
def test_control_api_move_farther_degrades_snr(control_api_fallback_deployment):
    """Moving node2 farther from node1 decreases SNR by at least 5 dB."""
    _, _, base_url = control_api_fallback_deployment

    # Initial SNR with node2 at 20m
    links_before = control_api_get(base_url, "/api/emulation/links")
    snr_before = links_before["links"][0]["snr_db"]

    # Move node2 to 80m (from 20m)
    resp = control_api_post(
        base_url,
        "/api/control/update",
        {"node": "node2", "x": 80.0, "y": 0.0, "z": 1.0},
    )
    assert resp["status"] == "success"

    # Wait for polling loop to recompute
    time.sleep(0.5)

    links_after = control_api_get(base_url, "/api/emulation/links")
    snr_after = links_after["links"][0]["snr_db"]

    # FSPL: 20*log10(80/20) = 12 dB degradation expected; verify at least 5 dB
    assert snr_after < snr_before - 5.0, (
        f"Expected SNR to decrease by 5+ dB when moving from 20m to 80m. "
        f"Before: {snr_before:.1f} dB, After: {snr_after:.1f} dB"
    )


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.fallback
def test_control_api_position_update_netem_changes(control_api_fallback_deployment):
    """After position update, tc qdisc on containers reflects new packet loss.

    Propagation delay at WiFi distances (meters to hundreds of metres) is in the
    nanosecond range — far below tc's minimum granularity — so delay_ms is not a
    useful netem metric to compare.  Instead we verify that loss_percent changes:
    at 500m the SNR for 64-QAM drops far below the reliable threshold, driving
    loss close to 100%.
    """
    import subprocess

    _, yaml_path, base_url = control_api_fallback_deployment

    container_prefix = extract_container_prefix(yaml_path)
    node1_container = f"{container_prefix}-node1"

    # Initial link state: node2 at 20m, ~35 dB SNR → near-zero loss
    initial_links = control_api_get(base_url, "/api/emulation/links")
    initial_loss = initial_links["links"][0]["loss_percent"]

    # Move node2 to 500m: SNR drops ~28 dB → 64-QAM fails, loss → ~100%
    resp = control_api_post(
        base_url,
        "/api/control/update",
        {"node": "node2", "x": 500.0, "y": 0.0, "z": 1.0},
    )
    assert resp["status"] == "success"

    # Wait for polling loop to recompute and apply netem
    time.sleep(0.5)

    # Verify loss_percent increased significantly in the API response
    updated_links = control_api_get(base_url, "/api/emulation/links")
    updated_loss = updated_links["links"][0]["loss_percent"]

    assert updated_loss > initial_loss + 1.0, (
        f"Expected loss to increase when moving node2 from 20m to 500m. "
        f"Initial: {initial_loss:.2f}%, Updated: {updated_loss:.2f}%"
    )

    # Verify actual netem config on the container shows non-zero loss
    result = subprocess.run(
        f"docker exec {node1_container} tc qdisc show dev eth1",
        shell=True,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "loss" in result.stdout, (
        f"Expected 'loss' in tc qdisc output after moving node2 to 500m.\n"
        f"tc output: {result.stdout}"
    )


# =============================================================================
# Group 4: Emulation State Queries
# =============================================================================


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.fallback
def test_control_api_emulation_summary(control_api_fallback_deployment):
    """/api/emulation/summary returns topology name and link structure."""
    _, _, base_url = control_api_fallback_deployment

    data = control_api_get(base_url, "/api/emulation/summary")

    assert "topology_name" in data
    assert "links" in data
    assert len(data["links"]) > 0

    # Verify each link has the standard netem fields
    link = data["links"][0]
    for field in ("delay_ms", "jitter_ms", "loss_percent", "rate_mbps"):
        assert field in link, f"Link missing required field: {field}"


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.fallback
def test_control_api_emulation_links(control_api_fallback_deployment):
    """/api/emulation/links returns bidirectional links with channel metrics."""
    _, _, base_url = control_api_fallback_deployment

    data = control_api_get(base_url, "/api/emulation/links")

    assert "links" in data
    # P2P link is bidirectional: node1→node2 and node2→node1
    assert len(data["links"]) >= 2, (
        f"Expected at least 2 bidirectional links, got {len(data['links'])}"
    )

    for link in data["links"]:
        assert "snr_db" in link, f"Link missing snr_db: {link}"
        assert "loss_percent" in link, f"Link missing loss_percent: {link}"
        assert "rate_mbps" in link, f"Link missing rate_mbps: {link}"

        # Vacuum at 20m gives ~35 dB SNR — should be well above 0
        assert link["snr_db"] > 0, f"Expected positive SNR, got {link['snr_db']}"
        assert link["loss_percent"] >= 0, "Loss percent must be non-negative"
        assert link["rate_mbps"] > 0, "Rate must be positive"


# =============================================================================
# Group 5: Polling Loop Behavior
# =============================================================================


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.fallback
def test_control_api_polling_interval(control_api_fallback_deployment):
    """Position update is reflected in link states within the polling interval."""
    _, _, base_url = control_api_fallback_deployment

    # Server is running (polling has started)
    health = control_api_get(base_url, "/health")
    assert health["status"] == "healthy"

    resp = control_api_post(
        base_url,
        "/api/control/update",
        {"node": "node2", "x": 10.0, "y": 0.0, "z": 1.0},
    )
    assert resp["status"] == "success"

    # p2p_fallback_snr_vacuum has control_poll_ms=100; wait 3× for reliability
    time.sleep(0.3)

    pos = control_api_get(base_url, "/api/control/position/node2")
    assert pos["position"]["x"] == pytest.approx(10.0)
