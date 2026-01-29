#!/usr/bin/env python3
"""
Spectral Efficiency Calculator for SiNE

Analyzes network.yaml topologies and computes spectral efficiency metrics
for each wireless link using the channel server.

Usage:
    uv run python utilities/calc_spectralefficiency.py <topology.yaml>
    uv run python utilities/calc_spectralefficiency.py --channel-server http://localhost:8000 <topology.yaml>
"""

import argparse
import math
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from rich.console import Console
from rich.table import Table

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sine.config.loader import load_topology
from sine.config.schema import WirelessParams


@dataclass
class LinkMetrics:
    """Comprehensive metrics for a wireless link"""

    # Link identification
    endpoint1: str  # "node1:eth1"
    endpoint2: str  # "node2:eth1"
    distance_m: float

    # Channel conditions
    path_loss_db: float
    snr_db: float

    # Shannon theoretical
    shannon_capacity_mbps: float
    shannon_spectral_efficiency: float  # b/s/Hz

    # Effective/practical
    effective_rate_mbps: float
    effective_spectral_efficiency: float  # b/s/Hz
    efficiency_category: str  # "High", "Medium", "Low"

    # Link quality metrics
    shannon_gap_db: float  # 10 × log₁₀(Shannon / Effective)
    link_margin_db: float | None  # SNR - min_SNR_for_MCS

    # Error rates
    ber: float
    per: float

    # MCS configuration
    modulation: str
    code_rate: float
    fec_type: str
    bandwidth_mhz: float
    min_snr_db: float | None = None  # For MCS table scenarios

    # Warnings
    warnings: list[str] = field(default_factory=list)


def compute_shannon_capacity(snr_db: float, bandwidth_hz: float) -> dict[str, float]:
    """
    Compute Shannon channel capacity.

    C = BW × log₂(1 + SNR_linear)

    Args:
        snr_db: Signal-to-noise ratio in dB
        bandwidth_hz: Channel bandwidth in Hz

    Returns:
        Dictionary with:
            - capacity_bps: Shannon capacity in bits/sec
            - capacity_mbps: Shannon capacity in Mbps
            - spectral_efficiency_bps_hz: Spectral efficiency in b/s/Hz
    """
    snr_linear = 10 ** (snr_db / 10.0)
    spectral_efficiency = math.log2(1 + snr_linear)  # b/s/Hz
    capacity_bps = bandwidth_hz * spectral_efficiency
    capacity_mbps = capacity_bps / 1e6

    return {
        "capacity_bps": capacity_bps,
        "capacity_mbps": capacity_mbps,
        "spectral_efficiency_bps_hz": spectral_efficiency,
    }


def categorize_spectral_efficiency(spec_eff: float) -> str:
    """
    Categorize spectral efficiency as High, Medium, or Low.

    Reference values:
    - High: ≥4.0 b/s/Hz (excellent WiFi, high SNR >20 dB)
    - Medium: 1.0-4.0 b/s/Hz (typical WiFi, good conditions)
    - Low: <1.0 b/s/Hz (military/tactical, robust modes, poor conditions)

    Args:
        spec_eff: Spectral efficiency in b/s/Hz

    Returns:
        Category string: "High", "Medium", or "Low"
    """
    if spec_eff >= 4.0:
        return "High"
    if spec_eff >= 1.0:
        return "Medium"
    return "Low"


def compute_shannon_gap(shannon_rate_mbps: float, effective_rate_mbps: float) -> float:
    """
    Compute Shannon gap in dB.

    Shannon gap = 10 × log₁₀(Shannon_capacity / Effective_rate)

    This quantifies how far the system is from the theoretical limit.
    Typical values: 3-8 dB (3 dB = 50% efficiency)

    Args:
        shannon_rate_mbps: Shannon capacity in Mbps
        effective_rate_mbps: Actual effective rate in Mbps

    Returns:
        Shannon gap in dB
    """
    if effective_rate_mbps <= 0:
        return float('inf')

    ratio = shannon_rate_mbps / effective_rate_mbps
    return 10 * math.log10(ratio)


def compute_link_margin(snr_db: float, min_snr_db: float | None) -> float | None:
    """
    Compute link margin in dB.

    Link margin = SNR - min_SNR_for_MCS

    Indicates robustness to fading. Higher is better.
    - >10 dB: Excellent margin
    - 3-10 dB: Adequate margin
    - <3 dB: Limited margin for fading

    Args:
        snr_db: Current SNR in dB
        min_snr_db: Minimum SNR required for current MCS (None for fixed MCS)

    Returns:
        Link margin in dB, or None if min_snr_db not available
    """
    if min_snr_db is None:
        return None

    return snr_db - min_snr_db


def generate_warnings(metrics: LinkMetrics) -> list[str]:
    """
    Generate warning messages for unusual conditions.

    Args:
        metrics: LinkMetrics object

    Returns:
        List of warning strings
    """
    warnings = []

    # Shannon gap too large (very conservative MCS)
    if metrics.shannon_gap_db > 10.0:
        warnings.append(f"Very conservative MCS (gap={metrics.shannon_gap_db:.1f} dB)")

    # High packet loss
    if metrics.per > 0.10:  # >10%
        warnings.append(f"High packet loss ({metrics.per*100:.1f}%)")

    # Poor link quality
    if metrics.snr_db < 5.0:
        warnings.append(f"Poor link quality (SNR={metrics.snr_db:.1f} dB)")

    # Limited link margin
    if metrics.link_margin_db is not None and metrics.link_margin_db < 3.0:
        warnings.append(f"Limited margin for fading ({metrics.link_margin_db:.1f} dB)")

    return warnings


def compute_link_metrics(
    endpoint1: str,
    endpoint2: str,
    interface1: WirelessParams,
    interface2: WirelessParams,
    channel_server_url: str,
) -> LinkMetrics:
    """
    Compute all metrics for a single wireless link via channel server.

    Args:
        endpoint1: First endpoint (e.g., "node1:eth1")
        endpoint2: Second endpoint (e.g., "node2:eth1")
        interface1: WirelessInterface config for first endpoint
        interface2: WirelessInterface config for second endpoint
        channel_server_url: URL of channel server

    Returns:
        LinkMetrics object with all computed metrics
    """
    # Extract node names from endpoints (e.g., "node1:eth1" -> "node1")
    tx_node = endpoint1.split(":")[0]
    rx_node = endpoint2.split(":")[0]

    # Prepare request payload for channel server
    payload = {
        "tx_node": tx_node,
        "rx_node": rx_node,
        "tx_position": {
            "x": interface1.position.x,
            "y": interface1.position.y,
            "z": interface1.position.z,
        },
        "rx_position": {
            "x": interface2.position.x,
            "y": interface2.position.y,
            "z": interface2.position.z,
        },
        "tx_power_dbm": interface1.rf_power_dbm,
        "tx_gain_dbi": interface1.antenna_gain_dbi,
        "rx_gain_dbi": interface2.antenna_gain_dbi,
        "antenna_pattern": interface1.antenna_pattern.value,
        "polarization": interface1.polarization.value,
        "frequency_hz": interface1.frequency_ghz * 1e9,
        "bandwidth_hz": interface1.bandwidth_mhz * 1e6,
    }

    # Add modulation/FEC params (either from MCS table or fixed)
    if interface1.mcs_table:
        # MCS table scenario - server will select MCS
        payload["mcs_table_path"] = str(interface1.mcs_table)
        if interface1.mcs_hysteresis_db:
            payload["mcs_hysteresis_db"] = interface1.mcs_hysteresis_db
    else:
        # Fixed modulation/FEC (convert enum to string value)
        payload["modulation"] = interface1.modulation.value if interface1.modulation else None
        payload["fec_type"] = interface1.fec_type.value if interface1.fec_type else None
        payload["fec_code_rate"] = interface1.fec_code_rate

    # Call channel server
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(f"{channel_server_url}/compute/single", json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as e:
        error_detail = ""
        try:
            error_detail = f"\nResponse: {response.text}"
        except Exception:
            pass
        raise RuntimeError(
            f"Channel server error: {e}{error_detail}\n"
            f"Make sure the channel server is running: uv run sine channel-server"
        ) from e

    # Extract response fields
    snr_db = data["snr_db"]
    path_loss_db = data["path_loss_db"]
    ber = data["ber"]
    per = data["per"]
    effective_rate_mbps = data["netem_rate_mbps"]

    # Compute distance from positions
    dx = interface2.position.x - interface1.position.x
    dy = interface2.position.y - interface1.position.y
    dz = interface2.position.z - interface1.position.z
    distance_m = math.sqrt(dx**2 + dy**2 + dz**2)

    # Extract MCS info (from adaptive MCS or fall back to fixed)
    modulation = data.get("selected_modulation")
    code_rate = data.get("selected_code_rate")
    fec_type = data.get("selected_fec_type")
    min_snr_db = None  # Not returned by API (would need MCS table lookup)

    # Fall back to fixed params if not using adaptive MCS
    if modulation is None and interface1.modulation:
        modulation = interface1.modulation.value
    if code_rate is None and interface1.fec_code_rate:
        code_rate = interface1.fec_code_rate
    if fec_type is None and interface1.fec_type:
        fec_type = interface1.fec_type.value

    bandwidth_mhz = data.get("selected_bandwidth_mhz") or interface1.bandwidth_mhz

    # Compute Shannon capacity
    bandwidth_hz = bandwidth_mhz * 1e6
    shannon = compute_shannon_capacity(snr_db, bandwidth_hz)
    shannon_capacity_mbps = shannon["capacity_mbps"]
    shannon_spectral_efficiency = shannon["spectral_efficiency_bps_hz"]

    # Compute effective spectral efficiency
    effective_spectral_efficiency = effective_rate_mbps / bandwidth_mhz

    # Categorize efficiency
    efficiency_category = categorize_spectral_efficiency(effective_spectral_efficiency)

    # Compute Shannon gap
    shannon_gap_db = compute_shannon_gap(shannon_capacity_mbps, effective_rate_mbps)

    # Compute link margin
    link_margin_db = compute_link_margin(snr_db, min_snr_db)

    # Create LinkMetrics object
    metrics = LinkMetrics(
        endpoint1=endpoint1,
        endpoint2=endpoint2,
        distance_m=distance_m,
        path_loss_db=path_loss_db,
        snr_db=snr_db,
        shannon_capacity_mbps=shannon_capacity_mbps,
        shannon_spectral_efficiency=shannon_spectral_efficiency,
        effective_rate_mbps=effective_rate_mbps,
        effective_spectral_efficiency=effective_spectral_efficiency,
        efficiency_category=efficiency_category,
        shannon_gap_db=shannon_gap_db,
        link_margin_db=link_margin_db,
        ber=ber,
        per=per,
        modulation=modulation,
        code_rate=code_rate,
        fec_type=fec_type,
        bandwidth_mhz=bandwidth_mhz,
        min_snr_db=min_snr_db,
    )

    # Generate warnings
    metrics.warnings = generate_warnings(metrics)

    return metrics


def discover_wireless_links(topology):
    """
    Discover all wireless links from topology.

    Supports two topology architectures:
    1. Shared bridge mode: Generate full mesh from shared_bridge.nodes
    2. Point-to-point links: Use explicit links from topology.links

    Args:
        topology: NetworkTopology object from load_topology()

    Returns:
        List of tuples: (endpoint1, endpoint2, wireless1, wireless2, is_shared_bridge)
        where endpoint format is "node:interface" and is_shared_bridge is a bool
    """
    wireless_links = []
    is_shared_bridge = False

    # Case 1: Shared bridge mode
    if topology.topology.shared_bridge and topology.topology.shared_bridge.enabled:
        is_shared_bridge = True
        nodes = topology.topology.shared_bridge.nodes
        iface_name = topology.topology.shared_bridge.interface_name

        # Generate full mesh of links between all nodes
        for i, node1_name in enumerate(nodes):
            for node2_name in nodes[i+1:]:  # Avoid duplicates
                node1 = topology.topology.nodes.get(node1_name)
                node2 = topology.topology.nodes.get(node2_name)

                if not node1 or not node2:
                    continue

                iface1 = node1.interfaces.get(iface_name)
                iface2 = node2.interfaces.get(iface_name)

                if not iface1 or not iface2:
                    continue

                # Check both are wireless
                if iface1.wireless and iface2.wireless:
                    endpoint1 = f"{node1_name}:{iface_name}"
                    endpoint2 = f"{node2_name}:{iface_name}"
                    wireless_links.append((endpoint1, endpoint2, iface1.wireless, iface2.wireless, is_shared_bridge))

    # Case 2: Explicit point-to-point links
    else:
        for link in topology.topology.links:
            # Parse endpoints
            ep1_parts = link.endpoints[0].split(":")
            ep2_parts = link.endpoints[1].split(":")

            if len(ep1_parts) != 2 or len(ep2_parts) != 2:
                continue

            node1_name, iface1_name = ep1_parts
            node2_name, iface2_name = ep2_parts

            node1 = topology.topology.nodes.get(node1_name)
            node2 = topology.topology.nodes.get(node2_name)

            if not node1 or not node2:
                continue

            iface1 = node1.interfaces.get(iface1_name)
            iface2 = node2.interfaces.get(iface2_name)

            if not iface1 or not iface2:
                continue

            if iface1.wireless and iface2.wireless:
                wireless_links.append((link.endpoints[0], link.endpoints[1], iface1.wireless, iface2.wireless, is_shared_bridge))

    return wireless_links


def display_results(link_metrics: list[LinkMetrics], is_shared_bridge: bool = False) -> None:
    """
    Display results using rich.Table with formatting.

    Args:
        link_metrics: List of LinkMetrics objects to display
        is_shared_bridge: Whether this is a shared bridge topology
    """
    console = Console()

    # Display warning banner for shared bridge (Phase 1)
    if is_shared_bridge:
        console.print()
        console.print("[bold yellow]⚠ SHARED BRIDGE MODE (Phase 1 - SNR-based)[/bold yellow]")
        console.print("[yellow]Note: Per-link rates computed using SNR (no interference modeling)[/yellow]")
        console.print("[yellow]      - Each link analyzed independently (best-case capacity)[/yellow]")
        console.print("[yellow]      - Actual throughput depends on MAC protocol and channel contention[/yellow]")
        console.print("[yellow]      - Aggregate throughput < sum of link capacities (shared medium)[/yellow]")
        console.print()

    # Create table
    table = Table(
        title="Spectral Efficiency Analysis",
        show_header=True,
        header_style="bold magenta",
        border_style="blue",
    )

    # Add columns
    table.add_column("Link", style="cyan", no_wrap=True)
    table.add_column("Dist\n(m)", justify="right")
    table.add_column("SNR\n(dB)", justify="right")
    table.add_column("Shannon\n(Mbps)", justify="right", style="cyan")
    table.add_column("Effective\nRate (Mbps)", justify="right")
    table.add_column("Spec Eff\n(b/s/Hz)", justify="right")
    table.add_column("Gap\n(dB)", justify="right")
    table.add_column("Link\nMargin\n(dB)", justify="right")
    table.add_column("BER /\nPER", justify="right")
    table.add_column("Warnings", style="bold red")

    # Add rows
    for metrics in link_metrics:
        # Color-code efficiency category
        if metrics.efficiency_category == "High":
            eff_style = "bold green"
        elif metrics.efficiency_category == "Medium":
            eff_style = "bold yellow"
        else:
            eff_style = "bold red"

        # Color-code link margin
        if metrics.link_margin_db is not None:
            if metrics.link_margin_db > 10:
                margin_style = "green"
            elif metrics.link_margin_db >= 3:
                margin_style = "yellow"
            else:
                margin_style = "red"
            margin_text = f"[{margin_style}]{metrics.link_margin_db:.1f}[/{margin_style}]"
        else:
            margin_text = "N/A"

        # Format link endpoints
        link_text = f"{metrics.endpoint1}\n↔\n{metrics.endpoint2}"

        # Format spectral efficiency with category
        spec_eff_text = (
            f"Shannon: {metrics.shannon_spectral_efficiency:.1f}\n"
            f"Effective: [{eff_style}]{metrics.effective_spectral_efficiency:.2f}[/{eff_style}]\n"
            f"[{eff_style}]({metrics.efficiency_category})[/{eff_style}]"
        )

        # Format BER/PER
        ber_per_text = f"{metrics.ber:.2e}\n{metrics.per:.2e}"

        # Format warnings
        warnings_text = "\n".join(f"⚠ {w}" for w in metrics.warnings) if metrics.warnings else ""

        table.add_row(
            link_text,
            f"{metrics.distance_m:.1f}",
            f"{metrics.snr_db:.1f}",
            f"{metrics.shannon_capacity_mbps:.1f}\n({metrics.shannon_spectral_efficiency:.1f})",
            f"{metrics.effective_rate_mbps:.1f}",
            spec_eff_text,
            f"{metrics.shannon_gap_db:.1f}",
            margin_text,
            ber_per_text,
            warnings_text,
        )

        # Add MCS info row (footer for this link)
        mcs_info = (
            f"MCS: {metrics.modulation.upper()}, "
            f"rate-{metrics.code_rate:.3f} {metrics.fec_type.upper()} | "
            f"Path Loss: {metrics.path_loss_db:.1f} dB | "
            f"BW: {metrics.bandwidth_mhz:.0f} MHz"
        )
        if metrics.min_snr_db is not None:
            mcs_info += f" | Min SNR: {metrics.min_snr_db:.1f} dB"

        table.add_row(
            "",  # Empty cells
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        )
        table.add_section()

    # Display table
    console.print(table)

    # Display MCS details below table
    console.print("\n[bold]MCS Configuration Details:[/bold]")
    for metrics in link_metrics:
        mcs_info = (
            f"  {metrics.endpoint1} ↔ {metrics.endpoint2}: "
            f"{metrics.modulation.upper()}, "
            f"rate-{metrics.code_rate:.3f} {metrics.fec_type.upper()} | "
            f"Path Loss: {metrics.path_loss_db:.1f} dB | "
            f"BW: {metrics.bandwidth_mhz:.0f} MHz"
        )
        if metrics.min_snr_db is not None:
            mcs_info += f" | Min SNR: {metrics.min_snr_db:.1f} dB"
        console.print(mcs_info)


def main(topology_path: str, channel_server_url: str) -> None:
    """
    Main entry point for spectral efficiency calculator.

    Args:
        topology_path: Path to network.yaml topology file
        channel_server_url: URL of channel server
    """
    console = Console()

    # Load topology
    console.print(f"[cyan]Loading topology from {topology_path}...[/cyan]")
    try:
        topology = load_topology(topology_path)
    except Exception as e:
        console.print(f"[red]Error loading topology: {e}[/red]")
        sys.exit(1)

    # Check channel server health and scene status
    console.print("[cyan]Checking channel server status...[/cyan]")
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(f"{channel_server_url}/health")
            response.raise_for_status()
            health_data = response.json()
            scene_already_loaded = health_data.get("scene_loaded", False)
    except httpx.HTTPError as e:
        console.print(f"[red]Channel server not available: {e}[/red]")
        console.print("[yellow]Make sure the channel server is running: uv run sine channel-server[/yellow]")
        sys.exit(1)

    # Load scene into channel server (required for ray tracing)
    if topology.topology.scene and topology.topology.scene.file:
        if scene_already_loaded:
            console.print("[yellow]⚠ WARNING: A scene is already loaded in the channel server![/yellow]")
            console.print("[yellow]  The channel server does not support scene reloading.[/yellow]")
            console.print("[yellow]  If you get incorrect path loss values, restart the channel server:[/yellow]")
            console.print("[yellow]    1. Stop the channel server (Ctrl+C)[/yellow]")
            console.print("[yellow]    2. Start it again: uv run sine channel-server[/yellow]")
            console.print(f"[yellow]  Then re-run this script.[/yellow]")
            console.print()
            # Continue anyway - the scene might be the same one we need
        else:
            console.print(f"[cyan]Loading scene into channel server: {topology.topology.scene.file}...[/cyan]")
            scene_payload = {
                "scene_file": str(topology.topology.scene.file),
                "frequency_hz": 5.18e9,  # Default, will be overridden per-link
                "bandwidth_hz": 80e6,     # Default, will be overridden per-link
            }
            try:
                with httpx.Client(timeout=30.0) as client:
                    response = client.post(f"{channel_server_url}/scene/load", json=scene_payload)
                    response.raise_for_status()
                    console.print(f"[green]✓[/green] Scene loaded successfully")
            except httpx.HTTPError as e:
                console.print(f"[red]Failed to load scene: {e}[/red]")
                sys.exit(1)
    else:
        console.print("[yellow]No scene file specified in topology (using empty/default scene)[/yellow]")

    # Discover wireless links (supports both point-to-point and shared bridge)
    console.print("[cyan]Discovering wireless links...[/cyan]")
    wireless_links = discover_wireless_links(topology)

    if not wireless_links:
        console.print("[red]No wireless links found in topology![/red]")
        sys.exit(1)

    # Check if this is a shared bridge topology
    is_shared_bridge = topology.topology.shared_bridge and topology.topology.shared_bridge.enabled

    if is_shared_bridge and topology.topology.shared_bridge:
        num_nodes = len(topology.topology.shared_bridge.nodes)
        console.print(
            f"[cyan]Found {len(wireless_links)} wireless link(s) "
            f"in shared bridge mode (full mesh from {num_nodes} nodes)[/cyan]"
        )
    else:
        console.print(f"[cyan]Found {len(wireless_links)} wireless link(s) (point-to-point)[/cyan]")

    # Compute metrics for each link
    console.print(f"[cyan]Computing channel metrics via {channel_server_url}...[/cyan]")
    link_metrics = []

    for endpoint1, endpoint2, iface1, iface2, _ in wireless_links:
        try:
            metrics = compute_link_metrics(
                endpoint1,
                endpoint2,
                iface1,
                iface2,
                channel_server_url,
            )
            link_metrics.append(metrics)
            console.print(f"  [green]✓[/green] {endpoint1} ↔ {endpoint2}")
        except Exception as e:
            console.print(f"  [red]✗[/red] {endpoint1} ↔ {endpoint2}: {e}")
            console.print(f"[dim]{traceback.format_exc()}[/dim]")

    if not link_metrics:
        console.print("[red]Failed to compute metrics for any links![/red]")
        sys.exit(1)

    # Display results
    console.print()
    display_results(link_metrics, is_shared_bridge=is_shared_bridge)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Calculate spectral efficiency for wireless links in a SiNE topology"
    )
    parser.add_argument(
        "topology",
        help="Path to network.yaml topology file",
    )
    parser.add_argument(
        "--channel-server",
        default="http://localhost:8000",
        help="Channel server URL (default: http://localhost:8000)",
    )

    args = parser.parse_args()

    main(args.topology, args.channel_server)
