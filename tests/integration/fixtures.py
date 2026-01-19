"""Shared fixtures and helper functions for integration tests.

This module contains:
- pytest fixtures (channel_server, etc.)
- Helper functions for deployment, cleanup, and testing
- Common utilities used across multiple integration test files

Import these in integration test files to avoid duplication.
"""

import logging
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

logger = logging.getLogger(__name__)


# =============================================================================
# Utility Functions
# =============================================================================


def get_uv_path() -> str:
    """Get the full path to the uv binary.

    Returns:
        Full path to uv executable

    Raises:
        RuntimeError: If uv is not found
    """
    result = subprocess.run(
        ["which", "uv"], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def deploy_topology(yaml_path: str) -> subprocess.Popen:
    """Deploy a topology using sine deploy command.

    Args:
        yaml_path: Path to the topology YAML file

    Returns:
        Popen object for the running deployment process

    Note:
        Caller is responsible for stopping the process and cleanup.
    """
    uv_path = get_uv_path()

    print(f"\n{'='*70}")
    print(f"Deploying topology: {yaml_path}")
    print(f"{'='*70}\n")

    # Start deployment in background
    process = subprocess.Popen(
        ["sudo", uv_path, "run", "sine", "deploy", str(yaml_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    # Wait for deployment to complete (read stdout until success message)
    print("Waiting for deployment to complete...")
    deployment_ready = False
    for line in process.stdout:
        print(line, end="")
        if "Emulation deployed successfully!" in line:
            deployment_ready = True
            break
        if process.poll() is not None:
            raise RuntimeError(f"Deployment failed (exit code {process.returncode})")

    if not deployment_ready:
        process.terminate()
        raise RuntimeError("Deployment did not complete successfully")

    print("\n" + "="*70)
    print("Deployment complete!")
    print("="*70 + "\n")

    return process


def stop_deployment_process(process: subprocess.Popen | None) -> None:
    """Stop a deployment process gracefully.

    Args:
        process: The deployment process to stop, or None
    """
    if process is None:
        return

    print("\nStopping deployment process...")
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        logger.warning("Deployment process did not stop gracefully, killing...")
        process.kill()
        process.wait()


def destroy_topology(yaml_path: str) -> None:
    """Destroy a deployed topology using sine destroy command.

    Args:
        yaml_path: Path to the topology YAML file
    """
    uv_path = get_uv_path()

    print(f"\n{'='*70}")
    print(f"Destroying topology: {yaml_path}")
    print(f"{'='*70}\n")

    result = subprocess.run(
        ["sudo", uv_path, "run", "sine", "destroy", str(yaml_path)],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        logger.warning(f"Destroy command failed: {result.stderr}")
    else:
        print("Topology destroyed successfully\n")


def configure_ips(container_prefix: str, node_ips: dict[str, str]) -> None:
    """Configure IP addresses on container interfaces.

    Args:
        container_prefix: Docker container name prefix (e.g., "clab-mylab")
        node_ips: Dictionary mapping node names to IP addresses
                  (e.g., {"node1": "192.168.1.1/24"})
    """
    for node_name, ip_addr in node_ips.items():
        container_name = f"{container_prefix}-{node_name}"
        cmd = f"docker exec {container_name} ip addr add {ip_addr} dev eth1"

        print(f"Configuring IP on {container_name}: {ip_addr}")
        subprocess.run(cmd, shell=True, check=False)


def run_iperf3_test(
    container_prefix: str,
    server_node: str,
    client_node: str,
    client_ip: str,
    duration_sec: int = 10,
) -> float:
    """Run iperf3 throughput test between two containers.

    Args:
        container_prefix: Docker container name prefix (e.g., "clab-mylab")
        server_node: Server node name
        client_node: Client node name
        client_ip: IP address of the server (from client's perspective)
        duration_sec: Test duration in seconds

    Returns:
        Measured throughput in Mbps

    Raises:
        RuntimeError: If iperf3 test fails
    """
    server_container = f"{container_prefix}-{server_node}"
    client_container = f"{container_prefix}-{client_node}"

    # Start iperf3 server in background
    print(f"\nStarting iperf3 server on {server_container}...")
    server_cmd = f"docker exec -d {server_container} iperf3 -s"
    subprocess.run(server_cmd, shell=True, check=True)

    # Give server time to start
    time.sleep(2)

    # Run iperf3 client
    print(f"Running iperf3 client on {client_container} -> {client_ip}...")
    client_cmd = (
        f"docker exec {client_container} iperf3 -c {client_ip} "
        f"-t {duration_sec} -J"
    )
    result = subprocess.run(
        client_cmd, shell=True, capture_output=True, text=True, check=True
    )

    # Parse JSON output to extract throughput
    import json
    output = json.loads(result.stdout)
    throughput_bps = output["end"]["sum_received"]["bits_per_second"]
    throughput_mbps = throughput_bps / 1e6

    print(f"Measured throughput: {throughput_mbps:.2f} Mbps\n")

    # Kill iperf3 server
    kill_cmd = f"docker exec {server_container} pkill iperf3"
    subprocess.run(kill_cmd, shell=True, timeout=10)

    return throughput_mbps


def test_ping_connectivity(container_prefix: str, node_ips: dict[str, str]) -> None:
    """Test all-to-all ping connectivity between nodes.

    Args:
        container_prefix: Docker container name prefix (e.g., "clab-mylab")
        node_ips: Dictionary mapping node names to IP addresses

    Raises:
        AssertionError: If any ping fails
    """
    nodes = list(node_ips.keys())

    print(f"\n{'='*70}")
    print("Testing all-to-all ping connectivity")
    print(f"{'='*70}\n")

    for src_node in nodes:
        for dst_node in nodes:
            if src_node == dst_node:
                continue

            src_container = f"{container_prefix}-{src_node}"
            dst_ip = node_ips[dst_node]

            print(f"Ping {src_node} -> {dst_node} ({dst_ip})...", end=" ")

            cmd = f"docker exec {src_container} ping -c 3 -W 2 {dst_ip}"
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True
            )

            if result.returncode == 0:
                print("✓ SUCCESS")
            else:
                print("✗ FAILED")
                raise AssertionError(
                    f"Ping failed: {src_node} -> {dst_node} ({dst_ip})\n"
                    f"Output: {result.stdout}\n{result.stderr}"
                )

    print(f"\n{'='*70}")
    print("All ping tests passed!")
    print(f"{'='*70}\n")


# =============================================================================
# Pytest Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def channel_server():
    """Start channel server for tests, stop after all tests complete.

    This is a session-scoped fixture that starts the channel server once
    at the beginning of the test session and stops it at the end.

    Yields:
        Server URL (http://localhost:8000)
    """
    uv_path = get_uv_path()

    # Start channel server in background
    logger.info("Starting channel server...")
    print("\n" + "="*70)
    print("CHANNEL SERVER STARTUP")
    print("="*70 + "\n")

    process = subprocess.Popen(
        [uv_path, "run", "sine", "channel-server"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Wait for server to be ready (check health endpoint)
    server_url = "http://localhost:8000"
    max_retries = 30

    for i in range(max_retries):
        try:
            with urllib.request.urlopen(f"{server_url}/health", timeout=1) as response:
                if response.status == 200:
                    logger.info(f"Channel server ready at {server_url}")
                    print(f"✓ Channel server is ready at {server_url}")
                    print("="*70 + "\n")
                    break
        except (urllib.error.URLError, OSError):
            if i < max_retries - 1:
                time.sleep(1)
            else:
                process.kill()
                raise RuntimeError("Channel server failed to start")

    yield server_url

    # Cleanup: stop channel server
    logger.info("Stopping channel server...")
    print("\n" + "="*70)
    print("Stopping channel server...")
    print("="*70 + "\n")

    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
