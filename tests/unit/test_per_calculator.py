"""
Unit tests for per_calculator.py - Packet Error Rate calculations.

Tests PER calculation from BER or BLER, netem parameter conversion,
and effective rate calculation.
"""

import pytest
import numpy as np
from sine.channel.per_calculator import PERCalculator, ChannelMetrics


class TestPERCalculatorInitialization:
    """Test PER calculator initialization."""

    def test_init_uncoded(self):
        """Test initialization for uncoded system."""
        calc = PERCalculator(fec_type="none")
        assert calc.fec_type == "none"
        assert calc.is_coded is False

    @pytest.mark.parametrize("fec_type", ["ldpc", "polar", "turbo"])
    def test_init_coded(self, fec_type: str):
        """Test initialization for coded systems."""
        calc = PERCalculator(fec_type=fec_type)
        assert calc.fec_type == fec_type
        assert calc.is_coded is True

    def test_default_packet_size(self):
        """Test that default packet size constants are set."""
        assert PERCalculator.DEFAULT_PACKET_BYTES == 1500
        assert PERCalculator.DEFAULT_PACKET_BITS == 1500 * 8


class TestPERFromBER:
    """Test PER calculation from BER (uncoded systems)."""

    def test_per_from_ber_basic(self):
        """Test basic PER calculation: PER = 1 - (1-BER)^N."""
        calc = PERCalculator(fec_type="none")
        ber = 1e-5
        packet_bits = 1500 * 8  # 12000 bits

        per = calc.calculate_per(ber=ber, packet_bits=packet_bits)

        # Expected: 1 - (1 - 1e-5)^12000 ≈ 0.1131 (11.31%)
        expected = 1.0 - (1.0 - ber) ** packet_bits
        assert abs(per - expected) < 0.001

    def test_per_zero_ber(self):
        """Test that PER = 0 when BER = 0."""
        calc = PERCalculator(fec_type="none")
        per = calc.calculate_per(ber=0.0, packet_bits=12000)
        assert per == 0.0

    def test_per_very_small_ber(self):
        """Test PER with very small BER (uses linear approximation)."""
        calc = PERCalculator(fec_type="none")
        ber = 1e-12
        packet_bits = 12000

        per = calc.calculate_per(ber=ber, packet_bits=packet_bits)

        # For small BER: PER ≈ BER × packet_bits
        expected_approx = ber * packet_bits
        assert abs(per - expected_approx) / expected_approx < 0.01  # Within 1%

    def test_per_high_ber(self):
        """Test PER with high BER (BER > 0.5)."""
        calc = PERCalculator(fec_type="none")
        ber = 0.6  # Above 0.5 (random/unusable)

        per = calc.calculate_per(ber=ber, packet_bits=12000)

        # Should return 1.0 (all packets lost)
        assert per == 1.0

    def test_per_ber_half(self):
        """Test PER at BER = 0.5 (threshold)."""
        calc = PERCalculator(fec_type="none")
        ber = 0.5

        per = calc.calculate_per(ber=ber, packet_bits=12000)

        # At BER=0.5, essentially all packets should be corrupted
        assert per >= 0.99

    @pytest.mark.parametrize(
        "ber,packet_bits,expected_per_approx",
        [
            (1e-6, 1500 * 8, 0.012),  # 1.2% packet loss
            (1e-4, 1500 * 8, 0.70),  # 70% packet loss
            (1e-3, 1500 * 8, 1.0),  # Nearly 100% loss
        ],
    )
    def test_per_at_various_ber_levels(
        self, ber: float, packet_bits: int, expected_per_approx: float
    ):
        """Test PER at various BER levels (order of magnitude check)."""
        calc = PERCalculator(fec_type="none")
        per = calc.calculate_per(ber=ber, packet_bits=packet_bits)

        # Allow factor of 2 tolerance (order of magnitude)
        assert per / expected_per_approx < 2.0
        assert per / expected_per_approx > 0.5

    def test_per_increases_with_packet_size(self):
        """Test that PER increases with larger packet size at same BER."""
        calc = PERCalculator(fec_type="none")
        ber = 1e-5

        per_small = calc.calculate_per(ber=ber, packet_bits=1000)
        per_large = calc.calculate_per(ber=ber, packet_bits=10000)

        assert per_large > per_small

    def test_per_requires_ber_for_uncoded(self):
        """Test that uncoded systems require BER parameter."""
        calc = PERCalculator(fec_type="none")
        with pytest.raises(ValueError, match="BER required"):
            calc.calculate_per(bler=0.1, packet_bits=12000)  # Missing ber


class TestPERFromBLER:
    """Test PER calculation from BLER (coded systems)."""

    def test_per_equals_bler_single_block(self):
        """Test that PER = BLER for single code block per packet."""
        calc = PERCalculator(fec_type="ldpc")
        bler = 0.01

        per = calc.calculate_per(bler=bler, num_code_blocks=1)

        assert per == bler

    def test_per_multiple_blocks(self):
        """Test PER with multiple code blocks per packet."""
        calc = PERCalculator(fec_type="ldpc")
        bler = 0.01
        num_blocks = 4

        per = calc.calculate_per(bler=bler, num_code_blocks=num_blocks)

        # Expected: 1 - (1 - 0.01)^4 ≈ 0.0394 (3.94%)
        expected = 1.0 - (1.0 - bler) ** num_blocks
        assert abs(per - expected) < 0.0001

    def test_per_zero_bler(self):
        """Test that PER = 0 when BLER = 0."""
        calc = PERCalculator(fec_type="ldpc")
        per = calc.calculate_per(bler=0.0, num_code_blocks=1)
        assert per == 0.0

    def test_per_requires_bler_for_coded(self):
        """Test that coded systems require BLER parameter."""
        calc = PERCalculator(fec_type="ldpc")
        with pytest.raises(ValueError, match="BLER required"):
            calc.calculate_per(ber=1e-5, packet_bits=12000)  # Missing bler

    def test_per_clamped_to_valid_range(self):
        """Test that PER is clamped to [0, 1] range."""
        calc = PERCalculator(fec_type="ldpc")

        per_low = calc.calculate_per(bler=0.0, num_code_blocks=1)
        per_high = calc.calculate_per(bler=1.0, num_code_blocks=1)

        assert 0.0 <= per_low <= 1.0
        assert 0.0 <= per_high <= 1.0


class TestPERToNetemLoss:
    """Test conversion of PER to netem loss percentage."""

    @pytest.mark.parametrize(
        "per,expected_loss_percent",
        [
            (0.0, 0.0),  # 0% PER → 0% loss
            (0.01, 1.0),  # 1% PER → 1% loss
            (0.10, 10.0),  # 10% PER → 10% loss
            (0.50, 50.0),  # 50% PER → 50% loss
            (1.0, 100.0),  # 100% PER → 100% loss
        ],
    )
    def test_per_to_loss_conversion(self, per: float, expected_loss_percent: float):
        """Test PER to netem loss percentage conversion."""
        loss_percent = PERCalculator.per_to_netem_loss(per)
        assert abs(loss_percent - expected_loss_percent) < 0.01


class TestEffectiveRateCalculation:
    """Test effective data rate calculation."""

    def test_rate_without_per(self):
        """Test rate calculation without packet loss."""
        # 80 MHz, 64-QAM (6 bits/sym), rate-1/2 code, no loss
        rate = PERCalculator.calculate_effective_rate(
            bandwidth_mhz=80.0, modulation_bits=6, code_rate=0.5, per=0.0
        )

        # Expected: 80 × 6 × 0.5 × 0.8 (efficiency) = 192 Mbps
        expected = 80.0 * 6 * 0.5 * 0.8
        assert abs(rate - expected) < 0.1

    def test_rate_with_per(self):
        """Test that PER reduces effective rate."""
        # Same params but with 10% PER
        rate_no_loss = PERCalculator.calculate_effective_rate(
            bandwidth_mhz=80.0, modulation_bits=6, code_rate=0.5, per=0.0
        )

        rate_with_loss = PERCalculator.calculate_effective_rate(
            bandwidth_mhz=80.0, modulation_bits=6, code_rate=0.5, per=0.10
        )

        # With 10% PER, rate should be 90% of no-loss rate
        expected_ratio = 0.9
        actual_ratio = rate_with_loss / rate_no_loss
        assert abs(actual_ratio - expected_ratio) < 0.01

    @pytest.mark.parametrize(
        "bandwidth_mhz,modulation_bits,code_rate,expected_rate_approx",
        [
            (20, 2, 0.5, 16),  # 20 MHz, QPSK, rate-1/2: ~16 Mbps
            (40, 4, 0.5, 64),  # 40 MHz, 16-QAM, rate-1/2: ~64 Mbps
            (80, 6, 0.5, 192),  # 80 MHz, 64-QAM, rate-1/2: ~192 Mbps
            (160, 8, 0.75, 768),  # 160 MHz, 256-QAM, rate-3/4: ~768 Mbps
        ],
    )
    def test_rate_calculation_examples(
        self,
        bandwidth_mhz: float,
        modulation_bits: int,
        code_rate: float,
        expected_rate_approx: float,
    ):
        """Test rate calculation for various WiFi configurations."""
        rate = PERCalculator.calculate_effective_rate(
            bandwidth_mhz=bandwidth_mhz,
            modulation_bits=modulation_bits,
            code_rate=code_rate,
            per=0.0,
        )

        # Allow ±10% tolerance for OFDM efficiency variation
        assert abs(rate - expected_rate_approx) / expected_rate_approx < 0.1

    def test_rate_minimum_threshold(self):
        """Test that rate has a minimum threshold (0.1 Mbps)."""
        # Extreme case: very low bandwidth, high PER
        rate = PERCalculator.calculate_effective_rate(
            bandwidth_mhz=1.0, modulation_bits=1, code_rate=0.1, per=0.99
        )

        # Should be clamped to minimum 0.1 Mbps
        assert rate >= 0.1

    def test_rate_uncoded_system(self):
        """Test rate calculation for uncoded system (code_rate=1.0)."""
        rate = PERCalculator.calculate_effective_rate(
            bandwidth_mhz=80.0, modulation_bits=6, code_rate=1.0, per=0.0
        )

        # Expected: 80 × 6 × 1.0 × 0.8 = 384 Mbps
        expected = 80.0 * 6 * 1.0 * 0.8
        assert abs(rate - expected) < 0.1


class TestCalculateNetemParams:
    """Test full channel metrics calculation."""

    def test_netem_params_uncoded(self):
        """Test netem params calculation for uncoded system."""
        calc = PERCalculator(fec_type="none")

        metrics = calc.calculate_netem_params(
            path_loss_db=60.0,
            received_power_dbm=-40.0,
            snr_db=48.0,
            ber=1e-5,
            bler=None,
            delay_ns=66.7,  # 20m / speed_of_light
            delay_spread_ns=10.0,
            bandwidth_mhz=80.0,
            modulation_bits=6,
            code_rate=1.0,
            packet_bits=12000,
        )

        assert isinstance(metrics, ChannelMetrics)
        assert abs(metrics.path_loss_db - 60.0) < 0.01
        assert abs(metrics.received_power_dbm - (-40.0)) < 0.01
        assert abs(metrics.snr_db - 48.0) < 0.01
        assert abs(metrics.ber - 1e-5) < 1e-10
        assert metrics.bler is None

        # Delay conversion: 66.7 ns → 0.0000667 ms
        assert abs(metrics.delay_ms - 0.0000667) < 1e-6
        # Jitter conversion: 10 ns → 0.00001 ms
        assert abs(metrics.jitter_ms - 0.00001) < 1e-6

        # PER from BER
        expected_per = calc.calculate_per(ber=1e-5, packet_bits=12000)
        assert abs(metrics.per - expected_per) < 0.001

        # Loss percent
        assert abs(metrics.loss_percent - expected_per * 100) < 0.1

        # Rate should be calculated
        assert metrics.rate_mbps > 0

    def test_netem_params_coded(self):
        """Test netem params calculation for coded system."""
        calc = PERCalculator(fec_type="ldpc")

        metrics = calc.calculate_netem_params(
            path_loss_db=60.0,
            received_power_dbm=-40.0,
            snr_db=48.0,
            ber=1e-6,  # Will be ignored (coded system)
            bler=0.001,
            delay_ns=66.7,
            delay_spread_ns=10.0,
            bandwidth_mhz=80.0,
            modulation_bits=6,
            code_rate=0.5,
            packet_bits=12000,
        )

        assert metrics.bler == 0.001
        # PER should equal BLER for single code block
        assert metrics.per == 0.001
        assert abs(metrics.loss_percent - 0.1) < 0.01  # 0.1%

    def test_netem_params_realistic_wifi6(self):
        """Test with realistic WiFi 6 parameters."""
        calc = PERCalculator(fec_type="ldpc")

        # Realistic WiFi 6 at 20m, excellent SNR
        metrics = calc.calculate_netem_params(
            path_loss_db=46.7,  # ~20m free space
            received_power_dbm=-26.7,  # 20dBm TX - 46.7dB loss
            snr_db=61.3,  # High SNR
            ber=1e-10,  # Excellent BER (ignored for coded)
            bler=1e-8,  # Excellent BLER
            delay_ns=66.7,  # 20m propagation
            delay_spread_ns=5.0,  # Low multipath
            bandwidth_mhz=80.0,
            modulation_bits=6,  # 64-QAM
            code_rate=0.5,
            packet_bits=12000,
        )

        # Sanity checks
        assert metrics.snr_db > 60
        assert metrics.per < 1e-6  # Very low packet error
        assert metrics.loss_percent < 0.001  # < 0.001%
        assert metrics.rate_mbps > 100  # High rate
        assert metrics.delay_ms < 1.0  # Sub-millisecond delay

    def test_netem_params_high_loss(self):
        """Test with high packet loss scenario."""
        calc = PERCalculator(fec_type="none")

        # Poor link: high BER
        metrics = calc.calculate_netem_params(
            path_loss_db=100.0,
            received_power_dbm=-80.0,
            snr_db=8.0,  # Low SNR
            ber=1e-3,  # High BER
            bler=None,
            delay_ns=333.3,  # 100m
            delay_spread_ns=50.0,  # High multipath
            bandwidth_mhz=20.0,
            modulation_bits=2,  # QPSK
            code_rate=1.0,
            packet_bits=12000,
        )

        # Should have significant packet loss
        assert metrics.per > 0.9  # >90% packet loss
        assert metrics.loss_percent > 90.0
        # Rate should be low due to QPSK and packet loss
        assert metrics.rate_mbps < 50


class TestChannelMetricsDataclass:
    """Test ChannelMetrics dataclass."""

    def test_channel_metrics_creation(self):
        """Test creating ChannelMetrics instance."""
        metrics = ChannelMetrics(
            path_loss_db=60.0,
            received_power_dbm=-40.0,
            snr_db=48.0,
            ber=1e-5,
            bler=0.001,
            per=0.113,
            delay_ms=0.067,
            jitter_ms=0.01,
            loss_percent=11.3,
            rate_mbps=192.0,
        )

        assert metrics.path_loss_db == 60.0
        assert metrics.received_power_dbm == -40.0
        assert metrics.snr_db == 48.0
        assert metrics.ber == 1e-5
        assert metrics.bler == 0.001
        assert metrics.per == 0.113
        assert metrics.delay_ms == 0.067
        assert metrics.jitter_ms == 0.01
        assert metrics.loss_percent == 11.3
        assert metrics.rate_mbps == 192.0

    def test_channel_metrics_optional_bler(self):
        """Test that BLER can be None for uncoded systems."""
        metrics = ChannelMetrics(
            path_loss_db=60.0,
            received_power_dbm=-40.0,
            snr_db=48.0,
            ber=1e-5,
            bler=None,  # Optional
            per=0.113,
            delay_ms=0.067,
            jitter_ms=0.01,
            loss_percent=11.3,
            rate_mbps=192.0,
        )

        assert metrics.bler is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
