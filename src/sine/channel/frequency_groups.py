"""
Frequency grouping utilities for SINR computation.

Groups nodes by frequency to reduce computational complexity. Nodes in different
frequency groups have negligible interference (orthogonal channels).
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class FrequencyGroup:
    """A group of nodes operating on nearby frequencies."""

    center_frequency_hz: float  # Representative frequency for the group
    nodes: list[str]  # Node names in this group
    frequencies: dict[str, float]  # {node_name: frequency_hz}

    @property
    def num_nodes(self) -> int:
        """Number of nodes in this group."""
        return len(self.nodes)

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"FrequencyGroup(center={self.center_frequency_hz/1e9:.3f} GHz, "
            f"nodes={self.num_nodes})"
        )


def group_nodes_by_frequency(
    node_frequencies: dict[str, float],
    adjacent_threshold_hz: float = 50e6,
    orthogonal_threshold_hz: float = 100e6,
) -> list[FrequencyGroup]:
    """
    Group nodes by frequency for interference computation.

    Nodes are grouped if their frequency separation is within the adjacent threshold.
    Nodes beyond the orthogonal threshold are considered non-interfering.

    Args:
        node_frequencies: {node_name: frequency_hz}
        adjacent_threshold_hz: Max frequency separation for adjacent channels (default: 50 MHz)
        orthogonal_threshold_hz: Min frequency separation for orthogonal channels (default: 100 MHz)

    Returns:
        List of FrequencyGroup objects

    Example:
        >>> nodes = {
        ...     "node1": 5.18e9,  # Group 1
        ...     "node2": 5.18e9,  # Group 1 (co-channel)
        ...     "node3": 5.20e9,  # Group 1 (adjacent, 20 MHz away)
        ...     "node4": 5.50e9,  # Group 2 (orthogonal, >100 MHz away)
        ... }
        >>> groups = group_nodes_by_frequency(nodes, adjacent_threshold_hz=50e6)
        >>> len(groups)
        2
    """
    if not node_frequencies:
        return []

    # Sort nodes by frequency
    sorted_nodes = sorted(node_frequencies.items(), key=lambda x: x[1])

    # Group nodes using clustering
    groups: list[FrequencyGroup] = []
    current_group_nodes: list[str] = []
    current_group_freqs: dict[str, float] = {}
    current_min_freq: Optional[float] = None

    for node_name, frequency_hz in sorted_nodes:
        if current_min_freq is None:
            # Start first group
            current_min_freq = frequency_hz
            current_group_nodes.append(node_name)
            current_group_freqs[node_name] = frequency_hz
        else:
            # Check if this node is within adjacent threshold of group
            freq_separation = abs(frequency_hz - current_min_freq)

            if freq_separation <= adjacent_threshold_hz:
                # Add to current group
                current_group_nodes.append(node_name)
                current_group_freqs[node_name] = frequency_hz
            else:
                # Start new group
                # Finalize current group
                center_freq = sum(current_group_freqs.values()) / len(current_group_freqs)
                groups.append(FrequencyGroup(
                    center_frequency_hz=center_freq,
                    nodes=current_group_nodes,
                    frequencies=current_group_freqs,
                ))

                # Start new group
                current_group_nodes = [node_name]
                current_group_freqs = {node_name: frequency_hz}
                current_min_freq = frequency_hz

    # Finalize last group
    if current_group_nodes:
        center_freq = sum(current_group_freqs.values()) / len(current_group_freqs)
        groups.append(FrequencyGroup(
            center_frequency_hz=center_freq,
            nodes=current_group_nodes,
            frequencies=current_group_freqs,
        ))

    logger.info(
        f"Grouped {len(node_frequencies)} nodes into {len(groups)} frequency groups "
        f"(adjacent_threshold={adjacent_threshold_hz/1e6:.1f} MHz)"
    )

    for i, group in enumerate(groups):
        logger.debug(
            f"  Group {i}: {group.num_nodes} nodes at "
            f"{group.center_frequency_hz/1e9:.3f} GHz"
        )

    return groups


def get_frequency_separation(freq1_hz: float, freq2_hz: float) -> float:
    """
    Get frequency separation between two frequencies.

    Args:
        freq1_hz: First frequency in Hz
        freq2_hz: Second frequency in Hz

    Returns:
        Absolute frequency separation in Hz
    """
    return abs(freq1_hz - freq2_hz)


def are_frequencies_orthogonal(
    freq1_hz: float,
    freq2_hz: float,
    orthogonal_threshold_hz: float = 100e6,
) -> bool:
    """
    Check if two frequencies are orthogonal (non-interfering).

    Args:
        freq1_hz: First frequency in Hz
        freq2_hz: Second frequency in Hz
        orthogonal_threshold_hz: Threshold for orthogonality (default: 100 MHz)

    Returns:
        True if frequencies are orthogonal (separation > threshold)
    """
    separation = get_frequency_separation(freq1_hz, freq2_hz)
    return separation > orthogonal_threshold_hz


def are_frequencies_cochannel(
    freq1_hz: float,
    freq2_hz: float,
    cochannel_tolerance_hz: float = 1e6,
) -> bool:
    """
    Check if two frequencies are co-channel (same channel).

    Args:
        freq1_hz: First frequency in Hz
        freq2_hz: Second frequency in Hz
        cochannel_tolerance_hz: Tolerance for co-channel (default: 1 MHz)

    Returns:
        True if frequencies are co-channel (separation < tolerance)
    """
    separation = get_frequency_separation(freq1_hz, freq2_hz)
    return separation < cochannel_tolerance_hz
