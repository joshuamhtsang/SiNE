#!/usr/bin/env python3
"""
Demonstration of InterferenceEngine (Phase 0).

Shows how to compute interference from multiple transmitters using PathSolver.
This is a standalone example that doesn't require deploying containers.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sine.channel.interference_calculator import (
    InterferenceEngine,
    TransmitterInfo,
)


def main():
    """Demonstrate interference computation for 3-node equilateral triangle."""
    print("=" * 80)
    print("InterferenceEngine Demo - 3-Node Equilateral Triangle")
    print("=" * 80)
    print()

    # Initialize engine with empty scene (vacuum)
    print("1. Initializing InterferenceEngine with vacuum scene...")
    engine = InterferenceEngine()
    engine.load_scene(scene_path=None, frequency_hz=5.18e9, bandwidth_hz=80e6)
    print("   ✓ Scene loaded (free space)")
    print()

    # Define 3-node equilateral triangle (100m sides)
    positions = {
        "node1": (0.0, 0.0, 1.5),
        "node2": (100.0, 0.0, 1.5),
        "node3": (50.0, 86.6, 1.5),
    }

    # Transmitter parameters (WiFi 6)
    tx_power_dbm = 20.0
    antenna_gain_dbi = 2.15
    frequency_hz = 5.18e9

    print("2. Topology:")
    print(f"   Node1: {positions['node1']}")
    print(f"   Node2: {positions['node2']}")
    print(f"   Node3: {positions['node3']}")
    print(f"   TX power: {tx_power_dbm} dBm")
    print(f"   Antenna gain: {antenna_gain_dbi} dBi")
    print()

    # Compute interference at each node from the other two
    print("3. Computing interference at each node:")
    print("-" * 80)

    for rx_node, rx_pos in positions.items():
        print(f"\n   Receiver: {rx_node} at {rx_pos}")

        # Create interferers list (all nodes except RX)
        interferers = [
            TransmitterInfo(
                node_name=tx_node,
                position=tx_pos,
                tx_power_dbm=tx_power_dbm,
                antenna_gain_dbi=antenna_gain_dbi,
                frequency_hz=frequency_hz
            )
            for tx_node, tx_pos in positions.items()
            if tx_node != rx_node
        ]

        # Compute interference
        result = engine.compute_interference_at_receiver(
            rx_position=rx_pos,
            rx_antenna_gain_dbi=antenna_gain_dbi,
            rx_node=rx_node,
            interferers=interferers
        )

        print(f"   Total interference: {result.total_interference_dbm:.2f} dBm")
        print(f"   Number of interferers: {result.num_interferers}")
        print(f"   Individual contributions:")

        for term in result.interference_terms:
            print(f"     • {term.source}: {term.power_dbm:.2f} dBm")

    print()
    print("=" * 80)

    # Get cache statistics
    cache_stats = engine.get_cache_stats()
    print(f"\nCache Statistics:")
    print(f"  Cached paths: {cache_stats['num_cached_paths']}")
    print(f"  (All paths cached for static topology)")

    print()
    print("=" * 80)
    print("Demo Complete!")
    print("=" * 80)
    print()
    print("Key observations:")
    print("  • All nodes see similar interference (~-59 dBm) due to symmetry")
    print("  • Interference includes TX and RX antenna gains")
    print("  • PathSolver provides accurate per-link computation")
    print("  • Path caching works for repeated computations")
    print()


if __name__ == "__main__":
    try:
        main()
    except ImportError as e:
        print(f"ERROR: {e}")
        print()
        print("This demo requires Sionna. Install with:")
        print("  uv sync")
        sys.exit(1)
