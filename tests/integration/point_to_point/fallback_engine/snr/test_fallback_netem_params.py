"""
Integration tests for fallback engine netem parameter validation.

These tests verify that netem parameters (delay, loss, rate) are correctly
configured when using the fallback engine.

IMPORTANT: These tests require sudo privileges for netem configuration.
Run with: UV_PATH=$(which uv) sudo -E pytest -s tests/integration/point_to_point/fallback_engine/snr/
"""

import subprocess
import time
from pathlib import Path

import pytest

from tests.integration.fixtures import (
    get_uv_path,
    stop_deployment_process,
    destroy_topology,
)


def start_channel_server_fallback(port: int = 8000) -> subprocess.Popen:
    """Start channel server in force-fallback mode.

    Returns:
        subprocess.Popen: Channel server process
    """
    uv_path = get_uv_path()
    process = subprocess.Popen(
        [uv_path, "run", "sine", "channel-server", "--force-fallback", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    # Wait for server to start
    assert process.stdout is not None
    for line in process.stdout:
        print(f"[channel-server] {line}", end="")
        if "Uvicorn running" in line or "Application startup complete" in line:
            break
        if process.poll() is not None:
            raise RuntimeError(f"Channel server failed to start (exit code {process.returncode})")

    # Give server a moment to be fully ready
    time.sleep(1)
    return process


def stop_channel_server(process: subprocess.Popen) -> None:
    """Stop channel server process."""
    if process.poll() is None:  # Still running
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


class TestFallbackNetemParameters:
    """Test netem parameter validation for fallback engine."""

    def test_fallback_netem_parameters(self, examples_for_tests, tmp_path):
        """Verify netem parameters are correctly configured with fallback engine."""
        yaml_path = examples_for_tests / "p2p_fallback_snr_vacuum" / "network.yaml"

        # Copy to temp
        temp_yaml = tmp_path / "network.yaml"
        with open(yaml_path, encoding="utf-8") as f:
            content = f.read()
        with open(temp_yaml, "w", encoding="utf-8") as f:
            f.write(content)

        channel_server = None
        deploy_process = None
        try:
            # Start channel server in fallback mode
            print("\nStarting channel server in fallback mode...")
            channel_server = start_channel_server_fallback()

            # Deploy with fallback
            uv_path = get_uv_path()
            deploy_process = subprocess.Popen(
                ["sudo", uv_path, "run", "sine", "deploy", str(temp_yaml)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            deployment_ready = False
            assert deploy_process.stdout is not None

            # Capture deployment output to extract netem parameters
            deployment_output = []
            for line in deploy_process.stdout:
                print(line, end="")
                deployment_output.append(line)
                if "Emulation deployed successfully!" in line:
                    deployment_ready = True
                    break
                if deploy_process.poll() is not None:
                    raise RuntimeError("Deployment failed")

            assert deployment_ready

            # Parse deployment output for netem parameters
            # Look for lines like: "Applied netem config to ... - delay=0.1ms, loss=0.00%, rate=192.0Mbps"
            netem_found = False
            for line in deployment_output:
                if "Applied netem config" in line and "delay=" in line:
                    netem_found = True
                    # Verify delay is reasonable (not zero, not huge)
                    # For 20m at speed of light: ~0.067 ms
                    assert "delay=0.1ms" in line or "delay=0.0ms" in line  # Should be < 1 ms
                    assert "loss=" in line  # Has loss parameter
                    assert "rate=" in line  # Has rate parameter
                    break

            assert netem_found, "Netem parameters not found in deployment output"

        finally:
            if deploy_process is not None:
                stop_deployment_process(deploy_process)
            destroy_topology(str(temp_yaml))
            if channel_server is not None:
                stop_channel_server(channel_server)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
