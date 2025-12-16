"""
SiNE Command Line Interface.

Commands:
- sine deploy <topology.yaml>  : Deploy and start emulation
- sine destroy <topology.yaml> : Destroy deployed emulation
- sine status                  : Show status of running emulations
- sine channel-server          : Start the channel computation server
- sine validate <topology.yaml>: Validate topology file
"""

import asyncio
import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.logging import RichHandler

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

    # Containers table
    if summary.get("containers"):
        container_table = Table(title="Deployed Containers")
        container_table.add_column("Container", style="cyan")
        container_table.add_column("Image")
        container_table.add_column("PID", style="dim")
        container_table.add_column("Interfaces", style="green")
        container_table.add_column("Position (x,y,z)")

        for c in summary["containers"]:
            interfaces = ", ".join(c.get("interfaces", [])) or "eth0"
            pos = ""
            if c.get("position"):
                p = c["position"]
                pos = f"({p['x']:.1f}, {p['y']:.1f}, {p['z']:.1f})"
            container_table.add_row(
                c.get("name", ""),
                c.get("image", ""),
                str(c.get("pid", "")),
                interfaces,
                pos,
            )

        console.print(container_table)

    # Wireless links table
    if summary.get("wireless_links"):
        console.print()
        link_table = Table(title="Wireless Link Parameters (netem)")
        link_table.add_column("Link", style="cyan")
        link_table.add_column("Delay", justify="right")
        link_table.add_column("Jitter", justify="right")
        link_table.add_column("Loss %", justify="right")
        link_table.add_column("Rate", justify="right")

        for link in summary["wireless_links"]:
            link_table.add_row(
                link["link"],
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
def deploy(topology: Path, channel_server: str) -> None:
    """Deploy wireless network emulation from topology file.

    TOPOLOGY is the path to a network.yaml file defining the emulation.
    """
    from sine.emulation.controller import EmulationController, EmulationError

    console.print(f"[bold blue]Deploying topology:[/] {topology}")

    controller = EmulationController(topology)

    async def run_emulation() -> None:
        try:
            success = await controller.start()
            if success:
                console.print("[bold green]Emulation deployed successfully![/]")

                # Print deployment summary
                summary = controller.get_deployment_summary()
                _print_deployment_summary(summary)

                console.print(f"\nCleanup script: {topology.parent / 'cleanup.sh'}")
                console.print("\n[dim]Press Ctrl+C to stop emulation[/]")

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
    from sine.topology.manager import ContainerlabManager, ContainerlabError

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

    # Print summary
    table = Table(title="Topology Summary")
    table.add_column("Property", style="cyan")
    table.add_column("Value")

    table.add_row("Name", config.name)
    table.add_row("Prefix", config.container_prefix)
    table.add_row("Nodes", str(len(config.topology.nodes)))
    table.add_row("Wireless Links", str(len(config.topology.wireless_links)))
    table.add_row("Scene Type", config.topology.scene.type)
    table.add_row("Channel Server", config.topology.channel_server)
    table.add_row("Mobility Poll", f"{config.topology.mobility_poll_ms}ms")

    console.print(table)

    # List nodes
    if config.topology.nodes:
        node_table = Table(title="Nodes")
        node_table.add_column("Name", style="cyan")
        node_table.add_column("Image")
        node_table.add_column("Position")
        node_table.add_column("Wireless")

        for name, node in config.topology.nodes.items():
            pos = ""
            wireless = "No"
            if node.wireless:
                pos = f"({node.wireless.position.x:.1f}, {node.wireless.position.y:.1f}, {node.wireless.position.z:.1f})"
                wireless = f"{node.wireless.modulation.value}, {node.wireless.fec_type.value}"
            node_table.add_row(name, node.image, pos, wireless)

        console.print(node_table)

    # Validate scene
    if config.topology.scene.type == "default":
        try:
            builder = SceneBuilder()
            builder.load_default_scene()
            warnings = builder.validate_scene()
            if warnings:
                for w in warnings:
                    console.print(f"[yellow]⚠ Scene warning:[/] {w}")
            else:
                console.print("[green]✓ Default scene valid[/]")
        except Exception as e:
            console.print(f"[red]✗ Scene error:[/] {e}")
    elif config.topology.scene.file:
        scene_path = Path(config.topology.scene.file)
        if scene_path.exists():
            console.print(f"[green]✓ Custom scene exists:[/] {scene_path}")
        else:
            console.print(f"[red]✗ Custom scene not found:[/] {scene_path}")

    console.print("\n[green]Validation complete[/]")


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
    from sine.channel.sionna_engine import is_sionna_available, get_sionna_import_error

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
