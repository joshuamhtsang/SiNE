"""
Unit tests for SINR calculation (Phase 1).

Tests SINR calculator with same-frequency co-channel interference.
"""

import pytest
import numpy as np
import math

from sine.channel.interference_utils import SINRCalculator, SINRResult, calculate_thermal_noise
from sine.channel.interference_calculator import InterferenceTerm


class TestThermalNoiseCalculation:
    """Test thermal noise calculation."""

    def test_thermal_noise_standard_conditions(self):
        """Test thermal noise calculation at standard temperature."""
        # 80 MHz bandwidth, 290K, 7 dB NF (WiFi 6 typical)
        noise_dbm = calculate_thermal_noise(
            bandwidth_hz=80e6,
            temperature_k=290.0,
            noise_figure_db=7.0
        )

        # Expected: -174 + 10*log10(80e6) + 7
        # = -174 + 79.03 + 7 = -87.97 dBm
        expected = -174 + 10 * math.log10(80e6) + 7

        assert abs(noise_dbm - expected) < 0.01
        assert abs(noise_dbm - (-87.97)) < 0.1

    def test_thermal_noise_different_bandwidth(self):
        """Test thermal noise scales with bandwidth."""
        noise_20mhz = calculate_thermal_noise(20e6)
        noise_80mhz = calculate_thermal_noise(80e6)

        # 80 MHz is 4× wider → 6 dB more noise
        delta_db = noise_80mhz - noise_20mhz
        expected_delta = 10 * math.log10(80e6 / 20e6)  # ~6.02 dB

        assert abs(delta_db - expected_delta) < 0.01


class TestSINRCalculation:
    """Test SINR calculator with various interference scenarios."""

    def test_no_interference_sinr_equals_snr(self):
        """With no interference, SINR should equal SNR."""
        calculator = SINRCalculator(rx_sensitivity_dbm=-80.0)

        signal_power_dbm = -50.0
        noise_power_dbm = -90.0
        interference_terms = []  # No interference

        result = calculator.calculate_sinr(
            tx_node="tx1",
            rx_node="rx1",
            signal_power_dbm=signal_power_dbm,
            noise_power_dbm=noise_power_dbm,
            interference_terms=interference_terms
        )

        # SINR should equal SNR when no interference
        expected_snr = signal_power_dbm - noise_power_dbm  # 40 dB
        assert abs(result.snr_db - expected_snr) < 0.01
        assert abs(result.sinr_db - result.snr_db) < 0.01
        assert result.regime == "noise-limited"
        assert result.num_interferers == 0

    def test_single_interferer_sinr_degradation(self):
        """Single interferer should degrade SINR below SNR."""
        calculator = SINRCalculator(rx_sensitivity_dbm=-80.0)

        signal_power_dbm = -50.0
        noise_power_dbm = -90.0

        # Single interferer at -60 dBm (stronger than noise, weaker than signal)
        interference_terms = [
            InterferenceTerm(source="interferer1", power_dbm=-60.0, frequency_hz=5.18e9)
        ]

        result = calculator.calculate_sinr(
            tx_node="tx1",
            rx_node="rx1",
            signal_power_dbm=signal_power_dbm,
            noise_power_dbm=noise_power_dbm,
            interference_terms=interference_terms
        )

        # Calculate expected SINR manually
        signal_linear = 10 ** (signal_power_dbm / 10.0)
        noise_linear = 10 ** (noise_power_dbm / 10.0)
        interference_linear = 10 ** (-60.0 / 10.0)
        expected_sinr_db = 10 * math.log10(
            signal_linear / (noise_linear + interference_linear)
        )

        # SNR = -50 - (-90) = 40 dB
        # SINR should be lower due to interference
        assert result.snr_db > result.sinr_db  # SINR degraded
        assert abs(result.sinr_db - expected_sinr_db) < 0.01
        assert result.num_interferers == 1

        # Interference dominates noise (-60 vs -90 dBm)
        assert result.regime in ["interference-limited", "mixed"]

    def test_two_interferers_aggregation(self):
        """Two interferers should aggregate in linear domain."""
        calculator = SINRCalculator(rx_sensitivity_dbm=-80.0)

        signal_power_dbm = -50.0
        noise_power_dbm = -90.0

        # Two interferers at same power
        interference_terms = [
            InterferenceTerm(source="intf1", power_dbm=-65.0, frequency_hz=5.18e9),
            InterferenceTerm(source="intf2", power_dbm=-65.0, frequency_hz=5.18e9),
        ]

        result = calculator.calculate_sinr(
            tx_node="tx1",
            rx_node="rx1",
            signal_power_dbm=signal_power_dbm,
            noise_power_dbm=noise_power_dbm,
            interference_terms=interference_terms
        )

        # Two equal interferers at -65 dBm each
        # Total interference = 10*log10(2 × 10^(-6.5)) = -65 + 3 = -62 dBm
        i1_linear = 10 ** (-65.0 / 10.0)
        i2_linear = 10 ** (-65.0 / 10.0)
        total_interference_linear = i1_linear + i2_linear
        expected_total_interference_dbm = 10 * math.log10(total_interference_linear)

        assert abs(result.total_interference_dbm - expected_total_interference_dbm) < 0.01
        assert abs(result.total_interference_dbm - (-62.0)) < 0.1  # ~3 dB increase
        assert result.num_interferers == 2

    def test_regime_classification_noise_limited(self):
        """Test regime classification: noise-limited."""
        calculator = SINRCalculator()

        # Strong signal, low noise, negligible interference
        result = calculator.calculate_sinr(
            tx_node="tx1",
            rx_node="rx1",
            signal_power_dbm=-40.0,
            noise_power_dbm=-90.0,
            interference_terms=[
                InterferenceTerm(source="intf1", power_dbm=-105.0, frequency_hz=5.18e9)
            ]  # Interference << noise
        )

        assert result.regime == "noise-limited"
        # Interference more than 10 dB below noise

    def test_regime_classification_interference_limited(self):
        """Test regime classification: interference-limited."""
        calculator = SINRCalculator()

        # Interference dominates noise
        result = calculator.calculate_sinr(
            tx_node="tx1",
            rx_node="rx1",
            signal_power_dbm=-40.0,
            noise_power_dbm=-90.0,
            interference_terms=[
                InterferenceTerm(source="intf1", power_dbm=-60.0, frequency_hz=5.18e9)
            ]  # Interference >> noise (30 dB higher)
        )

        assert result.regime == "interference-limited"

    def test_regime_classification_mixed(self):
        """Test regime classification: mixed."""
        calculator = SINRCalculator(rx_sensitivity_dbm=-100.0)  # Low sensitivity to not filter

        # Interference and noise comparable (within ±10 dB threshold)
        # For mixed: -10 < (I - N) < 10 dB
        result = calculator.calculate_sinr(
            tx_node="tx1",
            rx_node="rx1",
            signal_power_dbm=-40.0,
            noise_power_dbm=-87.0,  # Noise at -87 dBm
            interference_terms=[
                InterferenceTerm(source="intf1", power_dbm=-82.0, frequency_hz=5.18e9)
            ]  # Interference 5 dB above noise: I/N = 5 dB → mixed
        )

        assert result.regime == "mixed"


class TestReceiverSensitivity:
    """Test receiver sensitivity floor filtering."""

    def test_signal_below_sensitivity(self):
        """Signal below sensitivity should be marked unusable."""
        calculator = SINRCalculator(rx_sensitivity_dbm=-80.0)

        # Signal weaker than sensitivity
        result = calculator.calculate_sinr(
            tx_node="tx1",
            rx_node="rx1",
            signal_power_dbm=-85.0,  # Below -80 dBm sensitivity
            noise_power_dbm=-90.0,
            interference_terms=[]
        )

        assert result.regime == "unusable"
        assert result.sinr_db == -np.inf
        assert result.snr_db == -np.inf

    def test_interference_below_sensitivity_filtered(self):
        """Interference below sensitivity should be filtered out."""
        calculator = SINRCalculator(rx_sensitivity_dbm=-80.0)

        # Strong signal, but weak interferers below sensitivity
        interference_terms = [
            InterferenceTerm(source="intf1", power_dbm=-85.0, frequency_hz=5.18e9),  # Below sensitivity
            InterferenceTerm(source="intf2", power_dbm=-70.0, frequency_hz=5.18e9),  # Above sensitivity
        ]

        result = calculator.calculate_sinr(
            tx_node="tx1",
            rx_node="rx1",
            signal_power_dbm=-50.0,
            noise_power_dbm=-90.0,
            interference_terms=interference_terms
        )

        # Only intf2 should be counted (intf1 filtered)
        assert result.num_interferers == 1


class TestCaptureEffect:
    """Test capture effect (optional enhancement)."""

    def test_capture_effect_suppresses_weak_interference(self):
        """Strong signal should suppress weak interference."""
        # Enable capture effect with 6 dB threshold
        calculator = SINRCalculator(
            rx_sensitivity_dbm=-80.0,
            apply_capture_effect=True,
            capture_threshold_db=6.0
        )

        signal_power_dbm = -50.0
        noise_power_dbm = -90.0

        # Two interferers: one weak (suppressed), one strong (not suppressed)
        interference_terms = [
            InterferenceTerm(source="weak", power_dbm=-60.0, frequency_hz=5.18e9),    # 10 dB below signal → suppressed
            InterferenceTerm(source="strong", power_dbm=-52.0, frequency_hz=5.18e9),  # 2 dB below signal → NOT suppressed
        ]

        result = calculator.calculate_sinr(
            tx_node="tx1",
            rx_node="rx1",
            signal_power_dbm=signal_power_dbm,
            noise_power_dbm=noise_power_dbm,
            interference_terms=interference_terms
        )

        # Weak interferer should be suppressed (10 dB > 6 dB threshold)
        assert result.num_suppressed_interferers >= 1
        # Only strong interferer should remain
        assert result.num_interferers <= 1
        assert result.capture_effect_applied is True

    def test_capture_effect_disabled_by_default(self):
        """Capture effect should be disabled by default."""
        calculator = SINRCalculator()  # Default: apply_capture_effect=False

        result = calculator.calculate_sinr(
            tx_node="tx1",
            rx_node="rx1",
            signal_power_dbm=-50.0,
            noise_power_dbm=-90.0,
            interference_terms=[
                InterferenceTerm(source="weak", power_dbm=-70.0, frequency_hz=5.18e9)
            ]
        )

        assert result.capture_effect_applied is False
        assert result.num_suppressed_interferers == 0


class TestSINRPhysics:
    """Test SINR calculation against physical expectations."""

    def test_sinr_always_less_than_or_equal_snr(self):
        """SINR should never exceed SNR (interference can't help)."""
        calculator = SINRCalculator()

        # Test with various interference levels
        for interference_dbm in [-70, -60, -50]:
            result = calculator.calculate_sinr(
                tx_node="tx1",
                rx_node="rx1",
                signal_power_dbm=-40.0,
                noise_power_dbm=-90.0,
                interference_terms=[
                    InterferenceTerm(source="intf", power_dbm=interference_dbm, frequency_hz=5.18e9)
                ]
            )

            assert result.sinr_db <= result.snr_db, \
                f"SINR ({result.sinr_db}) > SNR ({result.snr_db}) with interference at {interference_dbm} dBm"

    def test_stronger_interference_degrades_sinr_more(self):
        """Stronger interference should result in lower SINR."""
        calculator = SINRCalculator()

        # Compute SINR with weak interference
        result_weak = calculator.calculate_sinr(
            tx_node="tx1",
            rx_node="rx1",
            signal_power_dbm=-50.0,
            noise_power_dbm=-90.0,
            interference_terms=[
                InterferenceTerm(source="intf", power_dbm=-70.0, frequency_hz=5.18e9)
            ]
        )

        # Compute SINR with strong interference
        result_strong = calculator.calculate_sinr(
            tx_node="tx1",
            rx_node="rx1",
            signal_power_dbm=-50.0,
            noise_power_dbm=-90.0,
            interference_terms=[
                InterferenceTerm(source="intf", power_dbm=-55.0, frequency_hz=5.18e9)
            ]
        )

        # Stronger interference → lower SINR
        assert result_strong.sinr_db < result_weak.sinr_db


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
