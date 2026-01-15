"""
SiNE Command Line Interface.

Commands:
- sine deploy <topology.yaml>  : Deploy and start emulation
- sine destroy <topology.yaml> : Destroy deployed emulation
- sine status                  : Show status of running emulations
- sine channel-server          : Start the channel computation server
- sine mobility-server <topology.yaml> : Start mobility API server with emulation
- sine validate <topology.yaml>: Validate topology file
- sine render <topology.yaml>  : Render scene with nodes and paths
- sine info                    : Show system information
"""

import asyncio
import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

console = Console()


def setup_logging(verbose: bool = False) -> None:
    """Configure logging with rich handler."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


def _print_deployment_summary(summary: dict) -> None:
    """Print a summary of the deployment."""
    console.print()

    # Show mode and bridge info if applicable
    mode = summary.get("mode", "point_to_point")
    if mode == "shared_bridge":
        bridge_info = summary.get("shared_bridge", {})
        console.print("[bold magenta]Mode:[/] Shared Bridge (true broadcast medium)")
        console.print(
            f"[bold]Bridge:[/] {bridge_info.get('name')} | "
            f"[bold]Interface:[/] {bridge_info.get('interface')} | "
            f"[bold]Nodes:[/] {', '.join(bridge_info.get('nodes', []))}"
        )
        console.print()

    # Containers table
    if summary.get("containers"):
        container_table = Table(title="Deployed Containers")
        container_table.add_column("Container", style="cyan")
        container_table.add_column("Image")
        container_table.add_column("PID", style="dim")
        container_table.add_column("Interfaces", style="green")

        # Add IP column for shared bridge mode
        if mode == "shared_bridge":
            container_table.add_column("IPs (iface: address)", style="yellow")

        container_table.add_column("Positions (iface: x,y,z)")

        for c in summary["containers"]:
            interfaces = ", ".join(c.get("interfaces", [])) or "eth0"

            # Format IPs per interface (shared bridge mode)
            ip_str = ""
            if mode == "shared_bridge" and c.get("ips"):
                ip_parts = []
                for iface, ip in c["ips"].items():
                    ip_parts.append(f"{iface}: {ip}")
                ip_str = ", ".join(ip_parts)

            # Format positions per interface
            pos_str = ""
            if c.get("positions"):
                pos_parts = []
                for iface, p in c["positions"].items():
                    pos_parts.append(f"{iface}: ({p['x']:.1f},{p['y']:.1f},{p['z']:.1f})")
                pos_str = ", ".join(pos_parts)

            if mode == "shared_bridge":
                container_table.add_row(
                    c.get("name", ""),
                    c.get("image", ""),
                    str(c.get("pid", "")),
                    interfaces,
                    ip_str,
                    pos_str,
                )
            else:
                container_table.add_row(
                    c.get("name", ""),
                    c.get("image", ""),
                    str(c.get("pid", "")),
                    interfaces,
                    pos_str,
                )

        console.print(container_table)

    # Links table (supports both wireless and fixed, P2P and shared bridge)
    if summary.get("links"):
        console.print()

        if mode == "shared_bridge":
            # Group links by source node for shared bridge mode
            per_node_links = {}
            for link in summary["links"]:
                tx_node = link["tx_node"]
                if tx_node not in per_node_links:
                    per_node_links[tx_node] = []
                per_node_links[tx_node].append(link)

            # Display per-node, per-destination tables
            for tx_node in sorted(per_node_links.keys()):
                link_table = Table(title=f"Per-Destination Parameters for {tx_node}")
                link_table.add_column("Destination", style="cyan")
                link_table.add_column("Delay", justify="right")
                link_table.add_column("Jitter", justify="right")
                link_table.add_column("Loss %", justify="right")
                link_table.add_column("Rate", justify="right")

                for link in per_node_links[tx_node]:
                    link_table.add_row(
                        f"{link['rx_node']} ({link.get('rx_interface', 'eth1')})",
                        f"{link['delay_ms']:.3f} ms",
                        f"{link['jitter_ms']:.3f} ms",
                        f"{link['loss_percent']:.2f}%",
                        f"{link['rate_mbps']:.1f} Mbps",
                    )

                console.print(link_table)
                console.print()
        else:
            # Point-to-point mode (original display)
            link_table = Table(title="Link Parameters (netem)")
            link_table.add_column("Link", style="cyan")
            link_table.add_column("Type", style="magenta")
            link_table.add_column("Delay", justify="right")
            link_table.add_column("Jitter", justify="right")
            link_table.add_column("Loss %", justify="right")
            link_table.add_column("Rate", justify="right")

            for link in summary["links"]:
                link_type = link.get("type", "unknown")
                type_style = "[green]wireless[/]" if link_type == "wireless" else "[blue]fixed[/]"
                link_table.add_row(
                    link["link"],
                    type_style,
                    f"{link['delay_ms']:.2f} ms",
                    f"{link['jitter_ms']:.2f} ms",
                    f"{link['loss_percent']:.2f}%",
                    f"{link['rate_mbps']:.1f} Mbps",
                )

            console.print(link_table)


@click.group()
@click.version_option(version="0.1.0", prog_name="sine")
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose output")
def main(verbose: bool) -> None:
    """SiNE - Sionna-based Network Emulation

    Wireless network emulation using Sionna ray tracing and Containerlab.
    """
    setup_logging(verbose)


@main.command()
@click.argument("topology", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-c",
    "--channel-server",
    default="http://localhost:8000",
    help="Channel computation server URL",
)
@click.option(
    "--enable-mobility",
    is_flag=True,
    help="Start mobility API server on port 8001 for dynamic position updates",
)
@click.option(
    "--mobility-port",
    default=8001,
    type=int,
    help="Port for mobility API server (default: 8001)",
)
def deploy(topology: Path, channel_server: str, enable_mobility: bool, mobility_port: int) -> None:
    """Deploy wireless network emulation from topology file.

    TOPOLOGY is the path to a network.yaml file defining the emulation.

    With --enable-mobility, the deployment also starts a REST API server
    that allows external scripts to update node positions in real-time.
    """
    from sine.emulation.controller import EmulationController, EmulationError

    console.print(f"[bold blue]Deploying topology:[/] {topology}")

    if enable_mobility:
        console.print(f"[dim]Mobility API will be available on port {mobility_port}[/]")

    controller = EmulationController(topology)

    async def run_emulation() -> None:
        try:
            success = await controller.start()
            if success:
                console.print("[bold green]Emulation deployed successfully![/]")

                # Print deployment summary
                summary = controller.get_deployment_summary()
                _print_deployment_summary(summary)

                console.print(f"\n[dim]To destroy: uv run sine destroy {topology}[/]")

                if enable_mobility:
                    console.print(f"[green]Mobility API running on http://localhost:{mobility_port}[/]")
                    console.print(f"[dim]Example: curl -X POST http://localhost:{mobility_port}/api/mobility/update \\")
                    console.print("[dim]         -H 'Content-Type: application/json' \\")
                    console.print("[dim]         -d '{'\"node\": \"node2\", \"x\": 10.0, \"y\": 5.0, \"z\": 1.5}'[/]")

                console.print("[dim]Press Ctrl+C to stop emulation[/]")

                # Keep running until interrupted
                try:
                    while True:
                        await asyncio.sleep(1)
                except KeyboardInterrupt:
                    console.print("\n[yellow]Stopping emulation...[/]")
                    await controller.stop()
                    console.print("[green]Emulation stopped[/]")
        except EmulationError as e:
            console.print(f"[bold red]Deployment failed:[/] {e}")
            sys.exit(1)

    # If mobility is enabled, run both emulation and mobility API server
    if enable_mobility:
        import uvicorn

        from sine.mobility.api import MobilityAPIServer

        async def run_with_mobility() -> None:
            # Start emulation controller
            controller_obj = EmulationController(topology)
            await controller_obj.start()

            console.print("[bold green]Emulation deployed successfully![/]")
            summary = controller_obj.get_deployment_summary()
            _print_deployment_summary(summary)

            console.print(f"\n[green]Mobility API running on http://localhost:{mobility_port}[/]")
            console.print(f"[dim]Example: curl -X POST http://localhost:{mobility_port}/api/mobility/update \\")
            console.print("[dim]         -H 'Content-Type: application/json' \\")
            console.print("[dim]         -d '{'\"node\": \"node2\", \"x\": 10.0, \"y\": 5.0, \"z\": 1.5}'[/]")
            console.print(f"[dim]To destroy: uv run sine destroy {topology}[/]")
            console.print("[dim]Press Ctrl+C to stop emulation[/]")

            # Create mobility API server (but with already-started controller)
            mobility_server = MobilityAPIServer(topology)
            mobility_server.controller = controller_obj  # Use existing controller

            # Start FastAPI server
            config = uvicorn.Config(
                mobility_server.app,
                host="0.0.0.0",
                port=mobility_port,
                log_level="info",
                access_log=False,
            )
            server = uvicorn.Server(config)

            try:
                await server.serve()
            except KeyboardInterrupt:
                console.print("\n[yellow]Stopping emulation...[/]")
            finally:
                if controller_obj:
                    await controller_obj.stop()
                console.print("[green]Emulation stopped[/]")

        try:
            asyncio.run(run_with_mobility())
        except KeyboardInterrupt:
            pass
    else:
        # Standard deployment without mobility API
        try:
            asyncio.run(run_emulation())
        except KeyboardInterrupt:
            pass


@main.command()
@click.argument("topology", type=click.Path(exists=True, path_type=Path))
def destroy(topology: Path) -> None:
    """Destroy a deployed emulation.

    TOPOLOGY is the path to the network.yaml file used for deployment.
    """
    from sine.topology.manager import ContainerlabError, ContainerlabManager

    console.print(f"[bold yellow]Destroying topology:[/] {topology}")

    try:
        manager = ContainerlabManager(topology)
        # Try to find and use existing clab topology file
        clab_path = topology.parent / ".sine_clab_topology.yaml"
        if clab_path.exists():
            manager._clab_topology_path = clab_path
            if manager.destroy():
                console.print("[green]Topology destroyed successfully[/]")
            else:
                console.print("[red]Failed to destroy topology[/]")
                sys.exit(1)
        else:
            console.print("[yellow]No deployed topology found[/]")
    except ContainerlabError as e:
        console.print(f"[bold red]Destroy failed:[/] {e}")
        sys.exit(1)


@main.command()
def status() -> None:
    """Show status of running SiNE emulations."""
    try:
        import docker

        client = docker.from_env()

        # Find SiNE/containerlab containers
        containers = [
            c
            for c in client.containers.list()
            if c.name.startswith("clab-") or c.name.startswith("sine-")
        ]

        if containers:
            table = Table(title="Running Containers")
            table.add_column("Name", style="cyan")
            table.add_column("Status", style="green")
            table.add_column("Image")
            table.add_column("ID", style="dim")

            for c in containers:
                table.add_row(c.name, c.status, c.image.tags[0] if c.image.tags else "unknown", c.short_id)

            console.print(table)
        else:
            console.print("[dim]No SiNE containers running[/]")

    except ImportError:
        console.print("[red]docker package not installed[/]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error checking status:[/] {e}")
        sys.exit(1)


@main.command("channel-server")
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("-p", "--port", default=8000, type=int, help="Port to listen on")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development")
def channel_server(host: str, port: int, reload: bool) -> None:
    """Start the channel computation server.

    The server provides REST API endpoints for computing wireless channel
    parameters using Sionna ray tracing.
    """
    console.print(f"[bold blue]Starting channel server on {host}:{port}[/]")

    # Check Sionna availability
    from sine.channel.sionna_engine import is_sionna_available

    if is_sionna_available():
        console.print("[green]Sionna available - GPU acceleration enabled[/]")
    else:
        console.print(
            "[yellow]Sionna not available - using fallback FSPL model[/]\n"
            "[dim]Install GPU support: pip install sine[gpu][/]"
        )

    import uvicorn

    uvicorn.run(
        "sine.channel.server:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


@main.command("mobility-server")
@click.argument("topology", type=click.Path(exists=True, path_type=Path))
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("-p", "--port", default=8001, type=int, help="Port to listen on")
def mobility_server(topology: Path, host: str, port: int) -> None:
    """Start the mobility API server with emulation.

    This starts both the emulation and a REST API server that allows
    external tools to update node positions in real-time.

    Example:
        # Start server
        uv run sine mobility-server examples/vacuum_20m/network.yaml

        # Update position (in another terminal)
        curl -X POST http://localhost:8001/api/mobility/update \\
             -H "Content-Type: application/json" \\
             -d '{"node": "node1", "x": 10.0, "y": 5.0, "z": 1.5}'
    """
    console.print(f"[bold blue]Starting mobility API server on {host}:{port}[/]")
    console.print(f"[dim]Topology: {topology}[/]")

    from sine.mobility import run_mobility_server

    asyncio.run(run_mobility_server(topology, host, port))


@main.command()
@click.argument("topology", type=click.Path(exists=True, path_type=Path))
def validate(topology: Path) -> None:
    """Validate a topology file.

    Checks the topology file for errors and prints a summary.
    """
    from sine.config.loader import TopologyLoader, TopologyLoadError
    from sine.scene.builder import SceneBuilder

    console.print(f"[bold blue]Validating:[/] {topology}")

    # Validate topology
    try:
        loader = TopologyLoader(topology)
        config = loader.load()
        console.print("[green]✓ Topology syntax valid[/]")
    except TopologyLoadError as e:
        console.print(f"[red]✗ Topology validation failed:[/]\n{e}")
        sys.exit(1)

    # Count wireless and fixed links
    wireless_count = 0
    fixed_count = 0
    for link in config.topology.links:
        from sine.config.schema import parse_endpoint
        node1_name, iface1 = parse_endpoint(link.endpoints[0])
        node1 = config.topology.nodes.get(node1_name)
        if node1 and node1.interfaces and iface1 in node1.interfaces:
            if node1.interfaces[iface1].is_wireless:
                wireless_count += 1
            else:
                fixed_count += 1

    # Print summary
    table = Table(title="Topology Summary")
    table.add_column("Property", style="cyan")
    table.add_column("Value")

    table.add_row("Name", config.name)
    table.add_row("Prefix", config.container_prefix)
    table.add_row("Nodes", str(len(config.topology.nodes)))
    table.add_row("Links", str(len(config.topology.links)))
    table.add_row("  Wireless", str(wireless_count))
    table.add_row("  Fixed", str(fixed_count))
    scene_file = config.topology.scene.file if config.topology.scene else "(none)"
    table.add_row("Scene File", scene_file)
    table.add_row("Channel Server", config.topology.channel_server)
    table.add_row("Mobility Poll", f"{config.topology.mobility_poll_ms}ms")

    console.print(table)

    # List nodes and their interfaces
    if config.topology.nodes:
        node_table = Table(title="Nodes")
        node_table.add_column("Name", style="cyan")
        node_table.add_column("Image")
        node_table.add_column("Interface", style="green")
        node_table.add_column("Type", style="magenta")
        node_table.add_column("Position / Config")

        for name, node in config.topology.nodes.items():
            if node.interfaces:
                for iface_name, iface_config in node.interfaces.items():
                    if iface_config.is_wireless:
                        w = iface_config.wireless
                        pos = f"({w.position.x:.1f}, {w.position.y:.1f}, {w.position.z:.1f})"
                        config_str = f"{pos} | {w.modulation.value}, {w.fec_type.value}"
                        iface_type = "wireless"
                    else:
                        f = iface_config.fixed_netem
                        config_str = f"delay={f.delay_ms}ms, rate={f.rate_mbps}Mbps"
                        iface_type = "fixed"
                    node_table.add_row(name, node.image, iface_name, iface_type, config_str)
            else:
                node_table.add_row(name, node.image, "-", "-", "-")

        console.print(node_table)

    # Validate scene (only if present)
    if not config.topology.scene:
        console.print("[dim]No scene configured (fixed links only)[/]")
    else:
        scene_path = Path(config.topology.scene.file)
        if scene_path.exists():
            try:
                builder = SceneBuilder()
                builder.load_scene(scene_path)
                warnings = builder.validate_scene()
                if warnings:
                    for w in warnings:
                        console.print(f"[yellow]⚠ Scene warning:[/] {w}")
                else:
                    console.print(f"[green]✓ Scene valid:[/] {scene_path}")
            except Exception as e:
                console.print(f"[red]✗ Scene error:[/] {e}")
        else:
            console.print(f"[red]✗ Scene file not found:[/] {scene_path}")

    console.print("\n[green]Validation complete[/]")


def _parse_resolution(value: str) -> tuple[int, int]:
    """Parse resolution string like '1920x1080' to tuple."""
    try:
        parts = value.lower().split("x")
        if len(parts) != 2:
            raise ValueError()
        return (int(parts[0]), int(parts[1]))
    except ValueError:
        raise click.BadParameter(f"Resolution must be WxH (e.g., '1920x1080'), got: {value}")


def _parse_position(value: str) -> tuple[float, float, float]:
    """Parse position string like '10,5,20' to tuple."""
    try:
        parts = value.split(",")
        if len(parts) != 3:
            raise ValueError()
        return (float(parts[0]), float(parts[1]), float(parts[2]))
    except ValueError:
        raise click.BadParameter(f"Position must be X,Y,Z (e.g., '10,5,20'), got: {value}")


@main.command()
@click.argument("topology", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-o",
    "--output",
    required=True,
    type=click.Path(path_type=Path),
    help="Output image path (e.g., scene.png)",
)
@click.option(
    "--resolution",
    default="655x500",
    help="Image resolution WxH (default: 655x500)",
)
@click.option(
    "--num-samples",
    default=512,
    type=int,
    help="Ray samples for quality (default: 512)",
)
@click.option(
    "--camera-position",
    default=None,
    help="Camera position X,Y,Z (default: auto)",
)
@click.option(
    "--look-at",
    default=None,
    help="Look-at position X,Y,Z (default: scene center)",
)
@click.option(
    "--fov",
    default=45.0,
    type=float,
    help="Field of view in degrees (default: 45)",
)
@click.option(
    "--no-paths",
    is_flag=True,
    help="Skip rendering propagation paths",
)
@click.option(
    "--no-devices",
    is_flag=True,
    help="Hide TX/RX device markers",
)
@click.option(
    "--clip-at",
    default=None,
    type=float,
    help="Clip plane height (z) to cut away ceiling/walls",
)
def render(
    topology: Path,
    output: Path,
    resolution: str,
    num_samples: int,
    camera_position: str | None,
    look_at: str | None,
    fov: float,
    no_paths: bool,
    no_devices: bool,
    clip_at: float | None,
) -> None:
    """Render a scene with nodes and propagation paths.

    TOPOLOGY is the path to a network.yaml file defining the scene and nodes.

    Uses Sionna's native ray-traced rendering to produce high-quality images
    showing the scene geometry, TX/RX positions, and propagation paths.
    """
    from sine.channel.sionna_engine import SionnaEngine, is_sionna_available
    from sine.config.loader import TopologyLoader, TopologyLoadError

    console.print(f"[bold blue]Rendering:[/] {topology}")

    # Check Sionna availability
    if not is_sionna_available():
        console.print(
            "[bold red]Error:[/] Sionna is required for rendering.\n"
            "[dim]Install with: pip install sine[gpu][/]"
        )
        sys.exit(1)

    # Parse resolution
    try:
        res_tuple = _parse_resolution(resolution)
    except click.BadParameter as e:
        console.print(f"[bold red]Error:[/] {e.message}")
        sys.exit(1)

    # Parse camera position if provided
    cam_pos = None
    if camera_position:
        try:
            cam_pos = _parse_position(camera_position)
        except click.BadParameter as e:
            console.print(f"[bold red]Error:[/] {e.message}")
            sys.exit(1)

    # Parse look-at if provided
    look_at_pos = None
    if look_at:
        try:
            look_at_pos = _parse_position(look_at)
        except click.BadParameter as e:
            console.print(f"[bold red]Error:[/] {e.message}")
            sys.exit(1)

    # Load topology
    try:
        loader = TopologyLoader(topology)
        config = loader.load()
    except TopologyLoadError as e:
        console.print(f"[bold red]Topology error:[/] {e}")
        sys.exit(1)

    # Check scene file (required for rendering)
    if not config.topology.scene:
        console.print("[bold red]Scene file required for rendering[/]")
        sys.exit(1)
    scene_path = Path(config.topology.scene.file)
    if not scene_path.exists():
        console.print(f"[bold red]Scene file not found:[/] {scene_path}")
        sys.exit(1)

    # Initialize engine and load scene
    try:
        engine = SionnaEngine()
        engine.load_scene(scene_path=str(scene_path))
        console.print(f"[green]✓ Loaded scene:[/] {scene_path}")
    except Exception as e:
        console.print(f"[bold red]Failed to load scene:[/] {e}")
        sys.exit(1)

    # Add TX/RX devices from wireless links
    from sine.config.schema import parse_endpoint
    devices_added = set()  # Track (node, interface) pairs
    for link in config.topology.links:
        # Use get_node_names() to handle "node:interface" format
        for endpoint in link.endpoints:
            node_name, iface_name = parse_endpoint(endpoint)
            device_key = (node_name, iface_name)
            if device_key in devices_added:
                continue

            node = config.topology.nodes.get(node_name)
            if node and node.interfaces and iface_name in node.interfaces:
                iface_config = node.interfaces[iface_name]
                if iface_config.is_wireless:
                    w = iface_config.wireless
                    pos = (w.position.x, w.position.y, w.position.z)
                    # Add as transmitter or receiver alternately (both ends need devices for path computation)
                    device_id = f"{node_name}_{iface_name}"
                    if len(devices_added) % 2 == 0:
                        engine.add_transmitter(device_id, pos)
                    else:
                        engine.add_receiver(device_id, pos)
                    devices_added.add(device_key)
                    console.print(f"[dim]Added device: {node_name}:{iface_name} at ({pos[0]:.1f}, {pos[1]:.1f}, {pos[2]:.1f})[/]")

    if not devices_added:
        console.print("[yellow]Warning: No wireless interfaces found in topology[/]")

    # Render scene
    try:
        console.print(f"[dim]Rendering with {num_samples} samples at {resolution}...[/]")
        engine.render_scene(
            output_path=str(output),
            camera_position=cam_pos,
            look_at=look_at_pos,
            fov=fov,
            resolution=res_tuple,
            num_samples=num_samples,
            show_devices=not no_devices,
            show_orientations=not no_devices,
            include_paths=not no_paths,
            clip_at=clip_at,
        )
        console.print(f"[bold green]Rendered scene to:[/] {output}")
    except Exception as e:
        console.print(f"[bold red]Render failed:[/] {e}")
        sys.exit(1)


@main.command()
def info() -> None:
    """Show system information and dependencies."""
    table = Table(title="SiNE System Information")
    table.add_column("Component", style="cyan")
    table.add_column("Status")
    table.add_column("Details", style="dim")

    # Python version
    import sys

    table.add_row("Python", f"[green]{sys.version.split()[0]}[/]", sys.executable)

    # Sionna
    from sine.channel.sionna_engine import get_sionna_import_error, is_sionna_available

    if is_sionna_available():
        table.add_row("Sionna", "[green]Available[/]", "GPU acceleration enabled")
    else:
        error = get_sionna_import_error() or "Not installed"
        table.add_row("Sionna", "[yellow]Not available[/]", error[:50])

    # TensorFlow GPU
    try:
        import tensorflow as tf

        gpus = tf.config.list_physical_devices("GPU")
        if gpus:
            table.add_row("TensorFlow GPU", f"[green]{len(gpus)} GPU(s)[/]", str(gpus[0]))
        else:
            table.add_row("TensorFlow GPU", "[yellow]No GPU[/]", "CPU only")
    except ImportError:
        table.add_row("TensorFlow", "[dim]Not installed[/]", "")

    # Containerlab
    from sine.topology.manager import check_containerlab_installed, get_containerlab_version

    if check_containerlab_installed():
        version = get_containerlab_version() or "Unknown version"
        table.add_row("Containerlab", "[green]Installed[/]", version)
    else:
        table.add_row("Containerlab", "[red]Not installed[/]", "Required for deployment")

    # Docker
    try:
        import docker

        client = docker.from_env()
        version = client.version()["Version"]
        table.add_row("Docker", f"[green]{version}[/]", "")
    except Exception as e:
        table.add_row("Docker", "[red]Error[/]", str(e)[:30])

    # tc (traffic control)
    from sine.topology.netem import check_tc_available

    if check_tc_available():
        table.add_row("tc (netem)", "[green]Available[/]", "")
    else:
        table.add_row("tc (netem)", "[red]Not available[/]", "Required for network emulation")

    console.print(table)


if __name__ == "__main__":
    main()
