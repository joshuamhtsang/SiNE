"""
Interference engine for computing multi-transmitter interference using PathSolver.

This module implements Phase 0 of the SINR plan: PathSolver-based interference
computation for MANET topologies. It computes interference from multiple transmitters
at a receiver position using Sionna's PathSolver iteratively.

Key insight: Use PathSolver for point-to-point interference links, not RadioMapSolver
(which is designed for 2D/3D coverage grids).
"""

from dataclasses import dataclass
from typing import Optional
import logging
import numpy as np

logger = logging.getLogger(__name__)

# Check for Sionna availability
try:
    from sine.channel.sionna_engine import SionnaEngine, PathResult, is_sionna_available
    _sionna_available = is_sionna_available()
except ImportError:
    _sionna_available = False


@dataclass
class TransmitterInfo:
    """Information about a transmitter for interference computation."""

    node_name: str
    position: tuple[float, float, float]  # (x, y, z) in meters
    tx_power_dbm: float
    antenna_gain_dbi: float
    frequency_hz: float
    bandwidth_hz: float = 80e6  # Default 80 MHz for WiFi 6


@dataclass
class InterferenceTerm:
    """Single interference contribution from one transmitter."""

    source: str  # Node name of interferer
    power_dbm: float  # Interference power at receiver (includes TX/RX gains, path loss, ACLR)
    frequency_hz: float  # Interferer frequency
    frequency_separation_hz: float = 0.0  # Absolute frequency separation from receiver
    aclr_db: float = 0.0  # ACLR rejection applied (dB)


@dataclass
class InterferenceResult:
    """Aggregated interference result for a receiver."""

    receiver_node: str
    interference_terms: list[InterferenceTerm]
    total_interference_dbm: float  # Aggregated in linear domain, converted to dB
    num_interferers: int


def calculate_aclr_db(
    freq_separation_hz: float,
    tx_bandwidth_hz: float = 80e6,
    rx_bandwidth_hz: float = 80e6,
) -> float:
    """
    Calculate ACLR based on IEEE 802.11ax-2021 spectral mask.

    Accounts for channel overlap by checking if TX and RX bands overlap.
    Uses bandwidth-dependent thresholds for accurate channel overlap detection.

    Args:
        freq_separation_hz: Absolute frequency separation (center freq)
        tx_bandwidth_hz: Transmitter channel bandwidth (default 80 MHz)
        rx_bandwidth_hz: Receiver channel bandwidth (default 80 MHz)

    Returns:
        ACLR rejection in dB (how much to subtract from interference power)

    Examples:
        >>> # Co-channel (overlapping channels, 80 MHz BW)
        >>> calculate_aclr_db(20e6, 80e6, 80e6)
        0.0

        >>> # Transition band (60 MHz separation, 80 MHz BW)
        >>> calculate_aclr_db(60e6, 80e6, 80e6)
        24.0

        >>> # 1st adjacent (100 MHz separation, 80 MHz BW)
        >>> calculate_aclr_db(100e6, 80e6, 80e6)
        40.0

        >>> # Orthogonal (200 MHz separation, 80 MHz BW)
        >>> calculate_aclr_db(200e6, 80e6, 80e6)
        45.0
    """
    freq_sep_mhz = abs(freq_separation_hz) / 1e6
    tx_bw_mhz = tx_bandwidth_hz / 1e6
    rx_bw_mhz = rx_bandwidth_hz / 1e6

    # Use TX bandwidth to determine spectral mask thresholds (transmitter-based ACLR)
    half_tx_bw = tx_bw_mhz / 2.0

    # Check for channel overlap (co-channel interference)
    # Channels overlap if separation < half of larger bandwidth
    # This is a simplified model: actual overlap depends on both bandwidths
    # For practical purposes, use TX bandwidth (spectral mask is transmitter property)
    if freq_sep_mhz < half_tx_bw:
        # Channels overlap → co-channel interference (0 dB ACLR)
        return 0.0

    # Non-overlapping channels: Apply IEEE 802.11ax spectral mask
    # Values based on 802.11ax-2021 Table 27-20 (transmit spectrum mask)
    # Thresholds are based on TX bandwidth

    if freq_sep_mhz < half_tx_bw + 40:
        # Transition band: BW/2 to BW/2+40 MHz
        # For 80 MHz BW: 40-80 MHz separation
        # Linear interpolation from -20 to -28 dB
        excess = freq_sep_mhz - half_tx_bw
        return 20.0 + (excess / 40.0) * 8.0
    elif freq_sep_mhz < half_tx_bw + 80:
        # 1st adjacent: BW/2+40 to BW/2+80 MHz
        # For 80 MHz BW: 80-120 MHz separation
        return 40.0
    else:
        # Orthogonal: > BW/2+80 MHz
        # For 80 MHz BW: >120 MHz separation
        return 45.0


class InterferenceEngine:
    """
    Compute interference from multiple transmitters using PathSolver.

    This engine uses Sionna's PathSolver iteratively for each interferer to compute
    interference power at receiver positions. This provides accurate per-link
    interference calculation without the overhead of RadioMapSolver's grid-based approach.

    Usage:
        engine = InterferenceEngine()
        engine.load_scene("scene.xml", frequency_hz=5.18e9)

        interferers = [
            TransmitterInfo("node2", (10, 0, 1), 20.0, 2.15, 5.18e9),
            TransmitterInfo("node3", (5, 8.66, 1), 20.0, 2.15, 5.18e9),
        ]

        result = engine.compute_interference_at_receiver(
            rx_position=(0, 0, 1),
            rx_antenna_gain_dbi=2.15,
            interferers=interferers,
            active_states={"node2": True, "node3": True}
        )
    """

    def __init__(self):
        """Initialize interference engine."""
        if not _sionna_available:
            raise ImportError(
                "Sionna is required for InterferenceEngine. "
                "Install with: pip install sine[gpu]"
            )

        self._engine: Optional[SionnaEngine] = None
        self._path_cache: dict[tuple[tuple[float, float, float], tuple[float, float, float]], PathResult] = {}
        self._scene_loaded = False
        self._frequency_hz = 5.18e9
        self._bandwidth_hz = 80e6

    def load_scene(
        self,
        scene_path: Optional[str] = None,
        frequency_hz: float = 5.18e9,
        bandwidth_hz: float = 80e6,
    ) -> None:
        """
        Load ray tracing scene for interference computation.

        Args:
            scene_path: Path to Mitsuba XML scene file, or None for empty scene
            frequency_hz: RF frequency for simulation
            bandwidth_hz: Channel bandwidth
        """
        self._engine = SionnaEngine()
        self._engine.load_scene(scene_path, frequency_hz, bandwidth_hz)
        self._scene_loaded = True
        self._frequency_hz = frequency_hz
        self._bandwidth_hz = bandwidth_hz
        self._path_cache.clear()

        logger.info(f"InterferenceEngine: loaded scene at {frequency_hz/1e9:.3f} GHz")

    def compute_interference_at_receiver(
        self,
        rx_position: tuple[float, float, float],
        rx_antenna_gain_dbi: float,
        rx_node: str,
        interferers: list[TransmitterInfo],
        active_states: Optional[dict[str, bool]] = None,
        rx_frequency_hz: float = 5.18e9,
        rx_bandwidth_hz: float = 80e6,
    ) -> InterferenceResult:
        """
        Compute interference from all active interferers at RX position.

        Uses PathSolver iteratively for each interferer to compute interference power.
        Applies ACLR (Adjacent-Channel Leakage Ratio) based on frequency separation.
        Filters out orthogonal interferers (>2× max bandwidth separation).
        Aggregates interference in linear domain (power sum).

        Args:
            rx_position: Receiver position (x, y, z) in meters
            rx_antenna_gain_dbi: Receiver antenna gain in dBi
            rx_node: Receiver node name (for logging)
            interferers: List of potential interferers
            active_states: Dict of {node_name: is_transmitting}. If None, all active.
            rx_frequency_hz: Receiver center frequency in Hz (for ACLR calculation)
            rx_bandwidth_hz: Receiver channel bandwidth in Hz (for ACLR calculation)

        Returns:
            InterferenceResult with individual and aggregated interference terms
        """
        if not self._scene_loaded:
            raise RuntimeError("Scene must be loaded before computing interference")

        if active_states is None:
            active_states = {i.node_name: True for i in interferers}

        interference_terms = []
        total_interference_linear = 0.0

        for interferer in interferers:
            # Skip inactive interferers
            if not active_states.get(interferer.node_name, True):
                logger.debug("Skipping inactive interferer: %s", interferer.node_name)
                continue

            # Calculate frequency separation for ACLR
            freq_separation = abs(interferer.frequency_hz - rx_frequency_hz)

            # Skip orthogonal interferers (> half_tx_bw + 80 MHz → 45 dB ACLR, negligible)
            # This threshold matches where calculate_aclr_db returns 45 dB
            half_tx_bw_hz = interferer.bandwidth_hz / 2.0
            orthogonal_threshold_hz = half_tx_bw_hz + 80e6  # 80 MHz from IEEE 802.11ax
            if freq_separation > orthogonal_threshold_hz:
                logger.debug(
                    "Skipping orthogonal interferer %s: %.1f MHz separation > %.1f MHz threshold",
                    interferer.node_name,
                    freq_separation / 1e6,
                    orthogonal_threshold_hz / 1e6,
                )
                continue

            # Calculate ACLR based on frequency separation and bandwidths
            aclr_db = calculate_aclr_db(
                freq_separation,
                tx_bandwidth_hz=interferer.bandwidth_hz,
                rx_bandwidth_hz=rx_bandwidth_hz,
            )

            # Check cache for this TX→RX path
            cache_key = (interferer.position, rx_position)

            if cache_key in self._path_cache:
                path_result = self._path_cache[cache_key]
                logger.debug("Using cached path for %s→%s", interferer.node_name, rx_node)
            else:
                # Compute path from interferer to receiver using PathSolver
                path_result = self._compute_interference_path(
                    interferer.position,
                    rx_position,
                    interferer.node_name,
                    rx_node
                )

                # Cache for static topologies
                self._path_cache[cache_key] = path_result

            # Compute interference power: P_tx + G_tx + G_rx - PL - ACLR
            # All in dBm/dBi/dB, so addition/subtraction is correct
            interference_dbm = (
                interferer.tx_power_dbm
                + interferer.antenna_gain_dbi  # TX gain towards RX
                + rx_antenna_gain_dbi          # RX gain towards interferer
                - path_result.path_loss_db     # Path loss (subtract because it's a loss)
                - aclr_db                      # ACLR rejection (subtract)
            )

            logger.debug(
                "Interference %s→%s: P_tx=%.1f dBm, G_tx=%.1f dBi, G_rx=%.1f dBi, "
                "PL=%.1f dB, ACLR=%.1f dB (%.1f MHz sep) → I=%.1f dBm",
                interferer.node_name,
                rx_node,
                interferer.tx_power_dbm,
                interferer.antenna_gain_dbi,
                rx_antenna_gain_dbi,
                path_result.path_loss_db,
                aclr_db,
                freq_separation / 1e6,
                interference_dbm,
            )

            # Store interference term
            interference_terms.append(InterferenceTerm(
                source=interferer.node_name,
                power_dbm=interference_dbm,
                frequency_hz=interferer.frequency_hz,
                frequency_separation_hz=freq_separation,
                aclr_db=aclr_db,
            ))

            # Aggregate in linear domain (power sum)
            interference_linear = 10 ** (interference_dbm / 10.0)
            total_interference_linear += interference_linear

        # Convert total interference back to dB
        if total_interference_linear > 0:
            total_interference_dbm = 10 * np.log10(total_interference_linear)
        else:
            total_interference_dbm = -np.inf  # No interference

        return InterferenceResult(
            receiver_node=rx_node,
            interference_terms=interference_terms,
            total_interference_dbm=total_interference_dbm,
            num_interferers=len(interference_terms)
        )

    def _compute_interference_path(
        self,
        tx_position: tuple[float, float, float],
        rx_position: tuple[float, float, float],
        tx_name: str,
        rx_name: str,
    ) -> PathResult:
        """
        Compute propagation path from interferer to receiver using PathSolver.

        Args:
            tx_position: Transmitter position
            rx_position: Receiver position
            tx_name: Transmitter node name (for logging)
            rx_name: Receiver node name (for logging)

        Returns:
            PathResult with path loss and propagation characteristics
        """
        # Clear previous devices
        self._engine.clear_devices()

        # Add TX and RX for this interference link
        self._engine.add_transmitter(f"tx_{tx_name}", tx_position)
        self._engine.add_receiver(f"rx_{rx_name}", rx_position)

        # Compute paths using PathSolver
        path_result = self._engine.compute_paths()

        logger.debug(
            f"Computed interference path {tx_name}→{rx_name}: "
            f"PL={path_result.path_loss_db:.1f} dB, "
            f"delay={path_result.min_delay_ns:.1f} ns, "
            f"num_paths={path_result.num_paths}"
        )

        return path_result

    def clear_cache(self) -> None:
        """Clear path cache (use when positions change)."""
        self._path_cache.clear()
        logger.debug("Cleared interference path cache")

    def get_cache_stats(self) -> dict[str, int]:
        """Get cache statistics."""
        return {
            "num_cached_paths": len(self._path_cache),
        }
