"""
Pydantic models for SiNE network topology configuration.

This module defines the schema for network.yaml files that describe:
- Network nodes (Docker containers) with wireless parameters
- Wireless links between nodes
- Scene configuration for ray tracing
- Channel server settings
"""

from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator


class ModulationType(str, Enum):
    """Supported digital modulation schemes."""

    BPSK = "bpsk"
    QPSK = "qpsk"
    QAM16 = "16qam"
    QAM64 = "64qam"
    QAM256 = "256qam"
    QAM1024 = "1024qam"  # WiFi 6 support

    @property
    def bits_per_symbol(self) -> int:
        """Return number of bits per symbol for this modulation."""
        mapping = {
            ModulationType.BPSK: 1,
            ModulationType.QPSK: 2,
            ModulationType.QAM16: 4,
            ModulationType.QAM64: 6,
            ModulationType.QAM256: 8,
            ModulationType.QAM1024: 10,
        }
        return mapping[self]


class FECType(str, Enum):
    """Supported Forward Error Correction schemes."""

    NONE = "none"
    LDPC = "ldpc"
    POLAR = "polar"
    TURBO = "turbo"


class AntennaPattern(str, Enum):
    """Supported antenna radiation patterns (Sionna v1.2.1 naming)."""

    ISO = "iso"  # Isotropic pattern
    DIPOLE = "dipole"  # Dipole antenna
    HW_DIPOLE = "hw_dipole"  # Half-wave dipole
    TR38901 = "tr38901"  # 3GPP TR 38.901 antenna model


class Polarization(str, Enum):
    """Antenna polarization options (Sionna v1.2.1)."""

    V = "V"  # Vertical
    H = "H"  # Horizontal
    VH = "VH"  # Dual vertical-horizontal
    CROSS = "cross"  # Cross-polarized


class Position(BaseModel):
    """3D position coordinates in meters."""

    model_config = ConfigDict(extra="forbid")

    x: float = Field(..., description="X coordinate in meters")
    y: float = Field(..., description="Y coordinate in meters")
    z: float = Field(default=1.0, description="Z coordinate in meters (height)")

    def as_tuple(self) -> tuple[float, float, float]:
        """Return position as (x, y, z) tuple."""
        return (self.x, self.y, self.z)


class WirelessParams(BaseModel):
    """Wireless link parameters for a node.

    Configuration modes:
    1. Adaptive MCS: Set mcs_table path, modulation/fec_type/fec_code_rate are ignored
    2. Fixed modulation: Set modulation, fec_type, fec_code_rate explicitly

    One of these modes must be configured - no defaults are provided.
    """

    model_config = ConfigDict(extra="forbid")

    rf_power_dbm: float = Field(
        default=20.0, description="Transmit power in dBm", ge=-30.0, le=40.0
    )
    antenna_pattern: AntennaPattern = Field(default=AntennaPattern.ISO)
    polarization: Polarization = Field(default=Polarization.V)
    antenna_gain_dbi: float = Field(default=0.0, description="Antenna gain in dBi")
    frequency_ghz: float = Field(
        default=5.18, description="RF frequency in GHz", gt=0.0, le=100.0
    )
    bandwidth_mhz: float = Field(
        default=20.0, description="Channel bandwidth in MHz", gt=0.0, le=1000.0
    )

    # MCS table for adaptive modulation (takes precedence over fixed params)
    mcs_table: str | None = Field(
        default=None, description="Path to MCS table CSV file for adaptive MCS selection"
    )
    mcs_hysteresis_db: float = Field(
        default=2.0,
        description="SNR hysteresis in dB to prevent rapid MCS switching",
        ge=0.0,
        le=10.0,
    )

    # Fixed modulation parameters (used when mcs_table is not set)
    modulation: ModulationType | None = Field(
        default=None, description="Fixed modulation scheme (ignored if mcs_table is set)"
    )
    fec_type: FECType | None = Field(
        default=None, description="Fixed FEC type (ignored if mcs_table is set)"
    )
    fec_code_rate: float | None = Field(
        default=None, description="Fixed FEC code rate (ignored if mcs_table is set)", ge=0.0, le=1.0
    )

    position: Position

    @model_validator(mode="after")
    def validate_mcs_or_fixed(self) -> "WirelessParams":
        """Ensure either MCS table or fixed modulation/fec is specified."""
        has_mcs_table = self.mcs_table is not None
        has_fixed = (
            self.modulation is not None
            and self.fec_type is not None
            and self.fec_code_rate is not None
        )

        if not has_mcs_table and not has_fixed:
            raise ValueError(
                "Wireless interface requires either 'mcs_table' or all of "
                "'modulation', 'fec_type', 'fec_code_rate' to be specified"
            )

        return self

    @property
    def uses_adaptive_mcs(self) -> bool:
        """Return True if adaptive MCS selection is enabled."""
        return self.mcs_table is not None

    @field_validator("frequency_ghz", mode="after")
    @classmethod
    def validate_wifi6_frequency(cls, v: float) -> float:
        """Validate frequency is in WiFi6/6E bands (warning only)."""
        # WiFi6 2.4GHz: 2.412-2.484 GHz
        # WiFi6 5GHz: 5.15-5.85 GHz
        # WiFi6E 6GHz: 5.925-7.125 GHz
        valid_ranges = [(2.4, 2.5), (5.15, 5.85), (5.925, 7.125)]
        in_wifi_band = any(low <= v <= high for low, high in valid_ranges)
        if not in_wifi_band:
            # Allow non-WiFi frequencies but could log a warning
            pass
        return v

    @property
    def frequency_hz(self) -> float:
        """Return frequency in Hz."""
        return self.frequency_ghz * 1e9

    @property
    def bandwidth_hz(self) -> float:
        """Return bandwidth in Hz."""
        return self.bandwidth_mhz * 1e6


class FixedNetemParams(BaseModel):
    """Fixed netem parameters for static link emulation.

    Use this instead of wireless params when you want to specify
    link characteristics directly without ray tracing computation.
    """

    model_config = ConfigDict(extra="forbid")

    delay_ms: float = Field(
        default=0.0, description="One-way delay in milliseconds", ge=0.0
    )
    jitter_ms: float = Field(
        default=0.0, description="Delay variation in milliseconds", ge=0.0
    )
    loss_percent: float = Field(
        default=0.0, description="Packet loss percentage", ge=0.0, le=100.0
    )
    rate_mbps: float = Field(
        default=1000.0, description="Bandwidth limit in Mbps", gt=0.0
    )
    correlation_percent: float = Field(
        default=25.0, description="Delay correlation for realistic jitter", ge=0.0, le=100.0
    )


class InterfaceConfig(BaseModel):
    """Configuration for a single network interface.

    Each interface must have exactly one of:
    - wireless: Wireless parameters (computed via ray tracing)
    - fixed_netem: Fixed netem parameters (applied directly)
    """

    model_config = ConfigDict(extra="forbid")

    wireless: WirelessParams | None = Field(
        default=None, description="Wireless parameters (computed via ray tracing)"
    )
    fixed_netem: FixedNetemParams | None = Field(
        default=None, description="Fixed netem parameters (applied directly)"
    )

    @model_validator(mode="after")
    def validate_exactly_one(self) -> "InterfaceConfig":
        """Ensure exactly one of wireless or fixed_netem is set."""
        if self.wireless and self.fixed_netem:
            raise ValueError("Interface cannot have both 'wireless' and 'fixed_netem'")
        if not self.wireless and not self.fixed_netem:
            raise ValueError("Interface must have either 'wireless' or 'fixed_netem'")
        return self

    @property
    def is_wireless(self) -> bool:
        """Return True if this interface uses wireless params."""
        return self.wireless is not None


class NodeConfig(BaseModel):
    """
    Node definition extending Containerlab format with interface parameters.

    A node represents a Docker container in the emulated network.
    Interfaces are configured per-interface with either wireless or fixed_netem params.
    """

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(default="linux", description="Containerlab node kind")
    image: str = Field(default="alpine:latest", description="Docker image")
    cmd: str | None = Field(default=None, description="Container command to run")
    binds: list[str] | None = Field(default=None, description="Volume mounts")
    env: dict[str, str] | None = Field(default=None, description="Environment variables")
    interfaces: dict[str, InterfaceConfig] | None = Field(
        default=None, description="Interface configurations (eth1, eth2, etc.)"
    )


def parse_endpoint(endpoint: str) -> tuple[str, str]:
    """
    Parse an endpoint string into (node_name, interface).

    Required format: "node:interface" (e.g., "node1:eth1")

    Args:
        endpoint: Endpoint string like "node1:eth1"

    Returns:
        Tuple of (node_name, interface)

    Raises:
        ValueError: If endpoint doesn't include interface specification
    """
    if ":" not in endpoint:
        raise ValueError(
            f"Endpoint '{endpoint}' must specify interface (e.g., '{endpoint}:eth1')"
        )
    parts = endpoint.split(":", 1)
    return (parts[0], parts[1])


class Link(BaseModel):
    """
    Definition of a link between two node interfaces.

    Endpoints must be specified in "node:interface" format.
    The link type (wireless or fixed_netem) is determined by the
    interface configurations on each node.

    Example:
        links:
          - endpoints: [node1:eth1, node2:eth1]
          - endpoints: [node1:eth2, node3:eth1]
    """

    model_config = ConfigDict(extra="forbid")

    endpoints: tuple[str, str] = Field(
        ...,
        description="Tuple of endpoints in 'node:interface' format (e.g., 'node1:eth1')",
    )

    @field_validator("endpoints", mode="after")
    @classmethod
    def validate_endpoints(cls, v: tuple[str, str]) -> tuple[str, str]:
        """Ensure endpoints are different nodes."""
        node1, _ = parse_endpoint(v[0])
        node2, _ = parse_endpoint(v[1])
        if node1 == node2:
            raise ValueError("Link endpoints must be different nodes")
        return v

    def get_node_names(self) -> tuple[str, str]:
        """Return just the node names (without interface suffixes)."""
        node1, _ = parse_endpoint(self.endpoints[0])
        node2, _ = parse_endpoint(self.endpoints[1])
        return (node1, node2)

    def get_interfaces(self) -> tuple[str, str]:
        """Return the interface specifications."""
        _, iface1 = parse_endpoint(self.endpoints[0])
        _, iface2 = parse_endpoint(self.endpoints[1])
        return (iface1, iface2)


# Backwards compatibility alias
WirelessLink = Link


class SceneConfig(BaseModel):
    """Ray tracing scene configuration."""

    model_config = ConfigDict(extra="forbid")

    file: str = Field(..., description="Path to Mitsuba XML scene file")


class TopologyDefinition(BaseModel):
    """Topology definition containing nodes, links, and scene."""

    model_config = ConfigDict(extra="forbid")

    defaults: dict | None = Field(default=None, description="Default node settings")
    kinds: dict[str, NodeConfig] | None = Field(
        default=None, description="Default settings per node kind"
    )
    nodes: dict[str, NodeConfig] = Field(..., description="Node definitions")
    links: list[Link] = Field(
        default_factory=list, description="Links between node interfaces"
    )
    scene: SceneConfig | None = Field(
        default=None, description="Ray tracing scene (required for wireless links)"
    )
    channel_server: str = Field(
        default="http://localhost:8000", description="Channel computation server URL"
    )
    mobility_poll_ms: int = Field(
        default=100,
        description="Mobility polling interval in milliseconds",
        ge=10,
        le=10000,
    )

    @field_validator("links", mode="after")
    @classmethod
    def validate_links(
        cls, v: list[Link], info: ValidationInfo
    ) -> list[Link]:
        """Validate links: nodes exist, interfaces configured, types match."""
        nodes = info.data.get("nodes", {})

        # Track interface assignments to detect conflicts
        # Format: {(node, interface): link_index}
        interface_assignments: dict[tuple[str, str], int] = {}

        for link_idx, link in enumerate(v):
            node_names = link.get_node_names()
            interfaces = link.get_interfaces()

            endpoint_types: list[bool] = []  # True = wireless, False = fixed

            for i, (node_name, interface) in enumerate(zip(node_names, interfaces)):
                # Check node exists
                if node_name not in nodes:
                    raise ValueError(
                        f"Link endpoint '{link.endpoints[i]}': "
                        f"node '{node_name}' not found in nodes"
                    )

                node = nodes[node_name]

                # Check interface is configured on node
                if not node.interfaces or interface not in node.interfaces:
                    raise ValueError(
                        f"Link endpoint '{link.endpoints[i]}': "
                        f"interface '{interface}' not configured on node '{node_name}'"
                    )

                # Track interface type
                endpoint_types.append(node.interfaces[interface].is_wireless)

                # Check for interface conflicts
                key = (node_name, interface)
                if key in interface_assignments:
                    prev_link_idx = interface_assignments[key]
                    raise ValueError(
                        f"Interface conflict: {node_name}:{interface} is used by "
                        f"multiple links (link {prev_link_idx + 1} and link {link_idx + 1})"
                    )
                interface_assignments[key] = link_idx

            # Ensure both endpoints are same type
            if len(endpoint_types) == 2 and endpoint_types[0] != endpoint_types[1]:
                raise ValueError(
                    f"Link {link.endpoints}: endpoints must be same type "
                    f"(both wireless or both fixed_netem)"
                )

        return v

    @model_validator(mode="after")
    def validate_scene_for_wireless(self) -> "TopologyDefinition":
        """Ensure scene is configured if any wireless links exist."""
        has_wireless_links = False

        for link in self.links:
            node1, iface1 = parse_endpoint(link.endpoints[0])
            node = self.nodes.get(node1)
            if node and node.interfaces and iface1 in node.interfaces:
                if node.interfaces[iface1].is_wireless:
                    has_wireless_links = True
                    break

        if has_wireless_links and not self.scene:
            raise ValueError("Scene configuration required when using wireless links")

        return self


class NetworkTopology(BaseModel):
    """Root topology definition for network.yaml files."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Topology name")
    prefix: str | None = Field(
        default=None, description="Prefix for container names (defaults to 'clab')"
    )
    topology: TopologyDefinition

    @property
    def container_prefix(self) -> str:
        """Return the effective container name prefix."""
        return self.prefix or "clab"
