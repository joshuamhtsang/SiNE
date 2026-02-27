"""
LinksSinrComputer: interference-aware batch channel computation.

Encapsulates _compute_batch_with_sinr() and the three globals it owns
(_interference_engine, _sinr_calculator, _interference_engine_scene_key)
that were previously in server.py.
"""

from __future__ import annotations

import logging
import math

from sine.channel.interference_engine import InterferenceEngine, TransmitterInfo
from sine.channel.sinr import SINRCalculator, calculate_thermal_noise
from sine.channel.snr import SNRCalculator
from sine.channel.csma_model import CSMAModel
from sine.channel.tdma_model import TDMAModel, TDMASlotConfig, SlotAssignmentMode

logger = logging.getLogger(__name__)


def _is_iface_active(iface_key: str, active_states: dict[str, bool]) -> bool:
    """Check if an interface is active.

    Args:
        iface_key: Interface key ("node:iface" or "node").
        active_states: Map of "node:interface" -> is_active.

    Returns:
        True if active (defaults to True if not in active_states).
    """
    if not active_states:
        return True
    # Direct match (e.g., "node1:eth1")
    if iface_key in active_states:
        return active_states[iface_key]
    # If key is just a node name, check if any interface is active
    matching = [
        v for k, v in active_states.items()
        if k.startswith(f"{iface_key}:")
    ]
    if matching:
        return any(matching)
    return True  # No info, assume active


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
        "Estimated communication range: %.1f m "
        "(TX=%s dBm, f=%.2f GHz, BW=%.0f MHz, min_SNR=%s dB)",
        communication_range_m, tx_power_dbm, frequency_ghz,
        bandwidth_hz / 1e6, min_snr_db,
    )

    return communication_range_m


class LinksSinrComputer:
    """
    Computes interference-aware SINR channels for a batch of links.

    Encapsulates the three interference-related globals and the
    _compute_batch_with_sinr() function from server.py.

    Thread-safety: not required — the channel server is single-threaded
    (FastAPI with asyncio) and all mutations happen inside request handlers.
    """

    def __init__(self) -> None:
        self._interference_engine: InterferenceEngine | None = None
        self._sinr_calculator: SINRCalculator | None = None
        self._interference_engine_scene_key: tuple | None = None

    async def compute(
        self,
        links: list,
        mac_model_config,
        scene_config,
        engine,
        engine_used,
        active_states: dict[str, bool],
        mcs_tables: dict,
        path_cache,
    ) -> list:
        """
        Compute channels for multiple links with SINR (interference-aware).

        This method handles interference-aware SINR computation, optionally using
        CSMA or TDMA statistical models for transmission probability weighting.

        Args:
            links: List of WirelessLinkRequest objects
            mac_model_config: MAC model configuration (CSMA or TDMA), or None
                              for worst-case (tx_prob=1.0)
            scene_config: Scene configuration
            engine: Channel engine instance to use for path computation
            engine_used: Engine type used (EngineType enum value)
            active_states: Interface active states ('node:interface' -> is_active)
            mcs_tables: MCS table cache (path -> MCSTable)
            path_cache: PathCache instance for visualization data

        Returns:
            List of ChannelResponse objects with SINR and MAC metadata
        """
        # Lazy import to avoid circular dependency with server.py.
        # server.py is fully initialized by the time this method is called.
        from sine.channel.server import (  # noqa: PLC0415
            ChannelResponse,
            compute_channel_for_link,
        )

        if mac_model_config is not None:
            logger.info(
                "Computing %d links with %s MAC model",
                len(links), mac_model_config.type.upper(),
            )
        else:
            logger.info(
                "Computing %d links with SINR (no MAC model, worst-case tx_probability=1.0)",
                len(links),
            )

        # Clear MCS hysteresis state to prevent stale per-link MCS history from
        # previous deployments affecting new computations. Without this, a prior
        # test that set MCS to a low value could prevent upgrades due to hysteresis.
        for mcs_table in mcs_tables.values():
            mcs_table.reset_hysteresis()

        # Initialize interference engine, reloading scene only when config changes.
        # Avoids expensive Sionna scene parsing on every batch while still handling
        # different deployments (e.g., different test topologies sharing the same
        # channel server process).
        scene_key = (scene_config.scene_file, scene_config.frequency_hz, scene_config.bandwidth_hz)
        if self._interference_engine is None:
            self._interference_engine = InterferenceEngine()
        if scene_key != self._interference_engine_scene_key:
            self._interference_engine.load_scene(
                scene_path=scene_config.scene_file,
                frequency_hz=scene_config.frequency_hz,
                bandwidth_hz=scene_config.bandwidth_hz,
            )
            self._interference_engine_scene_key = scene_key

        # Initialize SINR calculator if needed
        if self._sinr_calculator is None:
            self._sinr_calculator = SINRCalculator()

        # Collect positions, powers, gains, frequencies keyed by interface key.
        # When interface info is available: key = "node:iface" (e.g., "node1:eth1")
        # When not available (backward compat): key = "node" (e.g., "node1")
        iface_positions: dict[str, tuple[float, float, float]] = {}
        iface_powers: dict[str, float] = {}
        iface_gains: dict[str, float] = {}
        iface_tx_frequencies: dict[str, float] = {}
        iface_tx_bandwidths: dict[str, float] = {}
        iface_antenna_patterns: dict[str, str] = {}
        iface_polarizations: dict[str, str] = {}
        # Map interface key -> node name (for same-node exclusion)
        iface_to_node: dict[str, str] = {}
        all_iface_keys: set[str] = set()
        # Keep track of all node names too (for MAC models and backward compat)
        all_nodes: set[str] = set()

        for link in links:
            tx_key = link.iface_key()
            rx_key = link.rx_iface_key()

            iface_positions[tx_key] = link.tx_position.as_tuple()
            iface_positions[rx_key] = link.rx_position.as_tuple()
            iface_powers[tx_key] = link.tx_power_dbm
            iface_gains[tx_key] = link.tx_gain_dbi
            iface_gains[rx_key] = link.rx_gain_dbi
            iface_tx_frequencies[tx_key] = link.frequency_hz
            iface_tx_bandwidths[tx_key] = link.bandwidth_hz
            iface_antenna_patterns[tx_key] = link.antenna_pattern
            iface_polarizations[tx_key] = link.polarization
            iface_to_node[tx_key] = link.tx_node
            iface_to_node[rx_key] = link.rx_node
            all_iface_keys.add(tx_key)
            all_iface_keys.add(rx_key)
            all_nodes.add(link.tx_node)
            all_nodes.add(link.rx_node)

        # Instantiate MAC model (if configured)
        mac_model = None
        if mac_model_config is not None:
            if mac_model_config.type == "csma":
                mac_model = CSMAModel(
                    carrier_sense_range_multiplier=mac_model_config.carrier_sense_range_multiplier or 2.5,
                    default_traffic_load=mac_model_config.traffic_load or 0.3,
                )
            elif mac_model_config.type == "tdma":
                tdma_config = TDMASlotConfig(
                    frame_duration_ms=mac_model_config.frame_duration_ms or 10.0,
                    num_slots=mac_model_config.num_slots or 10,
                    slot_assignment_mode=SlotAssignmentMode(
                        mac_model_config.slot_assignment_mode or "round_robin"
                    ),
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

                # Get path result for signal
                path_result = engine.compute_paths()

                # Cache paths for visualization
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

                # Compute signal power using SNR calculator
                snr_calc = SNRCalculator(
                    bandwidth_hz=link.bandwidth_hz,
                    noise_figure_db=link.noise_figure_db,
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
                    noise_figure_db=link.noise_figure_db,
                )

                # Identify interferers: exclude TX/RX and same-node interfaces
                # (same-node cross-band coupling handled by controller's
                # self_isolation_db model, not ray tracing)
                tx_key = link.iface_key()
                rx_key = link.rx_iface_key()
                active_interferer_keys = [
                    k for k in all_iface_keys
                    if k != tx_key
                    and k != rx_key
                    and iface_to_node[k] != link.tx_node
                    and iface_to_node[k] != link.rx_node
                    and _is_iface_active(k, active_states)
                ]

                # Node names for MAC models
                active_interferer_nodes = list({
                    iface_to_node[k] for k in active_interferer_keys
                })

                if mac_model_config is not None:
                    if mac_model_config.type == "csma":
                        communication_range = estimate_communication_range(
                            tx_power_dbm=link.tx_power_dbm,
                            frequency_hz=link.frequency_hz,
                            bandwidth_hz=link.bandwidth_hz,
                            tx_gain_dbi=link.tx_gain_dbi,
                            rx_gain_dbi=link.rx_gain_dbi,
                            min_snr_db=mac_model_config.communication_range_snr_threshold_db or 20.0,
                            noise_figure_db=7.0,
                        )
                        # MAC models use node-level positions
                        node_positions = {
                            iface_to_node[k]: iface_positions[k]
                            for k in iface_positions
                        }
                        interference_probs = mac_model.compute_interference_probabilities(
                            tx_node=link.tx_node,
                            rx_node=link.rx_node,
                            interferer_nodes=active_interferer_nodes,
                            positions=node_positions,
                            communication_range=communication_range,
                            traffic_load=mac_model_config.traffic_load,
                        )
                        logger.info(
                            "CSMA %s→%s: comm_range=%.1fm, cs_range=%.1fm, "
                            "interference_probs=%s",
                            link.tx_node, link.rx_node,
                            communication_range,
                            communication_range * (
                                mac_model_config.carrier_sense_range_multiplier or 2.5
                            ),
                            {k: f"{v:.2f}" for k, v in interference_probs.items()},
                        )
                    elif mac_model_config.type == "tdma":
                        interference_probs = mac_model.compute_interference_probabilities(
                            tx_node=link.tx_node,
                            rx_node=link.rx_node,
                            interferer_nodes=active_interferer_nodes,
                            all_nodes=list(all_nodes),
                        )
                    else:
                        interference_probs = {}
                else:
                    interference_probs = {
                        iface_to_node[k]: 1.0
                        for k in active_interferer_keys
                    }
                    logger.debug(
                        "No MAC model. Worst-case tx_probability=1.0 "
                        "for %d active interferers.",
                        len(active_interferer_keys),
                    )

                # Build TransmitterInfo list from active interferer keys
                interferer_infos = []
                for ikey in active_interferer_keys:
                    if ikey in iface_positions and ikey in iface_powers:
                        interferer_infos.append(
                            TransmitterInfo(
                                node_name=iface_to_node[ikey],
                                position=iface_positions[ikey],
                                tx_power_dbm=iface_powers[ikey],
                                antenna_pattern=iface_antenna_patterns.get(ikey, "iso"),
                                polarization=iface_polarizations.get(ikey, "V"),
                                frequency_hz=iface_tx_frequencies.get(ikey, link.frequency_hz),
                                bandwidth_hz=iface_tx_bandwidths.get(ikey, link.bandwidth_hz),
                            )
                        )

                # Active states for interference engine
                iface_active_states = {
                    iface_to_node[k]: True
                    for k in active_interferer_keys
                }

                # Use RX frequency for ACLR (defaults to TX frequency if not specified)
                rx_freq_hz = (
                    link.rx_frequency_hz if link.rx_frequency_hz is not None
                    else link.frequency_hz
                )
                rx_bw_hz = (
                    link.rx_bandwidth_hz if link.rx_bandwidth_hz is not None
                    else link.bandwidth_hz
                )

                interference_result = self._interference_engine.compute_interference_at_receiver(
                    rx_position=rx_pos,
                    rx_antenna_gain_dbi=link.rx_gain_dbi,
                    rx_node=link.rx_node,
                    interferers=interferer_infos,
                    active_states=iface_active_states,
                    rx_frequency_hz=rx_freq_hz,
                    rx_bandwidth_hz=rx_bw_hz,
                    rx_antenna_pattern=link.antenna_pattern,
                    rx_polarization=link.polarization,
                )

                # Pass all interference terms to SINR calculator
                interference_terms_list = list(interference_result.interference_terms)

                # Compute SINR using MAC-specific methods (or basic SINR if no MAC model)
                if mac_model_config is not None:
                    if mac_model_config.type == "csma":
                        sinr_result, mac_metadata = self._sinr_calculator.calculate_sinr_with_csma(
                            tx_node=link.tx_node,
                            rx_node=link.rx_node,
                            signal_power_dbm=signal_power_dbm,
                            noise_power_dbm=noise_power_dbm,
                            interference_terms=interference_terms_list,
                            interference_probs=interference_probs,
                        )
                    elif mac_model_config.type == "tdma":
                        sinr_result, mac_metadata = self._sinr_calculator.calculate_sinr_with_tdma(
                            tx_node=link.tx_node,
                            rx_node=link.rx_node,
                            signal_power_dbm=signal_power_dbm,
                            noise_power_dbm=noise_power_dbm,
                            interference_terms=interference_terms_list,
                            interference_probs=interference_probs,
                        )
                    else:
                        logger.warning("Unknown MAC model type: %s", mac_model_config.type)
                        sinr_result = self._sinr_calculator.calculate_sinr(
                            tx_node=link.tx_node,
                            rx_node=link.rx_node,
                            signal_power_dbm=signal_power_dbm,
                            noise_power_dbm=noise_power_dbm,
                            interference_terms=interference_terms_list,
                        )
                        mac_metadata = {}
                else:
                    # No MAC model: Use basic SINR with worst-case tx_probability=1.0
                    sinr_result = self._sinr_calculator.calculate_sinr(
                        tx_node=link.tx_node,
                        rx_node=link.rx_node,
                        signal_power_dbm=signal_power_dbm,
                        noise_power_dbm=noise_power_dbm,
                        interference_terms=interference_terms_list,
                    )
                    mac_metadata = {}

                # Use SINR instead of SNR for MCS selection and BER/BLER/PER calculation
                effective_snr = sinr_result.sinr_db

                # DEBUG: Log SINR computation details
                logger.warning(
                    "SINR DEBUG: %s→%s | SNR=%.1f dB, SINR=%.1f dB, "
                    "Signal=%.1f dBm, Noise=%.1f dBm, "
                    "Interference=%.1f dBm, Interferers=%d",
                    link.tx_node, link.rx_node,
                    snr_db, effective_snr,
                    sinr_result.signal_power_dbm,
                    sinr_result.noise_power_dbm,
                    sinr_result.total_interference_dbm,
                    sinr_result.num_interferers,
                )

                # Compute channel parameters using SINR for MAC-aware MCS selection
                result = compute_channel_for_link(
                    link,
                    path_result,
                    engine_used=engine_used,
                    effective_metric_db=effective_snr,
                )

                # Override SNR with SINR and add MAC metadata
                result.snr_db = snr_db          # Keep original SNR (without interference)
                result.sinr_db = effective_snr  # Add SINR (with interference)

                if mac_model_config is not None:
                    result.mac_model_type = mac_model_config.type

                    if mac_model_config.type == "csma":
                        result.hidden_nodes = mac_metadata.get("num_hidden_nodes", 0)
                        result.expected_interference_dbm = mac_metadata.get(
                            "expected_interference_dbm"
                        )
                    elif mac_model_config.type == "tdma":
                        result.throughput_multiplier = mac_model.get_throughput_multiplier(
                            link.tx_node, all_nodes=list(all_nodes)
                        )
                        # Apply TDMA slot ownership to rate limit
                        result.netem_rate_mbps = result.netem_rate_mbps * result.throughput_multiplier
                else:
                    # No MAC model: SINR computed with worst-case tx_probability=1.0
                    result.mac_model_type = None

                results.append(result)

            except Exception as e:
                logger.error(
                    "Failed to compute SINR for %s->%s: %s",
                    link.tx_node, link.rx_node, e,
                    exc_info=True,
                )
                results.append(
                    ChannelResponse(
                        tx_node=link.tx_node,
                        rx_node=link.rx_node,
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
                        mac_model_type=mac_model_config.type if mac_model_config else None,
                    )
                )

        return results
