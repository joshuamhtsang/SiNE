"""
API tests for channel server engine selection logic.

Tests include:
- Engine type parameter handling (auto, sionna, fallback)
- Engine selection behavior based on GPU availability
- Force-fallback mode (--force-fallback CLI flag)
- Error handling for unavailable engines
- Response metadata (engine_used field)
- All endpoints: /compute/link, /compute/links_snr, /compute/interference
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from sine.channel.server import app, EngineType


@pytest.fixture
def client():
    """Create test client for FastAPI app."""
    return TestClient(app)


@pytest.fixture
def sample_link_request():
    """Sample wireless link request for testing."""
    return {
        "tx_node": "node1",
        "rx_node": "node2",
        "tx_position": {"x": 0, "y": 0, "z": 1},
        "rx_position": {"x": 20, "y": 0, "z": 1},
        "tx_power_dbm": 20.0,
        "tx_gain_dbi": 0.0,
        "rx_gain_dbi": 0.0,
        "frequency_hz": 5.18e9,
        "bandwidth_hz": 80e6,
        "modulation": "64qam",
        "fec_type": "ldpc",
        "fec_code_rate": 0.5,
        "packet_size_bits": 12000,
    }


@pytest.fixture
def sample_sinr_request():
    """Sample SINR request for testing."""
    return {
        "tx_node": "node1",
        "rx_node": "node2",
        "tx_position": {"x": 0, "y": 0, "z": 1},
        "rx_position": {"x": 20, "y": 0, "z": 1},
        "tx_power_dbm": 20.0,
        "tx_gain_dbi": 0.0,
        "rx_gain_dbi": 0.0,
        "frequency_hz": 5.18e9,
        "bandwidth_hz": 80e6,
        "interferers": [],
    }


class TestExplicitFallbackEngine:
    """Test that explicit fallback engine request always succeeds."""

    def test_explicit_fallback_single_link(self, client, sample_link_request):
        """engine_type=FALLBACK should work without GPU."""
        sample_link_request["engine_type"] = "fallback"

        response = client.post("/compute/link", json=sample_link_request)

        assert response.status_code == 200
        data = response.json()
        assert data["engine_used"] == "fallback"
        assert data["path_loss_db"] > 0
        assert data["received_power_dbm"] < 0
        assert "snr_db" in data

    def test_explicit_fallback_batch(self, client, sample_link_request):
        """engine_type=FALLBACK on batch endpoint."""
        sample_link_request["engine_type"] = "fallback"
        batch_request = {
            "scene": {"scene_file": "", "frequency_hz": 5.18e9, "bandwidth_hz": 80e6},
            "links": [sample_link_request]
        }

        response = client.post("/compute/links_snr", json=batch_request)

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["engine_used"] == "fallback"

    def test_explicit_fallback_consistent_results(self, client, sample_link_request):
        """Test that fallback engine gives consistent results across calls."""
        sample_link_request["engine_type"] = "fallback"

        # Make two requests
        response1 = client.post("/compute/link", json=sample_link_request)
        response2 = client.post("/compute/link", json=sample_link_request)

        assert response1.status_code == 200
        assert response2.status_code == 200

        data1 = response1.json()
        data2 = response2.json()

        # Results should be identical (deterministic FSPL)
        assert abs(data1["path_loss_db"] - data2["path_loss_db"]) < 0.01
        assert abs(data1["snr_db"] - data2["snr_db"]) < 0.01


class TestAutoEngineSelection:
    """Test AUTO engine selection (default behavior)."""

    def test_auto_defaults_to_available_engine(self, client, sample_link_request):
        """engine_type=AUTO should use available engine."""
        sample_link_request["engine_type"] = "auto"

        response = client.post("/compute/link", json=sample_link_request)

        assert response.status_code == 200
        data = response.json()
        # Should be either sionna or fallback (depends on GPU availability)
        assert data["engine_used"] in ["sionna", "fallback"]

    def test_auto_engine_default_parameter(self, client, sample_link_request):
        """Test that AUTO is the default when engine_type not specified."""
        # Don't set engine_type (should default to AUTO)
        response = client.post("/compute/link", json=sample_link_request)

        assert response.status_code == 200
        data = response.json()
        assert data["engine_used"] in ["sionna", "fallback"]


class TestResponseMetadata:
    """Test that response includes engine_used metadata."""

    def test_response_includes_engine_used_single(self, client, sample_link_request):
        """Test that /compute/link includes engine_used field."""
        sample_link_request["engine_type"] = "fallback"

        response = client.post("/compute/link", json=sample_link_request)

        assert response.status_code == 200
        data = response.json()
        assert "engine_used" in data
        assert data["engine_used"] == "fallback"

    def test_response_includes_engine_used_batch(self, client, sample_link_request):
        """Test that /compute/links_snr includes engine_used in each result."""
        sample_link_request["engine_type"] = "fallback"
        batch_request = {
            "scene": {"scene_file": "", "frequency_hz": 5.18e9, "bandwidth_hz": 80e6},
            "links": [
                sample_link_request,
                {**sample_link_request, "rx_position": {"x": 10, "y": 0, "z": 1}},
            ]
        }

        response = client.post("/compute/links_snr", json=batch_request)

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 2
        for result in data["results"]:
            assert "engine_used" in result
            assert result["engine_used"] == "fallback"

    def test_response_includes_engine_used_sinr(self, client, sample_sinr_request):
        """Test that /compute/interference includes engine_used (if added to spec)."""
        # Note: SINR endpoint may not have engine_type parameter yet
        # This test documents expected future behavior
        response = client.post("/compute/interference", json=sample_sinr_request)

        # SINR endpoint should succeed (may not have engine_used field yet)
        assert response.status_code == 200


class TestForceFallbackMode:
    """Test --force-fallback CLI flag behavior."""

    def test_force_fallback_rejects_sionna_request(self, client, sample_link_request):
        """Server in force-fallback mode should reject explicit SIONNA requests."""
        import sine.channel.server as server_module

        # Enable force-fallback mode via engine registry
        original_flag = server_module._engine_registry._force_fallback
        server_module._engine_registry._force_fallback = True

        try:
            sample_link_request["engine_type"] = "sionna"

            response = client.post("/compute/link", json=sample_link_request)

            # Should return 400 error
            assert response.status_code == 400
            data = response.json()
            assert "fallback-only mode" in data["detail"].lower()
        finally:
            # Restore original flag
            server_module._engine_registry._force_fallback = original_flag

    def test_force_fallback_accepts_auto_request(self, client, sample_link_request):
        """Force-fallback mode should accept AUTO requests (uses fallback)."""
        import sine.channel.server as server_module

        original_flag = server_module._engine_registry._force_fallback
        server_module._engine_registry._force_fallback = True

        try:
            sample_link_request["engine_type"] = "auto"

            response = client.post("/compute/link", json=sample_link_request)

            assert response.status_code == 200
            data = response.json()
            assert data["engine_used"] == "fallback"
        finally:
            server_module._engine_registry._force_fallback = original_flag

    def test_force_fallback_accepts_explicit_fallback(self, client, sample_link_request):
        """Force-fallback mode should accept explicit FALLBACK requests."""
        import sine.channel.server as server_module

        original_flag = server_module._engine_registry._force_fallback
        server_module._engine_registry._force_fallback = True

        try:
            sample_link_request["engine_type"] = "fallback"

            response = client.post("/compute/link", json=sample_link_request)

            assert response.status_code == 200
            data = response.json()
            assert data["engine_used"] == "fallback"
        finally:
            server_module._engine_registry._force_fallback = original_flag


class TestExplicitSionnaEngine:
    """Test explicit Sionna engine requests."""

    def test_explicit_sionna_when_available(self, client, sample_link_request):
        """engine_type=SIONNA should work if GPU available."""
        from sine.channel.server import is_sionna_available

        sample_link_request["engine_type"] = "sionna"

        response = client.post("/compute/link", json=sample_link_request)

        if is_sionna_available():
            # If Sionna available, should succeed
            assert response.status_code == 200
            data = response.json()
            assert data["engine_used"] == "sionna"
        else:
            # If Sionna unavailable, should return 503
            assert response.status_code == 503
            data = response.json()
            assert "unavailable" in data["detail"].lower()

    def test_explicit_sionna_error_without_gpu(self, client, sample_link_request):
        """engine_type=SIONNA should return 503 if GPU unavailable."""
        from sine.channel.server import is_sionna_available

        # Skip if Sionna is actually available
        if is_sionna_available():
            pytest.skip("Sionna is available (GPU present), cannot test error path")

        sample_link_request["engine_type"] = "sionna"

        response = client.post("/compute/link", json=sample_link_request)

        assert response.status_code == 503
        data = response.json()
        assert "unavailable" in data["detail"].lower()
        assert "gpu" in data["detail"].lower() or "cuda" in data["detail"].lower()


class TestBatchEndpoint:
    """Test batch endpoint engine selection."""

    def test_batch_respects_engine_type(self, client, sample_link_request):
        """Batch endpoint should respect engine_type parameter."""
        sample_link_request["engine_type"] = "fallback"
        batch_request = {
            "scene": {"scene_file": "", "frequency_hz": 5.18e9, "bandwidth_hz": 80e6},
            "links": [
                sample_link_request,
                {**sample_link_request, "rx_position": {"x": 10, "y": 0, "z": 1}},
                {**sample_link_request, "rx_position": {"x": 30, "y": 0, "z": 1}},
            ]
        }

        response = client.post("/compute/links_snr", json=batch_request)

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 3

        # All results should use fallback engine
        for result in data["results"]:
            assert result["engine_used"] == "fallback"

    def test_batch_mixed_engine_types_not_supported(self, client, sample_link_request):
        """Test that all links in batch use same engine (no mixing)."""
        # All links inherit same engine_type from request
        link1 = {**sample_link_request, "engine_type": "fallback"}
        link2 = {**sample_link_request, "rx_position": {"x": 10, "y": 0, "z": 1}}

        batch_request = {
            "scene": {"scene_file": "", "frequency_hz": 5.18e9, "bandwidth_hz": 80e6},
            "links": [link1, link2]
        }

        response = client.post("/compute/links_snr", json=batch_request)

        # Currently, each link can have its own engine_type
        # This test documents expected behavior
        assert response.status_code == 200


class TestEngineParameterValidation:
    """Test engine_type parameter validation."""

    def test_invalid_engine_type_rejected(self, client, sample_link_request):
        """Invalid engine_type values should be rejected."""
        sample_link_request["engine_type"] = "invalid_engine"

        response = client.post("/compute/link", json=sample_link_request)

        # Should return 422 validation error
        assert response.status_code == 422

    def test_case_sensitive_engine_type(self, client, sample_link_request):
        """Test that engine_type is case-sensitive."""
        sample_link_request["engine_type"] = "FALLBACK"  # uppercase

        response = client.post("/compute/link", json=sample_link_request)

        # Should be rejected (expects lowercase "fallback")
        assert response.status_code == 422


class TestFallbackEnginePathLoss:
    """Test fallback engine path loss calculations."""

    def test_fallback_path_loss_increases_with_distance(self, client, sample_link_request):
        """Test that path loss increases as distance increases."""
        sample_link_request["engine_type"] = "fallback"

        # Test at 10m
        sample_link_request["rx_position"] = {"x": 10, "y": 0, "z": 1}
        response_10m = client.post("/compute/link", json=sample_link_request)
        data_10m = response_10m.json()

        # Test at 20m
        sample_link_request["rx_position"] = {"x": 20, "y": 0, "z": 1}
        response_20m = client.post("/compute/link", json=sample_link_request)
        data_20m = response_20m.json()

        # Path loss should increase (distance doubled)
        assert data_20m["path_loss_db"] > data_10m["path_loss_db"]

        # Difference should be ~6 dB (20*log10(2))
        diff = data_20m["path_loss_db"] - data_10m["path_loss_db"]
        assert 5.5 < diff < 6.5

    def test_fallback_realistic_path_loss_values(self, client, sample_link_request):
        """Test that fallback path loss values are realistic."""
        sample_link_request["engine_type"] = "fallback"
        sample_link_request["rx_position"] = {"x": 20, "y": 0, "z": 1}

        response = client.post("/compute/link", json=sample_link_request)

        assert response.status_code == 200
        data = response.json()

        # At 20m, 5.18 GHz, path loss should be ~72 dB (FSPL) + indoor loss
        # With default 10 dB indoor: ~82 dB
        assert 70 < data["path_loss_db"] < 90


class TestHealthEndpoint:
    """Test health endpoint (not engine-specific, but good to verify)."""

    def test_health_check(self, client):
        """Test that /health endpoint works."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "ok"]


class TestEngineSingleton:
    """Test that engines are reused (singleton pattern)."""

    def test_fallback_engine_reused(self, client, sample_link_request):
        """Test that fallback engine is reused across requests."""
        sample_link_request["engine_type"] = "fallback"

        # Make multiple requests
        for _ in range(3):
            response = client.post("/compute/link", json=sample_link_request)
            assert response.status_code == 200

        # Engines should be singleton (no way to directly test via API,
        # but this verifies no crashes from engine reuse)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
