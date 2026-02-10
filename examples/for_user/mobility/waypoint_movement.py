#!/usr/bin/env python3
"""
Waypoint-Based Mobility Example for SiNE.

Moves nodes through a series of predefined waypoints at specified velocities.
Each node follows its own path independently.

Usage:
    # Terminal 1: Start channel server
    uv run sine channel-server

    # Terminal 2: Start mobility API server with emulation
    sudo $(which uv) run sine mobility-server examples/vacuum_20m/network.yaml

    # Terminal 3: Run this mobility script
    uv run python examples/mobility/waypoint_movement.py

Example waypoint definition:
    waypoints = [
        {"position": (0, 0, 1), "velocity": 1.0},   # Start, move at 1 m/s to next
        {"position": (10, 0, 1), "velocity": 2.0},  # Move at 2 m/s to next
        {"position": (10, 10, 1), "velocity": 1.5}, # Move at 1.5 m/s to next
        {"position": (0, 10, 1), "velocity": 1.0},  # Move at 1 m/s to next
        {"position": (0, 0, 1), "velocity": 0.5},   # Return to start slowly
    ]
"""

import asyncio
import httpx
import math
from typing import List, Dict, Tuple
from dataclasses import dataclass


@dataclass
class Waypoint:
    """A waypoint with position and velocity to next waypoint."""

    position: Tuple[float, float, float]  # (x, y, z) in meters
    velocity: float  # Velocity to NEXT waypoint in m/s


class WaypointMobility:
    """Move nodes through predefined waypoints."""

    def __init__(
        self,
        api_url: str = "http://localhost:8002",
        update_interval_ms: int = 100,
    ):
        """
        Initialize waypoint mobility controller.

        Args:
            api_url: Base URL of mobility API server
            update_interval_ms: Position update interval in milliseconds
        """
        self.api_url = api_url
        self.update_interval = update_interval_ms / 1000.0  # Convert to seconds
        self.client = httpx.AsyncClient()

    async def move_to_position(
        self,
        node: str,
        start: Tuple[float, float, float],
        end: Tuple[float, float, float],
        velocity: float,
    ) -> None:
        """
        Move node from start to end at constant velocity.

        Args:
            node: Node name
            start: Starting position (x, y, z)
            end: Ending position (x, y, z)
            velocity: Movement velocity in m/s
        """
        # Calculate distance and direction
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        dz = end[2] - start[2]
        distance = math.sqrt(dx**2 + dy**2 + dz**2)

        if distance < 0.01:  # Already at destination (within 1cm)
            return

        # Unit direction vector
        dir_x = dx / distance
        dir_y = dy / distance
        dir_z = dz / distance

        # Calculate steps
        total_time = distance / velocity
        num_steps = max(1, int(total_time / self.update_interval))
        step_distance = distance / num_steps

        # Move step by step
        current_pos = list(start)
        traveled = 0.0

        for step in range(num_steps + 1):
            try:
                response = await self.client.post(
                    f"{self.api_url}/api/mobility/update",
                    json={
                        "node": node,
                        "x": current_pos[0],
                        "y": current_pos[1],
                        "z": current_pos[2],
                    },
                    timeout=5.0,
                )
                response.raise_for_status()

            except httpx.HTTPError as e:
                print(f"  Error: {e}")
                return

            if traveled >= distance:
                break

            traveled += step_distance
            if traveled > distance:
                traveled = distance

            current_pos[0] = start[0] + dir_x * traveled
            current_pos[1] = start[1] + dir_y * traveled
            current_pos[2] = start[2] + dir_z * traveled

            await asyncio.sleep(self.update_interval)

    async def follow_waypoints(
        self, node: str, waypoints: List[Waypoint], loop: bool = False
    ) -> None:
        """
        Move node through a series of waypoints.

        Args:
            node: Node name to move
            waypoints: List of waypoints to follow
            loop: If True, return to first waypoint and repeat indefinitely
        """
        if len(waypoints) < 2:
            print(f"Error: Need at least 2 waypoints for {node}")
            return

        print(f"\nWaypoint Plan for {node}:")
        print(f"  Waypoints: {len(waypoints)}")
        print(f"  Loop: {'Yes (infinite)' if loop else 'No (once)'}")

        for i, wp in enumerate(waypoints):
            print(
                f"  {i+1}. ({wp.position[0]:.1f}, {wp.position[1]:.1f}, {wp.position[2]:.1f}) "
                f"→ {wp.velocity:.1f} m/s"
            )
        print()

        iteration = 0
        while True:
            iteration += 1
            if loop:
                print(f"[Iteration {iteration}]")

            for i in range(len(waypoints) - 1):
                current_wp = waypoints[i]
                next_wp = waypoints[i + 1]

                # Calculate segment distance
                dx = next_wp.position[0] - current_wp.position[0]
                dy = next_wp.position[1] - current_wp.position[1]
                dz = next_wp.position[2] - current_wp.position[2]
                distance = math.sqrt(dx**2 + dy**2 + dz**2)
                duration = distance / current_wp.velocity if current_wp.velocity > 0 else 0

                print(
                    f"Waypoint {i+1} → {i+2}: "
                    f"({current_wp.position[0]:.1f}, {current_wp.position[1]:.1f}, {current_wp.position[2]:.1f}) → "
                    f"({next_wp.position[0]:.1f}, {next_wp.position[1]:.1f}, {next_wp.position[2]:.1f}) "
                    f"[{distance:.1f}m @ {current_wp.velocity:.1f} m/s = {duration:.1f}s]"
                )

                await self.move_to_position(
                    node, current_wp.position, next_wp.position, current_wp.velocity
                )

            print(f"✓ {node} completed waypoint path")

            if not loop:
                break

            # Add a small delay between iterations
            await asyncio.sleep(1.0)

    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()


async def main():
    """Run example waypoint movement."""
    mobility = WaypointMobility(
        api_url="http://localhost:8002",
        update_interval_ms=100,
    )

    try:
        # Example 1: Simple rectangular path for node2
        print("=" * 60)
        print("Example: Rectangular Path")
        print("=" * 60)

        rectangular_path = [
            Waypoint(position=(20.0, 0.0, 1.0), velocity=1.0),  # Start (far from node1)
            Waypoint(position=(10.0, 0.0, 1.0), velocity=1.5),  # Move closer
            Waypoint(position=(10.0, 5.0, 1.0), velocity=2.0),  # Move perpendicular
            Waypoint(position=(20.0, 5.0, 1.0), velocity=1.5),  # Move away
            Waypoint(position=(20.0, 0.0, 1.0), velocity=1.0),  # Return to start
        ]

        await mobility.follow_waypoints(
            node="node2", waypoints=rectangular_path, loop=False
        )

        print("\n" + "=" * 60)
        print("Movement Complete!")
        print("=" * 60)
        print("\nObservations:")
        print("  - As node2 moved closer to node1 (at origin), SNR increased")
        print("  - As node2 moved away, path loss increased")
        print("  - Perpendicular movement had minimal link quality change")
        print("\nTry monitoring with:")
        print("  watch -n 0.5 'curl -s http://localhost:8002/api/nodes | jq'")

    finally:
        await mobility.close()


async def advanced_example():
    """Advanced example with multiple nodes and complex paths."""
    mobility = WaypointMobility(api_url="http://localhost:8002", update_interval_ms=100)

    try:
        # Example: Two nodes moving independently
        # node1 stays at origin
        # node2 moves in a pattern

        node2_waypoints = [
            Waypoint(position=(20.0, 0.0, 1.0), velocity=2.0),  # Start far
            Waypoint(position=(15.0, 0.0, 1.0), velocity=1.5),  # Approach
            Waypoint(position=(10.0, 0.0, 1.0), velocity=1.0),  # Slow approach
            Waypoint(position=(5.0, 0.0, 1.0), velocity=0.5),  # Very slow (near node1)
            Waypoint(position=(2.0, 0.0, 1.0), velocity=0.25),  # Very close
            Waypoint(position=(5.0, 0.0, 1.0), velocity=0.5),  # Back away slowly
            Waypoint(position=(10.0, 0.0, 1.0), velocity=1.0),  # Faster
            Waypoint(position=(20.0, 0.0, 1.0), velocity=2.0),  # Return to start
        ]

        print("\n" + "=" * 60)
        print("Advanced Example: Approach and Retreat")
        print("=" * 60)
        print("Node2 will approach node1 at origin, then retreat.")
        print("Watch how link quality changes with distance!")
        print()

        await mobility.follow_waypoints(
            node="node2", waypoints=node2_waypoints, loop=False
        )

    finally:
        await mobility.close()


if __name__ == "__main__":
    print("=" * 60)
    print("SiNE Waypoint Movement Example")
    print("=" * 60)
    print()
    print("Prerequisites:")
    print("  1. Channel server: uv run sine channel-server")
    print("  2. Mobility server:")
    print("     sudo $(which uv) run sine mobility-server examples/vacuum_20m/network.yaml")
    print()

    # Uncomment to run advanced example instead:
    # asyncio.run(advanced_example())

    asyncio.run(main())
