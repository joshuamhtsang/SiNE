"""
FastAPI Channel Computation Server.

Provides REST API endpoints for computing wireless channel parameters
using Sionna ray tracing. Returns netem parameters for network emulation.

Endpoints:
- POST /compute/single - Compute channel for single link
- POST /compute/batch - Compute channels for multiple links (efficient)
- POST /scene/load - Load/reload ray tracing scene
- POST /debug/paths - Get detailed path info for debugging (vertices, interactions)
- GET /health - Health check with GPU status
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

logger = logging.getLogger(__name__)

# Global engine instance
_engine = None


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
    modulation: str = Field(default="64qam")
    fec_type: str = Field(default="ldpc")
    fec_code_rate: float = Field(default=0.5)
    packet_size_bits: int = Field(default=12000, description="Packet size in bits")


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


# ============================================================================
# Helper Functions
# ============================================================================


def compute_channel_for_link(
    link: WirelessLinkRequest, path_result: PathResult
) -> ChannelResponse:
    """
    Compute complete channel parameters for a link given path results.

    Args:
        link: Link parameters
        path_result: Ray tracing path results

    Returns:
        Complete channel response with netem parameters
    """
    # Calculate SNR
    snr_calc = SNRCalculator(
        bandwidth_hz=link.bandwidth_hz, noise_figure_db=7.0  # Typical WiFi NF
    )
    rx_power, snr_db = snr_calc.calculate_link_snr(
        tx_power_dbm=link.tx_power_dbm,
        tx_gain_dbi=link.tx_gain_dbi,
        rx_gain_dbi=link.rx_gain_dbi,
        path_loss_db=path_result.path_loss_db,
    )

    # Calculate BER
    ber_calc = BERCalculator(link.modulation)
    ber = ber_calc.theoretical_ber_awgn(snr_db)

    # Calculate BLER if using FEC
    bler = None
    if link.fec_type.lower() not in ["none", "uncoded"]:
        bler_calc = BLERCalculator(
            fec_type=link.fec_type,
            code_rate=link.fec_code_rate,
            modulation=link.modulation,
            block_length=min(link.packet_size_bits, 8192),  # Max block size
        )
        bler = bler_calc.approximate_bler(snr_db)

    # Calculate PER
    per_calc = PERCalculator(fec_type=link.fec_type)
    per = per_calc.calculate_per(
        ber=ber if link.fec_type.lower() in ["none", "uncoded"] else None,
        bler=bler,
        packet_bits=link.packet_size_bits,
    )

    # Calculate effective rate
    modulation_bits = get_bits_per_symbol(link.modulation)
    rate_mbps = PERCalculator.calculate_effective_rate(
        bandwidth_mhz=link.bandwidth_hz / 1e6,
        modulation_bits=modulation_bits,
        code_rate=link.fec_code_rate if link.fec_type.lower() != "none" else 1.0,
        per=per,
    )

    # Convert netem parameters
    delay_ms = path_result.min_delay_ns / 1e6
    jitter_ms = path_result.delay_spread_ns / 1e6
    loss_percent = per * 100.0

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
    global _engine

    if _engine is None:
        _engine = get_engine()

    # Ensure scene is loaded
    if not getattr(_engine, "_scene_loaded", False):
        _engine.load_scene(frequency_hz=request.frequency_hz, bandwidth_hz=request.bandwidth_hz)

    try:
        # Clear previous devices and add new ones
        _engine.clear_devices()
        _engine.add_transmitter(
            name=request.tx_node,
            position=request.tx_position.as_tuple(),
            antenna_pattern=request.antenna_pattern,
            polarization=request.polarization,
        )
        _engine.add_receiver(
            name=request.rx_node,
            position=request.rx_position.as_tuple(),
            antenna_pattern=request.antenna_pattern,
            polarization=request.polarization,
        )

        # Compute paths
        path_result = _engine.compute_paths()

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
    """
    global _engine

    if _engine is None:
        _engine = get_engine()

    start_time = time.time()

    # Load scene
    _engine.load_scene(
        scene_path=request.scene.scene_file,
        frequency_hz=request.scene.frequency_hz,
        bandwidth_hz=request.scene.bandwidth_hz,
    )

    results = []

    for link in request.links:
        try:
            # Clear and set up devices for this link
            _engine.clear_devices()
            _engine.add_transmitter(
                name=link.tx_node,
                position=link.tx_position.as_tuple(),
                antenna_pattern=link.antenna_pattern,
                polarization=link.polarization,
            )
            _engine.add_receiver(
                name=link.rx_node,
                position=link.rx_position.as_tuple(),
                antenna_pattern=link.antenna_pattern,
                polarization=link.polarization,
            )

            # Compute paths
            path_result = _engine.compute_paths()

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
