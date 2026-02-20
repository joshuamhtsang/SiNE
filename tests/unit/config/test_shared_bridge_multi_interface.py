"""Unit tests for shared bridge multi-interface schema validation.

Tests:
- get_bridge_interfaces() auto-discovery
- Validation with multi-interface nodes
- Co-channel same-node warning
- self_isolation_db parameter validation
- IP conflict detection across multiple interfaces
"""

import logging

import pytest
from pydantic import ValidationError

from sine.config.schema import (
    InterfaceConfig,
    NetworkTopology,
    NodeConfig,
    SceneConfig,
    SharedBridgeDomain,
    TopologyDefinition,
    WirelessParams,
)


def _make_wireless(
    x: float,
    y: float,
    z: float = 1.0,
    freq: float = 5.18,
    bw: float = 80.0,
) -> WirelessParams:
    """Create a WirelessParams with minimal required fields."""
    return WirelessParams(
        position={"x": x, "y": y, "z": z},
        frequency_ghz=freq,
        rf_power_dbm=20.0,
        bandwidth_mhz=bw,
        antenna_pattern="hw_dipole",
        polarization="V",
        modulation="64qam",
        fec_type="ldpc",
        fec_code_rate=0.5,
    )


def _make_iface(
    ip: str,
    x: float,
    y: float,
    freq: float = 5.18,
    bw: float = 80.0,
) -> InterfaceConfig:
    """Create an InterfaceConfig with IP and wireless params."""
    return InterfaceConfig(
        ip_address=ip,
        wireless=_make_wireless(x, y, freq=freq, bw=bw),
    )


# ── get_bridge_interfaces() tests ──


def test_get_bridge_interfaces_single_interface_per_node():
    """Single wireless interface per node returns one entry each."""
    topo = TopologyDefinition(
        scene=SceneConfig(file="scenes/vacuum.xml"),
        shared_bridge=SharedBridgeDomain(
            name="br0", nodes=["n1", "n2"],
        ),
        nodes={
            "n1": NodeConfig(interfaces={
                "eth1": _make_iface("10.0.0.1/24", 0, 0),
            }),
            "n2": NodeConfig(interfaces={
                "eth1": _make_iface("10.0.0.2/24", 10, 0),
            }),
        },
    )
    ifaces = topo.get_bridge_interfaces()
    assert ifaces == [("n1", "eth1"), ("n2", "eth1")]


def test_get_bridge_interfaces_multi_interface():
    """Multi-interface node returns all wireless interfaces."""
    topo = TopologyDefinition(
        scene=SceneConfig(file="scenes/vacuum.xml"),
        shared_bridge=SharedBridgeDomain(
            name="br0", nodes=["n1", "n2"],
        ),
        nodes={
            "n1": NodeConfig(interfaces={
                "eth1": _make_iface("10.0.0.1/24", 0, 0, freq=5.18),
                "eth2": _make_iface("10.0.1.1/24", 0, 0, freq=2.4, bw=20.0),
            }),
            "n2": NodeConfig(interfaces={
                "eth1": _make_iface("10.0.0.2/24", 10, 0, freq=5.18),
                "eth2": _make_iface("10.0.1.2/24", 10, 0, freq=2.4, bw=20.0),
            }),
        },
    )
    ifaces = topo.get_bridge_interfaces()
    assert len(ifaces) == 4
    assert ("n1", "eth1") in ifaces
    assert ("n1", "eth2") in ifaces
    assert ("n2", "eth1") in ifaces
    assert ("n2", "eth2") in ifaces


def test_get_bridge_interfaces_excludes_non_bridge_nodes():
    """Non-bridge nodes are not included."""
    topo = TopologyDefinition(
        scene=SceneConfig(file="scenes/vacuum.xml"),
        shared_bridge=SharedBridgeDomain(
            name="br0", nodes=["n1"],
        ),
        nodes={
            "n1": NodeConfig(interfaces={
                "eth1": _make_iface("10.0.0.1/24", 0, 0),
            }),
            "n2": NodeConfig(interfaces={
                "eth1": InterfaceConfig(
                    wireless=_make_wireless(10, 0),
                ),
            }),
        },
    )
    ifaces = topo.get_bridge_interfaces()
    assert ifaces == [("n1", "eth1")]


def test_get_bridge_interfaces_disabled_bridge_returns_empty():
    """Disabled bridge returns empty list."""
    topo = TopologyDefinition(
        scene=SceneConfig(file="scenes/vacuum.xml"),
        shared_bridge=SharedBridgeDomain(
            enabled=False, name="br0", nodes=["n1", "n2"],
        ),
        nodes={
            "n1": NodeConfig(interfaces={
                "eth1": _make_iface("10.0.0.1/24", 0, 0),
            }),
            "n2": NodeConfig(interfaces={
                "eth1": _make_iface("10.0.0.2/24", 10, 0),
            }),
        },
        links=[{"endpoints": ["n1:eth1", "n2:eth1"]}],
    )
    assert topo.get_bridge_interfaces() == []


# ── self_isolation_db parameter tests ──


def test_self_isolation_db_default():
    """Default self_isolation_db is 30.0 dB."""
    bridge = SharedBridgeDomain(name="br0", nodes=["n1"])
    assert bridge.self_isolation_db == 30.0


def test_self_isolation_db_custom():
    """Custom self_isolation_db within range."""
    bridge = SharedBridgeDomain(
        name="br0", nodes=["n1"], self_isolation_db=40.0,
    )
    assert bridge.self_isolation_db == 40.0


def test_self_isolation_db_min_max():
    """self_isolation_db at boundary values."""
    bridge_min = SharedBridgeDomain(
        name="br0", nodes=["n1"], self_isolation_db=0.0,
    )
    assert bridge_min.self_isolation_db == 0.0

    bridge_max = SharedBridgeDomain(
        name="br0", nodes=["n1"], self_isolation_db=60.0,
    )
    assert bridge_max.self_isolation_db == 60.0


def test_self_isolation_db_out_of_range():
    """self_isolation_db out of [0, 60] range raises error."""
    with pytest.raises(ValidationError):
        SharedBridgeDomain(
            name="br0", nodes=["n1"], self_isolation_db=-1.0,
        )
    with pytest.raises(ValidationError):
        SharedBridgeDomain(
            name="br0", nodes=["n1"], self_isolation_db=61.0,
        )


def test_interface_name_field_removed():
    """interface_name field no longer accepted (breaking change)."""
    with pytest.raises(ValidationError):
        SharedBridgeDomain(
            name="br0",
            nodes=["n1"],
            interface_name="eth1",  # type: ignore[call-arg]
        )


# ── Shared bridge validation tests ──


def test_bridge_node_must_have_wireless_interface():
    """Bridge node with no wireless interface raises error."""
    with pytest.raises(
        ValueError, match="no wireless interfaces"
    ):
        TopologyDefinition(
            scene=SceneConfig(file="scenes/vacuum.xml"),
            shared_bridge=SharedBridgeDomain(
                name="br0", nodes=["n1"],
            ),
            nodes={
                "n1": NodeConfig(interfaces={
                    "eth1": InterfaceConfig(
                        ip_address="10.0.0.1/24",
                        fixed_netem={
                            "delay_ms": 1.0,
                            "rate_mbps": 100.0,
                        },
                    ),
                }),
            },
        )


def test_bridge_wireless_iface_requires_ip():
    """Wireless interface on bridge must have ip_address."""
    with pytest.raises(ValueError, match="must have ip_address"):
        TopologyDefinition(
            scene=SceneConfig(file="scenes/vacuum.xml"),
            shared_bridge=SharedBridgeDomain(
                name="br0", nodes=["n1", "n2"],
            ),
            nodes={
                "n1": NodeConfig(interfaces={
                    "eth1": InterfaceConfig(
                        wireless=_make_wireless(0, 0),
                    ),
                }),
                "n2": NodeConfig(interfaces={
                    "eth1": _make_iface("10.0.0.2/24", 10, 0),
                }),
            },
        )


def test_bridge_ip_must_be_cidr():
    """IP address must be in CIDR notation."""
    with pytest.raises(ValueError, match="missing subnet mask"):
        TopologyDefinition(
            scene=SceneConfig(file="scenes/vacuum.xml"),
            shared_bridge=SharedBridgeDomain(
                name="br0", nodes=["n1"],
            ),
            nodes={
                "n1": NodeConfig(interfaces={
                    "eth1": InterfaceConfig(
                        ip_address="10.0.0.1",  # No /24
                        wireless=_make_wireless(0, 0),
                    ),
                }),
            },
        )


def test_bridge_ip_conflict_detected():
    """Duplicate IP addresses across bridge interfaces raise error."""
    with pytest.raises(ValueError, match="IP address conflict"):
        TopologyDefinition(
            scene=SceneConfig(file="scenes/vacuum.xml"),
            shared_bridge=SharedBridgeDomain(
                name="br0", nodes=["n1", "n2"],
            ),
            nodes={
                "n1": NodeConfig(interfaces={
                    "eth1": _make_iface("10.0.0.1/24", 0, 0),
                }),
                "n2": NodeConfig(interfaces={
                    "eth1": _make_iface("10.0.0.1/24", 10, 0),
                }),
            },
        )


def test_bridge_ip_conflict_multi_iface():
    """IP conflict on same node's multiple interfaces."""
    with pytest.raises(ValueError, match="IP address conflict"):
        TopologyDefinition(
            scene=SceneConfig(file="scenes/vacuum.xml"),
            shared_bridge=SharedBridgeDomain(
                name="br0", nodes=["n1"],
            ),
            nodes={
                "n1": NodeConfig(interfaces={
                    "eth1": _make_iface(
                        "10.0.0.1/24", 0, 0, freq=5.18,
                    ),
                    "eth2": _make_iface(
                        "10.0.0.1/24", 0, 0, freq=2.4, bw=20.0,
                    ),
                }),
            },
        )


def test_bridge_no_ip_conflict_different_ips():
    """Different IPs across interfaces is valid."""
    topo = TopologyDefinition(
        scene=SceneConfig(file="scenes/vacuum.xml"),
        shared_bridge=SharedBridgeDomain(
            name="br0", nodes=["n1", "n2"],
        ),
        nodes={
            "n1": NodeConfig(interfaces={
                "eth1": _make_iface("10.0.0.1/24", 0, 0, freq=5.18),
                "eth2": _make_iface(
                    "10.0.1.1/24", 0, 0, freq=2.4, bw=20.0,
                ),
            }),
            "n2": NodeConfig(interfaces={
                "eth1": _make_iface("10.0.0.2/24", 10, 0, freq=5.18),
                "eth2": _make_iface(
                    "10.0.1.2/24", 10, 0, freq=2.4, bw=20.0,
                ),
            }),
        },
    )
    assert len(topo.get_bridge_interfaces()) == 4


# ── Co-channel same-node warning tests ──


def test_same_node_co_channel_warns(caplog):
    """Two interfaces on same node with same frequency logs warning."""
    caplog.set_level(logging.WARNING)

    TopologyDefinition(
        scene=SceneConfig(file="scenes/vacuum.xml"),
        shared_bridge=SharedBridgeDomain(
            name="br0", nodes=["n1"],
        ),
        nodes={
            "n1": NodeConfig(interfaces={
                "eth1": _make_iface("10.0.0.1/24", 0, 0, freq=5.18),
                "eth2": _make_iface("10.0.0.2/24", 0, 0, freq=5.18),
            }),
        },
    )

    assert any(
        "same frequency" in r.message and "5.18" in r.message
        for r in caplog.records
    )


def test_same_node_different_freq_no_warning(caplog):
    """Two interfaces on same node with different frequencies: no warning."""
    caplog.set_level(logging.WARNING)

    TopologyDefinition(
        scene=SceneConfig(file="scenes/vacuum.xml"),
        shared_bridge=SharedBridgeDomain(
            name="br0", nodes=["n1"],
        ),
        nodes={
            "n1": NodeConfig(interfaces={
                "eth1": _make_iface("10.0.0.1/24", 0, 0, freq=5.18),
                "eth2": _make_iface(
                    "10.0.1.1/24", 0, 0, freq=2.4, bw=20.0,
                ),
            }),
        },
    )

    assert not any(
        "same frequency" in r.message for r in caplog.records
    )


# ── Full multi-interface topology test ──


def test_dual_band_topology_validates():
    """Full dual-band topology with shared bridge validates."""
    network = NetworkTopology(
        name="dual-band-test",
        topology=TopologyDefinition(
            enable_sinr=True,
            scene=SceneConfig(file="scenes/vacuum.xml"),
            shared_bridge=SharedBridgeDomain(
                name="manet-br0",
                nodes=["n1", "n2", "n3"],
                self_isolation_db=30.0,
            ),
            nodes={
                "n1": NodeConfig(
                    image="alpine:latest",
                    interfaces={
                        "eth1": _make_iface(
                            "192.168.100.1/24", 0, 0, freq=5.18,
                        ),
                        "eth2": _make_iface(
                            "192.168.200.1/24", 0, 0,
                            freq=2.4, bw=20.0,
                        ),
                    },
                ),
                "n2": NodeConfig(
                    image="alpine:latest",
                    interfaces={
                        "eth1": _make_iface(
                            "192.168.100.2/24", 20, 0, freq=5.18,
                        ),
                        "eth2": _make_iface(
                            "192.168.200.2/24", 20, 0,
                            freq=2.4, bw=20.0,
                        ),
                    },
                ),
                "n3": NodeConfig(
                    image="alpine:latest",
                    interfaces={
                        "eth1": _make_iface(
                            "192.168.100.3/24", 10, 17, freq=5.18,
                        ),
                        "eth2": _make_iface(
                            "192.168.200.3/24", 10, 17,
                            freq=2.4, bw=20.0,
                        ),
                    },
                ),
            },
        ),
    )

    # 3 nodes x 2 interfaces = 6 bridge interfaces
    ifaces = network.topology.get_bridge_interfaces()
    assert len(ifaces) == 6

    # All unique IPs
    ips = set()
    for node_name, iface_name in ifaces:
        ip = network.topology.nodes[node_name].interfaces[iface_name].ip_address
        ips.add(ip.split("/")[0])
    assert len(ips) == 6
