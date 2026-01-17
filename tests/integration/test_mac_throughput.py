"""
Integration tests for CSMA and TDMA throughput validation.

These tests deploy example topologies and measure actual iperf3 throughput
to validate that:
1. CSMA achieves 80-90% throughput via spatial reuse
2. TDMA fixed slots achieve throughput matching slot ownership (20%)
3. TDMA round-robin achieves throughput matching slot ownership (33.3%)
4. CSMA is 4-5× faster than TDMA for the same PHY configuration

Requirements:
- sudo access for netem configuration
- containerlab installed
- iperf3 installed in container images
"""

import logging
import subprocess
import time
from pathlib import Path

import pytest

logger = logging.getLogger(__name__)


def deploy_topology(yaml_path: str) -> dict:
    """
    Deploy a topology using sine CLI.

    Args:
        yaml_path: Path to topology YAML file

    Returns:
        Dictionary with deployment information
    """
    result = subprocess.run(
        ["sudo", "uv", "run", "sine", "deploy", yaml_path],
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        logger.error(f"Deploy failed: {result.stderr}")
        raise RuntimeError(f"Failed to deploy {yaml_path}: {result.stderr}")

    logger.info(f"Deployed {yaml_path}")
    return {"stdout": result.stdout, "stderr": result.stderr}


def destroy_topology(yaml_path: str) -> None:
    """
    Destroy a topology using sine CLI.

    Args:
        yaml_path: Path to topology YAML file
    """
    result = subprocess.run(
        ["sudo", "uv", "run", "sine", "destroy", yaml_path],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        logger.warning(f"Destroy failed: {result.stderr}")
    else:
        logger.info(f"Destroyed {yaml_path}")


def configure_ips(container_prefix: str, node_ips: dict[str, str]) -> None:
    """
    Configure IP addresses on container interfaces.

    Args:
        container_prefix: Container name prefix (e.g., "clab-sinr-csma-wifi6")
        node_ips: Dictionary {node_name: ip_address}
    """
    for node_name, ip_addr in node_ips.items():
        container_name = f"{container_prefix}-{node_name}"
        cmd = f"docker exec {container_name} ip addr add {ip_addr}/24 dev eth1"
        subprocess.run(cmd, shell=True, capture_output=True, timeout=10)
        logger.debug(f"Configured {container_name}:eth1 = {ip_addr}")


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

    # Start iperf3 server in background
    server_cmd = f"docker exec -d {server_container} iperf3 -s"
    subprocess.run(server_cmd, shell=True, timeout=10)
    time.sleep(2)  # Give server time to start

    # Run iperf3 client
    client_cmd = (
        f"docker exec {client_container} iperf3 -c {client_ip} "
        f"-t {duration_sec} -J"
    )
    result = subprocess.run(
        client_cmd, shell=True, capture_output=True, text=True, timeout=duration_sec + 10
    )

    if result.returncode != 0:
        logger.error(f"iperf3 client failed: {result.stderr}")
        raise RuntimeError(f"iperf3 test failed: {result.stderr}")

    # Parse JSON output to extract throughput
    import json

    iperf_data = json.loads(result.stdout)
    throughput_bps = iperf_data["end"]["sum_received"]["bits_per_second"]
    throughput_mbps = throughput_bps / 1e6

    logger.info(f"Measured throughput: {throughput_mbps:.1f} Mbps")

    # Kill iperf3 server
    kill_cmd = f"docker exec {server_container} pkill iperf3"
    subprocess.run(kill_cmd, shell=True, timeout=10)

    return throughput_mbps


@pytest.fixture
def examples_dir() -> Path:
    """Return path to examples directory."""
    return Path(__file__).parent.parent.parent / "examples"


@pytest.mark.integration
@pytest.mark.slow
def test_csma_throughput_spatial_reuse(examples_dir: Path):
    """
    Test CSMA achieves 80-90% throughput via spatial reuse.

    Expected: ~400-450 Mbps (80-90% of 480 Mbps PHY rate)
    """
    yaml_path = examples_dir / "sinr_csma_example.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    try:
        # Deploy
        deploy_topology(str(yaml_path))

        # Configure IPs
        configure_ips(
            "clab-sinr-csma-wifi6",
            {
                "node1": "192.168.1.1",
                "node2": "192.168.1.2",
            },
        )

        # Run iperf3 test
        throughput = run_iperf3_test(
            container_prefix="clab-sinr-csma-wifi6",
            server_node="node1",
            client_node="node2",
            client_ip="192.168.1.1",
            duration_sec=30,
        )

        # Validate: 80-90% of 480 Mbps PHY
        assert 400 <= throughput <= 450, (
            f"CSMA throughput {throughput:.1f} Mbps not in expected range "
            f"[400-450 Mbps] (80-90% spatial reuse)"
        )

    finally:
        # Cleanup
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
def test_tdma_fixed_throughput_matches_slot_ownership(examples_dir: Path):
    """
    Test TDMA fixed slots achieve expected throughput.

    Expected: ~90-96 Mbps (95-99% of 96 Mbps, 20% slot ownership × 480 Mbps PHY)
    """
    yaml_path = examples_dir / "sinr_tdma_fixed" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    try:
        # Deploy
        deploy_topology(str(yaml_path))

        # Configure IPs
        configure_ips(
            "clab-sinr-tdma-fixed",
            {
                "node1": "192.168.1.1",
                "node2": "192.168.1.2",
            },
        )

        # Run iperf3 test
        throughput = run_iperf3_test(
            container_prefix="clab-sinr-tdma-fixed",
            server_node="node1",
            client_node="node2",
            client_ip="192.168.1.1",
            duration_sec=30,
        )

        # Validate: 95-99% of 96 Mbps (20% slot ownership)
        assert 90 <= throughput <= 96, (
            f"TDMA fixed throughput {throughput:.1f} Mbps not in expected range "
            f"[90-96 Mbps] (20% slot ownership)"
        )

    finally:
        # Cleanup
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
def test_tdma_roundrobin_throughput(examples_dir: Path):
    """
    Test TDMA round-robin gives equal throughput per node.

    Expected: ~152-160 Mbps (95-100% of 160 Mbps, 33.3% slot ownership × 480 Mbps PHY)
    """
    yaml_path = examples_dir / "sinr_tdma_roundrobin" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    try:
        # Deploy
        deploy_topology(str(yaml_path))

        # Configure IPs
        configure_ips(
            "clab-sinr-tdma-roundrobin",
            {
                "node1": "192.168.1.1",
                "node2": "192.168.1.2",
            },
        )

        # Run iperf3 test
        throughput = run_iperf3_test(
            container_prefix="clab-sinr-tdma-roundrobin",
            server_node="node1",
            client_node="node2",
            client_ip="192.168.1.1",
            duration_sec=30,
        )

        # Validate: 95-100% of 160 Mbps (33.3% slot ownership)
        assert 152 <= throughput <= 160, (
            f"TDMA round-robin throughput {throughput:.1f} Mbps not in expected range "
            f"[152-160 Mbps] (33.3% slot ownership)"
        )

    finally:
        # Cleanup
        destroy_topology(str(yaml_path))


@pytest.mark.integration
@pytest.mark.slow
def test_csma_vs_tdma_ratio(examples_dir: Path):
    """
    Test CSMA is 4-5× faster than TDMA for same PHY.

    This validates that CSMA spatial reuse provides significant throughput
    advantage over TDMA deterministic scheduling.
    """
    csma_yaml = examples_dir / "sinr_csma_example.yaml"
    tdma_yaml = examples_dir / "sinr_tdma_fixed" / "network.yaml"

    if not csma_yaml.exists() or not tdma_yaml.exists():
        pytest.skip("Required examples not found")

    csma_throughput = None
    tdma_throughput = None

    try:
        # Test CSMA
        deploy_topology(str(csma_yaml))
        configure_ips(
            "clab-sinr-csma-wifi6",
            {"node1": "192.168.1.1", "node2": "192.168.1.2"},
        )
        csma_throughput = run_iperf3_test(
            container_prefix="clab-sinr-csma-wifi6",
            server_node="node1",
            client_node="node2",
            client_ip="192.168.1.1",
            duration_sec=30,
        )
        destroy_topology(str(csma_yaml))

        # Test TDMA
        deploy_topology(str(tdma_yaml))
        configure_ips(
            "clab-sinr-tdma-fixed",
            {"node1": "192.168.1.1", "node2": "192.168.1.2"},
        )
        tdma_throughput = run_iperf3_test(
            container_prefix="clab-sinr-tdma-fixed",
            server_node="node1",
            client_node="node2",
            client_ip="192.168.1.1",
            duration_sec=30,
        )

        # Compute ratio
        ratio = csma_throughput / tdma_throughput

        logger.info(
            f"CSMA: {csma_throughput:.1f} Mbps, "
            f"TDMA: {tdma_throughput:.1f} Mbps, "
            f"Ratio: {ratio:.2f}×"
        )

        # Validate: CSMA should be 4-5× faster
        assert 4.0 <= ratio <= 5.0, (
            f"CSMA/TDMA ratio {ratio:.2f}× not in expected range [4.0-5.0×]"
        )

    finally:
        # Cleanup
        if csma_yaml:
            destroy_topology(str(csma_yaml))
        if tdma_yaml:
            destroy_topology(str(tdma_yaml))


if __name__ == "__main__":
    # Run tests manually for debugging
    import sys

    logging.basicConfig(level=logging.INFO)

    examples = Path(__file__).parent.parent.parent / "examples"

    print("=" * 80)
    print("CSMA Throughput Test")
    print("=" * 80)
    test_csma_throughput_spatial_reuse(examples)

    print("\n" + "=" * 80)
    print("TDMA Fixed Throughput Test")
    print("=" * 80)
    test_tdma_fixed_throughput_matches_slot_ownership(examples)

    print("\n" + "=" * 80)
    print("TDMA Round-Robin Throughput Test")
    print("=" * 80)
    test_tdma_roundrobin_throughput(examples)

    print("\n" + "=" * 80)
    print("CSMA vs TDMA Ratio Test")
    print("=" * 80)
    test_csma_vs_tdma_ratio(examples)

    print("\n" + "=" * 80)
    print("All tests passed!")
    print("=" * 80)
