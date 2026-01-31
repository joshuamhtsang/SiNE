"""
Unit tests for snr.py - SNR calculation from link budget.

Tests SNR calculation including:
- Received power calculation (with/without Sionna antenna gains)
- Noise floor calculation
- Free-space path loss (FSPL)
- Link budget SNR
"""

import pytest
import numpy as np
from sine.channel.snr import SNRCalculator, BOLTZMANN_DBM_HZ, SPEED_OF_LIGHT


class TestSNRCalculator:
    """Test SNR calculator initialization and basic functions."""

    def test_initialization_defaults(self):
        """Test SNRCalculator initialization with default values."""
        calc = SNRCalculator(bandwidth_hz=80e6)
        assert calc.bandwidth_hz == 80e6
        assert calc.temperature_k == 290.0
        assert calc.noise_figure_db == 7.0
        # Noise floor = -174 + 10*log10(80e6) + 7
        # = -174 + 79.03 + 7 = -87.97 dBm
        expected_noise = -174 + 10 * np.log10(80e6) + 7
        assert abs(calc.noise_floor_dbm - expected_noise) < 0.1

    def test_initialization_custom_params(self):
        """Test initialization with custom temperature and noise figure."""
        calc = SNRCalculator(
            bandwidth_hz=20e6, temperature_k=300.0, noise_figure_db=5.0
        )
        assert calc.bandwidth_hz == 20e6
        assert calc.temperature_k == 300.0
        assert calc.noise_figure_db == 5.0

    @pytest.mark.parametrize(
        "bandwidth_hz,expected_noise_approx",
        [
            (20e6, -174 + 73 + 7),  # 20 MHz: -94 dBm (with 7dB NF)
            (40e6, -174 + 76 + 7),  # 40 MHz: -91 dBm
            (80e6, -174 + 79 + 7),  # 80 MHz: -88 dBm
            (160e6, -174 + 82 + 7),  # 160 MHz: -85 dBm
        ],
    )
    def test_noise_floor_calculation(
        self, bandwidth_hz: float, expected_noise_approx: float
    ):
        """Test noise floor calculation for various bandwidths."""
        calc = SNRCalculator(bandwidth_hz=bandwidth_hz, noise_figure_db=7.0)
        # Allow ±1 dB tolerance for rounding
        assert abs(calc.noise_floor_dbm - expected_noise_approx) < 1.0


class TestReceivedPowerCalculation:
    """Test received power calculation with and without Sionna antenna gains."""

    def test_received_power_sionna_mode(self):
        """Test received power when path loss from Sionna RT (includes antenna gains)."""
        calc = SNRCalculator(bandwidth_hz=80e6)
        tx_power_dbm = 20.0
        # These gains should be IGNORED when from_sionna=True
        tx_gain_dbi = 3.0
        rx_gain_dbi = 3.0
        channel_loss_db = 60.0  # Path loss from Sionna (includes antenna patterns)

        rx_power = calc.calculate_received_power(
            tx_power_dbm=tx_power_dbm,
            tx_gain_dbi=tx_gain_dbi,
            rx_gain_dbi=rx_gain_dbi,
            path_loss_db=channel_loss_db,
            from_sionna=True,
        )

        # Expected: 20 - 60 = -40 dBm (antenna gains NOT added)
        expected = tx_power_dbm - channel_loss_db
        assert abs(rx_power - expected) < 0.01

    def test_received_power_fspl_mode(self):
        """Test received power when using FSPL (add antenna gains explicitly)."""
        calc = SNRCalculator(bandwidth_hz=80e6)
        tx_power_dbm = 20.0
        tx_gain_dbi = 3.0
        rx_gain_dbi = 3.0
        path_loss_db = 60.0  # Pure propagation loss (no antenna effects)

        rx_power = calc.calculate_received_power(
            tx_power_dbm=tx_power_dbm,
            tx_gain_dbi=tx_gain_dbi,
            rx_gain_dbi=rx_gain_dbi,
            path_loss_db=path_loss_db,
            from_sionna=False,
        )

        # Expected: 20 + 3 - 60 + 3 = -34 dBm (antenna gains ADDED)
        expected = tx_power_dbm + tx_gain_dbi - path_loss_db + rx_gain_dbi
        assert abs(rx_power - expected) < 0.01

    def test_antenna_gain_difference_warning(self):
        """Test that Sionna vs FSPL modes give different results (antenna gain handling)."""
        calc = SNRCalculator(bandwidth_hz=80e6)
        params = {
            "tx_power_dbm": 20.0,
            "tx_gain_dbi": 3.0,
            "rx_gain_dbi": 3.0,
            "path_loss_db": 60.0,
        }

        rx_power_sionna = calc.calculate_received_power(**params, from_sionna=True)
        rx_power_fspl = calc.calculate_received_power(**params, from_sionna=False)

        # With 3dBi gains on both sides, difference should be 6dB
        expected_diff = params["tx_gain_dbi"] + params["rx_gain_dbi"]
        actual_diff = rx_power_fspl - rx_power_sionna
        assert abs(actual_diff - expected_diff) < 0.01


class TestSNRCalculation:
    """Test SNR calculation from received power."""

    def test_calculate_snr_basic(self):
        """Test basic SNR calculation from received power."""
        calc = SNRCalculator(bandwidth_hz=80e6, noise_figure_db=7.0)
        # Noise floor ≈ -88 dBm
        received_power_dbm = -40.0

        snr_db = calc.calculate_snr(received_power_dbm)

        # SNR = -40 - (-88) = 48 dB
        expected_snr = received_power_dbm - calc.noise_floor_dbm
        assert abs(snr_db - expected_snr) < 0.01

    def test_snr_positive_with_strong_signal(self):
        """Test that strong signal gives positive SNR."""
        calc = SNRCalculator(bandwidth_hz=80e6)
        rx_power = -30.0  # Strong signal
        snr = calc.calculate_snr(rx_power)
        assert snr > 0

    def test_snr_negative_with_weak_signal(self):
        """Test that weak signal gives negative SNR."""
        calc = SNRCalculator(bandwidth_hz=80e6)
        rx_power = -100.0  # Very weak signal (below noise)
        snr = calc.calculate_snr(rx_power)
        assert snr < 0

    @pytest.mark.parametrize(
        "rx_power_dbm,bandwidth_hz,nf_db,expected_snr_approx",
        [
            (-40, 80e6, 7, 48),  # -40 - (-88) = 48 dB
            (-50, 80e6, 7, 38),  # -50 - (-88) = 38 dB
            (-30, 20e6, 7, 64),  # -30 - (-94) = 64 dB
        ],
    )
    def test_snr_calculation_examples(
        self,
        rx_power_dbm: float,
        bandwidth_hz: float,
        nf_db: float,
        expected_snr_approx: float,
    ):
        """Test SNR calculation with various parameters."""
        calc = SNRCalculator(bandwidth_hz=bandwidth_hz, noise_figure_db=nf_db)
        snr = calc.calculate_snr(rx_power_dbm)
        # Allow ±1 dB tolerance
        assert abs(snr - expected_snr_approx) < 1.0


class TestLinkSNR:
    """Test full link budget SNR calculation."""

    def test_calculate_link_snr_sionna(self):
        """Test full link SNR calculation with Sionna path loss."""
        calc = SNRCalculator(bandwidth_hz=80e6, noise_figure_db=7.0)
        tx_power_dbm = 20.0
        tx_gain_dbi = 3.0  # Ignored
        rx_gain_dbi = 3.0  # Ignored
        channel_loss_db = 60.0

        rx_power, snr = calc.calculate_link_snr(
            tx_power_dbm=tx_power_dbm,
            tx_gain_dbi=tx_gain_dbi,
            rx_gain_dbi=rx_gain_dbi,
            path_loss_db=channel_loss_db,
            from_sionna=True,
        )

        # Rx power = 20 - 60 = -40 dBm
        # Noise ≈ -88 dBm
        # SNR = -40 - (-88) = 48 dB
        assert abs(rx_power - (-40.0)) < 0.01
        expected_snr = rx_power - calc.noise_floor_dbm
        assert abs(snr - expected_snr) < 0.1

    def test_calculate_link_snr_fspl(self):
        """Test full link SNR calculation with FSPL."""
        calc = SNRCalculator(bandwidth_hz=80e6, noise_figure_db=7.0)
        tx_power_dbm = 20.0
        tx_gain_dbi = 3.0
        rx_gain_dbi = 3.0
        path_loss_db = 60.0

        rx_power, snr = calc.calculate_link_snr(
            tx_power_dbm=tx_power_dbm,
            tx_gain_dbi=tx_gain_dbi,
            rx_gain_dbi=rx_gain_dbi,
            path_loss_db=path_loss_db,
            from_sionna=False,
        )

        # Rx power = 20 + 3 - 60 + 3 = -34 dBm
        # SNR = -34 - (-88) = 54 dB
        assert abs(rx_power - (-34.0)) < 0.01
        expected_snr = rx_power - calc.noise_floor_dbm
        assert abs(snr - expected_snr) < 0.1

    def test_link_snr_realistic_wifi6(self):
        """Test realistic WiFi 6 link at 20m in free space."""
        calc = SNRCalculator(bandwidth_hz=80e6, noise_figure_db=7.0)

        # Typical WiFi 6 params
        tx_power_dbm = 20.0  # 100mW
        tx_gain_dbi = 3.0
        rx_gain_dbi = 3.0

        # FSPL at 20m, 5.18 GHz
        distance_m = 20.0
        frequency_hz = 5.18e9
        fspl = calc.free_space_path_loss(distance_m, frequency_hz)

        rx_power, snr = calc.calculate_link_snr(
            tx_power_dbm=tx_power_dbm,
            tx_gain_dbi=tx_gain_dbi,
            rx_gain_dbi=rx_gain_dbi,
            path_loss_db=fspl,
            from_sionna=False,
        )

        # At 20m in free space, should have excellent SNR (>40 dB)
        assert snr > 40.0
        # Received power should be well above noise
        assert rx_power > calc.noise_floor_dbm + 20


class TestFreeSpacePathLoss:
    """Test FSPL calculation."""

    def test_fspl_at_1m(self):
        """Test FSPL at 1 meter (reference distance)."""
        frequency_hz = 5.18e9  # 5.18 GHz (WiFi)
        fspl = SNRCalculator.free_space_path_loss(distance_m=1.0, frequency_hz=frequency_hz)

        # FSPL(1m, 5.18GHz) = 20*log10(1) + 20*log10(5.18e9) - 147.55
        # = 0 + 194.28 - 147.55 = 46.73 dB
        expected = 20 * np.log10(frequency_hz) - 147.55
        assert abs(fspl - expected) < 0.1

    def test_fspl_doubles_per_distance_doubling(self):
        """Test that FSPL increases by 6dB when distance doubles (20*log10(2))."""
        frequency_hz = 5.18e9

        fspl_10m = SNRCalculator.free_space_path_loss(10.0, frequency_hz)
        fspl_20m = SNRCalculator.free_space_path_loss(20.0, frequency_hz)

        # Difference should be 20*log10(2) ≈ 6.02 dB
        diff = fspl_20m - fspl_10m
        assert abs(diff - 6.02) < 0.1

    def test_fspl_at_zero_distance(self):
        """Test that FSPL at 0m returns 0 (edge case)."""
        fspl = SNRCalculator.free_space_path_loss(0.0, 5.18e9)
        assert fspl == 0.0

    def test_fspl_realistic_values(self):
        """Test FSPL at realistic distances for WiFi."""
        frequency_hz = 5.18e9

        # 10m: ~66 dB
        fspl_10m = SNRCalculator.free_space_path_loss(10.0, frequency_hz)
        assert 65 < fspl_10m < 67

        # 20m: ~72 dB
        fspl_20m = SNRCalculator.free_space_path_loss(20.0, frequency_hz)
        assert 71 < fspl_20m < 73

        # 100m: ~86 dB
        fspl_100m = SNRCalculator.free_space_path_loss(100.0, frequency_hz)
        assert 85 < fspl_100m < 87


class TestDistanceFromPositions:
    """Test 3D distance calculation."""

    def test_distance_same_position(self):
        """Test distance between same positions is zero."""
        pos1 = (0.0, 0.0, 0.0)
        pos2 = (0.0, 0.0, 0.0)
        dist = SNRCalculator.distance_from_positions(pos1, pos2)
        assert dist == 0.0

    def test_distance_along_x_axis(self):
        """Test distance along X axis."""
        pos1 = (0.0, 0.0, 0.0)
        pos2 = (10.0, 0.0, 0.0)
        dist = SNRCalculator.distance_from_positions(pos1, pos2)
        assert abs(dist - 10.0) < 0.01

    def test_distance_diagonal_2d(self):
        """Test distance on XY plane (diagonal)."""
        pos1 = (0.0, 0.0, 0.0)
        pos2 = (3.0, 4.0, 0.0)  # 3-4-5 triangle
        dist = SNRCalculator.distance_from_positions(pos1, pos2)
        assert abs(dist - 5.0) < 0.01

    def test_distance_3d(self):
        """Test full 3D distance."""
        pos1 = (0.0, 0.0, 0.0)
        pos2 = (1.0, 1.0, 1.0)
        expected = np.sqrt(3)  # sqrt(1^2 + 1^2 + 1^2)
        dist = SNRCalculator.distance_from_positions(pos1, pos2)
        assert abs(dist - expected) < 0.01

    def test_distance_symmetry(self):
        """Test that distance is symmetric (d(A,B) = d(B,A))."""
        pos1 = (1.0, 2.0, 3.0)
        pos2 = (4.0, 5.0, 6.0)
        dist1 = SNRCalculator.distance_from_positions(pos1, pos2)
        dist2 = SNRCalculator.distance_from_positions(pos2, pos1)
        assert abs(dist1 - dist2) < 1e-10

    def test_distance_realistic_wifi(self):
        """Test distance for realistic WiFi node positions."""
        # Node1 at origin, Node2 at 20m along X axis, 1m height
        pos1 = (0.0, 0.0, 1.0)
        pos2 = (20.0, 0.0, 1.0)
        dist = SNRCalculator.distance_from_positions(pos1, pos2)
        assert abs(dist - 20.0) < 0.01


class TestConstants:
    """Test physical constants."""

    def test_boltzmann_constant(self):
        """Test that Boltzmann constant is correct."""
        # kTB at room temp (290K) = -174 dBm/Hz
        assert BOLTZMANN_DBM_HZ == -174.0

    def test_speed_of_light(self):
        """Test that speed of light is correct."""
        assert SPEED_OF_LIGHT == 3e8  # m/s


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
