"""
Unit tests for FallbackEngine - FSPL-based fallback channel computation.

Tests include:
- FSPL calculation accuracy against theoretical values
- Configurable indoor loss
- Distance scaling properties
- Minimum distance clipping
- Path details computation
"""

import pytest
import numpy as np
from sine.channel.sionna_engine import FallbackEngine
from sine.channel.snr import SNRCalculator


class TestFallbackEngineInitialization:
    """Test FallbackEngine initialization and configuration."""

    def test_initialization_default_indoor_loss(self):
        """Test FallbackEngine initialization with default indoor loss."""
        engine = FallbackEngine()
        assert engine.indoor_loss_db == 10.0
        assert not engine._scene_loaded
        assert len(engine._transmitters) == 0
        assert len(engine._receivers) == 0

    def test_initialization_custom_indoor_loss(self):
        """Test FallbackEngine initialization with custom indoor loss."""
        engine = FallbackEngine(indoor_loss_db=5.0)
        assert engine.indoor_loss_db == 5.0

    def test_initialization_zero_indoor_loss(self):
        """Test FallbackEngine initialization with zero indoor loss (pure FSPL)."""
        engine = FallbackEngine(indoor_loss_db=0.0)
        assert engine.indoor_loss_db == 0.0


class TestFallbackEngineSceneLoading:
    """Test scene loading for FallbackEngine."""

    def test_load_scene_default_frequency(self):
        """Test loading scene with default frequency."""
        engine = FallbackEngine()
        engine.load_scene()
        assert engine._scene_loaded
        assert engine._frequency_hz == 5.18e9  # Default frequency

    def test_load_scene_custom_frequency(self):
        """Test loading scene with custom frequency."""
        engine = FallbackEngine()
        custom_freq = 2.4e9  # 2.4 GHz WiFi
        engine.load_scene(frequency_hz=custom_freq)
        assert engine._scene_loaded
        assert engine._frequency_hz == custom_freq

    def test_load_scene_ignores_path(self):
        """Test that scene_path is ignored in fallback mode."""
        engine = FallbackEngine()
        # Should not raise error even with invalid path
        engine.load_scene(scene_path="/nonexistent/path.xml", frequency_hz=5.18e9)
        assert engine._scene_loaded


class TestFallbackEngineDeviceManagement:
    """Test adding and updating transmitters and receivers."""

    def test_add_transmitter(self):
        """Test adding a transmitter."""
        engine = FallbackEngine()
        engine.add_transmitter("tx1", (0, 0, 1))
        assert "tx1" in engine._transmitters
        assert engine._transmitters["tx1"] == (0, 0, 1)

    def test_add_receiver(self):
        """Test adding a receiver."""
        engine = FallbackEngine()
        engine.add_receiver("rx1", (20, 0, 1))
        assert "rx1" in engine._receivers
        assert engine._receivers["rx1"] == (20, 0, 1)

    def test_update_transmitter_position(self):
        """Test updating transmitter position."""
        engine = FallbackEngine()
        engine.add_transmitter("tx1", (0, 0, 1))
        engine.update_position("tx1", (5, 5, 1))
        assert engine._transmitters["tx1"] == (5, 5, 1)

    def test_update_receiver_position(self):
        """Test updating receiver position."""
        engine = FallbackEngine()
        engine.add_receiver("rx1", (20, 0, 1))
        engine.update_position("rx1", (10, 10, 1))
        assert engine._receivers["rx1"] == (10, 10, 1)

    def test_update_unknown_device_raises_error(self):
        """Test that updating unknown device raises ValueError."""
        engine = FallbackEngine()
        with pytest.raises(ValueError, match="Unknown device"):
            engine.update_position("unknown", (0, 0, 0))


class TestFSPLCalculationAccuracy:
    """Test FSPL calculation accuracy against theoretical values."""

    def test_fspl_vacuum_20m_known_value(self):
        """Verify FSPL matches theoretical calculation at 20m with zero indoor loss."""
        # FSPL = 20*log10(d) + 20*log10(f) - 147.55
        # d=20m, f=5.18 GHz
        # Expected: 20*log10(20) + 20*log10(5.18e9) - 147.55
        #         = 26.02 + 194.28 - 147.55 = 72.75 dB
        # With 0 dB indoor loss: total = 72.75 dB

        engine = FallbackEngine(indoor_loss_db=0.0)
        engine.load_scene(frequency_hz=5.18e9)
        engine.add_transmitter("tx", (0, 0, 1))
        engine.add_receiver("rx", (20, 0, 1))

        result = engine.compute_paths()

        # Calculate expected FSPL using SNRCalculator
        expected_fspl = SNRCalculator.free_space_path_loss(20.0, 5.18e9)
        expected_total = expected_fspl  # + 0.0 indoor loss

        assert abs(result.path_loss_db - expected_total) < 0.1

    def test_fspl_1m_reference(self):
        """Test FSPL at 1 meter (reference distance)."""
        engine = FallbackEngine(indoor_loss_db=0.0)
        engine.load_scene(frequency_hz=5.18e9)
        engine.add_transmitter("tx", (0, 0, 1))
        engine.add_receiver("rx", (1, 0, 1))

        result = engine.compute_paths()

        # FSPL(1m, 5.18GHz) = 20*log10(5.18e9) - 147.55 ≈ 46.73 dB
        expected_fspl = SNRCalculator.free_space_path_loss(1.0, 5.18e9)
        assert abs(result.path_loss_db - expected_fspl) < 0.1

    def test_fspl_10m(self):
        """Test FSPL at 10m."""
        engine = FallbackEngine(indoor_loss_db=0.0)
        engine.load_scene(frequency_hz=5.18e9)
        engine.add_transmitter("tx", (0, 0, 1))
        engine.add_receiver("rx", (10, 0, 1))

        result = engine.compute_paths()

        # FSPL at 10m should be ~66 dB
        expected_fspl = SNRCalculator.free_space_path_loss(10.0, 5.18e9)
        assert abs(result.path_loss_db - expected_fspl) < 0.1
        assert 65 < result.path_loss_db < 67


class TestIndoorLossConfiguration:
    """Test configurable indoor loss behavior."""

    def test_indoor_loss_default_10db(self):
        """Test that default 10 dB indoor loss is applied."""
        engine = FallbackEngine()  # Default indoor_loss_db=10.0
        engine.load_scene(frequency_hz=5.18e9)
        engine.add_transmitter("tx", (0, 0, 1))
        engine.add_receiver("rx", (20, 0, 1))

        result = engine.compute_paths()

        # FSPL at 20m ≈ 72.75 dB, + 10 dB indoor = 82.75 dB
        expected_fspl = SNRCalculator.free_space_path_loss(20.0, 5.18e9)
        expected_total = expected_fspl + 10.0

        assert abs(result.path_loss_db - expected_total) < 0.1

    def test_indoor_loss_custom_5db(self):
        """Test custom 5 dB indoor loss."""
        engine = FallbackEngine(indoor_loss_db=5.0)
        engine.load_scene(frequency_hz=5.18e9)
        engine.add_transmitter("tx", (0, 0, 1))
        engine.add_receiver("rx", (20, 0, 1))

        result = engine.compute_paths()

        # FSPL at 20m ≈ 72.75 dB, + 5 dB indoor = 77.75 dB
        expected_fspl = SNRCalculator.free_space_path_loss(20.0, 5.18e9)
        expected_total = expected_fspl + 5.0

        assert abs(result.path_loss_db - expected_total) < 0.1

    def test_zero_indoor_loss_pure_fspl(self):
        """Test zero indoor loss gives pure FSPL."""
        engine = FallbackEngine(indoor_loss_db=0.0)
        engine.load_scene(frequency_hz=5.18e9)
        engine.add_transmitter("tx", (0, 0, 1))
        engine.add_receiver("rx", (20, 0, 1))

        result = engine.compute_paths()

        # Should match pure FSPL
        expected_fspl = SNRCalculator.free_space_path_loss(20.0, 5.18e9)
        assert abs(result.path_loss_db - expected_fspl) < 0.1


class TestDistanceScaling:
    """Test FSPL distance scaling properties."""

    def test_fspl_distance_scaling_6db_per_doubling(self):
        """Verify FSPL increases by ~6 dB when distance doubles (20*log10(2))."""
        engine = FallbackEngine(indoor_loss_db=0.0)
        engine.load_scene(frequency_hz=5.18e9)

        # Test at 10m
        engine.add_transmitter("tx", (0, 0, 1))
        engine.add_receiver("rx", (10, 0, 1))
        result_10m = engine.compute_paths()
        path_loss_10m = result_10m.path_loss_db

        # Test at 20m (reset engine)
        engine = FallbackEngine(indoor_loss_db=0.0)
        engine.load_scene(frequency_hz=5.18e9)
        engine.add_transmitter("tx", (0, 0, 1))
        engine.add_receiver("rx", (20, 0, 1))
        result_20m = engine.compute_paths()
        path_loss_20m = result_20m.path_loss_db

        # Difference should be 20*log10(2) ≈ 6.02 dB
        diff = path_loss_20m - path_loss_10m
        assert abs(diff - 6.02) < 0.1

    def test_fspl_quadrupling_distance(self):
        """Test that quadrupling distance increases FSPL by ~12 dB (2 × 6 dB)."""
        engine = FallbackEngine(indoor_loss_db=0.0)
        engine.load_scene(frequency_hz=5.18e9)

        # Test at 5m
        engine.add_transmitter("tx", (0, 0, 1))
        engine.add_receiver("rx", (5, 0, 1))
        result_5m = engine.compute_paths()
        path_loss_5m = result_5m.path_loss_db

        # Test at 20m (4× distance)
        engine = FallbackEngine(indoor_loss_db=0.0)
        engine.load_scene(frequency_hz=5.18e9)
        engine.add_transmitter("tx", (0, 0, 1))
        engine.add_receiver("rx", (20, 0, 1))
        result_20m = engine.compute_paths()
        path_loss_20m = result_20m.path_loss_db

        # Difference should be 20*log10(4) ≈ 12.04 dB
        diff = path_loss_20m - path_loss_5m
        assert abs(diff - 12.04) < 0.2


class TestMinimumDistanceClipping:
    """Test minimum distance clipping to avoid log(0)."""

    def test_minimum_distance_clipping_at_zero(self):
        """Test that zero distance is clipped to 0.1m."""
        engine = FallbackEngine(indoor_loss_db=0.0)
        engine.load_scene(frequency_hz=5.18e9)
        engine.add_transmitter("tx", (0, 0, 1))
        engine.add_receiver("rx", (0, 0, 1))  # Same position

        result = engine.compute_paths()

        # Should use 0.1m instead of 0m
        expected_fspl = SNRCalculator.free_space_path_loss(0.1, 5.18e9)
        assert abs(result.path_loss_db - expected_fspl) < 0.1

    def test_minimum_distance_clipping_at_5cm(self):
        """Test that 5cm distance is clipped to 0.1m."""
        engine = FallbackEngine(indoor_loss_db=0.0)
        engine.load_scene(frequency_hz=5.18e9)
        engine.add_transmitter("tx", (0, 0, 1))
        engine.add_receiver("rx", (0.05, 0, 1))  # 5cm

        result = engine.compute_paths()

        # Should use 0.1m instead of 0.05m
        expected_fspl = SNRCalculator.free_space_path_loss(0.1, 5.18e9)
        assert abs(result.path_loss_db - expected_fspl) < 0.1

    def test_no_clipping_above_minimum(self):
        """Test that distances above 0.1m are not clipped."""
        engine = FallbackEngine(indoor_loss_db=0.0)
        engine.load_scene(frequency_hz=5.18e9)
        engine.add_transmitter("tx", (0, 0, 1))
        engine.add_receiver("rx", (0.2, 0, 1))  # 0.2m

        result = engine.compute_paths()

        # Should use actual 0.2m
        expected_fspl = SNRCalculator.free_space_path_loss(0.2, 5.18e9)
        assert abs(result.path_loss_db - expected_fspl) < 0.1


class TestPropagationDelay:
    """Test propagation delay calculation."""

    def test_delay_at_20m(self):
        """Test propagation delay at 20m."""
        engine = FallbackEngine()
        engine.load_scene(frequency_hz=5.18e9)
        engine.add_transmitter("tx", (0, 0, 1))
        engine.add_receiver("rx", (20, 0, 1))

        result = engine.compute_paths()

        # Delay = distance / c = 20 / 3e8 * 1e9 ≈ 66.67 ns
        expected_delay_ns = (20.0 / 3e8) * 1e9
        assert abs(result.min_delay_ns - expected_delay_ns) < 1.0

    def test_delay_at_100m(self):
        """Test propagation delay at 100m."""
        engine = FallbackEngine()
        engine.load_scene(frequency_hz=5.18e9)
        engine.add_transmitter("tx", (0, 0, 1))
        engine.add_receiver("rx", (100, 0, 1))

        result = engine.compute_paths()

        # Delay = 100 / 3e8 * 1e9 ≈ 333.33 ns
        expected_delay_ns = (100.0 / 3e8) * 1e9
        assert abs(result.min_delay_ns - expected_delay_ns) < 1.0

    def test_delay_spread(self):
        """Test that delay spread is small for FSPL (single path)."""
        engine = FallbackEngine()
        engine.load_scene(frequency_hz=5.18e9)
        engine.add_transmitter("tx", (0, 0, 1))
        engine.add_receiver("rx", (20, 0, 1))

        result = engine.compute_paths()

        # Delay spread should be small (5ns typical)
        assert result.delay_spread_ns == 5.0
        # Max delay should be min + small spread
        assert result.max_delay_ns == result.min_delay_ns + 10.0


class TestPathDetails:
    """Test get_path_details() method."""

    def test_path_details_basic(self):
        """Test basic path details retrieval."""
        engine = FallbackEngine(indoor_loss_db=0.0)
        engine.load_scene(frequency_hz=5.18e9)
        engine.add_transmitter("tx", (0, 0, 1))
        engine.add_receiver("rx", (20, 0, 1))

        details = engine.get_path_details()

        assert details.tx_position == (0, 0, 1)
        assert details.rx_position == (20, 0, 1)
        assert abs(details.distance_m - 20.0) < 0.01
        assert details.num_paths == 1
        assert details.strongest_path_index == 0
        assert details.shortest_path_index == 0

    def test_path_details_single_path(self):
        """Test that path details includes single LOS path."""
        engine = FallbackEngine(indoor_loss_db=10.0)
        engine.load_scene(frequency_hz=5.18e9)
        engine.add_transmitter("tx", (0, 0, 1))
        engine.add_receiver("rx", (20, 0, 1))

        details = engine.get_path_details()

        assert len(details.paths) == 1
        path = details.paths[0]
        assert path.path_index == 0
        assert path.is_los is True
        assert len(path.interaction_types) == 0
        assert len(path.vertices) == 0

    def test_path_details_power_calculation(self):
        """Test that path power is negative FSPL + indoor loss."""
        engine = FallbackEngine(indoor_loss_db=10.0)
        engine.load_scene(frequency_hz=5.18e9)
        engine.add_transmitter("tx", (0, 0, 1))
        engine.add_receiver("rx", (20, 0, 1))

        details = engine.get_path_details()

        # Path power should be -(FSPL + indoor_loss)
        expected_fspl = SNRCalculator.free_space_path_loss(20.0, 5.18e9)
        expected_power_db = -(expected_fspl + 10.0)

        assert abs(details.paths[0].power_db - expected_power_db) < 0.1

    def test_path_details_no_devices_raises_error(self):
        """Test that get_path_details raises error when no devices configured."""
        engine = FallbackEngine()
        engine.load_scene(frequency_hz=5.18e9)

        with pytest.raises(RuntimeError, match="At least one transmitter and receiver required"):
            engine.get_path_details()


class TestComputePathsValidation:
    """Test validation for compute_paths()."""

    def test_compute_paths_no_transmitter_raises_error(self):
        """Test that compute_paths raises error when no transmitter."""
        engine = FallbackEngine()
        engine.load_scene(frequency_hz=5.18e9)
        engine.add_receiver("rx", (20, 0, 1))

        with pytest.raises(RuntimeError, match="At least one transmitter and receiver required"):
            engine.compute_paths()

    def test_compute_paths_no_receiver_raises_error(self):
        """Test that compute_paths raises error when no receiver."""
        engine = FallbackEngine()
        engine.load_scene(frequency_hz=5.18e9)
        engine.add_transmitter("tx", (0, 0, 1))

        with pytest.raises(RuntimeError, match="At least one transmitter and receiver required"):
            engine.compute_paths()

    def test_compute_paths_requires_both_devices(self):
        """Test that compute_paths requires both TX and RX."""
        engine = FallbackEngine()
        engine.load_scene(frequency_hz=5.18e9)

        with pytest.raises(RuntimeError, match="At least one transmitter and receiver required"):
            engine.compute_paths()


class Test3DDistanceCalculation:
    """Test 3D distance calculation in path computation."""

    def test_distance_3d_diagonal(self):
        """Test 3D diagonal distance calculation."""
        engine = FallbackEngine(indoor_loss_db=0.0)
        engine.load_scene(frequency_hz=5.18e9)
        engine.add_transmitter("tx", (0, 0, 0))
        engine.add_receiver("rx", (3, 4, 0))  # 3-4-5 triangle

        details = engine.get_path_details()
        assert abs(details.distance_m - 5.0) < 0.01

    def test_distance_3d_xyz(self):
        """Test full 3D distance (X, Y, Z components)."""
        engine = FallbackEngine(indoor_loss_db=0.0)
        engine.load_scene(frequency_hz=5.18e9)
        engine.add_transmitter("tx", (0, 0, 0))
        engine.add_receiver("rx", (1, 1, 1))

        details = engine.get_path_details()
        expected_distance = np.sqrt(3)  # sqrt(1^2 + 1^2 + 1^2)
        assert abs(details.distance_m - expected_distance) < 0.01


class TestPathResultMetadata:
    """Test metadata fields in PathResult."""

    def test_path_result_num_paths(self):
        """Test that PathResult always has num_paths=1."""
        engine = FallbackEngine()
        engine.load_scene(frequency_hz=5.18e9)
        engine.add_transmitter("tx", (0, 0, 1))
        engine.add_receiver("rx", (20, 0, 1))

        result = engine.compute_paths()
        assert result.num_paths == 1

    def test_path_result_dominant_path_type(self):
        """Test that dominant path type is labeled as FSPL estimate."""
        engine = FallbackEngine()
        engine.load_scene(frequency_hz=5.18e9)
        engine.add_transmitter("tx", (0, 0, 1))
        engine.add_receiver("rx", (20, 0, 1))

        result = engine.compute_paths()
        assert result.dominant_path_type == "fspl_estimate"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
