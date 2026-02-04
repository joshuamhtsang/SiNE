"""Unit tests for enable_sinr flag and is_active field in schema."""

import logging
from sine.config.schema import (
    NetworkTopology,
    TopologyDefinition,
    NodeConfig,
    InterfaceConfig,
    WirelessParams,
    CSMAConfig,
    TDMAConfig,
    SceneConfig,
)

logger = logging.getLogger(__name__)


def _create_test_nodes():
    """Helper to create standard test nodes for unit tests."""
    return {
        "node1": NodeConfig(
            kind="linux",
            image="alpine:latest",
            interfaces={
                "eth1": InterfaceConfig(
                    wireless=WirelessParams(
                        position={"x": 0.0, "y": 0.0, "z": 1.0},
                        frequency_ghz=5.18,
                        rf_power_dbm=20.0,
                        bandwidth_mhz=80.0,
                        antenna_pattern="hw_dipole",
                        polarization="V",
                        modulation="64qam",
                        fec_type="ldpc",
                        fec_code_rate=0.5,
                    )
                )
            },
        ),
        "node2": NodeConfig(
            kind="linux",
            image="alpine:latest",
            interfaces={
                "eth1": InterfaceConfig(
                    wireless=WirelessParams(
                        position={"x": 20.0, "y": 0.0, "z": 1.0},
                        frequency_ghz=5.18,
                        rf_power_dbm=20.0,
                        bandwidth_mhz=80.0,
                        antenna_pattern="hw_dipole",
                        polarization="V",
                        modulation="64qam",
                        fec_type="ldpc",
                        fec_code_rate=0.5,
                    )
                )
            },
        ),
    }


def test_enable_sinr_explicit_true():
    """Test enable_sinr=true with wireless interfaces."""
    network = NetworkTopology(
        name="test-sinr-enabled",
        topology=TopologyDefinition(
            enable_sinr=True,
            scene=SceneConfig(file="scenes/vacuum.xml"),
            nodes=_create_test_nodes(),
            links=[{"endpoints": ["node1:eth1", "node2:eth1"]}],
        ),
    )
    assert network.topology.enable_sinr is True


def test_enable_sinr_explicit_false():
    """Test enable_sinr=false (SNR-only mode)."""
    network = NetworkTopology(
        name="test-sinr-disabled",
        topology=TopologyDefinition(
            enable_sinr=False,
            scene=SceneConfig(file="scenes/vacuum.xml"),
            nodes=_create_test_nodes(),
            links=[{"endpoints": ["node1:eth1", "node2:eth1"]}],
        ),
    )
    assert network.topology.enable_sinr is False


def test_enable_sinr_default_false():
    """Test default value (false when not specified)."""
    network = NetworkTopology(
        name="test-sinr-default",
        topology=TopologyDefinition(
            scene=SceneConfig(file="scenes/vacuum.xml"),
            nodes=_create_test_nodes(),
            links=[{"endpoints": ["node1:eth1", "node2:eth1"]}],
        ),
    )
    assert network.topology.enable_sinr is False


def test_enable_sinr_false_with_csma_warns(caplog):
    """Test warning when CSMA configured with enable_sinr=false."""
    caplog.set_level(logging.WARNING)

    nodes = _create_test_nodes()
    # Add CSMA to node1
    nodes["node1"].interfaces["eth1"].wireless.csma = CSMAConfig(enabled=True)

    network = NetworkTopology(
        name="test-csma-no-sinr",
        topology=TopologyDefinition(
            enable_sinr=False,
            scene=SceneConfig(file="scenes/vacuum.xml"),
            nodes=nodes,
            links=[{"endpoints": ["node1:eth1", "node2:eth1"]}],
        ),
    )

    assert network.topology.enable_sinr is False
    # Verify warning was logged
    assert any(
        "MAC model" in record.message and "enable_sinr=false" in record.message
        for record in caplog.records
    )


def test_enable_sinr_false_with_tdma_warns(caplog):
    """Test warning when TDMA configured with enable_sinr=false."""
    caplog.set_level(logging.WARNING)

    nodes = _create_test_nodes()
    # Add TDMA to node1
    nodes["node1"].interfaces["eth1"].wireless.tdma = TDMAConfig(
        enabled=True,
        fixed_slot_map={"node1": [0, 1, 2]},
    )

    network = NetworkTopology(
        name="test-tdma-no-sinr",
        topology=TopologyDefinition(
            enable_sinr=False,
            scene=SceneConfig(file="scenes/vacuum.xml"),
            nodes=nodes,
            links=[{"endpoints": ["node1:eth1", "node2:eth1"]}],
        ),
    )

    assert network.topology.enable_sinr is False
    # Verify warning was logged
    assert any(
        "MAC model" in record.message and "enable_sinr=false" in record.message
        for record in caplog.records
    )


def test_is_active_field_default_true():
    """Test is_active field defaults to True."""
    wireless_params = WirelessParams(
        position={"x": 0.0, "y": 0.0, "z": 1.0},
        frequency_ghz=5.18,
        rf_power_dbm=20.0,
        bandwidth_mhz=80.0,
        antenna_pattern="hw_dipole",
        polarization="V",
        modulation="64qam",
        fec_type="ldpc",
        fec_code_rate=0.5,
    )
    assert wireless_params.is_active is True


def test_is_active_field_explicit_false():
    """Test is_active can be set to False."""
    wireless_params = WirelessParams(
        position={"x": 0.0, "y": 0.0, "z": 1.0},
        frequency_ghz=5.18,
        rf_power_dbm=20.0,
        bandwidth_mhz=80.0,
        antenna_pattern="hw_dipole",
        polarization="V",
        modulation="64qam",
        fec_type="ldpc",
        fec_code_rate=0.5,
        is_active=False,
    )
    assert wireless_params.is_active is False


def test_is_active_field_explicit_true():
    """Test is_active can be explicitly set to True."""
    wireless_params = WirelessParams(
        position={"x": 0.0, "y": 0.0, "z": 1.0},
        frequency_ghz=5.18,
        rf_power_dbm=20.0,
        bandwidth_mhz=80.0,
        antenna_pattern="hw_dipole",
        polarization="V",
        modulation="64qam",
        fec_type="ldpc",
        fec_code_rate=0.5,
        is_active=True,
    )
    assert wireless_params.is_active is True


def test_multi_radio_selective_disable():
    """Test multi-radio node with selective interface disable."""
    network = NetworkTopology(
        name="test-multi-radio",
        topology=TopologyDefinition(
            enable_sinr=True,
            scene=SceneConfig(file="scenes/vacuum.xml"),
            nodes={
                "dual_band_node": NodeConfig(
                    kind="linux",
                    image="alpine:latest",
                    interfaces={
                        "eth1": InterfaceConfig(
                            wireless=WirelessParams(
                                position={"x": 0.0, "y": 0.0, "z": 1.0},
                                frequency_ghz=5.18,
                                rf_power_dbm=20.0,
                                bandwidth_mhz=80.0,
                                antenna_pattern="hw_dipole",
                                polarization="V",
                                modulation="64qam",
                                fec_type="ldpc",
                                fec_code_rate=0.5,
                                is_active=True,  # 5 GHz active
                            )
                        ),
                        "eth2": InterfaceConfig(
                            wireless=WirelessParams(
                                position={"x": 0.0, "y": 0.0, "z": 1.0},
                                frequency_ghz=2.4,
                                rf_power_dbm=20.0,
                                bandwidth_mhz=20.0,
                                antenna_pattern="hw_dipole",
                                polarization="V",
                                modulation="64qam",
                                fec_type="ldpc",
                                fec_code_rate=0.5,
                                is_active=False,  # 2.4 GHz disabled
                            )
                        ),
                    },
                ),
                "node2": NodeConfig(
                    kind="linux",
                    image="alpine:latest",
                    interfaces={
                        "eth1": InterfaceConfig(
                            wireless=WirelessParams(
                                position={"x": 20.0, "y": 0.0, "z": 1.0},
                                frequency_ghz=5.18,
                                rf_power_dbm=20.0,
                                bandwidth_mhz=80.0,
                                antenna_pattern="hw_dipole",
                                polarization="V",
                                modulation="64qam",
                                fec_type="ldpc",
                                fec_code_rate=0.5,
                            )
                        )
                    },
                ),
            },
            links=[{"endpoints": ["dual_band_node:eth1", "node2:eth1"]}],
        ),
    )

    # Verify both interfaces configured correctly
    node = network.topology.nodes["dual_band_node"]
    assert node.interfaces["eth1"].wireless.is_active is True
    assert node.interfaces["eth1"].wireless.frequency_ghz == 5.18
    assert node.interfaces["eth2"].wireless.is_active is False
    assert node.interfaces["eth2"].wireless.frequency_ghz == 2.4


def test_inactive_tx_interface_validation():
    """Test validation error when TX interface is inactive.

    Note: This test is currently expected to pass (no error) because
    the validation for inactive TX interfaces has not been implemented yet.
    Once Step 1, Change 1.3 from the plan is implemented, this test should
    be updated to expect a ValueError.
    """
    # For now, this should succeed (no validation yet)
    network = NetworkTopology(
        name="test-inactive-tx",
        topology=TopologyDefinition(
            enable_sinr=True,
            scene=SceneConfig(file="scenes/vacuum.xml"),
            nodes={
                "node1": NodeConfig(
                    kind="linux",
                    image="alpine:latest",
                    interfaces={
                        "eth1": InterfaceConfig(
                            wireless=WirelessParams(
                                position={"x": 0.0, "y": 0.0, "z": 1.0},
                                frequency_ghz=5.18,
                                rf_power_dbm=20.0,
                                bandwidth_mhz=80.0,
                                antenna_pattern="hw_dipole",
                                polarization="V",
                                modulation="64qam",
                                fec_type="ldpc",
                                fec_code_rate=0.5,
                                is_active=False,  # TX is inactive!
                            )
                        )
                    },
                ),
                "node2": NodeConfig(
                    kind="linux",
                    image="alpine:latest",
                    interfaces={
                        "eth1": InterfaceConfig(
                            wireless=WirelessParams(
                                position={"x": 20.0, "y": 0.0, "z": 1.0},
                                frequency_ghz=5.18,
                                rf_power_dbm=20.0,
                                bandwidth_mhz=80.0,
                                antenna_pattern="hw_dipole",
                                polarization="V",
                                modulation="64qam",
                                fec_type="ldpc",
                                fec_code_rate=0.5,
                                is_active=True,
                            )
                        )
                    },
                ),
            },
            links=[{"endpoints": ["node1:eth1", "node2:eth1"]}],
        ),
    )

    # Verify network was created (validation not implemented yet)
    assert network.topology.nodes["node1"].interfaces["eth1"].wireless.is_active is False


def test_inactive_rx_interface_allowed():
    """Test that inactive RX interface is allowed (listen-only mode)."""
    # This should NOT raise an error - RX can be inactive
    network = NetworkTopology(
        name="test-inactive-rx",
        topology=TopologyDefinition(
            enable_sinr=True,
            scene=SceneConfig(file="scenes/vacuum.xml"),
            nodes={
                "node1": NodeConfig(
                    kind="linux",
                    image="alpine:latest",
                    interfaces={
                        "eth1": InterfaceConfig(
                            wireless=WirelessParams(
                                position={"x": 0.0, "y": 0.0, "z": 1.0},
                                frequency_ghz=5.18,
                                rf_power_dbm=20.0,
                                bandwidth_mhz=80.0,
                                antenna_pattern="hw_dipole",
                                polarization="V",
                                modulation="64qam",
                                fec_type="ldpc",
                                fec_code_rate=0.5,
                                is_active=True,  # TX is active
                            )
                        )
                    },
                ),
                "node2": NodeConfig(
                    kind="linux",
                    image="alpine:latest",
                    interfaces={
                        "eth1": InterfaceConfig(
                            wireless=WirelessParams(
                                position={"x": 20.0, "y": 0.0, "z": 1.0},
                                frequency_ghz=5.18,
                                rf_power_dbm=20.0,
                                bandwidth_mhz=80.0,
                                antenna_pattern="hw_dipole",
                                polarization="V",
                                modulation="64qam",
                                fec_type="ldpc",
                                fec_code_rate=0.5,
                                is_active=False,  # RX is inactive (listen-only)
                            )
                        )
                    },
                ),
            },
            links=[{"endpoints": ["node1:eth1", "node2:eth1"]}],
        ),
    )

    # Verify topology was created successfully
    assert network.topology.nodes["node1"].interfaces["eth1"].wireless.is_active is True
    assert network.topology.nodes["node2"].interfaces["eth1"].wireless.is_active is False
