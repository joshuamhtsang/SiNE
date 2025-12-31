"""
Main emulation orchestrator for SiNE.

Coordinates:
1. Parse network.yaml topology
2. Load/build ray tracing scene
3. Deploy containers via Containerlab
4. Initialize channel computation
5. Configure netem on all links
6. Poll for mobility updates
7. Update netem when channel conditions change
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional, Union

import httpx

from sine.config.loader import TopologyLoader
from sine.config.schema import NetworkTopology, parse_endpoint
from sine.topology.manager import ContainerlabManager
from sine.topology.netem import NetemConfigurator, NetemParams, check_sudo_available
from sine.scene.builder import SceneBuilder
from sine.emulation.cleanup import CleanupGenerator

logger = logging.getLogger(__name__)


class EmulationError(Exception):
    """Error during emulation."""

    pass


class EmulationController:
    """Main SiNE emulation controller."""

    def __init__(self, topology_path: Union[str, Path]):
        """
        Initialize controller with path to topology file.

        Args:
            topology_path: Path to network.yaml file
        """
        self.topology_path = Path(topology_path)
        self.loader = TopologyLoader(topology_path)
        self.config: Optional[NetworkTopology] = None
        self.clab_manager: Optional[ContainerlabManager] = None
        self.netem_config = NetemConfigurator()
        self.scene_builder = SceneBuilder()
        self.channel_server_url: str = "http://localhost:8000"
        self._running = False
        self._link_states: dict[tuple[str, str], NetemParams] = {}
        self._mobility_task: Optional[asyncio.Task] = None
        self._netem_failures: list[tuple[str, str]] = []  # Track failed netem applications

    async def start(self) -> bool:
        """
        Start the emulation.

        Steps:
        1. Load and validate topology
        2. Deploy containers via Containerlab
        3. Initialize scene on channel server
        4. Compute initial channel conditions
        5. Configure netem on all links
        6. Start mobility polling loop

        Returns:
            True if emulation started successfully
        """
        logger.info(f"Starting emulation from {self.topology_path}")

        # Check sudo availability for netem configuration
        if not check_sudo_available():
            logger.warning("")
            logger.warning("=" * 80)
            logger.warning("SUDO ACCESS REQUIRED")
            logger.warning("=" * 80)
            logger.warning("")
            logger.warning("Network emulation (netem) requires sudo privileges to configure")
            logger.warning("traffic control (tc) in container network namespaces.")
            logger.warning("")
            logger.warning("Sudo is needed to:")
            logger.warning("  - Apply delay, jitter, and packet loss to wireless links")
            logger.warning("  - Set bandwidth rate limits based on channel conditions")
            logger.warning("")
            logger.warning("Please run this command with sudo:")
            logger.warning(f"  sudo uv run sine deploy {self.topology_path}")
            logger.warning("")
            logger.warning("Or configure passwordless sudo for nsenter and tc commands.")
            logger.warning("See README.md for setup instructions.")
            logger.warning("")
            logger.warning("=" * 80)
            logger.warning("")
            logger.warning("Continuing deployment WITHOUT netem configuration...")
            logger.warning("(Containers will be created but links will have no emulation)")
            logger.warning("")

        # Load topology
        try:
            self.config = self.loader.load()
            logger.info(f"Loaded topology: {self.config.name}")
        except Exception as e:
            logger.error(f"Failed to load topology: {e}")
            raise EmulationError(f"Failed to load topology: {e}") from e

        self.channel_server_url = self.config.topology.channel_server

        # Load scene (only required if there are wireless links)
        if self._has_wireless_links():
            try:
                scene_config = self.config.topology.scene
                self.scene_builder.load_scene(scene_config.file)
            except Exception as e:
                logger.error(f"Failed to load scene: {e}")
                raise EmulationError(f"Failed to load scene: {e}") from e
        else:
            logger.info("No wireless links - skipping scene loading")

        # Deploy containers via Containerlab
        try:
            self.clab_manager = ContainerlabManager(self.topology_path)
            clab_topo = self.clab_manager.generate_clab_topology(
                self.config.model_dump()
            )
            self.clab_manager.deploy(clab_topo)
            logger.info("Containerlab deployment succeeded")
        except Exception as e:
            logger.error(f"Failed to deploy containers: {e}")
            raise EmulationError(f"Failed to deploy containers: {e}") from e

        # Generate cleanup script
        try:
            cleanup_path = self.topology_path.parent / "cleanup.sh"
            CleanupGenerator(self.config).generate(cleanup_path)
            logger.info(f"Generated cleanup script: {cleanup_path}")
        except Exception as e:
            logger.warning(f"Failed to generate cleanup script: {e}")

        # Initialize channel server with scene (only for wireless links)
        if self._has_wireless_links():
            try:
                await self._initialize_scene()
            except Exception as e:
                logger.error(f"Failed to initialize scene on channel server: {e}")
                raise EmulationError(f"Failed to initialize channel server: {e}") from e

        # Compute initial channel conditions and configure netem
        try:
            await self._update_all_links()
        except Exception as e:
            logger.error(f"Failed to compute initial channels: {e}")
            raise EmulationError(f"Failed to compute channels: {e}") from e

        # Start mobility polling
        self._running = True
        self._mobility_task = asyncio.create_task(self._mobility_polling_loop())

        # Report any netem failures
        if self._netem_failures:
            logger.warning("")
            logger.warning("=" * 80)
            logger.warning("NETEM CONFIGURATION INCOMPLETE")
            logger.warning("=" * 80)
            logger.warning("")
            logger.warning(f"Failed to apply netem to {len(self._netem_failures)} wireless link(s):")
            for tx, rx in self._netem_failures:
                logger.warning(f"  - {tx} <-> {rx}")
            logger.warning("")
            logger.warning("These links will operate at full container bandwidth (~10+ Gbps)")
            logger.warning("without delay, jitter, or packet loss emulation.")
            logger.warning("")
            logger.warning("To fix this, destroy the emulation and redeploy with sudo:")
            logger.warning(f"  sudo uv run sine destroy {self.topology_path}")
            logger.warning(f"  sudo uv run sine deploy {self.topology_path}")
            logger.warning("")
            logger.warning("=" * 80)
            logger.warning("")

        logger.info("Emulation started successfully")
        return True

    async def stop(self) -> None:
        """Stop the emulation."""
        logger.info("Stopping emulation")

        self._running = False

        # Cancel mobility polling
        if self._mobility_task:
            self._mobility_task.cancel()
            try:
                await self._mobility_task
            except asyncio.CancelledError:
                pass

        # Destroy containers
        if self.clab_manager:
            self.clab_manager.destroy()

        logger.info("Emulation stopped")

    def _has_wireless_links(self) -> bool:
        """Check if topology has any wireless links."""
        for link in self.config.topology.links:
            node1, iface1 = parse_endpoint(link.endpoints[0])
            node = self.config.topology.nodes.get(node1)
            if node and node.interfaces and iface1 in node.interfaces:
                if node.interfaces[iface1].is_wireless:
                    return True
        return False

    async def _initialize_scene(self) -> None:
        """Initialize scene on channel server."""
        scene_config = self.config.topology.scene

        # Get frequency from first wireless interface
        frequency_hz = 5.18e9
        bandwidth_hz = 80e6

        for node in self.config.topology.nodes.values():
            if node.interfaces:
                for iface_config in node.interfaces.values():
                    if iface_config.wireless:
                        frequency_hz = iface_config.wireless.frequency_hz
                        bandwidth_hz = iface_config.wireless.bandwidth_hz
                        break
                else:
                    continue
                break

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.channel_server_url}/scene/load",
                json={
                    "scene_file": scene_config.file,
                    "frequency_hz": frequency_hz,
                    "bandwidth_hz": bandwidth_hz,
                },
            )
            response.raise_for_status()
            logger.info("Scene loaded on channel server")

    async def _update_all_links(self) -> None:
        """Update channel conditions for all links."""
        links = self.config.topology.links
        nodes = self.config.topology.nodes

        if not links:
            logger.info("No links to configure")
            return

        # Separate wireless and fixed links
        wireless_links = []
        fixed_links = []

        for link in links:
            node1_name, iface1 = parse_endpoint(link.endpoints[0])
            node1 = nodes.get(node1_name)

            if node1 and node1.interfaces and iface1 in node1.interfaces:
                if node1.interfaces[iface1].is_wireless:
                    wireless_links.append(link)
                else:
                    fixed_links.append(link)

        # Process fixed links directly (no channel server needed)
        for link in fixed_links:
            await self._apply_fixed_link(link)

        if fixed_links:
            logger.info(f"Configured {len(fixed_links)} fixed link(s)")

        # Process wireless links via channel server
        if not wireless_links:
            return

        # Build batch request for wireless links
        link_requests = []

        for link in wireless_links:
            node1_name, iface1 = parse_endpoint(link.endpoints[0])
            node2_name, iface2 = parse_endpoint(link.endpoints[1])
            node1 = nodes.get(node1_name)
            node2 = nodes.get(node2_name)

            if not node1 or not node2:
                logger.warning(f"Link references unknown nodes: {link.endpoints}")
                continue

            wireless1 = node1.interfaces[iface1].wireless
            wireless2 = node2.interfaces[iface2].wireless

            # Use node1 as TX, node2 as RX (will apply to both directions)
            link_requests.append(
                {
                    "tx_node": node1_name,
                    "rx_node": node2_name,
                    "tx_position": {
                        "x": wireless1.position.x,
                        "y": wireless1.position.y,
                        "z": wireless1.position.z,
                    },
                    "rx_position": {
                        "x": wireless2.position.x,
                        "y": wireless2.position.y,
                        "z": wireless2.position.z,
                    },
                    "tx_power_dbm": wireless1.rf_power_dbm,
                    "tx_gain_dbi": wireless1.antenna_gain_dbi,
                    "rx_gain_dbi": wireless2.antenna_gain_dbi,
                    "antenna_pattern": wireless1.antenna_pattern.value,
                    "polarization": wireless1.polarization.value,
                    "frequency_hz": wireless1.frequency_hz,
                    "bandwidth_hz": wireless1.bandwidth_hz,
                    "modulation": wireless1.modulation.value,
                    "fec_type": wireless1.fec_type.value,
                    "fec_code_rate": wireless1.fec_code_rate,
                }
            )

        if not link_requests:
            return

        # Send batch request to channel server
        scene_config = self.config.topology.scene

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.channel_server_url}/compute/batch",
                json={
                    "scene": {
                        "scene_file": scene_config.file,
                        "frequency_hz": link_requests[0]["frequency_hz"],
                        "bandwidth_hz": link_requests[0]["bandwidth_hz"],
                    },
                    "links": link_requests,
                },
            )
            response.raise_for_status()
            results = response.json()

        # Apply netem configurations
        for result in results.get("results", []):
            await self._apply_wireless_link_config(result)

        logger.info(
            f"Updated {len(results.get('results', []))} wireless link(s) in "
            f"{results.get('computation_time_ms', 0):.1f}ms"
        )

    async def _apply_fixed_link(self, link) -> None:
        """Apply fixed netem parameters for a link."""
        node1_name, iface1 = parse_endpoint(link.endpoints[0])
        node2_name, iface2 = parse_endpoint(link.endpoints[1])

        nodes = self.config.topology.nodes
        fixed1 = nodes[node1_name].interfaces[iface1].fixed_netem
        fixed2 = nodes[node2_name].interfaces[iface2].fixed_netem

        # Create NetemParams from fixed config for each endpoint
        params1 = NetemParams(
            delay_ms=fixed1.delay_ms,
            jitter_ms=fixed1.jitter_ms,
            loss_percent=fixed1.loss_percent,
            rate_mbps=fixed1.rate_mbps,
            correlation_percent=fixed1.correlation_percent,
        )
        params2 = NetemParams(
            delay_ms=fixed2.delay_ms,
            jitter_ms=fixed2.jitter_ms,
            loss_percent=fixed2.loss_percent,
            rate_mbps=fixed2.rate_mbps,
            correlation_percent=fixed2.correlation_percent,
        )

        # Get container info
        container1 = self.clab_manager.get_container_info(node1_name)
        container2 = self.clab_manager.get_container_info(node2_name)

        if not container1 or not container2:
            logger.warning(f"Container info not found for {node1_name} or {node2_name}")
            return

        # Apply netem on both sides
        success1 = False
        success2 = False

        success1 = self.netem_config.apply_config(
            container_name=container1["name"],
            interface=iface1,
            params=params1,
            pid=container1["pid"],
        )
        if not success1:
            logger.error(f"Failed to apply netem to {node1_name}:{iface1}")
            self._netem_failures.append((node1_name, node2_name))

        success2 = self.netem_config.apply_config(
            container_name=container2["name"],
            interface=iface2,
            params=params2,
            pid=container2["pid"],
        )
        if not success2:
            logger.error(f"Failed to apply netem to {node2_name}:{iface2}")
            if (node1_name, node2_name) not in self._netem_failures:
                self._netem_failures.append((node1_name, node2_name))

        # Store state for summary (use params1 as representative)
        if success1 or success2:
            self._link_states[(node1_name, node2_name)] = params1
            logger.debug(
                f"Applied fixed netem to {node1_name}<->{node2_name}: "
                f"delay={params1.delay_ms:.1f}ms, loss={params1.loss_percent:.2f}%, "
                f"rate={params1.rate_mbps:.1f}Mbps"
            )

    async def _apply_wireless_link_config(self, channel_result: dict) -> None:
        """Apply netem configuration for a wireless link from channel server result."""
        tx_node = channel_result["tx_node"]
        rx_node = channel_result["rx_node"]

        # Create netem params from channel computation results
        params = NetemParams(
            delay_ms=max(0.1, channel_result["netem_delay_ms"]),  # Min 0.1ms
            jitter_ms=channel_result["netem_jitter_ms"],
            loss_percent=channel_result["netem_loss_percent"],
            rate_mbps=max(0.1, channel_result["netem_rate_mbps"]),  # Min 0.1 Mbps
        )

        # Get container info
        tx_container = self.clab_manager.get_container_info(tx_node)
        rx_container = self.clab_manager.get_container_info(rx_node)

        if not tx_container or not rx_container:
            logger.warning(f"Container info not found for {tx_node} or {rx_node}")
            return

        # Find the interfaces for this link
        # In containerlab, interfaces are named eth1, eth2, etc.
        # We use the interface mapping to find the correct interface for each peer
        tx_interface = self._find_link_interface(tx_container, tx_node, rx_node)
        rx_interface = self._find_link_interface(rx_container, rx_node, tx_node)

        # Apply netem on both sides (wireless is bidirectional)
        tx_success = False
        rx_success = False

        if tx_interface:
            tx_success = self.netem_config.apply_config(
                container_name=tx_container["name"],
                interface=tx_interface,
                params=params,
                pid=tx_container["pid"],
            )
            if not tx_success:
                logger.error(
                    f"Failed to apply netem to {tx_node}:{tx_interface} "
                    f"(likely missing sudo privileges)"
                )
                self._netem_failures.append((tx_node, rx_node))

        if rx_interface:
            rx_success = self.netem_config.apply_config(
                container_name=rx_container["name"],
                interface=rx_interface,
                params=params,
                pid=rx_container["pid"],
            )
            if not rx_success:
                logger.error(
                    f"Failed to apply netem to {rx_node}:{rx_interface} "
                    f"(likely missing sudo privileges)"
                )
                if (tx_node, rx_node) not in self._netem_failures:
                    self._netem_failures.append((tx_node, rx_node))

        # Store state for change detection only if at least one side succeeded
        if tx_success or rx_success:
            self._link_states[(tx_node, rx_node)] = params
            logger.debug(
                f"Applied netem to {tx_node}<->{rx_node}: "
                f"delay={params.delay_ms:.1f}ms, loss={params.loss_percent:.2f}%, "
                f"rate={params.rate_mbps:.1f}Mbps"
            )

    def _find_link_interface(
        self, container_info: dict, node_name: str, peer_node: str
    ) -> Optional[str]:
        """
        Find interface on node that connects to peer_node.

        In containerlab, interfaces are named eth<N>.
        eth0 is reserved for management, so wireless links use eth1, eth2, etc.

        For MANET topologies with 3+ nodes, each node may have multiple wireless
        interfaces (eth1, eth2, etc.) connecting to different peers. We use the
        interface mapping from ContainerlabManager to find the correct one.

        Args:
            container_info: Container information dict
            node_name: Name of this node
            peer_node: Name of the peer node at the other end of the link

        Returns:
            Interface name (e.g., "eth1") or None if not found
        """
        # First, try to get the interface from the topology mapping
        # This is the correct approach for MANET topologies
        if self.clab_manager:
            mapped_interface = self.clab_manager.get_interface_for_peer(
                node_name, peer_node
            )
            if mapped_interface:
                return mapped_interface

        # Fallback: Find first non-management interface (for backwards compatibility)
        # This works for 2-node topologies but may be incorrect for 3+ nodes
        interfaces = container_info.get("interfaces", [])
        for iface in interfaces:
            if iface.startswith("eth") and iface != "eth0":
                logger.warning(
                    f"Using fallback interface {iface} for {node_name}->{peer_node} "
                    f"(interface mapping not found)"
                )
                return iface

        # If no interfaces found besides eth0, log warning and use eth1 as fallback
        logger.warning(
            f"No wireless interfaces found for {container_info.get('name', 'unknown')}, "
            f"using eth1 as fallback"
        )
        return "eth1"

    async def _mobility_polling_loop(self) -> None:
        """
        Poll for mobility updates at configured interval.

        Default: 100ms polling period
        """
        poll_interval = self.config.topology.mobility_poll_ms / 1000.0

        while self._running:
            await asyncio.sleep(poll_interval)

            # In a full implementation, this would:
            # 1. Query an external mobility model or API
            # 2. Update node positions
            # 3. Recompute channels if positions changed

            # For now, this is a placeholder for future mobility support

    async def update_node_position(
        self, node_name: str, interface: str, x: float, y: float, z: float
    ) -> None:
        """
        Update a node interface's position and recompute affected channels.

        Called by mobility handler when a node moves.

        Args:
            node_name: Name of the node to update
            interface: Interface name (e.g., "eth1")
            x: New X coordinate
            y: New Y coordinate
            z: New Z coordinate
        """
        node = self.config.topology.nodes.get(node_name)
        if node and node.interfaces and interface in node.interfaces:
            iface_config = node.interfaces[interface]
            if iface_config.wireless:
                iface_config.wireless.position.x = x
                iface_config.wireless.position.y = y
                iface_config.wireless.position.z = z

                logger.info(f"Updated position of {node_name}:{interface} to ({x}, {y}, {z})")

                # Recompute channels for all links involving this node
                await self._update_all_links()

    def get_link_status(self) -> dict[str, dict]:
        """
        Get current status of all wireless links.

        Returns:
            Dictionary mapping link names to their current netem parameters
        """
        status = {}
        for (tx, rx), params in self._link_states.items():
            link_name = f"{tx}<->{rx}"
            status[link_name] = params.to_dict()
        return status

    def get_container_status(self) -> dict[str, dict]:
        """
        Get status of all deployed containers.

        Returns:
            Dictionary with container information
        """
        if self.clab_manager:
            return self.clab_manager.get_all_containers()
        return {}

    @property
    def is_running(self) -> bool:
        """Check if emulation is currently running."""
        return self._running

    def get_deployment_summary(self) -> dict:
        """
        Get a summary of the deployment.

        Returns:
            Dictionary with deployment information including containers,
            network interfaces, and channel parameters.
        """
        summary = {
            "topology_name": self.config.name if self.config else "Unknown",
            "containers": [],
            "links": [],
        }

        # Get container info
        if self.clab_manager:
            containers = self.clab_manager.get_all_containers()
            for name, info in containers.items():
                container_info = {
                    "name": info.get("name", name),
                    "image": info.get("image", "unknown"),
                    "pid": info.get("pid"),
                    "interfaces": info.get("interfaces", []),
                    "ipv4": info.get("ipv4", ""),
                }
                # Add wireless positions if available (from interfaces)
                short_name = name.replace(f"clab-{self.config.name}-", "")
                node = self.config.topology.nodes.get(short_name)
                if node and node.interfaces:
                    # Collect positions from all wireless interfaces
                    positions = {}
                    for iface_name, iface_config in node.interfaces.items():
                        if iface_config.wireless:
                            positions[iface_name] = {
                                "x": iface_config.wireless.position.x,
                                "y": iface_config.wireless.position.y,
                                "z": iface_config.wireless.position.z,
                            }
                    if positions:
                        container_info["positions"] = positions
                summary["containers"].append(container_info)

        # Get link states with interface information
        for (tx, rx), params in self._link_states.items():
            # Get interface names from the mapping
            tx_iface = None
            rx_iface = None
            if self.clab_manager:
                tx_iface = self.clab_manager.get_interface_for_peer(tx, rx)
                rx_iface = self.clab_manager.get_interface_for_peer(rx, tx)

            # Determine link type from interface config
            link_type = "unknown"
            tx_node = self.config.topology.nodes.get(tx)
            if tx_node and tx_node.interfaces and tx_iface:
                if tx_iface in tx_node.interfaces:
                    link_type = "wireless" if tx_node.interfaces[tx_iface].is_wireless else "fixed"

            # Format link with interfaces: "node1 (eth1) <-> node2 (eth1)"
            tx_str = f"{tx} ({tx_iface})" if tx_iface else tx
            rx_str = f"{rx} ({rx_iface})" if rx_iface else rx

            summary["links"].append({
                "link": f"{tx_str} <-> {rx_str}",
                "type": link_type,
                "tx_node": tx,
                "rx_node": rx,
                "tx_interface": tx_iface,
                "rx_interface": rx_iface,
                "delay_ms": params.delay_ms,
                "jitter_ms": params.jitter_ms,
                "loss_percent": params.loss_percent,
                "rate_mbps": params.rate_mbps,
            })

        return summary
