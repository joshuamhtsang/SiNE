# Mobility Examples for SiNE

This directory contains example scripts demonstrating how to control node movement in SiNE wireless network emulations.

## Complete Mobility Workflow

This guide walks you through a complete mobility experiment from setup to monitoring.

### Step 1: Build Node Image

First, build the Docker image for the nodes (contains iperf3, tcpdump, etc.):

```bash
docker build -t sine-node:latest docker/node/
```

### Step 2: Start Channel Server

The channel server computes wireless link parameters (Terminal 1):

```bash
uv run sine channel-server
```

**Expected output:**
```
INFO:     Started server process [...]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Step 3: Deploy with Mobility API

Deploy the emulation with mobility API enabled (Terminal 2):

```bash
sudo $(which uv) run sine deploy --enable-mobility examples/for_tests/p2p_fallback_snr_vacuum/network.yaml
```

**What this does:**
- Creates Docker containers via Containerlab
- Computes initial channel conditions via ray tracing
- Applies netem to container interfaces
- **Starts mobility API server on port 8002**
- Keeps running to accept position updates

**Expected output:**
```
Deployed Containers:
  clab-p2p-fb-snr-vacuum-node1 (sine-node:latest)
    PID: 12345
    Interfaces:
      - eth1 @ position (0.0, 0.0, 1.0)

  clab-p2p-fb-snr-vacuum-node2 (sine-node:latest)
    PID: 12346
    Interfaces:
      - eth1 @ position (20.0, 0.0, 1.0)

Link Parameters:
  node1:eth1 ↔ node2:eth1 [wireless]
    Delay: 0.07 ms | Jitter: 0.00 ms | Loss: 0.00% | Rate: 192.0 Mbps

INFO:     Uvicorn running on http://0.0.0.0:8002 (Press CTRL+C to quit)
```

### Step 4: Configure IP Addresses

Containers start with no IP addresses. Assign them (Terminal 3):

```bash
docker exec -it clab-p2p-fb-snr-vacuum-node1 ip addr add 18.0.0.1/24 dev eth1
docker exec -it clab-p2p-fb-snr-vacuum-node2 ip addr add 18.0.0.2/24 dev eth1

# Verify connectivity
docker exec clab-p2p-fb-snr-vacuum-node2 ping -c 3 18.0.0.1
```

### Step 5: Start iperf3 Monitoring

Start iperf3 server on node1 (Terminal 4):

```bash
docker exec -it clab-p2p-fb-snr-vacuum-node1 iperf3 -s
```

Run continuous throughput tests from node2 (Terminal 5):

```bash
while true; do
    docker exec clab-p2p-fb-snr-vacuum-node2 iperf3 -c 18.0.0.1 -t 2
    sleep 1
done
```

### Step 6: Run Mobility Script

Move node2 from 20m to 300m away (Terminal 6):

```bash
# Move at 3 m/s (takes ~93 seconds)
uv run python examples/mobility/linear_movement.py node2 20.0 0.0 1.0 300.0 0.0 1.0 3.0
```

**What you'll see:**
- Terminal 5 (iperf3): Throughput decreasing from ~188 Mbps to ~50-100 Mbps
- Terminal 2 (deployment): Logs showing position updates and netem reconfigurations

### Step 7: Cleanup

When done, destroy the emulation:

```bash
sudo $(which uv) run sine destroy examples/for_tests/p2p_fallback_snr_vacuum/network.yaml
```

## Prerequisites Summary

1. **Channel Server** - Computes link parameters (Terminal 1):
   ```bash
   uv run sine channel-server
   ```

2. **Emulation with Mobility API** - Deploy with `--enable-mobility` (Terminal 2):
   ```bash
   sudo $(which uv) run sine deploy --enable-mobility examples/for_tests/p2p_fallback_snr_vacuum/network.yaml
   ```

3. **Python dependencies** - Installed automatically via `uv sync`:
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
# Move node2 from (20, 0, 1) to (300, 0, 1) at 3 m/s (takes ~93 seconds)
uv run python examples/mobility/linear_movement.py node2 20.0 0.0 1.0 300.0 0.0 1.0 3.0

# Move node2 back from (300, 0, 1) to (20, 0, 1) at 3 m/s
uv run python examples/mobility/linear_movement.py node2 300.0 0.0 1.0 20.0 0.0 1.0 3.0

# Move node2 from (20, 0, 1) to (0, 0, 1) at 1 m/s (takes 20 seconds)
uv run python examples/mobility/linear_movement.py node2 20.0 0.0 1.0 0.0 0.0 1.0 1.0
```

**What it does:**
- Moves the specified node from start position to end position at constant velocity
- Updates position every 100ms (configurable in the script)
- Demonstrates how SNR/throughput changes with distance
- Travel time = distance / velocity
  - Example: 280 meters at 3 m/s = ~93 seconds
  - Example: 20 meters at 1 m/s = 20 seconds

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
curl -X POST http://localhost:8002/api/mobility/update \
     -H "Content-Type: application/json" \
     -d '{"node": "node2", "x": 10.0, "y": 5.0, "z": 1.5}'
```

### Get Position
```bash
curl http://localhost:8002/api/mobility/position/node2
```

### List All Nodes
```bash
curl http://localhost:8002/api/nodes | jq
```

### Health Check
```bash
curl http://localhost:8002/health
```

## Monitoring Link Quality During Movement

While running mobility scripts, you can monitor the changing link conditions in real-time:

### Option 1: Monitor with iperf3 (Recommended)

**Setup** (run once after deployment):
```bash
# Configure IP addresses
docker exec -it clab-p2p-fb-snr-vacuum-node1 ip addr add 18.0.0.1/24 dev eth1
docker exec -it clab-p2p-fb-snr-vacuum-node2 ip addr add 18.0.0.2/24 dev eth1

# Start iperf3 server on node1 (Terminal 1)
docker exec -it clab-p2p-fb-snr-vacuum-node1 iperf3 -s
```

**Continuous monitoring** (Terminal 2):
```bash
# Run continuous 2-second iperf3 tests
while true; do
    docker exec clab-p2p-fb-snr-vacuum-node2 iperf3 -c 18.0.0.1 -t 2
    sleep 1
done
```

**Expected behavior:**
- **20m distance**: ~188 Mbps (good SNR, low loss)
- **100m distance**: ~188 Mbps (still good with 64-QAM LDPC)
- **200m distance**: ~150-180 Mbps (SNR degrading, increased loss)
- **300m distance**: ~50-100 Mbps (significant degradation, high loss)

**Interpreting iperf3 output:**
```
[ ID] Interval           Transfer     Bitrate         Retr  Cwnd
[  5]   0.00-2.00   sec  44.8 MBytes   188 Mbits/sec    0   1.12 MBytes
                                      ^^^^^^^^^^^^^^^  ^^^
                                      Throughput       Retransmissions
```
- **Bitrate**: Actual throughput (decreases with distance)
- **Retr**: Retransmissions (increases when SNR drops, packet loss increases)
- **Cwnd**: TCP congestion window (shrinks when experiencing loss)

### Option 2: Query Positions via API
```bash
# Watch node positions update
watch -n 0.5 'curl -s http://localhost:8002/api/nodes | jq'

# Get single node position
curl -s http://localhost:8002/api/mobility/position/node2 | jq
```

**Example output:**
```json
{
  "node1": {
    "interfaces": {
      "eth1": {"x": 0.0, "y": 0.0, "z": 1.0}
    }
  },
  "node2": {
    "interfaces": {
      "eth1": {"x": 150.5, "y": 0.0, "z": 1.0}
    }
  }
}
```

### Option 3: Check Netem Configuration
```bash
# Watch netem parameters update in real-time
watch -n 0.5 'docker exec clab-p2p-fb-snr-vacuum-node1 tc -s qdisc show dev eth1'

# OR use the check script
cd examples/vacuum_20m
watch -n 0.5 './check_netem.sh'
```

**What to look for:**
```
qdisc netem 1: root ... delay 100us ...
qdisc tbf 2: parent 1: rate 192Mbit burst 98174b lat 50ms
                            ^^^^^^^
                            Rate decreases as distance increases
```

### Option 4: Debug Ray Tracing Paths

Query detailed path information at specific positions:

```bash
# Get path details at current position
curl -X POST http://localhost:8000/debug/paths \
  -H "Content-Type: application/json" \
  -d '{
    "tx_position": {"x": 0.0, "y": 0.0, "z": 1.0},
    "rx_position": {"x": 100.0, "y": 0.0, "z": 1.0}
  }' | jq
```

This shows:
- `distance_m`: Direct line distance
- `num_paths`: Number of propagation paths found
- `strongest_path.power_db`: Received power
- `paths[].delay_ns`: Propagation delay per path

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
    mobility = LinearMobility(api_url="http://localhost:8002")

    # Your custom movement logic here
    # ...

    await mobility.close()

asyncio.run(my_custom_pattern())
```

## Troubleshooting

**Problem**: `Connection refused` error

**Solution**: Make sure you deployed with the `--enable-mobility` flag:
```bash
sudo $(which uv) run sine deploy --enable-mobility examples/for_tests/p2p_fallback_snr_vacuum/network.yaml
```

---

**Problem**: `AttributeError: 'NodeConfig' object has no attribute 'wireless'`

**Solution**: This was a bug in older versions. Update to the latest version of SiNE.

---

**Problem**: Node position not updating

**Solution**: Check that the node name exists and has wireless capability:
```bash
curl http://localhost:8002/api/nodes
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

## Advanced Configuration

### Packet Size Configuration

The `packet_size_bits` parameter (default: 12000 bits = 1500 bytes MTU) affects PER calculation and thus the `loss_percent` netem parameter. Adjust this based on your application's typical packet size:

```yaml
interfaces:
  eth1:
    wireless:
      packet_size_bits: 4800  # 600 byte packets for VoIP
      # ... other wireless params
```

**Typical values:**
- **VoIP/gaming**: 480-960 bits (60-120 bytes) - Low latency, small packets
- **Standard Ethernet**: 12000 bits (1500 bytes) - Default MTU
- **IoT sensors**: 160-800 bits (20-100 bytes) - Minimal payload
- **Satellite links**: 4000-8000 bits (500-1000 bytes) - Reduce error probability
- **Jumbo frames**: 72000 bits (9000 bytes) - High-throughput file transfer

**Impact on PER:**
Larger packets have higher error probability at the same BER:
```
PER = 1 - (1 - BER)^packet_size_bits
```

For example, at BER = 1e-5:
- 480 bits → PER ≈ 0.48%
- 4800 bits → PER ≈ 4.7%
- 12000 bits → PER ≈ 11.3%

Smaller packets improve reliability but increase protocol overhead.

## Documentation

For more information, see:
- [Main README.md](../../README.md) - SiNE overview
- [CLAUDE.md](../../CLAUDE.md) - Developer documentation
- Mobility API: http://localhost:8002/docs (when server running)
