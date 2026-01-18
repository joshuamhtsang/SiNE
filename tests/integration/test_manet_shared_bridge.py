"""
Integration tests for MANET shared bridge topology.

These tests deploy the manet_triangle_shared example and validate:
1. All nodes can reach each other (connectivity)
2. iperf3 throughput matches expected rates

Requirements:
- Channel server running (automatically started by test fixture)
- sudo access for netem configuration (passwordless or pre-authenticated)
- containerlab installed
- iperf3 installed in container images

Running these tests:
    # Authenticate sudo before running
    sudo -v && uv run pytest tests/integration/test_manet_shared_bridge.py -v -m integration
"""

import logging
import subprocess
import time
from pathlib import Path

import pytest

logger = logging.getLogger(__name__)


def deploy_topology(yaml_path: str) -> subprocess.Popen:
    """
    Deploy a topology using sine CLI in background.

    Args:
        yaml_path: Path to topology YAML file

    Returns:
        Popen object for the running deployment process
    """
    # Use full path to uv to avoid "command not found" with sudo
    uv_path = subprocess.run(
        ["which", "uv"], capture_output=True, text=True, check=True
    ).stdout.strip()

    print(f"\n{'='*70}")
    print(f"Deploying topology: {yaml_path}")
    print(f"{'='*70}\n")

    # Start deployment in background (Popen, not run)
    # Capture output so we can monitor for "Emulation deployed successfully!"
    process = subprocess.Popen(
        ["sudo", uv_path, "run", "sine", "deploy", yaml_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,  # Line buffered
    )

    # Wait for deployment to complete by watching stdout
    print("Waiting for deployment to complete...")
    deployment_ready = False
    for line in process.stdout:
        print(line, end="")  # Echo output in real-time
        if "Emulation deployed successfully!" in line:
            deployment_ready = True
            break
        # Check if process exited with error
        if process.poll() is not None:
            raise RuntimeError(f"Deployment process exited unexpectedly (code {process.returncode})")

    if not deployment_ready:
        process.terminate()
        raise RuntimeError("Deployment did not complete successfully")

    print(f"\n{'='*70}")
    print(f"Deployment complete (process running in background)")
    print(f"{'='*70}\n")

    # Give containers a moment to fully initialize
    time.sleep(2)

    return process


def stop_deployment_process(process: subprocess.Popen | None) -> None:
    """
    Stop a running deployment process gracefully.

    Args:
        process: The deployment Popen object to stop
    """
    if not process:
        return

    print("\nStopping deployment process...")
    process.terminate()
    try:
        process.wait(timeout=10)
        print("  Deployment process stopped")
    except subprocess.TimeoutExpired:
        print("  Force killing deployment process...")
        process.kill()
        process.wait()
        print("  Deployment process killed")


def destroy_topology(yaml_path: str) -> None:
    """
    Destroy a topology using sine CLI.

    Args:
        yaml_path: Path to topology YAML file
    """
    # Use full path to uv to avoid "command not found" with sudo
    uv_path = subprocess.run(
        ["which", "uv"], capture_output=True, text=True, check=True
    ).stdout.strip()

    print(f"Cleaning up existing deployment (if any)...")
    # Suppress output for destroy - we don't care if it fails (no existing deployment)
    result = subprocess.run(
        ["sudo", uv_path, "run", "sine", "destroy", yaml_path],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        print(f"  No existing deployment to clean up")
    else:
        print(f"  Cleaned up existing deployment")


def run_iperf3_test(
    container_prefix: str,
    server_node: str,
    client_node: str,
    client_ip: str,
    duration_sec: int = 30,
) -> float:
    """
    Run iperf3 test and return measured throughput.

    Args:
        container_prefix: Container name prefix
        server_node: Server node name
        client_node: Client node name
        client_ip: Client IP address (to connect to server)
        duration_sec: Test duration in seconds

    Returns:
        Throughput in Mbps
    """
    server_container = f"{container_prefix}-{server_node}"
    client_container = f"{container_prefix}-{client_node}"

    print(f"\n{'='*70}")
    print(f"Running iperf3 throughput test ({duration_sec}s)")
    print(f"  Server: {server_container}")
    print(f"  Client: {client_container} -> {client_ip}")
    print(f"{'='*70}\n")

    # Start iperf3 server in background
    print(f"Starting iperf3 server on {server_node}...")
    server_cmd = f"docker exec -d {server_container} iperf3 -s"
    subprocess.run(server_cmd, shell=True, timeout=10)
    time.sleep(2)  # Give server time to start

    # Run iperf3 client with real-time output
    print(f"Running iperf3 client from {client_node} (this will take {duration_sec}s)...")

    client_cmd = (
        f"docker exec {client_container} iperf3 -c {client_ip} "
        f"-t {duration_sec} -J"
    )
    print(f"\n{'─'*70}")
    process = subprocess.Popen(
        client_cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,  # Line buffered
    )

    # Collect output for JSON parsing while displaying progress
    output_lines = []
    json_started = False

    for line in process.stdout:
        output_lines.append(line)

        # Detect when JSON output starts (begins with '{')
        if line.strip().startswith("{"):
            json_started = True

        # Only print non-JSON lines (the progress output)
        if not json_started:
            print(line, end="")

    process.wait(timeout=duration_sec + 10)
    print(f"{'─'*70}\n")

    if process.returncode != 0:
        raise RuntimeError(f"iperf3 test failed with code {process.returncode}")

    # Parse JSON output to extract throughput
    import json

    # Join all lines to get complete JSON
    full_output = "".join(output_lines)

    # Extract JSON portion (everything from first '{' to last '}')
    json_start = full_output.find("{")
    json_end = full_output.rfind("}") + 1

    if json_start == -1 or json_end == 0:
        raise RuntimeError("Could not find JSON output from iperf3")

    json_output = full_output[json_start:json_end]
    iperf_data = json.loads(json_output)
    throughput_bps = iperf_data["end"]["sum_received"]["bits_per_second"]
    throughput_mbps = throughput_bps / 1e6

    print(f"\nMeasured throughput: {throughput_mbps:.1f} Mbps\n")

    # Kill iperf3 server
    kill_cmd = f"docker exec {server_container} pkill iperf3"
    subprocess.run(kill_cmd, shell=True, timeout=10)

    return throughput_mbps


def test_ping_connectivity(container_prefix: str, node_ips: dict[str, str]) -> None:
    """
    Test that all nodes can ping each other.

    Args:
        container_prefix: Container name prefix
        node_ips: Dictionary {node_name: ip_address}
    """
    print(f"\n{'='*70}")
    print(f"Testing connectivity (ping)")
    print(f"{'='*70}\n")

    nodes = list(node_ips.keys())
    for i, src_node in enumerate(nodes):
        for dst_node in nodes[i+1:]:
            src_container = f"{container_prefix}-{src_node}"
            dst_ip = node_ips[dst_node]

            print(f"  {src_node} → {dst_node} ({dst_ip})...", end=" ")

            # Ping with 3 packets, 1 second timeout
            cmd = f"docker exec {src_container} ping -c 3 -W 1 {dst_ip}"
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                print("✓ OK")
            else:
                print("✗ FAILED")
                print(f"    stdout: {result.stdout}")
                print(f"    stderr: {result.stderr}")
                raise RuntimeError(f"Ping failed: {src_node} → {dst_node}")

    print(f"\n{'='*70}")
    print("All connectivity tests passed")
    print(f"{'='*70}\n")


@pytest.fixture(scope="session")
def channel_server():
    """Start channel server for tests, stop after all tests complete."""
    # Get uv path
    uv_path = subprocess.run(
        ["which", "uv"], capture_output=True, text=True, check=True
    ).stdout.strip()

    # Start channel server in background
    logger.info("Starting channel server...")
    process = subprocess.Popen(
        [uv_path, "run", "sine", "channel-server"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Wait for server to be ready (check health endpoint)
    import urllib.request
    import urllib.error

    server_url = "http://localhost:8000"
    max_retries = 30
    for i in range(max_retries):
        try:
            with urllib.request.urlopen(f"{server_url}/health", timeout=1) as response:
                if response.status == 200:
                    logger.info(f"Channel server ready at {server_url}")
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
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


@pytest.fixture
def examples_dir() -> Path:
    """Return path to examples directory."""
    return Path(__file__).parent.parent.parent / "examples"


@pytest.mark.integration
@pytest.mark.slow
def test_manet_shared_bridge_connectivity(channel_server, examples_dir: Path):
    """
    Test MANET shared bridge connectivity.

    Expected: All nodes can ping each other (all-to-all connectivity).
    """
    yaml_path = examples_dir / "manet_triangle_shared" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    # Cleanup any existing deployment first
    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        # Deploy (returns background process)
        deploy_process = deploy_topology(str(yaml_path))

        # Test connectivity (IPs already configured by deployment)
        node_ips = {
            "node1": "192.168.100.1",
            "node2": "192.168.100.2",
            "node3": "192.168.100.3",
        }

        test_ping_connectivity("clab-manet-triangle-shared", node_ips)

    finally:
        # Stop deployment process
        stop_deployment_process(deploy_process)
        # Cleanup containers
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
def test_manet_shared_bridge_throughput(channel_server, examples_dir: Path):
    """
    Test MANET shared bridge throughput.

    Expected: Throughput matches configured rate (~192 Mbps for 64-QAM, 80 MHz, rate-1/2).
    PHY rate = 80 MHz × 6 bits/symbol × 0.5 code_rate × 0.8 efficiency = 192 Mbps
    """
    yaml_path = examples_dir / "manet_triangle_shared" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    # Cleanup any existing deployment first
    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        # Deploy (returns background process)
        deploy_process = deploy_topology(str(yaml_path))

        # Run iperf3 test (using the shared bridge IPs already configured)
        throughput = run_iperf3_test(
            container_prefix="clab-manet-triangle-shared",
            server_node="node1",
            client_node="node2",
            client_ip="192.168.100.1",  # Use existing bridge IP
            duration_sec=30,
        )

        # Validate: 93-100% of ~192 Mbps (64-QAM, 80 MHz, rate-1/2)
        # Allow for protocol overhead and measurement variance
        # Relaxed from 95% to account for TCP overhead and timing variance
        assert 178.5 <= throughput <= 192, (
            f"Throughput {throughput:.1f} Mbps not in expected range "
            f"[178.5-192 Mbps] (93-100% of PHY rate)"
        )

    finally:
        # Stop deployment process
        stop_deployment_process(deploy_process)
        # Cleanup containers
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
def test_manet_shared_bridge_bidirectional_throughput(channel_server, examples_dir: Path):
    """
    Test bidirectional throughput in MANET shared bridge.

    Expected: Both directions achieve similar throughput (symmetric links).
    """
    yaml_path = examples_dir / "manet_triangle_shared" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    # Cleanup any existing deployment first
    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        # Deploy (returns background process)
        deploy_process = deploy_topology(str(yaml_path))

        # Test node1 → node2
        throughput_1_to_2 = run_iperf3_test(
            container_prefix="clab-manet-triangle-shared",
            server_node="node1",
            client_node="node2",
            client_ip="192.168.100.1",
            duration_sec=20,
        )

        # Test node2 → node1
        throughput_2_to_1 = run_iperf3_test(
            container_prefix="clab-manet-triangle-shared",
            server_node="node2",
            client_node="node1",
            client_ip="192.168.100.2",
            duration_sec=20,
        )

        # Both directions should be within 10% of each other
        ratio = max(throughput_1_to_2, throughput_2_to_1) / min(throughput_1_to_2, throughput_2_to_1)
        assert ratio <= 1.1, (
            f"Bidirectional throughput asymmetry too high: "
            f"{throughput_1_to_2:.1f} Mbps vs {throughput_2_to_1:.1f} Mbps (ratio: {ratio:.2f})"
        )

        logger.info(
            f"Bidirectional throughput test passed: "
            f"node1→node2: {throughput_1_to_2:.1f} Mbps, "
            f"node2→node1: {throughput_2_to_1:.1f} Mbps"
        )

    finally:
        # Stop deployment process
        stop_deployment_process(deploy_process)
        # Cleanup containers
        destroy_topology(str(yaml_path))


if __name__ == "__main__":
    # Run tests manually for debugging
    import sys

    logging.basicConfig(level=logging.INFO)

    examples = Path(__file__).parent.parent.parent / "examples"

    print("=" * 80)
    print("MANET Shared Bridge Connectivity Test")
    print("=" * 80)
    test_manet_shared_bridge_connectivity(None, examples)

    print("\n" + "=" * 80)
    print("MANET Shared Bridge Throughput Test")
    print("=" * 80)
    test_manet_shared_bridge_throughput(None, examples)

    print("\n" + "=" * 80)
    print("MANET Shared Bridge Bidirectional Throughput Test")
    print("=" * 80)
    test_manet_shared_bridge_bidirectional_throughput(None, examples)

    print("\n" + "=" * 80)
    print("All tests passed!")
    print("=" * 80)
