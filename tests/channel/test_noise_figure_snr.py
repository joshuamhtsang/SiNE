"""
Tests for noise_figure_db impact on SNR calculations.

Verifies that noise figure properly affects noise floor and SNR calculations
in the channel computation pipeline.
"""

import math
import pytest

from sine.channel.snr import SNRCalculator
from sine.channel.sinr import SINRCalculator, calculate_thermal_noise


def test_noise_floor_calculation():
    """Verify noise floor changes correctly with noise figure.

    Noise floor formula: N = -174 dBm/Hz + 10*log10(BW) + NF

    For 80 MHz bandwidth:
    - NF=7 dB: noise_floor = -174 + 79 + 7 = -88 dBm
    - NF=4 dB: noise_floor = -174 + 79 + 4 = -91 dBm (3 dB better)
    - NF=10 dB: noise_floor = -174 + 79 + 10 = -85 dBm (3 dB worse)
    """
    bandwidth_hz = 80e6  # 80 MHz

    # Default WiFi 6: 7 dB NF
    snr_calc_7db = SNRCalculator(bandwidth_hz=bandwidth_hz, noise_figure_db=7.0)
    expected_noise_7db = -174.0 + 10 * math.log10(bandwidth_hz) + 7.0
    assert abs(snr_calc_7db.noise_floor_dbm - expected_noise_7db) < 0.01
    assert abs(snr_calc_7db.noise_floor_dbm - (-88.0)) < 0.1

    # High-performance 5G BS: 4 dB NF
    snr_calc_4db = SNRCalculator(bandwidth_hz=bandwidth_hz, noise_figure_db=4.0)
    expected_noise_4db = -174.0 + 10 * math.log10(bandwidth_hz) + 4.0
    assert abs(snr_calc_4db.noise_floor_dbm - expected_noise_4db) < 0.01
    assert abs(snr_calc_4db.noise_floor_dbm - (-91.0)) < 0.1

    # Low-cost IoT: 10 dB NF
    snr_calc_10db = SNRCalculator(bandwidth_hz=bandwidth_hz, noise_figure_db=10.0)
    expected_noise_10db = -174.0 + 10 * math.log10(bandwidth_hz) + 10.0
    assert abs(snr_calc_10db.noise_floor_dbm - expected_noise_10db) < 0.01
    assert abs(snr_calc_10db.noise_floor_dbm - (-85.0)) < 0.1

    # Verify 3 dB difference between 4 dB and 7 dB NF
    assert abs((snr_calc_7db.noise_floor_dbm - snr_calc_4db.noise_floor_dbm) - 3.0) < 0.01

    # Verify 3 dB difference between 7 dB and 10 dB NF
    assert abs((snr_calc_10db.noise_floor_dbm - snr_calc_7db.noise_floor_dbm) - 3.0) < 0.01


def test_snr_scales_with_noise_figure():
    """Verify SNR decreases when noise figure increases.

    Fixed link scenario:
    - TX power: 20 dBm
    - Path loss: 68 dB (e.g., 20m at 5.18 GHz)
    - RX power: 20 - 68 = -48 dBm
    - Bandwidth: 80 MHz

    Expected SNR:
    - NF=7 dB: SNR = -48 - (-88) = 40 dB
    - NF=10 dB: SNR = -48 - (-85) = 37 dB (3 dB worse)
    - NF=4 dB: SNR = -48 - (-91) = 43 dB (3 dB better)
    """
    bandwidth_hz = 80e6  # 80 MHz
    tx_power_dbm = 20.0
    path_loss_db = 68.0  # Typical for 20m at 5.18 GHz
    tx_gain_dbi = 0.0
    rx_gain_dbi = 0.0

    # WiFi 6 default: 7 dB NF
    snr_calc_7db = SNRCalculator(bandwidth_hz=bandwidth_hz, noise_figure_db=7.0)
    rx_power_7db, snr_7db = snr_calc_7db.calculate_link_snr(
        tx_power_dbm=tx_power_dbm,
        tx_gain_dbi=tx_gain_dbi,
        rx_gain_dbi=rx_gain_dbi,
        path_loss_db=path_loss_db,
        from_sionna=False,  # FSPL mode
    )
    expected_rx_power = tx_power_dbm + tx_gain_dbi + rx_gain_dbi - path_loss_db
    assert abs(rx_power_7db - expected_rx_power) < 0.01
    assert abs(snr_7db - 40.0) < 0.1

    # Low-cost IoT: 10 dB NF
    snr_calc_10db = SNRCalculator(bandwidth_hz=bandwidth_hz, noise_figure_db=10.0)
    rx_power_10db, snr_10db = snr_calc_10db.calculate_link_snr(
        tx_power_dbm=tx_power_dbm,
        tx_gain_dbi=tx_gain_dbi,
        rx_gain_dbi=rx_gain_dbi,
        path_loss_db=path_loss_db,
        from_sionna=False,
    )
    assert abs(rx_power_10db - expected_rx_power) < 0.01
    assert abs(snr_10db - 37.0) < 0.1

    # High-performance 5G BS: 4 dB NF
    snr_calc_4db = SNRCalculator(bandwidth_hz=bandwidth_hz, noise_figure_db=4.0)
    rx_power_4db, snr_4db = snr_calc_4db.calculate_link_snr(
        tx_power_dbm=tx_power_dbm,
        tx_gain_dbi=tx_gain_dbi,
        rx_gain_dbi=rx_gain_dbi,
        path_loss_db=path_loss_db,
        from_sionna=False,
    )
    assert abs(rx_power_4db - expected_rx_power) < 0.01
    assert abs(snr_4db - 43.0) < 0.1

    # Verify SNR differences
    assert abs((snr_7db - snr_10db) - 3.0) < 0.1  # 7 dB NF is 3 dB better than 10 dB
    assert abs((snr_4db - snr_7db) - 3.0) < 0.1  # 4 dB NF is 3 dB better than 7 dB


def test_calculate_thermal_noise_function():
    """Test the standalone calculate_thermal_noise() function."""
    bandwidth_hz = 80e6  # 80 MHz

    # Default: 7 dB NF
    noise_7db = calculate_thermal_noise(bandwidth_hz=bandwidth_hz, noise_figure_db=7.0)
    assert abs(noise_7db - (-88.0)) < 0.1

    # High-performance: 4 dB NF
    noise_4db = calculate_thermal_noise(bandwidth_hz=bandwidth_hz, noise_figure_db=4.0)
    assert abs(noise_4db - (-91.0)) < 0.1

    # Low-cost: 10 dB NF
    noise_10db = calculate_thermal_noise(bandwidth_hz=bandwidth_hz, noise_figure_db=10.0)
    assert abs(noise_10db - (-85.0)) < 0.1

    # Verify 3 dB steps
    assert abs((noise_7db - noise_4db) - 3.0) < 0.01
    assert abs((noise_10db - noise_7db) - 3.0) < 0.01


def test_sinr_calculator_noise_figure():
    """Test SINRCalculator with different noise figures."""
    # Create SINR calculators with different noise figures
    sinr_calc_7db = SINRCalculator(
        rx_sensitivity_dbm=-80.0,
        noise_figure_db=7.0,
    )
    assert sinr_calc_7db.noise_figure_db == 7.0

    sinr_calc_4db = SINRCalculator(
        rx_sensitivity_dbm=-80.0,
        noise_figure_db=4.0,
    )
    assert sinr_calc_4db.noise_figure_db == 4.0

    sinr_calc_10db = SINRCalculator(
        rx_sensitivity_dbm=-80.0,
        noise_figure_db=10.0,
    )
    assert sinr_calc_10db.noise_figure_db == 10.0


def test_noise_figure_boundary_values():
    """Test SNR calculation at noise figure boundary values."""
    bandwidth_hz = 80e6

    # Minimum: 0 dB (theoretical ideal)
    snr_calc_0db = SNRCalculator(bandwidth_hz=bandwidth_hz, noise_figure_db=0.0)
    expected_noise_0db = -174.0 + 10 * math.log10(bandwidth_hz) + 0.0
    assert abs(snr_calc_0db.noise_floor_dbm - expected_noise_0db) < 0.01
    assert abs(snr_calc_0db.noise_floor_dbm - (-95.0)) < 0.1

    # Maximum: 20 dB (extremely poor receiver)
    snr_calc_20db = SNRCalculator(bandwidth_hz=bandwidth_hz, noise_figure_db=20.0)
    expected_noise_20db = -174.0 + 10 * math.log10(bandwidth_hz) + 20.0
    assert abs(snr_calc_20db.noise_floor_dbm - expected_noise_20db) < 0.01
    assert abs(snr_calc_20db.noise_floor_dbm - (-75.0)) < 0.1


def test_different_bandwidths_with_noise_figure():
    """Test noise floor calculation for different bandwidths.

    Typical WiFi 6 bandwidths:
    - 20 MHz: -174 + 73 + 7 = -94 dBm
    - 40 MHz: -174 + 76 + 7 = -91 dBm
    - 80 MHz: -174 + 79 + 7 = -88 dBm
    - 160 MHz: -174 + 82 + 7 = -85 dBm
    """
    noise_figure_db = 7.0

    # 20 MHz
    snr_20mhz = SNRCalculator(bandwidth_hz=20e6, noise_figure_db=noise_figure_db)
    assert abs(snr_20mhz.noise_floor_dbm - (-94.0)) < 0.1

    # 40 MHz
    snr_40mhz = SNRCalculator(bandwidth_hz=40e6, noise_figure_db=noise_figure_db)
    assert abs(snr_40mhz.noise_floor_dbm - (-91.0)) < 0.1

    # 80 MHz
    snr_80mhz = SNRCalculator(bandwidth_hz=80e6, noise_figure_db=noise_figure_db)
    assert abs(snr_80mhz.noise_floor_dbm - (-88.0)) < 0.1

    # 160 MHz
    snr_160mhz = SNRCalculator(bandwidth_hz=160e6, noise_figure_db=noise_figure_db)
    assert abs(snr_160mhz.noise_floor_dbm - (-85.0)) < 0.1

    # Each doubling of bandwidth increases noise by 3 dB
    assert abs((snr_40mhz.noise_floor_dbm - snr_20mhz.noise_floor_dbm) - 3.0) < 0.1
    assert abs((snr_80mhz.noise_floor_dbm - snr_40mhz.noise_floor_dbm) - 3.0) < 0.1
    assert abs((snr_160mhz.noise_floor_dbm - snr_80mhz.noise_floor_dbm) - 3.0) < 0.1
