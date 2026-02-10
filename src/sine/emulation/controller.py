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

import httpx

from sine.config.loader import TopologyLoader
from sine.config.schema import NetworkTopology, WirelessParams, parse_endpoint
from sine.emulation.cleanup import CleanupGenerator
from sine.scene.builder import SceneBuilder
from sine.topology.manager import ContainerlabManager
from sine.topology.netem import NetemConfigurator, NetemParams, check_sudo_available
from sine.topology.shared_netem import PerDestinationConfig, SharedNetemConfigurator

logger = logging.getLogger(__name__)


class EmulationError(Exception):
    """Error during emulation."""

    pass


class EmulationController:
    """Main SiNE emulation controller."""

    def __init__(self, topology_path: str | Path, channel_server_url: str | None = None):
        """
        Initialize controller with path to topology file.

        Args:
            topology_path: Path to network.yaml file
            channel_server_url: Optional channel server URL to override YAML config
        """
        self.topology_path = Path(topology_path)
        self.loader = TopologyLoader(topology_path)
        self.config: NetworkTopology | None = None
        self.clab_manager: ContainerlabManager | None = None
        self.netem_config = NetemConfigurator()
        self.scene_builder = SceneBuilder()
        self.channel_server_url: str = "http://localhost:8000"
        self._channel_server_override: str | None = channel_server_url  # CLI override
        self._running = False
        self._link_states: dict[tuple[str, str], dict] = {}  # Stores netem and RF metrics
        self._link_mcs_info: dict[tuple[str, str], dict] = {}  # MCS info for each link
        self._mobility_task: asyncio.Task | None = None
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

        # Use CLI override if provided, otherwise use YAML config
        if self._channel_server_override:
            self.channel_server_url = self._channel_server_override
            logger.info(f"Using channel server from CLI: {self.channel_server_url}")
        else:
            self.channel_server_url = self.config.topology.channel_server
            logger.info(f"Using channel server from YAML: {self.channel_server_url}")

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
            sine_config_dict = self.config.model_dump()

            # Detect shared bridge mode
            bridge_config = sine_config_dict.get("topology", {}).get("shared_bridge")
            if bridge_config and bridge_config.get("enabled"):
                logger.info("Using shared bridge topology generation")
                clab_topo = self.clab_manager.generate_shared_bridge_topology(sine_config_dict)
            else:
                logger.info("Using point-to-point topology generation")
                clab_topo = self.clab_manager.generate_clab_topology(sine_config_dict)

            # Deploy with config for IP assignment in bridge mode
            self.clab_manager.deploy(clab_topo, sine_config_dict)
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
        """Check if topology has any wireless links (P2P or shared bridge)."""
        # Check for shared bridge mode (always wireless)
        if self.config.topology.shared_bridge and self.config.topology.shared_bridge.enabled:
            return True

        # Check for P2P wireless links
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

    async def _update_shared_bridge_links(self) -> None:
        """Compute and apply per-destination netem for shared bridge mode."""
        bridge_config = self.config.topology.shared_bridge
        if not bridge_config:
            return

        nodes = bridge_config.nodes
        interface_name = bridge_config.interface_name

        logger.info(
            f"Computing all-to-all links for shared bridge: "
            f"{len(nodes)} nodes, {len(nodes) * (len(nodes) - 1)} directional links"
        )

        # 1. Build all-to-all link list for channel computation
        wireless_links = []
        for tx_node in nodes:
            for rx_node in nodes:
                if tx_node == rx_node:
                    continue  # Skip self-links

                tx_iface_config = self.config.topology.nodes[tx_node].interfaces[
                    interface_name
                ]
                rx_iface_config = self.config.topology.nodes[rx_node].interfaces[
                    interface_name
                ]

                wireless_links.append(
                    {
                        "tx_node": tx_node,
                        "rx_node": rx_node,
                        "tx_params": tx_iface_config.wireless,
                        "rx_params": rx_iface_config.wireless,
                    }
                )

        # 2. Batch compute all link conditions
        link_requests = []
        for link_info in wireless_links:
            tx_params = link_info["tx_params"]
            rx_params = link_info["rx_params"]

            request = self._build_channel_request(
                tx_node=link_info["tx_node"],
                rx_node=link_info["rx_node"],
                tx_params=tx_params,
                rx_params=rx_params,
            )

            link_requests.append(request)

        # Get scene configuration
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
                    "enable_sinr": self.config.topology.enable_sinr,
                    "active_states": self._build_active_states_dict(),
                },
            )
            if response.status_code != 200:
                logger.error(f"Channel server error response: {response.text}")
            response.raise_for_status()
            results = response.json()["results"]

        logger.info(f"Computed {len(results)} link conditions")

        # 3. Build per-node destination maps
        per_node_config: dict[str, PerDestinationConfig] = {}
        ip_map: dict[str, str] = {}

        # Get IP addresses (strip CIDR suffix if present)
        for node_name in nodes:
            ip_address = self.config.topology.nodes[node_name].interfaces[
                interface_name
            ].ip_address
            if ip_address:
                # Strip /XX CIDR notation for use in tc flower filters
                # Example: "192.168.100.1/24" -> "192.168.100.1"
                ip_only = ip_address.split("/")[0] if "/" in ip_address else ip_address
                ip_map[node_name] = ip_only

        # Initialize per-node configs
        for tx_node in nodes:
            per_node_config[tx_node] = PerDestinationConfig(
                node=tx_node,
                interface=interface_name,
                default_params=NetemParams(
                    delay_ms=1.0, jitter_ms=0.0, loss_percent=0.0, rate_mbps=1000.0
                ),
                dest_params={},
            )

        # Populate destination parameters and store link states
        for i, link_info in enumerate(wireless_links):
            tx_node = link_info["tx_node"]
            rx_node = link_info["rx_node"]
            rx_ip = ip_map.get(rx_node)

            if not rx_ip:
                logger.error(f"No IP address for {rx_node}, skipping")
                continue

            result = results[i]

            # Note: TDMA throughput multiplier already applied by channel server
            # (see server.py:703 - netem_rate_mbps includes slot ownership)
            netem_params = NetemParams(
                delay_ms=result["netem_delay_ms"],
                jitter_ms=result["netem_jitter_ms"],
                loss_percent=result["netem_loss_percent"],
                rate_mbps=result["netem_rate_mbps"],
            )

            per_node_config[tx_node].dest_params[rx_ip] = netem_params

            # Store link state for deployment summary
            self._link_states[(tx_node, rx_node)] = {
                "netem": netem_params,
                "rf": {
                    "snr_db": result.get("snr_db"),
                    "sinr_db": result.get("sinr_db"),  # SINR when MAC model present
                    "path_loss_db": result.get("path_loss_db"),
                    "per": result.get("per"),
                    "rx_power_dbm": result.get("rx_power_dbm"),
                    "mac_model_type": result.get("mac_model_type"),  # CSMA, TDMA, or None
                },
            }

            # Store MCS info if available
            if result.get("selected_mcs_index") is not None:
                self._link_mcs_info[(tx_node, rx_node)] = {
                    "mcs_index": result.get("selected_mcs_index"),
                    "modulation": result.get("selected_modulation"),
                    "code_rate": result.get("selected_code_rate"),
                    "fec_type": result.get("selected_fec_type"),
                    "bandwidth_mhz": result.get("selected_bandwidth_mhz"),
                }

        # 4. Apply per-destination netem to all nodes
        configurator = SharedNetemConfigurator(self.clab_manager)

        for node_name, config in per_node_config.items():
            success = configurator.apply_per_destination_netem(config)
            if not success:
                logger.error(f"Failed to apply per-dest netem to {node_name}")
                self._netem_failures.append((node_name, "shared_bridge"))

        logger.info(
            f"Applied per-destination netem to {len(per_node_config)} nodes "
            f"in shared bridge mode"
        )

    async def _update_all_links(self) -> None:
        """Update channel conditions for all links (point-to-point or shared bridge)."""
        # Detect shared bridge mode
        bridge_config = self.config.topology.shared_bridge
        if bridge_config and bridge_config.enabled:
            logger.info("Using shared bridge link update")
            await self._update_shared_bridge_links()
            return

        # Point-to-point mode
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

            # BIDIRECTIONAL COMPUTATION for P2P links
            # Compute both directions independently with correct receiver NF

            # Direction 1: node1 → node2 (uses node2's RX noise figure)
            request_12 = self._build_channel_request(
                tx_node=node1_name,
                rx_node=node2_name,
                tx_params=wireless1,
                rx_params=wireless2,
            )

            link_requests.append(request_12)

            # Direction 2: node2 → node1 (uses node1's RX noise figure)
            request_21 = self._build_channel_request(
                tx_node=node2_name,
                rx_node=node1_name,
                tx_params=wireless2,
                rx_params=wireless1,
            )

            link_requests.append(request_21)

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
                    "enable_sinr": self.config.topology.enable_sinr,
                    "active_states": self._build_active_states_dict(),
                },
            )
            response.raise_for_status()
            results = response.json()

        # Apply netem configurations
        # Note: TDMA throughput multiplier already applied by channel server
        for result in results.get("results", []):
            await self._apply_wireless_link_config(result)

        logger.info(
            f"Updated {len(results.get('results', []))} wireless link(s) in "
            f"{results.get('computation_time_ms', 0):.1f}ms"
        )

    def _build_active_states_dict(self) -> dict[str, bool]:
        """Build active states dictionary from interface configurations.

        Returns:
            Dictionary mapping "node:interface" to is_active boolean.
            Example: {"node1:eth1": True, "node1:eth2": False, "node2:eth1": True}
        """
        active_states = {}
        for node_name, node_config in self.config.topology.nodes.items():
            if node_config.interfaces:
                for iface_name, iface_config in node_config.interfaces.items():
                    if iface_config.wireless:
                        key = f"{node_name}:{iface_name}"
                        active_states[key] = iface_config.wireless.is_active
        return active_states

    def _build_channel_request(
        self,
        tx_node: str,
        rx_node: str,
        tx_params: WirelessParams,
        rx_params: WirelessParams,
    ) -> dict:
        """
        Build a channel computation request dictionary for the batch compute endpoint.

        Args:
            tx_node: Transmitter node name
            rx_node: Receiver node name
            tx_params: Wireless configuration for transmitter interface
            rx_params: Wireless configuration for receiver interface

        Returns:
            Dictionary with all fields required by the channel server's /compute/batch endpoint,
            including:
            - Core link parameters (positions, power, gains, antenna config, frequencies)
            - Either adaptive MCS (mcs_table_path, mcs_hysteresis_db) OR
              fixed modulation (modulation, fec_type, fec_code_rate)
            - Optional MAC model configuration (CSMA or TDMA)

        Note:
            - Antenna gain defaults to 0.0 if not specified
            - Antenna pattern defaults to "iso" if not specified
            - Polarization defaults to "V" if not specified
            - Uses transmitter's frequency/bandwidth and receiver's noise figure
        """
        # Build core request fields
        request = {
            "tx_node": tx_node,
            "rx_node": rx_node,
            "tx_position": {
                "x": tx_params.position.x,
                "y": tx_params.position.y,
                "z": tx_params.position.z,
            },
            "rx_position": {
                "x": rx_params.position.x,
                "y": rx_params.position.y,
                "z": rx_params.position.z,
            },
            "tx_power_dbm": tx_params.rf_power_dbm,
            "tx_gain_dbi": (
                tx_params.antenna_gain_dbi if tx_params.antenna_gain_dbi is not None else 0.0
            ),
            "rx_gain_dbi": (
                rx_params.antenna_gain_dbi if rx_params.antenna_gain_dbi is not None else 0.0
            ),
            "antenna_pattern": (
                tx_params.antenna_pattern.value if tx_params.antenna_pattern else "iso"
            ),
            "polarization": (
                tx_params.polarization.value if tx_params.polarization else "V"
            ),
            "frequency_hz": tx_params.frequency_hz,
            "bandwidth_hz": tx_params.bandwidth_hz,
            "rx_frequency_hz": rx_params.frequency_hz,
            "rx_bandwidth_hz": rx_params.bandwidth_hz,
            "noise_figure_db": rx_params.noise_figure_db,
        }

        # Add MCS table OR fixed modulation parameters
        if tx_params.uses_adaptive_mcs:
            request["mcs_table_path"] = tx_params.mcs_table
            request["mcs_hysteresis_db"] = tx_params.mcs_hysteresis_db
        else:
            request["modulation"] = (
                tx_params.modulation.value if tx_params.modulation else None
            )
            request["fec_type"] = (
                tx_params.fec_type.value if tx_params.fec_type else None
            )
            request["fec_code_rate"] = tx_params.fec_code_rate

        # Add MAC model configuration (CSMA or TDMA)
        mac_model = None
        if tx_params.csma and tx_params.csma.enabled:
            mac_model = {
                "type": "csma",
                "carrier_sense_range_multiplier": tx_params.csma.carrier_sense_range_multiplier,
                "traffic_load": tx_params.csma.traffic_load,
                "communication_range_snr_threshold_db": tx_params.csma.communication_range_snr_threshold_db,
            }
        elif tx_params.tdma and tx_params.tdma.enabled:
            mac_model = {
                "type": "tdma",
                "frame_duration_ms": tx_params.tdma.frame_duration_ms,
                "num_slots": tx_params.tdma.num_slots,
                "slot_assignment_mode": tx_params.tdma.slot_assignment_mode,
                "fixed_slot_map": tx_params.tdma.fixed_slot_map,
                "slot_probability": tx_params.tdma.slot_probability,
            }

        if mac_model:
            request["mac_model"] = mac_model

        return request

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
            # Store with consistent structure (no RF metrics for fixed links)
            self._link_states[(node1_name, node2_name)] = {
                "netem": params1,
                "rf": None,  # Fixed links don't have RF computation
            }
            logger.debug(
                f"Applied fixed netem to {node1_name}<->{node2_name}: "
                f"delay={params1.delay_ms:.1f}ms, loss={params1.loss_percent:.2f}%, "
                f"rate={params1.rate_mbps:.1f}Mbps"
            )

    def _validate_channel_result(self, result: dict, link_id: str) -> None:
        """Validate channel server response for suspicious values."""
        required_fields = [
            "tx_node",
            "rx_node",
            "netem_delay_ms",
            "netem_jitter_ms",
            "netem_loss_percent",
            "netem_rate_mbps",
            "snr_db",
            "per",
            "path_loss_db",
        ]

        # Check all required fields present
        for field in required_fields:
            if field not in result:
                raise ValueError(
                    f"Channel server missing field '{field}' for link {link_id}"
                )

        # Sanity checks for RF metrics
        snr = result["snr_db"]
        loss_pct = result["netem_loss_percent"]

        if snr > 50.0:
            logger.warning(
                f"Link {link_id}: SNR={snr:.1f} dB is unusually high "
                f"(possible antenna gain double-counting)"
            )

        if snr < -20.0:
            logger.warning(
                f"Link {link_id}: SNR={snr:.1f} dB is very low (link likely unusable)"
            )

        if snr > 25.0 and loss_pct > 10.0:
            logger.warning(
                f"Link {link_id}: High SNR ({snr:.1f} dB) but high loss "
                f"({loss_pct:.1f}%) - possible BER calculation error"
            )

    async def _apply_wireless_link_config(self, channel_result: dict) -> None:
        """Apply netem configuration for a wireless link from channel server result."""
        tx_node = channel_result["tx_node"]
        rx_node = channel_result["rx_node"]
        link_id = f"{tx_node}→{rx_node}"

        # Validate response
        self._validate_channel_result(channel_result, link_id)

        # Log RF metrics for debugging
        logger.debug(
            f"Link {link_id} RF metrics: "
            f"SNR={channel_result['snr_db']:.1f} dB, "
            f"Rx_power={channel_result.get('received_power_dbm', 'N/A')} dBm, "
            f"Path_loss={channel_result['path_loss_db']:.1f} dB, "
            f"BER={channel_result.get('ber', 'N/A')}, "
            f"PER={channel_result['per']:.4f}"
        )

        # Apply minimum and maximum thresholds with logging
        delay_ms = channel_result["netem_delay_ms"]
        rate_mbps = channel_result["netem_rate_mbps"]

        # Minimum thresholds
        if delay_ms < 0.1:
            logger.debug(
                f"Link {link_id}: Correcting delay {delay_ms:.4f}ms → 0.1ms "
                f"(minimum threshold)"
            )
            delay_ms = 0.1

        if rate_mbps < 0.1:
            logger.warning(
                f"Link {link_id}: Very low rate {rate_mbps:.4f} Mbps → 0.1 Mbps "
                f"(link nearly unusable, SNR={channel_result['snr_db']:.1f} dB)"
            )
            rate_mbps = 0.1

        # Maximum thresholds
        if delay_ms > 1000.0:
            logger.warning(
                f"Link {link_id}: Delay {delay_ms:.1f}ms > 1000ms (satellite orbit?) "
                f"- capping to 1000ms"
            )
            delay_ms = 1000.0

        if rate_mbps > 10000.0:
            logger.warning(
                f"Link {link_id}: Rate {rate_mbps:.1f} Mbps exceeds WiFi 6E theoretical max "
                f"- capping to 10000 Mbps"
            )
            rate_mbps = 10000.0

        # Create netem params from channel computation results
        params = NetemParams(
            delay_ms=delay_ms,
            jitter_ms=channel_result["netem_jitter_ms"],
            loss_percent=channel_result["netem_loss_percent"],
            rate_mbps=rate_mbps,
        )

        # Get container info
        tx_container = self.clab_manager.get_container_info(tx_node)
        rx_container = self.clab_manager.get_container_info(rx_node)

        if not tx_container or not rx_container:
            logger.warning(f"Container info not found for {tx_node} or {rx_node}")
            return

        # Find the interface for the TX node (egress direction)
        # In containerlab, interfaces are named eth1, eth2, etc.
        # We use the interface mapping to find the correct interface for each peer
        tx_interface = self._find_link_interface(tx_container, tx_node, rx_node)

        # BIDIRECTIONAL: Apply netem ONLY to TX side (egress)
        # The reverse direction will be handled by a separate channel computation
        # with tx_node and rx_node swapped
        tx_success = False

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
        else:
            logger.warning(
                f"No interface found for {tx_node} → {rx_node} link"
            )

        # Store state for change detection if netem succeeded
        if tx_success:
            # Store both netem and RF metrics
            self._link_states[(tx_node, rx_node)] = {
                "netem": params,
                "rf": {
                    "snr_db": channel_result["snr_db"],
                    "sinr_db": channel_result.get("sinr_db"),  # SINR when MAC model present
                    "path_loss_db": channel_result["path_loss_db"],
                    "per": channel_result["per"],
                    "rx_power_dbm": channel_result.get("received_power_dbm"),
                    "mac_model_type": channel_result.get("mac_model_type"),  # CSMA, TDMA, or None
                },
            }

            # Store MCS info if available
            mcs_info = {}
            if channel_result.get("selected_mcs_index") is not None:
                mcs_info = {
                    "mcs_index": channel_result.get("selected_mcs_index"),
                    "modulation": channel_result.get("selected_modulation"),
                    "code_rate": channel_result.get("selected_code_rate"),
                    "fec_type": channel_result.get("selected_fec_type"),
                    "bandwidth_mhz": channel_result.get("selected_bandwidth_mhz"),
                    "snr_db": channel_result.get("snr_db"),
                }
            else:
                # Fixed modulation - still store for display
                mcs_info = {
                    "modulation": channel_result.get("selected_modulation"),
                    "code_rate": channel_result.get("selected_code_rate"),
                    "fec_type": channel_result.get("selected_fec_type"),
                    "snr_db": channel_result.get("snr_db"),
                }
            self._link_mcs_info[(tx_node, rx_node)] = mcs_info

            # Log with MCS info if available
            mcs_str = ""
            if channel_result.get("selected_mcs_index") is not None:
                mcs_str = f", MCS{channel_result['selected_mcs_index']}"
            logger.debug(
                f"Applied netem to {tx_node}<->{rx_node}: "
                f"delay={params.delay_ms:.1f}ms, loss={params.loss_percent:.2f}%, "
                f"rate={params.rate_mbps:.1f}Mbps{mcs_str}"
            )

    def _find_link_interface(
        self, container_info: dict, node_name: str, peer_node: str
    ) -> str | None:
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
            Dictionary mapping link names to their netem parameters and RF metrics
        """
        status = {}
        for (tx, rx), link_state in self._link_states.items():
            link_name = f"{tx}→{rx}"  # Directional for bidirectional computation
            status[link_name] = {
                "netem": link_state["netem"].to_dict(),
                "rf": link_state["rf"],
            }
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
        # Detect shared bridge mode
        is_shared_bridge = (
            self.config.topology.shared_bridge
            and self.config.topology.shared_bridge.enabled
        )

        summary = {
            "topology_name": self.config.name if self.config else "Unknown",
            "mode": "shared_bridge" if is_shared_bridge else "point_to_point",
            "sinr_enabled": self.config.topology.enable_sinr if self.config else False,
            "containers": [],
            "links": [],
        }

        # Add shared bridge info
        if is_shared_bridge:
            summary["shared_bridge"] = {
                "name": self.config.topology.shared_bridge.name,
                "nodes": self.config.topology.shared_bridge.nodes,
                "interface": self.config.topology.shared_bridge.interface_name,
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
                # Add wireless positions and IPs if available (from interfaces)
                short_name = name.replace(f"clab-{self.config.name}-", "")
                node = self.config.topology.nodes.get(short_name)
                if node and node.interfaces:
                    # Collect positions and IPs from all wireless interfaces
                    positions = {}
                    ips = {}
                    for iface_name, iface_config in node.interfaces.items():
                        if iface_config.wireless:
                            positions[iface_name] = {
                                "x": iface_config.wireless.position.x,
                                "y": iface_config.wireless.position.y,
                                "z": iface_config.wireless.position.z,
                            }
                        if iface_config.ip_address:
                            ips[iface_name] = iface_config.ip_address
                    if positions:
                        container_info["positions"] = positions
                    if ips:
                        container_info["ips"] = ips
                summary["containers"].append(container_info)

        # Get link states with interface information
        for (tx, rx), link_state in self._link_states.items():
            params = link_state["netem"]
            rf_metrics = link_state["rf"]

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

            # Format link with interfaces: "node1 (eth1) → node2 (eth1)" (directional)
            tx_str = f"{tx} ({tx_iface})" if tx_iface else tx
            rx_str = f"{rx} ({rx_iface})" if rx_iface else rx

            link_info = {
                "link": f"{tx_str} → {rx_str}",  # Directional arrow for bidirectional computation
                "type": link_type,
                "tx_node": tx,
                "rx_node": rx,
                "tx_interface": tx_iface,
                "rx_interface": rx_iface,
                "delay_ms": params.delay_ms,
                "jitter_ms": params.jitter_ms,
                "loss_percent": params.loss_percent,
                "rate_mbps": params.rate_mbps,
            }

            # Add RF metrics if available (wireless links only)
            if rf_metrics:
                link_info["snr_db"] = rf_metrics["snr_db"]
                # Add SINR if available (MAC model case)
                if rf_metrics.get("sinr_db") is not None:
                    link_info["sinr_db"] = rf_metrics["sinr_db"]
                if rf_metrics.get("mac_model_type"):
                    link_info["mac_model_type"] = rf_metrics["mac_model_type"]
                link_info["path_loss_db"] = rf_metrics["path_loss_db"]
                link_info["per"] = rf_metrics["per"]
                if rf_metrics["rx_power_dbm"] is not None:
                    link_info["rx_power_dbm"] = rf_metrics["rx_power_dbm"]

            # Add MCS info if available
            mcs_info = self._link_mcs_info.get((tx, rx), {})
            if mcs_info:
                link_info["modulation"] = mcs_info.get("modulation")
                link_info["code_rate"] = mcs_info.get("code_rate")
                link_info["fec_type"] = mcs_info.get("fec_type")
                if mcs_info.get("mcs_index") is not None:
                    link_info["mcs_index"] = mcs_info.get("mcs_index")
                if mcs_info.get("bandwidth_mhz") is not None:
                    link_info["bandwidth_mhz"] = mcs_info.get("bandwidth_mhz")

            summary["links"].append(link_info)

        return summary
