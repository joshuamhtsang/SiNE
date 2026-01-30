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
    import os
    import shutil

    # Try environment variable first (set by user when running with sudo)
    uv_path = os.environ.get("UV_PATH")
    if uv_path and os.path.exists(uv_path):
        return uv_path

    # Try using shutil.which (respects PATH)
    uv_path = shutil.which("uv")
    if uv_path:
        return uv_path

    # Try common installation locations
    common_paths = [
        os.path.expanduser("~/.local/bin/uv"),
        os.path.expanduser("~/.cargo/bin/uv"),
        "/usr/local/bin/uv",
        "/usr/bin/uv",
    ]

    for path in common_paths:
        if os.path.exists(path):
            return path

    # Last resort: try which command
    try:
        result = subprocess.run(
            ["which", "uv"], capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        pass

    raise RuntimeError(
        "Could not find uv binary. Set UV_PATH environment variable or ensure uv is in PATH."
    )


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

    # Type assertion: stdout is guaranteed to be available since we passed PIPE
    assert process.stdout is not None, "stdout should not be None when PIPE is used"

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
    duration_sec: int = 8,
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
    print(f"Running iperf3 client on {client_container} -> {client_ip}... (expected duration {duration_sec}s)")
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


def verify_ping_connectivity(container_prefix: str, node_ips: dict[str, str]) -> None:
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


def verify_route_to_cidr(
    container_prefix: str,
    node: str,
    cidr: str,
    interface: str
) -> None:
    """Verify route to CIDR exists on the correct interface.

    Args:
        container_prefix: Docker container name prefix (e.g., "clab-mylab")
        node: Node name
        cidr: CIDR to check (e.g., "192.168.100.0/24")
        interface: Expected interface name (e.g., "eth1")

    Raises:
        AssertionError: If route is missing or on wrong interface
    """
    container_name = f"{container_prefix}-{node}"

    # Get routing table
    cmd = f"docker exec {container_name} ip route show"
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)

    # Parse routing table
    routes = result.stdout.strip().split('\n')

    # Find matching route
    for route in routes:
        if cidr in route:
            # Extract interface from route line
            # Format: "192.168.100.0/24 dev eth1 proto kernel scope link src 192.168.100.1"
            parts = route.split()
            if 'dev' in parts:
                dev_idx = parts.index('dev')
                if dev_idx + 1 < len(parts):
                    actual_iface = parts[dev_idx + 1]
                    if actual_iface == interface:
                        return  # Route found on correct interface
                    else:
                        raise AssertionError(
                            f"Route to {cidr} found on {actual_iface}, expected {interface}\n"
                            f"Routing table:\n{result.stdout}"
                        )

    # Route not found
    raise AssertionError(
        f"Route to {cidr} not found in routing table\n"
        f"Routing table:\n{result.stdout}"
    )


def verify_tc_config(
    container_prefix: str,
    node: str,
    interface: str,
    dst_node_ip: str | None = None,
    expected_rate_mbps: float | None = None,
    expected_delay_ms: float | None = None,
    expected_jitter_ms: float | None = None,
    expected_loss_percent: float | None = None,
    delay_tolerance_ms: float = 0.01,
    jitter_tolerance_ms: float = 0.01,
    loss_tolerance_percent: float = 0.1,
    rate_tolerance_mbps: float = 1.0
) -> dict[str, float | str | None]:
    """Verify TC configuration matches expected parameters.

    Args:
        container_prefix: Docker container name prefix (e.g., "clab-mylab")
        node: Node name
        interface: Interface name (e.g., "eth1")
        dst_node_ip: Destination IP for shared bridge mode (optional)
        expected_rate_mbps: Expected rate in Mbps (optional)
        expected_delay_ms: Expected delay in ms (optional)
        expected_jitter_ms: Expected jitter in ms (optional)
        expected_loss_percent: Expected loss percentage (optional)
        delay_tolerance_ms: Tolerance for delay comparison (default: 0.01 ms)
        jitter_tolerance_ms: Tolerance for jitter comparison (default: 0.01 ms)
        loss_tolerance_percent: Tolerance for loss comparison (default: 0.1%)
        rate_tolerance_mbps: Tolerance for rate comparison (default: 1.0 Mbps)

    Returns:
        Dict with actual values:
        {
            "mode": "shared_bridge" | "point_to_point" | "none",
            "rate_mbps": float | None,
            "delay_ms": float | None,
            "jitter_ms": float | None,
            "loss_percent": float | None,
            "htb_classid": str | None,  # e.g., "1:10" (shared bridge only)
            "filter_match": bool | None  # Filter exists for dst_ip (shared bridge only)
        }

    Raises:
        AssertionError: If values don't match within tolerance
    """
    import re

    container_name = f"{container_prefix}-{node}"

    # Initialize result dict
    result: dict[str, float | str | None] = {
        "mode": None,
        "rate_mbps": None,
        "delay_ms": None,
        "jitter_ms": None,
        "loss_percent": None,
        "htb_classid": None,
        "filter_match": None,
    }

    # Get qdisc info
    cmd = f"docker exec {container_name} tc qdisc show dev {interface}"
    print(f"Running: {cmd}")
    qdisc_result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
    qdisc_output = qdisc_result.stdout
    print(f"Qdisc output:\n{qdisc_output}")

    # Detect mode
    if "qdisc htb 1: root" in qdisc_output:
        result["mode"] = "shared_bridge"
    elif "qdisc netem" in qdisc_output and "root" in qdisc_output:
        result["mode"] = "point_to_point"
    else:
        result["mode"] = "none"
        return result

    # Parse based on mode
    if result["mode"] == "shared_bridge":
        # Shared bridge mode: HTB + flower filters
        if dst_node_ip is None:
            raise ValueError("dst_node_ip required for shared_bridge mode")

        # Get filters to find classid for destination IP
        filter_cmd = f"docker exec {container_name} tc filter show dev {interface}"
        print(f"Running: {filter_cmd}")
        filter_result = subprocess.run(filter_cmd, shell=True, capture_output=True, text=True, check=True)
        filter_output = filter_result.stdout
        print(f"Filter output:\n{filter_output}")

        # Parse filter output to find classid/flowid for dst_ip
        # Format:
        #   filter parent 1: protocol ip pref 1 flower chain 0 handle 0x1 classid 1:10
        #     eth_type ipv4
        #     dst_ip 192.168.100.2
        flowid = None
        lines = filter_output.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i]
            if f"dst_ip {dst_node_ip}" in line:
                result["filter_match"] = True
                # Search backwards for the line with classid
                for j in range(i - 1, max(-1, i - 10), -1):
                    if j >= 0:
                        classid_match = re.search(r'classid\s+(1:\d+)', lines[j])
                        if classid_match:
                            flowid = classid_match.group(1)
                            result["htb_classid"] = flowid
                            break
                if flowid:
                    break
            i += 1

        if flowid is None:
            raise AssertionError(
                f"Expected HTB class for dst_ip {dst_node_ip}, no matching filter found\n"
                f"Filter output:\n{filter_output}"
            )

        # Get HTB class info for rate
        class_cmd = f"docker exec {container_name} tc class show dev {interface}"
        print(f"Running: {class_cmd}")
        class_result = subprocess.run(class_cmd, shell=True, capture_output=True, text=True, check=True)
        class_output = class_result.stdout
        print(f"Class output:\n{class_output}")

        # Extract rate from class
        for line in class_output.split('\n'):
            if f"class htb {flowid}" in line:
                # Parse: "class htb 1:10 parent 1:1 prio 0 rate 192Mbit ceil 192Mbit ..."
                rate_match = re.search(r'rate\s+(\d+(?:\.\d+)?)([KMG]?)bit', line)
                if rate_match:
                    rate_value = float(rate_match.group(1))
                    rate_unit = rate_match.group(2)
                    # Convert to Mbps
                    if rate_unit == 'K':
                        result["rate_mbps"] = rate_value / 1000
                    elif rate_unit == 'G':
                        result["rate_mbps"] = rate_value * 1000
                    else:  # M or empty (defaults to Mbit)
                        result["rate_mbps"] = rate_value
                break

        # Get netem params from qdisc with parent=flowid
        # Note: Very small delays may not appear in netem output
        result["delay_ms"] = 0.0
        result["jitter_ms"] = 0.0
        result["loss_percent"] = 0.0

        for line in qdisc_output.split('\n'):
            if f"parent {flowid}" in line and "netem" in line:
                # Parse: "qdisc netem 10: parent 1:10 limit 1000 delay 0.067ms loss 0%"
                # Note: delay may be absent if very small
                delay_match = re.search(r'delay\s+(\d+(?:\.\d+)?)ms(?:\s+(\d+(?:\.\d+)?)ms)?', line)
                if delay_match:
                    result["delay_ms"] = float(delay_match.group(1))
                    if delay_match.group(2):
                        result["jitter_ms"] = float(delay_match.group(2))
                    else:
                        result["jitter_ms"] = 0.0

                loss_match = re.search(r'loss\s+([\d.eE+-]+)%', line)
                if loss_match:
                    result["loss_percent"] = float(loss_match.group(1))
                break

    elif result["mode"] == "point_to_point":
        # Point-to-point mode: netem root + tbf child
        # Parse netem params from root qdisc
        for line in qdisc_output.split('\n'):
            if "qdisc netem" in line and "root" in line:
                # Parse: "qdisc netem 1: root refcnt 2 limit 1000 delay 10.0ms 1.0ms loss 0.1%"
                delay_match = re.search(r'delay\s+(\d+(?:\.\d+)?)ms(?:\s+(\d+(?:\.\d+)?)ms)?', line)
                if delay_match:
                    result["delay_ms"] = float(delay_match.group(1))
                    if delay_match.group(2):
                        result["jitter_ms"] = float(delay_match.group(2))
                    else:
                        result["jitter_ms"] = 0.0

                loss_match = re.search(r'loss\s+([\d.eE+-]+)%', line)
                if loss_match:
                    result["loss_percent"] = float(loss_match.group(1))

            elif "qdisc tbf" in line:
                # Parse: "qdisc tbf 2: parent 1: rate 100Mbit burst 400Kb lat 50ms"
                rate_match = re.search(r'rate\s+(\d+(?:\.\d+)?)([KMG]?)bit', line)
                if rate_match:
                    rate_value = float(rate_match.group(1))
                    rate_unit = rate_match.group(2)
                    # Convert to Mbps
                    if rate_unit == 'K':
                        result["rate_mbps"] = rate_value / 1000
                    elif rate_unit == 'G':
                        result["rate_mbps"] = rate_value * 1000
                    else:  # M or empty (defaults to Mbit)
                        result["rate_mbps"] = rate_value

    # Validate against expected values
    if expected_rate_mbps is not None and result["rate_mbps"] is not None:
        if abs(result["rate_mbps"] - expected_rate_mbps) > rate_tolerance_mbps:
            raise AssertionError(
                f"Expected rate {expected_rate_mbps}mbps ± {rate_tolerance_mbps}mbps, "
                f"got {result['rate_mbps']}mbps"
            )

    if expected_delay_ms is not None and result["delay_ms"] is not None:
        if abs(result["delay_ms"] - expected_delay_ms) > delay_tolerance_ms:
            raise AssertionError(
                f"Expected delay {expected_delay_ms}ms ± {delay_tolerance_ms}ms, "
                f"got {result['delay_ms']}ms"
            )

    if expected_jitter_ms is not None and result["jitter_ms"] is not None:
        if abs(result["jitter_ms"] - expected_jitter_ms) > jitter_tolerance_ms:
            raise AssertionError(
                f"Expected jitter {expected_jitter_ms}ms ± {jitter_tolerance_ms}ms, "
                f"got {result['jitter_ms']}ms"
            )

    if expected_loss_percent is not None and result["loss_percent"] is not None:
        if abs(result["loss_percent"] - expected_loss_percent) > loss_tolerance_percent:
            raise AssertionError(
                f"Expected loss {expected_loss_percent}% ± {loss_tolerance_percent}%, "
                f"got {result['loss_percent']}%"
            )

    return result


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
        # stdout and stderr will go to the test output (not piped)
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
