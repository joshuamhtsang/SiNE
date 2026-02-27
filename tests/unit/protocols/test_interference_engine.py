"""
Unit tests for InterferenceEngine (Phase 0).

Tests PathSolver-based interference computation against theoretical values.
"""

from unittest.mock import patch

import pytest
import numpy as np
from sine.channel.interference_calculator import (
    InterferenceEngine,
    TransmitterInfo,
    InterferenceTerm,
    InterferenceResult,
    calculate_aclr_db,
)
from sine.channel.sionna_engine import is_sionna_available, PathResult


# Skip all tests if Sionna is not available
pytestmark = pytest.mark.skipif(
    not is_sionna_available(),
    reason="Sionna not available (requires GPU dependencies)"
)


class TestInterferenceEngineBasics:
    """Test basic interference engine functionality."""

    def test_engine_initialization(self):
        """Test that engine initializes correctly."""
        engine = InterferenceEngine()
        assert engine is not None
        assert not engine._scene_loaded

    def test_load_empty_scene(self):
        """Test loading empty scene (vacuum)."""
        engine = InterferenceEngine()
        engine.load_scene(scene_path=None, frequency_hz=5.18e9, bandwidth_hz=80e6)
        assert engine._scene_loaded
        assert engine._frequency_hz == 5.18e9
        assert engine._bandwidth_hz == 80e6

    def test_cache_clearing(self):
        """Test that cache can be cleared."""
        engine = InterferenceEngine()
        engine.load_scene()

        # Add something to cache manually
        engine._path_cache[((0, 0, 0), (1, 0, 0))] = None
        assert len(engine._path_cache) > 0

        engine.clear_cache()
        assert len(engine._path_cache) == 0


class TestFreeSpaceInterference:
    """Test interference computation in free space against Friis equation."""

    def test_single_interferer_free_space(self):
        """
        Test single interferer in free space.

        Validates that computed interference power matches Friis equation within 0.5 dB.
        """
        engine = InterferenceEngine()
        engine.load_scene(scene_path=None, frequency_hz=5.18e9, bandwidth_hz=80e6)

        # Setup: RX at origin, interferer at 20m distance
        rx_position = (0.0, 0.0, 1.5)
        rx_antenna_gain_dbi = 2.15

        interferer = TransmitterInfo(
            node_name="interferer1",
            position=(20.0, 0.0, 1.5),  # 20m away, same height
            tx_power_dbm=20.0,
            antenna_gain_dbi=2.15,
            frequency_hz=5.18e9
        )

        # Compute interference
        result = engine.compute_interference_at_receiver(
            rx_position=rx_position,
            rx_antenna_gain_dbi=rx_antenna_gain_dbi,
            rx_node="rx1",
            interferers=[interferer],
            active_states={"interferer1": True}
        )

        # Verify result structure
        assert result.receiver_node == "rx1"
        assert result.num_interferers == 1
        assert len(result.interference_terms) == 1

        # Theoretical calculation using Friis equation
        # P_rx = P_tx + G_tx + G_rx - FSPL
        # FSPL = 20*log10(d) + 20*log10(f) - 147.55
        distance_m = 20.0
        frequency_hz = 5.18e9

        fspl_db = 20 * np.log10(distance_m) + 20 * np.log10(frequency_hz) - 147.55

        expected_interference_dbm = (
            interferer.tx_power_dbm
            + interferer.antenna_gain_dbi
            + rx_antenna_gain_dbi
            - fspl_db
        )

        # Compare computed vs theoretical (allow 0.5 dB tolerance)
        computed_interference_dbm = result.interference_terms[0].power_dbm
        error_db = abs(computed_interference_dbm - expected_interference_dbm)

        print(f"\nFree-space interference validation:")
        print(f"  Distance: {distance_m} m")
        print(f"  FSPL: {fspl_db:.2f} dB")
        print(f"  Expected interference: {expected_interference_dbm:.2f} dBm")
        print(f"  Computed interference: {computed_interference_dbm:.2f} dBm")
        print(f"  Error: {error_db:.2f} dB")

        assert error_db < 0.5, (
            f"Interference power error {error_db:.2f} dB exceeds 0.5 dB tolerance "
            f"(expected {expected_interference_dbm:.2f}, got {computed_interference_dbm:.2f})"
        )

    def test_two_interferers_aggregation(self):
        """
        Test interference aggregation from two interferers.

        Verifies that interference is correctly summed in linear domain.
        """
        engine = InterferenceEngine()
        engine.load_scene(scene_path=None, frequency_hz=5.18e9, bandwidth_hz=80e6)

        rx_position = (0.0, 0.0, 1.5)
        rx_antenna_gain_dbi = 2.15

        # Two interferers at different distances
        interferers = [
            TransmitterInfo(
                node_name="interferer1",
                position=(20.0, 0.0, 1.5),
                tx_power_dbm=20.0,
                antenna_gain_dbi=2.15,
                frequency_hz=5.18e9
            ),
            TransmitterInfo(
                node_name="interferer2",
                position=(0.0, 30.0, 1.5),
                tx_power_dbm=20.0,
                antenna_gain_dbi=2.15,
                frequency_hz=5.18e9
            ),
        ]

        result = engine.compute_interference_at_receiver(
            rx_position=rx_position,
            rx_antenna_gain_dbi=rx_antenna_gain_dbi,
            rx_node="rx1",
            interferers=interferers,
            active_states={"interferer1": True, "interferer2": True}
        )

        # Verify we got both interferers
        assert result.num_interferers == 2
        assert len(result.interference_terms) == 2

        # Compute theoretical aggregation
        i1_dbm = result.interference_terms[0].power_dbm
        i2_dbm = result.interference_terms[1].power_dbm

        # Convert to linear, sum, convert back
        i1_linear = 10 ** (i1_dbm / 10.0)
        i2_linear = 10 ** (i2_dbm / 10.0)
        total_linear = i1_linear + i2_linear
        expected_total_dbm = 10 * np.log10(total_linear)

        # Compare
        error_db = abs(result.total_interference_dbm - expected_total_dbm)

        print(f"\nTwo-interferer aggregation:")
        print(f"  I1: {i1_dbm:.2f} dBm")
        print(f"  I2: {i2_dbm:.2f} dBm")
        print(f"  Expected total: {expected_total_dbm:.2f} dBm")
        print(f"  Computed total: {result.total_interference_dbm:.2f} dBm")
        print(f"  Error: {error_db:.2f} dB")

        assert error_db < 0.1, (
            f"Aggregation error {error_db:.2f} dB exceeds 0.1 dB tolerance"
        )

    def test_inactive_interferer_skipped(self):
        """Test that inactive interferers are correctly skipped."""
        engine = InterferenceEngine()
        engine.load_scene(scene_path=None, frequency_hz=5.18e9, bandwidth_hz=80e6)

        rx_position = (0.0, 0.0, 1.5)
        rx_antenna_gain_dbi = 2.15

        interferers = [
            TransmitterInfo("active", (20.0, 0.0, 1.5), 20.0, 2.15, frequency_hz=5.18e9),
            TransmitterInfo("inactive", (30.0, 0.0, 1.5), 20.0, 2.15, frequency_hz=5.18e9),
        ]

        # Only activate first interferer
        result = engine.compute_interference_at_receiver(
            rx_position=rx_position,
            rx_antenna_gain_dbi=rx_antenna_gain_dbi,
            rx_node="rx1",
            interferers=interferers,
            active_states={"active": True, "inactive": False}
        )

        # Should only see one interferer
        assert result.num_interferers == 1
        assert result.interference_terms[0].source == "active"


class TestInterferenceCache:
    """Test interference path caching for performance."""

    def test_cache_usage(self):
        """Test that cache is used for repeated computations."""
        engine = InterferenceEngine()
        engine.load_scene(scene_path=None, frequency_hz=5.18e9, bandwidth_hz=80e6)

        rx_position = (0.0, 0.0, 1.5)
        interferer = TransmitterInfo("i1", (20.0, 0.0, 1.5), 20.0, 2.15, frequency_hz=5.18e9)

        # First computation - should populate cache
        result1 = engine.compute_interference_at_receiver(
            rx_position=rx_position,
            rx_antenna_gain_dbi=2.15,
            rx_node="rx1",
            interferers=[interferer]
        )

        stats1 = engine.get_cache_stats()
        assert stats1["num_cached_paths"] == 1

        # Second computation - should use cache
        result2 = engine.compute_interference_at_receiver(
            rx_position=rx_position,
            rx_antenna_gain_dbi=2.15,
            rx_node="rx1",
            interferers=[interferer]
        )

        # Results should be identical (cached)
        assert result1.total_interference_dbm == result2.total_interference_dbm

        # Cache size should still be 1
        stats2 = engine.get_cache_stats()
        assert stats2["num_cached_paths"] == 1


class TestCacheKeyIsolation:
    """
    Regression tests for _path_cache key completeness (Feb 2026).

    Bug: cache key was only (tx_pos, rx_pos), missing antenna pattern and scene path.
    Sionna RT embeds antenna pattern gains into path_loss_db, so paths computed with
    different patterns are NOT interchangeable even at identical positions.

    Scenario that revealed the bug:
    - Integration test A (asym-triangle, hw_dipole = halfwave dipole antennas) ran first,
      caching (0,0,1)→(30,0,1) with path_loss_db ≈ 71.95 dB (72 - 2×2.16 dBi gains)
    - Integration test B (csma-mcs, iso antennas) looked up same (0,0,1)→(30,0,1)
      → cache HIT → used halfwave dipole path loss for iso computation
    - Interference appeared 4.32 dB too strong → SINR 4.32 dB too low
      → MCS 1 selected instead of MCS 3, causing test assertion failure

    Fix: cache key now includes (scene_path, tx_pos, rx_pos, tx_pattern,
         rx_pattern, tx_polarization, rx_polarization).
    """

    # Positions matching the original bug scenario (asym-triangle / csma-mcs)
    _TX_POS = (0.0, 0.0, 1.0)
    _RX_POS = (30.0, 0.0, 1.0)

    def _fake_path(self, path_loss_db: float):
        return PathResult(
            path_loss_db=path_loss_db,
            min_delay_ns=100.0,
            max_delay_ns=100.0,
            delay_spread_ns=0.0,
            num_paths=1,
            dominant_path_type="los",
        )

    def _interferer(self, antenna_pattern: str) -> TransmitterInfo:
        return TransmitterInfo(
            node_name="node1",
            position=self._TX_POS,
            tx_power_dbm=20.0,
            antenna_pattern=antenna_pattern,
            polarization="V",
            frequency_hz=5.18e9,
            bandwidth_hz=80e6,
        )

    def _rx_kwargs(self, antenna_pattern: str, interferer: TransmitterInfo) -> dict:
        return {
            "rx_position": self._RX_POS,
            "rx_antenna_gain_dbi": 0.0,
            "rx_node": "node2",
            "interferers": [interferer],
            "rx_antenna_pattern": antenna_pattern,
            "rx_polarization": "V",
        }

    def test_different_antenna_patterns_produce_separate_cache_entries(self):
        """
        Regression: iso and hw_dipole (halfwave dipole) at the same positions must
        produce two separate cache entries, not share one.

        Before the fix, the iso request hit the halfwave dipole cache entry, returning
        a path_loss_db that was 4.32 dB too low (antenna gains embedded by Sionna RT),
        making interference appear 4.32 dB too strong and reducing SINR accordingly.
        """
        engine = InterferenceEngine()
        engine.load_scene(scene_path=None, frequency_hz=5.18e9, bandwidth_hz=80e6)

        # halfwave dipole result: lower path loss because Sionna embeds 2×2.16 dBi gains
        hw_dipole_result = self._fake_path(71.95)
        # iso result: pure propagation loss, no embedded antenna gains
        iso_result = self._fake_path(76.27)

        # --- First call: halfwave dipole ---
        interferer_hw = self._interferer("hw_dipole")
        with patch.object(engine, "_compute_interference_path", return_value=hw_dipole_result):
            engine.compute_interference_at_receiver(**self._rx_kwargs("hw_dipole", interferer_hw))

        assert engine.get_cache_stats()["num_cached_paths"] == 1

        # --- Second call: iso at the SAME positions ---
        interferer_iso = self._interferer("iso")
        with patch.object(
            engine, "_compute_interference_path", return_value=iso_result
        ) as mock_compute:
            engine.compute_interference_at_receiver(**self._rx_kwargs("iso", interferer_iso))
            assert mock_compute.call_count == 1, (
                "iso request incorrectly hit the halfwave dipole cache entry — "
                "antenna pattern must be part of the cache key"
            )

        assert engine.get_cache_stats()["num_cached_paths"] == 2, (
            "Different antenna patterns at the same positions must produce separate cache entries. "
            "If only 1 entry exists, the halfwave dipole result was incorrectly reused for iso."
        )

    def test_different_scene_paths_produce_separate_cache_entries(self):
        """
        Regression: same positions and antenna pattern for two different scenes must
        produce separate cache entries.

        The scene path is included in the cache key as defence-in-depth: even though
        the cache is cleared on scene reload, a bug that skips that clear would otherwise
        silently return a path computed for a different geometric environment.
        """
        engine = InterferenceEngine()
        engine.load_scene(scene_path=None, frequency_hz=5.18e9, bandwidth_hz=80e6)

        scene_a_result = self._fake_path(72.0)
        scene_b_result = self._fake_path(85.0)  # Different scene → different geometry

        interferer = self._interferer("iso")
        kwargs = self._rx_kwargs("iso", interferer)

        # --- First call: scene A ---
        engine._scene_path = "scenes/vacuum.xml"
        with patch.object(engine, "_compute_interference_path", return_value=scene_a_result):
            engine.compute_interference_at_receiver(**kwargs)

        assert engine.get_cache_stats()["num_cached_paths"] == 1

        # --- Second call: scene B, same positions and antenna pattern ---
        engine._scene_path = "scenes/two_rooms.xml"
        with patch.object(
            engine, "_compute_interference_path", return_value=scene_b_result
        ) as mock_compute:
            engine.compute_interference_at_receiver(**kwargs)
            assert mock_compute.call_count == 1, (
                "Scene B request incorrectly hit the Scene A cache entry — "
                "scene path must be part of the cache key"
            )

        assert engine.get_cache_stats()["num_cached_paths"] == 2, (
            "Different scene paths at the same positions must produce separate cache entries."
        )

    def test_identical_parameters_reuse_cache_entry(self):
        """Sanity check: identical calls must share one cache entry."""
        engine = InterferenceEngine()
        engine.load_scene(scene_path=None, frequency_hz=5.18e9, bandwidth_hz=80e6)

        interferer = self._interferer("iso")
        kwargs = self._rx_kwargs("iso", interferer)

        with patch.object(
            engine, "_compute_interference_path", return_value=self._fake_path(76.27)
        ) as mock_compute:
            engine.compute_interference_at_receiver(**kwargs)
            engine.compute_interference_at_receiver(**kwargs)  # identical second call

            assert mock_compute.call_count == 1, "Identical parameters must reuse the cache entry"

        assert engine.get_cache_stats()["num_cached_paths"] == 1


class TestEquilateralTriangle:
    """Test 3-node equilateral triangle topology (integration-level test)."""

    def test_three_node_triangle_symmetry(self):
        """
        Test 3-node equilateral triangle with symmetric interference.

        All links should have similar interference levels due to symmetry.
        """
        engine = InterferenceEngine()
        engine.load_scene(scene_path=None, frequency_hz=5.18e9, bandwidth_hz=80e6)

        # Equilateral triangle with 100m sides
        # Node1 at origin, Node2 at (100, 0), Node3 at (50, 86.6)
        positions = {
            "node1": (0.0, 0.0, 1.5),
            "node2": (100.0, 0.0, 1.5),
            "node3": (50.0, 86.6, 1.5),
        }

        antenna_gain = 2.15
        tx_power = 20.0
        frequency = 5.18e9

        # Compute interference at each node from the other two
        results = {}

        for rx_node, rx_pos in positions.items():
            # Create interferers list (all nodes except RX)
            interferers = [
                TransmitterInfo(
                    node_name=tx_node,
                    position=tx_pos,
                    tx_power_dbm=tx_power,
                    antenna_gain_dbi=antenna_gain,
                    frequency_hz=frequency
                )
                for tx_node, tx_pos in positions.items()
                if tx_node != rx_node
            ]

            result = engine.compute_interference_at_receiver(
                rx_position=rx_pos,
                rx_antenna_gain_dbi=antenna_gain,
                rx_node=rx_node,
                interferers=interferers
            )

            results[rx_node] = result

        # Verify symmetry: all nodes should see similar total interference
        # (within 1 dB due to numerical precision and geometry)
        total_interferences = [r.total_interference_dbm for r in results.values()]

        print(f"\nEquilateral triangle interference:")
        for node, result in results.items():
            print(f"  {node}: {result.total_interference_dbm:.2f} dBm from {result.num_interferers} interferers")

        max_interference = max(total_interferences)
        min_interference = min(total_interferences)
        spread_db = max_interference - min_interference

        assert spread_db < 1.0, (
            f"Interference spread {spread_db:.2f} dB exceeds 1.0 dB tolerance "
            f"(expected symmetry in equilateral triangle)"
        )

        # Verify all nodes see 2 interferers
        for result in results.values():
            assert result.num_interferers == 2


class TestACLRCalculation:
    """Test ACLR (Adjacent-Channel Leakage Ratio) calculation function."""

    def test_cochannel_zero_separation(self):
        """Test co-channel interference (0 MHz separation) returns 0 dB ACLR."""
        aclr = calculate_aclr_db(
            freq_separation_hz=0.0,
            tx_bandwidth_hz=80e6,
            rx_bandwidth_hz=80e6,
        )
        assert aclr == 0.0, "Co-channel (0 MHz separation) should have 0 dB ACLR"

    def test_cochannel_overlap_20mhz(self):
        """Test overlapping channels (20 MHz separation, 80 MHz BW) returns 0 dB ACLR."""
        # For 80 MHz BW, channels overlap if separation < 40 MHz (BW/2)
        aclr = calculate_aclr_db(
            freq_separation_hz=20e6,
            tx_bandwidth_hz=80e6,
            rx_bandwidth_hz=80e6,
        )
        assert aclr == 0.0, "Overlapping channels (20 MHz < 40 MHz threshold) should have 0 dB ACLR"

    def test_cochannel_threshold_80mhz(self):
        """Test channel overlap threshold for 80 MHz bandwidth."""
        # Threshold for non-overlap: (TX_BW + RX_BW) / 2 = (80 + 80) / 2 = 40 MHz
        # Just below threshold (overlap)
        aclr_below = calculate_aclr_db(39e6, 80e6, 80e6)
        assert aclr_below == 0.0, "39 MHz < 40 MHz threshold should overlap (0 dB)"

        # Just at threshold (non-overlap, transition band starts)
        aclr_at = calculate_aclr_db(40e6, 80e6, 80e6)
        assert aclr_at > 0.0, "40 MHz >= 40 MHz threshold should not overlap (ACLR > 0)"

    def test_transition_band_60mhz(self):
        """Test transition band (60 MHz separation, 80 MHz BW) interpolation."""
        # For 80 MHz BW: transition band is 40-80 MHz (half_bw to half_bw + 40)
        # 60 MHz = half_bw (40) + 20 MHz excess
        # Linear interpolation: 20 + (20/40) * 8 = 20 + 4 = 24 dB
        aclr = calculate_aclr_db(60e6, 80e6, 80e6)
        expected = 24.0
        assert abs(aclr - expected) < 0.1, f"Expected {expected} dB, got {aclr:.2f} dB"

    def test_first_adjacent_100mhz(self):
        """Test 1st adjacent channel (100 MHz separation, 80 MHz BW) returns 40 dB."""
        # For 80 MHz BW: 1st adjacent is 80-120 MHz (half_bw + 40 to half_bw + 80)
        aclr = calculate_aclr_db(100e6, 80e6, 80e6)
        assert aclr == 40.0, "1st adjacent (100 MHz) should have 40 dB ACLR"

    def test_orthogonal_200mhz(self):
        """Test orthogonal channels (200 MHz separation, 80 MHz BW) returns 45 dB."""
        # For 80 MHz BW: orthogonal is >120 MHz (half_bw + 80)
        aclr = calculate_aclr_db(200e6, 80e6, 80e6)
        assert aclr == 45.0, "Orthogonal (200 MHz) should have 45 dB ACLR"

    def test_bandwidth_dependent_thresholds_20mhz(self):
        """Test ACLR thresholds scale with bandwidth (20 MHz channels)."""
        # For 20 MHz BW:
        # - Overlap threshold: (20 + 20) / 2 = 10 MHz
        # - Transition band: 10-50 MHz (half_bw to half_bw + 40)
        # - 1st adjacent: 50-90 MHz
        # - Orthogonal: >90 MHz

        # Co-channel (5 MHz < 10 MHz threshold)
        aclr_co = calculate_aclr_db(5e6, 20e6, 20e6)
        assert aclr_co == 0.0, "5 MHz < 10 MHz threshold should overlap"

        # Transition band (30 MHz = half_bw (10) + 20 excess)
        aclr_trans = calculate_aclr_db(30e6, 20e6, 20e6)
        expected_trans = 20.0 + (20.0 / 40.0) * 8.0  # 24 dB
        assert abs(aclr_trans - expected_trans) < 0.1

        # 1st adjacent (70 MHz in 50-90 range)
        aclr_adj = calculate_aclr_db(70e6, 20e6, 20e6)
        assert aclr_adj == 40.0

        # Orthogonal (150 MHz > 90 MHz)
        aclr_orth = calculate_aclr_db(150e6, 20e6, 20e6)
        assert aclr_orth == 45.0

    def test_asymmetric_bandwidths(self):
        """Test ACLR with different TX and RX bandwidths."""
        # TX: 80 MHz, RX: 20 MHz
        # Overlap threshold: (80 + 20) / 2 = 50 MHz
        # Transition band uses TX half_bw: 40 MHz
        # So transition is 40-80 MHz (based on TX bandwidth)

        # 30 MHz < 50 MHz overlap threshold → co-channel
        aclr_overlap = calculate_aclr_db(30e6, tx_bandwidth_hz=80e6, rx_bandwidth_hz=20e6)
        assert aclr_overlap == 0.0, "30 MHz < 50 MHz threshold should overlap"

        # 60 MHz >= 50 MHz → non-overlapping, in transition band
        aclr_trans = calculate_aclr_db(60e6, tx_bandwidth_hz=80e6, rx_bandwidth_hz=20e6)
        assert aclr_trans > 0.0, "60 MHz >= 50 MHz should not overlap"

    def test_negative_frequency_separation(self):
        """Test that negative frequency separation is handled correctly (absolute value)."""
        aclr_positive = calculate_aclr_db(100e6, 80e6, 80e6)
        aclr_negative = calculate_aclr_db(-100e6, 80e6, 80e6)
        assert aclr_positive == aclr_negative, "ACLR should be symmetric (use abs value)"


class TestACLRIntegration:
    """Test ACLR integration with InterferenceEngine."""

    def test_adjacent_channel_rejection(self):
        """
        Test that adjacent-channel interferers are rejected by ACLR.

        Compares co-channel (0 dB ACLR) vs adjacent-channel (40 dB ACLR).
        """
        engine = InterferenceEngine()
        engine.load_scene(scene_path=None, frequency_hz=5.18e9, bandwidth_hz=80e6)

        rx_position = (0.0, 0.0, 1.5)
        rx_frequency_hz = 5.18e9
        rx_bandwidth_hz = 80e6

        # Two interferers at same distance, different frequencies
        interferers = [
            # Co-channel interferer (0 dB ACLR)
            TransmitterInfo(
                node_name="cochannel",
                position=(20.0, 0.0, 1.5),
                tx_power_dbm=20.0,
                antenna_gain_dbi=2.15,
                frequency_hz=5.18e9,  # Same frequency
                bandwidth_hz=80e6,
            ),
            # Adjacent-channel interferer (40 dB ACLR at 100 MHz separation)
            TransmitterInfo(
                node_name="adjacent",
                position=(20.0, 0.0, 1.5),  # Same position
                tx_power_dbm=20.0,
                antenna_gain_dbi=2.15,
                frequency_hz=5.28e9,  # +100 MHz
                bandwidth_hz=80e6,
            ),
        ]

        # Compute interference with ACLR
        result = engine.compute_interference_at_receiver(
            rx_position=rx_position,
            rx_antenna_gain_dbi=2.15,
            rx_node="rx1",
            interferers=interferers,
            active_states={"cochannel": True, "adjacent": True},
            rx_frequency_hz=rx_frequency_hz,
            rx_bandwidth_hz=rx_bandwidth_hz,
        )

        # Verify both interferers are present
        assert result.num_interferers == 2

        # Find each interferer's term
        cochannel_term = next(t for t in result.interference_terms if t.source == "cochannel")
        adjacent_term = next(t for t in result.interference_terms if t.source == "adjacent")

        # Verify ACLR values
        assert cochannel_term.aclr_db == 0.0, "Co-channel should have 0 dB ACLR"
        assert adjacent_term.aclr_db == 40.0, "100 MHz separation should have 40 dB ACLR"

        # Verify interference power difference (~40 dB)
        power_diff = cochannel_term.power_dbm - adjacent_term.power_dbm
        print(f"\nACLR integration test:")
        print(f"  Co-channel interference: {cochannel_term.power_dbm:.2f} dBm (ACLR: {cochannel_term.aclr_db} dB)")
        print(f"  Adjacent-channel interference: {adjacent_term.power_dbm:.2f} dBm (ACLR: {adjacent_term.aclr_db} dB)")
        print(f"  Power difference: {power_diff:.2f} dB")

        assert abs(power_diff - 40.0) < 0.5, (
            f"Power difference {power_diff:.2f} dB should be ~40 dB (ACLR rejection)"
        )

    def test_orthogonal_filtering(self):
        """
        Test that orthogonal interferers (>2× bandwidth separation) are filtered out.
        """
        engine = InterferenceEngine()
        engine.load_scene(scene_path=None, frequency_hz=5.18e9, bandwidth_hz=80e6)

        rx_position = (0.0, 0.0, 1.5)
        rx_frequency_hz = 5.18e9
        rx_bandwidth_hz = 80e6

        interferers = [
            # Co-channel (included)
            TransmitterInfo("cochannel", (20.0, 0.0, 1.5), 20.0, 2.15, frequency_hz=5.18e9, bandwidth_hz=80e6),
            # Adjacent (included, 100 MHz separation < 2 × 80 MHz = 160 MHz)
            TransmitterInfo("adjacent", (20.0, 0.0, 1.5), 20.0, 2.15, frequency_hz=5.28e9, bandwidth_hz=80e6),
            # Orthogonal (filtered out, 200 MHz separation > 160 MHz threshold)
            TransmitterInfo("orthogonal", (20.0, 0.0, 1.5), 20.0, 2.15, frequency_hz=5.38e9, bandwidth_hz=80e6),
        ]

        result = engine.compute_interference_at_receiver(
            rx_position=rx_position,
            rx_antenna_gain_dbi=2.15,
            rx_node="rx1",
            interferers=interferers,
            active_states={"cochannel": True, "adjacent": True, "orthogonal": True},
            rx_frequency_hz=rx_frequency_hz,
            rx_bandwidth_hz=rx_bandwidth_hz,
        )

        # Should only see co-channel and adjacent (orthogonal filtered out)
        assert result.num_interferers == 2, "Orthogonal interferer should be filtered out"
        sources = [term.source for term in result.interference_terms]
        assert "cochannel" in sources
        assert "adjacent" in sources
        assert "orthogonal" not in sources, "Orthogonal interferer (200 MHz away) should be filtered"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
