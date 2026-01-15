"""
Per-destination netem configuration for shared bridge mode.

This module implements HTB (Hierarchical Token Bucket) + tc flower filters
for applying different netem parameters to each destination in a shared
broadcast domain.

Architecture:
    Root HTB qdisc (handle 1:)
      └── Parent class (1:1, unlimited rate)
           ├── Class 1:10 → Netem (to dest1) → flower filter (dst IP1)
           ├── Class 1:20 → Netem (to dest2) → flower filter (dst IP2)
           └── Class 1:99 → Netem (default)  → No filter (broadcast/multicast)

Requirements:
    - Linux kernel 4.2+ (for tc flower filters)
    - HTB qdisc support
    - sudo access for nsenter
"""

import logging
import subprocess
from dataclasses import dataclass

from sine.topology.netem import NetemParams

logger = logging.getLogger(__name__)


@dataclass
class PerDestinationConfig:
    """Per-destination netem configuration for a single node interface."""

    node: str
    interface: str
    default_params: NetemParams  # For broadcast/multicast traffic
    dest_params: dict[str, NetemParams]  # {dest_ip: NetemParams}


class SharedNetemConfigurator:
    """Configure per-destination netem on shared bridge interfaces.

    This class generates and applies tc commands to create HTB hierarchies
    with per-destination netem rules using flower filters for IP-based
    classification.
    """

    def __init__(self, container_manager):
        """
        Initialize configurator with container manager.

        Args:
            container_manager: ContainerlabManager instance for container access
        """
        self.container_manager = container_manager

    def apply_per_destination_netem(self, config: PerDestinationConfig) -> bool:
        """
        Apply HTB + per-destination netem to interface.

        Creates a 3-layer hierarchy:
        1. HTB root qdisc with default class 1:99
        2. Parent class 1:1 (unlimited rate)
        3. Per-destination classes (1:10, 1:20, ...) with netem + flower filters
        4. Default class 1:99 for broadcast/multicast with default netem

        Args:
            config: Per-destination configuration

        Returns:
            True if all commands succeeded, False otherwise
        """
        container_info = self.container_manager.get_container_info(config.node)
        if not container_info:
            logger.error(f"Container info not found for {config.node}")
            return False

        pid = container_info.get("pid")
        if not pid:
            logger.error(f"PID not found for {config.node}")
            return False

        interface = config.interface
        commands = self._generate_tc_commands(config)

        logger.info(
            f"Applying per-destination netem to {config.node}:{interface} "
            f"({len(config.dest_params)} destinations)"
        )

        # Execute all commands in container namespace
        for cmd in commands:
            try:
                subprocess.run(
                    ["sudo", "nsenter", "-t", str(pid), "-n", "sh", "-c", cmd],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                logger.debug(f"  ✓ {cmd[:60]}...")
            except subprocess.CalledProcessError as e:
                logger.error(
                    f"Failed to apply tc command on {config.node}:{interface}: {cmd}"
                )
                logger.error(f"  Error: {e.stderr}")
                return False

        logger.info(
            f"Successfully configured per-destination netem on {config.node}:{interface}"
        )
        return True

    def _generate_tc_commands(self, config: PerDestinationConfig) -> list[str]:
        """
        Generate tc commands for HTB + per-destination netem setup.

        Args:
            config: Per-destination configuration

        Returns:
            List of tc command strings
        """
        commands = []
        interface = config.interface

        # 1. HTB root qdisc (default to class 1:99 for broadcast)
        commands.append(f"tc qdisc add dev {interface} root handle 1: htb default 99")

        # 2. Parent class (unlimited rate)
        commands.append(
            f"tc class add dev {interface} parent 1: classid 1:1 htb rate 1000mbit"
        )

        # 3. Default class for broadcast/multicast
        default = config.default_params
        commands.append(
            f"tc class add dev {interface} parent 1:1 classid 1:99 htb rate 1000mbit"
        )

        # Default netem parameters (minimal delay for broadcast)
        default_netem_opts = [f"delay {default.delay_ms}ms"]
        if default.jitter_ms > 0:
            default_netem_opts.append(f"{default.jitter_ms}ms")

        commands.append(
            f"tc qdisc add dev {interface} parent 1:99 handle 99: "
            f"netem {' '.join(default_netem_opts)}"
        )

        # 4. Per-destination classes + netem + flower filters
        classid = 10
        for dest_ip, params in config.dest_params.items():
            # HTB class (rate limit per destination)
            commands.append(
                f"tc class add dev {interface} parent 1:1 classid 1:{classid} "
                f"htb rate {params.rate_mbps}mbit"
            )

            # Netem qdisc (delay, jitter, loss)
            netem_opts = [f"delay {params.delay_ms}ms"]
            if params.jitter_ms > 0:
                netem_opts.append(f"{params.jitter_ms}ms")
            if params.loss_percent > 0:
                netem_opts.append(f"loss {params.loss_percent}%")

            commands.append(
                f"tc qdisc add dev {interface} parent 1:{classid} handle {classid}: "
                f"netem {' '.join(netem_opts)}"
            )

            # flower filter (hash-based IP destination match)
            # Uses O(1) hash lookup for efficient classification
            commands.append(
                f"tc filter add dev {interface} protocol ip parent 1:0 prio 1 "
                f"flower dst_ip {dest_ip} action pass flowid 1:{classid}"
            )

            logger.debug(
                f"  → {dest_ip}: delay={params.delay_ms:.1f}ms, "
                f"loss={params.loss_percent:.2f}%, rate={params.rate_mbps:.1f}Mbps"
            )

            classid += 10

        return commands

    def remove_per_destination_netem(self, node: str, interface: str) -> bool:
        """
        Remove per-destination netem configuration from interface.

        Args:
            node: Node name
            interface: Interface name

        Returns:
            True if removal succeeded, False otherwise
        """
        container_info = self.container_manager.get_container_info(node)
        if not container_info:
            logger.error(f"Container info not found for {node}")
            return False

        pid = container_info.get("pid")
        if not pid:
            logger.error(f"PID not found for {node}")
            return False

        try:
            # Remove root qdisc (removes all classes and filters)
            subprocess.run(
                [
                    "sudo",
                    "nsenter",
                    "-t",
                    str(pid),
                    "-n",
                    "tc",
                    "qdisc",
                    "del",
                    "dev",
                    interface,
                    "root",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            logger.info(f"Removed per-destination netem from {node}:{interface}")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to remove netem from {node}:{interface}: {e.stderr}")
            return False

    def get_tc_stats(self, node: str, interface: str) -> dict | None:
        """
        Get tc statistics for debugging.

        Args:
            node: Node name
            interface: Interface name

        Returns:
            Dictionary with qdisc, class, and filter stats, or None on error
        """
        container_info = self.container_manager.get_container_info(node)
        if not container_info:
            return None

        pid = container_info.get("pid")
        if not pid:
            return None

        stats = {}

        # Get qdisc stats
        try:
            result = subprocess.run(
                [
                    "sudo",
                    "nsenter",
                    "-t",
                    str(pid),
                    "-n",
                    "tc",
                    "-s",
                    "qdisc",
                    "show",
                    "dev",
                    interface,
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            stats["qdisc"] = result.stdout
        except subprocess.CalledProcessError:
            stats["qdisc"] = None

        # Get class stats
        try:
            result = subprocess.run(
                [
                    "sudo",
                    "nsenter",
                    "-t",
                    str(pid),
                    "-n",
                    "tc",
                    "-s",
                    "class",
                    "show",
                    "dev",
                    interface,
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            stats["class"] = result.stdout
        except subprocess.CalledProcessError:
            stats["class"] = None

        # Get filter stats
        try:
            result = subprocess.run(
                [
                    "sudo",
                    "nsenter",
                    "-t",
                    str(pid),
                    "-n",
                    "tc",
                    "-s",
                    "filter",
                    "show",
                    "dev",
                    interface,
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            stats["filter"] = result.stdout
        except subprocess.CalledProcessError:
            stats["filter"] = None

        return stats
