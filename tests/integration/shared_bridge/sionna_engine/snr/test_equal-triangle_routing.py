"""
Integration tests for MANET shared bridge routing configuration.

These tests verify that routing tables are correctly configured for the shared bridge topology.

Requirements:
- Channel server running (automatically started by test fixture)
- sudo access for netem configuration
- containerlab installed

Running these tests:
    UV_PATH=$(which uv) sudo -E pytest -s tests/integration/shared_bridge/sionna_engine/snr/test_manet_routing.py -v
"""

import logging
from pathlib import Path

import pytest

from tests.integration.fixtures import (
    channel_server,
    deploy_topology,
    destroy_topology,
    extract_container_prefix,
    stop_deployment_process,
    verify_route_to_cidr,
)

logger = logging.getLogger(__name__)


# Prevent "imported but unused" warnings - these are pytest fixtures
__all__ = ["channel_server"]


@pytest.mark.integration
def test_manet_shared_bridge_routing(channel_server, examples_for_tests: Path):
    """
    Test MANET shared bridge routing configuration.

    Expected: All nodes have routes to the bridge subnet (192.168.100.0/24) on eth1.
    """
    yaml_path = examples_for_tests / "shared_sionna_snr_equal-triangle" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    # Cleanup any existing deployment first
    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        # Deploy (returns background process)
        deploy_process = deploy_topology(str(yaml_path))

        # Get container prefix from topology
        container_prefix = extract_container_prefix(str(yaml_path))

        # Verify routing for all nodes
        for node in ["node1", "node2", "node3"]:
            verify_route_to_cidr(
                container_prefix,
                node,
                "192.168.100.0/24",
                "eth1"
            )
            logger.info(f"✓ {node}: Route to 192.168.100.0/24 verified on eth1")

        print("\n" + "="*70)
        print("All routing verification tests passed!")
        print("="*70 + "\n")

    finally:
        # Stop deployment process
        stop_deployment_process(deploy_process)
        # Cleanup containers
        destroy_topology(str(yaml_path))


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
