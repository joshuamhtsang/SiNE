"""
Unit tests for TDMA statistical model.

Tests Phase 1.6: Military MANET TDMA behavior with slot assignment modes.
"""

import pytest

from sine.channel.tdma_model import (
    SlotAssignmentMode,
    TDMAModel,
    TDMASlotConfig,
)


def test_tdma_model_init():
    """Test TDMA model initialization."""
    config = TDMASlotConfig(
        frame_duration_ms=10.0,
        num_slots=10,
        slot_assignment_mode=SlotAssignmentMode.ROUND_ROBIN,
    )

    model = TDMAModel(config)

    assert model.config.frame_duration_ms == 10.0
    assert model.config.num_slots == 10
    assert model.config.slot_assignment_mode == SlotAssignmentMode.ROUND_ROBIN


def test_tdma_fixed_orthogonal_slots():
    """Test TDMA fixed mode with orthogonal slot assignments."""
    config = TDMASlotConfig(
        slot_assignment_mode=SlotAssignmentMode.FIXED,
        num_slots=10,
        fixed_slot_map={
            "node1": [0, 5],  # Slots 0, 5
            "node2": [1, 6],  # Slots 1, 6
            "node3": [2, 7],  # Slots 2, 7
        },
    )

    model = TDMAModel(config)

    # Link node1→node2 with interferer node3
    # All slots are orthogonal (no collisions)
    prob = model.compute_interference_probability(
        tx_node="node1",
        rx_node="node2",
        interferer_node="node3",
    )

    # Expected: node1 and node3 have orthogonal slots → Pr[collision] = 0.0
    assert prob == 0.0, "Orthogonal TDMA slots should have zero collision probability"


def test_tdma_fixed_collision_slots():
    """Test TDMA fixed mode with colliding slot assignments."""
    config = TDMASlotConfig(
        slot_assignment_mode=SlotAssignmentMode.FIXED,
        num_slots=10,
        fixed_slot_map={
            "node1": [0, 5],  # Slots 0, 5
            "node2": [1, 6],  # Slots 1, 6
            "node3": [0, 2],  # Slot 0 collides with node1
        },
    )

    model = TDMAModel(config)

    # Link node1→node2 with interferer node3
    # node1 and node3 both own slot 0 (collision)
    prob = model.compute_interference_probability(
        tx_node="node1",
        rx_node="node2",
        interferer_node="node3",
    )

    # Expected: 1 collision slot out of 10 → Pr[collision] = 0.1
    assert prob == 0.1, "TDMA collision in 1/10 slots → 10% probability"


def test_tdma_round_robin_no_collisions():
    """Test TDMA round-robin mode (cyclic slots, no collisions)."""
    config = TDMASlotConfig(
        slot_assignment_mode=SlotAssignmentMode.ROUND_ROBIN,
        num_slots=12,
    )

    model = TDMAModel(config)

    # Round-robin with 3 nodes → slots [0,3,6,9], [1,4,7,10], [2,5,8,11]
    # No collisions by design
    prob = model.compute_interference_probability(
        tx_node="node1",
        rx_node="node2",
        interferer_node="node3",
        all_nodes=["node1", "node2", "node3"],
    )

    # Expected: round-robin guarantees orthogonal slots → Pr[collision] = 0.0
    assert prob == 0.0, "Round-robin TDMA should have zero collisions"


def test_tdma_random_statistical_collisions():
    """Test TDMA random mode (statistical slot allocation)."""
    config = TDMASlotConfig(
        slot_assignment_mode=SlotAssignmentMode.RANDOM,
        slot_probability=0.3,  # 30% duty cycle
    )

    model = TDMAModel(config)

    # Random mode: each node has 30% probability to transmit in any slot
    prob = model.compute_interference_probability(
        tx_node="node1",
        rx_node="node2",
        interferer_node="node3",
    )

    # Expected: Pr[interferer TX] = slot_probability = 0.3
    assert prob == 0.3, "Random TDMA should have slot_probability collision rate"


def test_tdma_distributed_reduced_collisions():
    """Test TDMA distributed mode (DAMA-style with coordination)."""
    config = TDMASlotConfig(
        slot_assignment_mode=SlotAssignmentMode.DISTRIBUTED,
        slot_probability=0.3,
    )

    model = TDMAModel(config)

    # Distributed mode: coordination reduces collisions by ~50%
    prob = model.compute_interference_probability(
        tx_node="node1",
        rx_node="node2",
        interferer_node="node3",
    )

    # Expected: slot_probability × 0.5 (coordination factor)
    assert prob == 0.15, "Distributed TDMA should reduce collisions by 50%"


def test_tdma_throughput_multiplier_fixed():
    """Test throughput multiplier for TDMA fixed mode."""
    config = TDMASlotConfig(
        slot_assignment_mode=SlotAssignmentMode.FIXED,
        num_slots=10,
        fixed_slot_map={
            "node1": [0, 5],  # 2 slots out of 10 → 20%
            "node2": [1, 6, 3],  # 3 slots out of 10 → 30%
        },
    )

    model = TDMAModel(config)

    # Node1 owns 2 slots → 20% throughput
    multiplier_node1 = model.get_throughput_multiplier("node1")
    assert multiplier_node1 == 0.2, "Node1 should have 20% throughput"

    # Node2 owns 3 slots → 30% throughput
    multiplier_node2 = model.get_throughput_multiplier("node2")
    assert multiplier_node2 == 0.3, "Node2 should have 30% throughput"


def test_tdma_throughput_multiplier_round_robin():
    """Test throughput multiplier for TDMA round-robin mode."""
    config = TDMASlotConfig(
        slot_assignment_mode=SlotAssignmentMode.ROUND_ROBIN,
        num_slots=12,
        fixed_slot_map={  # Used to infer number of nodes
            "node1": [],
            "node2": [],
            "node3": [],
        },
    )

    model = TDMAModel(config)

    # 3 nodes in round-robin → each gets 33.3%
    multiplier = model.get_throughput_multiplier(
        "node1", all_nodes=["node1", "node2", "node3"]
    )

    expected = 1.0 / 3.0
    assert abs(multiplier - expected) < 0.001, "Round-robin should give 33.3% per node"


def test_tdma_throughput_multiplier_random():
    """Test throughput multiplier for TDMA random mode."""
    config = TDMASlotConfig(
        slot_assignment_mode=SlotAssignmentMode.RANDOM,
        slot_probability=0.3,
    )

    model = TDMAModel(config)

    # Random mode: throughput = slot_probability
    multiplier = model.get_throughput_multiplier("node1")

    assert multiplier == 0.3, "Random TDMA throughput should equal slot_probability"


def test_tdma_all_interferers():
    """Test compute_interference_probabilities for multiple interferers."""
    config = TDMASlotConfig(
        slot_assignment_mode=SlotAssignmentMode.FIXED,
        num_slots=10,
        fixed_slot_map={
            "node1": [0, 5],
            "node2": [1, 6],
            "node3": [0, 2],  # Collides with node1 in slot 0
            "node4": [9],
        },
    )

    model = TDMAModel(config)

    # Link node1→node2 with interferers node3, node4
    probs = model.compute_interference_probabilities(
        tx_node="node1",
        rx_node="node2",
        interferer_nodes=["node3", "node4"],
    )

    # node3: 1 collision slot (0) → Pr = 0.1
    # node4: orthogonal → Pr = 0.0
    assert probs["node3"] == 0.1, "node3 should collide in 1/10 slots"
    assert probs["node4"] == 0.0, "node4 should be orthogonal"


def test_tdma_slot_duration():
    """Test slot duration calculation."""
    frame_duration_ms = 10.0
    num_slots = 10

    slot_duration = TDMAModel.compute_slot_duration_ms(frame_duration_ms, num_slots)

    assert slot_duration == 1.0, "10ms frame / 10 slots = 1ms per slot"


def test_tdma_fixed_requires_slot_map():
    """Test that FIXED mode requires fixed_slot_map."""
    config = TDMASlotConfig(
        slot_assignment_mode=SlotAssignmentMode.FIXED,
        fixed_slot_map=None,  # Missing!
    )

    with pytest.raises(ValueError, match="FIXED slot assignment mode requires"):
        TDMAModel(config)


def test_tdma_vs_csma_comparison():
    """Test that TDMA provides better SINR than CSMA for orthogonal slots."""
    # TDMA with orthogonal slots
    tdma_config = TDMASlotConfig(
        slot_assignment_mode=SlotAssignmentMode.FIXED,
        num_slots=10,
        fixed_slot_map={
            "node1": [0, 5],
            "node2": [1, 6],
            "node3": [2, 7],
        },
    )

    tdma_model = TDMAModel(tdma_config)

    # Link node1→node2 with interferer node3
    tdma_prob = tdma_model.compute_interference_probability(
        tx_node="node1",
        rx_node="node2",
        interferer_node="node3",
    )

    # TDMA orthogonal: Pr[interference] = 0.0
    assert tdma_prob == 0.0

    # Compare to CSMA hidden node scenario (Pr = traffic_load)
    # CSMA would have Pr = 0.3 for hidden nodes
    # TDMA provides deterministic zero interference (better SINR)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
