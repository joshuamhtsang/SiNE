"""
Unit tests for InterferenceEngine (Phase 0).

Tests PathSolver-based interference computation against theoretical values.
"""

import pytest
import numpy as np
from sine.channel.interference_engine import (
    InterferenceEngine,
    TransmitterInfo,
    InterferenceTerm,
    InterferenceResult,
)
from sine.channel.sionna_engine import is_sionna_available


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
            TransmitterInfo("active", (20.0, 0.0, 1.5), 20.0, 2.15, 5.18e9),
            TransmitterInfo("inactive", (30.0, 0.0, 1.5), 20.0, 2.15, 5.18e9),
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
        interferer = TransmitterInfo("i1", (20.0, 0.0, 1.5), 20.0, 2.15, 5.18e9)

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


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
