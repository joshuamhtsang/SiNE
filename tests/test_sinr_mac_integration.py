"""
Unit tests for MAC model SINR integration.

Verifies that CSMA and TDMA SINR calculations correctly apply interference
probabilities instead of treating all interferers as 100% active.
"""

import pytest
from sine.channel.sinr import SINRCalculator
from sine.channel.interference_engine import InterferenceTerm


def test_csma_sinr_uses_probabilities():
    """Verify CSMA SINR calculation uses interference probabilities.

    This test validates the fix for the bug where interference probabilities
    were computed but not applied to the SINR calculation.

    Expected behavior:
    - Interference power should be scaled by probability
    - SINR should be lower than SNR when interference is present
    - Effective interference = raw_interference_power * probability
    """
    # Setup
    signal_power_dbm = -52.7
    noise_power_dbm = -95.0

    # Interferer at -58.8 dBm with 30% probability (hidden node)
    interference_terms = [
        InterferenceTerm(
            source="node1",
            power_dbm=-58.8,
            frequency_hz=5.18e9,
        )
    ]
    interference_probs = {"node1": 0.3}

    # Calculate SINR with CSMA
    calculator = SINRCalculator()
    sinr_result, metadata = calculator.calculate_sinr_with_csma(
        tx_node="node2",
        rx_node="node3",
        signal_power_dbm=signal_power_dbm,
        noise_power_dbm=noise_power_dbm,
        interference_terms=interference_terms,
        interference_probs=interference_probs,
    )

    # Expected SINR calculation
    # Effective interference = -58.8 dBm * 0.3 probability = -64.0 dBm
    # Total noise+interference = 10^(-95/10) + 10^(-64/10) = 3.16e-10 + 3.98e-7 ≈ 3.98e-7 mW
    # SINR = -52.7 - 10*log10(3.98e-7) ≈ -52.7 - (-64.0) = 11.3 dB
    expected_sinr = 11.3

    # Verify SINR is within expected range (allowing for calculation precision)
    assert abs(sinr_result.sinr_db - expected_sinr) < 0.5, \
        f"CSMA SINR {sinr_result.sinr_db:.1f} dB != expected {expected_sinr} dB"

    # Verify SINR is significantly lower than SNR (interference-limited)
    snr_db = signal_power_dbm - noise_power_dbm  # -52.7 - (-95.0) = 42.3 dB
    assert sinr_result.sinr_db < snr_db - 20, \
        f"SINR {sinr_result.sinr_db:.1f} dB should be << SNR {snr_db:.1f} dB"

    # Verify metadata
    assert metadata["interference_model"] == "csma"
    assert metadata["num_hidden_nodes"] == 1
    assert abs(metadata["expected_interference_dbm"] - (-64.0)) < 0.5, \
        f"Expected interference {metadata['expected_interference_dbm']:.1f} dBm != -64.0 dBm"


def test_csma_sinr_zero_probability():
    """Verify CSMA SINR ignores interferers with zero probability (within CS range)."""
    signal_power_dbm = -52.7
    noise_power_dbm = -95.0

    # Interferer at -58.8 dBm but with 0% probability (within carrier sense range)
    interference_terms = [
        InterferenceTerm(
            source="node1",
            power_dbm=-58.8,
            frequency_hz=5.18e9,
        )
    ]
    interference_probs = {"node1": 0.0}  # Within CS range, won't transmit

    calculator = SINRCalculator()
    sinr_result, metadata = calculator.calculate_sinr_with_csma(
        tx_node="node2",
        rx_node="node3",
        signal_power_dbm=signal_power_dbm,
        noise_power_dbm=noise_power_dbm,
        interference_terms=interference_terms,
        interference_probs=interference_probs,
    )

    # Expected: SINR ≈ SNR (no effective interference)
    snr_db = signal_power_dbm - noise_power_dbm
    assert abs(sinr_result.sinr_db - snr_db) < 0.5, \
        f"SINR {sinr_result.sinr_db:.1f} dB should equal SNR {snr_db:.1f} dB with zero probability"

    # Verify no hidden nodes counted
    assert metadata["num_hidden_nodes"] == 0


def test_csma_sinr_multiple_interferers():
    """Verify CSMA SINR correctly aggregates multiple interferers with different probabilities."""
    signal_power_dbm = -50.0
    noise_power_dbm = -95.0

    # Two interferers with different probabilities
    interference_terms = [
        InterferenceTerm(source="node1", power_dbm=-60.0, frequency_hz=5.18e9),
        InterferenceTerm(source="node2", power_dbm=-65.0, frequency_hz=5.18e9),
    ]
    interference_probs = {
        "node1": 0.3,  # Hidden node, 30% traffic load
        "node2": 0.5,  # Hidden node, 50% traffic load
    }

    calculator = SINRCalculator()
    sinr_result, metadata = calculator.calculate_sinr_with_csma(
        tx_node="node3",
        rx_node="node4",
        signal_power_dbm=signal_power_dbm,
        noise_power_dbm=noise_power_dbm,
        interference_terms=interference_terms,
        interference_probs=interference_probs,
    )

    # Expected interference contributions (linear domain):
    # I1 = 10^(-60/10) * 0.3 = 1e-6 * 0.3 = 3e-7 mW
    # I2 = 10^(-65/10) * 0.5 = 3.16e-7 * 0.5 = 1.58e-7 mW
    # Total = 4.58e-7 mW = -63.4 dBm
    expected_interference_dbm = -63.4

    assert abs(metadata["expected_interference_dbm"] - expected_interference_dbm) < 0.5, \
        f"Expected interference {metadata['expected_interference_dbm']:.1f} dBm != {expected_interference_dbm} dBm"

    # Verify both hidden nodes counted
    assert metadata["num_hidden_nodes"] == 2


def test_phase1_vs_csma_comparison():
    """Compare Phase 1 (all-transmitting) vs CSMA (probabilistic) SINR.

    This test demonstrates the bug: Phase 1 ignores probabilities and assumes
    all interferers are always transmitting (worst-case).
    """
    signal_power_dbm = -52.7
    noise_power_dbm = -95.0

    interference_terms = [
        InterferenceTerm(source="node1", power_dbm=-58.8, frequency_hz=5.18e9),
    ]
    interference_probs = {"node1": 0.3}

    calculator = SINRCalculator()

    # Phase 1: All-transmitting (ignores probabilities)
    phase1_result = calculator.calculate_sinr(
        tx_node="node2",
        rx_node="node3",
        signal_power_dbm=signal_power_dbm,
        noise_power_dbm=noise_power_dbm,
        interference_terms=interference_terms,
    )

    # CSMA: Probabilistic (uses probabilities)
    csma_result, _ = calculator.calculate_sinr_with_csma(
        tx_node="node2",
        rx_node="node3",
        signal_power_dbm=signal_power_dbm,
        noise_power_dbm=noise_power_dbm,
        interference_terms=interference_terms,
        interference_probs=interference_probs,
    )

    # CSMA SINR should be HIGHER than Phase 1 (less interference with probabilities)
    assert csma_result.sinr_db > phase1_result.sinr_db, \
        f"CSMA SINR {csma_result.sinr_db:.1f} dB should be > Phase 1 SINR {phase1_result.sinr_db:.1f} dB"

    # Difference should be significant (5+ dB for 30% probability)
    sinr_improvement = csma_result.sinr_db - phase1_result.sinr_db
    assert sinr_improvement > 5.0, \
        f"SINR improvement {sinr_improvement:.1f} dB should be > 5 dB for 30% probability"
