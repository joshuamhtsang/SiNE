"""Integration tests for asymmetric noise figure routing.

Tests routing configuration with heterogeneous receivers.
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
def test_asymmetric_nf_routing(channel_server, examples_for_tests: Path):
    """Verify routing with heterogeneous noise figures.

    Validates that:
    - Routes to bridge subnet are configured correctly
    - Heterogeneous NF values don't affect routing setup
    - All nodes use eth1 for bridge subnet traffic

    Topology has nodes with different noise figures:
    - node1: 7.0 dB (WiFi 6)
    - node2: 10.0 dB (cheap IoT)
    - node3: 5.0 dB (high-end BS)
    """
    yaml_path = examples_for_tests / "shared_sionna_snr_asymmetric-nf" / "network.yaml"

    if not yaml_path.exists():
        pytest.skip(f"Example not found: {yaml_path}")

    destroy_topology(str(yaml_path))

    deploy_process = None
    try:
        deploy_process = deploy_topology(str(yaml_path))

        # Verify routes on all nodes regardless of NF
        for node in ["node1", "node2", "node3"]:
            verify_route_to_cidr(
                "clab-manet-triangle-shared-asymmetric-nf",
                node,
                "192.168.100.0/24",
                "eth1"
            )

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(yaml_path))
