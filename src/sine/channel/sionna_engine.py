"""
Sionna RT integration for ray tracing channel computation.

Uses Sionna's PathSolver API (v1.2+) for computing propagation paths
and extracting channel characteristics like path loss, delay spread, etc.

This module requires the 'gpu' optional dependencies:
    pip install sine[gpu]
"""

from pathlib import Path
from typing import Optional
from dataclasses import dataclass
import logging

import numpy as np

logger = logging.getLogger(__name__)

# Check for Sionna availability
_sionna_available = False
_sionna_import_error: Optional[str] = None

try:
    import tensorflow as tf
    import sionna
    from sionna.rt import load_scene, PlanarArray, Transmitter, Receiver, PathSolver

    _sionna_available = True
except ImportError as e:
    _sionna_import_error = str(e)


def is_sionna_available() -> bool:
    """Check if Sionna is available."""
    return _sionna_available


def get_sionna_import_error() -> Optional[str]:
    """Get the import error message if Sionna is not available."""
    return _sionna_import_error


@dataclass
class PathResult:
    """Results from ray tracing path computation."""

    path_loss_db: float
    min_delay_ns: float
    max_delay_ns: float
    delay_spread_ns: float
    num_paths: int
    dominant_path_type: str  # 'los', 'nlos', 'diffraction', etc.


@dataclass
class ChannelResult:
    """Complete channel computation results."""

    tx_node: str
    rx_node: str
    path_result: PathResult
    snr_db: float
    ber: float
    bler: Optional[float]
    per: float
    # netem parameters
    delay_ms: float
    jitter_ms: float
    loss_percent: float
    rate_mbps: float


class SionnaEngine:
    """
    Sionna RT engine for ray tracing channel computation.

    Uses Sionna's PathSolver API for computing propagation paths through
    a ray-traced scene.
    """

    def __init__(self):
        """Initialize Sionna engine."""
        if not _sionna_available:
            raise ImportError(
                f"Sionna is required for SionnaEngine. "
                f"Install with: pip install sine[gpu]\n"
                f"Import error: {_sionna_import_error}"
            )

        self.scene = None
        self.path_solver = None
        self._scene_loaded = False
        self._transmitters: dict[str, tuple[float, float, float]] = {}
        self._receivers: dict[str, tuple[float, float, float]] = {}

    def load_scene(
        self,
        scene_path: Optional[str] = None,
        frequency_hz: float = 5.18e9,
        bandwidth_hz: float = 80e6,
    ) -> None:
        """
        Load ray tracing scene.

        Args:
            scene_path: Path to Mitsuba XML scene file, or None for empty scene
            frequency_hz: RF frequency for simulation
            bandwidth_hz: Channel bandwidth
        """
        if scene_path:
            self.scene = load_scene(scene_path)
        else:
            # Load empty scene
            self.scene = load_scene(sionna.rt.scene.empty)

        # Configure RF parameters
        self.scene.frequency = frequency_hz
        self.scene.bandwidth = bandwidth_hz

        # Initialize PathSolver
        self.path_solver = PathSolver()
        self._scene_loaded = True

        logger.info(f"Loaded scene: {scene_path or 'empty'}")
        logger.info(f"Frequency: {frequency_hz/1e9:.3f} GHz, Bandwidth: {bandwidth_hz/1e6:.1f} MHz")

    def add_transmitter(
        self,
        name: str,
        position: tuple[float, float, float],
        antenna_pattern: str = "isotropic",
    ) -> None:
        """
        Add a transmitter to the scene.

        Args:
            name: Unique transmitter name
            position: (x, y, z) position in meters
            antenna_pattern: Antenna pattern type
        """
        if not self._scene_loaded:
            raise RuntimeError("Scene must be loaded before adding transmitters")

        # Remove existing transmitter with same name if present
        if name in self.scene.transmitters:
            self.scene.remove(name)

        # Create antenna array (single element for simplicity)
        tx_array = PlanarArray(
            num_rows=1,
            num_cols=1,
            vertical_spacing=0.5,
            horizontal_spacing=0.5,
            pattern=antenna_pattern,
        )

        # Create and add transmitter
        tx = Transmitter(name=name, position=list(position), orientation=[0, 0, 0])
        self.scene.add(tx)
        self.scene.tx_array = tx_array

        self._transmitters[name] = position
        logger.debug(f"Added transmitter '{name}' at {position}")

    def add_receiver(
        self,
        name: str,
        position: tuple[float, float, float],
        antenna_pattern: str = "isotropic",
    ) -> None:
        """
        Add a receiver to the scene.

        Args:
            name: Unique receiver name
            position: (x, y, z) position in meters
            antenna_pattern: Antenna pattern type
        """
        if not self._scene_loaded:
            raise RuntimeError("Scene must be loaded before adding receivers")

        # Remove existing receiver with same name if present
        if name in self.scene.receivers:
            self.scene.remove(name)

        # Create antenna array
        rx_array = PlanarArray(
            num_rows=1,
            num_cols=1,
            vertical_spacing=0.5,
            horizontal_spacing=0.5,
            pattern=antenna_pattern,
        )

        # Create and add receiver
        rx = Receiver(name=name, position=list(position), orientation=[0, 0, 0])
        self.scene.add(rx)
        self.scene.rx_array = rx_array

        self._receivers[name] = position
        logger.debug(f"Added receiver '{name}' at {position}")

    def compute_paths(self) -> PathResult:
        """
        Compute propagation paths using ray tracing.

        Returns:
            PathResult with path loss, delays, and path information
        """
        if not self._scene_loaded:
            raise RuntimeError("Scene must be loaded before computing paths")

        if not self._transmitters or not self._receivers:
            raise RuntimeError("At least one transmitter and receiver must be added")

        # Compute paths using PathSolver (Sionna 1.2+ API)
        paths = self.path_solver(self.scene)

        # Get channel impulse response
        # Returns: (batch, num_rx, num_rx_ant, num_tx, num_tx_ant, num_paths)
        a, tau = paths.cir()

        # Convert to numpy
        a_np = a.numpy()
        tau_np = tau.numpy()

        # Check if we have valid paths
        num_valid_paths = int(np.sum(np.abs(a_np) > 1e-10))

        if num_valid_paths == 0:
            # No valid paths - return worst case
            logger.warning("No valid propagation paths found")
            return PathResult(
                path_loss_db=200.0,  # Very high loss
                min_delay_ns=0.0,
                max_delay_ns=0.0,
                delay_spread_ns=0.0,
                num_paths=0,
                dominant_path_type="none",
            )

        # Compute path loss from path coefficients
        # Total received power = sum of |a_i|^2 for all paths
        path_powers = np.abs(a_np) ** 2
        total_path_gain = np.sum(path_powers)
        path_loss_db = -10 * np.log10(total_path_gain + 1e-30)

        # Get delays for valid paths (non-zero power)
        valid_mask = np.abs(a_np.flatten()) > 1e-10
        valid_taus = tau_np.flatten()[valid_mask]
        valid_powers = path_powers.flatten()[valid_mask]

        if len(valid_taus) > 0:
            min_delay_ns = float(np.min(valid_taus) * 1e9)
            max_delay_ns = float(np.max(valid_taus) * 1e9)

            # Compute RMS delay spread
            mean_delay = np.average(valid_taus, weights=valid_powers)
            delay_spread = np.sqrt(
                np.average((valid_taus - mean_delay) ** 2, weights=valid_powers)
            )
            delay_spread_ns = float(delay_spread * 1e9)
        else:
            min_delay_ns = 0.0
            max_delay_ns = 0.0
            delay_spread_ns = 0.0

        # Determine dominant path type
        # This would require access to path interaction types from Sionna
        # For now, use a simple heuristic
        if min_delay_ns < 1.0 and num_valid_paths > 0:
            dominant_path_type = "los"
        else:
            dominant_path_type = "nlos"

        return PathResult(
            path_loss_db=float(path_loss_db),
            min_delay_ns=min_delay_ns,
            max_delay_ns=max_delay_ns,
            delay_spread_ns=delay_spread_ns,
            num_paths=num_valid_paths,
            dominant_path_type=dominant_path_type,
        )

    def update_position(self, name: str, position: tuple[float, float, float]) -> None:
        """
        Update position of a transmitter or receiver.

        Args:
            name: Name of the transmitter or receiver
            position: New (x, y, z) position
        """
        if name in self.scene.transmitters:
            self.scene.transmitters[name].position = list(position)
            self._transmitters[name] = position
        elif name in self.scene.receivers:
            self.scene.receivers[name].position = list(position)
            self._receivers[name] = position
        else:
            raise ValueError(f"Unknown transmitter/receiver: {name}")

    def clear_devices(self) -> None:
        """Remove all transmitters and receivers from the scene."""
        for name in list(self._transmitters.keys()):
            if name in self.scene.transmitters:
                self.scene.remove(name)
        for name in list(self._receivers.keys()):
            if name in self.scene.receivers:
                self.scene.remove(name)
        self._transmitters.clear()
        self._receivers.clear()

    def render_scene(
        self, output_path: str, camera_position: Optional[tuple[float, float, float]] = None
    ) -> None:
        """
        Render the scene to an image file.

        Args:
            output_path: Path to save the rendered image
            camera_position: Optional camera position (uses default if None)
        """
        if not self._scene_loaded:
            raise RuntimeError("Scene must be loaded before rendering")

        self.scene.render_to_file(
            filename=output_path,
            camera="preview" if camera_position is None else None,
            num_samples=512,
        )
        logger.info(f"Rendered scene to {output_path}")


class FallbackEngine:
    """
    Fallback channel computation engine when Sionna is not available.

    Uses simple free-space path loss model for basic functionality.
    """

    def __init__(self):
        """Initialize fallback engine."""
        self._transmitters: dict[str, tuple[float, float, float]] = {}
        self._receivers: dict[str, tuple[float, float, float]] = {}
        self._frequency_hz = 5.18e9

    def load_scene(
        self,
        scene_path: Optional[str] = None,
        frequency_hz: float = 5.18e9,
        bandwidth_hz: float = 80e6,
    ) -> None:
        """Load scene (no-op for fallback, just store frequency)."""
        self._frequency_hz = frequency_hz
        logger.warning("Using fallback engine - ray tracing not available")

    def add_transmitter(
        self, name: str, position: tuple[float, float, float], antenna_pattern: str = "isotropic"
    ) -> None:
        """Add transmitter position."""
        self._transmitters[name] = position

    def add_receiver(
        self, name: str, position: tuple[float, float, float], antenna_pattern: str = "isotropic"
    ) -> None:
        """Add receiver position."""
        self._receivers[name] = position

    def compute_paths(self) -> PathResult:
        """
        Compute path using free-space model.

        Returns:
            PathResult with FSPL-based path loss
        """
        if not self._transmitters or not self._receivers:
            raise RuntimeError("At least one transmitter and receiver required")

        # Get first TX and RX positions
        tx_pos = list(self._transmitters.values())[0]
        rx_pos = list(self._receivers.values())[0]

        # Calculate distance
        distance = np.sqrt(
            (rx_pos[0] - tx_pos[0]) ** 2
            + (rx_pos[1] - tx_pos[1]) ** 2
            + (rx_pos[2] - tx_pos[2]) ** 2
        )

        # Free-space path loss
        if distance < 0.1:
            distance = 0.1  # Minimum distance
        fspl = 20 * np.log10(distance) + 20 * np.log10(self._frequency_hz) - 147.55

        # Add indoor loss factor (rough estimate)
        indoor_loss = 10.0  # dB

        # Propagation delay
        speed_of_light = 3e8
        delay_ns = (distance / speed_of_light) * 1e9

        return PathResult(
            path_loss_db=float(fspl + indoor_loss),
            min_delay_ns=delay_ns,
            max_delay_ns=delay_ns + 10.0,  # Small spread
            delay_spread_ns=5.0,  # Typical indoor
            num_paths=1,
            dominant_path_type="fspl_estimate",
        )

    def update_position(self, name: str, position: tuple[float, float, float]) -> None:
        """Update device position."""
        if name in self._transmitters:
            self._transmitters[name] = position
        elif name in self._receivers:
            self._receivers[name] = position
        else:
            raise ValueError(f"Unknown device: {name}")

    def clear_devices(self) -> None:
        """Clear all devices."""
        self._transmitters.clear()
        self._receivers.clear()


def get_engine() -> SionnaEngine | FallbackEngine:
    """
    Get the appropriate channel computation engine.

    Returns SionnaEngine if Sionna is available, otherwise FallbackEngine.
    """
    if _sionna_available:
        return SionnaEngine()
    else:
        logger.warning(
            "Sionna not available, using fallback FSPL model. "
            "Install with: pip install sine[gpu]"
        )
        return FallbackEngine()
