"""
FastAPI Channel Computation Server.

Provides REST API endpoints for computing wireless channel parameters
using Sionna ray tracing. Returns netem parameters for network emulation.

Endpoints:
- POST /compute/single - Compute channel for single link
- POST /compute/batch - Compute channels for multiple links (efficient)
- POST /compute/sinr - Compute SINR with multi-transmitter interference (Phase 1)
- POST /scene/load - Load/reload ray tracing scene
- POST /debug/paths - Get detailed path info for debugging (vertices, interactions)
- GET /health - Health check with GPU status
- GET /api/visualization/state - Get cached visualization data (scene, devices, paths)
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from sine.channel.sionna_engine import get_engine, is_sionna_available, PathResult, PathDetails, SinglePathInfo
from sine.channel.snr import SNRCalculator
from sine.channel.modulation import BERCalculator, BLERCalculator, get_bits_per_symbol
from sine.channel.per_calculator import PERCalculator
from sine.channel.mcs import MCSTable, MCSEntry
from sine.channel.sinr import SINRCalculator, SINRResult, calculate_thermal_noise
from sine.channel.interference_engine import InterferenceEngine, TransmitterInfo
from sine.channel.frequency_groups import group_nodes_by_frequency
from sine.channel.csma_model import CSMAModel
from sine.channel.tdma_model import TDMAModel, TDMASlotConfig, SlotAssignmentMode
import math

logger = logging.getLogger(__name__)

# Global MCS table cache
_mcs_tables: dict[str, MCSTable] = {}

# Global engine instance
_engine = None

# Global interference engine (for SINR computation)
_interference_engine: InterferenceEngine | None = None

# Global SINR calculator
_sinr_calculator: SINRCalculator | None = None

# Global path cache for visualization (stores computed paths from channel computations)
_path_cache: dict[str, dict] = {}  # {link_id: {tx_pos, rx_pos, path_details, wireless_metrics}}
_device_positions: dict[str, tuple[float, float, float]] = {}  # {device_name: (x,y,z)}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global _engine
    _engine = get_engine()
    logger.info("Channel computation server started")
    yield
    logger.info("Channel computation server shutting down")


app = FastAPI(
    title="SiNE Channel Computation Server",
    description="Compute wireless channel parameters using Sionna ray tracing",
    version="0.1.0",
    lifespan=lifespan,
)


# ============================================================================
# Request/Response Models
# ============================================================================


class Position(BaseModel):
    """3D position in meters."""

    x: float
    y: float
    z: float

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


class SceneConfig(BaseModel):
    """Scene configuration for ray tracing."""

    scene_file: str = Field(..., description="Path to Mitsuba XML scene file")
    frequency_hz: float = Field(default=5.18e9, description="RF frequency in Hz")
    bandwidth_hz: float = Field(default=80e6, description="Channel bandwidth in Hz")


class MACModel(BaseModel):
    """MAC layer model configuration (CSMA or TDMA)."""

    type: str = Field(..., description="MAC model type: csma or tdma")
    # CSMA parameters
    carrier_sense_range_multiplier: float | None = Field(default=None, description="CSMA: CS range multiplier")
    traffic_load: float | None = Field(default=None, description="CSMA: Traffic duty cycle")
    communication_range_snr_threshold_db: float | None = Field(
        default=None,
        description="CSMA: SNR threshold for communication range estimation (default: 20 dB)"
    )
    # TDMA parameters
    frame_duration_ms: float | None = Field(default=None, description="TDMA: Frame duration in ms")
    num_slots: int | None = Field(default=None, description="TDMA: Number of slots per frame")
    slot_assignment_mode: str | None = Field(default=None, description="TDMA: Slot assignment mode")
    fixed_slot_map: dict[str, list[int]] | None = Field(default=None, description="TDMA: Fixed slot assignments")
    slot_probability: float | None = Field(default=None, description="TDMA: Slot ownership probability")


class WirelessLinkRequest(BaseModel):
    """Request to compute channel for a single wireless link."""

    tx_node: str = Field(..., description="Transmitter node name")
    rx_node: str = Field(..., description="Receiver node name")
    tx_position: Position
    rx_position: Position
    tx_power_dbm: float = Field(default=20.0, description="Transmit power in dBm")
    tx_gain_dbi: float = Field(default=0.0, description="TX antenna gain in dBi")
    rx_gain_dbi: float = Field(default=0.0, description="RX antenna gain in dBi")
    antenna_pattern: str = Field(default="iso", description="Antenna pattern: iso, dipole, hw_dipole, tr38901")
    polarization: str = Field(default="V", description="Antenna polarization: V, H, VH, cross")
    frequency_hz: float = Field(default=5.18e9)
    bandwidth_hz: float = Field(default=80e6)
    # Fixed modulation parameters (used when mcs_table_path is not set)
    modulation: str | None = Field(default=None, description="Fixed modulation scheme")
    fec_type: str | None = Field(default=None, description="Fixed FEC type")
    fec_code_rate: float | None = Field(default=None, description="Fixed FEC code rate")
    # MCS table for adaptive modulation
    mcs_table_path: str | None = Field(default=None, description="Path to MCS table CSV for adaptive selection")
    mcs_hysteresis_db: float = Field(default=2.0, description="MCS selection hysteresis in dB")
    packet_size_bits: int = Field(default=12000, description="Packet size in bits")
    # MAC layer model
    mac_model: MACModel | None = Field(default=None, description="MAC layer model (CSMA or TDMA)")


class ChannelResponse(BaseModel):
    """Response with computed channel parameters."""

    tx_node: str
    rx_node: str
    # Ray tracing results
    path_loss_db: float
    num_paths: int
    dominant_path_type: str
    # Link budget
    received_power_dbm: float
    snr_db: float
    # Error rates
    ber: float
    bler: float | None
    per: float
    # netem parameters
    netem_delay_ms: float
    netem_jitter_ms: float
    netem_loss_percent: float
    netem_rate_mbps: float
    # MCS selection info (populated when using adaptive MCS)
    selected_mcs_index: int | None = None
    selected_modulation: str | None = None
    selected_code_rate: float | None = None
    selected_fec_type: str | None = None
    selected_bandwidth_mhz: float | None = None
    # MAC model metadata
    mac_model_type: str | None = None  # "csma", "tdma", or None
    sinr_db: float | None = None  # SINR when using MAC models
    hidden_nodes: int | None = None  # CSMA: Number of hidden nodes
    expected_interference_dbm: float | None = None  # CSMA: Expected interference power with probabilities
    throughput_multiplier: float | None = None  # TDMA: Slot ownership fraction


class BatchChannelRequest(BaseModel):
    """Request to compute channels for multiple links."""

    scene: SceneConfig = Field(default_factory=SceneConfig)
    links: list[WirelessLinkRequest]


class BatchChannelResponse(BaseModel):
    """Response with results for multiple links."""

    results: list[ChannelResponse]
    computation_time_ms: float


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    sionna_available: bool
    gpu_available: bool
    scene_loaded: bool


class SceneLoadResponse(BaseModel):
    """Response for scene load operation."""

    status: str
    scene_file: str
    frequency_ghz: float
    bandwidth_mhz: float


class SinglePathInfoResponse(BaseModel):
    """Information about a single propagation path."""

    path_index: int
    delay_ns: float
    power_db: float
    interaction_types: list[str]
    vertices: list[list[float]]  # List of [x, y, z] coordinates
    is_los: bool


class PathDetailsRequest(BaseModel):
    """Request for path details between two positions."""

    tx_name: str = Field(default="tx", description="Transmitter name")
    rx_name: str = Field(default="rx", description="Receiver name")
    tx_position: Position
    rx_position: Position
    antenna_pattern: str = Field(default="iso")
    polarization: str = Field(default="V")


class PathDetailsResponse(BaseModel):
    """Detailed path information for debugging."""

    tx_position: list[float]
    rx_position: list[float]
    distance_m: float
    num_paths: int
    paths: list[SinglePathInfoResponse]
    strongest_path_index: int
    shortest_path_index: int
    strongest_path: SinglePathInfoResponse | None
    shortest_path: SinglePathInfoResponse | None


class SINRLinkRequest(BaseModel):
    """Request to compute SINR for a single link with interference."""

    # Target link (signal)
    tx_node: str
    rx_node: str
    tx_position: Position
    rx_position: Position
    tx_power_dbm: float = Field(default=20.0)
    tx_gain_dbi: float = Field(default=0.0)
    rx_gain_dbi: float = Field(default=0.0)
    frequency_hz: float = Field(default=5.18e9)
    bandwidth_hz: float = Field(default=80e6)
    antenna_pattern: str = Field(default="iso")
    polarization: str = Field(default="V")

    # Interferers
    interferers: list["InterfererInfo"]

    # SINR calculator settings
    rx_sensitivity_dbm: float = Field(default=-80.0, description="Receiver sensitivity floor")
    apply_capture_effect: bool = Field(default=False, description="Enable capture effect")
    capture_threshold_db: float = Field(default=6.0, description="Capture threshold in dB")


class InterfererInfo(BaseModel):
    """Information about an interfering transmitter."""

    node_name: str
    position: Position
    tx_power_dbm: float
    antenna_gain_dbi: float
    frequency_hz: float
    bandwidth_hz: float = Field(default=80e6, description="Transmitter channel bandwidth in Hz")
    is_active: bool = Field(default=True, description="Whether this interferer is currently transmitting")


class SINRResponse(BaseModel):
    """Response with SINR computation results."""

    tx_node: str
    rx_node: str

    # Power levels (dBm)
    signal_power_dbm: float
    noise_power_dbm: float
    total_interference_dbm: float

    # Ratios (dB)
    snr_db: float
    sinr_db: float

    # Interference details
    num_interferers: int
    num_active_interferers: int
    regime: str  # "noise-limited", "interference-limited", "mixed", "unusable"

    # Optional capture effect info
    capture_effect_applied: bool = False
    num_suppressed_interferers: int = 0


# ============================================================================
# Helper Functions
# ============================================================================


def calculate_k_factor(path_details: PathDetails) -> float | None:
    """
    Calculate Rician K-factor (LOS/NLOS power ratio).

    K = P_LOS / P_NLOS
    K_dB = 10×log10(K)

    The K-factor characterizes the channel type:
    - K > 10 dB: Strong LOS component (low fading variance)
    - 0 < K < 10 dB: Mixed LOS + multipath
    - K < 0 dB: NLOS dominant (Rayleigh-like fading)
    - None: No LOS path exists

    Args:
        path_details: PathDetails object with propagation path information

    Returns:
        K-factor in dB, or None if no LOS path exists
    """
    import numpy as np

    los_paths = [p for p in path_details.paths if p.is_los]
    nlos_paths = [p for p in path_details.paths if not p.is_los]

    if not los_paths:
        return None

    # Convert dB to linear power
    p_los = 10 ** (los_paths[0].power_db / 10)
    p_nlos_total = sum(10 ** (p.power_db / 10) for p in nlos_paths)

    if p_nlos_total < 1e-20:
        return 100.0  # Very strong LOS, weak multipath

    k_linear = p_los / p_nlos_total
    k_db = 10 * np.log10(k_linear)

    return float(k_db)


def cache_path_for_visualization(
    tx_node: str,
    rx_node: str,
    tx_pos: tuple[float, float, float],
    rx_pos: tuple[float, float, float],
    path_result: PathResult,
    path_details: PathDetails,
    bandwidth_hz: float
) -> None:
    """
    Cache computed path data for visualization.

    This function extracts and stores path information including wireless
    channel metrics (K-factor, coherence bandwidth, delay spread) for later
    retrieval by the visualization endpoint.

    Args:
        tx_node: Transmitter node name
        rx_node: Receiver node name
        tx_pos: Transmitter position (x, y, z)
        rx_pos: Receiver position (x, y, z)
        path_result: Ray tracing path computation results
        path_details: Detailed path information with vertices and interactions
        bandwidth_hz: Channel bandwidth in Hz
    """
    global _path_cache, _device_positions

    logger.info(f"Caching visualization data for link {tx_node}->{rx_node}")

    try:
        # Create link identifier (tx_node -> rx_node)
        link_id = f"{tx_node}->{rx_node}"

        # Calculate Rician K-factor (LOS/NLOS characterization)
        k_factor_db = calculate_k_factor(path_details)

        # Calculate coherence bandwidth from RMS delay spread
        # Bc ≈ 1/(5×τ_rms) - indicates frequency selectivity
        if path_result.delay_spread_ns > 0:
            coherence_bw_hz = 1.0 / (5.0 * path_result.delay_spread_ns * 1e-9)
        else:
            coherence_bw_hz = bandwidth_hz  # No multipath, flat channel

        # Limit to 5 strongest paths for visualization
        sorted_paths = sorted(path_details.paths, key=lambda p: p.power_db, reverse=True)
        limited_paths = sorted_paths[:5]

        # Calculate power coverage of shown paths
        total_power_linear = sum(10**(p.power_db/10) for p in path_details.paths)
        shown_power_linear = sum(10**(p.power_db/10) for p in limited_paths)
        power_coverage_pct = 100 * shown_power_linear / total_power_linear if total_power_linear > 0 else 0

        # Convert to JSON-serializable format
        paths_data = [{
            "delay_ns": float(p.delay_ns),
            "power_db": float(p.power_db),
            "vertices": [[float(v[0]), float(v[1]), float(v[2])] for v in p.vertices],
            "interaction_types": p.interaction_types,
            "is_los": p.is_los,
            "doppler_hz": None,  # TODO: Extract from Sionna in Phase 2
        } for p in limited_paths]

        _path_cache[link_id] = {
            "tx_name": tx_node,
            "rx_name": rx_node,
            "tx_position": [tx_pos[0], tx_pos[1], tx_pos[2]],
            "rx_position": [rx_pos[0], rx_pos[1], rx_pos[2]],
            "distance_m": float(path_details.distance_m),
            "num_paths_total": path_details.num_paths,
            "num_paths_shown": len(paths_data),
            "power_coverage_percent": float(power_coverage_pct),

            # Wireless channel metrics
            "rms_delay_spread_ns": float(path_result.delay_spread_ns),
            "coherence_bandwidth_hz": float(coherence_bw_hz),
            "k_factor_db": float(k_factor_db) if k_factor_db is not None else None,
            "dominant_path_type": path_result.dominant_path_type,

            "paths": paths_data
        }

        # Also store device positions
        _device_positions[tx_node] = tx_pos
        _device_positions[rx_node] = rx_pos

        logger.info(f"Cached {len(paths_data)} paths for link {link_id}. Total cache size: {len(_path_cache)}")

    except Exception as e:
        logger.warning(f"Failed to cache paths for visualization: {e}")
        import traceback
        logger.warning(traceback.format_exc())


def get_or_load_mcs_table(path: str, hysteresis_db: float = 2.0) -> MCSTable:
    """Get cached MCS table or load from file."""
    cache_key = f"{path}:{hysteresis_db}"
    if cache_key not in _mcs_tables:
        _mcs_tables[cache_key] = MCSTable.from_csv(path, hysteresis_db)
    return _mcs_tables[cache_key]


def _validate_channel_result(
    snr_db: float,
    per: float,
    path_loss_db: float,
    frequency_hz: float,
    distance_m: float,
) -> None:
    """Validate channel computation results for physics sanity."""
    # Check SNR range
    if snr_db > 50.0:
        logger.warning(
            f"SNR={snr_db:.1f} dB exceeds typical range (< 50 dB) - "
            f"possible antenna gain double-counting"
        )

    if snr_db < -20.0:
        logger.warning(f"SNR={snr_db:.1f} dB very low - link likely unusable")

    # Check PER vs SNR correlation
    if snr_db > 25.0 and per > 0.1:
        logger.warning(
            f"High SNR ({snr_db:.1f} dB) but high PER ({per:.2%}) - "
            f"possible BER calculation error"
        )

    # Check path loss vs FSPL (path loss should be >= FSPL)
    if distance_m > 0:
        from sine.channel.snr import SNRCalculator

        fspl = SNRCalculator.free_space_path_loss(distance_m, frequency_hz)
        if path_loss_db < fspl - 3.0:  # 3 dB margin for antenna gain
            logger.warning(
                f"Path loss ({path_loss_db:.1f} dB) less than FSPL "
                f"({fspl:.1f} dB) - physics violation"
            )


def estimate_communication_range(
    tx_power_dbm: float,
    frequency_hz: float,
    bandwidth_hz: float,
    tx_gain_dbi: float = 0.0,
    rx_gain_dbi: float = 0.0,
    min_snr_db: float = 10.0,
    noise_figure_db: float = 7.0,
) -> float:
    """
    Estimate communication range from link budget.

    Finds the distance where SNR drops to min_snr_db threshold.
    Uses free-space path loss (FSPL) model for conservative estimate.

    Args:
        tx_power_dbm: Transmit power in dBm
        frequency_hz: Carrier frequency in Hz
        bandwidth_hz: Channel bandwidth in Hz
        tx_gain_dbi: TX antenna gain in dBi (default: 0)
        rx_gain_dbi: RX antenna gain in dBi (default: 0)
        min_snr_db: Minimum SNR threshold for communication (default: 10 dB)
        noise_figure_db: Receiver noise figure (default: 7 dB)

    Returns:
        Estimated communication range in meters
    """
    # Thermal noise power: -174 dBm/Hz + 10*log10(BW) + NF
    noise_floor_dbm = -174.0 + 10.0 * math.log10(bandwidth_hz) + noise_figure_db

    # Required RX power for min_snr_db
    min_rx_power_dbm = noise_floor_dbm + min_snr_db

    # Maximum allowable path loss
    max_path_loss_db = tx_power_dbm + tx_gain_dbi + rx_gain_dbi - min_rx_power_dbm

    # FSPL formula: PL = 20*log10(d) + 20*log10(f) - 147.55
    # Solve for d: d = 10^((PL - 20*log10(f) + 147.55) / 20)
    frequency_ghz = frequency_hz / 1e9
    log_distance = (max_path_loss_db - 20.0 * math.log10(frequency_ghz * 1e9) + 147.55) / 20.0
    communication_range_m = 10.0 ** log_distance

    logger.info(
        f"Estimated communication range: {communication_range_m:.1f} m "
        f"(TX={tx_power_dbm} dBm, f={frequency_ghz:.2f} GHz, "
        f"BW={bandwidth_hz/1e6:.0f} MHz, min_SNR={min_snr_db} dB)"
    )

    return communication_range_m


async def _compute_batch_with_mac_model(
    links: list[WirelessLinkRequest],
    mac_model_config: MACModel,
    scene_config: SceneConfig,
) -> list[ChannelResponse]:
    """
    Compute channels for multiple links with MAC model (CSMA or TDMA).

    This function handles interference-aware SINR computation using either
    CSMA or TDMA statistical models.

    Args:
        links: List of link requests
        mac_model_config: MAC model configuration (CSMA or TDMA)
        scene_config: Scene configuration

    Returns:
        List of channel responses with SINR and MAC metadata
    """
    global _engine, _interference_engine, _sinr_calculator

    logger.info(f"Computing {len(links)} links with {mac_model_config.type.upper()} MAC model")

    # Initialize interference engine if needed
    if _interference_engine is None:
        _interference_engine = InterferenceEngine()
        _interference_engine.load_scene(
            scene_path=scene_config.scene_file,
            frequency_hz=scene_config.frequency_hz,
            bandwidth_hz=scene_config.bandwidth_hz,
        )

    # Initialize SINR calculator if needed
    if _sinr_calculator is None:
        _sinr_calculator = SINRCalculator()

    # Collect all unique node positions and info
    node_positions: dict[str, tuple[float, float, float]] = {}
    node_powers: dict[str, float] = {}
    node_gains: dict[str, float] = {}
    all_nodes: set[str] = set()

    for link in links:
        node_positions[link.tx_node] = link.tx_position.as_tuple()
        node_positions[link.rx_node] = link.rx_position.as_tuple()
        node_powers[link.tx_node] = link.tx_power_dbm
        node_gains[link.tx_node] = link.tx_gain_dbi
        node_gains[link.rx_node] = link.rx_gain_dbi
        all_nodes.add(link.tx_node)
        all_nodes.add(link.rx_node)

    # Instantiate MAC model
    mac_model = None
    if mac_model_config.type == "csma":
        mac_model = CSMAModel(
            carrier_sense_range_multiplier=mac_model_config.carrier_sense_range_multiplier or 2.5,
            default_traffic_load=mac_model_config.traffic_load or 0.3,
        )
    elif mac_model_config.type == "tdma":
        tdma_config = TDMASlotConfig(
            frame_duration_ms=mac_model_config.frame_duration_ms or 10.0,
            num_slots=mac_model_config.num_slots or 10,
            slot_assignment_mode=SlotAssignmentMode(mac_model_config.slot_assignment_mode or "round_robin"),
            fixed_slot_map=mac_model_config.fixed_slot_map,
            slot_probability=mac_model_config.slot_probability or 0.1,
        )
        mac_model = TDMAModel(tdma_config)
    else:
        raise ValueError(f"Unknown MAC model type: {mac_model_config.type}")

    # Compute channels for each link
    results = []
    for link in links:
        try:
            # Compute signal path (TX -> RX)
            _engine.clear_devices()
            tx_pos = link.tx_position.as_tuple()
            rx_pos = link.rx_position.as_tuple()

            _engine.add_transmitter(
                name=link.tx_node,
                position=tx_pos,
                antenna_pattern=link.antenna_pattern,
                polarization=link.polarization,
            )
            _engine.add_receiver(
                name=link.rx_node,
                position=rx_pos,
                antenna_pattern=link.antenna_pattern,
                polarization=link.polarization,
            )

            # Get path result for signal
            path_result = _engine.compute_paths()

            # Cache paths for visualization
            path_details = _engine.get_path_details()
            cache_path_for_visualization(
                tx_node=link.tx_node,
                rx_node=link.rx_node,
                tx_pos=tx_pos,
                rx_pos=rx_pos,
                path_result=path_result,
                path_details=path_details,
                bandwidth_hz=link.bandwidth_hz
            )

            # Compute signal power using SNR calculator
            snr_calc = SNRCalculator(
                bandwidth_hz=link.bandwidth_hz,
                noise_figure_db=7.0,
            )
            signal_power_dbm, snr_db = snr_calc.calculate_link_snr(
                tx_power_dbm=link.tx_power_dbm,
                tx_gain_dbi=link.tx_gain_dbi,
                rx_gain_dbi=link.rx_gain_dbi,
                path_loss_db=path_result.path_loss_db,
                from_sionna=True,
            )

            # Compute noise power
            noise_power_dbm = calculate_thermal_noise(
                bandwidth_hz=link.bandwidth_hz,
                noise_figure_db=7.0,
            )

            # Compute interference probabilities using MAC model
            interferer_nodes = [n for n in all_nodes if n not in (link.tx_node, link.rx_node)]

            if mac_model_config.type == "csma":
                # CSMA: Estimate communication range from link budget
                # Use configured SNR threshold from network.yaml
                communication_range = estimate_communication_range(
                    tx_power_dbm=link.tx_power_dbm,
                    frequency_hz=link.frequency_hz,
                    bandwidth_hz=link.bandwidth_hz,
                    tx_gain_dbi=link.tx_gain_dbi,
                    rx_gain_dbi=link.rx_gain_dbi,
                    min_snr_db=mac_model_config.communication_range_snr_threshold_db,
                    noise_figure_db=7.0,
                )

                interference_probs = mac_model.compute_interference_probabilities(
                    tx_node=link.tx_node,
                    rx_node=link.rx_node,
                    interferer_nodes=interferer_nodes,
                    positions=node_positions,
                    communication_range=communication_range,
                    traffic_load=mac_model_config.traffic_load,
                )
            elif mac_model_config.type == "tdma":
                interference_probs = mac_model.compute_interference_probabilities(
                    tx_node=link.tx_node,
                    rx_node=link.rx_node,
                    interferer_nodes=interferer_nodes,
                    all_nodes=list(all_nodes),
                )
            else:
                interference_probs = {}

            # Build interference terms for SINR calculator
            # Compute actual interference power from each interferer using InterferenceEngine
            interferer_infos = []
            for interferer_name in interferer_nodes:
                if interferer_name in node_positions and interferer_name in node_powers:
                    interferer_infos.append(
                        TransmitterInfo(
                            node_name=interferer_name,
                            position=node_positions[interferer_name],
                            tx_power_dbm=node_powers[interferer_name],
                            antenna_gain_dbi=node_gains.get(interferer_name, 0.0),
                            frequency_hz=link.frequency_hz,
                        )
                    )

            # Compute interference at RX using InterferenceEngine
            interference_result = _interference_engine.compute_interference_at_receiver(
                rx_position=rx_pos,
                rx_antenna_gain_dbi=link.rx_gain_dbi,
                rx_node=link.rx_node,
                interferers=interferer_infos,
                active_states={name: True for name in interferer_nodes},  # Assume all active for now
            )

            # Pass all interference terms to SINR calculator
            # The MAC-specific methods will apply probability scaling internally
            interference_terms_list = list(interference_result.interference_terms)

            # Compute SINR using MAC-specific methods
            if mac_model_config.type == "csma":
                # CSMA model: Use probabilistic interference
                sinr_result, mac_metadata = _sinr_calculator.calculate_sinr_with_csma(
                    tx_node=link.tx_node,
                    rx_node=link.rx_node,
                    signal_power_dbm=signal_power_dbm,
                    noise_power_dbm=noise_power_dbm,
                    interference_terms=interference_terms_list,
                    interference_probs=interference_probs,
                )
            elif mac_model_config.type == "tdma":
                # TDMA model: Use slot-based interference
                sinr_result, mac_metadata = _sinr_calculator.calculate_sinr_with_tdma(
                    tx_node=link.tx_node,
                    rx_node=link.rx_node,
                    signal_power_dbm=signal_power_dbm,
                    noise_power_dbm=noise_power_dbm,
                    interference_terms=interference_terms_list,
                    interference_probs=interference_probs,
                )
            else:
                # Fallback: Phase 1 all-transmitting (should not happen with MAC models)
                logger.warning(f"Unknown MAC model type: {mac_model_config.type}")
                sinr_result = _sinr_calculator.calculate_sinr(
                    tx_node=link.tx_node,
                    rx_node=link.rx_node,
                    signal_power_dbm=signal_power_dbm,
                    noise_power_dbm=noise_power_dbm,
                    interference_terms=interference_terms_list,
                )
                mac_metadata = {}

            # Use SINR instead of SNR for MCS selection and BER/BLER/PER calculation
            effective_snr = sinr_result.sinr_db

            # Compute channel parameters using SINR for MAC-aware MCS selection
            result = compute_channel_for_link(
                link,
                path_result,
                effective_metric_db=effective_snr  # Pass SINR for accurate MCS selection
            )

            # Override SNR with SINR and add MAC metadata
            result.snr_db = snr_db  # Keep original SNR (without interference)
            result.sinr_db = effective_snr  # Add SINR (with interference)
            result.mac_model_type = mac_model_config.type

            # Extract MAC-specific metadata from SINR calculation
            if mac_model_config.type == "csma":
                result.hidden_nodes = mac_metadata.get("num_hidden_nodes", 0)
                result.expected_interference_dbm = mac_metadata.get("expected_interference_dbm")
            elif mac_model_config.type == "tdma":
                result.throughput_multiplier = mac_model.get_throughput_multiplier(
                    link.tx_node, all_nodes=list(all_nodes)
                )
                # Apply TDMA slot ownership to rate limit
                result.netem_rate_mbps = result.netem_rate_mbps * result.throughput_multiplier

            results.append(result)

        except Exception as e:
            logger.error(f"Failed to compute SINR for {link.tx_node}->{link.rx_node}: {e}", exc_info=True)
            # Add error result
            results.append(
                ChannelResponse(
                    tx_node=link.tx_node,
                    rx_node=link.rx_node,
                    path_loss_db=200.0,
                    num_paths=0,
                    dominant_path_type="error",
                    received_power_dbm=-200.0,
                    snr_db=-50.0,
                    ber=0.5,
                    bler=1.0,
                    per=1.0,
                    netem_delay_ms=0.0,
                    netem_jitter_ms=0.0,
                    netem_loss_percent=100.0,
                    netem_rate_mbps=0.1,
                    mac_model_type=mac_model_config.type,
                )
            )

    return results


def compute_channel_for_link(
    link: WirelessLinkRequest,
    path_result: PathResult,
    effective_metric_db: float | None = None
) -> ChannelResponse:
    """
    Compute complete channel parameters for a wireless link.

    This function converts ray tracing path results into netem parameters
    via the complete link budget → SNR → BER → BLER → PER pipeline.

    CRITICAL: Antenna Gain Handling
    ================================
    The antenna gains (tx_gain_dbi, rx_gain_dbi) are passed to SNRCalculator
    with from_sionna=True, which means:

    - Path loss from Sionna RT ALREADY INCLUDES antenna pattern gains
    - Antenna gains are NOT added again in SNR calculation
    - This prevents double-counting and ~6-12 dB SNR overestimation

    Formula used (from_sionna=True):
        P_rx = P_tx - channel_loss_db
        (where channel_loss_db includes propagation + antenna effects)

    The antenna gain parameters are accepted in the API for consistency
    but are intentionally ignored when from_sionna=True.

    Supports both adaptive MCS selection (when mcs_table_path is set) and
    fixed modulation/coding (when modulation/fec_type/fec_code_rate are set).

    Args:
        link: Wireless link request with RF parameters
        path_result: Ray tracing results from Sionna PathSolver
        effective_metric_db: Optional SINR value to use instead of SNR for MCS
                           selection and BER/BLER/PER calculation. When provided
                           (MAC model case), uses SINR for accurate modulation
                           selection under interference.

    Returns:
        ChannelResponse with SNR, BER, BLER, PER, and netem parameters

    See Also:
        - SNRCalculator.calculate_link_snr() for antenna gain handling
        - CHANNEL_CODE_REVIEW.md Issue #1 for fix details
    """
    # Calculate SNR first (needed for MCS selection)
    snr_calc = SNRCalculator(
        bandwidth_hz=link.bandwidth_hz, noise_figure_db=7.0  # Typical WiFi NF
    )
    rx_power, snr_db = snr_calc.calculate_link_snr(
        tx_power_dbm=link.tx_power_dbm,
        tx_gain_dbi=link.tx_gain_dbi,  # Passed for API consistency
        rx_gain_dbi=link.rx_gain_dbi,  # Passed for API consistency
        path_loss_db=path_result.path_loss_db,
        from_sionna=True,  # Path loss from RT includes antenna gains (do NOT add again)
    )

    # Use SINR if provided (MAC model case), otherwise SNR
    metric_for_mcs = effective_metric_db if effective_metric_db is not None else snr_db

    # Determine modulation, FEC, and bandwidth based on MCS table or fixed params
    selected_mcs_index: int | None = None
    selected_bandwidth_mhz: float | None = None

    if link.mcs_table_path:
        # Adaptive MCS selection
        mcs_table = get_or_load_mcs_table(link.mcs_table_path, link.mcs_hysteresis_db)
        link_id = f"{link.tx_node}->{link.rx_node}"
        mcs = mcs_table.select_mcs(metric_for_mcs, link_id)

        modulation = mcs.modulation
        fec_type = mcs.fec_type
        fec_code_rate = mcs.code_rate
        selected_mcs_index = mcs.mcs_index

        # Use MCS bandwidth if specified, otherwise use link bandwidth
        if mcs.bandwidth_mhz is not None:
            bandwidth_hz = mcs.bandwidth_mhz * 1e6
            selected_bandwidth_mhz = mcs.bandwidth_mhz
        else:
            bandwidth_hz = link.bandwidth_hz
            selected_bandwidth_mhz = link.bandwidth_hz / 1e6

        metric_name = "SINR" if effective_metric_db is not None else "SNR"
        logger.debug(
            f"Link {link_id}: {metric_name}={metric_for_mcs:.1f}dB -> MCS{mcs.mcs_index} "
            f"({mcs.modulation}, rate={mcs.code_rate})"
        )
    else:
        # Fixed modulation/coding
        modulation = link.modulation or "64qam"
        fec_type = link.fec_type or "ldpc"
        fec_code_rate = link.fec_code_rate if link.fec_code_rate is not None else 0.5
        bandwidth_hz = link.bandwidth_hz

    # Calculate BER with selected modulation
    # Use effective metric (SINR if MAC model, otherwise SNR)
    ber_calc = BERCalculator(modulation)
    ber = ber_calc.theoretical_ber_awgn(metric_for_mcs)

    # Calculate BLER if using FEC
    bler = None
    if fec_type.lower() not in ["none", "uncoded"]:
        bler_calc = BLERCalculator(
            fec_type=fec_type,
            code_rate=fec_code_rate,
            modulation=modulation,
            block_length=min(link.packet_size_bits, 8192),  # Max block size
        )
        bler = bler_calc.approximate_bler(metric_for_mcs)

    # Calculate PER
    per_calc = PERCalculator(fec_type=fec_type)
    per = per_calc.calculate_per(
        ber=ber if fec_type.lower() in ["none", "uncoded"] else None,
        bler=bler,
        packet_bits=link.packet_size_bits,
    )

    # Calculate effective rate with selected modulation/coding/bandwidth
    modulation_bits = get_bits_per_symbol(modulation)
    rate_mbps = PERCalculator.calculate_effective_rate(
        bandwidth_mhz=bandwidth_hz / 1e6,
        modulation_bits=modulation_bits,
        code_rate=fec_code_rate if fec_type.lower() != "none" else 1.0,
        per=per,
    )

    # Convert netem parameters
    delay_ms = path_result.min_delay_ns / 1e6

    # IMPORTANT: Jitter set to 0.0 because delay spread does NOT cause packet jitter
    # - Delay spread is PHY-layer multipath timing dispersion (20-300 ns typical)
    # - For OFDM (WiFi 6), this is absorbed by cyclic prefix (800-3200 ns)
    # - Real packet jitter is caused by MAC layer effects (0.1-10 ms):
    #   * CSMA/CA backoff and contention
    #   * HARQ retransmissions
    #   * Queue dynamics and buffer drain variability
    #   * Frame aggregation (A-MPDU)
    # - Mapping delay_spread_ns to jitter would underestimate by 1000-10000x
    # - To model jitter properly, implement MAC/queue simulation
    jitter_ms = 0.0  # Jitter requires MAC/queue modeling (not currently implemented)

    loss_percent = per * 100.0

    # Validate results for physics sanity
    distance_m = path_result.min_delay_ns * 3e8 / 1e9  # Approx distance from delay
    _validate_channel_result(
        snr_db=snr_db,
        per=per,
        path_loss_db=path_result.path_loss_db,
        frequency_hz=link.frequency_hz,
        distance_m=distance_m,
    )

    return ChannelResponse(
        tx_node=link.tx_node,
        rx_node=link.rx_node,
        path_loss_db=path_result.path_loss_db,
        num_paths=path_result.num_paths,
        dominant_path_type=path_result.dominant_path_type,
        received_power_dbm=rx_power,
        snr_db=snr_db,
        ber=ber,
        bler=bler,
        per=per,
        netem_delay_ms=delay_ms,
        netem_jitter_ms=jitter_ms,
        netem_loss_percent=loss_percent,
        netem_rate_mbps=rate_mbps,
        # MCS selection info
        selected_mcs_index=selected_mcs_index,
        selected_modulation=modulation,
        selected_code_rate=fec_code_rate,
        selected_fec_type=fec_type,
        selected_bandwidth_mhz=selected_bandwidth_mhz,
    )


# ============================================================================
# API Endpoints
# ============================================================================


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check server health and capabilities."""
    gpu_available = False
    if is_sionna_available():
        try:
            import tensorflow as tf

            gpu_available = len(tf.config.list_physical_devices("GPU")) > 0
        except Exception:
            pass

    return HealthResponse(
        status="healthy",
        sionna_available=is_sionna_available(),
        gpu_available=gpu_available,
        scene_loaded=_engine is not None and getattr(_engine, "_scene_loaded", False),
    )


@app.post("/scene/load", response_model=SceneLoadResponse)
async def load_scene(config: SceneConfig) -> SceneLoadResponse:
    """
    Load or reload the ray tracing scene.

    Call this before computing channels.
    """
    global _engine

    if _engine is None:
        _engine = get_engine()

    try:
        _engine.load_scene(
            scene_path=config.scene_file,
            frequency_hz=config.frequency_hz,
            bandwidth_hz=config.bandwidth_hz,
        )

        return SceneLoadResponse(
            status="success",
            scene_file=config.scene_file,
            frequency_ghz=config.frequency_hz / 1e9,
            bandwidth_mhz=config.bandwidth_hz / 1e6,
        )

    except Exception as e:
        logger.error("Failed to load scene: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to load scene: {str(e)}"
        ) from e


@app.post("/compute/single", response_model=ChannelResponse)
async def compute_single_link(request: WirelessLinkRequest):
    """Compute channel parameters for a single wireless link."""
    global _engine, _path_cache, _device_positions

    if _engine is None:
        _engine = get_engine()

    # Ensure scene is loaded
    if not getattr(_engine, "_scene_loaded", False):
        _engine.load_scene(frequency_hz=request.frequency_hz, bandwidth_hz=request.bandwidth_hz)

    try:
        # Clear previous devices and add new ones
        _engine.clear_devices()
        tx_pos = request.tx_position.as_tuple()
        rx_pos = request.rx_position.as_tuple()

        _engine.add_transmitter(
            name=request.tx_node,
            position=tx_pos,
            antenna_pattern=request.antenna_pattern,
            polarization=request.polarization,
        )
        _engine.add_receiver(
            name=request.rx_node,
            position=rx_pos,
            antenna_pattern=request.antenna_pattern,
            polarization=request.polarization,
        )

        # Compute paths
        path_result = _engine.compute_paths()

        # Cache path details for visualization
        path_details = _engine.get_path_details()
        cache_path_for_visualization(
            tx_node=request.tx_node,
            rx_node=request.rx_node,
            tx_pos=tx_pos,
            rx_pos=rx_pos,
            path_result=path_result,
            path_details=path_details,
            bandwidth_hz=request.bandwidth_hz
        )

        # Compute complete channel parameters
        return compute_channel_for_link(request, path_result)

    except Exception as e:
        logger.error(f"Channel computation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Computation failed: {str(e)}")


@app.post("/compute/batch", response_model=BatchChannelResponse)
async def compute_batch_links(request: BatchChannelRequest):
    """
    Compute channel parameters for multiple wireless links.

    More efficient than calling /compute/single multiple times as the
    scene is loaded once and reused.

    Supports MAC models (CSMA or TDMA) for interference-aware channel computation.
    """
    global _engine, _interference_engine, _sinr_calculator

    if _engine is None:
        _engine = get_engine()

    start_time = time.time()

    # Load scene
    _engine.load_scene(
        scene_path=request.scene.scene_file,
        frequency_hz=request.scene.frequency_hz,
        bandwidth_hz=request.scene.bandwidth_hz,
    )

    # Check if any links use MAC models
    mac_model_config = None
    for link in request.links:
        if link.mac_model is not None:
            mac_model_config = link.mac_model
            break

    results = []

    # Branch: MAC model mode vs. simple SNR mode
    if mac_model_config is not None:
        # MAC model mode: Use SINR computation with interference
        results = await _compute_batch_with_mac_model(
            request.links, mac_model_config, request.scene
        )
    else:
        # Simple SNR mode: Compute each link independently (original behavior)
        for link in request.links:
            try:
                # Clear and set up devices for this link
                _engine.clear_devices()
                tx_pos = link.tx_position.as_tuple()
                rx_pos = link.rx_position.as_tuple()

                _engine.add_transmitter(
                    name=link.tx_node,
                    position=tx_pos,
                    antenna_pattern=link.antenna_pattern,
                    polarization=link.polarization,
                )
                _engine.add_receiver(
                    name=link.rx_node,
                    position=rx_pos,
                    antenna_pattern=link.antenna_pattern,
                    polarization=link.polarization,
                )

                # Compute paths
                path_result = _engine.compute_paths()

                # Cache path details for visualization
                path_details = _engine.get_path_details()
                cache_path_for_visualization(
                    tx_node=link.tx_node,
                    rx_node=link.rx_node,
                    tx_pos=tx_pos,
                    rx_pos=rx_pos,
                    path_result=path_result,
                    path_details=path_details,
                    bandwidth_hz=link.bandwidth_hz
                )

                # Compute complete channel
                result = compute_channel_for_link(link, path_result)
                results.append(result)

            except Exception as e:
                logger.error(f"Failed to compute channel for {link.tx_node}->{link.rx_node}: {e}")
                # Add error result
                results.append(
                    ChannelResponse(
                        tx_node=link.tx_node,
                        rx_node=link.rx_node,
                        path_loss_db=200.0,
                        num_paths=0,
                        dominant_path_type="error",
                        received_power_dbm=-200.0,
                        snr_db=-50.0,
                        ber=0.5,
                        bler=1.0,
                        per=1.0,
                        netem_delay_ms=0.0,
                        netem_jitter_ms=0.0,
                        netem_loss_percent=100.0,
                        netem_rate_mbps=0.1,
                    )
                )

    computation_time_ms = (time.time() - start_time) * 1000

    return BatchChannelResponse(results=results, computation_time_ms=computation_time_ms)


@app.post("/debug/paths", response_model=PathDetailsResponse)
async def get_path_details(request: PathDetailsRequest):
    """
    Get detailed ray tracing path information for debugging.

    Returns information about all propagation paths between TX and RX,
    including interaction types (reflection, refraction) and vertices
    (bounce points).

    Requires scene to be loaded first via POST /scene/load.
    """
    global _engine

    if _engine is None:
        raise HTTPException(status_code=400, detail="Engine not initialized")

    if not getattr(_engine, "_scene_loaded", False):
        raise HTTPException(status_code=400, detail="Scene not loaded. Call POST /scene/load first.")

    try:
        # Set up TX/RX
        _engine.clear_devices()
        _engine.add_transmitter(
            name=request.tx_name,
            position=request.tx_position.as_tuple(),
            antenna_pattern=request.antenna_pattern,
            polarization=request.polarization,
        )
        _engine.add_receiver(
            name=request.rx_name,
            position=request.rx_position.as_tuple(),
            antenna_pattern=request.antenna_pattern,
            polarization=request.polarization,
        )

        # Get path details
        details: PathDetails = _engine.get_path_details()

        # Convert to response format
        path_responses = []
        for p in details.paths:
            path_responses.append(SinglePathInfoResponse(
                path_index=p.path_index,
                delay_ns=p.delay_ns,
                power_db=p.power_db,
                interaction_types=p.interaction_types,
                vertices=[list(v) for v in p.vertices],
                is_los=p.is_los,
            ))

        # Get strongest and shortest paths
        strongest = None
        shortest = None
        if details.strongest_path_index >= 0 and details.strongest_path_index < len(path_responses):
            strongest = path_responses[details.strongest_path_index]
        if details.shortest_path_index >= 0 and details.shortest_path_index < len(path_responses):
            shortest = path_responses[details.shortest_path_index]

        return PathDetailsResponse(
            tx_position=list(details.tx_position),
            rx_position=list(details.rx_position),
            distance_m=details.distance_m,
            num_paths=details.num_paths,
            paths=path_responses,
            strongest_path_index=details.strongest_path_index,
            shortest_path_index=details.shortest_path_index,
            strongest_path=strongest,
            shortest_path=shortest,
        )

    except Exception as e:
        logger.error(f"Failed to get path details: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get path details: {str(e)}")


@app.post("/compute/sinr", response_model=SINRResponse)
async def compute_sinr(request: SINRLinkRequest):
    """
    Compute SINR for a link with multi-transmitter interference.

    Computes Signal-to-Interference-plus-Noise Ratio (SINR) for a wireless link
    considering interference from other active transmitters. Uses PathSolver to
    compute interference power from each interferer.

    Phase 1: Same-frequency (co-channel) interference only.
    """
    global _interference_engine, _sinr_calculator

    # Initialize interference engine if needed
    if _interference_engine is None:
        from sine.channel.interference_engine import InterferenceEngine
        _interference_engine = InterferenceEngine()
        logger.info("Initialized InterferenceEngine for SINR computation")

    # Initialize SINR calculator if needed
    if _sinr_calculator is None:
        _sinr_calculator = SINRCalculator(
            rx_sensitivity_dbm=request.rx_sensitivity_dbm,
            apply_capture_effect=request.apply_capture_effect,
            capture_threshold_db=request.capture_threshold_db,
        )

    # Load scene if not loaded
    if not _interference_engine._scene_loaded:
        _interference_engine.load_scene(
            scene_path=None,  # Use empty scene for now
            frequency_hz=request.frequency_hz,
            bandwidth_hz=request.bandwidth_hz,
        )

    try:
        # Compute signal power using PathSolver
        _interference_engine._engine.clear_devices()
        _interference_engine._engine.add_transmitter(
            name=request.tx_node,
            position=request.tx_position.as_tuple(),
            antenna_pattern=request.antenna_pattern,
            polarization=request.polarization,
        )
        _interference_engine._engine.add_receiver(
            name=request.rx_node,
            position=request.rx_position.as_tuple(),
            antenna_pattern=request.antenna_pattern,
            polarization=request.polarization,
        )

        # Get path loss for signal
        path_result = _interference_engine._engine.compute_paths()

        # Compute signal power: P_tx + G_tx + G_rx - PL
        signal_power_dbm = (
            request.tx_power_dbm
            + request.tx_gain_dbi
            + request.rx_gain_dbi
            - path_result.path_loss_db
        )

        # Calculate thermal noise
        noise_power_dbm = calculate_thermal_noise(
            bandwidth_hz=request.bandwidth_hz,
            noise_figure_db=7.0,  # WiFi 6 typical
        )

        # Convert interferer infos to TransmitterInfo list
        interferers = [
            TransmitterInfo(
                node_name=intf.node_name,
                position=intf.position.as_tuple(),
                tx_power_dbm=intf.tx_power_dbm,
                antenna_gain_dbi=intf.antenna_gain_dbi,
                frequency_hz=intf.frequency_hz,
                bandwidth_hz=intf.bandwidth_hz,
            )
            for intf in request.interferers
        ]

        # Build active states dict
        active_states = {
            intf.node_name: intf.is_active
            for intf in request.interferers
        }

        # Compute interference with ACLR (Phase 2: Adjacent-Channel Interference)
        interference_result = _interference_engine.compute_interference_at_receiver(
            rx_position=request.rx_position.as_tuple(),
            rx_antenna_gain_dbi=request.rx_gain_dbi,
            rx_node=request.rx_node,
            interferers=interferers,
            active_states=active_states,
            rx_frequency_hz=request.frequency_hz,
            rx_bandwidth_hz=request.bandwidth_hz,
        )

        # Calculate SINR
        sinr_result = _sinr_calculator.calculate_sinr(
            tx_node=request.tx_node,
            rx_node=request.rx_node,
            signal_power_dbm=signal_power_dbm,
            noise_power_dbm=noise_power_dbm,
            interference_terms=interference_result.interference_terms,
        )

        # Build response
        return SINRResponse(
            tx_node=sinr_result.tx_node,
            rx_node=sinr_result.rx_node,
            signal_power_dbm=sinr_result.signal_power_dbm,
            noise_power_dbm=sinr_result.noise_power_dbm,
            total_interference_dbm=sinr_result.total_interference_dbm,
            snr_db=sinr_result.snr_db,
            sinr_db=sinr_result.sinr_db,
            num_interferers=len(request.interferers),
            num_active_interferers=sinr_result.num_interferers,
            regime=sinr_result.regime,
            capture_effect_applied=sinr_result.capture_effect_applied,
            num_suppressed_interferers=sinr_result.num_suppressed_interferers,
        )

    except Exception as e:
        logger.error(f"Failed to compute SINR: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to compute SINR: {str(e)}")


@app.get("/api/visualization/state")
async def get_visualization_state():
    """
    Get complete visualization state (scene, devices, paths).

    Returns cached data from previous channel computations.
    No ray tracing is performed - this is instant.

    Returns:
        dict: Visualization state containing scene geometry, device positions, and cached paths

    Raises:
        HTTPException: 404 if no scene is loaded
    """
    global _engine, _path_cache, _device_positions

    if not _engine or not getattr(_engine, "_scene_loaded", False):
        raise HTTPException(status_code=404, detail="No scene loaded")

    # Extract scene geometry
    scene_objects = []
    try:
        for name, obj in _engine.scene.objects.items():
            pos = obj.position
            bbox = obj.mi_mesh.bbox()
            scene_objects.append({
                "name": name,
                "material": obj.radio_material.name,
                "center": [float(pos[0][0]), float(pos[1][0]), float(pos[2][0])],
                "bbox_min": [float(bbox.min[0]), float(bbox.min[1]), float(bbox.min[2])],
                "bbox_max": [float(bbox.max[0]), float(bbox.max[1]), float(bbox.max[2])]
            })
    except Exception as e:
        logger.warning(f"Failed to extract scene geometry: {e}")
        scene_objects = []

    # Convert device positions to simple dict
    devices = [{
        "name": name,
        "position": {"x": pos[0], "y": pos[1], "z": pos[2]}
    } for name, pos in _device_positions.items()]

    # Return cached paths (already JSON-serializable)
    paths = list(_path_cache.values())

    return {
        "scene_file": str(_engine.scene_path) if hasattr(_engine, 'scene_path') else None,
        "scene_loaded": True,
        "scene_objects": scene_objects,
        "devices": devices,
        "paths": paths,
        "cache_size": len(_path_cache)
    }


# ============================================================================
# Main entry point for standalone server
# ============================================================================


def run_server(host: str = "0.0.0.0", port: int = 8000):
    """Run the channel computation server."""
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_server()
