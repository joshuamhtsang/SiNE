"""
Integration tests for SINR frequency filtering with ACLR.

Tests Phase 2 of PLAN_SINR.md: Adjacent-Channel Interference with IEEE 802.11ax ACLR.

These tests verify that:
- Co-channel interferers (overlapping channels) have full interference (0 dB ACLR)
- Adjacent-channel interferers have ACLR rejection (20-40 dB)
- Orthogonal interferers (>2× bandwidth separation) are filtered out (45 dB rejection)
- Bandwidth-dependent thresholds work correctly for different channel bandwidths
"""

import pytest
from sine.channel.interference_calculator import InterferenceEngine, TransmitterInfo
from sine.channel.sionna_engine import is_sionna_available


# Skip all tests if Sionna is not available
pytestmark = pytest.mark.skipif(
    not is_sionna_available(),
    reason="Sionna not available (requires GPU dependencies)"
)


@pytest.mark.integration
class TestCochannelInterference:
    """Test co-channel (overlapping channels) interference."""

    def test_cochannel_overlap_80mhz(self):
        """
        Test co-channel interference with overlapping 80 MHz channels.

        For 80 MHz BW, channels overlap if separation < 40 MHz (BW/2).
        Verifies 0 dB ACLR for 20 MHz separation.
        """
        engine = InterferenceEngine()
        engine.load_scene(scene_path=None, frequency_hz=5.18e9, bandwidth_hz=80e6)

        rx_position = (0.0, 0.0, 1.5)
        rx_frequency_hz = 5.18e9
        rx_bandwidth_hz = 80e6

        # Interferer at +20 MHz (overlapping channels)
        interferer = TransmitterInfo(
            node_name="interferer_20mhz",
            position=(20.0, 0.0, 1.5),
            tx_power_dbm=20.0,
            antenna_gain_dbi=2.15,
            frequency_hz=5.20e9,  # +20 MHz
            bandwidth_hz=80e6,
        )

        result = engine.compute_interference_at_receiver(
            rx_position=rx_position,
            rx_antenna_gain_dbi=2.15,
            rx_node="rx1",
            interferers=[interferer],
            rx_frequency_hz=rx_frequency_hz,
            rx_bandwidth_hz=rx_bandwidth_hz,
        )

        assert result.num_interferers == 1, "Co-channel interferer should be included"
        term = result.interference_terms[0]

        # Verify 0 dB ACLR for overlapping channels
        assert term.frequency_separation_hz == 20e6, "Frequency separation should be 20 MHz"
        assert term.aclr_db == 0.0, "Overlapping channels (20 MHz < 40 MHz) should have 0 dB ACLR"

        print(f"\nCo-channel overlap test (80 MHz BW):")
        print(f"  Frequency separation: {term.frequency_separation_hz / 1e6:.1f} MHz")
        print(f"  ACLR: {term.aclr_db:.1f} dB")
        print(f"  Interference power: {term.power_dbm:.2f} dBm")


@pytest.mark.integration
class TestTransitionBandRejection:
    """Test transition band ACLR rejection (20-28 dB)."""

    def test_transition_band_60mhz_80mhz_bw(self):
        """
        Test transition band rejection at 60 MHz separation (80 MHz BW).

        For 80 MHz BW: transition band is 40-80 MHz (BW/2 to BW).
        60 MHz separation should give 24 dB ACLR (linear interpolation).
        """
        engine = InterferenceEngine()
        engine.load_scene(scene_path=None, frequency_hz=5.18e9, bandwidth_hz=80e6)

        rx_position = (0.0, 0.0, 1.5)
        rx_frequency_hz = 5.18e9
        rx_bandwidth_hz = 80e6

        # Interferer at +60 MHz (transition band)
        interferer = TransmitterInfo(
            node_name="interferer_60mhz",
            position=(20.0, 0.0, 1.5),
            tx_power_dbm=20.0,
            antenna_gain_dbi=2.15,
            frequency_hz=5.24e9,  # +60 MHz
            bandwidth_hz=80e6,
        )

        result = engine.compute_interference_at_receiver(
            rx_position=rx_position,
            rx_antenna_gain_dbi=2.15,
            rx_node="rx1",
            interferers=[interferer],
            rx_frequency_hz=rx_frequency_hz,
            rx_bandwidth_hz=rx_bandwidth_hz,
        )

        assert result.num_interferers == 1
        term = result.interference_terms[0]

        # Verify 24 dB ACLR (transition band interpolation)
        assert term.frequency_separation_hz == 60e6
        expected_aclr = 24.0  # 20 + (20/40) * 8
        assert abs(term.aclr_db - expected_aclr) < 0.1, (
            f"Expected {expected_aclr} dB ACLR at 60 MHz separation, got {term.aclr_db:.2f} dB"
        )

        print(f"\nTransition band test (60 MHz separation, 80 MHz BW):")
        print(f"  Frequency separation: {term.frequency_separation_hz / 1e6:.1f} MHz")
        print(f"  ACLR: {term.aclr_db:.1f} dB (expected {expected_aclr:.1f} dB)")
        print(f"  Interference power: {term.power_dbm:.2f} dBm")


@pytest.mark.integration
class TestFirstAdjacentRejection:
    """Test 1st adjacent channel ACLR rejection (40 dB)."""

    def test_first_adjacent_100mhz_80mhz_bw(self):
        """
        Test 1st adjacent channel rejection at 100 MHz separation (80 MHz BW).

        For 80 MHz BW: 1st adjacent is 80-120 MHz (BW to 1.5×BW).
        100 MHz separation should give 40 dB ACLR.
        """
        engine = InterferenceEngine()
        engine.load_scene(scene_path=None, frequency_hz=5.18e9, bandwidth_hz=80e6)

        rx_position = (0.0, 0.0, 1.5)
        rx_frequency_hz = 5.18e9
        rx_bandwidth_hz = 80e6

        # Interferer at +100 MHz (1st adjacent)
        interferer = TransmitterInfo(
            node_name="interferer_100mhz",
            position=(20.0, 0.0, 1.5),
            tx_power_dbm=20.0,
            antenna_gain_dbi=2.15,
            frequency_hz=5.28e9,  # +100 MHz
            bandwidth_hz=80e6,
        )

        result = engine.compute_interference_at_receiver(
            rx_position=rx_position,
            rx_antenna_gain_dbi=2.15,
            rx_node="rx1",
            interferers=[interferer],
            rx_frequency_hz=rx_frequency_hz,
            rx_bandwidth_hz=rx_bandwidth_hz,
        )

        assert result.num_interferers == 1
        term = result.interference_terms[0]

        # Verify 40 dB ACLR
        assert term.frequency_separation_hz == 100e6
        assert term.aclr_db == 40.0, (
            f"Expected 40 dB ACLR at 100 MHz separation, got {term.aclr_db:.2f} dB"
        )

        print(f"\n1st adjacent test (100 MHz separation, 80 MHz BW):")
        print(f"  Frequency separation: {term.frequency_separation_hz / 1e6:.1f} MHz")
        print(f"  ACLR: {term.aclr_db:.1f} dB")
        print(f"  Interference power: {term.power_dbm:.2f} dBm")


@pytest.mark.integration
class TestOrthogonalFiltering:
    """Test orthogonal interferer filtering (>2× bandwidth)."""

    def test_orthogonal_200mhz_filtered_80mhz_bw(self):
        """
        Test orthogonal interferers are filtered out (200 MHz separation, 80 MHz BW).

        For 80 MHz BW: orthogonal threshold is 2 × 80 = 160 MHz.
        200 MHz separation exceeds threshold, so interferer should be filtered out.
        """
        engine = InterferenceEngine()
        engine.load_scene(scene_path=None, frequency_hz=5.18e9, bandwidth_hz=80e6)

        rx_position = (0.0, 0.0, 1.5)
        rx_frequency_hz = 5.18e9
        rx_bandwidth_hz = 80e6

        # Interferer at +200 MHz (orthogonal, should be filtered)
        interferer = TransmitterInfo(
            node_name="interferer_200mhz",
            position=(20.0, 0.0, 1.5),
            tx_power_dbm=20.0,
            antenna_gain_dbi=2.15,
            frequency_hz=5.38e9,  # +200 MHz
            bandwidth_hz=80e6,
        )

        result = engine.compute_interference_at_receiver(
            rx_position=rx_position,
            rx_antenna_gain_dbi=2.15,
            rx_node="rx1",
            interferers=[interferer],
            rx_frequency_hz=rx_frequency_hz,
            rx_bandwidth_hz=rx_bandwidth_hz,
        )

        # Orthogonal interferer should be filtered out
        assert result.num_interferers == 0, (
            f"Orthogonal interferer (200 MHz > 160 MHz threshold) should be filtered out"
        )

        print(f"\nOrthogonal filtering test (200 MHz separation, 80 MHz BW):")
        print(f"  Expected: 0 interferers (filtered out)")
        print(f"  Actual: {result.num_interferers} interferers")


@pytest.mark.integration
class TestBandwidthDependentThresholds:
    """Test bandwidth-dependent ACLR thresholds for different channel bandwidths."""

    def test_20mhz_channel_thresholds(self):
        """
        Test ACLR thresholds scale correctly for 20 MHz channels.

        For 20 MHz BW:
        - Overlap threshold: (20 + 20) / 2 = 10 MHz
        - Transition band: 10-50 MHz (BW/2 to BW/2 + 40)
        - 1st adjacent: 50-90 MHz (BW/2 + 40 to BW/2 + 80)
        - Orthogonal: > 2 × 20 = 40 MHz
        """
        engine = InterferenceEngine()
        engine.load_scene(scene_path=None, frequency_hz=5.18e9, bandwidth_hz=20e6)

        rx_position = (0.0, 0.0, 1.5)
        rx_frequency_hz = 5.18e9
        rx_bandwidth_hz = 20e6

        # Test cases: (freq_offset_mhz, expected_behavior)
        test_cases = [
            (5, "cochannel", 0.0),      # 5 MHz < 10 MHz threshold → overlap (0 dB)
            (30, "transition", 24.0),   # 30 MHz in 10-50 range → transition (24 dB)
            (70, "adjacent", 40.0),     # 70 MHz in 50-90 range → 1st adjacent (40 dB)
            (100, "orthogonal", None),  # 100 MHz > 40 MHz threshold → filtered out
        ]

        for freq_offset_mhz, behavior, expected_aclr in test_cases:
            interferer = TransmitterInfo(
                node_name=f"interferer_{freq_offset_mhz}mhz",
                position=(20.0, 0.0, 1.5),
                tx_power_dbm=20.0,
                antenna_gain_dbi=2.15,
                frequency_hz=5.18e9 + freq_offset_mhz * 1e6,
                bandwidth_hz=20e6,
            )

            result = engine.compute_interference_at_receiver(
                rx_position=rx_position,
                rx_antenna_gain_dbi=2.15,
                rx_node="rx1",
                interferers=[interferer],
                rx_frequency_hz=rx_frequency_hz,
                rx_bandwidth_hz=rx_bandwidth_hz,
            )

            if behavior == "orthogonal":
                assert result.num_interferers == 0, (
                    f"{freq_offset_mhz} MHz should be filtered (orthogonal)"
                )
                print(f"  {freq_offset_mhz} MHz: filtered (orthogonal)")
            else:
                assert result.num_interferers == 1, (
                    f"{freq_offset_mhz} MHz should be included ({behavior})"
                )
                term = result.interference_terms[0]
                assert abs(term.aclr_db - expected_aclr) < 0.1, (
                    f"{freq_offset_mhz} MHz: expected {expected_aclr} dB, got {term.aclr_db:.2f} dB"
                )
                print(f"  {freq_offset_mhz} MHz: ACLR = {term.aclr_db:.1f} dB ({behavior})")

    def test_40mhz_channel_thresholds(self):
        """
        Test ACLR thresholds scale correctly for 40 MHz channels.

        For 40 MHz BW:
        - Overlap threshold: (40 + 40) / 2 = 20 MHz
        - Orthogonal: > 2 × 40 = 80 MHz
        """
        engine = InterferenceEngine()
        engine.load_scene(scene_path=None, frequency_hz=5.18e9, bandwidth_hz=40e6)

        rx_position = (0.0, 0.0, 1.5)
        rx_frequency_hz = 5.18e9
        rx_bandwidth_hz = 40e6

        # Test cases
        test_cases = [
            (10, "cochannel", 0.0),     # 10 MHz < 20 MHz threshold → overlap
            (50, "transition", None),   # 50 MHz in transition band
            (120, "orthogonal", None),  # 120 MHz > 80 MHz threshold → filtered
        ]

        for freq_offset_mhz, behavior, expected_aclr in test_cases:
            interferer = TransmitterInfo(
                node_name=f"interferer_{freq_offset_mhz}mhz",
                position=(20.0, 0.0, 1.5),
                tx_power_dbm=20.0,
                antenna_gain_dbi=2.15,
                frequency_hz=5.18e9 + freq_offset_mhz * 1e6,
                bandwidth_hz=40e6,
            )

            result = engine.compute_interference_at_receiver(
                rx_position=rx_position,
                rx_antenna_gain_dbi=2.15,
                rx_node="rx1",
                interferers=[interferer],
                rx_frequency_hz=rx_frequency_hz,
                rx_bandwidth_hz=rx_bandwidth_hz,
            )

            if behavior == "orthogonal":
                assert result.num_interferers == 0
                print(f"  {freq_offset_mhz} MHz (40 MHz BW): filtered (orthogonal)")
            else:
                assert result.num_interferers == 1
                term = result.interference_terms[0]
                if expected_aclr is not None:
                    assert abs(term.aclr_db - expected_aclr) < 0.1
                print(f"  {freq_offset_mhz} MHz (40 MHz BW): ACLR = {term.aclr_db:.1f} dB ({behavior})")


@pytest.mark.integration
class TestMixedFrequencyTopology:
    """Test realistic mixed-frequency topology with multiple interferers."""

    def test_three_frequency_groups(self):
        """
        Test topology with 3 frequency groups.

        - Group 1: 5.18 GHz (co-channel with RX)
        - Group 2: 5.28 GHz (+100 MHz, 1st adjacent, 40 dB ACLR)
        - Group 3: 5.50 GHz (+320 MHz, orthogonal, filtered out)
        """
        engine = InterferenceEngine()
        engine.load_scene(scene_path=None, frequency_hz=5.18e9, bandwidth_hz=80e6)

        rx_position = (0.0, 0.0, 1.5)
        rx_frequency_hz = 5.18e9
        rx_bandwidth_hz = 80e6

        interferers = [
            # Group 1: Co-channel (0 dB ACLR)
            TransmitterInfo("cochannel_1", (20.0, 0.0, 1.5), 20.0, 2.15, frequency_hz=5.18e9, bandwidth_hz=80e6),
            TransmitterInfo("cochannel_2", (0.0, 20.0, 1.5), 20.0, 2.15, frequency_hz=5.18e9, bandwidth_hz=80e6),

            # Group 2: 1st adjacent (40 dB ACLR)
            TransmitterInfo("adjacent_1", (20.0, 20.0, 1.5), 20.0, 2.15, frequency_hz=5.28e9, bandwidth_hz=80e6),
            TransmitterInfo("adjacent_2", (-20.0, 0.0, 1.5), 20.0, 2.15, frequency_hz=5.28e9, bandwidth_hz=80e6),

            # Group 3: Orthogonal (filtered out)
            TransmitterInfo("orthogonal_1", (30.0, 0.0, 1.5), 20.0, 2.15, frequency_hz=5.50e9, bandwidth_hz=80e6),
            TransmitterInfo("orthogonal_2", (0.0, 30.0, 1.5), 20.0, 2.15, frequency_hz=5.50e9, bandwidth_hz=80e6),
        ]

        result = engine.compute_interference_at_receiver(
            rx_position=rx_position,
            rx_antenna_gain_dbi=2.15,
            rx_node="rx1",
            interferers=interferers,
            rx_frequency_hz=rx_frequency_hz,
            rx_bandwidth_hz=rx_bandwidth_hz,
        )

        # Should only see co-channel and adjacent (4 total, not 6)
        assert result.num_interferers == 4, (
            f"Expected 4 interferers (2 co-channel + 2 adjacent), got {result.num_interferers}"
        )

        # Verify frequency groups
        sources = [term.source for term in result.interference_terms]

        # Co-channel interferers should be present
        assert "cochannel_1" in sources
        assert "cochannel_2" in sources

        # Adjacent-channel interferers should be present
        assert "adjacent_1" in sources
        assert "adjacent_2" in sources

        # Orthogonal interferers should be filtered out
        assert "orthogonal_1" not in sources
        assert "orthogonal_2" not in sources

        # Verify ACLR values
        for term in result.interference_terms:
            if "cochannel" in term.source:
                assert term.aclr_db == 0.0, f"{term.source} should have 0 dB ACLR"
            elif "adjacent" in term.source:
                assert term.aclr_db == 40.0, f"{term.source} should have 40 dB ACLR"

        print(f"\nMixed-frequency topology test:")
        print(f"  Total interferers: {result.num_interferers} (expected 4)")
        for term in sorted(result.interference_terms, key=lambda t: t.source):
            print(f"    {term.source}: {term.frequency_hz / 1e9:.3f} GHz, "
                  f"sep={term.frequency_separation_hz / 1e6:.0f} MHz, "
                  f"ACLR={term.aclr_db:.0f} dB, "
                  f"power={term.power_dbm:.1f} dBm")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "-m", "integration"])
