"""
CSMA/CA (Carrier Sense Multiple Access with Collision Avoidance) statistical model.

Implements Phase 1.5 of SINR plan: WiFi CSMA/CA behavior without full MAC simulation.
Captures spatial reuse and hidden node effects through carrier sensing range model.
"""

import logging
import math
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CSMAConfig:
    """CSMA/CA statistical model configuration."""

    enabled: bool = True
    carrier_sense_range_multiplier: float = 2.5  # CS range / communication range
    traffic_load: float = 0.3  # Default traffic duty cycle (30%)


def compute_distance(
    pos1: tuple[float, float, float],
    pos2: tuple[float, float, float],
) -> float:
    """
    Compute Euclidean distance between two 3D positions.

    Args:
        pos1: First position (x, y, z)
        pos2: Second position (x, y, z)

    Returns:
        Distance in meters
    """
    dx = pos1[0] - pos2[0]
    dy = pos1[1] - pos2[1]
    dz = pos1[2] - pos2[2]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


class CSMAModel:
    """
    Statistical CSMA/CA model for WiFi MANET SINR computation.

    Captures spatial reuse and hidden node problem without event simulation.

    Key Insight: WiFi CSMA/CA achieves statistical time-domain separation:
    - Nodes within carrier sense range defer (don't transmit simultaneously)
    - Nodes beyond carrier sense range are "hidden nodes" (potential collisions)
    - Typical carrier sense range: 2.5× communication range
    """

    def __init__(
        self,
        carrier_sense_range_multiplier: float = 2.5,
        default_traffic_load: float = 0.3,
    ):
        """
        Initialize CSMA/CA model.

        Args:
            carrier_sense_range_multiplier: CS range / communication range (WiFi typical: 2.5)
            default_traffic_load: Default traffic duty cycle (30% typical)
        """
        self.cs_multiplier = carrier_sense_range_multiplier
        self.traffic_load = default_traffic_load

        logger.info(
            f"CSMA/CA model initialized: CS multiplier={carrier_sense_range_multiplier}, "
            f"traffic load={default_traffic_load}"
        )

    def compute_interference_probability(
        self,
        tx_node: str,
        rx_node: str,
        interferer_node: str,
        positions: dict[str, tuple[float, float, float]],
        communication_range: float,
        traffic_load: float | None = None,
    ) -> float:
        """
        Compute probability that interferer is transmitting when tx_node transmits.

        Args:
            tx_node: Transmitter node name
            rx_node: Receiver node name (not used in binary carrier sense model)
            interferer_node: Potential interferer node name
            positions: Node positions {node_name: (x, y, z)}
            communication_range: Communication range in meters
            traffic_load: Override traffic load for this calculation (optional)

        Returns:
            Probability that interferer transmits when tx_node transmits:
            - 0.0 if interferer within carrier sense range (defers due to CSMA)
            - traffic_load if interferer beyond carrier sense range (hidden node)
        """
        if traffic_load is None:
            traffic_load = self.traffic_load

        tx_pos = positions[tx_node]
        interferer_pos = positions[interferer_node]

        # Distance from interferer to TX node
        dist_to_tx = compute_distance(interferer_pos, tx_pos)

        # Carrier sense range
        cs_range = communication_range * self.cs_multiplier

        if dist_to_tx < cs_range:
            # Interferer can sense TX node, defers transmission (CSMA/CA)
            logger.debug(
                f"CSMA: {interferer_node} within CS range of {tx_node} "
                f"({dist_to_tx:.1f}m < {cs_range:.1f}m) → Pr[TX]=0.0"
            )
            return 0.0
        else:
            # Hidden node: interferer cannot sense TX, may transmit
            # Probability = traffic load (duty cycle)
            logger.debug(
                f"CSMA: {interferer_node} hidden from {tx_node} "
                f"({dist_to_tx:.1f}m > {cs_range:.1f}m) → Pr[TX]={traffic_load}"
            )
            return traffic_load

    def compute_interference_probabilities(
        self,
        tx_node: str,
        rx_node: str,
        interferer_nodes: list[str],
        positions: dict[str, tuple[float, float, float]],
        communication_range: float,
        traffic_load: float | None = None,
    ) -> dict[str, float]:
        """
        Compute interference probabilities for all interferers.

        Args:
            tx_node: Transmitter node name
            rx_node: Receiver node name
            interferer_nodes: List of potential interferer node names
            positions: Node positions {node_name: (x, y, z)}
            communication_range: Communication range in meters
            traffic_load: Override traffic load (optional)

        Returns:
            Dictionary {interferer_name: Pr[TX]}
        """
        probs = {}

        for interferer in interferer_nodes:
            # Skip self and RX node
            if interferer in (tx_node, rx_node):
                continue

            prob = self.compute_interference_probability(
                tx_node=tx_node,
                rx_node=rx_node,
                interferer_node=interferer,
                positions=positions,
                communication_range=communication_range,
                traffic_load=traffic_load,
            )

            probs[interferer] = prob

        # Count hidden nodes
        num_hidden = sum(1 for p in probs.values() if p > 0)
        num_within_cs = sum(1 for p in probs.values() if p == 0)

        logger.info(
            f"Link {tx_node}→{rx_node}: {num_within_cs} within CS range, "
            f"{num_hidden} hidden nodes"
        )

        return probs

    @staticmethod
    def compute_carrier_sense_range(
        communication_range: float,
        cs_multiplier: float = 2.5,
    ) -> float:
        """
        Compute carrier sense range from communication range.

        Typical WiFi: CS range = 2.5× communication range

        Args:
            communication_range: Maximum communication distance in meters
            cs_multiplier: CS range multiplier (default: 2.5)

        Returns:
            Carrier sense range in meters
        """
        return communication_range * cs_multiplier
