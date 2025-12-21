"""
Pydantic models for SiNE network topology configuration.

This module defines the schema for network.yaml files that describe:
- Network nodes (Docker containers) with wireless parameters
- Wireless links between nodes
- Scene configuration for ray tracing
- Channel server settings
"""

from enum import Enum
from pydantic import BaseModel, Field, ValidationInfo, field_validator


class ModulationType(str, Enum):
    """Supported digital modulation schemes."""

    BPSK = "bpsk"
    QPSK = "qpsk"
    QAM16 = "16qam"
    QAM64 = "64qam"
    QAM256 = "256qam"

    @property
    def bits_per_symbol(self) -> int:
        """Return number of bits per symbol for this modulation."""
        mapping = {
            ModulationType.BPSK: 1,
            ModulationType.QPSK: 2,
            ModulationType.QAM16: 4,
            ModulationType.QAM64: 6,
            ModulationType.QAM256: 8,
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

    x: float = Field(..., description="X coordinate in meters")
    y: float = Field(..., description="Y coordinate in meters")
    z: float = Field(default=1.0, description="Z coordinate in meters (height)")

    def as_tuple(self) -> tuple[float, float, float]:
        """Return position as (x, y, z) tuple."""
        return (self.x, self.y, self.z)


class WirelessParams(BaseModel):
    """Wireless link parameters for a node."""

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
    modulation: ModulationType = Field(default=ModulationType.QAM64)
    fec_type: FECType = Field(default=FECType.LDPC)
    fec_code_rate: float = Field(
        default=0.5, description="FEC code rate (k/n)", ge=0.0, le=1.0
    )
    position: Position

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


class NodeConfig(BaseModel):
    """
    Node definition extending Containerlab format with wireless parameters.

    A node represents a Docker container in the emulated network.
    """

    kind: str = Field(default="linux", description="Containerlab node kind")
    image: str = Field(default="alpine:latest", description="Docker image")
    cmd: str | None = Field(default=None, description="Container command to run")
    binds: list[str] | None = Field(default=None, description="Volume mounts")
    env: dict[str, str] | None = Field(default=None, description="Environment variables")
    wireless: WirelessParams | None = Field(
        default=None, description="Wireless parameters (if this node has a wireless interface)"
    )


class WirelessLink(BaseModel):
    """Definition of a wireless link between two nodes."""

    endpoints: tuple[str, str] = Field(
        ..., description="Tuple of (node1_name, node2_name)"
    )
    bandwidth_override_mbps: float | None = Field(
        default=None, description="Override computed bandwidth limit (Mbps)"
    )

    @field_validator("endpoints", mode="after")
    @classmethod
    def validate_endpoints(cls, v: tuple[str, str]) -> tuple[str, str]:
        """Ensure endpoints are different nodes."""
        if v[0] == v[1]:
            raise ValueError("Link endpoints must be different nodes")
        return v


class SceneConfig(BaseModel):
    """Ray tracing scene configuration."""

    file: str = Field(..., description="Path to Mitsuba XML scene file")


class TopologyDefinition(BaseModel):
    """Topology definition containing nodes, links, and scene."""

    defaults: dict | None = Field(default=None, description="Default node settings")
    kinds: dict[str, NodeConfig] | None = Field(
        default=None, description="Default settings per node kind"
    )
    nodes: dict[str, NodeConfig] = Field(..., description="Node definitions")
    wireless_links: list[WirelessLink] = Field(
        default_factory=list, description="Wireless links between nodes"
    )
    scene: SceneConfig = Field(default_factory=SceneConfig)
    channel_server: str = Field(
        default="http://localhost:8000", description="Channel computation server URL"
    )
    mobility_poll_ms: int = Field(
        default=100,
        description="Mobility polling interval in milliseconds",
        ge=10,
        le=10000,
    )

    @field_validator("wireless_links", mode="after")
    @classmethod
    def validate_link_nodes_exist(
        cls, v: list[WirelessLink], info: ValidationInfo
    ) -> list[WirelessLink]:
        """Ensure all link endpoints reference existing nodes."""
        nodes = info.data.get("nodes", {})
        for link in v:
            for endpoint in link.endpoints:
                if endpoint not in nodes:
                    raise ValueError(
                        f"Link endpoint '{endpoint}' not found in nodes"
                    )
        return v


class NetworkTopology(BaseModel):
    """Root topology definition for network.yaml files."""

    name: str = Field(..., description="Topology name")
    prefix: str | None = Field(
        default=None, description="Prefix for container names (defaults to 'clab')"
    )
    topology: TopologyDefinition

    @property
    def container_prefix(self) -> str:
        """Return the effective container name prefix."""
        return self.prefix or "clab"
