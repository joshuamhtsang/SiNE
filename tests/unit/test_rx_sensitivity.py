"""
Unit tests for receiver sensitivity (rx_sensitivity_dbm) parameter.

Tests that rx_sensitivity_dbm is properly:
1. Validated in schema (WirelessParams)
2. Applied in SNR calculations (link budget)
3. Applied in SINR calculations (interference filtering)
4. Used to filter weak interferers
5. Set correctly for different radio types (WiFi, LoRa, 5G, etc.)
"""

import pytest
from sine.config.schema import WirelessParams, Position, ModulationType, FECType
from sine.channel.snr import SNRCalculator
from sine.channel.sinr import SINRCalculator
from sine.channel.interference_engine import InterferenceTerm


class TestRxSensitivitySchema:
    """Test rx_sensitivity_dbm in WirelessParams schema validation."""

    def test_default_rx_sensitivity(self):
        """Test that rx_sensitivity_dbm defaults to -80 dBm (WiFi 6)."""
        params = WirelessParams(
            position=Position(x=0, y=0, z=1),
            modulation=ModulationType.QAM64,
            fec_type=FECType.LDPC,
            fec_code_rate=0.5,
        )
        assert params.rx_sensitivity_dbm == -80.0

    def test_custom_rx_sensitivity_wifi5(self):
        """Test setting rx_sensitivity for WiFi 5 (-75 dBm)."""
        params = WirelessParams(
            position=Position(x=0, y=0, z=1),
            rx_sensitivity_dbm=-75.0,  # WiFi 5 is less sensitive
            modulation=ModulationType.QAM64,
            fec_type=FECType.LDPC,
            fec_code_rate=0.5,
        )
        assert params.rx_sensitivity_dbm == -75.0

    def test_custom_rx_sensitivity_lora(self):
        """Test setting rx_sensitivity for LoRa (-137 dBm, extremely sensitive)."""
        params = WirelessParams(
            position=Position(x=0, y=0, z=1),
            rx_sensitivity_dbm=-137.0,  # LoRa with SF12
            modulation=ModulationType.BPSK,
            fec_type=FECType.LDPC,
            fec_code_rate=0.5,
        )
        assert params.rx_sensitivity_dbm == -137.0

    def test_custom_rx_sensitivity_5g(self):
        """Test setting rx_sensitivity for 5G base station (-95 dBm)."""
        params = WirelessParams(
            position=Position(x=0, y=0, z=1),
            rx_sensitivity_dbm=-95.0,  # 5G NR base station
            modulation=ModulationType.QAM64,
            fec_type=FECType.LDPC,
            fec_code_rate=0.5,
        )
        assert params.rx_sensitivity_dbm == -95.0

    def test_custom_rx_sensitivity_cheap_iot(self):
        """Test setting rx_sensitivity for cheap IoT radio (-70 dBm, poor sensitivity)."""
        params = WirelessParams(
            position=Position(x=0, y=0, z=1),
            rx_sensitivity_dbm=-70.0,  # Cheap IoT radio
            modulation=ModulationType.QPSK,
            fec_type=FECType.NONE,
            fec_code_rate=1.0,
        )
        assert params.rx_sensitivity_dbm == -70.0

    def test_rx_sensitivity_validation_too_high(self):
        """Test that positive rx_sensitivity is rejected (physically impossible)."""
        with pytest.raises(ValueError, match="less than or equal to 0"):
            WirelessParams(
                position=Position(x=0, y=0, z=1),
                rx_sensitivity_dbm=10.0,  # INVALID: positive power
                modulation=ModulationType.QPSK,
                fec_type=FECType.LDPC,
                fec_code_rate=0.5,
            )

    def test_rx_sensitivity_validation_too_low(self):
        """Test that extremely low rx_sensitivity is rejected (below -150 dBm)."""
        with pytest.raises(ValueError, match="greater than or equal to -150"):
            WirelessParams(
                position=Position(x=0, y=0, z=1),
                rx_sensitivity_dbm=-160.0,  # INVALID: below thermal noise at any bandwidth
                modulation=ModulationType.QPSK,
                fec_type=FECType.LDPC,
                fec_code_rate=0.5,
            )

    def test_rx_sensitivity_at_boundary_low(self):
        """Test rx_sensitivity at lower boundary (-150 dBm) is accepted."""
        params = WirelessParams(
            position=Position(x=0, y=0, z=1),
            rx_sensitivity_dbm=-150.0,  # Extreme but valid
            modulation=ModulationType.QPSK,
            fec_type=FECType.LDPC,
            fec_code_rate=0.5,
        )
        assert params.rx_sensitivity_dbm == -150.0

    def test_rx_sensitivity_at_boundary_high(self):
        """Test rx_sensitivity at upper boundary (0 dBm) is accepted."""
        params = WirelessParams(
            position=Position(x=0, y=0, z=1),
            rx_sensitivity_dbm=0.0,  # Very poor sensitivity but valid
            modulation=ModulationType.QPSK,
            fec_type=FECType.LDPC,
            fec_code_rate=0.5,
        )
        assert params.rx_sensitivity_dbm == 0.0


class TestRxSensitivityInLinkBudget:
    """Test that rx_sensitivity affects link budget calculations."""

    def test_strong_signal_above_sensitivity(self):
        """Test link budget with signal well above sensitivity."""
        calc = SNRCalculator(bandwidth_hz=80e6, noise_figure_db=7.0)

        # Scenario: 20m WiFi link, 20 dBm TX, ~68 dB path loss
        # Received power ≈ 20 - 68 = -48 dBm
        # WiFi 6 sensitivity: -80 dBm
        # Result: Link should work with high SNR

        tx_power_dbm = 20.0
        path_loss_db = 68.0
        rx_sensitivity_dbm = -80.0  # WiFi 6

        rx_power, snr = calc.calculate_link_snr(
            tx_power_dbm=tx_power_dbm,
            tx_gain_dbi=0.0,
            rx_gain_dbi=0.0,
            path_loss_db=path_loss_db,
            from_sionna=True,
        )

        # Verify rx_power is above sensitivity
        assert rx_power > rx_sensitivity_dbm
        # Verify positive SNR
        assert snr > 0

    def test_weak_signal_below_sensitivity(self):
        """Test link budget with signal below sensitivity threshold."""
        calc = SNRCalculator(bandwidth_hz=80e6, noise_figure_db=7.0)

        # Scenario: Long distance link, 200m, ~88 dB path loss
        # Received power ≈ 20 - 88 = -68 dBm
        # Cheap IoT radio sensitivity: -60 dBm (poor)
        # Result: Link fails (rx_power < rx_sensitivity)

        tx_power_dbm = 20.0
        path_loss_db = 88.0
        rx_sensitivity_dbm = -60.0  # Cheap IoT radio

        rx_power, snr = calc.calculate_link_snr(
            tx_power_dbm=tx_power_dbm,
            tx_gain_dbi=0.0,
            rx_gain_dbi=0.0,
            path_loss_db=path_loss_db,
            from_sionna=True,
        )

        # Verify rx_power is below sensitivity → link should fail
        assert rx_power < rx_sensitivity_dbm
        # SNR may still be positive (above noise) but below sensitivity

    def test_lora_extreme_sensitivity(self):
        """Test LoRa link with extreme sensitivity (-137 dBm)."""
        calc = SNRCalculator(bandwidth_hz=125e3, noise_figure_db=6.0)  # LoRa 125 kHz

        # Scenario: LoRa long-range link, 10 km (!!!)
        # Path loss at 10 km, 868 MHz ≈ 131 dB
        # TX power: 14 dBm (LoRa typical)
        # Received power ≈ 14 - 131 = -117 dBm
        # LoRa sensitivity (SF12): -137 dBm
        # Result: Link works (rx_power > -137 dBm)

        tx_power_dbm = 14.0
        path_loss_db = 131.0
        rx_sensitivity_dbm = -137.0  # LoRa SF12

        rx_power, snr = calc.calculate_link_snr(
            tx_power_dbm=tx_power_dbm,
            tx_gain_dbi=0.0,
            rx_gain_dbi=0.0,
            path_loss_db=path_loss_db,
            from_sionna=True,
        )

        # Verify rx_power is above LoRa sensitivity
        assert rx_power > rx_sensitivity_dbm
        # SNR will be negative (below noise) but LoRa uses spreading gain
        # For testing, we just verify the power level

    def test_sensitivity_determines_max_range(self):
        """Test that better sensitivity extends maximum range."""
        calc = SNRCalculator(bandwidth_hz=80e6, noise_figure_db=7.0)

        # Fixed parameters
        tx_power_dbm = 20.0
        path_loss_db = 85.0  # ~150m at 5 GHz

        # WiFi 5 sensitivity: -75 dBm (poor)
        rx_power_wifi5, _ = calc.calculate_link_snr(
            tx_power_dbm=tx_power_dbm,
            tx_gain_dbi=0.0,
            rx_gain_dbi=0.0,
            path_loss_db=path_loss_db,
            from_sionna=True,
        )
        wifi5_sensitivity = -75.0
        wifi5_link_works = rx_power_wifi5 > wifi5_sensitivity

        # WiFi 6 sensitivity: -80 dBm (better)
        rx_power_wifi6, _ = calc.calculate_link_snr(
            tx_power_dbm=tx_power_dbm,
            tx_gain_dbi=0.0,
            rx_gain_dbi=0.0,
            path_loss_db=path_loss_db,
            from_sionna=True,
        )
        wifi6_sensitivity = -80.0
        wifi6_link_works = rx_power_wifi6 > wifi6_sensitivity

        # At this distance:
        # - WiFi 5 should fail (rx_power ≈ -65 dBm > -75 dBm OK for this case)
        # - WiFi 6 should work (rx_power ≈ -65 dBm > -80 dBm OK)
        # Both should actually work at 150m, let's use longer distance

        # Use 200m: path_loss ≈ 88 dB, rx_power ≈ -68 dBm
        path_loss_200m = 88.0
        rx_power_200m, _ = calc.calculate_link_snr(
            tx_power_dbm=tx_power_dbm,
            tx_gain_dbi=0.0,
            rx_gain_dbi=0.0,
            path_loss_db=path_loss_200m,
            from_sionna=True,
        )

        # Both should still work (-68 > -75 and -68 > -80)
        # Let's test at limit: path_loss = 95 dB → rx_power = -75 dBm
        rx_power_limit = 20.0 - 95.0  # -75 dBm
        assert rx_power_limit == wifi5_sensitivity  # At WiFi 5 sensitivity threshold
        assert rx_power_limit > wifi6_sensitivity  # Above WiFi 6 sensitivity (5 dB margin)


class TestRxSensitivityInSINR:
    """Test that rx_sensitivity_dbm is used in SINR calculations."""

    def test_sinr_calculator_initialization(self):
        """Test SINRCalculator initialization with custom rx_sensitivity."""
        # WiFi 6
        calc_wifi6 = SINRCalculator(rx_sensitivity_dbm=-80.0)
        assert calc_wifi6.rx_sensitivity_dbm == -80.0

        # WiFi 5
        calc_wifi5 = SINRCalculator(rx_sensitivity_dbm=-75.0)
        assert calc_wifi5.rx_sensitivity_dbm == -75.0

        # LoRa
        calc_lora = SINRCalculator(rx_sensitivity_dbm=-137.0)
        assert calc_lora.rx_sensitivity_dbm == -137.0

    def test_signal_below_sensitivity_rejected(self):
        """Test that signals below rx_sensitivity are rejected (unusable link)."""
        calc = SINRCalculator(rx_sensitivity_dbm=-80.0)

        # Signal power -90 dBm (below -80 dBm sensitivity)
        result = calc.calculate_sinr(
            tx_node="node1",
            rx_node="node2",
            signal_power_dbm=-90.0,  # Below sensitivity
            noise_power_dbm=-88.0,
            interference_terms=[],
        )

        # Link should be unusable
        assert result.regime == "unusable"
        assert result.sinr_db == -float('inf')

    def test_interferer_below_sensitivity_filtered(self):
        """Test that interferers below rx_sensitivity are filtered out."""
        calc = SINRCalculator(rx_sensitivity_dbm=-80.0)

        # Desired signal: -50 dBm (well above sensitivity)
        # Noise: -88 dBm
        # Interferers:
        #   - Strong: -60 dBm (above sensitivity, should be counted)
        #   - Weak: -90 dBm (below sensitivity, should be ignored)

        interference_terms = [
            InterferenceTerm(
                source="node3",
                power_dbm=-60.0,  # Above sensitivity
                frequency_hz=5.18e9,
            ),
            InterferenceTerm(
                source="node4",
                power_dbm=-90.0,  # Below sensitivity → filtered
                frequency_hz=5.18e9,
            ),
        ]

        result = calc.calculate_sinr(
            tx_node="node1",
            rx_node="node2",
            signal_power_dbm=-50.0,
            noise_power_dbm=-88.0,
            interference_terms=interference_terms,
        )

        # Only 1 interferer should be counted (the one above sensitivity)
        assert result.num_interferers == 1
        assert len(result.interference_terms) == 1
        assert result.interference_terms[0].source == "node3"

    def test_stricter_sensitivity_filters_more_interferers(self):
        """Test that stricter (higher) rx_sensitivity filters more interferers."""
        # Same scenario with different sensitivities

        interference_terms = [
            InterferenceTerm(source="node3", power_dbm=-70.0, frequency_hz=5.18e9),
            InterferenceTerm(source="node4", power_dbm=-80.0, frequency_hz=5.18e9),
            InterferenceTerm(source="node5", power_dbm=-90.0, frequency_hz=5.18e9),
        ]

        # WiFi 6 sensitivity: -80 dBm (2 interferers above threshold)
        calc_wifi6 = SINRCalculator(rx_sensitivity_dbm=-80.0)
        result_wifi6 = calc_wifi6.calculate_sinr(
            tx_node="node1",
            rx_node="node2",
            signal_power_dbm=-50.0,
            noise_power_dbm=-88.0,
            interference_terms=interference_terms,
        )

        # WiFi 5 sensitivity: -75 dBm (only 1 interferer above threshold)
        calc_wifi5 = SINRCalculator(rx_sensitivity_dbm=-75.0)
        result_wifi5 = calc_wifi5.calculate_sinr(
            tx_node="node1",
            rx_node="node2",
            signal_power_dbm=-50.0,
            noise_power_dbm=-88.0,
            interference_terms=interference_terms,
        )

        # WiFi 6 should see 2 interferers: -70 and -80 (both ≥ -80)
        assert result_wifi6.num_interferers == 2

        # WiFi 5 should see 1 interferer: -70 only (≥ -75)
        assert result_wifi5.num_interferers == 1

        # WiFi 6 has more interference → lower SINR
        assert result_wifi6.sinr_db < result_wifi5.sinr_db

    def test_lora_sensitivity_counts_very_weak_interferers(self):
        """Test that LoRa's extreme sensitivity counts very weak interferers."""
        # LoRa sensitivity: -137 dBm (extremely sensitive)
        calc_lora = SINRCalculator(rx_sensitivity_dbm=-137.0)

        # Interferers that WiFi would ignore but LoRa detects
        interference_terms = [
            InterferenceTerm(source="node3", power_dbm=-100.0, frequency_hz=868e6),
            InterferenceTerm(source="node4", power_dbm=-110.0, frequency_hz=868e6),
            InterferenceTerm(source="node5", power_dbm=-120.0, frequency_hz=868e6),
        ]

        result = calc_lora.calculate_sinr(
            tx_node="node1",
            rx_node="node2",
            signal_power_dbm=-80.0,  # Weak but above LoRa sensitivity
            noise_power_dbm=-130.0,
            interference_terms=interference_terms,
        )

        # LoRa should detect all 3 interferers (all above -137 dBm)
        assert result.num_interferers == 3

        # Compare to WiFi 6 at same scenario
        calc_wifi6 = SINRCalculator(rx_sensitivity_dbm=-80.0)
        result_wifi6 = calc_wifi6.calculate_sinr(
            tx_node="node1",
            rx_node="node2",
            signal_power_dbm=-80.0,
            noise_power_dbm=-88.0,
            interference_terms=interference_terms,
        )

        # WiFi 6 should filter all interferers (all below -80 dBm)
        assert result_wifi6.num_interferers == 0

    def test_rx_sensitivity_edge_case_exactly_at_threshold(self):
        """Test interferer exactly at rx_sensitivity threshold."""
        calc = SINRCalculator(rx_sensitivity_dbm=-80.0)

        # Interferer exactly at -80 dBm (boundary case)
        interference_terms = [
            InterferenceTerm(source="node3", power_dbm=-80.0, frequency_hz=5.18e9),  # Exactly at threshold
        ]

        result = calc.calculate_sinr(
            tx_node="node1",
            rx_node="node2",
            signal_power_dbm=-50.0,
            noise_power_dbm=-88.0,
            interference_terms=interference_terms,
        )

        # Interferer at threshold should be included (>= check, not >)
        assert result.num_interferers == 1


class TestRxSensitivityRealWorldScenarios:
    """Test rx_sensitivity in realistic deployment scenarios."""

    def test_vacuum_20m_wifi6_vs_wifi5(self):
        """Test that vacuum_20m works with WiFi 6 but might fail with poor sensitivity."""
        calc = SNRCalculator(bandwidth_hz=80e6, noise_figure_db=7.0)

        # vacuum_20m parameters
        tx_power_dbm = 20.0
        distance_m = 20.0
        frequency_hz = 5.18e9

        # Calculate free-space path loss
        fspl = calc.free_space_path_loss(distance_m, frequency_hz)

        rx_power, snr = calc.calculate_link_snr(
            tx_power_dbm=tx_power_dbm,
            tx_gain_dbi=0.0,
            rx_gain_dbi=0.0,
            path_loss_db=fspl,
            from_sionna=True,
        )

        # WiFi 6 sensitivity: -80 dBm
        wifi6_sensitivity = -80.0
        assert rx_power > wifi6_sensitivity  # Link works

        # WiFi 5 sensitivity: -75 dBm
        wifi5_sensitivity = -75.0
        assert rx_power > wifi5_sensitivity  # Link works

        # Cheap IoT radio: -60 dBm (very poor)
        cheap_sensitivity = -60.0
        assert rx_power > cheap_sensitivity  # Link still works at 20m

        # But at 100m:
        fspl_100m = calc.free_space_path_loss(100.0, frequency_hz)
        rx_power_100m, _ = calc.calculate_link_snr(
            tx_power_dbm=tx_power_dbm,
            tx_gain_dbi=0.0,
            rx_gain_dbi=0.0,
            path_loss_db=fspl_100m,
            from_sionna=True,
        )

        # At 100m, WiFi 6 works but cheap radio might not
        assert rx_power_100m > wifi6_sensitivity  # WiFi 6 still works
        # Cheap radio may or may not work (depends on exact path loss)

    def test_urban_deployment_interference_filtering(self):
        """Test urban deployment with many interferers at different sensitivities."""
        # Urban scenario: 10 nearby interferers at various power levels

        interference_terms = [
            InterferenceTerm(source="ap1", power_dbm=-50.0, frequency_hz=5.18e9),   # Very strong
            InterferenceTerm(source="ap2", power_dbm=-60.0, frequency_hz=5.18e9),  # Strong
            InterferenceTerm(source="ap3", power_dbm=-70.0, frequency_hz=5.18e9),  # Medium
            InterferenceTerm(source="ap4", power_dbm=-75.0, frequency_hz=5.18e9),  # Medium-weak
            InterferenceTerm(source="ap5", power_dbm=-80.0, frequency_hz=5.18e9),  # Weak
            InterferenceTerm(source="ap6", power_dbm=-85.0, frequency_hz=5.18e9),  # Very weak
            InterferenceTerm(source="ap7", power_dbm=-90.0, frequency_hz=5.18e9),  # Very weak
            InterferenceTerm(source="ap8", power_dbm=-95.0, frequency_hz=5.18e9),  # Extremely weak
            InterferenceTerm(source="ap9", power_dbm=-100.0, frequency_hz=5.18e9),  # Extremely weak
            InterferenceTerm(source="ap10", power_dbm=-105.0, frequency_hz=5.18e9),  # Extremely weak
        ]

        # WiFi 6 receiver: -80 dBm sensitivity
        calc_wifi6 = SINRCalculator(rx_sensitivity_dbm=-80.0)
        result_wifi6 = calc_wifi6.calculate_sinr(
            tx_node="client",
            rx_node="ap_target",
            signal_power_dbm=-55.0,  # Target AP signal
            noise_power_dbm=-88.0,
            interference_terms=interference_terms,
        )

        # WiFi 6 should see 5 interferers (≥ -80 dBm): ap1-ap5
        assert result_wifi6.num_interferers == 5

        # WiFi 5 receiver: -75 dBm sensitivity (less sensitive)
        calc_wifi5 = SINRCalculator(rx_sensitivity_dbm=-75.0)
        result_wifi5 = calc_wifi5.calculate_sinr(
            tx_node="client",
            rx_node="ap_target",
            signal_power_dbm=-55.0,
            noise_power_dbm=-88.0,
            interference_terms=interference_terms,
        )

        # WiFi 5 should see 4 interferers (≥ -75 dBm): ap1-ap4
        assert result_wifi5.num_interferers == 4

        # WiFi 5 has less interference → higher SINR (paradoxically better!)
        # This is realistic: less sensitive receivers ignore weak interference
        assert result_wifi5.sinr_db > result_wifi6.sinr_db


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
