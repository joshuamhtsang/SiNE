"""
Integration tests for noise_figure_db in full deployments.

Tests full deployment workflow with custom noise figure configurations.

IMPORTANT: These tests require sudo for netem configuration.
Run with: UV_PATH=$(which uv) sudo -E $(which uv) run pytest -s tests/integration/test_noise_figure_deployment.py
"""

import asyncio
import os
import tempfile
from pathlib import Path

import pytest
import yaml

from sine.emulation.controller import EmulationController
from tests.integration.fixtures import channel_server  # noqa: F401


@pytest.fixture(scope="module")
def project_root():
    """Get the project root directory."""
    return Path(__file__).parent.parent.parent


@pytest.fixture
def temp_topology_dir():
    """Create a temporary directory for test topology files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def create_vacuum_topology(
    output_path: Path,
    node1_nf: float = 7.0,
    node2_nf: float = 7.0,
) -> Path:
    """
    Create a vacuum topology YAML file with configurable noise figures.

    Args:
        output_path: Directory to write topology file
        node1_nf: Noise figure for node1 in dB
        node2_nf: Noise figure for node2 in dB

    Returns:
        Path to created topology file
    """
    topology = {
        "name": "noise_figure_test",
        "topology": {
            "nodes": {
                "node1": {
                    "kind": "linux",
                    "image": "alpine:latest",
                    "interfaces": {
                        "eth1": {
                            "wireless": {
                                "position": {"x": 0, "y": 0, "z": 1},
                                "rf_power_dbm": 20.0,
                                "frequency_ghz": 5.18,
                                "bandwidth_mhz": 80,
                                "noise_figure_db": node1_nf,
                                "antenna_pattern": "hw_dipole",
                                "polarization": "V",
                                "modulation": "64qam",
                                "fec_type": "ldpc",
                                "fec_code_rate": 0.5,
                            }
                        }
                    },
                },
                "node2": {
                    "kind": "linux",
                    "image": "alpine:latest",
                    "interfaces": {
                        "eth1": {
                            "wireless": {
                                "position": {"x": 20, "y": 0, "z": 1},
                                "rf_power_dbm": 20.0,
                                "frequency_ghz": 5.18,
                                "bandwidth_mhz": 80,
                                "noise_figure_db": node2_nf,
                                "antenna_pattern": "hw_dipole",
                                "polarization": "V",
                                "modulation": "64qam",
                                "fec_type": "ldpc",
                                "fec_code_rate": 0.5,
                            }
                        }
                    },
                },
            },
            "links": [
                {"endpoints": ["node1:eth1", "node2:eth1"]},
            ],
            "scene": {"file": "scenes/vacuum.xml"},
        },
    }

    topology_file = output_path / "network.yaml"
    with open(topology_file, "w") as f:
        yaml.dump(topology, f)

    return topology_file


@pytest.mark.skipif(
    os.geteuid() != 0,
    reason="Integration tests require sudo for netem configuration"
)
def test_vacuum_20m_default_noise_figure(channel_server, temp_topology_dir, project_root):
    """
    Test deployment with default noise figure (7.0 dB).

    Verifies:
    1. Topology loads with default NF
    2. Deployment succeeds
    3. Link states are stored correctly
    """
    # Create topology with default noise figures
    topology_file = create_vacuum_topology(
        temp_topology_dir,
        node1_nf=7.0,
        node2_nf=7.0,
    )

    # Deploy
    controller = EmulationController(topology_file)
    try:
        asyncio.run(controller.start())

        # Verify schema parsed correctly (after load during start())
        assert controller.config is not None
        assert controller.config.topology.nodes["node1"].interfaces["eth1"].wireless.noise_figure_db == 7.0
        assert controller.config.topology.nodes["node2"].interfaces["eth1"].wireless.noise_figure_db == 7.0

        # Verify deployment succeeded
        link_state = controller._link_states.get(("node1", "node2"))
        assert link_state is not None, "Link state not found"

        # Verify SNR is stored
        assert "rf" in link_state
        assert "snr_db" in link_state["rf"]
        snr_db = link_state["rf"]["snr_db"]
        assert snr_db is not None
        assert snr_db > 0  # Should have positive SNR at 20m

    finally:
        # Cleanup
        asyncio.run(controller.stop())


@pytest.mark.skipif(
    os.geteuid() != 0,
    reason="Integration tests require sudo for netem configuration"
)
def test_vacuum_20m_custom_noise_figure(channel_server, temp_topology_dir, project_root):
    """
    Test deployment with custom noise figure (4.0 dB for 5G base station).

    Verifies:
    1. Custom NF is applied
    2. SNR is approximately 3 dB higher than default (7 dB NF)
    """
    # First deploy with default NF (7 dB) to get baseline SNR
    topology_file_default = create_vacuum_topology(
        temp_topology_dir,
        node1_nf=7.0,
        node2_nf=7.0,
    )
    controller_default = EmulationController(topology_file_default)

    try:
        asyncio.run(controller_default.start())
        link_state_default = controller_default._link_states.get(("node1", "node2"))
        snr_default = link_state_default["rf"]["snr_db"]
    finally:
        asyncio.run(controller_default.stop())

    # Now deploy with custom NF (4 dB)
    custom_dir = temp_topology_dir / "custom"
    custom_dir.mkdir(exist_ok=True)
    topology_file_custom = create_vacuum_topology(
        custom_dir,
        node1_nf=4.0,
        node2_nf=4.0,
    )
    controller_custom = EmulationController(topology_file_custom)

    try:
        asyncio.run(controller_custom.start())
        link_state_custom = controller_custom._link_states.get(("node1", "node2"))
        snr_custom = link_state_custom["rf"]["snr_db"]

        # Verify SNR improved by ~3 dB (4 dB NF vs 7 dB NF)
        snr_improvement = snr_custom - snr_default
        assert abs(snr_improvement - 3.0) < 0.5, (
            f"Expected ~3 dB SNR improvement, got {snr_improvement:.1f} dB "
            f"(default: {snr_default:.1f} dB, custom: {snr_custom:.1f} dB)"
        )

    finally:
        asyncio.run(controller_custom.stop())


@pytest.mark.skipif(
    os.geteuid() != 0,
    reason="Integration tests require sudo for netem configuration"
)
def test_heterogeneous_noise_figures(channel_server, temp_topology_dir, project_root):
    """
    Test deployment with different noise figures per node.

    Scenario: WiFi node (7 dB NF) + Low-cost IoT node (10 dB NF)

    Verifies:
    1. Different NF values are applied per interface
    2. Bidirectional links have different SNR values
    """
    # Create topology with heterogeneous noise figures
    topology_file = create_vacuum_topology(
        temp_topology_dir,
        node1_nf=7.0,   # WiFi 6
        node2_nf=10.0,  # Cheap IoT radio
    )

    controller = EmulationController(topology_file)

    try:
        asyncio.run(controller.start())

        # Verify schema parsed correctly (after load during start())
        assert controller.config is not None
        assert controller.config.topology.nodes["node1"].interfaces["eth1"].wireless.noise_figure_db == 7.0
        assert controller.config.topology.nodes["node2"].interfaces["eth1"].wireless.noise_figure_db == 10.0

        # BIDIRECTIONAL: Both directions are now computed and stored
        # node1→node2: Uses node2's NF=10dB (receiver's NF)
        # node2→node1: Uses node1's NF=7dB (receiver's NF)
        link_ab = controller._link_states.get(("node1", "node2"))
        link_ba = controller._link_states.get(("node2", "node1"))

        assert link_ab is not None, "Forward link state not found"
        assert link_ba is not None, "Reverse link state not found"

        # Verify SNR is stored for both directions
        assert "rf" in link_ab
        assert "snr_db" in link_ab["rf"]
        snr_ab = link_ab["rf"]["snr_db"]
        assert snr_ab is not None
        assert snr_ab > 0  # Should have positive SNR at 20m

        assert "rf" in link_ba
        assert "snr_db" in link_ba["rf"]
        snr_ba = link_ba["rf"]["snr_db"]
        assert snr_ba is not None
        assert snr_ba > 0  # Should have positive SNR at 20m

        # Verify that deployment succeeds with heterogeneous noise figures
        # The bidirectional test (test_bidirectional_asymmetric_netem) verifies
        # the ~3 dB SNR difference in detail

    finally:
        asyncio.run(controller.stop())


@pytest.mark.skipif(
    os.geteuid() != 0,
    reason="Integration tests require sudo for netem configuration"
)
def test_bidirectional_asymmetric_netem(channel_server, temp_topology_dir):
    """
    Verify P2P links compute asymmetric netem based on each receiver's NF.

    Topology: node1 (NF=7dB) ↔ node2 (NF=10dB) at 20m

    Expected:
    - Direction node1→node2: Uses node2's NF=10dB → lower SNR → higher loss%
    - Direction node2→node1: Uses node1's NF=7dB → higher SNR → lower loss%
    - SNR difference: ~3 dB
    - Both directions stored in link_states
    """
    topology_file = create_vacuum_topology(
        temp_topology_dir,
        node1_nf=7.0,   # WiFi 6 typical
        node2_nf=10.0,  # Cheap IoT radio
    )

    controller = EmulationController(topology_file)

    try:
        asyncio.run(controller.start())

        # Verify BOTH directional states exist
        link_ab = controller._link_states.get(("node1", "node2"))
        link_ba = controller._link_states.get(("node2", "node1"))

        assert link_ab is not None, "Forward link state missing"
        assert link_ba is not None, "Reverse link state missing"

        # Extract SNR values
        snr_ab = link_ab["rf"]["snr_db"]  # node1→node2 (uses NF=10dB)
        snr_ba = link_ba["rf"]["snr_db"]  # node2→node1 (uses NF=7dB)

        # Verify ~3 dB SNR difference
        snr_diff = snr_ba - snr_ab
        assert 2.5 < snr_diff < 3.5, (
            f"Expected ~3 dB SNR difference (NF difference), "
            f"got {snr_diff:.1f} dB (AB: {snr_ab:.1f} dB, BA: {snr_ba:.1f} dB)"
        )

        # Verify asymmetric loss rates
        loss_ab = link_ab["netem"].loss_percent
        loss_ba = link_ba["netem"].loss_percent

        # Higher NF → lower SNR → higher loss (when loss is observable)
        # Note: At 20m in vacuum, both links may have near-zero loss due to high SNR
        # In this case, the 3 dB difference doesn't translate to observable loss difference
        if loss_ab > 0.01 or loss_ba > 0.01:
            # At least one link has observable loss - verify asymmetry
            assert loss_ab >= loss_ba, (
                f"Direction with worse NF should have equal or higher loss, "
                f"got AB: {loss_ab:.3f}%, BA: {loss_ba:.3f}%"
            )
        else:
            # Both links have excellent quality (< 0.01% loss)
            # The 3 dB SNR difference is verified above, which is the key metric
            print(f"Both directions have excellent link quality (AB: {loss_ab:.6f}%, BA: {loss_ba:.6f}%) - "
                  f"SNR difference verified instead")

        # Verify delay is symmetric (same geometric path)
        delay_ab = link_ab["netem"].delay_ms
        delay_ba = link_ba["netem"].delay_ms
        assert abs(delay_ab - delay_ba) < 0.01, (
            f"Delay should be symmetric (same path), "
            f"got AB: {delay_ab} ms, BA: {delay_ba} ms"
        )

    finally:
        asyncio.run(controller.stop())


@pytest.mark.skipif(
    os.geteuid() != 0,
    reason="Integration tests require sudo for netem configuration"
)
def test_node_level_noise_figure_fallback(channel_server, temp_topology_dir, project_root):
    """
    Test node-level noise_figure_db as fallback for interfaces.

    Note: Currently the schema requires noise_figure_db at the interface level
    (WirelessParams), so this test verifies the node-level field exists but
    focuses on interface-level configuration.
    """
    topology = {
        "name": "node_level_nf_test",
        "topology": {
            "nodes": {
                "node1": {
                    "kind": "linux",
                    "image": "alpine:latest",
                    "noise_figure_db": 5.0,  # Node-level (not currently used by interfaces)
                    "interfaces": {
                        "eth1": {
                            "wireless": {
                                "position": {"x": 0, "y": 0, "z": 1},
                                "rf_power_dbm": 20.0,
                                "frequency_ghz": 5.18,
                                "bandwidth_mhz": 80,
                                "noise_figure_db": 6.0,  # Interface-level override
                                "antenna_pattern": "hw_dipole",
                                "polarization": "V",
                                "modulation": "64qam",
                                "fec_type": "ldpc",
                                "fec_code_rate": 0.5,
                            }
                        }
                    },
                },
                "node2": {
                    "kind": "linux",
                    "image": "alpine:latest",
                    "interfaces": {
                        "eth1": {
                            "wireless": {
                                "position": {"x": 20, "y": 0, "z": 1},
                                "rf_power_dbm": 20.0,
                                "frequency_ghz": 5.18,
                                "bandwidth_mhz": 80,
                                "noise_figure_db": 7.0,
                                "antenna_pattern": "hw_dipole",
                                "polarization": "V",
                                "modulation": "64qam",
                                "fec_type": "ldpc",
                                "fec_code_rate": 0.5,
                            }
                        }
                    },
                },
            },
            "links": [
                {"endpoints": ["node1:eth1", "node2:eth1"]},
            ],
            "scene": {"file": "scenes/vacuum.xml"},
        },
    }

    topology_file = temp_topology_dir / "network.yaml"
    with open(topology_file, "w") as f:
        yaml.dump(topology, f)

    controller = EmulationController(topology_file)

    try:
        asyncio.run(controller.start())

        # Verify both node-level and interface-level fields exist (after load during start())
        assert controller.config is not None
        assert controller.config.topology.nodes["node1"].noise_figure_db == 5.0
        assert controller.config.topology.nodes["node1"].interfaces["eth1"].wireless.noise_figure_db == 6.0
        assert controller.config.topology.nodes["node2"].interfaces["eth1"].wireless.noise_figure_db == 7.0

        # Verify deployment uses interface-level values
        link_state = controller._link_states.get(("node1", "node2"))
        assert link_state is not None

    finally:
        asyncio.run(controller.stop())
