"""
Integration tests for fallback engine netem parameter validation.

These tests verify that netem parameters (delay, loss, rate) are correctly
configured when using the fallback engine.

IMPORTANT: These tests require sudo privileges for netem configuration.
Run with:
  UV_PATH=$(which uv) sudo -E $(which uv) run pytest -s \
      tests/integration/point_to_point/fallback_engine/snr/
"""

import pytest

from tests.integration.fixtures import (
    channel_server_fallback,  # noqa: F401 — pytest fixture
    deploy_topology,
    destroy_topology,
    extract_container_prefix,
    stop_deployment_process,
    verify_tc_config,
)


class TestFallbackNetemParameters:
    """Test netem parameter validation for fallback engine."""

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.fallback
    def test_fallback_netem_parameters(self, channel_server_fallback, examples_for_tests):
        """Verify netem parameters are correctly configured with fallback engine.

        p2p_fallback_snr_vacuum: 20m free-space link, 64-QAM rate-1/2, 80 MHz.
        Expected: delay ~0.067 ms, loss ~0%, rate = 192 Mbps.
        """
        yaml_path = examples_for_tests / "p2p_fallback_snr_vacuum" / "network.yaml"

        deploy_process = None
        try:
            deploy_process = deploy_topology(
                str(yaml_path),
                channel_server_url=channel_server_fallback,
            )
            container_prefix = extract_container_prefix(str(yaml_path))

            # 20m free-space: delay = 20 / 3e8 = 0.067 ms
            # 64-QAM rate-1/2 @ 80 MHz: rate = 80 × 6 × 0.5 × 0.8 = 192 Mbps
            verify_tc_config(
                container_prefix=container_prefix,
                node="node1",
                interface="eth1",
                expected_delay_ms=0.067,
                delay_tolerance_ms=0.05,
                expected_rate_mbps=192.0,
                rate_tolerance_mbps=2.0,
            )

        finally:
            if deploy_process is not None:
                stop_deployment_process(deploy_process)
            destroy_topology(str(yaml_path))


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
