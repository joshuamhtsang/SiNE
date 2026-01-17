"""
Containerlab topology management.

Handles:
- Converting SiNE topology to Containerlab format
- Deploying and destroying topologies
- Discovering container information
"""

import json
import logging
import subprocess
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


class ContainerlabError(Exception):
    """Error interacting with Containerlab."""

    pass


class ContainerlabManager:
    """Manage Containerlab topology deployment."""

    def __init__(self, topology_path: str | Path):
        """
        Initialize manager with path to SiNE topology file.

        Args:
            topology_path: Path to network.yaml file
        """
        self.topology_path = Path(topology_path)
        self._deployed = False
        self._container_info: dict[str, dict] = {}
        self._clab_topology_path: Path | None = None
        self._lab_name: str | None = None
        # Interface mapping: (node, peer_node) -> interface_name
        # This enables correct interface selection for MANET topologies
        self._interface_mapping: dict[tuple[str, str], str] = {}

    def generate_clab_topology(self, sine_config: dict) -> dict:
        """
        Convert SiNE topology to Containerlab format.

        SiNE extends Containerlab with wireless parameters. We strip those
        and create a pure Containerlab YAML.

        Args:
            sine_config: SiNE NetworkTopology as dict

        Returns:
            Containerlab topology dictionary
        """
        clab_topology = {
            "name": sine_config["name"],
            "topology": {"nodes": {}, "links": []},
        }

        if sine_config.get("prefix"):
            clab_topology["prefix"] = sine_config["prefix"]

        # Store lab name for later
        self._lab_name = sine_config["name"]

        topology_def = sine_config.get("topology", {})

        # Convert nodes (strip wireless params)
        for node_name, node_config in topology_def.get("nodes", {}).items():
            clab_node = {
                "kind": node_config.get("kind", "linux"),
                "image": node_config.get("image", "alpine:latest"),
            }
            if node_config.get("cmd"):
                clab_node["cmd"] = node_config["cmd"]
            if node_config.get("binds"):
                clab_node["binds"] = node_config["binds"]
            if node_config.get("env"):
                clab_node["env"] = node_config["env"]
            if node_config.get("exec"):
                clab_node["exec"] = node_config["exec"]

            clab_topology["topology"]["nodes"][node_name] = clab_node

        # Convert links to veth links
        # Containerlab link format: endpoints: ["node1:eth1", "node2:eth1"]
        # Endpoints must be in "node:interface" format (validated by schema)

        # Clear any previous interface mapping
        self._interface_mapping = {}

        for link_def in topology_def.get("links", []):
            endpoints = link_def.get("endpoints", [])
            if len(endpoints) != 2:
                continue

            # Parse endpoints - interface specification is required
            node1, iface1 = self._parse_endpoint(endpoints[0])
            node2, iface2 = self._parse_endpoint(endpoints[1])

            # Store interface mapping for later use
            # node1 uses iface1 to reach node2, and vice versa
            self._interface_mapping[(node1, node2)] = iface1
            self._interface_mapping[(node2, node1)] = iface2

            link = {"endpoints": [f"{node1}:{iface1}", f"{node2}:{iface2}"]}
            clab_topology["topology"]["links"].append(link)

            logger.debug(
                f"Link {node1}<->{node2}: {node1}:{iface1} <-> {node2}:{iface2}"
            )

        return clab_topology

    def generate_shared_bridge_topology(self, sine_config: dict) -> dict:
        """
        Generate containerlab topology with container-namespace bridge.

        Creates a container-namespace bridge (not host-namespace) which is
        automatically created by containerlab without manual pre-creation.

        Architecture:
        1. Parent container (bridge-host) to host the bridge
        2. Bridge node inside parent's namespace (name|parent syntax)
        3. Links with correct endpoint format (both sides have interfaces)

        Args:
            sine_config: SiNE NetworkTopology as dict

        Returns:
            Containerlab topology dictionary with container-namespace bridge
        """
        clab_topology = {
            "name": sine_config["name"],
            "topology": {"nodes": {}, "links": []},
        }

        if sine_config.get("prefix"):
            clab_topology["prefix"] = sine_config["prefix"]

        # Store lab name for later
        self._lab_name = sine_config["name"]

        topology_def = sine_config.get("topology", {})
        bridge_config = topology_def.get("shared_bridge")

        if not bridge_config or not bridge_config.get("enabled"):
            raise ContainerlabError(
                "generate_shared_bridge_topology called but shared_bridge not enabled"
            )

        bridge_name = bridge_config["name"]
        bridge_nodes = bridge_config["nodes"]
        interface_name = bridge_config.get("interface_name", "eth1")

        # Create parent container to host the bridge
        parent_node = "bridge-host"
        clab_topology["topology"]["nodes"][parent_node] = {
            "kind": "linux",
            "image": "alpine:latest"
        }
        logger.debug(f"Created bridge host node: {parent_node}")

        # Create container-namespace bridge with pipe syntax
        bridge_full_name = f"{bridge_name}|{parent_node}"
        clab_topology["topology"]["nodes"][bridge_full_name] = {
            "kind": "bridge",
            "network-mode": f"container:{parent_node}"
        }
        logger.debug(f"Created container-namespace bridge: {bridge_full_name}")

        # Add all nodes in broadcast domain
        for node_name in bridge_nodes:
            node_config = topology_def["nodes"][node_name]
            clab_node = {
                "kind": node_config.get("kind", "linux"),
                "image": node_config.get("image", "alpine:latest"),
            }
            if node_config.get("cmd"):
                clab_node["cmd"] = node_config["cmd"]
            if node_config.get("binds"):
                clab_node["binds"] = node_config["binds"]
            if node_config.get("env"):
                clab_node["env"] = node_config["env"]
            if node_config.get("exec"):
                clab_node["exec"] = node_config["exec"]

            clab_topology["topology"]["nodes"][node_name] = clab_node

        # Connect each node to bridge with correct endpoint format
        for node_name in bridge_nodes:
            bridge_interface = f"{node_name}-{interface_name}"  # Unique per node
            link = {
                "endpoints": [
                    f"{node_name}:{interface_name}",
                    f"{bridge_full_name}:{bridge_interface}"
                ]
            }
            clab_topology["topology"]["links"].append(link)

            logger.debug(
                f"Connected {node_name}:{interface_name} to "
                f"{bridge_full_name}:{bridge_interface}"
            )

        return clab_topology

    @staticmethod
    def _parse_endpoint(endpoint: str) -> tuple[str, str]:
        """
        Parse an endpoint string into (node_name, interface).

        Required format: "node:interface" (e.g., "node1:eth1")

        Args:
            endpoint: Endpoint string like "node1:eth1"

        Returns:
            Tuple of (node_name, interface)
        """
        parts = endpoint.split(":", 1)
        return (parts[0], parts[1])

    def deploy(self, clab_topology: dict, sine_config: dict | None = None) -> bool:
        """
        Deploy topology using containerlab.

        Args:
            clab_topology: Containerlab topology dictionary
            sine_config: Optional SiNE config dict for IP assignment in bridge mode

        Returns:
            True if deployment succeeded
        """
        # Write temporary topology file
        self._clab_topology_path = self.topology_path.parent / ".sine_clab_topology.yaml"

        with open(self._clab_topology_path, "w") as f:
            yaml.dump(clab_topology, f, default_flow_style=False)

        logger.info(f"Generated Containerlab topology: {self._clab_topology_path}")

        try:
            result = subprocess.run(
                ["containerlab", "deploy", "-t", str(self._clab_topology_path)],
                capture_output=True,
                text=True,
                check=True,
            )
            logger.info("Containerlab deployment succeeded")
            logger.debug(f"Deploy output: {result.stdout}")

            self._deployed = True
            self._discover_containers()

            # Apply IP addresses to all interfaces with ip_address defined
            if sine_config:
                topology_def = sine_config.get("topology", {})
                bridge_config = topology_def.get("shared_bridge")
                if bridge_config and bridge_config.get("enabled"):
                    logger.info("Applying IP addresses for shared bridge mode")
                    self.apply_bridge_ips(sine_config)
                else:
                    # For point-to-point mode, apply IPs if defined
                    logger.info("Applying IP addresses for point-to-point mode")
                    self.apply_interface_ips(sine_config)

            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Containerlab deployment failed: {e.stderr}")
            raise ContainerlabError(f"Deployment failed: {e.stderr}") from e
        except FileNotFoundError as e:
            raise ContainerlabError(
                "containerlab command not found. "
                "Install from: https://containerlab.dev/install/"
            ) from e

    def _get_bridge_subnet(self, sine_config: dict, bridge_config: dict) -> str:
        """
        Extract bridge subnet from node IPs in CIDR notation.

        Args:
            sine_config: SiNE NetworkTopology as dict
            bridge_config: Shared bridge configuration dict

        Returns:
            Bridge subnet string (e.g., '192.168.100.0/24')
        """
        import ipaddress

        interface_name = bridge_config.get("interface_name", "eth1")
        first_node = bridge_config["nodes"][0]
        first_ip_cidr = sine_config["topology"]["nodes"][first_node]["interfaces"][
            interface_name
        ]["ip_address"]

        # Parse CIDR notation and extract network
        ip_interface = ipaddress.ip_interface(first_ip_cidr)
        network = ip_interface.network
        return str(network)

    def apply_bridge_ips(self, sine_config: dict) -> dict[str, str]:
        """
        Apply user-specified IPs and routing to container interfaces in shared bridge mode.

        Args:
            sine_config: SiNE NetworkTopology as dict

        Returns:
            Dictionary mapping node_name to ip_address
        """
        topology_def = sine_config.get("topology", {})
        bridge_config = topology_def.get("shared_bridge")

        if not bridge_config or not bridge_config.get("enabled"):
            logger.warning("apply_bridge_ips called but shared_bridge not enabled")
            return {}

        interface_name = bridge_config.get("interface_name", "eth1")
        bridge_nodes = bridge_config["nodes"]
        ip_assignments = {}

        # Get bridge subnet for routing configuration
        bridge_subnet = self._get_bridge_subnet(sine_config, bridge_config)

        for node_name in bridge_nodes:
            node_config = topology_def["nodes"][node_name]
            interface_config = node_config["interfaces"][interface_name]
            ip_cidr = interface_config["ip_address"]

            # Store IP portion only for mapping (for tc filter compatibility)
            import ipaddress
            ip_only = str(ipaddress.ip_interface(ip_cidr).ip)
            ip_assignments[node_name] = ip_only

            # Apply IP to container interface
            container_info = self.get_container_info(node_name)
            if not container_info:
                logger.error(f"Container info not found for {node_name}")
                continue

            pid = container_info.get("pid")
            if not pid:
                logger.error(f"PID not found for {node_name}")
                continue

            try:
                # 1. Apply IP address (with CIDR notation)
                result = subprocess.run(
                    [
                        "sudo",
                        "nsenter",
                        "-t",
                        str(pid),
                        "-n",
                        "ip",
                        "addr",
                        "add",
                        ip_cidr,
                        "dev",
                        interface_name,
                    ],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    logger.info(f"Applied IP {ip_cidr} to {node_name}:{interface_name}")
                elif "File exists" in result.stderr:
                    logger.debug(f"IP {ip_cidr} already exists on {node_name}:{interface_name}")
                else:
                    logger.error(f"Failed to apply IP to {node_name}:{interface_name}: {result.stderr}")
                    continue

                # 2. Add route for bridge subnet
                result = subprocess.run(
                    [
                        "sudo",
                        "nsenter",
                        "-t",
                        str(pid),
                        "-n",
                        "ip",
                        "route",
                        "add",
                        bridge_subnet,
                        "dev",
                        interface_name,
                    ],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    logger.info(
                        f"Added route {bridge_subnet} via {interface_name} on {node_name}"
                    )
                elif "File exists" in result.stderr:
                    logger.debug(f"Route {bridge_subnet} already exists on {node_name}:{interface_name}")
                else:
                    logger.warning(
                        f"Failed to add route on {node_name}:{interface_name}: {result.stderr}"
                    )

            except Exception as e:
                logger.error(
                    f"Unexpected error configuring {node_name}:{interface_name}: {e}"
                )

        return ip_assignments

    def apply_interface_ips(self, sine_config: dict) -> dict[str, dict[str, str]]:
        """
        Apply user-specified IPs and routing to all container interfaces with ip_address defined.

        This method works for both shared bridge and point-to-point topologies.
        For each interface with an ip_address in CIDR notation:
        1. Applies the IP address to the interface
        2. Adds a route for the subnet via that interface

        Args:
            sine_config: SiNE NetworkTopology as dict

        Returns:
            Dictionary mapping node_name to {interface_name: ip_address}
        """
        import ipaddress

        topology_def = sine_config.get("topology", {})
        nodes = topology_def.get("nodes", {})
        ip_assignments: dict[str, dict[str, str]] = {}

        for node_name, node_config in nodes.items():
            interfaces = node_config.get("interfaces", {})
            node_ips: dict[str, str] = {}

            for interface_name, interface_config in interfaces.items():
                ip_cidr = interface_config.get("ip_address")
                if not ip_cidr:
                    continue

                # Parse CIDR to get IP and network
                try:
                    ip_interface_obj = ipaddress.ip_interface(ip_cidr)
                    ip_only = str(ip_interface_obj.ip)
                    subnet = str(ip_interface_obj.network)
                except ValueError as e:
                    logger.error(f"Invalid IP CIDR for {node_name}:{interface_name}: {ip_cidr} - {e}")
                    continue

                node_ips[interface_name] = ip_only

                # Apply IP to container interface
                container_info = self.get_container_info(node_name)
                if not container_info:
                    logger.error(f"Container info not found for {node_name}")
                    continue

                pid = container_info.get("pid")
                if not pid:
                    logger.error(f"PID not found for {node_name}")
                    continue

                try:
                    # 1. Apply IP address (with CIDR notation)
                    result = subprocess.run(
                        [
                            "sudo",
                            "nsenter",
                            "-t",
                            str(pid),
                            "-n",
                            "ip",
                            "addr",
                            "add",
                            ip_cidr,
                            "dev",
                            interface_name,
                        ],
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode == 0:
                        logger.info(f"Applied IP {ip_cidr} to {node_name}:{interface_name}")
                    elif "File exists" in result.stderr:
                        logger.debug(f"IP {ip_cidr} already exists on {node_name}:{interface_name}")
                    else:
                        logger.error(f"Failed to apply IP to {node_name}:{interface_name}: {result.stderr}")
                        continue

                    # 2. Add route for subnet via this interface
                    result = subprocess.run(
                        [
                            "sudo",
                            "nsenter",
                            "-t",
                            str(pid),
                            "-n",
                            "ip",
                            "route",
                            "add",
                            subnet,
                            "dev",
                            interface_name,
                        ],
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode == 0:
                        logger.info(f"Added route {subnet} via {interface_name} on {node_name}")
                    elif "File exists" in result.stderr:
                        logger.debug(f"Route {subnet} already exists on {node_name}:{interface_name}")
                    else:
                        logger.warning(f"Failed to add route on {node_name}:{interface_name}: {result.stderr}")

                except Exception as e:
                    logger.error(f"Unexpected error configuring {node_name}:{interface_name}: {e}")

            if node_ips:
                ip_assignments[node_name] = node_ips

        return ip_assignments

    def _discover_containers(self) -> None:
        """Discover deployed container information."""
        if not self._lab_name:
            return

        # Container names follow pattern: clab-<lab_name>-<node_name>
        prefix = f"clab-{self._lab_name}"

        try:
            import docker

            client = docker.from_env()

            for container in client.containers.list():
                if container.name.startswith(prefix):
                    node_name = container.name.replace(f"{prefix}-", "")
                    self._container_info[node_name] = {
                        "id": container.id,
                        "name": container.name,
                        "pid": container.attrs["State"]["Pid"],
                        "interfaces": self._get_container_interfaces(container),
                    }
                    logger.debug(f"Discovered container: {container.name}")

        except ImportError:
            logger.warning("docker package not installed, using subprocess fallback")
            self._discover_containers_subprocess()
        except Exception as e:
            logger.error(f"Failed to discover containers: {e}")

    def _discover_containers_subprocess(self) -> None:
        """Fallback container discovery using subprocess."""
        if not self._lab_name:
            return

        prefix = f"clab-{self._lab_name}"

        try:
            result = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                check=True,
            )

            for name in result.stdout.strip().split("\n"):
                if name.startswith(prefix):
                    node_name = name.replace(f"{prefix}-", "")

                    # Get container info
                    inspect = subprocess.run(
                        ["docker", "inspect", name],
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    info = json.loads(inspect.stdout)[0]

                    self._container_info[node_name] = {
                        "id": info["Id"],
                        "name": name,
                        "pid": info["State"]["Pid"],
                        "interfaces": [],  # Would need nsenter to get
                    }

        except Exception as e:
            logger.error(f"Subprocess container discovery failed: {e}")

    def _get_container_interfaces(self, container) -> list[str]:
        """Get network interfaces for a container."""
        try:
            result = container.exec_run("ip -j link show")
            if result.exit_code == 0:
                interfaces = json.loads(result.output)
                return [
                    iface["ifname"]
                    for iface in interfaces
                    if iface["ifname"] not in ["lo"]
                ]
        except Exception:
            pass
        return []

    def get_container_info(self, node_name: str) -> dict:
        """
        Get container info for a node.

        Args:
            node_name: Node name from topology

        Returns:
            Dictionary with container id, name, pid, interfaces
        """
        return self._container_info.get(node_name, {})

    def get_all_containers(self) -> dict[str, dict]:
        """Get info for all deployed containers."""
        return self._container_info.copy()

    def get_interface_for_peer(self, node: str, peer_node: str) -> str | None:
        """
        Get the interface on `node` that connects to `peer_node`.

        This is essential for MANET topologies where a node may have multiple
        wireless interfaces (eth1, eth2, etc.) connecting to different peers.

        Args:
            node: The node whose interface we want
            peer_node: The peer node at the other end of the link

        Returns:
            Interface name (e.g., "eth1") or None if no direct link exists
        """
        return self._interface_mapping.get((node, peer_node))

    def get_interface_mapping(self) -> dict[tuple[str, str], str]:
        """
        Get the full interface mapping.

        Returns:
            Dictionary mapping (node, peer_node) tuples to interface names
        """
        return self._interface_mapping.copy()

    def destroy(self) -> bool:
        """
        Destroy the deployed topology.

        Returns:
            True if destruction succeeded
        """
        if self._clab_topology_path and self._clab_topology_path.exists():
            try:
                result = subprocess.run(
                    [
                        "containerlab",
                        "destroy",
                        "-t",
                        str(self._clab_topology_path),
                        "--cleanup",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                logger.info("Containerlab topology destroyed")
                logger.debug(f"Destroy output: {result.stdout}")

                self._deployed = False
                self._container_info = {}

                # Clean up temp file
                self._clab_topology_path.unlink(missing_ok=True)
                self._clab_topology_path = None

                return True

            except subprocess.CalledProcessError as e:
                logger.error(f"Containerlab destroy failed: {e.stderr}")
                return False
        else:
            logger.warning("No topology file to destroy")
            return False

    @property
    def is_deployed(self) -> bool:
        """Check if topology is currently deployed."""
        return self._deployed

    @property
    def lab_name(self) -> str | None:
        """Get the lab name."""
        return self._lab_name


def check_containerlab_installed() -> bool:
    """Check if containerlab is installed."""
    try:
        result = subprocess.run(
            ["containerlab", "version"], capture_output=True, text=True
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def get_containerlab_version() -> str | None:
    """Get containerlab version if installed."""
    try:
        result = subprocess.run(
            ["containerlab", "version"], capture_output=True, text=True
        )
        if result.returncode == 0:
            # Parse version from output
            for line in result.stdout.split("\n"):
                if "version" in line.lower():
                    return line.strip()
        return None
    except FileNotFoundError:
        return None
