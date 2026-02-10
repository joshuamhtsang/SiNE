"""Shared fixtures and helper functions for integration tests.

This module contains:
- pytest fixtures (channel_server, etc.)
- Helper functions for deployment, cleanup, and testing
- Common utilities used across multiple integration test files

Import these in integration test files to avoid duplication.
"""

import atexit
import logging
import signal
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

logger = logging.getLogger(__name__)


# =============================================================================
# Global cleanup tracking (for Ctrl+C handling)
# =============================================================================

# Track deployed topologies and channel server process for cleanup on exit
_deployed_topologies: list[Path] = []
_channel_server_process: subprocess.Popen | None = None
_cleanup_registered = False


def _cleanup_all():
    """Clean up all deployed topologies and channel server on exit.

    Called by atexit handler or signal handlers (SIGINT, SIGTERM).
    """
    global _channel_server_process  # Needed because we reassign to None later

    if not _deployed_topologies and not _channel_server_process:
        return  # Nothing to clean up

    print("\n" + "="*70)
    print("EMERGENCY CLEANUP (Ctrl+C or test interruption detected)")
    print("="*70)

    # Destroy all deployed topologies
    if _deployed_topologies:
        print(f"\nCleaning up {len(_deployed_topologies)} deployed topology(ies)...")
        for yaml_path in _deployed_topologies:
            try:
                print(f"  Destroying: {yaml_path}")
                destroy_topology(str(yaml_path))
            except Exception as e:
                logger.error(f"Failed to destroy {yaml_path}: {e}")

        _deployed_topologies.clear()

    # Stop channel server
    if _channel_server_process:
        print("\nStopping channel server...")
        try:
            _channel_server_process.terminate()
            try:
                _channel_server_process.wait(timeout=5)
                print("  ✓ Channel server stopped")
            except subprocess.TimeoutExpired:
                print("  Channel server didn't stop gracefully, killing...")
                _channel_server_process.kill()
                _channel_server_process.wait()
                print("  ✓ Channel server killed")

            # Wait for port to be released (important for next test run)
            print("  Waiting for port 8000 to be released...")
            try:
                wait_for_port_available(8000, timeout_seconds=5)
                print("  ✓ Port 8000 is now available")
            except RuntimeError:
                print("  ⚠ Port 8000 still in use (may need manual cleanup)")
        except Exception as e:
            logger.error(f"Failed to stop channel server: {e}")
        finally:
            _channel_server_process = None

    print("="*70)
    print("Cleanup complete")
    print("="*70 + "\n")


def _signal_handler(signum, _frame):
    """Handle SIGINT (Ctrl+C) and SIGTERM by cleaning up."""
    print(f"\n\nReceived signal {signum}, cleaning up...")
    _cleanup_all()
    # Re-raise KeyboardInterrupt to let pytest handle it
    if signum == signal.SIGINT:
        raise KeyboardInterrupt


def _register_cleanup_handlers():
    """Register atexit and signal handlers for cleanup.

    Only registers once per process.
    """
    global _cleanup_registered

    if _cleanup_registered:
        return

    # Register atexit handler
    atexit.register(_cleanup_all)

    # Register signal handlers for Ctrl+C and SIGTERM
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    _cleanup_registered = True
    logger.debug("Registered cleanup handlers for atexit, SIGINT, and SIGTERM")


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


def extract_container_prefix(yaml_path: str | Path) -> str:
    """Extract container prefix from topology YAML name field.

    Containerlab convention: <prefix>-<name>-<node>
    This extracts the '<prefix>-<name>' part (e.g., 'clab-fallback-vacuum').

    Args:
        yaml_path: Path to topology YAML (str or Path)

    Returns:
        Container prefix (e.g., 'clab-fallback-vacuum')

    Raises:
        ValueError: If 'name' field is missing from YAML

    Example:
        >>> yaml_path = Path("examples/for_tests/p2p_fallback_snr_vacuum/network.yaml")
        >>> prefix = extract_container_prefix(yaml_path)
        >>> # prefix == "clab-fallback-vacuum"
    """
    import yaml

    # Convert to Path if string
    if isinstance(yaml_path, str):
        yaml_path = Path(yaml_path)

    with open(yaml_path, "r") as f:
        config = yaml.safe_load(f)

    # Extract the top-level 'name' field (required by schema)
    if "name" not in config:
        raise ValueError(f"Missing required 'name' field in {yaml_path}")

    lab_name = config["name"]

    # Get prefix (defaults to 'clab' if not specified)
    prefix = config.get("prefix", "clab")

    return f"{prefix}-{lab_name}"


def deploy_topology(yaml_path: str, enable_mobility: bool = False, channel_server_url: str = "http://localhost:8000") -> subprocess.Popen:
    """Deploy a topology using sine deploy command.

    Args:
        yaml_path: Path to the topology YAML file
        enable_mobility: If True, deploy with --enable-mobility flag
        channel_server_url: URL of the channel server to use (default: http://localhost:8000)

    Returns:
        Popen object for the running deployment process

    Note:
        This function automatically registers the topology for cleanup on exit
        (via atexit handler) in case of Ctrl+C or test interruption.
        Tests should still call destroy_topology() in their finally blocks for
        normal cleanup.
    """
    global _deployed_topologies

    uv_path = get_uv_path()
    yaml_path_obj = Path(yaml_path)

    # Register cleanup handlers on first deployment
    _register_cleanup_handlers()

    mobility_str = " (with mobility)" if enable_mobility else ""
    print(f"\n{'='*70}")
    print(f"Deploying topology{mobility_str}: {yaml_path}")
    print(f"Using channel server: {channel_server_url}")
    print(f"{'='*70}\n")

    # Build command
    cmd = ["sudo", uv_path, "run", "sine", "deploy", str(yaml_path)]
    # Always specify the channel server URL to avoid starting a new one
    cmd.extend(["--channel-server", channel_server_url])
    if enable_mobility:
        cmd.append("--enable-mobility")

    # Start deployment in background
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    # Wait for deployment to complete (read stdout until success message)
    print("Waiting for deployment to complete...")
    deployment_ready = False
    output_lines = []  # Capture all output for error reporting

    # Type assertion: stdout is guaranteed to be available since we passed PIPE
    assert process.stdout is not None, "stdout should not be None when PIPE is used"

    for line in process.stdout:
        output_lines.append(line)
        print(line, end="")
        if "Emulation deployed successfully!" in line:
            deployment_ready = True
            break
        if process.poll() is not None:
            # Process exited - capture remaining output and report error
            remaining = process.stdout.read()
            if remaining:
                output_lines.append(remaining)
                print(remaining, end="")

            full_output = ''.join(output_lines)
            raise RuntimeError(
                f"Deployment failed (exit code {process.returncode})\n\n"
                f"{'='*70}\n"
                f"DEPLOYMENT OUTPUT:\n"
                f"{'='*70}\n"
                f"{full_output}\n"
                f"{'='*70}"
            )

    if not deployment_ready:
        # Read any remaining output
        try:
            remaining = process.stdout.read()
            if remaining:
                output_lines.append(remaining)
                print(remaining, end="")
        except Exception:
            pass

        process.terminate()
        full_output = ''.join(output_lines)
        raise RuntimeError(
            f"Deployment did not complete successfully\n\n"
            f"{'='*70}\n"
            f"DEPLOYMENT OUTPUT:\n"
            f"{'='*70}\n"
            f"{full_output}\n"
            f"{'='*70}"
        )

    print("\n" + "="*70)
    print("Deployment complete!")
    print("="*70 + "\n")

    # Register this topology for emergency cleanup
    if yaml_path_obj not in _deployed_topologies:
        _deployed_topologies.append(yaml_path_obj)
        logger.debug(f"Registered topology for cleanup: {yaml_path_obj}")

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

    Note:
        Automatically unregisters the topology from emergency cleanup tracking.
    """
    global _deployed_topologies

    uv_path = get_uv_path()
    yaml_path_obj = Path(yaml_path)

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

    # Unregister from emergency cleanup tracking
    if yaml_path_obj in _deployed_topologies:
        _deployed_topologies.remove(yaml_path_obj)
        logger.debug(f"Unregistered topology from cleanup: {yaml_path_obj}")


def wait_for_iperf3(container_name: str, max_wait_sec: int = 30) -> None:
    """Wait for iperf3 to be available in a container.

    Containerlab's exec commands run asynchronously, so we need to wait for
    package installation to complete before using iperf3.

    Args:
        container_name: Docker container name
        max_wait_sec: Maximum time to wait in seconds

    Raises:
        RuntimeError: If iperf3 is not available after max_wait_sec
    """
    start_time = time.time()
    while time.time() - start_time < max_wait_sec:
        result = subprocess.run(
            f"docker exec {container_name} which iperf3",
            shell=True,
            capture_output=True,
        )
        if result.returncode == 0:
            return  # iperf3 is available

        time.sleep(0.5)  # Wait before retrying

    raise RuntimeError(
        f"iperf3 not available in {container_name} after {max_wait_sec}s. "
        f"Check that the container has 'exec: apk add iperf3' in the topology YAML."
    )


def run_iperf3_test(
    container_prefix: str,
    server_node: str,
    client_node: str,
    server_ip: str,
    duration_sec: int = 8,
    protocol: str = "tcp",
    udp_bandwidth_mbps: int = 300,
) -> float:
    """Run iperf3 throughput test between two containers.

    Args:
        container_prefix: Docker container name prefix (e.g., "clab-mylab")
        server_node: Server node name
        client_node: Client node name
        server_ip: IP address of the server (where client connects)
        duration_sec: Test duration in seconds
        protocol: Protocol to use ("tcp" or "udp")
        udp_bandwidth_mbps: Target bandwidth for UDP tests (default: 300 Mbps)

    Returns:
        Measured throughput in Mbps

    Raises:
        RuntimeError: If iperf3 test fails
        ValueError: If invalid protocol specified
        subprocess.TimeoutExpired: If test doesn't complete within duration_sec + 2 seconds
    """
    if protocol not in ["tcp", "udp"]:
        raise ValueError(f"Invalid protocol: {protocol}. Must be 'tcp' or 'udp'")

    server_container = f"{container_prefix}-{server_node}"
    client_container = f"{container_prefix}-{client_node}"

    # Wait for iperf3 to be available in both containers
    # (containerlab exec commands run asynchronously)
    print(f"Waiting for iperf3 to be available in {server_container} and {client_container}...")
    wait_for_iperf3(server_container)
    wait_for_iperf3(client_container)
    print("iperf3 is available in both containers\n")

    # Kill any existing iperf3 processes first
    print(f"\nCleaning up any existing iperf3 processes on {server_container}...")
    kill_cmd = f"docker exec {server_container} pkill -9 iperf3 || true"
    subprocess.run(kill_cmd, shell=True)
    time.sleep(0.5)

    # Start iperf3 server in background
    print(f"Starting iperf3 server on {server_container}...")
    server_cmd = f"docker exec -d {server_container} iperf3 -s"
    subprocess.run(server_cmd, shell=True, check=True)

    # Give server time to start
    time.sleep(2)

    # Build client command based on protocol
    print(f"Running iperf3 client ({protocol.upper()}) on {client_container} -> {server_ip}... "
          f"(expected duration {duration_sec}s)")

    if protocol == "udp":
        client_cmd = (
            f"docker exec {client_container} iperf3 -c {server_ip} "
            f"-u -b {udp_bandwidth_mbps}M -t {duration_sec} -J"
        )
    else:  # tcp
        client_cmd = (
            f"docker exec {client_container} iperf3 -c {server_ip} "
            f"-t {duration_sec} -J"
        )

    # Add timeout: test duration + 5 seconds grace period
    # This accounts for:
    # - Docker exec overhead (~1s)
    # - iperf3 startup/shutdown (~1-2s)
    # - JSON output generation (~1s)
    # - Network delays and cleanup (~1s)
    timeout_sec = duration_sec + 5

    try:
        result = subprocess.run(
            client_cmd, shell=True, capture_output=True, text=True, check=False, timeout=timeout_sec
        )
    except subprocess.TimeoutExpired as e:
        # Print debugging info before re-raising
        print(f"\n{'='*70}")
        print(f"IPERF3 TIMEOUT DEBUGGING")
        print(f"{'='*70}")
        print(f"Command: {client_cmd}")
        print(f"Timeout: {timeout_sec}s (test duration: {duration_sec}s)")
        print(f"\nPartial stdout: {e.stdout[:1000] if e.stdout else '(none)'}")
        print(f"\nPartial stderr: {e.stderr[:1000] if e.stderr else '(none)'}")
        print(f"\nChecking container status...")

        # Check if containers are still running
        container_check = subprocess.run(
            f"docker ps --filter name={container_prefix} --format '{{{{.Names}}}} {{{{.Status}}}}'",
            shell=True, capture_output=True, text=True
        )
        print(f"Running containers:\n{container_check.stdout}")

        # Check iperf3 processes
        server_ps = subprocess.run(
            f"docker exec {server_container} ps aux | grep iperf3 || echo 'No iperf3 processes'",
            shell=True, capture_output=True, text=True
        )
        print(f"\niperf3 processes on {server_container}:\n{server_ps.stdout}")

        client_ps = subprocess.run(
            f"docker exec {client_container} ps aux | grep iperf3 || echo 'No iperf3 processes'",
            shell=True, capture_output=True, text=True
        )
        print(f"\niperf3 processes on {client_container}:\n{client_ps.stdout}")

        # Check network connectivity
        ping_check = subprocess.run(
            f"docker exec {client_container} ping -c 3 -W 1 {server_ip}",
            shell=True, capture_output=True, text=True
        )
        print(f"\nPing test from {client_container} to {server_ip}:")
        print(f"Exit code: {ping_check.returncode}")
        print(f"Output: {ping_check.stdout}")
        print(f"{'='*70}\n")

        raise

    # Check if command failed
    if result.returncode != 0:
        # For UDP, iperf3 sometimes returns non-zero exit code even with valid results
        # (e.g., when there's packet loss). Try to parse the output anyway.
        if protocol == "udp" and result.stdout:
            print(f"Warning: iperf3 exited with code {result.returncode}, attempting to parse output anyway...")
        else:
            # For TCP or if there's no stdout, this is a real failure
            print(f"Error output: {result.stderr}")
            raise subprocess.CalledProcessError(result.returncode, client_cmd, result.stdout, result.stderr)

    # Parse JSON output to extract throughput
    import json
    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON output. Exit code: {result.returncode}")
        print(f"Stdout: {result.stdout[:500]}")
        print(f"Stderr: {result.stderr[:500]}")
        raise RuntimeError(f"iperf3 did not produce valid JSON output: {e}")

    # Different JSON paths for TCP vs UDP
    if protocol == "udp":
        throughput_bps = output["end"]["sum"]["bits_per_second"]
    else:  # tcp
        throughput_bps = output["end"]["sum_received"]["bits_per_second"]

    throughput_mbps = throughput_bps / 1e6

    print(f"Measured throughput: {throughput_mbps:.2f} Mbps\n")

    # Kill iperf3 server
    kill_cmd = f"docker exec {server_container} pkill iperf3"
    subprocess.run(kill_cmd, shell=True, timeout=10)

    return throughput_mbps


def run_netcat_udp_test(
    container_prefix: str,
    server_node: str,
    client_node: str,
    server_ip: str,
    duration_sec: int = 8,
    target_bandwidth_mbps: int = 300,
    port: int = 5001,
) -> float:
    """Run one-directional UDP throughput test using netcat.

    Unlike iperf3, netcat truly doesn't require bidirectional traffic - it only
    sends data in one direction with no control channel or ACKs. This makes it
    suitable for testing hidden node scenarios where the return path has negative SINR.

    Methodology:
    1. Start netcat UDP receiver on server (saves to /tmp/nc_received)
    2. Send data from client using dd + nc for duration_sec seconds
    3. Calculate throughput from received bytes

    Args:
        container_prefix: Docker container name prefix (e.g., "clab-mylab")
        server_node: Server node name (receiver)
        client_node: Client node name (sender)
        server_ip: IP address of the server
        duration_sec: Test duration in seconds (default: 8)
        target_bandwidth_mbps: Target bandwidth to attempt (default: 300 Mbps)
        port: UDP port to use (default: 5001)

    Returns:
        Measured throughput in Mbps (received bytes / duration)

    Raises:
        RuntimeError: If test fails or no data received
        subprocess.TimeoutExpired: If test doesn't complete

    Note:
        - Uses BusyBox nc (Alpine Linux default)
        - Receiver stores data to /tmp/nc_received
        - Throughput calculated from actual bytes received
        - No packet loss statistics available (netcat doesn't track this)
        - Packet size fixed at 1400 bytes (typical WiFi MTU minus headers)

    Example:
        >>> throughput = run_netcat_udp_test(
        ...     container_prefix="clab-csma-mcs-test",
        ...     server_node="node1",
        ...     client_node="node2",
        ...     server_ip="192.168.100.1",
        ...     duration_sec=8,
        ...     target_bandwidth_mbps=300,
        ... )
        >>> print(f"Measured: {throughput:.2f} Mbps")
    """
    server_container = f"{container_prefix}-{server_node}"
    client_container = f"{container_prefix}-{client_node}"

    packet_size_bytes = 1400  # Typical WiFi MTU minus IP/UDP headers

    print(f"\n{'='*70}")
    print("One-Directional UDP Test (netcat)")
    print(f"{'='*70}\n")
    print(f"Server: {server_container}")
    print(f"Client: {client_container} -> {server_ip}:{port}")
    print(f"Duration: {duration_sec}s | Target: {target_bandwidth_mbps} Mbps")
    print(f"Packet size: {packet_size_bytes} bytes\n")

    # Clean up any previous test files
    cleanup_cmd = f"docker exec {server_container} rm -f /tmp/nc_received"
    subprocess.run(cleanup_cmd, shell=True)

    # Kill any existing netcat processes
    print("Cleaning up any existing netcat processes...")
    kill_cmd_server = f"docker exec {server_container} pkill -9 nc || true"
    kill_cmd_client = f"docker exec {client_container} pkill -9 nc || true"
    subprocess.run(kill_cmd_server, shell=True)
    subprocess.run(kill_cmd_client, shell=True)
    time.sleep(0.5)

    # Start netcat receiver in background
    # BusyBox nc syntax: nc -u -l -p <port>
    print(f"Starting netcat receiver on {server_container}...")
    receiver_cmd = f"docker exec -d {server_container} sh -c 'nc -u -l -p {port} > /tmp/nc_received'"
    subprocess.run(receiver_cmd, shell=True, check=True)

    # Give receiver time to start
    time.sleep(2)

    # Calculate total packets to send based on target bandwidth
    # target_bandwidth_mbps = (packets_per_sec × packet_size_bytes × 8) / 1e6
    # packets_per_sec = (target_bandwidth_mbps × 1e6) / (packet_size_bytes × 8)
    packets_per_sec = (target_bandwidth_mbps * 1e6) / (packet_size_bytes * 8)
    total_packets = int(packets_per_sec * duration_sec)

    print(f"Sending {total_packets:,} packets ({packet_size_bytes} bytes each)...")

    # Send UDP packets using dd + nc
    # Use -w 1 flag to make nc exit 1 second after stdin closes
    sender_cmd = (
        f"docker exec {client_container} sh -c '"
        f"dd if=/dev/zero bs={packet_size_bytes} count={total_packets} 2>/dev/null | "
        f"nc -u -w 1 {server_ip} {port}'"
    )

    # Start sender in background
    print("Starting sender in background...")
    sender_process = subprocess.Popen(
        sender_cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # Monitor received file size until transmission complete
    bytes_expected = total_packets * packet_size_bytes
    print(f"Monitoring transfer progress (expecting {bytes_expected:,} bytes)...")

    check_interval_sec = 0.5  # Check every 500ms
    max_stall_checks = 6  # No progress for 3 seconds (6 × 0.5s) → done
    max_total_time = 120  # Overall timeout: 120 seconds

    prev_size = 0
    stall_count = 0
    start_time = time.time()

    size_cmd = f"docker exec {server_container} stat -c %s /tmp/nc_received 2>/dev/null || echo 0"

    while True:
        elapsed = time.time() - start_time

        # Check file size
        size_result = subprocess.run(size_cmd, shell=True, capture_output=True, text=True)
        try:
            current_size = int(size_result.stdout.strip())
        except ValueError:
            current_size = 0

        # Print progress
        progress_pct = (current_size / bytes_expected * 100) if bytes_expected > 0 else 0
        print(f"  Progress: {current_size:,} / {bytes_expected:,} bytes ({progress_pct:.1f}%) | Elapsed: {elapsed:.1f}s")

        # Check if transfer complete
        if current_size >= bytes_expected:
            print(f"✓ Transfer complete! Received all {bytes_expected:,} bytes")
            break

        # Check if size stopped changing (sender finished or stalled)
        if current_size == prev_size:
            stall_count += 1
            if stall_count >= max_stall_checks:
                print(f"✓ Transfer finished (no change for {max_stall_checks * check_interval_sec:.1f}s)")
                break
        else:
            stall_count = 0  # Reset stall counter if data is flowing

        prev_size = current_size

        # Overall timeout check
        if elapsed > max_total_time:
            print(f"\nError: Transfer timeout after {max_total_time}s")
            sender_process.kill()
            subprocess.run(kill_cmd_server, shell=True)
            subprocess.run(kill_cmd_client, shell=True)
            raise RuntimeError(f"Transfer timeout: only received {current_size:,} / {bytes_expected:,} bytes")

        # Check if sender process exited
        if sender_process.poll() is not None:
            print("Sender process exited, waiting for final data...")
            time.sleep(1.0)  # Give receiver time to write final data
            # Do one more size check after sender exits
            size_result = subprocess.run(size_cmd, shell=True, capture_output=True, text=True)
            try:
                current_size = int(size_result.stdout.strip())
            except ValueError:
                current_size = prev_size
            break

        time.sleep(check_interval_sec)

    # Clean up sender process if still running
    if sender_process.poll() is None:
        print("Terminating sender process...")
        sender_process.terminate()
        try:
            sender_process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            sender_process.kill()

    bytes_sent = total_packets * packet_size_bytes

    # Kill receiver
    subprocess.run(kill_cmd_server, shell=True)

    # Use the current_size from monitoring loop
    bytes_received = current_size
    print(f"Final received: {bytes_received:,} bytes")

    # Calculate throughput
    if bytes_received == 0:
        print("Error: No data received!")
        raise RuntimeError(
            "No data received - check network connectivity. "
            "This can happen if the forward path also has negative SINR or very high loss."
        )

    # Throughput = (bytes × 8 bits/byte) / (duration × 1e6 bits/Mbit)
    throughput_mbps = (bytes_received * 8) / (duration_sec * 1e6)

    # Calculate packet loss (sent vs received)
    bytes_sent = total_packets * packet_size_bytes
    loss_percent = ((bytes_sent - bytes_received) / bytes_sent) * 100 if bytes_sent > 0 else 0.0

    print(f"\nResults:")
    print(f"  Bytes sent: {bytes_sent:,} ({bytes_sent / 1e6:.2f} MB)")
    print(f"  Bytes received: {bytes_received:,} ({bytes_received / 1e6:.2f} MB)")
    print(f"  Packet loss: {loss_percent:.2f}%")
    print(f"  Duration: {duration_sec}s")
    print(f"  Throughput: {throughput_mbps:.2f} Mbps")
    print(f"{'='*70}\n")

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


def verify_selective_ping_connectivity(
    container_prefix: str,
    node_ips: dict[str, str],
    expected_success: list[tuple[str, str]] | None = None,
    expected_failure: list[tuple[str, str]] | None = None,
) -> None:
    """Test selective ping connectivity between nodes.

    Args:
        container_prefix: Docker container name prefix (e.g., "clab-mylab")
        node_ips: Dictionary mapping node names to IP addresses
        expected_success: List of (src_node, dst_node) tuples expected to succeed
        expected_failure: List of (src_node, dst_node) tuples expected to fail

    Raises:
        AssertionError: If expected successes fail OR expected failures succeed
    """
    print(f"\n{'='*70}")
    print("Testing selective ping connectivity")
    print(f"{'='*70}\n")

    # Test expected successes
    if expected_success:
        print("Testing links expected to SUCCEED:")
        for src_node, dst_node in expected_success:
            src_container = f"{container_prefix}-{src_node}"
            dst_ip = node_ips[dst_node]

            print(f"  {src_node} -> {dst_node} ({dst_ip})...", end=" ")

            cmd = f"docker exec {src_container} ping -c 3 -W 2 {dst_ip}"
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True
            )

            if result.returncode == 0:
                print("✓ SUCCESS (as expected)")
            else:
                print("✗ FAILED (unexpected!)")
                raise AssertionError(
                    f"Ping unexpectedly failed: {src_node} -> {dst_node} ({dst_ip})\n"
                    f"This link was expected to succeed (positive SINR).\n"
                    f"Output: {result.stdout}\n{result.stderr}"
                )

    # Test expected failures
    if expected_failure:
        print("\nTesting links expected to FAIL (negative SINR):")
        for src_node, dst_node in expected_failure:
            src_container = f"{container_prefix}-{src_node}"
            dst_ip = node_ips[dst_node]

            print(f"  {src_node} -> {dst_node} ({dst_ip})...", end=" ")

            cmd = f"docker exec {src_container} ping -c 3 -W 2 {dst_ip}"
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True
            )

            if result.returncode != 0:
                print("✓ FAILED (as expected, negative SINR)")
            else:
                print("✗ SUCCESS (unexpected!)")
                raise AssertionError(
                    f"Ping unexpectedly succeeded: {src_node} -> {dst_node} ({dst_ip})\n"
                    f"This link was expected to fail due to negative SINR.\n"
                    f"Check SINR computation or link parameters."
                )

    print(f"\n{'='*70}")
    print("Selective ping tests passed!")
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


def force_kill_port_occupants(port: int) -> bool:
    """Forcibly kill any processes using the specified port.

    Args:
        port: Port number to free

    Returns:
        True if any processes were killed, False if port was already free
    """
    import shutil

    # Check if lsof is available
    if not shutil.which("lsof"):
        print(f"Warning: lsof not found, cannot force-kill port {port} occupants")
        return False

    try:
        # Find PIDs using the port
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0 and result.stdout.strip():
            pids = result.stdout.strip().split("\n")
            print(f"Found {len(pids)} process(es) using port {port}: {', '.join(pids)}")

            # Kill each PID
            for pid in pids:
                try:
                    subprocess.run(["kill", "-9", pid], timeout=2)
                    print(f"  ✓ Killed PID {pid}")
                except subprocess.TimeoutExpired:
                    print(f"  ✗ Failed to kill PID {pid} (timeout)")
                except subprocess.CalledProcessError as e:
                    print(f"  ✗ Failed to kill PID {pid}: {e}")

            # Wait a moment for ports to be released
            time.sleep(0.5)
            return True
        else:
            # No processes found or lsof returned error (port likely free)
            return False

    except subprocess.TimeoutExpired:
        print(f"Warning: lsof timed out while checking port {port}")
        return False
    except Exception as e:
        print(f"Warning: Error while force-killing port {port} occupants: {e}")
        return False


def wait_for_port_available(
    port: int, timeout_seconds: int = 10, force_kill: bool = False
) -> None:
    """Wait for a port to become available.

    Args:
        port: Port number to check
        timeout_seconds: Maximum time to wait in seconds
        force_kill: If True, attempt to kill processes using the port before waiting

    Raises:
        RuntimeError: If port is still in use after timeout
    """
    import socket

    print(f"Waiting for port {port} to be available...")

    # Optionally force-kill processes on the port first
    if force_kill:
        print(f"Attempting to force-kill processes on port {port}...")
        killed = force_kill_port_occupants(port)
        if killed:
            print(f"Force-killed processes on port {port}, waiting for port release...")
            time.sleep(1)  # Give OS time to release the port

    for attempt in range(timeout_seconds):
        try:
            # Try to bind to the port to check if it's available
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('0.0.0.0', port))
                print(f"✓ Port {port} is available")
                return
        except OSError as exc:
            if attempt < timeout_seconds - 1:
                print(
                    f"  Port {port} in use, waiting... "
                    f"(attempt {attempt + 1}/{timeout_seconds})"
                )
                time.sleep(1)
            else:
                print(f"✗ Port {port} still in use after {timeout_seconds} seconds")
                raise RuntimeError(
                    f"Port {port} is in use by another process. "
                    f"Please kill it manually:\n  lsof -ti :{port} | xargs kill -9"
                ) from exc


@pytest.fixture(scope="session")
def channel_server():
    """Start channel server for tests, stop after all tests complete.

    This is a session-scoped fixture that starts the channel server once
    at the beginning of the test session and stops it at the end.

    Handles Ctrl+C gracefully via registered cleanup handlers.

    Yields:
        Server URL (http://localhost:8000)
    """
    global _channel_server_process

    # DEFENSIVE FIX: Check if server already running (pytest sometimes double-enters session fixtures)
    # Each test can still use different scenes - server reloads via /scene/load endpoint
    if _channel_server_process is not None and _channel_server_process.poll() is None:
        print("\n" + "="*70)
        print("Channel server already running, reusing existing instance")
        print(f"✓ Server PID: {_channel_server_process.pid}")
        print("  (Different scenes/configs handled via /scene/load endpoint)")
        print("="*70 + "\n")
        yield "http://localhost:8000"
        # Early return - don't run cleanup since server is shared
        return

    uv_path = get_uv_path()

    # Register cleanup handlers (will handle Ctrl+C)
    _register_cleanup_handlers()

    # Wait for port 8000 to be available (from previous run shutdown)
    print("\n" + "="*70)
    print("CHANNEL SERVER STARTUP (session-scoped fixture)")
    print(f"DEBUG: Starting new server at {time.time()}")
    print("="*70 + "\n")
    wait_for_port_available(8000, timeout_seconds=15, force_kill=True)
    print()

    # Start channel server in background
    logger.info("Starting channel server...")

    process = subprocess.Popen(
        [uv_path, "run", "sine", "channel-server"],
        # stdout and stderr will go to the test output (not piped)
    )

    # Track process for emergency cleanup
    _channel_server_process = process

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
                _channel_server_process = None
                raise RuntimeError("Channel server failed to start")

    try:
        yield server_url
    finally:
        # Normal cleanup: stop channel server
        logger.info("Stopping channel server...")
        print("\n" + "="*70)
        print("Stopping channel server (normal shutdown)...")
        print(f"DEBUG: Fixture cleanup being called at {time.time()}")
        print(f"DEBUG: process.poll() = {process.poll()}")
        print("="*70 + "\n")

        if process.poll() is None:  # Check if still running
            process.terminate()
            try:
                process.wait(timeout=5)
                print("✓ Channel server stopped")
            except subprocess.TimeoutExpired:
                print("Channel server didn't stop gracefully, killing...")
                process.kill()
                process.wait()
                print("✓ Channel server killed")

        # Force-kill any lingering processes on port 8000
        print("Checking for lingering processes on port 8000...")
        force_kill_port_occupants(8000)

        # Wait for port to be released (important for next test session)
        print("Waiting for port 8000 to be released...")
        wait_for_port_available(8000, timeout_seconds=15, force_kill=True)
        print("✓ Port 8000 is now available")

        # Clear tracking (already cleaned up)
        _channel_server_process = None


@pytest.fixture(scope="session")
def channel_server_fallback():
    """Start channel server in fallback mode for tests.

    This is a session-scoped fixture that starts the channel server once
    with --force-fallback flag for testing fallback engine without GPU.

    Yields:
        Server URL (http://localhost:8001)
    """
    uv_path = get_uv_path()

    # Wait for port 8001 to be available (from previous run shutdown)
    print("\n" + "="*70)
    print("CHANNEL SERVER STARTUP (FALLBACK MODE)")
    print(f"DEBUG: Starting fallback server at {time.time()}")
    print("="*70 + "\n")
    wait_for_port_available(8001, timeout_seconds=15, force_kill=True)
    print()

    # Start channel server in background with --force-fallback
    logger.info("Starting channel server in fallback mode...")

    process = subprocess.Popen(
        [uv_path, "run", "sine", "channel-server", "--force-fallback", "--port", "8001"],
        # stdout and stderr will go to the test output (not piped)
    )

    # Wait for server to be ready (check health endpoint)
    server_url = "http://localhost:8001"
    max_retries = 30

    for i in range(max_retries):
        try:
            with urllib.request.urlopen(f"{server_url}/health", timeout=1) as response:
                if response.status == 200:
                    logger.info(f"Channel server ready at {server_url} (fallback mode)")
                    print(f"✓ Channel server is ready at {server_url} (fallback mode)")
                    print("="*70 + "\n")
                    break
        except (urllib.error.URLError, OSError):
            if i < max_retries - 1:
                time.sleep(1)
            else:
                process.kill()
                raise RuntimeError("Channel server failed to start in fallback mode")

    yield server_url

    # Cleanup: stop channel server
    logger.info("Stopping channel server (fallback mode)...")
    print("\n" + "="*70)
    print("Stopping channel server (fallback mode)...")
    print(f"DEBUG: Fixture cleanup being called at {time.time()}")
    print(f"DEBUG: process.poll() = {process.poll()}")
    print("="*70 + "\n")

    # Check if process is still running before attempting termination
    if process.poll() is None:  # Still running
        process.terminate()
        try:
            process.wait(timeout=5)
            print("✓ Channel server (fallback) stopped gracefully")
        except subprocess.TimeoutExpired:
            print("Channel server (fallback) didn't stop gracefully, killing...")
            process.kill()
            process.wait()
            print("✓ Channel server (fallback) killed")
    else:
        print("Channel server (fallback) already stopped")

    # Force-kill any lingering processes on port 8001 (e.g., mobility API from tests)
    print("Checking for lingering processes on port 8001...")
    force_kill_port_occupants(8001)

    # Wait for port to be released (important for next test session)
    print("Waiting for port 8001 to be released...")
    wait_for_port_available(8001, timeout_seconds=15, force_kill=True)
    print("✓ Port 8001 is now available")


@pytest.fixture
def bridge_node_ips() -> dict[str, str]:
    """Standard shared bridge node IPs (192.168.100.x/24).

    Returns:
        Dictionary mapping node names to IP addresses for shared bridge topology
    """
    return {
        "node1": "192.168.100.1",
        "node2": "192.168.100.2",
        "node3": "192.168.100.3",
    }


@pytest.fixture
def p2p_node_ips() -> dict[str, str]:
    """Standard P2P node IPs.

    Returns:
        Dictionary mapping node names to IP addresses for P2P topology
    """
    return {
        "node1": "10.0.0.1",
        "node2": "10.0.0.2",
    }


# =============================================================================
# YAML Config Modification Helpers
# =============================================================================


def modify_topology_mcs(
    source_yaml: Path,
    modulation: str | None = None,
    fec_type: str | None = None,
    fec_code_rate: float | None = None,
    tx_power_dbm: float | None = None,
) -> dict:
    """Create a modified copy of a topology with different MCS settings.

    Returns the modified config as a dict. Tests can write this to a temporary
    file if needed. Modifies all wireless interfaces in the topology.

    Args:
        source_yaml: Path to source network.yaml
        modulation: Optional modulation to set (e.g., "bpsk", "qpsk", "64qam")
        fec_type: Optional FEC type to set (e.g., "ldpc", "polar", "turbo")
        fec_code_rate: Optional FEC code rate to set (e.g., 0.5, 0.75)
        tx_power_dbm: Optional TX power to set (e.g., 20.0, 30.0)

    Returns:
        Modified topology config as dict

    Example:
        >>> # Test with BPSK for low-SINR scenarios
        >>> config = modify_topology_mcs(
        ...     source_yaml=Path("examples/for_tests/shared_sionna_sinr_equal-triangle/network.yaml"),
        ...     modulation="bpsk",
        ...     fec_type="ldpc",
        ...     fec_code_rate=0.5,
        ... )
        >>> # Write to temp file and deploy
        >>> with open("/tmp/test_bpsk.yaml", "w") as f:
        ...     yaml.dump(config, f)
    """
    import yaml

    # Load source YAML
    with open(source_yaml, "r") as f:
        config = yaml.safe_load(f)

    # Modify all wireless interfaces
    if "topology" in config and "nodes" in config["topology"]:
        for node_name, node_config in config["topology"]["nodes"].items():
            if "interfaces" in node_config:
                for iface_name, iface_config in node_config["interfaces"].items():
                    if "wireless" in iface_config:
                        wireless = iface_config["wireless"]

                        # Update MCS parameters
                        if modulation is not None:
                            wireless["modulation"] = modulation
                        if fec_type is not None:
                            wireless["fec_type"] = fec_type
                        if fec_code_rate is not None:
                            wireless["fec_code_rate"] = fec_code_rate
                        if tx_power_dbm is not None:
                            wireless["rf_power_dbm"] = tx_power_dbm

    logger.info(f"Modified topology MCS settings: modulation={modulation}, fec={fec_type}, rate={fec_code_rate}, tx_power={tx_power_dbm} dBm")

    return config


def modify_topology_wireless(
    source_yaml: Path,
    frequency_ghz: float | None = None,
    rf_power_dbm: float | None = None,
    bandwidth_mhz: int | None = None,
    noise_figure_db: float | None = None,
    is_active: bool | None = None,
) -> dict:
    """Modify wireless parameters in a topology YAML.

    Similar to modify_topology_mcs but for RF parameters.
    Returns modified config as dict (caller writes to temp file).

    Args:
        source_yaml: Path to source network.yaml
        frequency_ghz: Optional frequency in GHz (e.g., 2.4, 5.18)
        rf_power_dbm: Optional TX power in dBm (e.g., 5, 20, 30)
        bandwidth_mhz: Optional bandwidth in MHz (e.g., 20, 40, 80, 160)
        noise_figure_db: Optional noise figure in dB (e.g., 6.0, 7.0, 10.0)
        is_active: Optional active state (True/False)

    Returns:
        Modified topology config as dict

    Example:
        >>> # Test different frequency bands
        >>> config = modify_topology_wireless(
        ...     source_yaml=Path("examples/for_tests/shared_sionna_snr_equal-triangle/network.yaml"),
        ...     frequency_ghz=2.4,
        ...     bandwidth_mhz=20,
        ... )
    """
    import yaml

    # Load source YAML
    with open(source_yaml, "r") as f:
        config = yaml.safe_load(f)

    # Modify all wireless interfaces
    if "topology" in config and "nodes" in config["topology"]:
        for node_name, node_config in config["topology"]["nodes"].items():
            if "interfaces" in node_config:
                for iface_name, iface_config in node_config["interfaces"].items():
                    if "wireless" in iface_config:
                        wireless = iface_config["wireless"]

                        # Update wireless parameters
                        if frequency_ghz is not None:
                            wireless["frequency_ghz"] = frequency_ghz
                        if rf_power_dbm is not None:
                            wireless["rf_power_dbm"] = rf_power_dbm
                        if bandwidth_mhz is not None:
                            wireless["bandwidth_mhz"] = bandwidth_mhz
                        if noise_figure_db is not None:
                            wireless["noise_figure_db"] = noise_figure_db
                        if is_active is not None:
                            wireless["is_active"] = is_active

    logger.info(f"Modified wireless parameters: freq={frequency_ghz} GHz, power={rf_power_dbm} dBm, bw={bandwidth_mhz} MHz, nf={noise_figure_db} dB, active={is_active}")

    return config


def modify_topology_antenna(
    source_yaml: Path,
    antenna_gain_dbi: float | None = None,
    antenna_pattern: str | None = None,
    polarization: str | None = None,
) -> dict:
    """Modify antenna parameters in a topology YAML.

    Note: antenna_gain_dbi and antenna_pattern are mutually exclusive.
    Returns modified config as dict.

    Args:
        source_yaml: Path to source network.yaml
        antenna_gain_dbi: Optional antenna gain in dBi (e.g., 0.0, 2.15, 3.0)
        antenna_pattern: Optional pattern ("iso", "dipole", "hw_dipole", "tr38901")
        polarization: Optional polarization ("V", "H", "VH", "cross")

    Returns:
        Modified topology config as dict

    Raises:
        ValueError: If both antenna_gain_dbi and antenna_pattern are specified

    Example:
        >>> # Test with different antenna types
        >>> config = modify_topology_antenna(
        ...     source_yaml=Path("examples/for_tests/shared_sionna_snr_equal-triangle/network.yaml"),
        ...     antenna_pattern="iso",
        ...     polarization="V",
        ... )
    """
    import yaml

    if antenna_gain_dbi is not None and antenna_pattern is not None:
        raise ValueError("Cannot specify both antenna_gain_dbi and antenna_pattern")

    # Load source YAML
    with open(source_yaml, "r") as f:
        config = yaml.safe_load(f)

    # Modify all wireless interfaces
    if "topology" in config and "nodes" in config["topology"]:
        for node_name, node_config in config["topology"]["nodes"].items():
            if "interfaces" in node_config:
                for iface_name, iface_config in node_config["interfaces"].items():
                    if "wireless" in iface_config:
                        wireless = iface_config["wireless"]

                        # Update antenna parameters
                        if antenna_gain_dbi is not None:
                            # Remove antenna_pattern if present
                            wireless.pop("antenna_pattern", None)
                            wireless["antenna_gain_dbi"] = antenna_gain_dbi
                        elif antenna_pattern is not None:
                            # Remove antenna_gain_dbi if present
                            wireless.pop("antenna_gain_dbi", None)
                            wireless["antenna_pattern"] = antenna_pattern

                        if polarization is not None:
                            wireless["polarization"] = polarization

    logger.info(f"Modified antenna parameters: gain={antenna_gain_dbi} dBi, pattern={antenna_pattern}, pol={polarization}")

    return config
