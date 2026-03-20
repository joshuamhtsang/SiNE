#!/usr/bin/env python3
"""
Linear Movement Script for SiNE.

Moves a node linearly from a start position to an end position
at a constant velocity, updating the Controller API at each step.

Usage:
    # Terminal 1: Start channel server
    uv run sine channel-server

    # Terminal 2: Deploy with control API enabled
    UV_PATH=$(which uv) sudo -E $(which uv) run sine deploy --enable-control examples/for_user/05_moving_node/network.yaml

    # Terminal 3: Run this script
    uv run python examples/for_user/05_moving_node/linear_movement.py <node> <start_x> <start_y> <start_z> <end_x> <end_y> <end_z> <velocity>

Examples:
    # Walk client northward past the doorway (1 m/s)
    uv run python examples/for_user/05_moving_node/linear_movement.py \\
        client 30.0 5.0 1.0 30.0 35.0 1.0 1.0

    # Walk client southward back to start (1 m/s)
    uv run python examples/for_user/05_moving_node/linear_movement.py \\
        client 30.0 35.0 1.0 30.0 5.0 1.0 1.0
"""

import asyncio
import httpx
import math
import sys
from typing import Tuple


class LinearMobility:
    """Move a node linearly from start to end position."""

    def __init__(
        self,
        api_url: str = "http://localhost:8002",
        update_interval_ms: int = 100,
    ):
        self.api_url = api_url
        self.update_interval = update_interval_ms / 1000.0
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
            node: Node name to move (e.g., "client")
            start: Starting position (x, y, z) in meters
            end: Ending position (x, y, z) in meters
            velocity: Movement velocity in meters/second
        """
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        dz = end[2] - start[2]
        distance = math.sqrt(dx**2 + dy**2 + dz**2)

        if distance == 0:
            print(f"Node {node} already at destination")
            return

        dir_x = dx / distance
        dir_y = dy / distance
        dir_z = dz / distance

        total_time = distance / velocity
        num_steps = int(total_time / self.update_interval)
        step_distance = velocity * self.update_interval

        print(f"\nLinear Movement Plan for {node}:")
        print(f"  Start: ({start[0]:.2f}, {start[1]:.2f}, {start[2]:.2f}) m")
        print(f"  End:   ({end[0]:.2f}, {end[1]:.2f}, {end[2]:.2f}) m")
        print(f"  Distance: {distance:.2f} m")
        print(f"  Velocity: {velocity:.2f} m/s")
        print(f"  Duration: {total_time:.2f} s")
        print(f"  Steps: {num_steps} (every {self.update_interval*1000:.0f} ms)")
        print()

        current_pos = list(start)
        traveled = 0.0

        for step in range(num_steps + 1):
            try:
                response = await self.client.post(
                    f"{self.api_url}/api/control/update",
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

            if traveled >= distance:
                break

            traveled += step_distance
            if traveled > distance:
                traveled = distance

            current_pos[0] = start[0] + dir_x * traveled
            current_pos[1] = start[1] + dir_y * traveled
            current_pos[2] = start[2] + dir_z * traveled

            await asyncio.sleep(self.update_interval)

        print(f"\nDone: {node} reached destination")

    async def close(self) -> None:
        await self.client.aclose()


async def main():
    args = sys.argv[1:]

    if len(args) != 8:
        print(f"Error: Expected 8 arguments, got {len(args)}")
        print()
        print("Usage:")
        print("  uv run python examples/for_user/05_moving_node/linear_movement.py")
        print("      <node> <start_x> <start_y> <start_z> <end_x> <end_y> <end_z> <velocity>")
        print()
        print("Example (walk client past doorway at 1 m/s):")
        print("  uv run python examples/for_user/05_moving_node/linear_movement.py \\")
        print("      client 30.0 5.0 1.0 30.0 35.0 1.0 1.0")
        sys.exit(1)

    try:
        node = args[0]
        start_x = float(args[1])
        start_y = float(args[2])
        start_z = float(args[3])
        end_x = float(args[4])
        end_y = float(args[5])
        end_z = float(args[6])
        velocity = float(args[7])

        if velocity <= 0:
            print("Error: Velocity must be positive")
            sys.exit(1)

    except ValueError as e:
        print(f"Error: Invalid argument — {e}")
        sys.exit(1)

    mobility = LinearMobility(api_url="http://localhost:8002", update_interval_ms=100)

    try:
        await mobility.move_linear(
            node=node,
            start=(start_x, start_y, start_z),
            end=(end_x, end_y, end_z),
            velocity=velocity,
        )
        print("\nMovement complete!")
        print("Watch live positions: curl http://localhost:8002/api/control/position/" + node)

    finally:
        await mobility.close()


if __name__ == "__main__":
    print("=" * 60)
    print("SiNE Linear Movement — Example 5: Moving Node")
    print("=" * 60)
    print()
    print("Prerequisites:")
    print("  1. Channel server:  uv run sine channel-server")
    print("  2. Deploy:          UV_PATH=$(which uv) sudo -E $(which uv) run sine deploy \\")
    print("                          --enable-control examples/for_user/05_moving_node/network.yaml")
    print()

    asyncio.run(main())
