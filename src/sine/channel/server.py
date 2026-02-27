"""
FastAPI Channel Computation Server.

Provides REST API endpoints for computing wireless channel parameters
using Sionna ray tracing. Returns netem parameters for network emulation.

Endpoints:
- POST /compute/link - Compute channel for single link
- POST /compute/links_snr - Independent per-link SNR (no interference, O(N))
- POST /compute/links_sinr - Interference-aware topology SINR (O(N²))
- POST /compute/interference - Compute SINR with explicit TX/RX/interferers
- POST /scene/load - Load/reload ray tracing scene
- POST /debug/paths - Get detailed path info for debugging (vertices, interactions)
- GET /health - Health check with GPU status
- GET /visualization/state - Get cached visualization data (scene, devices, paths)
"""

import logging
import time
from contextlib import asynccontextmanager
from enum import Enum

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from sine.channel.sionna_engine import is_sionna_available, PathResult, PathDetails
from sine.channel.path_cache import PathCache
from sine.channel.engine_registry import EngineRegistry
from sine.channel.batch_sinr import LinksSinrComputer
from sine.channel.snr import SNRCalculator
from sine.channel.modulation import BERCalculator, BLERCalculator, get_bits_per_symbol
from sine.channel.per_calculator import PERCalculator
from sine.channel.mcs import MCSTable
from sine.channel.interference_utils import SINRCalculator, calculate_thermal_noise
from sine.channel.interference_calculator import InterferenceEngine, TransmitterInfo

logger = logging.getLogger(__name__)

# Global MCS table cache
_mcs_tables: dict[str, MCSTable] = {}

# Global engine registry
_engine_registry = EngineRegistry()

# Global links SINR computer (encapsulates interference engine + SINR calculator)
_links_sinr_computer = LinksSinrComputer()

# Global path cache for visualization
_path_cache_obj = PathCache()

# Global interference engine and SINR calculator for /compute/interference endpoint
_interference_engine: InterferenceEngine | None = None
_sinr_calculator: SINRCalculator | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Engine will be lazy-loaded on first request based on engine_type
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


class EngineType(str, Enum):
    """Channel computation engine selection."""
    AUTO = "auto"        # Default: use Sionna if available, else fallback
    SIONNA = "sionna"    # Force Sionna RT (error if unavailable)
    FALLBACK = "fallback"  # Force FSPL fallback (no GPU needed)


class SionnaUnavailableError(HTTPException):
    """Raised when Sionna engine requested but unavailable."""
    def __init__(self):
        super().__init__(
            status_code=503,
            detail="Sionna engine requested but unavailable (GPU/CUDA required)"
        )


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
    tx_interface: str | None = Field(
        default=None,
        description="TX interface name for interface-level SINR identity (e.g., 'eth1')"
    )
    rx_interface: str | None = Field(
        default=None,
        description="RX interface name for interface-level SINR identity (e.g., 'eth1')"
    )
    tx_position: Position
    rx_position: Position
    tx_power_dbm: float = Field(default=20.0, description="Transmit power in dBm")
    tx_gain_dbi: float = Field(default=0.0, description="TX antenna gain in dBi")
    rx_gain_dbi: float = Field(default=0.0, description="RX antenna gain in dBi")
    antenna_pattern: str = Field(default="iso", description="Antenna pattern: iso, dipole, hw_dipole, tr38901")
    polarization: str = Field(default="V", description="Antenna polarization: V, H, VH, cross")
    frequency_hz: float = Field(default=5.18e9, description="TX frequency in Hz")
    bandwidth_hz: float = Field(default=80e6, description="TX bandwidth in Hz")
    rx_frequency_hz: float | None = Field(default=None, description="RX frequency in Hz (for ACLR, defaults to frequency_hz)")
    rx_bandwidth_hz: float | None = Field(default=None, description="RX bandwidth in Hz (for ACLR, defaults to bandwidth_hz)")
    noise_figure_db: float = Field(
        default=7.0,
        ge=0.0,
        le=20.0,
        description="Receiver noise figure in dB (WiFi 6: 6-8 dB)"
    )
    engine_type: EngineType = Field(default=EngineType.AUTO, description="Channel engine: auto, sionna, or fallback")
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

    def iface_key(self) -> str:
        """Return interface-level key ('node:iface') or node-level key ('node') for identification."""
        if self.tx_interface:
            return f"{self.tx_node}:{self.tx_interface}"
        return self.tx_node

    def rx_iface_key(self) -> str:
        """Return RX interface-level key ('node:iface') or node-level key ('node')."""
        if self.rx_interface:
            return f"{self.rx_node}:{self.rx_interface}"
        return self.rx_node


class ChannelResponse(BaseModel):
    """Response with computed channel parameters."""

    tx_node: str
    rx_node: str
    # Engine metadata
    engine_used: EngineType
    # Ray tracing results
    path_loss_db: float
    num_paths: int
    dominant_path_type: str
    delay_spread_ns: float  # RMS delay spread in nanoseconds
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


class LinksSnrRequest(BaseModel):
    """Request to compute independent per-link SNR (no interference)."""

    scene: SceneConfig = Field(default_factory=SceneConfig)
    links: list[WirelessLinkRequest]
    active_states: dict[str, bool] = Field(
        default_factory=dict,
        description="Interface active states ('node:interface' -> is_active, e.g. 'node1:eth1' -> True)"
    )


class LinksSinrRequest(BaseModel):
    """Request to compute interference-aware SINR across a topology."""

    scene: SceneConfig = Field(default_factory=SceneConfig)
    links: list[WirelessLinkRequest]
    active_states: dict[str, bool] = Field(
        default_factory=dict,
        description="Interface active states ('node:interface' -> is_active, e.g. 'node1:eth1' -> True)"
    )


class LinksResponse(BaseModel):
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


class InterferenceRequest(BaseModel):
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
    engine_type: EngineType = Field(default=EngineType.AUTO, description="Channel engine: auto, sionna, or fallback")

    # Interferers
    interferers: list["InterfererInfo"]

    # SINR calculator settings
    rx_sensitivity_dbm: float = Field(default=-80.0, description="Receiver sensitivity floor")
    noise_figure_db: float = Field(
        default=7.0,
        ge=0.0,
        le=20.0,
        description="Receiver noise figure in dB (WiFi 6: 6-8 dB)"
    )
    apply_capture_effect: bool = Field(default=False, description="Enable capture effect")
    capture_threshold_db: float = Field(default=6.0, description="Capture threshold in dB")


class InterfererInfo(BaseModel):
    """Information about an interfering transmitter."""

    node_name: str
    position: Position
    tx_power_dbm: float
    antenna_gain_dbi: float | None = Field(default=None, description="Explicit antenna gain in dBi (mutually exclusive with antenna_pattern)")
    antenna_pattern: str | None = Field(default=None, description="Antenna pattern name (mutually exclusive with antenna_gain_dbi)")
    frequency_hz: float
    bandwidth_hz: float = Field(default=80e6, description="Transmitter channel bandwidth in Hz")
    is_active: bool = Field(default=True, description="Whether this interferer is currently transmitting")


class InterferenceResponse(BaseModel):
    """Response with SINR computation results."""

    tx_node: str
    rx_node: str
    # Engine metadata
    engine_used: EngineType

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
    sinr_db: float | None = None,
) -> None:
    """Validate channel computation results for physics sanity."""
    # Use SINR if available (interference mode), otherwise SNR
    effective_metric = sinr_db if sinr_db is not None else snr_db
    metric_name = "SINR" if sinr_db is not None else "SNR"

    # Check SNR/SINR range
    if effective_metric > 50.0:
        logger.warning(
            f"{metric_name}={effective_metric:.1f} dB exceeds typical range (< 50 dB) - "
            f"possible antenna gain double-counting"
        )

    if effective_metric < -20.0:
        logger.warning(f"{metric_name}={effective_metric:.1f} dB very low - link likely unusable")

    # Check PER vs SNR/SINR correlation
    if effective_metric > 25.0 and per > 0.1:
        logger.warning(
            f"High {metric_name} ({effective_metric:.1f} dB) but high PER ({per:.2%}) - "
            f"possible BER calculation error"
        )
    elif sinr_db is not None and sinr_db < 10.0 and per > 0.5:
        # Expected behavior: low SINR causes high PER (co-channel interference)
        logger.debug(
            f"Low SINR ({sinr_db:.1f} dB, SNR={snr_db:.1f} dB) causing high PER ({per:.2%}) - "
            f"expected with strong co-channel interference"
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


def compute_channel_for_link(
    link: WirelessLinkRequest,
    path_result: PathResult,
    engine_used: EngineType,
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
    # Determine if path loss includes antenna gains (depends on engine type)
    # Sionna RT: path loss includes antenna pattern gains (from_sionna=True, do NOT add again)
    # FallbackEngine: FSPL only, antenna gains NOT included (from_sionna=False, add them)
    from_sionna = (engine_used == EngineType.SIONNA)

    # Calculate SNR first (needed for MCS selection)
    snr_calc = SNRCalculator(
        bandwidth_hz=link.bandwidth_hz, noise_figure_db=link.noise_figure_db
    )
    rx_power, snr_db = snr_calc.calculate_link_snr(
        tx_power_dbm=link.tx_power_dbm,
        tx_gain_dbi=link.tx_gain_dbi,  # Sionna: ignored, Fallback: added
        rx_gain_dbi=link.rx_gain_dbi,  # Sionna: ignored, Fallback: added
        path_loss_db=path_result.path_loss_db,
        from_sionna=from_sionna,  # False for FallbackEngine, True for SionnaEngine
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
        sinr_db=effective_metric_db if effective_metric_db != snr_db else None,
    )

    return ChannelResponse(
        tx_node=link.tx_node,
        rx_node=link.rx_node,
        engine_used=engine_used,
        path_loss_db=path_result.path_loss_db,
        num_paths=path_result.num_paths,
        dominant_path_type=path_result.dominant_path_type,
        delay_spread_ns=path_result.delay_spread_ns,
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
        scene_loaded=(
            _engine_registry.primary_engine is not None
            and getattr(_engine_registry.primary_engine, "_scene_loaded", False)
        ),
    )


@app.post("/scene/load", response_model=SceneLoadResponse)
async def load_scene(config: SceneConfig) -> SceneLoadResponse:
    """
    Load or reload the ray tracing scene.

    Call this before computing channels.
    """
    engine = _engine_registry.get("auto")

    try:
        engine.load_scene(
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


def _run_single_path(
    engine,
    link,
    path_cache: PathCache,
) -> tuple[PathResult, PathDetails]:
    """Clear devices, compute paths for one link, cache results, and return (path_result, path_details)."""
    engine.clear_devices()
    tx_pos = link.tx_position.as_tuple()
    rx_pos = link.rx_position.as_tuple()

    engine.add_transmitter(
        name=link.tx_node,
        position=tx_pos,
        antenna_pattern=link.antenna_pattern,
        polarization=link.polarization,
    )
    engine.add_receiver(
        name=link.rx_node,
        position=rx_pos,
        antenna_pattern=link.antenna_pattern,
        polarization=link.polarization,
    )

    path_result = engine.compute_paths()
    path_details = engine.get_path_details()

    path_cache.store(
        tx_node=link.tx_node,
        rx_node=link.rx_node,
        tx_pos=tx_pos,
        rx_pos=rx_pos,
        path_result=path_result,
        path_details=path_details,
        bandwidth_hz=link.bandwidth_hz,
    )

    return path_result, path_details


@app.post("/compute/link", response_model=ChannelResponse)
async def compute_single_link(request: WirelessLinkRequest):
    """Compute channel parameters for a single wireless link."""
    # Get engine based on request type
    engine = _engine_registry.get(request.engine_type.value)
    engine_used = EngineType(engine.engine_type)

    # Ensure scene is loaded
    if not getattr(engine, "_scene_loaded", False):
        engine.load_scene(frequency_hz=request.frequency_hz, bandwidth_hz=request.bandwidth_hz)

    try:
        path_result, _ = _run_single_path(engine, request, _path_cache_obj)

        # Compute complete channel parameters
        return compute_channel_for_link(request, path_result, engine_used)

    except Exception as e:
        logger.error(f"Channel computation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Computation failed: {str(e)}")


@app.post("/compute/links_snr", response_model=LinksResponse)
async def compute_links_snr(request: LinksSnrRequest):
    """
    Compute independent per-link SNR for multiple wireless links.

    Each link is computed independently (O(N)); no interference modeling.
    More efficient than calling /compute/link multiple times as the
    scene is loaded once and reused.

    Supports MAC models (CSMA or TDMA) for throughput computation.
    """
    engine_type = request.links[0].engine_type if request.links else EngineType.AUTO
    engine = _engine_registry.get(engine_type.value)
    engine_used = EngineType(engine.engine_type)

    start_time = time.time()

    engine.load_scene(
        scene_path=request.scene.scene_file,
        frequency_hz=request.scene.frequency_hz,
        bandwidth_hz=request.scene.bandwidth_hz,
    )

    results = []
    for link in request.links:
        try:
            path_result, _ = _run_single_path(engine, link, _path_cache_obj)
            result = compute_channel_for_link(link, path_result, engine_used)
            results.append(result)

        except Exception as e:
            logger.error(f"Failed to compute channel for {link.tx_node}->{link.rx_node}: {e}")
            results.append(
                ChannelResponse(
                    tx_node=link.tx_node,
                    rx_node=link.rx_node,
                    engine_used=engine_used,
                    path_loss_db=200.0,
                    num_paths=0,
                    dominant_path_type="error",
                    delay_spread_ns=0.0,
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
    return LinksResponse(results=results, computation_time_ms=computation_time_ms)


@app.post("/compute/links_sinr", response_model=LinksResponse)
async def compute_links_sinr(request: LinksSinrRequest):
    """
    Compute interference-aware SINR for a full wireless topology.

    Models co-channel interference from all active transmitters (O(N²)).
    Supports MAC models (CSMA or TDMA) for interference probability weighting.
    """
    engine_type = request.links[0].engine_type if request.links else EngineType.AUTO
    engine = _engine_registry.get(engine_type.value)
    engine_used = EngineType(engine.engine_type)

    start_time = time.time()

    engine.load_scene(
        scene_path=request.scene.scene_file,
        frequency_hz=request.scene.frequency_hz,
        bandwidth_hz=request.scene.bandwidth_hz,
    )

    mac_model_config = None
    for link in request.links:
        if link.mac_model is not None:
            mac_model_config = link.mac_model
            break

    results = await _links_sinr_computer.compute(
        request.links,
        mac_model_config,
        request.scene,
        engine,
        engine_used,
        request.active_states,
        mcs_tables=_mcs_tables,
        path_cache=_path_cache_obj,
    )

    computation_time_ms = (time.time() - start_time) * 1000
    return LinksResponse(results=results, computation_time_ms=computation_time_ms)


@app.post("/debug/paths", response_model=PathDetailsResponse)
async def get_path_details(request: PathDetailsRequest):
    """
    Get detailed ray tracing path information for debugging.

    Returns information about all propagation paths between TX and RX,
    including interaction types (reflection, refraction) and vertices
    (bounce points).

    Requires scene to be loaded first via POST /scene/load.
    """
    engine = _engine_registry.primary_engine

    if engine is None:
        raise HTTPException(status_code=400, detail="Engine not initialized")

    if not getattr(engine, "_scene_loaded", False):
        raise HTTPException(status_code=400, detail="Scene not loaded. Call POST /scene/load first.")

    try:
        # Set up TX/RX
        engine.clear_devices()
        engine.add_transmitter(
            name=request.tx_name,
            position=request.tx_position.as_tuple(),
            antenna_pattern=request.antenna_pattern,
            polarization=request.polarization,
        )
        engine.add_receiver(
            name=request.rx_name,
            position=request.rx_position.as_tuple(),
            antenna_pattern=request.antenna_pattern,
            polarization=request.polarization,
        )

        # Get path details
        details: PathDetails = engine.get_path_details()

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


def resolve_antenna_gain(
    antenna_pattern: str | None,
    antenna_gain_dbi: float | None,
) -> float:
    """
    Resolve antenna gain from either pattern name or explicit value.

    Args:
        antenna_pattern: Sionna pattern name (iso/dipole/hw_dipole/tr38901)
        antenna_gain_dbi: Explicit gain in dBi

    Returns:
        Antenna gain in dBi

    Raises:
        ValueError: If neither or both are specified
    """
    from sine.channel.antenna_patterns import get_antenna_gain

    has_pattern = antenna_pattern is not None
    has_gain = antenna_gain_dbi is not None

    if has_pattern and has_gain:
        raise ValueError("Cannot specify both antenna_pattern and antenna_gain_dbi")
    if not has_pattern and not has_gain:
        raise ValueError("Must specify either antenna_pattern or antenna_gain_dbi")

    return get_antenna_gain(antenna_pattern) if has_pattern else antenna_gain_dbi


@app.post("/compute/interference", response_model=InterferenceResponse)
async def compute_sinr(request: InterferenceRequest):
    """
    Compute SINR for a link with multi-transmitter interference.

    Computes Signal-to-Interference-plus-Noise Ratio (SINR) for a wireless link
    considering interference from other active transmitters. Uses PathSolver to
    compute interference power from each interferer.

    Phase 1: Same-frequency (co-channel) interference only.
    """
    global _interference_engine, _sinr_calculator

    # Get engine based on request type
    engine = _engine_registry.get(request.engine_type.value)
    engine_used = EngineType(engine.engine_type)

    # Initialize interference engine if needed
    if _interference_engine is None:
        from sine.channel.interference_calculator import InterferenceEngine
        _interference_engine = InterferenceEngine()
        logger.info("Initialized InterferenceEngine for SINR computation")

    # Initialize SINR calculator if needed
    if _sinr_calculator is None:
        _sinr_calculator = SINRCalculator(
            rx_sensitivity_dbm=request.rx_sensitivity_dbm,
            noise_figure_db=request.noise_figure_db,
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
        # Compute signal power using the selected engine
        engine.clear_devices()
        engine.add_transmitter(
            name=request.tx_node,
            position=request.tx_position.as_tuple(),
            antenna_pattern=request.antenna_pattern,
            polarization=request.polarization,
        )
        engine.add_receiver(
            name=request.rx_node,
            position=request.rx_position.as_tuple(),
            antenna_pattern=request.antenna_pattern,
            polarization=request.polarization,
        )

        # Get path loss for signal
        path_result = engine.compute_paths()

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
            noise_figure_db=request.noise_figure_db,
        )

        # Convert interferer infos to TransmitterInfo list
        # Pass both antenna_pattern and antenna_gain_dbi through - InterferenceEngine will use pattern if available
        interferers = [
            TransmitterInfo(
                node_name=intf.node_name,
                position=intf.position.as_tuple(),
                tx_power_dbm=intf.tx_power_dbm,
                antenna_gain_dbi=intf.antenna_gain_dbi,
                antenna_pattern=intf.antenna_pattern,
                polarization="V",  # TODO: Add polarization field to InterfererInfo if needed
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
            rx_antenna_pattern=request.antenna_pattern,
            rx_polarization=request.polarization,
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
        return InterferenceResponse(
            tx_node=sinr_result.tx_node,
            rx_node=sinr_result.rx_node,
            engine_used=engine_used,
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


@app.get("/visualization/state")
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
    engine = _engine_registry.primary_engine

    if not engine or not getattr(engine, "_scene_loaded", False):
        raise HTTPException(status_code=404, detail="No scene loaded")

    # Extract scene geometry
    scene_objects = []
    try:
        for name, obj in engine.scene.objects.items():
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
        logger.warning("Failed to extract scene geometry: %s", e)
        scene_objects = []

    devices = [
        {"name": name, "position": {"x": pos[0], "y": pos[1], "z": pos[2]}}
        for name, pos in _path_cache_obj.positions.items()
    ]

    paths = list(_path_cache_obj.links.values())

    return {
        "scene_file": str(engine.scene_path) if hasattr(engine, "scene_path") else None,
        "scene_loaded": True,
        "scene_objects": scene_objects,
        "devices": devices,
        "paths": paths,
        "cache_size": len(_path_cache_obj.links),
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
