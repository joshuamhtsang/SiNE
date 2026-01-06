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
    from sionna.rt import load_scene, Scene, PlanarArray, Transmitter, Receiver, PathSolver, Camera

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
class SinglePathInfo:
    """Information about a single propagation path."""

    path_index: int
    delay_ns: float
    power_db: float
    interaction_types: list[str]  # e.g., ['reflection', 'refraction']
    vertices: list[tuple[float, float, float]]  # interaction points
    is_los: bool


@dataclass
class PathDetails:
    """Detailed path information for debugging."""

    tx_position: tuple[float, float, float]
    rx_position: tuple[float, float, float]
    distance_m: float
    num_paths: int
    paths: list[SinglePathInfo]
    strongest_path_index: int
    shortest_path_index: int


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
        self.scene_path: Optional[Path] = None
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
        # Store scene path for later reference (for visualization)
        self.scene_path = Path(scene_path) if scene_path else None

        if scene_path:
            self.scene = load_scene(scene_path)
        else:
            # Create empty scene (Sionna 1.2+ API)
            self.scene = Scene()

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
        antenna_pattern: str = "iso",
        polarization: str = "V",
    ) -> None:
        """
        Add a transmitter to the scene.

        Args:
            name: Unique transmitter name
            position: (x, y, z) position in meters
            antenna_pattern: Antenna pattern type ("iso", "dipole", "hw_dipole", "tr38901")
            polarization: Antenna polarization ("V", "H", "VH", "cross")
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
            polarization=polarization,
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
        antenna_pattern: str = "iso",
        polarization: str = "V",
    ) -> None:
        """
        Add a receiver to the scene.

        Args:
            name: Unique receiver name
            position: (x, y, z) position in meters
            antenna_pattern: Antenna pattern type ("iso", "dipole", "hw_dipole", "tr38901")
            polarization: Antenna polarization ("V", "H", "VH", "cross")
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
            polarization=polarization,
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
        # Sionna v1.2.1 cir() with out_type='numpy' returns:
        # - a: np.array (complex) with shape [num_rx, num_rx_ant, num_tx, num_tx_ant, num_paths, num_time_steps]
        # - tau: np.array with shape [num_rx, num_rx_ant, num_tx, num_tx_ant, num_paths] or [num_rx, num_tx, num_paths]
        cir_result = paths.cir(out_type='numpy')

        # Handle different return formats
        if isinstance(cir_result, tuple) and len(cir_result) == 2:
            a_np, tau_np = cir_result
        else:
            # Fallback: might be a single value or different structure
            logger.error(f"Unexpected CIR result type: {type(cir_result)}")
            raise ValueError(f"Unexpected CIR result format: {type(cir_result)}")

        # Handle different formats for complex channel coefficients
        if isinstance(a_np, tuple) and len(a_np) == 2:
            # Real and imaginary components returned separately
            a_np = a_np[0] + 1j * a_np[1]
        elif not np.iscomplexobj(a_np):
            # If we got a real array, convert to complex (shouldn't happen, but be safe)
            logger.warning("CIR returned real amplitudes; expected complex. Converting to complex dtype.")
            a_np = a_np.astype(np.complex128)

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

            # Compute RMS delay spread (second moment of power delay profile)
            # Note: For single-path channels, delay spread is zero by definition
            if len(valid_taus) > 1:
                mean_delay = np.average(valid_taus, weights=valid_powers)
                delay_variance = np.average((valid_taus - mean_delay) ** 2, weights=valid_powers)
                delay_spread_ns = float(np.sqrt(delay_variance) * 1e9)
            else:
                # Single path - no multipath dispersion
                delay_spread_ns = 0.0
        else:
            min_delay_ns = 0.0
            max_delay_ns = 0.0
            delay_spread_ns = 0.0

        # Determine dominant path type from strongest path's interactions
        dominant_path_type = "nlos"  # Default
        try:
            # Try to get actual interaction data from Sionna
            interactions = paths.interactions.numpy()
            # Find index of strongest path
            strongest_idx = int(np.argmax(path_powers.flatten()))
            # Get interactions for strongest path (first rx/tx antenna pair)
            path_interactions = interactions[:, 0, 0, 0, 0, strongest_idx]

            # Check interaction types
            if np.all(path_interactions == 0):
                dominant_path_type = "los"  # No interactions = line of sight
            elif np.any(path_interactions == 3):
                dominant_path_type = "diffraction"  # Diffraction present
            else:
                dominant_path_type = "nlos"  # Reflections, scattering, etc.
        except (AttributeError, IndexError, Exception):
            # Fallback heuristic: short delay likely indicates LOS
            # Use 10 ns threshold (~3m indoor, reasonable for LOS detection)
            if min_delay_ns < 10.0 and num_valid_paths > 0:
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

    def get_path_details(self) -> PathDetails:
        """
        Get detailed information about all propagation paths for debugging.

        Returns:
            PathDetails with information about each path including vertices,
            interaction types, and power levels.
        """
        if not self._scene_loaded:
            raise RuntimeError("Scene must be loaded before getting path details")

        if not self._transmitters or not self._receivers:
            raise RuntimeError("At least one transmitter and receiver must be added")

        # Compute paths using PathSolver
        paths = self.path_solver(self.scene)

        # Get CIR for power/delay info
        cir_result = paths.cir(out_type='numpy')
        if isinstance(cir_result, tuple) and len(cir_result) == 2:
            a_np, tau_np = cir_result
        else:
            raise ValueError(f"Unexpected CIR result format: {type(cir_result)}")

        if isinstance(a_np, tuple) and len(a_np) == 2:
            a_np = a_np[0] + 1j * a_np[1]

        # Get TX/RX positions
        tx_pos = list(self._transmitters.values())[0]
        rx_pos = list(self._receivers.values())[0]
        distance = np.sqrt(
            (rx_pos[0] - tx_pos[0]) ** 2
            + (rx_pos[1] - tx_pos[1]) ** 2
            + (rx_pos[2] - tx_pos[2]) ** 2
        )

        # Interaction type mapping from Sionna RT interaction codes
        # Reference: Sionna RT documentation - Paths.interactions property
        interaction_map = {
            0: "none",  # LOS path (no interactions)
            1: "specular_reflection",  # Mirror-like reflection
            2: "diffuse_reflection",  # Diffuse scattering
            3: "diffraction",  # Edge/wedge diffraction
            4: "refraction",  # Transmission through materials
        }

        # Extract path information
        path_powers = np.abs(a_np.flatten()) ** 2
        path_delays = tau_np.flatten()

        # Get interactions and vertices if available
        try:
            interactions = paths.interactions.numpy()  # [max_depth, num_rx, num_rx_ant, num_tx, num_tx_ant, num_paths]
            vertices = paths.vertices.numpy()  # [max_depth, num_rx, num_rx_ant, num_tx, num_tx_ant, num_paths, 3]
            has_geometry = True
        except (AttributeError, Exception) as e:
            logger.debug(f"Could not get path geometry: {e}")
            has_geometry = False
            interactions = None
            vertices = None

        path_infos = []
        num_paths = len(path_powers)

        for i in range(num_paths):
            power = path_powers[i]
            if power < 1e-20:
                continue  # Skip invalid paths

            delay_ns = float(path_delays[i] * 1e9)
            power_db = float(10 * np.log10(power + 1e-30))

            # Get interaction types for this path
            interaction_types = []
            path_vertices = []

            if has_geometry and interactions is not None:
                # interactions shape: [max_depth, ...]
                # Get interactions for first rx/tx antenna pair
                path_interactions = interactions[:, 0, 0, 0, 0, i] if i < interactions.shape[-1] else []
                for interaction_code in path_interactions:
                    if interaction_code in interaction_map and interaction_code != 0:
                        interaction_types.append(interaction_map[int(interaction_code)])

                # Get vertices for this path
                if vertices is not None and i < vertices.shape[-2]:
                    path_verts = vertices[:, 0, 0, 0, 0, i, :]
                    for v in path_verts:
                        if not np.all(v == 0):  # Skip zero vertices
                            path_vertices.append((float(v[0]), float(v[1]), float(v[2])))

            is_los = len(interaction_types) == 0

            path_infos.append(SinglePathInfo(
                path_index=i,
                delay_ns=delay_ns,
                power_db=power_db,
                interaction_types=interaction_types,
                vertices=path_vertices,
                is_los=is_los,
            ))

        # Sort by power to find strongest
        if path_infos:
            strongest_idx = max(range(len(path_infos)), key=lambda i: path_infos[i].power_db)
            shortest_idx = min(range(len(path_infos)), key=lambda i: path_infos[i].delay_ns)
        else:
            strongest_idx = -1
            shortest_idx = -1

        return PathDetails(
            tx_position=tx_pos,
            rx_position=rx_pos,
            distance_m=float(distance),
            num_paths=len(path_infos),
            paths=path_infos,
            strongest_path_index=strongest_idx,
            shortest_path_index=shortest_idx,
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

    def _compute_default_camera(
        self,
        look_at: Optional[tuple[float, float, float]] = None,
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        """
        Compute a default camera position and look_at point based on scene geometry.

        The camera is positioned to show all transmitters and receivers.

        Args:
            look_at: Optional explicit look_at point. If None, computed from devices.

        Returns:
            Tuple of (camera_position, look_at_point)
        """
        # Collect all device positions
        positions = list(self._transmitters.values()) + list(self._receivers.values())

        if not positions:
            # No devices, use scene center estimate
            return ((10.0, 10.0, 15.0), (5.0, 2.0, 1.5))

        # Compute bounding box
        xs = [p[0] for p in positions]
        ys = [p[1] for p in positions]
        zs = [p[2] for p in positions]

        center_x = (min(xs) + max(xs)) / 2
        center_y = (min(ys) + max(ys)) / 2
        center_z = (min(zs) + max(zs)) / 2

        # Compute scene extent
        extent_x = max(xs) - min(xs) + 2.0  # Add padding
        extent_y = max(ys) - min(ys) + 2.0
        extent = max(extent_x, extent_y, 5.0)  # Minimum extent

        # Position camera at a distance proportional to scene extent
        # Offset diagonally and above to get a good view
        camera_pos = (
            center_x + extent * 1.5,
            center_y + extent * 0.8,
            center_z + extent * 1.2,
        )

        if look_at is None:
            look_at = (center_x, center_y, center_z)

        return (camera_pos, look_at)

    def render_scene(
        self,
        output_path: str,
        camera_position: Optional[tuple[float, float, float]] = None,
        look_at: Optional[tuple[float, float, float]] = None,
        fov: float = 45.0,
        resolution: tuple[int, int] = (655, 500),
        num_samples: int = 512,
        show_devices: bool = True,
        show_orientations: bool = True,
        include_paths: bool = True,
        clip_at: Optional[float] = None,
    ) -> None:
        """
        Render the scene to an image file.

        Args:
            output_path: Path to save the rendered image
            camera_position: Camera position (x, y, z). If None, auto-computed.
            look_at: Point to look at (x, y, z). If None, auto-computed.
            fov: Field of view in degrees
            resolution: Image resolution as (width, height)
            num_samples: Number of ray samples (higher = better quality)
            show_devices: Show TX/RX device markers
            show_orientations: Show device orientation indicators
            include_paths: Compute and render propagation paths
            clip_at: Clip plane height (z) to cut away geometry above this level
        """
        if not self._scene_loaded:
            raise RuntimeError("Scene must be loaded before rendering")

        # Compute camera position if not provided
        if camera_position is None or look_at is None:
            default_pos, default_look_at = self._compute_default_camera(look_at)
            if camera_position is None:
                camera_position = default_pos
            if look_at is None:
                look_at = default_look_at

        # Create camera
        camera = Camera(position=camera_position)
        camera.look_at(look_at)

        # Compute paths if requested and devices are present
        paths = None
        if include_paths and self._transmitters and self._receivers:
            try:
                paths = self.path_solver(self.scene)
                logger.info(f"Computed propagation paths for rendering")
            except Exception as e:
                logger.warning(f"Could not compute paths for rendering: {e}")

        # Render scene
        render_kwargs = {
            "filename": output_path,
            "camera": camera,
            "fov": fov,
            "resolution": resolution,
            "num_samples": num_samples,
            "show_devices": show_devices,
            "show_orientations": show_orientations,
            "paths": paths,
        }
        if clip_at is not None:
            render_kwargs["clip_at"] = clip_at
        self.scene.render_to_file(**render_kwargs)
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
        self._scene_loaded = False

    def load_scene(
        self,
        scene_path: Optional[str] = None,
        frequency_hz: float = 5.18e9,
        bandwidth_hz: float = 80e6,
    ) -> None:
        """Load scene (no-op for fallback, just store frequency)."""
        self._frequency_hz = frequency_hz
        self._scene_loaded = True
        logger.info(f"Fallback engine: scene loaded (frequency={frequency_hz/1e9:.3f} GHz)")

    def add_transmitter(
        self,
        name: str,
        position: tuple[float, float, float],
        antenna_pattern: str = "iso",
        polarization: str = "V",
    ) -> None:
        """Add transmitter position."""
        self._transmitters[name] = position

    def add_receiver(
        self,
        name: str,
        position: tuple[float, float, float],
        antenna_pattern: str = "iso",
        polarization: str = "V",
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

        # Free-space path loss (Friis transmission equation)
        # FSPL(dB) = 20·log₁₀(4πd/λ) = 20·log₁₀(d) + 20·log₁₀(f) + 20·log₁₀(4π/c)
        #          = 20·log₁₀(d) + 20·log₁₀(f) - 147.55
        # where 20·log₁₀(4π/(3×10⁸)) ≈ -147.55 dB
        if distance < 0.1:
            distance = 0.1  # Minimum distance to avoid log(0)
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

    def get_path_details(self) -> PathDetails:
        """
        Get path details for fallback engine (simplified).

        Returns:
            PathDetails with single FSPL path estimate.
        """
        if not self._transmitters or not self._receivers:
            raise RuntimeError("At least one transmitter and receiver required")

        tx_pos = list(self._transmitters.values())[0]
        rx_pos = list(self._receivers.values())[0]

        distance = np.sqrt(
            (rx_pos[0] - tx_pos[0]) ** 2
            + (rx_pos[1] - tx_pos[1]) ** 2
            + (rx_pos[2] - tx_pos[2]) ** 2
        )

        if distance < 0.1:
            distance = 0.1

        fspl = 20 * np.log10(distance) + 20 * np.log10(self._frequency_hz) - 147.55
        delay_ns = (distance / 3e8) * 1e9

        single_path = SinglePathInfo(
            path_index=0,
            delay_ns=delay_ns,
            power_db=float(-fspl - 10.0),  # Negative FSPL + indoor loss
            interaction_types=[],
            vertices=[],
            is_los=True,
        )

        return PathDetails(
            tx_position=tx_pos,
            rx_position=rx_pos,
            distance_m=float(distance),
            num_paths=1,
            paths=[single_path],
            strongest_path_index=0,
            shortest_path_index=0,
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
