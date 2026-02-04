"""Integration tests for SINR routing configuration.

Tests that shared bridge routing is correctly configured for SINR topologies.
"""

import pytest
from pathlib import Path
from tests.integration.fixtures import (
    channel_server,
    deploy_topology,
    destroy_topology,
    stop_deployment_process,
    verify_route_to_cidr,
)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_sinr_triangle_routing(channel_server, examples_for_tests: Path):
    """Verify routes to bridge subnet on eth1.

    Validates that:
    - Each node has a route to the bridge subnet (192.168.100.0/24)
    - Routes use the correct interface (eth1, not eth0)
    - Routing configuration is compatible with SINR computation
    """
    yaml_path = examples_for_tests / "shared_sionna_sinr_triangle" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Verify routes on all nodes
        for node in ["node1", "node2", "node3"]:
            verify_route_to_cidr(
                "clab-manet-triangle-shared-sinr",
                node,
                "192.168.100.0/24",
                "eth1"
            )

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))
