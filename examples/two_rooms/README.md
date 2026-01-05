# Two-Room Indoor Propagation Example

This example demonstrates indoor RF propagation through a doorway between two concrete rooms, showcasing multipath effects, diffraction, and wall penetration loss.

## Scene Description

The scene (`scenes/two_rooms.xml`) consists of:

- **Two equal-sized rooms**: 20m × 40m each (total area: 40m × 40m)
- **Dividing wall**: 10cm thick concrete wall at x=20m separating the rooms
- **Doorway**: 1.3m wide × 2m high rectangular opening in center of dividing wall
- **External walls**: 10cm thick concrete, forming the perimeter
- **Floor**: Concrete floor at z=0 (x-y plane)
- **No ceiling**: Open top allows viewing from above
- **Wall height**: 3m (z: 0-3m)
- **Material**: All walls use `itu_concrete` (ITU material model)

### Room Layout (Top-Down View)

```
         y
         ↑
    40m  ├─────────────────┬─────────────────┐
         │                 │                 │
         │    Room 1       │    Room 2       │
         │   (West)        │    (East)       │
         │                 │                 │
    20m  │                ┌┴┐                │  ← Doorway (1.3m wide)
         │      node1     └┬┘      node2    │     centered at y=20m
         │       @         │         @       │
         │                 │                 │
     0m  └─────────────────┴─────────────────┘
         0m               20m               40m → x

    Legend:
      @ = Node position (z=1m height)
      │ = Concrete wall (10cm thick)
      ┌┴┐ = Doorway opening (2m high)
```

## Node Positions

| Node | Position | Room | Description |
|------|----------|------|-------------|
| node1 | (10, 10, 1) | Room 1 (West) | South side of west room |
| node2 | (30, 10, 1) | Room 2 (East) | South side of east room |

**Key points:**
- Nodes are separated by the dividing wall (20m apart in x-direction)
- Both at z=1m (desktop/table height)
- Direct line-of-sight blocked by concrete wall
- RF propagation primarily through doorway (indirect path)

## RF Configuration

### WiFi 6 with 256-QAM Modulation

Both nodes use high-order modulation that is sensitive to low SNR:

| Parameter | Value | Notes |
|-----------|-------|-------|
| **Frequency** | 5.18 GHz | WiFi 6 channel 36 |
| **Bandwidth** | 80 MHz | Wide channel |
| **Modulation** | 256-QAM | 8 bits/symbol, high spectral efficiency |
| **FEC** | LDPC | Low-density parity-check coding |
| **Code rate** | 0.75 | 3/4 rate |
| **TX Power** | 20 dBm | Typical WiFi 6 transmit power |
| **Antenna gain** | 2 dBi | Antenna pattern selection (NOT added to link budget) |
| **Min SNR** | ~29 dB (uncoded) | ~22.5 dB with LDPC coding gain (6.5 dB) |

**Expected behavior:**
- **Theoretical rate**: 80 MHz × 8 bits × 0.75 × 0.8 = **384 Mbps**
- **Wall attenuation**: Concrete wall adds ~20-30 dB path loss
- **Doorway propagation**: Primary path via reflections through doorway
- **Multipath effects**: Multiple reflections from walls create delay spread
- **SNR degradation**: Through-wall path may drop below 29 dB (uncoded) / 22.5 dB (coded) threshold
- **Packet loss**: Expected if SNR < 22.5 dB (256-QAM with LDPC fails to demodulate)

## Deployment and Testing

### Prerequisites

1. Build the node image:
   ```bash
   docker build -t sine-node:latest docker/node/
   ```

2. Ensure channel server dependencies are installed:
   ```bash
   uv sync
   ```

### Step-by-Step Deployment

#### 1. Start Channel Server (Terminal 1)

```bash
uv run sine channel-server
```

**Expected output:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

#### 2. Deploy Emulation (Terminal 2)

```bash
sudo $(which uv) run sine deploy --enable-mobility examples/two_rooms/network.yaml
```

**What to expect:**
- Containerlab creates two Docker containers
- Sionna loads the two-room scene
- Ray tracing computes propagation paths through doorway
- Netem parameters applied based on computed SNR and packet loss
- Mobility API server starts on port 8001

**Expected output:**
```
Deployed Containers:
  clab-two-rooms-node1 (sine-node:latest)
    PID: 12345
    Interfaces:
      - eth1 @ position (10.0, 10.0, 1.0)

  clab-two-rooms-node2 (sine-node:latest)
    PID: 12346
    Interfaces:
      - eth1 @ position (30.0, 10.0, 1.0)

Link Parameters:
  node1:eth1 ↔ node2:eth1 [wireless]
    Delay: X.XX ms | Jitter: X.XX ms | Loss: X.X% | Rate: XXX.X Mbps
```

#### 3. Configure IP Addresses (Terminal 3)

```bash
# Assign IP addresses to wireless interfaces
docker exec -it clab-two-rooms-node1 ip addr add 18.0.0.1/24 dev eth1
docker exec -it clab-two-rooms-node2 ip addr add 18.0.0.2/24 dev eth1

# Verify connectivity
docker exec clab-two-rooms-node2 ping -c 3 18.0.0.1
```

#### 4. Test Throughput (Terminal 4)

```bash
# Start iperf3 server on node1
docker exec -it clab-two-rooms-node1 iperf3 -s
```

**In another terminal (Terminal 5):**
```bash
# Run iperf3 client on node2
docker exec -it clab-two-rooms-node2 iperf3 -c 18.0.0.1 -t 10
```

**Expected results:**
- Throughput likely **lower than 384 Mbps** theoretical rate
- Packet loss may occur if SNR < 22.5 dB (256-QAM with LDPC coding threshold)
- Higher delay and jitter compared to free-space due to multipath
- Check deployment output for actual netem parameters

### 5. Cleanup

```bash
uv run sine destroy examples/two_rooms/network.yaml
```

## Mobility Experiment

This example demonstrates how node movement affects link quality in an indoor environment.

### Experiment: Moving Along East Wall

Move `node2` along the east wall (x=30m) from south (y=10m) to north (y=30m):

```bash
# Move node2 from (30, 10, 1) to (30, 30, 1) at 1 m/s (takes 20 seconds)
uv run python examples/mobility/linear_movement.py node2 30.0 10.0 1.0 30.0 30.0 1.0 1.0
```

**What this does:**
- Starts at: (30, 10, 1) - south side of Room 2
- Ends at: (30, 30, 1) - north side of Room 2
- Movement: 20m along y-axis at 1 m/s
- Duration: 20 seconds

### Expected Behavior During Movement

As `node2` moves from (30, 10, 1) to (30, 30, 1):

| Position (y) | Distance from doorway | Expected effect |
|--------------|----------------------|----------------|
| **10m** (start) | 10m south | Poor signal (off-axis from doorway) |
| **15m** | 5m south | Improving signal |
| **20m** (doorway) | 0m (aligned) | **Best signal** (direct path through doorway) |
| **25m** | 5m north | Degrading signal |
| **30m** (end) | 10m north | Poor signal (off-axis from doorway) |

**Key observations:**
1. **Best throughput at y=20m** when node2 aligns with doorway center
2. **SNR decreases** as node2 moves away from doorway alignment
3. **Packet loss increases** when off-axis (multipath becomes weaker)
4. **256-QAM may fail** at extreme positions if SNR < 22.5 dB (with LDPC coding)

### Monitoring During Mobility

#### Option 1: Continuous iperf3 (Recommended)

**Setup** (after step 4 above):
```bash
# Terminal 4: iperf3 server already running
# Terminal 5: Continuous throughput tests
while true; do
    docker exec clab-two-rooms-node2 iperf3 -c 18.0.0.1 -t 2
    sleep 1
done
```

**Terminal 6: Run mobility script**
```bash
uv run python examples/mobility/linear_movement.py node2 30.0 10.0 1.0 30.0 30.0 1.0 1.0
```

**What you'll see:**
- Throughput increases as node2 approaches y=20m (doorway)
- Peak throughput when aligned with doorway
- Throughput decreases as node2 moves past y=20m
- Retransmissions increase when off-axis

#### Option 2: Monitor Netem Parameters

```bash
# Watch netem configuration update
watch -n 0.5 'docker exec clab-two-rooms-node1 tc -s qdisc show dev eth1'
```

Look for:
- `rate` - Data rate (should peak at y=20m)
- `loss` - Packet loss percentage (should be lowest at y=20m)

#### Option 3: Query Node Positions

```bash
# Watch position updates
watch -n 0.5 'curl -s http://localhost:8001/api/nodes | jq'
```

#### Option 4: Debug Ray Tracing

Query path details at specific positions:

```bash
# When node2 is at doorway alignment (y=20m)
curl -X POST http://localhost:8000/debug/paths \
  -H "Content-Type: application/json" \
  -d '{
    "tx_position": {"x": 10.0, "y": 10.0, "z": 1.0},
    "rx_position": {"x": 30.0, "y": 20.0, "z": 1.0}
  }' | jq

# When node2 is off-axis (y=30m)
curl -X POST http://localhost:8000/debug/paths \
  -H "Content-Type: application/json" \
  -d '{
    "tx_position": {"x": 10.0, "y": 10.0, "z": 1.0},
    "rx_position": {"x": 30.0, "y": 30.0, "z": 1.0}
  }' | jq
```

Compare:
- `num_paths` - More paths when aligned with doorway
- `strongest_path.power_db` - Higher power when aligned
- `paths[].interaction_types` - Reflections vs direct path

## Alternative Mobility Patterns

### Move Toward Doorway from Far Corner

```bash
# Start at far corner of Room 2, move toward doorway
uv run python examples/mobility/linear_movement.py node2 40.0 0.0 1.0 30.0 20.0 1.0 2.0
```

### Move Through Doorway (Cross Rooms)

**Note:** This requires updating node2's position to cross x=20m.

```bash
# Move from Room 2 to Room 1 through doorway
# Start: (25, 20, 1) - just east of doorway
# End: (15, 20, 1) - just west of doorway
uv run python examples/mobility/linear_movement.py node2 25.0 20.0 1.0 15.0 20.0 1.0 0.5
```

**Expected:** SNR improves dramatically as node2 enters line-of-sight with node1.

### Circular Path Around Room 2

Create a custom script to move node2 in a circle around Room 2:

```python
import asyncio
from examples.mobility.linear_movement import LinearMobility

async def circle_room2():
    mobility = LinearMobility(api_url="http://localhost:8001")

    # Square path around Room 2 (clockwise from south)
    await mobility.move_linear("node2", (30, 10, 1), (30, 30, 1), 1.0)  # North
    await mobility.move_linear("node2", (30, 30, 1), (40, 30, 1), 1.0)  # East
    await mobility.move_linear("node2", (40, 30, 1), (40, 10, 1), 1.0)  # South
    await mobility.move_linear("node2", (40, 10, 1), (30, 10, 1), 1.0)  # West (back)

    await mobility.close()

asyncio.run(circle_room2())
```

## Visualizing the Scene

### Render Static Image

```bash
# Render scene with nodes and paths
uv run sine render examples/two_rooms/network.yaml -o two_rooms.png \
    --camera-position 20,20,15 --look-at 20,20,0 --resolution 1920x1080
```

### Interactive Viewer (Jupyter)

```bash
# Launch Jupyter viewer
uv run --with jupyter jupyter notebook scenes/viewer.ipynb
```

In the notebook:
```python
from sionna.rt import load_scene

# Load the two-room scene
scene = load_scene("scenes/two_rooms.xml", merge_shapes=False)

# Preview from above (no ceiling, so you can see inside)
scene.preview(resolution=[1024, 1024])

# Add nodes as transmitters/receivers to visualize paths
tx = scene.add_tx(name="node1", position=[10, 10, 1])
rx = scene.add_rx(name="node2", position=[30, 10, 1])

# Compute and visualize paths
paths = scene.compute_paths()
scene.render(paths=paths, show_devices=True)
```

## Troubleshooting

### High Packet Loss / Low Throughput

**Problem**: iperf3 shows very low throughput or high packet loss.

**Possible causes:**
1. **SNR below 256-QAM threshold**: Through-wall path loss is too high
2. **Multipath interference**: Destructive interference at certain positions

**Solutions:**
- Check deployment output for actual SNR and packet loss
- Try lower-order modulation (64-QAM or 16-QAM) in `network.yaml`
- Increase TX power (`rf_power_dbm`)
- Move nodes closer to doorway alignment

### No Connectivity

**Problem**: `ping` fails or iperf3 cannot connect.

**Cause**: Likely no propagation path found (blocked by walls).

**Solution:**
1. Verify scene loaded correctly:
   ```bash
   curl -X POST http://localhost:8000/debug/paths \
     -H "Content-Type: application/json" \
     -d '{
       "tx_position": {"x": 10.0, "y": 10.0, "z": 1.0},
       "rx_position": {"x": 30.0, "y": 10.0, "z": 1.0}
     }'
   ```
2. Check `num_paths` > 0
3. If no paths, verify doorway geometry in `scenes/two_rooms.xml`

### Mobility Not Working

**Problem**: Position updates don't change throughput.

**Cause**: Deployment not started with `--enable-mobility` flag.

**Solution:**
```bash
# Destroy current deployment
uv run sine destroy examples/two_rooms/network.yaml

# Redeploy with mobility API
sudo $(which uv) run sine deploy --enable-mobility examples/two_rooms/network.yaml
```

## Advanced Experiments

### Compare Modulation Schemes

Test how different modulation schemes handle indoor propagation:

1. **256-QAM** (current): High rate, fragile to low SNR
2. **64-QAM**: Lower rate, more robust
3. **16-QAM**: Even lower rate, very robust

Edit `network.yaml` and change:
```yaml
modulation: 64qam      # Instead of 256qam
fec_code_rate: 0.5     # Instead of 0.75
```

### Add Third Node in Doorway

Add a relay node in the doorway to bridge the two rooms:

```yaml
node3:
  kind: linux
  image: sine-node:latest
  interfaces:
    eth1:
      wireless:
        # ... same RF config ...
        position:
          x: 20.0     # In doorway
          y: 20.0     # Center
          z: 1.0
```

This creates a 3-node MANET topology.

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

## References

- [Main README.md](../../README.md) - SiNE overview
- [CLAUDE.md](../../CLAUDE.md) - Developer documentation
- [Mobility Examples](../mobility/README.md) - Detailed mobility guide
- [Sionna Documentation](https://nvlabs.github.io/sionna/) - Ray tracing details
- Scene file: [scenes/two_rooms.xml](../../scenes/two_rooms.xml)
