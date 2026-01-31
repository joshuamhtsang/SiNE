"""
Tests for noise_figure_db schema validation.

Verifies that noise_figure_db can be configured at node and interface levels,
with proper defaults and validation.
"""

import pytest
from pydantic import ValidationError

from sine.config.schema import (
    InterfaceConfig,
    NetworkTopology,
    NodeConfig,
    Position,
    WirelessParams,
)


def test_default_noise_figure_interface_level():
    """Verify default noise_figure_db is 7.0 dB at interface level."""
    wireless = WirelessParams(
        position=Position(x=0, y=0, z=1),
        rf_power_dbm=20.0,
        frequency_ghz=5.18,
        bandwidth_mhz=80,
        antenna_pattern="hw_dipole",
        polarization="V",
        modulation="64qam",
        fec_type="ldpc",
        fec_code_rate=0.5,
    )
    assert wireless.noise_figure_db == 7.0


def test_default_noise_figure_node_level():
    """Verify default noise_figure_db is 7.0 dB at node level."""
    node = NodeConfig(
        kind="linux",
        image="alpine:latest",
    )
    assert node.noise_figure_db == 7.0


def test_custom_noise_figure_wifi6():
    """Test custom noise figure for high-performance WiFi 6 (6.0 dB)."""
    wireless = WirelessParams(
        position=Position(x=0, y=0, z=1),
        rf_power_dbm=20.0,
        frequency_ghz=5.18,
        bandwidth_mhz=80,
        noise_figure_db=6.0,
        antenna_pattern="hw_dipole",
        polarization="V",
        modulation="64qam",
        fec_type="ldpc",
        fec_code_rate=0.5,
    )
    assert wireless.noise_figure_db == 6.0


def test_custom_noise_figure_5g_bs():
    """Test custom noise figure for 5G base station (4.0 dB)."""
    wireless = WirelessParams(
        position=Position(x=0, y=0, z=1),
        rf_power_dbm=30.0,
        frequency_ghz=3.5,
        bandwidth_mhz=100,
        noise_figure_db=4.0,
        antenna_pattern="tr38901",
        polarization="V",
        modulation="64qam",
        fec_type="ldpc",
        fec_code_rate=0.667,
    )
    assert wireless.noise_figure_db == 4.0


def test_custom_noise_figure_cheap_iot():
    """Test custom noise figure for cheap IoT radio (10.0 dB)."""
    wireless = WirelessParams(
        position=Position(x=0, y=0, z=1),
        rf_power_dbm=14.0,
        frequency_ghz=0.915,
        bandwidth_mhz=20,
        noise_figure_db=10.0,
        antenna_pattern="dipole",
        polarization="V",
        modulation="qpsk",
        fec_type="ldpc",
        fec_code_rate=0.5,
    )
    assert wireless.noise_figure_db == 10.0


def test_noise_figure_validation_too_low():
    """Test that negative noise figure is rejected."""
    with pytest.raises(ValidationError) as excinfo:
        WirelessParams(
            position=Position(x=0, y=0, z=1),
            rf_power_dbm=20.0,
            frequency_ghz=5.18,
            bandwidth_mhz=80,
            noise_figure_db=-1.0,  # Invalid: negative
            antenna_pattern="hw_dipole",
            polarization="V",
            modulation="64qam",
            fec_type="ldpc",
            fec_code_rate=0.5,
        )
    assert "noise_figure_db" in str(excinfo.value)


def test_noise_figure_validation_too_high():
    """Test that noise figure > 20 dB is rejected."""
    with pytest.raises(ValidationError) as excinfo:
        WirelessParams(
            position=Position(x=0, y=0, z=1),
            rf_power_dbm=20.0,
            frequency_ghz=5.18,
            bandwidth_mhz=80,
            noise_figure_db=25.0,  # Invalid: > 20 dB
            antenna_pattern="hw_dipole",
            polarization="V",
            modulation="64qam",
            fec_type="ldpc",
            fec_code_rate=0.5,
        )
    assert "noise_figure_db" in str(excinfo.value)


def test_noise_figure_at_boundary_low():
    """Test noise figure at lower boundary (0.0 dB - theoretical ideal)."""
    wireless = WirelessParams(
        position=Position(x=0, y=0, z=1),
        rf_power_dbm=20.0,
        frequency_ghz=5.18,
        bandwidth_mhz=80,
        noise_figure_db=0.0,  # Boundary: theoretical ideal receiver
        antenna_pattern="hw_dipole",
        polarization="V",
        modulation="64qam",
        fec_type="ldpc",
        fec_code_rate=0.5,
    )
    assert wireless.noise_figure_db == 0.0


def test_noise_figure_at_boundary_high():
    """Test noise figure at upper boundary (20.0 dB - extremely poor receiver)."""
    wireless = WirelessParams(
        position=Position(x=0, y=0, z=1),
        rf_power_dbm=20.0,
        frequency_ghz=5.18,
        bandwidth_mhz=80,
        noise_figure_db=20.0,  # Boundary: extremely poor/broken receiver
        antenna_pattern="hw_dipole",
        polarization="V",
        modulation="64qam",
        fec_type="ldpc",
        fec_code_rate=0.5,
    )
    assert wireless.noise_figure_db == 20.0


def test_node_level_noise_figure():
    """Test node-level noise_figure_db configuration."""
    node = NodeConfig(
        kind="linux",
        image="alpine:latest",
        noise_figure_db=5.0,
    )
    assert node.noise_figure_db == 5.0


def test_node_level_boundary_values():
    """Test node-level noise_figure_db boundary validation."""
    # Valid: 0.0 dB
    node = NodeConfig(kind="linux", image="alpine:latest", noise_figure_db=0.0)
    assert node.noise_figure_db == 0.0

    # Valid: 20.0 dB
    node = NodeConfig(kind="linux", image="alpine:latest", noise_figure_db=20.0)
    assert node.noise_figure_db == 20.0

    # Invalid: negative
    with pytest.raises(ValidationError):
        NodeConfig(kind="linux", image="alpine:latest", noise_figure_db=-1.0)

    # Invalid: > 20 dB
    with pytest.raises(ValidationError):
        NodeConfig(kind="linux", image="alpine:latest", noise_figure_db=21.0)


def test_full_topology_with_custom_noise_figure():
    """Test complete topology with custom noise figure values."""
    topology_dict = {
        "name": "noise_figure_test",
        "topology": {
            "nodes": {
                "node1": {
                    "kind": "linux",
                    "image": "alpine:latest",
                    "noise_figure_db": 6.0,  # Node-level default
                    "interfaces": {
                        "eth1": {
                            "wireless": {
                                "position": {"x": 0, "y": 0, "z": 1},
                                "rf_power_dbm": 20.0,
                                "frequency_ghz": 5.18,
                                "bandwidth_mhz": 80,
                                "noise_figure_db": 7.0,  # Interface-level override
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

    topology = NetworkTopology(**topology_dict)

    # Verify node-level noise figure
    assert topology.topology.nodes["node1"].noise_figure_db == 6.0
    assert topology.topology.nodes["node2"].noise_figure_db == 7.0  # Default

    # Verify interface-level noise figure
    assert (
        topology.topology.nodes["node1"].interfaces["eth1"].wireless.noise_figure_db
        == 7.0
    )
    assert (
        topology.topology.nodes["node2"].interfaces["eth1"].wireless.noise_figure_db
        == 7.0
    )
