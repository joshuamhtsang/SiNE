"""
Unit tests for CSMA/CA statistical model.

Tests Phase 1.5: WiFi CSMA/CA behavior with carrier sensing and hidden nodes.
"""

import pytest

from sine.channel.csma_model import CSMAModel, compute_distance


def test_compute_distance():
    """Test Euclidean distance calculation."""
    pos1 = (0.0, 0.0, 1.0)
    pos2 = (3.0, 4.0, 1.0)

    # 3-4-5 triangle
    distance = compute_distance(pos1, pos2)
    assert abs(distance - 5.0) < 0.001


def test_csma_model_init():
    """Test CSMA model initialization."""
    model = CSMAModel(
        carrier_sense_range_multiplier=2.5,
        default_traffic_load=0.3,
    )

    assert model.cs_multiplier == 2.5
    assert model.traffic_load == 0.3


def test_csma_within_carrier_sense_range():
    """Test interference probability when interferer is within CS range."""
    model = CSMAModel(carrier_sense_range_multiplier=2.5, default_traffic_load=0.3)

    # Setup: 3 nodes in a line
    # A --- B --- C (50m spacing)
    # Communication range: 50m
    # CS range: 125m (50m × 2.5)
    positions = {
        "A": (0.0, 0.0, 1.0),
        "B": (50.0, 0.0, 1.0),
        "C": (100.0, 0.0, 1.0),
    }

    communication_range = 50.0

    # Link A→B with interferer C
    # Distance A to C: 100m < CS range (125m)
    # Expected: C within CS range of A, Pr[TX]=0.0
    prob = model.compute_interference_probability(
        tx_node="A",
        rx_node="B",
        interferer_node="C",
        positions=positions,
        communication_range=communication_range,
    )

    assert prob == 0.0, "Interferer within CS range should have Pr[TX]=0.0"


def test_csma_hidden_node():
    """Test interference probability for hidden node scenario."""
    model = CSMAModel(carrier_sense_range_multiplier=2.5, default_traffic_load=0.3)

    # Setup: 3 nodes far apart
    # A ----------- B ----------- C (150m spacing)
    # Communication range: 50m
    # CS range: 125m
    # Distance A to C: 300m > CS range
    positions = {
        "A": (0.0, 0.0, 1.0),
        "B": (150.0, 0.0, 1.0),
        "C": (300.0, 0.0, 1.0),
    }

    communication_range = 50.0

    # Link A→B with interferer C
    # Distance A to C: 300m > CS range (125m)
    # Expected: C is hidden node, Pr[TX]=traffic_load
    prob = model.compute_interference_probability(
        tx_node="A",
        rx_node="B",
        interferer_node="C",
        positions=positions,
        communication_range=communication_range,
    )

    assert prob == 0.3, "Hidden node should have Pr[TX]=traffic_load"


def test_csma_all_interferers():
    """Test compute_interference_probabilities for multiple interferers."""
    model = CSMAModel(carrier_sense_range_multiplier=2.5, default_traffic_load=0.3)

    # Setup: 4-node linear topology
    # A --- B --- C --- D (50m spacing)
    # Communication range: 50m
    # CS range: 125m
    positions = {
        "A": (0.0, 0.0, 1.0),
        "B": (50.0, 0.0, 1.0),
        "C": (100.0, 0.0, 1.0),
        "D": (150.0, 0.0, 1.0),
    }

    communication_range = 50.0

    # Link A→B with interferers C, D
    probs = model.compute_interference_probabilities(
        tx_node="A",
        rx_node="B",
        interferer_nodes=["C", "D"],
        positions=positions,
        communication_range=communication_range,
    )

    # Distance A to C: 100m < CS range (125m) → Pr[TX]=0.0
    # Distance A to D: 150m > CS range (125m) → Pr[TX]=0.3
    assert probs["C"] == 0.0, "C within CS range"
    assert probs["D"] == 0.3, "D is hidden node"


def test_csma_spatial_reuse():
    """Test that CSMA model provides spatial reuse benefit."""
    model = CSMAModel(carrier_sense_range_multiplier=2.5, default_traffic_load=0.3)

    # Setup: 4-node linear
    # A --- B --- C --- D (50m spacing)
    positions = {
        "A": (0.0, 0.0, 1.0),
        "B": (50.0, 0.0, 1.0),
        "C": (100.0, 0.0, 1.0),
        "D": (150.0, 0.0, 1.0),
    }

    communication_range = 50.0

    # Link A→B
    probs_ab = model.compute_interference_probabilities(
        tx_node="A",
        rx_node="B",
        interferer_nodes=["C", "D"],
        positions=positions,
        communication_range=communication_range,
    )

    # Expected: C within CS range (Pr=0), D hidden (Pr=0.3)
    # Spatial reuse: only 1 hidden node contributes interference
    num_hidden = sum(1 for p in probs_ab.values() if p > 0)
    assert num_hidden == 1, "Should have 1 hidden node (spatial reuse)"


def test_csma_carrier_sense_range_calculation():
    """Test carrier sense range calculation."""
    communication_range = 50.0
    cs_multiplier = 2.5

    cs_range = CSMAModel.compute_carrier_sense_range(
        communication_range, cs_multiplier
    )

    assert cs_range == 125.0, "CS range should be 2.5× communication range"


def test_csma_custom_traffic_load():
    """Test CSMA model with custom traffic load."""
    model = CSMAModel(carrier_sense_range_multiplier=2.5, default_traffic_load=0.5)

    positions = {
        "A": (0.0, 0.0, 1.0),
        "B": (150.0, 0.0, 1.0),
        "C": (300.0, 0.0, 1.0),
    }

    # Hidden node scenario
    prob = model.compute_interference_probability(
        tx_node="A",
        rx_node="B",
        interferer_node="C",
        positions=positions,
        communication_range=50.0,
        traffic_load=0.5,  # Override default
    )

    assert prob == 0.5, "Should use custom traffic load"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
