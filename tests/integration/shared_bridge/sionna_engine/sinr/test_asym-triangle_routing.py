"""Integration tests for asym-triangle routing configuration.

Tests that shared bridge routing is correctly configured for the asymmetric
triangle topology, even for nodes with no active link connectivity.
"""

import pytest
from pathlib import Path
from tests.integration.fixtures import (
    channel_server,
    deploy_topology,
    destroy_topology,
    extract_container_prefix,
    stop_deployment_process,
    verify_route_to_cidr,
)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
def test_sinr_asym_triangle_routing(channel_server, examples_for_tests: Path):
    """Verify routes to bridge subnet on eth1 for all nodes.

    Validates that:
    - Each node has a route to the bridge subnet (192.168.100.0/24)
    - Routes use eth1 (not the default Docker eth0)
    - Routing is correct even for node3, which has negative SINR and no
      active connectivity to node1 or node2

    Key assertion: Routing infrastructure is independent of link quality.
    Even nodes that cannot communicate due to negative SINR have their
    routes correctly configured.
    """
    yaml_path = examples_for_tests / "shared_sionna_sinr_asym-triangle" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        container_prefix = extract_container_prefix(str(yaml_path))

        # Verify routes on all three nodes, including node3 (negative SINR, no connectivity)
        for node in ["node1", "node2", "node3"]:
            verify_route_to_cidr(
                container_prefix,
                node,
                "192.168.100.0/24",
                "eth1",
            )

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))
