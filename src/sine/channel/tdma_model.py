"""
TDMA (Time Division Multiple Access) statistical model.

Implements Phase 1.6 of SINR plan: Military MANET radios using TDMA-based MAC.
Supports fixed/round-robin/random/distributed slot assignment strategies.
"""

import logging
import math
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class SlotAssignmentMode(str, Enum):
    """TDMA slot assignment strategies."""

    FIXED = "fixed"  # Pre-assigned slots per node
    ROUND_ROBIN = "round_robin"  # Cyclic slot allocation
    RANDOM = "random"  # Probabilistic slot allocation
    DISTRIBUTED = "distributed"  # DAMA-style distributed coordination


@dataclass
class TDMASlotConfig:
    """TDMA frame and slot configuration."""

    frame_duration_ms: float = 10.0  # TDMA frame duration (10ms typical)
    num_slots: int = 10  # Number of slots per frame
    slot_assignment_mode: SlotAssignmentMode = SlotAssignmentMode.ROUND_ROBIN
    fixed_slot_map: dict[str, list[int]] | None = None  # For FIXED mode
    slot_probability: float = 0.1  # For RANDOM/DISTRIBUTED modes


class TDMAModel:
    """
    Statistical TDMA model for military MANET SINR computation.

    Captures scheduled access behavior without discrete-event simulation.

    Key Insight: Military radios use deterministic time slots for channel access,
    not WiFi's probabilistic carrier sensing. This means:
    - No carrier sense range concept (orthogonal time slots prevent collisions)
    - Deterministic interference when slot assignments are known (Pr[collision] = 0 or 1)
    - Throughput depends on slot ownership (fraction of TDMA frame allocated to node)
    """

    def __init__(self, config: TDMASlotConfig):
        """
        Initialize TDMA model.

        Args:
            config: TDMA slot configuration
        """
        self.config = config

        # Validate configuration
        if config.slot_assignment_mode == SlotAssignmentMode.FIXED:
            if config.fixed_slot_map is None:
                raise ValueError(
                    "FIXED slot assignment mode requires fixed_slot_map to be set"
                )

        logger.info(
            f"TDMA model initialized: mode={config.slot_assignment_mode.value}, "
            f"frame={config.frame_duration_ms}ms, slots={config.num_slots}"
        )

    def compute_interference_probability(
        self,
        tx_node: str,
        rx_node: str,
        interferer_node: str,
        current_slot: int | None = None,
        all_nodes: list[str] | None = None,
    ) -> float:
        """
        Compute probability that interferer is transmitting when tx_node transmits.

        In TDMA:
        - If slot assignments are known (FIXED/ROUND_ROBIN): deterministic (0.0 or 1.0)
        - If slot assignments are probabilistic (RANDOM/DISTRIBUTED): statistical

        Args:
            tx_node: Transmitter node name
            rx_node: Receiver node name (not used in TDMA)
            interferer_node: Potential interferer node name
            current_slot: Current time slot (optional, for FIXED mode)
            all_nodes: List of all nodes (for ROUND_ROBIN mode)

        Returns:
            Probability that interferer transmits when tx_node transmits
        """
        mode = self.config.slot_assignment_mode

        if mode == SlotAssignmentMode.FIXED:
            # Deterministic: check if both nodes own the same slot
            return self._compute_probability_fixed(
                tx_node, interferer_node, current_slot
            )

        elif mode == SlotAssignmentMode.ROUND_ROBIN:
            # Deterministic: nodes get sequential slots (no collisions)
            return 0.0  # Orthogonal slots by design

        elif mode == SlotAssignmentMode.RANDOM:
            # Statistical: collision probability = slot_probability^2
            return self.config.slot_probability

        elif mode == SlotAssignmentMode.DISTRIBUTED:
            # Statistical with coordination: reduced collision probability
            # DAMA-style signaling reduces collisions by ~50%
            return self.config.slot_probability * 0.5

        else:
            raise ValueError(f"Unknown slot assignment mode: {mode}")

    def _compute_probability_fixed(
        self,
        tx_node: str,
        interferer_node: str,
        current_slot: int | None,
    ) -> float:
        """
        Compute interference probability for FIXED slot assignment.

        Args:
            tx_node: Transmitter node name
            interferer_node: Interferer node name
            current_slot: Current time slot (optional)

        Returns:
            0.0 if slots are orthogonal, 1.0 if slots collide
        """
        if self.config.fixed_slot_map is None:
            raise ValueError("fixed_slot_map not set for FIXED mode")

        tx_slots = set(self.config.fixed_slot_map.get(tx_node, []))
        interferer_slots = set(self.config.fixed_slot_map.get(interferer_node, []))

        if current_slot is not None:
            # Check specific slot
            if current_slot in tx_slots and current_slot in interferer_slots:
                return 1.0  # Collision in this slot
            else:
                return 0.0  # Orthogonal
        else:
            # Average over all slots
            collision_slots = tx_slots.intersection(interferer_slots)
            if collision_slots:
                # Some slots collide
                prob = len(collision_slots) / self.config.num_slots
                logger.debug(
                    f"TDMA FIXED: {tx_node} and {interferer_node} collide in "
                    f"{len(collision_slots)} slots → Pr[collision]={prob:.2f}"
                )
                return prob
            else:
                # Orthogonal slots
                logger.debug(
                    f"TDMA FIXED: {tx_node} and {interferer_node} have orthogonal slots"
                )
                return 0.0

    def compute_interference_probabilities(
        self,
        tx_node: str,
        rx_node: str,
        interferer_nodes: list[str],
        current_slot: int | None = None,
        all_nodes: list[str] | None = None,
    ) -> dict[str, float]:
        """
        Compute interference probabilities for all interferers.

        Args:
            tx_node: Transmitter node name
            rx_node: Receiver node name
            interferer_nodes: List of potential interferer node names
            current_slot: Current time slot (optional)
            all_nodes: List of all nodes (for ROUND_ROBIN mode)

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
                current_slot=current_slot,
                all_nodes=all_nodes,
            )

            probs[interferer] = prob

        # Count deterministic vs probabilistic interferers
        num_deterministic = sum(1 for p in probs.values() if p in [0.0, 1.0])
        num_probabilistic = len(probs) - num_deterministic

        logger.info(
            f"Link {tx_node}→{rx_node} (TDMA {self.config.slot_assignment_mode.value}): "
            f"{num_deterministic} deterministic, {num_probabilistic} probabilistic interferers"
        )

        return probs

    def get_throughput_multiplier(self, node_name: str, all_nodes: list[str] | None = None) -> float:
        """
        Get throughput scaling factor for node based on slot ownership.

        Returns:
            Fraction of time node can transmit (0.0 to 1.0)
        """
        mode = self.config.slot_assignment_mode

        if mode == SlotAssignmentMode.FIXED:
            if self.config.fixed_slot_map is None:
                raise ValueError("fixed_slot_map not set for FIXED mode")

            num_owned_slots = len(self.config.fixed_slot_map.get(node_name, []))
            multiplier = num_owned_slots / self.config.num_slots

            logger.debug(
                f"TDMA FIXED: {node_name} owns {num_owned_slots}/{self.config.num_slots} slots "
                f"→ throughput multiplier={multiplier:.2f}"
            )
            return multiplier

        elif mode == SlotAssignmentMode.ROUND_ROBIN:
            if all_nodes is None:
                raise ValueError("all_nodes required for ROUND_ROBIN mode")

            num_nodes = len(all_nodes)
            multiplier = 1.0 / num_nodes

            logger.debug(
                f"TDMA ROUND_ROBIN: {num_nodes} nodes "
                f"→ throughput multiplier={multiplier:.2f}"
            )
            return multiplier

        elif mode in [SlotAssignmentMode.RANDOM, SlotAssignmentMode.DISTRIBUTED]:
            # Statistical slot allocation
            multiplier = self.config.slot_probability

            logger.debug(
                f"TDMA {mode.value}: slot_probability={self.config.slot_probability} "
                f"→ throughput multiplier={multiplier:.2f}"
            )
            return multiplier

        else:
            raise ValueError(f"Unknown slot assignment mode: {mode}")

    @staticmethod
    def compute_slot_duration_ms(frame_duration_ms: float, num_slots: int) -> float:
        """
        Compute duration of a single slot.

        Args:
            frame_duration_ms: TDMA frame duration in milliseconds
            num_slots: Number of slots per frame

        Returns:
            Slot duration in milliseconds
        """
        return frame_duration_ms / num_slots
