# Mobility Examples for SiNE

This directory contains example scripts demonstrating how to control node movement in SiNE wireless network emulations.

## Prerequisites

1. **Channel Server** - Must be running (Terminal 1):
   ```bash
   uv run sine channel-server
   ```

2. **Emulation with Mobility API** - Deploy with `--enable-mobility` flag (Terminal 2):
   ```bash
   sudo $(which uv) run sine deploy --enable-mobility examples/vacuum_20m/network.yaml
   ```

   This starts both the emulation and the mobility API server on port 8001.

3. **Python dependencies** - Installed automatically:
   - `httpx` - For HTTP requests to mobility API
   - `asyncio` - For async movement control

## Available Examples

### 1. Linear Movement (`linear_movement.py`)

Moves a node linearly from one position to another at constant velocity.

**Usage:**
```bash
uv run python examples/mobility/linear_movement.py <node> <start_x> <start_y> <start_z> <end_x> <end_y> <end_z> <velocity>
```

**Examples:**
```bash
# Move node2 from (20, 0, 1) to (0, 0, 1) at 1 m/s
uv run python examples/mobility/linear_movement.py node2 20.0 0.0 1.0 0.0 0.0 1.0 1.0

# Move node2 from (0, 0, 1) to (20, 0, 1) at 2 m/s
uv run python examples/mobility/linear_movement.py node2 0.0 0.0 1.0 20.0 0.0 1.0 2.0
```

**What it does:**
- Moves the specified node from start position to end position at constant velocity
- Updates position every 100ms
- Demonstrates how SNR/throughput changes with distance
- Example: Moving from (20, 0, 1) to (0, 0, 1) at 1 m/s takes 20 seconds

### 2. Waypoint Movement (`waypoint_movement.py`)

Moves nodes through a series of predefined waypoints with different velocities.

**Usage:**
```bash
uv run python examples/mobility/waypoint_movement.py
```

**What it does:**
- Moves `node2` through a rectangular path
- Each segment has its own velocity
- Demonstrates path-based mobility patterns

**Customization:**
```python
waypoints = [
    Waypoint(position=(20, 0, 1), velocity=1.0),   # Start, move at 1 m/s
    Waypoint(position=(10, 0, 1), velocity=2.0),   # Move at 2 m/s
    Waypoint(position=(10, 10, 1), velocity=1.5),  # Move at 1.5 m/s
    Waypoint(position=(20, 10, 1), velocity=1.0),  # Back to start
]

await mobility.follow_waypoints(
    node="node2",
    waypoints=waypoints,
    loop=False  # Set to True for continuous movement
)
```

## Mobility API Endpoints

The mobility server exposes these REST endpoints:

### Update Position
```bash
curl -X POST http://localhost:8001/api/mobility/update \
     -H "Content-Type: application/json" \
     -d '{"node": "node2", "x": 10.0, "y": 5.0, "z": 1.5}'
```

### Get Position
```bash
curl http://localhost:8001/api/mobility/position/node2
```

### List All Nodes
```bash
curl http://localhost:8001/api/nodes | jq
```

### Health Check
```bash
curl http://localhost:8001/health
```

## Monitoring Link Quality During Movement

While running mobility scripts, you can monitor the changing link conditions:

### Option 1: Check Netem Configuration
```bash
# Watch netem parameters update in real-time
watch -n 0.5 './check_netem.sh'
```

### Option 2: Monitor with iperf3
```bash
# Terminal 1: Start iperf3 server on node1
docker exec -it clab-vacuum-20m-node1 iperf3 -s

# Terminal 2: Continuous iperf3 tests from node2
while true; do
    docker exec -it clab-vacuum-20m-node2 iperf3 -c 192.168.1.1 -t 2
    sleep 1
done
```

### Option 3: Query Positions via API
```bash
watch -n 0.5 'curl -s http://localhost:8001/api/nodes | jq'
```

## Expected Behavior

As nodes move:

1. **Getting Closer** (decreasing distance):
   - Path loss decreases
   - SNR increases
   - Data rate increases (higher throughput)
   - Packet loss decreases

2. **Moving Apart** (increasing distance):
   - Path loss increases
   - SNR decreases
   - Data rate decreases (lower throughput)
   - Packet loss may increase

3. **Perpendicular Movement** (constant distance):
   - Link quality remains relatively stable
   - Small variations due to different multipath conditions

## Creating Custom Mobility Patterns

You can create your own mobility scripts using the examples as templates:

```python
import asyncio
from examples.mobility.linear_movement import LinearMobility

async def my_custom_pattern():
    mobility = LinearMobility(api_url="http://localhost:8001")

    # Your custom movement logic here
    # ...

    await mobility.close()

asyncio.run(my_custom_pattern())
```

## Troubleshooting

**Problem**: `Connection refused` error

**Solution**: Make sure you deployed with the `--enable-mobility` flag:
```bash
sudo $(which uv) run sine deploy --enable-mobility examples/vacuum_20m/network.yaml
```

---

**Problem**: `AttributeError: 'NodeConfig' object has no attribute 'wireless'`

**Solution**: This was a bug in older versions. Update to the latest version of SiNE.

---

**Problem**: Node position not updating

**Solution**: Check that the node name exists and has wireless capability:
```bash
curl http://localhost:8001/api/nodes
```

---

**Problem**: `503 Service Unavailable`

**Solution**: Emulation may have stopped. Restart deployment with `--enable-mobility`.

---

**Problem**: Slow updates or timeouts

**Solution**: Reduce `update_interval_ms` or check if channel server is overloaded.

## Advanced Usage

### Parallel Movement

Move multiple nodes simultaneously:

```python
async def parallel_movement():
    mobility = LinearMobility()

    # Start both movements concurrently
    await asyncio.gather(
        mobility.move_linear("node1", (0, 0, 1), (10, 0, 1), 1.0),
        mobility.move_linear("node2", (20, 0, 1), (10, 0, 1), 1.0),
    )
```

### Variable Velocity

Change velocity during movement by breaking into multiple linear segments:

```python
# Slow start, fast middle, slow end
await mobility.move_linear(node, (0, 0, 1), (5, 0, 1), 0.5)   # Slow
await mobility.move_linear(node, (5, 0, 1), (15, 0, 1), 2.0)  # Fast
await mobility.move_linear(node, (15, 0, 1), (20, 0, 1), 0.5) # Slow
```

## Documentation

For more information, see:
- [Main README.md](../../README.md) - SiNE overview
- [CLAUDE.md](../../CLAUDE.md) - Developer documentation
- Mobility API: http://localhost:8001/docs (when server running)
