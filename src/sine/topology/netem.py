"""
Linux netem (Network Emulator) configuration.

netem allows adding delay, packet loss, jitter, and bandwidth limits
to network interfaces using tc (traffic control).

Key commands:
- tc qdisc add dev <if> root netem delay <ms>ms <jitter>ms loss <percent>%
- tc qdisc add dev <if> parent 1: handle 2: tbf rate <mbps>mbit burst 32kbit latency 400ms

Note: netem doesn't have native rate control - use tbf (token bucket filter)
for bandwidth limiting, chained with netem for other parameters.

Reference: https://man7.org/linux/man-pages/man8/tc-netem.8.html
"""

import logging
import re
import subprocess
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class NetemParams:
    """Parameters for netem configuration."""

    delay_ms: float = 0.0
    jitter_ms: float = 0.0
    loss_percent: float = 0.0
    rate_mbps: float = 1000.0  # Default 1Gbps (effectively unlimited)
    correlation_percent: float = 25.0  # Delay correlation for realistic jitter

    def __post_init__(self):
        """Validate parameters."""
        if self.delay_ms < 0:
            raise ValueError("delay_ms must be non-negative")
        if self.jitter_ms < 0:
            raise ValueError("jitter_ms must be non-negative")
        if not 0 <= self.loss_percent <= 100:
            raise ValueError("loss_percent must be between 0 and 100")
        if self.rate_mbps <= 0:
            raise ValueError("rate_mbps must be positive")

    def to_tc_commands(
        self, interface: str, use_nsenter: bool = False, pid: Optional[int] = None
    ) -> list[str]:
        """
        Generate tc commands for this configuration.

        Args:
            interface: Network interface name
            use_nsenter: If True, prefix commands with nsenter for container netns
            pid: Container PID (required if use_nsenter is True)

        Returns:
            List of shell commands to execute
        """
        commands = []
        ns_prefix = ""

        if use_nsenter:
            if pid is None:
                raise ValueError("PID required when use_nsenter is True")
            # sudo is required to enter another process's network namespace
            ns_prefix = f"sudo nsenter -t {pid} -n "

        # First, delete any existing qdisc (ignore errors)
        commands.append(
            f"{ns_prefix}tc qdisc del dev {interface} root 2>/dev/null || true"
        )

        # Build netem parameters
        netem_params = []

        if self.delay_ms > 0:
            netem_params.append(f"delay {self.delay_ms:.2f}ms")
            if self.jitter_ms > 0:
                netem_params.append(
                    f"{self.jitter_ms:.2f}ms {self.correlation_percent:.0f}%"
                )

        if self.loss_percent > 0:
            netem_params.append(f"loss {self.loss_percent:.2f}%")

        # If we have netem params, add netem qdisc with tbf child for rate
        if netem_params:
            netem_cmd = (
                f"{ns_prefix}tc qdisc add dev {interface} root handle 1: "
                f"netem {' '.join(netem_params)}"
            )
            commands.append(netem_cmd)

            # Add tbf for rate limiting as child of netem
            # Burst should be at least rate/HZ (typically rate/250 for 250 Hz kernel)
            burst_kb = max(32, int(self.rate_mbps * 1000 / 250))
            tbf_cmd = (
                f"{ns_prefix}tc qdisc add dev {interface} parent 1: handle 2: "
                f"tbf rate {self.rate_mbps:.2f}mbit burst {burst_kb}kbit latency 50ms"
            )
            commands.append(tbf_cmd)
        else:
            # Only rate limiting needed
            burst_kb = max(32, int(self.rate_mbps * 1000 / 250))
            tbf_cmd = (
                f"{ns_prefix}tc qdisc add dev {interface} root "
                f"tbf rate {self.rate_mbps:.2f}mbit burst {burst_kb}kbit latency 50ms"
            )
            commands.append(tbf_cmd)

        return commands

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "delay_ms": self.delay_ms,
            "jitter_ms": self.jitter_ms,
            "loss_percent": self.loss_percent,
            "rate_mbps": self.rate_mbps,
            "correlation_percent": self.correlation_percent,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NetemParams":
        """Create from dictionary."""
        return cls(
            delay_ms=data.get("delay_ms", 0.0),
            jitter_ms=data.get("jitter_ms", 0.0),
            loss_percent=data.get("loss_percent", 0.0),
            rate_mbps=data.get("rate_mbps", 1000.0),
            correlation_percent=data.get("correlation_percent", 25.0),
        )


class NetemConfigurator:
    """Configure netem on container interfaces."""

    def __init__(self):
        """Initialize configurator."""
        self._current_configs: dict[tuple[str, str], NetemParams] = {}

    def apply_config(
        self, container_name: str, interface: str, params: NetemParams, pid: int
    ) -> bool:
        """
        Apply netem configuration to a container interface.

        Args:
            container_name: Docker container name
            interface: Interface name inside container
            params: Netem parameters to apply
            pid: Container PID for nsenter

        Returns:
            True if configuration succeeded
        """
        commands = params.to_tc_commands(interface, use_nsenter=True, pid=pid)

        success = True
        for cmd in commands:
            try:
                result = subprocess.run(
                    cmd, shell=True, check=True, capture_output=True, text=True
                )
                logger.debug(f"Executed: {cmd}")
            except subprocess.CalledProcessError as e:
                # Ignore deletion errors, fail on add errors
                if "del" not in cmd:
                    logger.error(f"Failed to apply netem: {e.stderr}")
                    success = False

        if success:
            self._current_configs[(container_name, interface)] = params
            logger.info(
                f"Applied netem config to {container_name}:{interface} - "
                f"delay={params.delay_ms:.1f}ms, loss={params.loss_percent:.2f}%, "
                f"rate={params.rate_mbps:.1f}Mbps"
            )

        return success

    def get_current_config(
        self, container_name: str, interface: str, pid: int
    ) -> Optional[dict]:
        """
        Get current netem configuration on an interface.

        Args:
            container_name: Docker container name
            interface: Interface name
            pid: Container PID

        Returns:
            Dictionary with current config or None
        """
        cmd = f"sudo nsenter -t {pid} -n tc qdisc show dev {interface}"

        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, check=True
            )
            return self._parse_tc_output(result.stdout)
        except subprocess.CalledProcessError:
            return None

    def _parse_tc_output(self, output: str) -> dict:
        """Parse tc qdisc show output."""
        config = {
            "delay_ms": 0.0,
            "jitter_ms": 0.0,
            "loss_percent": 0.0,
            "rate_mbps": 0.0,
        }

        for line in output.split("\n"):
            # Parse delay
            delay_match = re.search(r"delay (\d+\.?\d*)(ms|us|s)", line)
            if delay_match:
                value = float(delay_match.group(1))
                unit = delay_match.group(2)
                if unit == "us":
                    value /= 1000
                elif unit == "s":
                    value *= 1000
                config["delay_ms"] = value

            # Parse jitter (appears after delay)
            jitter_match = re.search(r"delay \d+\.?\d*\w+\s+(\d+\.?\d*)(ms|us|s)", line)
            if jitter_match:
                value = float(jitter_match.group(1))
                unit = jitter_match.group(2)
                if unit == "us":
                    value /= 1000
                elif unit == "s":
                    value *= 1000
                config["jitter_ms"] = value

            # Parse loss
            loss_match = re.search(r"loss (\d+\.?\d*)%", line)
            if loss_match:
                config["loss_percent"] = float(loss_match.group(1))

            # Parse rate (from tbf)
            rate_match = re.search(r"rate (\d+\.?\d*)(M|K|G)?bit", line)
            if rate_match:
                rate = float(rate_match.group(1))
                unit = rate_match.group(2) or ""
                if unit == "K":
                    rate /= 1000
                elif unit == "G":
                    rate *= 1000
                config["rate_mbps"] = rate

        return config

    def clear_config(self, container_name: str, interface: str, pid: int) -> bool:
        """
        Clear netem configuration from an interface.

        Args:
            container_name: Docker container name
            interface: Interface name
            pid: Container PID

        Returns:
            True if successful
        """
        cmd = f"sudo nsenter -t {pid} -n tc qdisc del dev {interface} root 2>/dev/null || true"

        try:
            subprocess.run(cmd, shell=True, check=True, capture_output=True)
            self._current_configs.pop((container_name, interface), None)
            logger.info(f"Cleared netem config from {container_name}:{interface}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to clear netem: {e}")
            return False

    def get_all_configs(self) -> dict[tuple[str, str], NetemParams]:
        """Get all currently applied configurations."""
        return self._current_configs.copy()


def check_tc_available() -> bool:
    """Check if tc (traffic control) is available."""
    try:
        result = subprocess.run(["tc", "-V"], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False
