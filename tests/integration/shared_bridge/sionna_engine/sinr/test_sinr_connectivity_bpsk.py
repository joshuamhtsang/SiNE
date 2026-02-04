"""Integration test for SINR connectivity with BPSK modulation.

Tests low-SINR scenarios (co-channel interference) using BPSK modulation,
which is more robust than higher-order modulations like 64-QAM.
"""

import pytest
import tempfile
import yaml
from pathlib import Path
from tests.integration.fixtures import (
    channel_server,
    deploy_topology,
    destroy_topology,
    stop_deployment_process,
    verify_ping_connectivity,
    modify_topology_mcs,
)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
@pytest.mark.xfail(
    reason="Even BPSK cannot handle SINR = 0 dB. Effective SNR with LDPC = 6.5 dB, "
           "BER ≈ 0.0014, PER ≈ 100% for 12000-bit packets. Need SINR ≥ 5-10 dB minimum."
)
def test_sinr_triangle_connectivity_bpsk(channel_server, examples_for_tests: Path):
    """Test all-to-all ping connectivity with BPSK in low-SINR scenario.

    **EXPECTED TO FAIL**: Uses the equilateral triangle topology with co-channel
    interference, which produces SINR ≈ 0 dB. Even BPSK with LDPC cannot reliably
    handle this low SINR.

    Analysis:
    - SINR = 0 dB (signal = interference)
    - LDPC coding gain = 6.5 dB
    - Effective SNR = 6.5 dB
    - BPSK BER ≈ 0.0014 at 6.5 dB
    - PER ≈ 100% for 12000-bit packets
    - Need SINR ≥ 5-10 dB for reliable BPSK

    Topology:
    - 3 nodes in equilateral triangle (30m sides)
    - Co-channel interference (all nodes at 5.18 GHz)
    - SINR ≈ 0 dB (worst-case: signal = interference)
    - Modulation: BPSK with LDPC rate-1/2
    """
    source_yaml = examples_for_tests / "shared_sionna_sinr_triangle" / "network.yaml"

    if not source_yaml.exists():
        pytest.skip(f"Example not found: {source_yaml}")

    # Modify topology to use BPSK instead of 64-QAM
    modified_config = modify_topology_mcs(
        source_yaml=source_yaml,
        modulation="bpsk",
        fec_type="ldpc",
        fec_code_rate=0.5,
    )

    # Write to temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(modified_config, f, default_flow_style=False, sort_keys=False)
        temp_yaml = Path(f.name)

    deploy_process = None
    try:
        # Deploy with BPSK topology
        deploy_process = deploy_topology(str(temp_yaml))

        node_ips = {
            "node1": "192.168.100.1",
            "node2": "192.168.100.2",
            "node3": "192.168.100.3",
        }

        # Verify connectivity works with BPSK
        verify_ping_connectivity("clab-manet-triangle-shared-sinr", node_ips)

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(temp_yaml))
        temp_yaml.unlink(missing_ok=True)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.sionna
@pytest.mark.xfail(
    reason="QPSK also cannot handle SINR = 0 dB. Need SINR ≥ 8-12 dB for QPSK."
)
def test_sinr_triangle_connectivity_qpsk(channel_server, examples_for_tests: Path):
    """Test all-to-all ping connectivity with QPSK in low-SINR scenario.

    **EXPECTED TO FAIL**: Uses QPSK as a middle ground between BPSK and 64-QAM,
    but still cannot handle SINR = 0 dB.

    Expected: QPSK should handle low SINR better than 64-QAM but worse than BPSK.
    However, SINR = 0 dB is too low for any practical modulation.
    """
    source_yaml = examples_for_tests / "shared_sionna_sinr_triangle" / "network.yaml"

    if not source_yaml.exists():
        pytest.skip(f"Example not found: {source_yaml}")

    # Modify topology to use QPSK
    modified_config = modify_topology_mcs(
        source_yaml=source_yaml,
        modulation="qpsk",
        fec_type="ldpc",
        fec_code_rate=0.5,
    )

    # Write to temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(modified_config, f, default_flow_style=False, sort_keys=False)
        temp_yaml = Path(f.name)

    deploy_process = None
    try:
        # Deploy with QPSK topology
        deploy_process = deploy_topology(str(temp_yaml))

        node_ips = {
            "node1": "192.168.100.1",
            "node2": "192.168.100.2",
            "node3": "192.168.100.3",
        }

        # Verify connectivity
        verify_ping_connectivity("clab-manet-triangle-shared-sinr", node_ips)

    finally:
        stop_deployment_process(deploy_process)
        destroy_topology(str(temp_yaml))
        temp_yaml.unlink(missing_ok=True)
