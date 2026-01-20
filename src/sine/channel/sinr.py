"""
SINR (Signal-to-Interference-plus-Noise Ratio) calculation for wireless links.

Implements Phase 1 of SINR plan: same-frequency co-channel interference with
static transmission states (all nodes transmitting).
"""

import logging
import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

from sine.channel.interference_engine import InterferenceTerm

logger = logging.getLogger(__name__)


@dataclass
class SINRResult:
    """Result of SINR calculation for a link."""

    tx_node: str
    rx_node: str

    # Power levels (dBm)
    signal_power_dbm: float
    noise_power_dbm: float
    total_interference_dbm: float

    # Ratios (dB)
    snr_db: float  # Signal-to-Noise Ratio (without interference)
    sinr_db: float  # Signal-to-Interference-plus-Noise Ratio

    # Interference details
    num_interferers: int
    interference_terms: list[InterferenceTerm]

    # Regime classification
    regime: str  # "noise-limited", "interference-limited", or "mixed"

    # Optional: capture effect applied
    capture_effect_applied: bool = False
    num_suppressed_interferers: int = 0


class SINRCalculator:
    """
    Calculate SINR for wireless links with multi-transmitter interference.

    Phase 1 implementation: Same-frequency (co-channel) interference only.
    """

    def __init__(
        self,
        rx_sensitivity_dbm: float = -80.0,
        apply_capture_effect: bool = False,
        capture_threshold_db: float = 6.0,
    ):
        """
        Initialize SINR calculator.

        Args:
            rx_sensitivity_dbm: Receiver sensitivity floor (default: -80 dBm for WiFi 6)
            apply_capture_effect: Enable capture effect (strong signal suppresses weak interference)
            capture_threshold_db: Capture threshold in dB (default: 6 dB for WiFi)
        """
        self.rx_sensitivity_dbm = rx_sensitivity_dbm
        self.apply_capture_effect = apply_capture_effect
        self.capture_threshold_db = capture_threshold_db

    def calculate_sinr(
        self,
        tx_node: str,
        rx_node: str,
        signal_power_dbm: float,
        noise_power_dbm: float,
        interference_terms: list[InterferenceTerm],
    ) -> SINRResult:
        """
        Calculate SINR for a link with interference from other transmitters.

        Formula:
            SINR (dB) = P_signal - 10*log10(P_noise_linear + P_interference_linear)

        where:
            P_noise_linear = 10^(N_dBm / 10)
            P_interference_linear = sum(10^(I_i / 10)) for all interferers i

        Args:
            tx_node: Transmitter node name
            rx_node: Receiver node name
            signal_power_dbm: Desired signal power at receiver (dBm)
            noise_power_dbm: Thermal noise power (dBm)
            interference_terms: List of interference contributions

        Returns:
            SINRResult with SINR, SNR, and regime classification
        """
        # Check if signal is above receiver sensitivity
        if signal_power_dbm < self.rx_sensitivity_dbm:
            logger.warning(
                f"Link {tx_node}→{rx_node}: Signal {signal_power_dbm:.1f} dBm "
                f"below sensitivity {self.rx_sensitivity_dbm:.1f} dBm"
            )
            # Return unusable link (SINR = -inf)
            return SINRResult(
                tx_node=tx_node,
                rx_node=rx_node,
                signal_power_dbm=signal_power_dbm,
                noise_power_dbm=noise_power_dbm,
                total_interference_dbm=-float('inf'),
                snr_db=-float('inf'),
                sinr_db=-float('inf'),
                num_interferers=0,
                interference_terms=[],
                regime="unusable",
            )

        # Calculate SNR (without interference)
        snr_db = signal_power_dbm - noise_power_dbm

        # Filter interference terms below sensitivity
        filtered_interference = [
            term for term in interference_terms
            if term.power_dbm >= self.rx_sensitivity_dbm
        ]

        num_filtered = len(interference_terms) - len(filtered_interference)
        if num_filtered > 0:
            logger.debug(
                f"Link {tx_node}→{rx_node}: Filtered {num_filtered} interferers "
                f"below sensitivity {self.rx_sensitivity_dbm:.1f} dBm"
            )

        # Apply capture effect if enabled
        num_suppressed = 0
        if self.apply_capture_effect and filtered_interference:
            filtered_interference, num_suppressed = self._apply_capture_effect(
                signal_power_dbm,
                filtered_interference
            )

        # Aggregate interference in linear domain
        if filtered_interference:
            interference_linear = sum(
                10 ** (term.power_dbm / 10.0)
                for term in filtered_interference
            )
            total_interference_dbm = 10 * math.log10(interference_linear)
        else:
            interference_linear = 0.0
            # Use very low value instead of -inf for JSON serialization
            total_interference_dbm = -200.0

        # Calculate SINR
        noise_linear = 10 ** (noise_power_dbm / 10.0)
        total_noise_plus_interference_linear = noise_linear + interference_linear

        if total_noise_plus_interference_linear > 0:
            sinr_db = signal_power_dbm - 10 * math.log10(total_noise_plus_interference_linear)
        else:
            # No noise or interference (shouldn't happen, but handle gracefully)
            sinr_db = snr_db

        # Classify regime
        regime = self._classify_regime(noise_power_dbm, total_interference_dbm)

        logger.debug(
            f"Link {tx_node}→{rx_node}: "
            f"Signal={signal_power_dbm:.1f} dBm, "
            f"Noise={noise_power_dbm:.1f} dBm, "
            f"Interference={total_interference_dbm:.1f} dBm, "
            f"SNR={snr_db:.1f} dB, "
            f"SINR={sinr_db:.1f} dB, "
            f"Regime={regime}"
        )

        return SINRResult(
            tx_node=tx_node,
            rx_node=rx_node,
            signal_power_dbm=signal_power_dbm,
            noise_power_dbm=noise_power_dbm,
            total_interference_dbm=total_interference_dbm,
            snr_db=snr_db,
            sinr_db=sinr_db,
            num_interferers=len(filtered_interference),
            interference_terms=filtered_interference,
            regime=regime,
            capture_effect_applied=self.apply_capture_effect,
            num_suppressed_interferers=num_suppressed,
        )

    def _apply_capture_effect(
        self,
        signal_power_dbm: float,
        interference_terms: list[InterferenceTerm],
    ) -> tuple[list[InterferenceTerm], int]:
        """
        Apply capture effect: suppress interference weaker than signal by threshold.

        WiFi receivers can "capture" the stronger signal when it exceeds interference
        by a certain margin (typically 4-6 dB).

        Args:
            signal_power_dbm: Desired signal power
            interference_terms: List of interference terms

        Returns:
            (filtered_terms, num_suppressed)
        """
        filtered = []
        num_suppressed = 0

        for term in interference_terms:
            signal_to_interference_db = signal_power_dbm - term.power_dbm

            if signal_to_interference_db >= self.capture_threshold_db:
                # Signal is strong enough to suppress this interferer
                logger.debug(
                    f"Capture effect: Suppressing {term.source} "
                    f"(S/I = {signal_to_interference_db:.1f} dB)"
                )
                num_suppressed += 1
            else:
                # Interference is significant
                filtered.append(term)

        return filtered, num_suppressed

    def calculate_sinr_with_csma(
        self,
        tx_node: str,
        rx_node: str,
        signal_power_dbm: float,
        noise_power_dbm: float,
        interference_terms: list[InterferenceTerm],
        interference_probs: dict[str, float],
    ) -> tuple[SINRResult, dict]:
        """
        Calculate SINR with CSMA/CA statistical model.

        Expected interference = sum(Pr[TX_i] × I_i) for each interferer.

        Args:
            tx_node: Transmitter node name
            rx_node: Receiver node name
            signal_power_dbm: Desired signal power at receiver (dBm)
            noise_power_dbm: Thermal noise power (dBm)
            interference_terms: List of interference contributions
            interference_probs: Per-interferer TX probability {interferer_name: Pr[TX]}

        Returns:
            (SINRResult, metadata_dict) where metadata contains CSMA-specific info
        """
        # Check if signal is above receiver sensitivity
        if signal_power_dbm < self.rx_sensitivity_dbm:
            logger.warning(
                f"Link {tx_node}→{rx_node}: Signal {signal_power_dbm:.1f} dBm "
                f"below sensitivity {self.rx_sensitivity_dbm:.1f} dBm"
            )
            return (
                SINRResult(
                    tx_node=tx_node,
                    rx_node=rx_node,
                    signal_power_dbm=signal_power_dbm,
                    noise_power_dbm=noise_power_dbm,
                    total_interference_dbm=-np.inf,
                    snr_db=-np.inf,
                    sinr_db=-np.inf,
                    num_interferers=0,
                    interference_terms=[],
                    regime="unusable",
                ),
                {"interference_model": "csma", "num_hidden_nodes": 0},
            )

        # Calculate SNR (without interference)
        snr_db = signal_power_dbm - noise_power_dbm

        # Filter interference terms below sensitivity
        filtered_interference = [
            term
            for term in interference_terms
            if term.power_dbm >= self.rx_sensitivity_dbm
        ]

        # Aggregate expected interference (probabilistic)
        expected_interference_linear = 0.0
        num_hidden_nodes = 0

        for term in filtered_interference:
            prob = interference_probs.get(term.source, 0.0)
            if prob > 0:
                num_hidden_nodes += 1

            # Expected interference contribution: Pr[TX] × I_linear
            interference_contribution = prob * (10 ** (term.power_dbm / 10.0))
            expected_interference_linear += interference_contribution

        # Calculate total interference in dBm
        if expected_interference_linear > 0:
            total_interference_dbm = 10 * math.log10(expected_interference_linear)
        else:
            # Use very low value instead of -inf for JSON serialization
            total_interference_dbm = -200.0

        # Calculate SINR
        noise_linear = 10 ** (noise_power_dbm / 10.0)
        total_noise_plus_interference_linear = noise_linear + expected_interference_linear

        if total_noise_plus_interference_linear > 0:
            sinr_db = signal_power_dbm - 10 * math.log10(
                total_noise_plus_interference_linear
            )
        else:
            sinr_db = snr_db

        # Classify regime
        regime = self._classify_regime(noise_power_dbm, total_interference_dbm)

        logger.debug(
            f"Link {tx_node}→{rx_node} (CSMA): "
            f"Signal={signal_power_dbm:.1f} dBm, "
            f"Noise={noise_power_dbm:.1f} dBm, "
            f"Expected Interference={total_interference_dbm:.1f} dBm, "
            f"Hidden nodes={num_hidden_nodes}/{len(filtered_interference)}, "
            f"SNR={snr_db:.1f} dB, "
            f"SINR={sinr_db:.1f} dB, "
            f"Regime={regime}"
        )

        metadata = {
            "interference_model": "csma",
            "num_interferers": len(filtered_interference),
            "num_hidden_nodes": num_hidden_nodes,
            "expected_interference_dbm": total_interference_dbm,
        }

        result = SINRResult(
            tx_node=tx_node,
            rx_node=rx_node,
            signal_power_dbm=signal_power_dbm,
            noise_power_dbm=noise_power_dbm,
            total_interference_dbm=total_interference_dbm,
            snr_db=snr_db,
            sinr_db=sinr_db,
            num_interferers=len(filtered_interference),
            interference_terms=filtered_interference,
            regime=regime,
        )

        return result, metadata

    def calculate_sinr_with_tdma(
        self,
        tx_node: str,
        rx_node: str,
        signal_power_dbm: float,
        noise_power_dbm: float,
        interference_terms: list[InterferenceTerm],
        interference_probs: dict[str, float],
    ) -> tuple[SINRResult, dict]:
        """
        Calculate SINR with TDMA statistical model.

        Expected interference = sum(Pr[TX_i] × I_i) where Pr[TX_i] from slot assignment.

        Args:
            tx_node: Transmitter node name
            rx_node: Receiver node name
            signal_power_dbm: Desired signal power at receiver (dBm)
            noise_power_dbm: Thermal noise power (dBm)
            interference_terms: List of interference contributions
            interference_probs: Per-interferer TX probability {interferer_name: Pr[TX]}

        Returns:
            (SINRResult, metadata_dict) where metadata contains TDMA-specific info
        """
        # Check if signal is above receiver sensitivity
        if signal_power_dbm < self.rx_sensitivity_dbm:
            logger.warning(
                f"Link {tx_node}→{rx_node}: Signal {signal_power_dbm:.1f} dBm "
                f"below sensitivity {self.rx_sensitivity_dbm:.1f} dBm"
            )
            return (
                SINRResult(
                    tx_node=tx_node,
                    rx_node=rx_node,
                    signal_power_dbm=signal_power_dbm,
                    noise_power_dbm=noise_power_dbm,
                    total_interference_dbm=-np.inf,
                    snr_db=-np.inf,
                    sinr_db=-np.inf,
                    num_interferers=0,
                    interference_terms=[],
                    regime="unusable",
                ),
                {
                    "interference_model": "tdma",
                    "num_deterministic_interferers": 0,
                    "num_probabilistic_interferers": 0,
                },
            )

        # Calculate SNR (without interference)
        snr_db = signal_power_dbm - noise_power_dbm

        # Filter interference terms below sensitivity
        filtered_interference = [
            term
            for term in interference_terms
            if term.power_dbm >= self.rx_sensitivity_dbm
        ]

        # Aggregate expected interference (probabilistic or deterministic)
        expected_interference_linear = 0.0

        for term in filtered_interference:
            prob = interference_probs.get(term.source, 0.0)

            # Expected interference contribution: Pr[TX] × I_linear
            interference_contribution = prob * (10 ** (term.power_dbm / 10.0))
            expected_interference_linear += interference_contribution

        # Calculate total interference in dBm
        if expected_interference_linear > 0:
            total_interference_dbm = 10 * math.log10(expected_interference_linear)
        else:
            # Use very low value instead of -inf for JSON serialization
            total_interference_dbm = -200.0

        # Calculate SINR
        noise_linear = 10 ** (noise_power_dbm / 10.0)
        total_noise_plus_interference_linear = noise_linear + expected_interference_linear

        if total_noise_plus_interference_linear > 0:
            sinr_db = signal_power_dbm - 10 * math.log10(
                total_noise_plus_interference_linear
            )
        else:
            sinr_db = snr_db

        # Classify regime
        regime = self._classify_regime(noise_power_dbm, total_interference_dbm)

        # Count deterministic vs probabilistic interferers
        num_deterministic = sum(
            1 for p in interference_probs.values() if p in [0.0, 1.0]
        )
        num_probabilistic = len(interference_probs) - num_deterministic

        logger.debug(
            f"Link {tx_node}→{rx_node} (TDMA): "
            f"Signal={signal_power_dbm:.1f} dBm, "
            f"Noise={noise_power_dbm:.1f} dBm, "
            f"Expected Interference={total_interference_dbm:.1f} dBm, "
            f"Deterministic={num_deterministic}, Probabilistic={num_probabilistic}, "
            f"SNR={snr_db:.1f} dB, "
            f"SINR={sinr_db:.1f} dB, "
            f"Regime={regime}"
        )

        metadata = {
            "interference_model": "tdma",
            "num_interferers": len(filtered_interference),
            "num_deterministic_interferers": num_deterministic,
            "num_probabilistic_interferers": num_probabilistic,
            "expected_interference_dbm": total_interference_dbm,
        }

        result = SINRResult(
            tx_node=tx_node,
            rx_node=rx_node,
            signal_power_dbm=signal_power_dbm,
            noise_power_dbm=noise_power_dbm,
            total_interference_dbm=total_interference_dbm,
            snr_db=snr_db,
            sinr_db=sinr_db,
            num_interferers=len(filtered_interference),
            interference_terms=filtered_interference,
            regime=regime,
        )

        return result, metadata

    def _classify_regime(
        self,
        noise_power_dbm: float,
        total_interference_dbm: float,
    ) -> str:
        """
        Classify link regime based on dominant impairment.

        Args:
            noise_power_dbm: Thermal noise power
            total_interference_dbm: Total interference power

        Returns:
            "noise-limited", "interference-limited", or "mixed"
        """
        if total_interference_dbm <= -200.0:
            # No interference (or negligible)
            return "noise-limited"

        # Compare interference to noise (10 dB threshold)
        i_over_n = total_interference_dbm - noise_power_dbm

        if i_over_n < -10.0:
            return "noise-limited"  # Interference negligible
        elif i_over_n > 10.0:
            return "interference-limited"  # Interference dominates
        else:
            return "mixed"  # Both contribute significantly


def calculate_thermal_noise(
    bandwidth_hz: float,
    temperature_k: float = 290.0,
    noise_figure_db: float = 7.0,
) -> float:
    """
    Calculate thermal noise power for a receiver.

    Formula:
        N (dBm) = -174 dBm/Hz + 10*log10(BW) + NF

    where:
        -174 dBm/Hz is thermal noise density at 290K
        BW is bandwidth in Hz
        NF is receiver noise figure in dB

    Args:
        bandwidth_hz: Channel bandwidth in Hz
        temperature_k: Temperature in Kelvin (default: 290K)
        noise_figure_db: Receiver noise figure in dB (default: 7 dB for WiFi)

    Returns:
        Noise power in dBm
    """
    # Boltzmann constant: k = 1.380649e-23 J/K
    # Thermal noise density: N0 = k * T (W/Hz)
    # In dBm/Hz: N0_dBm = 10*log10(k*T*1000) = 10*log10(k*T) + 30
    #
    # For T=290K: N0_dBm = 10*log10(1.380649e-23 * 290) + 30 = -174 dBm/Hz

    thermal_noise_density_dbm_hz = -174.0  # At 290K

    # Adjust for temperature if not 290K
    if temperature_k != 290.0:
        thermal_noise_density_dbm_hz += 10 * math.log10(temperature_k / 290.0)

    # Add bandwidth and noise figure
    noise_power_dbm = (
        thermal_noise_density_dbm_hz
        + 10 * math.log10(bandwidth_hz)
        + noise_figure_db
    )

    return noise_power_dbm
