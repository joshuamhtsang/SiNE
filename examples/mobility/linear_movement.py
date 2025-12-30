#!/usr/bin/env python3
"""
Linear Movement Mobility Example for SiNE.

Moves a node linearly from a start position to an end position
at a constant velocity.

Usage:
    # Terminal 1: Start channel server
    uv run sine channel-server

    # Terminal 2: Start mobility API server with emulation
    sudo $(which uv) run sine mobility-server examples/vacuum_20m/network.yaml

    # Terminal 3: Run this mobility script
    uv run python examples/mobility/linear_movement.py

Example:
    Move node2 from (20, 0, 1) to (0, 0, 1) at 1 m/s:
    - Distance: 20 meters
    - Velocity: 1 m/s
    - Time: 20 seconds
    - Updates every 100ms
"""

import asyncio
import httpx
import math
from typing import Tuple


class LinearMobility:
    """Move a node linearly from start to end position."""

    def __init__(
        self,
        api_url: str = "http://localhost:8001",
        update_interval_ms: int = 100,
    ):
        """
        Initialize linear mobility controller.

        Args:
            api_url: Base URL of mobility API server
            update_interval_ms: Position update interval in milliseconds
        """
        self.api_url = api_url
        self.update_interval = update_interval_ms / 1000.0  # Convert to seconds
        self.client = httpx.AsyncClient()

    async def move_linear(
        self,
        node: str,
        start: Tuple[float, float, float],
        end: Tuple[float, float, float],
        velocity: float,
    ) -> None:
        """
        Move node linearly from start to end at constant velocity.

        Args:
            node: Node name to move
            start: Starting position (x, y, z) in meters
            end: Ending position (x, y, z) in meters
            velocity: Movement velocity in meters/second

        The node will move from start to end, updating position every
        update_interval seconds.
        """
        # Calculate total distance and direction
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        dz = end[2] - start[2]
        distance = math.sqrt(dx**2 + dy**2 + dz**2)

        if distance == 0:
            print(f"Node {node} already at destination")
            return

        # Unit direction vector
        dir_x = dx / distance
        dir_y = dy / distance
        dir_z = dz / distance

        # Calculate total time and number of steps
        total_time = distance / velocity
        num_steps = int(total_time / self.update_interval)

        # Distance per step
        step_distance = velocity * self.update_interval

        print(f"\nLinear Movement Plan for {node}:")
        print(f"  Start: ({start[0]:.2f}, {start[1]:.2f}, {start[2]:.2f}) m")
        print(f"  End:   ({end[0]:.2f}, {end[1]:.2f}, {end[2]:.2f}) m")
        print(f"  Distance: {distance:.2f} m")
        print(f"  Velocity: {velocity:.2f} m/s")
        print(f"  Duration: {total_time:.2f} s")
        print(f"  Steps: {num_steps} (every {self.update_interval*1000:.0f} ms)")
        print()

        # Move node step by step
        current_pos = list(start)
        traveled = 0.0

        for step in range(num_steps + 1):
            # Update position
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

                progress = (traveled / distance) * 100
                print(
                    f"Step {step}/{num_steps}: "
                    f"({current_pos[0]:.2f}, {current_pos[1]:.2f}, {current_pos[2]:.2f}) "
                    f"[{progress:.1f}%]"
                )

            except httpx.HTTPError as e:
                print(f"Error updating position: {e}")
                break

            # Check if we've reached the destination
            if traveled >= distance:
                break

            # Calculate next position
            traveled += step_distance
            if traveled > distance:
                traveled = distance

            # Update current position along direction vector
            current_pos[0] = start[0] + dir_x * traveled
            current_pos[1] = start[1] + dir_y * traveled
            current_pos[2] = start[2] + dir_z * traveled

            await asyncio.sleep(self.update_interval)

        print(f"\n✓ {node} reached destination")

    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()


async def main():
    """Run example linear movement."""
    mobility = LinearMobility(
        api_url="http://localhost:8001",
        update_interval_ms=100,  # Update every 100ms
    )

    try:
        # Example: Move node2 from (20, 0, 1) to (0, 0, 1) at 1 m/s
        # This simulates node2 moving towards node1 along the X-axis
        await mobility.move_linear(
            node="node2",
            start=(20.0, 0.0, 1.0),  # Starting position
            end=(0.0, 0.0, 1.0),  # Ending position (near node1)
            velocity=1.0,  # 1 meter per second
        )

        print("\nMovement complete! Check iperf3 throughput at different distances.")
        print("As node2 approaches node1, you should see:")
        print("  - Decreasing path loss")
        print("  - Increasing SNR")
        print("  - Higher data rates (closer to theoretical maximum)")

    finally:
        await mobility.close()


if __name__ == "__main__":
    print("=" * 60)
    print("SiNE Linear Movement Example")
    print("=" * 60)
    print()
    print("Prerequisites:")
    print("  1. Channel server running: uv run sine channel-server")
    print("  2. Mobility server running:")
    print("     sudo $(which uv) run sine mobility-server examples/vacuum_20m/network.yaml")
    print()
    print("Starting linear movement in 2 seconds...")
    print()

    asyncio.run(main())
