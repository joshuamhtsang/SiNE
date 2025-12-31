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
import tempfile
from pathlib import Path
from typing import Optional, Union

import yaml

logger = logging.getLogger(__name__)


class ContainerlabError(Exception):
    """Error interacting with Containerlab."""

    pass


class ContainerlabManager:
    """Manage Containerlab topology deployment."""

    def __init__(self, topology_path: Union[str, Path]):
        """
        Initialize manager with path to SiNE topology file.

        Args:
            topology_path: Path to network.yaml file
        """
        self.topology_path = Path(topology_path)
        self._deployed = False
        self._container_info: dict[str, dict] = {}
        self._clab_topology_path: Optional[Path] = None
        self._lab_name: Optional[str] = None
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

            clab_topology["topology"]["nodes"][node_name] = clab_node

        # Convert wireless links to veth links
        # Containerlab link format: endpoints: ["node1:eth1", "node2:eth1"]
        #
        # Endpoints can be specified as:
        # - "node1" (auto-assign interface starting from eth1)
        # - "node1:eth2" (explicit interface assignment)
        interface_counters: dict[str, int] = {}

        # Clear any previous interface mapping
        self._interface_mapping = {}

        for wlink in topology_def.get("wireless_links", []):
            endpoints = wlink.get("endpoints", [])
            if len(endpoints) != 2:
                continue

            # Parse endpoints - may include interface specification
            node1, iface1 = self._parse_endpoint(endpoints[0])
            node2, iface2 = self._parse_endpoint(endpoints[1])

            # Auto-assign interfaces if not explicitly specified
            if iface1 is None:
                if_num1 = interface_counters.get(node1, 1)
                interface_counters[node1] = if_num1 + 1
                iface1 = f"eth{if_num1}"

            if iface2 is None:
                if_num2 = interface_counters.get(node2, 1)
                interface_counters[node2] = if_num2 + 1
                iface2 = f"eth{if_num2}"

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

    @staticmethod
    def _parse_endpoint(endpoint: str) -> tuple[str, Optional[str]]:
        """
        Parse an endpoint string into (node_name, interface).

        Supports two formats:
        - "node1" -> ("node1", None) - interface will be auto-assigned
        - "node1:eth1" -> ("node1", "eth1") - explicit interface

        Args:
            endpoint: Endpoint string like "node1" or "node1:eth1"

        Returns:
            Tuple of (node_name, interface_or_none)
        """
        if ":" in endpoint:
            parts = endpoint.split(":", 1)
            return (parts[0], parts[1])
        return (endpoint, None)

    def deploy(self, clab_topology: dict) -> bool:
        """
        Deploy topology using containerlab.

        Args:
            clab_topology: Containerlab topology dictionary

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
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Containerlab deployment failed: {e.stderr}")
            raise ContainerlabError(f"Deployment failed: {e.stderr}") from e
        except FileNotFoundError:
            raise ContainerlabError(
                "containerlab command not found. "
                "Install from: https://containerlab.dev/install/"
            )

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

    def get_interface_for_peer(self, node: str, peer_node: str) -> Optional[str]:
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
    def lab_name(self) -> Optional[str]:
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


def get_containerlab_version() -> Optional[str]:
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
