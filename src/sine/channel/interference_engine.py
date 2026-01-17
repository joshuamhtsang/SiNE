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


@dataclass
class InterferenceTerm:
    """Single interference contribution from one transmitter."""

    source: str  # Node name of interferer
    power_dbm: float  # Interference power at receiver (includes TX/RX gains, path loss)
    frequency_hz: float  # Interferer frequency


@dataclass
class InterferenceResult:
    """Aggregated interference result for a receiver."""

    receiver_node: str
    interference_terms: list[InterferenceTerm]
    total_interference_dbm: float  # Aggregated in linear domain, converted to dB
    num_interferers: int


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
    ) -> InterferenceResult:
        """
        Compute interference from all active interferers at RX position.

        Uses PathSolver iteratively for each interferer to compute interference power.
        Aggregates interference in linear domain (power sum).

        Args:
            rx_position: Receiver position (x, y, z) in meters
            rx_antenna_gain_dbi: Receiver antenna gain in dBi
            rx_node: Receiver node name (for logging)
            interferers: List of potential interferers
            active_states: Dict of {node_name: is_transmitting}. If None, all active.

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
                logger.debug(f"Skipping inactive interferer: {interferer.node_name}")
                continue

            # Check cache for this TX→RX path
            cache_key = (interferer.position, rx_position)

            if cache_key in self._path_cache:
                path_result = self._path_cache[cache_key]
                logger.debug(f"Using cached path for {interferer.node_name}→{rx_node}")
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

            # Compute interference power: P_tx + G_tx + G_rx - PL
            # All in dBm/dBi, so addition is correct
            interference_dbm = (
                interferer.tx_power_dbm
                + interferer.antenna_gain_dbi  # TX gain towards RX
                + rx_antenna_gain_dbi          # RX gain towards interferer
                - path_result.path_loss_db     # Path loss (subtract because it's a loss)
            )

            logger.debug(
                f"Interference {interferer.node_name}→{rx_node}: "
                f"P_tx={interferer.tx_power_dbm:.1f} dBm, "
                f"G_tx={interferer.antenna_gain_dbi:.1f} dBi, "
                f"G_rx={rx_antenna_gain_dbi:.1f} dBi, "
                f"PL={path_result.path_loss_db:.1f} dB → "
                f"I={interference_dbm:.1f} dBm"
            )

            # Store interference term
            interference_terms.append(InterferenceTerm(
                source=interferer.node_name,
                power_dbm=interference_dbm,
                frequency_hz=interferer.frequency_hz
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
