"""
Integration tests for fallback engine deployment.

These tests verify that:
1. Fallback engine can deploy topologies without GPU/Sionna
2. Deployment works without scene files (using force-fallback mode)
3. AUTO mode falls back when GPU unavailable

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


class TestFallbackDeployment:
    """Test deployment using fallback engine."""

    def test_deploy_vacuum_with_fallback(self, examples_for_tests, tmp_path):
        """Deploy vacuum topology using fallback engine explicitly."""
        yaml_path = examples_for_tests / "p2p_fallback_snr_vacuum" / "network.yaml"

        # Read original
        with open(yaml_path, encoding="utf-8") as f:
            content = f.read()

        # Write to temp file
        temp_yaml = tmp_path / "network.yaml"
        with open(temp_yaml, "w", encoding="utf-8") as f:
            f.write(content)

        channel_server = None
        deploy_process = None
        try:
            # Start channel server in fallback mode
            print("\nStarting channel server in fallback mode...")
            channel_server = start_channel_server_fallback()

            # Deploy topology (connects to running channel server)
            uv_path = get_uv_path()
            print(f"\nDeploying with fallback engine: {temp_yaml}")

            deploy_process = subprocess.Popen(
                ["sudo", uv_path, "run", "sine", "deploy", str(temp_yaml)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            # Wait for deployment
            deployment_ready = False
            assert deploy_process.stdout is not None

            for line in deploy_process.stdout:
                print(line, end="")
                if "Emulation deployed successfully!" in line:
                    deployment_ready = True
                    break
                if deploy_process.poll() is not None:
                    raise RuntimeError(f"Deployment failed (exit code {deploy_process.returncode})")

            assert deployment_ready, "Deployment did not complete"

            # Give netem a moment to stabilize
            time.sleep(2)

            # Verify containers are running
            result = subprocess.run(
                ["sudo", "docker", "ps", "--filter", "name=clab-", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                check=True,
            )
            container_names = result.stdout.strip().split("\n")
            assert len(container_names) >= 2, "Expected at least 2 containers"

            print(f"\nDeployed containers: {container_names}")

        finally:
            # Cleanup
            if deploy_process is not None:
                stop_deployment_process(deploy_process)
            destroy_topology(str(temp_yaml))
            if channel_server is not None:
                stop_channel_server(channel_server)


class TestFallbackWithoutScene:
    """Test fallback engine doesn't require scene data."""

    def test_fallback_ignores_scene_file(self, examples_for_tests, tmp_path):
        """Test that fallback mode works (scene file exists but isn't used)."""
        yaml_path = examples_for_tests / "p2p_fallback_snr_vacuum" / "network.yaml"

        if not yaml_path.exists():
            pytest.skip(f"Example not found: {yaml_path}")

        # Copy to temp
        temp_yaml = tmp_path / "network.yaml"
        with open(yaml_path, encoding="utf-8") as f:
            content = f.read()
        with open(temp_yaml, "w", encoding="utf-8") as f:
            f.write(content)

        channel_server = None
        deploy_process = None
        try:
            # Start channel server in fallback mode (scene file exists but fallback doesn't use it)
            print("\nStarting channel server in fallback mode...")
            channel_server = start_channel_server_fallback()

            # Deploy topology
            uv_path = get_uv_path()
            print(f"\nDeploying with fallback (scene file ignored): {temp_yaml}")

            deploy_process = subprocess.Popen(
                ["sudo", uv_path, "run", "sine", "deploy", str(temp_yaml)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            deployment_ready = False
            assert deploy_process.stdout is not None

            for line in deploy_process.stdout:
                print(line, end="")
                if "Emulation deployed successfully!" in line:
                    deployment_ready = True
                    break
                if deploy_process.poll() is not None:
                    raise RuntimeError("Deployment failed unexpectedly")

            assert deployment_ready, "Deployment should succeed in fallback mode"

        finally:
            if deploy_process is not None:
                stop_deployment_process(deploy_process)
            destroy_topology(str(temp_yaml))
            if channel_server is not None:
                stop_channel_server(channel_server)


class TestFallbackPerformance:
    """Test fallback engine performance characteristics."""

    def test_fallback_deployment_speed(self, examples_for_tests, tmp_path):
        """Test that fallback deployment is fast (no GPU initialization overhead)."""
        yaml_path = examples_for_tests / "p2p_fallback_snr_vacuum" / "network.yaml"

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

            # Time the deployment
            start_time = time.time()

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

            for line in deploy_process.stdout:
                print(line, end="")
                if "Emulation deployed successfully!" in line:
                    deployment_ready = True
                    break
                if deploy_process.poll() is not None:
                    raise RuntimeError("Deployment failed")

            end_time = time.time()
            deployment_time = end_time - start_time

            assert deployment_ready

            # Fallback should be fast (no GPU init, simple FSPL calculation)
            # Typically < 30 seconds on reasonable hardware
            print(f"\nFallback deployment time: {deployment_time:.2f} seconds")
            assert deployment_time < 60, "Fallback deployment took too long"

        finally:
            if deploy_process is not None:
                stop_deployment_process(deploy_process)
            destroy_topology(str(temp_yaml))
            if channel_server is not None:
                stop_channel_server(channel_server)


class TestFallbackVsAutoMode:
    """Test differences between force-fallback and auto mode."""

    def test_auto_mode_uses_fallback_when_no_gpu(self, examples_for_tests, tmp_path):
        """Test that AUTO mode gracefully falls back when GPU unavailable."""
        from sine.channel.server import is_sionna_available

        # Skip if Sionna is available (can't test fallback behavior)
        if is_sionna_available():
            pytest.skip("Sionna available, cannot test fallback behavior in AUTO mode")

        yaml_path = examples_for_tests / "p2p_fallback_snr_vacuum" / "network.yaml"

        temp_yaml = tmp_path / "network.yaml"
        with open(yaml_path) as f:
            content = f.read()
        with open(temp_yaml, "w") as f:
            f.write(content)

        process = None
        try:
            # Deploy WITHOUT --force-fallback (AUTO mode)
            uv_path = get_uv_path()
            process = subprocess.Popen(
                ["sudo", uv_path, "run", "sine", "deploy", str(temp_yaml)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            deployment_ready = False
            assert process.stdout is not None

            for line in process.stdout:
                print(line, end="")
                if "Emulation deployed successfully!" in line:
                    deployment_ready = True
                    break
                if process.poll() is not None:
                    raise RuntimeError("Deployment failed")

            # Should succeed via fallback
            assert deployment_ready

        finally:
            if process is not None:
                stop_deployment_process(process)
            destroy_topology(str(temp_yaml))


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
