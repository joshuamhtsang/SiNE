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
    client 30.0 5.0 1.0 30.0 38.0 1.0 1.0

# If you see lag warnings, increase the update interval (e.g. 500ms)
uv run python examples/for_user/05_moving_node/linear_movement.py \
    client 30.0 5.0 1.0 30.0 38.0 1.0 1.0 500
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
| y=38 (past doorway) | NLOS again — signal bounces back through doorway | ~100-200 Mbps |

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

Watch propagation paths update in real-time as the client moves through the doorway. You'll need to open a 6th terminal and do:

### Terminal 6 — Live viewer

```bash
# Recommended: copy the notebook before running
cp scenes/viewer_live.ipynb scenes/viewer_live_copy.ipynb

uv run --with jupyter jupyter notebook scenes/viewer_live_copy.ipynb
```

Open the notebook in your browser, in fact it should automatically open the following URL:
(http://localhost:8888/notebooks/viewer_live_copy.ipynb)[http://localhost:8888/notebooks/viewer_live_copy.ipynb]


Set `RUN_MODE` in **Cell 1** to control what the notebook does, then go `Run` → `Run All Cells`:

| `RUN_MODE` | What runs |
|------------|-----------|
| `"signal"` | Channel gain monitor only (Cell 10) |
| `"movie"` | Animated 3D scene only (Cell 8) |
| `"both"` | Both |

> **Re-running the mobility script?** Use `Kernel` → `Restart Kernel and Run All Cells` instead of just `Run All Cells`. This clears accumulated state (timestamps, path buffers) so the plot starts fresh.

### Cell 5 — One-time 3D snapshot

Fetches the current scene state from the channel server and renders it once: node positions, propagation paths, and a text summary of channel metrics (SNR, delay spread, K-factor). Run this at any point during the emulation to see which paths are active. Propagation type is colour-coded by Sionna.

![image](./images/user-example-05_paths-viz.png)

### Cell 8 — Animated 3D movie (`RUN_MODE = "movie"`)

Polls the channel server repeatedly and renders the 3D scene at each time step, then stitches the frames into a playable animation. Start the movement script first, then run the notebook — Cell 8 captures the node moving through the scene in real time.

### Cell 10 — Channel gain vs time (`RUN_MODE = "signal"`)

Polls the channel server at 0.5 s intervals for `t_monitor` seconds (default: 35 s to match the movement script duration) and records the total channel gain at each sample. Produces a static two-panel plot: channel gain in dB with dominant propagation mode transitions annotated, and active path count below. Start the movement script first, then run the notebook.

The moment the client aligns with the doorway is clearly visible as a sharp upward spike in channel gain (~15–20 dB), corresponding to the `refraction + refraction` → `LOS` transition.

![image](./images/user-example05_signalplot.png)

### Understanding propagation mode labels

The live viewer and signal plot annotate each sample with a **dominant path mode** — the propagation mechanism of the strongest ray at that moment. A few labels that may look surprising:

| Label | Meaning |
|-------|---------|
| `LOS` | Direct line-of-sight — no interactions |
| `refraction` | Ray passed through one surface boundary (entry or exit of a wall) |
| `refraction + refraction` | Ray traversed **one wall** — one refraction entering the material, one exiting |
| `refraction + refraction + refraction + refraction` | Ray traversed **two walls** |
| `specular reflection` | Ray bounced off a surface |
| `refraction + specular reflection` | Ray went through one wall face then reflected |

Sionna models each wall as a dielectric slab with two surfaces. A single wall crossing therefore produces **two** refraction events (air→concrete at entry, concrete→air at exit). So `refraction + refraction` almost always means the signal went through the dividing wall — not two separate walls.

### Understanding the channel gain axis

The y-axis shows **channel gain in dB** — the incoherent sum of Sionna's per-path power coefficients:

```
channel_gain_dB = 10 · log10( Σ |aᵢ|² )
```

where `aᵢ` are the complex amplitudes returned by Sionna's `PathSolver` for each propagation path. This is a **dimensionless ratio** (not dBm): a value of −72 dB means the received signal power is 10⁻⁷·² times the transmitted power. To convert to absolute received power:

```
received_power_dBm = channel_gain_dB + tx_power_dBm
                   = channel_gain_dB + 20.0   (for this example)
```

The channel gain is what drives adaptive MCS selection — a 15–20 dB jump at the doorway (NLOS → LOS) pushes the link from 64-QAM (MCS 5–7, ~200–320 Mbps) to 1024-QAM (MCS 10–11, ~480–533 Mbps).

**Why the gain is negative:** free-space path loss at 20 m and 5.18 GHz is already ~72 dB, so the channel always attenuates the signal. The NLOS wall-penetration case adds a further ~15–20 dB of concrete attenuation on top of that.

## Destroy

```bash
UV_PATH=$(which uv) sudo -E $(which uv) run sine destroy examples/for_user/05_moving_node/network.yaml
```

## Next

Ready to build your own? Head to the [Creating Your Own Network](../../README.md#creating-your-own-network) section in the main README.
