#!/usr/bin/env python3
"""
Waypoint Movement Script for SiNE.

Moves a node through a series of predefined waypoints at specified velocities.
Useful for scripted mobility patterns (e.g., walk into a room, pause, walk back).

Usage:
    # Terminal 1: Start channel server
    uv run sine channel-server

    # Terminal 2: Deploy with control API enabled
    UV_PATH=$(which uv) sudo -E $(which uv) run sine deploy \
        --enable-control examples/for_user/05_moving_node/network.yaml

    # Terminal 3: Edit the waypoints in this script, then run it
    uv run python examples/for_user/05_moving_node/waypoint_movement.py

    # Use a slower update interval if you see lag warnings (default: 100ms)
    uv run python examples/for_user/05_moving_node/waypoint_movement.py --interval 500

Example waypoint definition:
    waypoints = [
        Waypoint(position=(30, 5, 1), velocity=1.0),   # Start south
        Waypoint(position=(30, 20, 1), velocity=1.0),  # Move to doorway
        Waypoint(position=(30, 35, 1), velocity=1.0),  # Move north past doorway
        Waypoint(position=(30, 5, 1), velocity=2.0),   # Return quickly
    ]
"""

import argparse
import asyncio
import math
import time
from dataclasses import dataclass
from typing import List, Tuple

import httpx


@dataclass
class Waypoint:
    """A waypoint with position and velocity to the next waypoint."""

    position: Tuple[float, float, float]  # (x, y, z) in meters
    velocity: float  # Velocity to NEXT waypoint in m/s


class WaypointMobility:
    """Move nodes through predefined waypoints."""

    def __init__(
        self,
        api_url: str = "http://localhost:8002",
        update_interval_ms: int = 100,
    ):
        self.api_url = api_url
        self.update_interval = update_interval_ms / 1000.0
        self.client = httpx.AsyncClient()

    async def move_to_position(
        self,
        node: str,
        start: Tuple[float, float, float],
        end: Tuple[float, float, float],
        velocity: float,
    ) -> None:
        """Move node linearly from start to end at constant velocity."""
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        dz = end[2] - start[2]
        distance = math.sqrt(dx**2 + dy**2 + dz**2)

        if distance < 0.01:
            return

        dir_x = dx / distance
        dir_y = dy / distance
        dir_z = dz / distance

        total_time = distance / velocity
        num_steps = max(1, int(total_time / self.update_interval))
        step_distance = distance / num_steps

        current_pos = list(start)
        traveled = 0.0

        for _ in range(num_steps + 1):
            t0 = time.monotonic()
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

            except httpx.HTTPError as e:
                print(f"  Error: {e}")
                return

            if traveled >= distance:
                break

            traveled = min(traveled + step_distance, distance)

            current_pos[0] = start[0] + dir_x * traveled
            current_pos[1] = start[1] + dir_y * traveled
            current_pos[2] = start[2] + dir_z * traveled

            elapsed = time.monotonic() - t0
            remaining = self.update_interval - elapsed
            if remaining < 0:
                print(
                    f"  WARNING: channel server took {elapsed*1000:.0f}ms "
                    f"(>{self.update_interval*1000:.0f}ms interval) — "
                    f"movement will lag real-time. "
                    f"Run with --interval {int(elapsed*1000 + 50)} or higher."
                )
            await asyncio.sleep(max(0.0, remaining))

    async def follow_waypoints(
        self, node: str, waypoints: List[Waypoint], loop: bool = False
    ) -> None:
        """
        Move node through a series of waypoints.

        Args:
            node: Node name to move (e.g., "client")
            waypoints: List of Waypoint objects
            loop: If True, repeat path indefinitely
        """
        if len(waypoints) < 2:
            print(f"Error: Need at least 2 waypoints for {node}")
            return

        print(f"\nWaypoint Plan for {node}:")
        print(f"  Waypoints: {len(waypoints)}")
        print(f"  Update interval: {self.update_interval*1000:.0f}ms")
        print(f"  Loop: {'Yes (infinite)' if loop else 'No (once)'}")

        for i, wp in enumerate(waypoints):
            print(
                f"  {i+1}. ({wp.position[0]:.1f}, {wp.position[1]:.1f}, "
                f"{wp.position[2]:.1f}) → {wp.velocity:.1f} m/s"
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

                dx = next_wp.position[0] - current_wp.position[0]
                dy = next_wp.position[1] - current_wp.position[1]
                dz = next_wp.position[2] - current_wp.position[2]
                distance = math.sqrt(dx**2 + dy**2 + dz**2)
                duration = (
                    distance / current_wp.velocity if current_wp.velocity > 0 else 0
                )

                print(
                    f"Waypoint {i+1} → {i+2}: "
                    f"({current_wp.position[0]:.1f}, {current_wp.position[1]:.1f}, "
                    f"{current_wp.position[2]:.1f}) → "
                    f"({next_wp.position[0]:.1f}, {next_wp.position[1]:.1f}, "
                    f"{next_wp.position[2]:.1f}) "
                    f"[{distance:.1f}m @ {current_wp.velocity:.1f} m/s = {duration:.1f}s]"
                )

                await self.move_to_position(
                    node, current_wp.position, next_wp.position, current_wp.velocity
                )

            print(f"Done: {node} completed waypoint path")

            if not loop:
                break

            await asyncio.sleep(1.0)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()


async def main(interval_ms: int) -> None:
    """Walk client through doorway and back."""
    mobility = WaypointMobility(
        api_url="http://localhost:8002", update_interval_ms=interval_ms
    )

    try:
        # Walk client from south (far from doorway) → doorway → north, then return
        # Doorway is at y=20; AP is at (10, 20, 2.5) aligned with doorway
        doorway_crossing = [
            Waypoint(position=(30.0, 5.0, 1.0), velocity=1.0),   # Start: south
            Waypoint(position=(30.0, 20.0, 1.0), velocity=1.0),  # Doorway
            Waypoint(position=(30.0, 35.0, 1.0), velocity=1.0),  # North of doorway
            Waypoint(position=(30.0, 5.0, 1.0), velocity=2.0),   # Return quickly
        ]

        await mobility.follow_waypoints(node="client", waypoints=doorway_crossing)

        print("\nExpected throughput observations:")
        print("  y=5  (south, far from doorway): ~50-100 Mbps  (NLOS, high path loss)")
        print("  y=20 (aligned with doorway):    ~300+ Mbps    (near-LOS via doorway)")
        print("  y=35 (north, past doorway):     ~100-200 Mbps (NLOS again)")

    finally:
        await mobility.close()


if __name__ == "__main__":
    print("=" * 60)
    print("SiNE Waypoint Movement — Example 5: Moving Node")
    print("=" * 60)
    print()
    print("Prerequisites:")
    print("  1. Channel server:  uv run sine channel-server")
    print("  2. Deploy:          UV_PATH=$(which uv) sudo -E $(which uv) run sine deploy \\")
    print("                        --enable-control "
          "examples/for_user/05_moving_node/network.yaml")
    print()

    parser = argparse.ArgumentParser(description="Waypoint movement for SiNE nodes")
    parser.add_argument(
        "--interval",
        type=int,
        default=100,
        metavar="MS",
        help="Position update interval in milliseconds (default: 100). "
             "Increase if you see lag warnings.",
    )
    parsed = parser.parse_args()

    asyncio.run(main(interval_ms=parsed.interval))
