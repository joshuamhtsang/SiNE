# Example 5: Moving Node

Watch iperf3 throughput change in real-time as a node walks through a doorway. Sionna ray tracing recomputes the channel after each position update via the Controller API.

## Setup

You'll need five terminals open for this one. Run all commands from the **SiNE root directory**.

### Terminal 1 — Channel server

```bash
uv run sine channel-server
```

### Terminal 2 — Deploy with control API

```bash
UV_PATH=$(which uv) sudo -E $(which uv) run sine deploy --enable-control examples/for_user/05_moving_node/network.yaml
```

The `--enable-control` flag starts the Controller API on port 8002.

### Terminal 3 — iperf3 server (AP node)

```bash
docker exec -it clab-moving-node-05-ap sh
```

```sh
iperf3 -s
```

### Terminal 4 — iperf3 client (watch throughput change as node moves)

```bash
docker exec -it clab-moving-node-05-client sh
```

```sh
iperf3 -c 10.0.1.1 -t 120 -i 1
```

### Terminal 5 — Run movement script

```bash
# Walk client northward past the doorway (1 m/s)
uv run python examples/for_user/05_moving_node/linear_movement.py \
    client 30.0 5.0 1.0 30.0 35.0 1.0 1.0
```

## Scene Layout

```
y=40 ─────────────────────────────────────────
     │           Room 1       │    Room 2      │
     │    ap (10, 20, 2.5)   (doorway y=20)   │
y=20 │    [ceiling mount]     │                │
     │                        │  client moves  │
     │                        │  south → north │
y=5  │                        │  client start  │
y=0  ─────────────────────────────────────────
     x=0         x=10     x=20   x=30      x=40
                              wall at x=20
```

The AP is ceiling-mounted in Room 1, directly aligned with the doorway (y=20). The client starts south of the doorway in Room 2 and walks north.

## Expected Throughput at Key Positions

| Client position | Geometry | Expected throughput |
|-----------------|----------|---------------------|
| y=5 (start) | NLOS — signal bounces via doorway at oblique angle | ~50-100 Mbps |
| y=20 (doorway) | Near-LOS — client aligned with doorway | ~300+ Mbps |
| y=35 (past doorway) | NLOS again — signal bounces back through doorway | ~100-200 Mbps |

## Controller API

The Controller API (port 8002) is what the movement scripts use. You can also call it directly:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/control/update` | Update node position and recompute channels |
| `GET` | `/api/control/position/{node}` | Get current node position |
| `POST` | `/api/control/recompute` | Force recompute of all channels |
| `POST` | `/api/control/interface` | Enable/disable a wireless interface |

```bash
# Move client manually
curl -X POST http://localhost:8002/api/control/update \
     -H "Content-Type: application/json" \
     -d '{"node": "client", "x": 30.0, "y": 20.0, "z": 1.0}'

# Check position
curl http://localhost:8002/api/control/position/client
```

## Scripted Movement Options

### Linear movement (command-line)

```bash
uv run python examples/for_user/05_moving_node/linear_movement.py \
    <node> <start_x> <start_y> <start_z> <end_x> <end_y> <end_z> <velocity_m_s>
```

### Waypoint movement (edit script)

Edit `waypoint_movement.py` to define your own path, then run:

```bash
uv run python examples/for_user/05_moving_node/waypoint_movement.py
```

## Live Visualization (Optional)

Watch propagation paths update in real-time as the client moves through the doorway.

### Terminal 6 — Live viewer

```bash
# Recommended: copy the notebook before running
cp scenes/viewer_live.ipynb scenes/viewer_live_copy.ipynb

uv run --with jupyter jupyter notebook scenes/viewer_live_copy.ipynb
```

Open the notebook in your browser (not VS Code's Jupyter extension). In the notebook:

- **Cell 5** — Single snapshot with 3D scene and propagation paths
- **Cell 7** — Continuous auto-refresh (uncomment to enable, 1-second updates)

Run Cell 7 while the movement script is running to see channel metrics (SNR, delay spread, K-factor) and propagation paths update live.

![](./images/user-example-05_paths-viz.png)

## Destroy

```bash
UV_PATH=$(which uv) sudo -E $(which uv) run sine destroy examples/for_user/05_moving_node/network.yaml
```

## Next

Ready to build your own? Head to the [Creating Your Own Network](../../README.md#creating-your-own-network) section in the main README.
