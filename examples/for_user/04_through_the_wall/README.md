# Example 4: Through the Wall

**Same geometry as [Example 3](../03_adaptive_wifi_link/)** — same AP position (ceiling mount), same client position (desk height), same 20m link — but now placed inside a two-room concrete environment. Sionna's ray tracer finds the doorway path; wall attenuation drops SNR by ~15-20 dB and MCS adapts automatically.

## Room Layout

```
y=40 ──────────────────────────────────────────
     │            Room 1      │    Room 2       │
y=20 │                        (doorway 1.3m wide)
     │   node1 (5,10,2.5)    │  node2 (25,10,1) │
y=0  ──────────────────────────────────────────
     x=0   x=5         x=20 x=25          x=40
                   wall at x=20
```

Both nodes sit south of the doorway (y=10). Signal must travel through the concrete wall or find the longer path up through the doorway opening. Sionna RT computes the actual multipath propagation.

## Impact of Adding a Concrete Wall (same geometry as Example 3)

| Scenario | Scene | Path | SNR | MCS | Rate |
|----------|-------|------|-----|-----|------|
| Example 3 | Free space | Direct LOS | ~36 dB | 10 | ~480 Mbps |
| Example 4 (this) | Two rooms | Via doorway / wall | ~18-22 dB | 4-7 | ~100-300 Mbps |

The only change is the scene file. The link remains usable — NLOS degrades quality but doesn't kill it. The radio adapts automatically.

## Prerequisites

Run all commands from the **SiNE root directory** — you'll need two terminals open.

**Terminal 1** — Start the channel server:
```bash
uv run sine channel-server
```

## Deploy

**Terminal 2** — Deploy the emulation:
```bash
UV_PATH=$(which uv) sudo -E $(which uv) run sine deploy examples/for_user/04_through_the_wall/network.yaml
```

### Expected deployment summary

```
Link Parameters:
  node1:eth1 ↔ node2:eth1 [wireless]
    MCS: 5-7 (64qam, rate-0.667 to 0.833, ldpc)
    Delay: 0.10-0.15 ms | Jitter: 0.00 ms | Loss: 0-2% | Rate: ~150-250 Mbps
```

The exact MCS will vary depending on what Sionna's ray tracer finds through the two-rooms scene — expect somewhere in the 64-QAM range.

## Test

```bash
# Check connectivity
docker exec clab-through-the-wall-04-node1 ping -c 5 10.0.0.2

# Measure throughput
docker exec -d clab-through-the-wall-04-node2 iperf3 -s
docker exec clab-through-the-wall-04-node1 iperf3 -c 10.0.0.2 -t 5
```

## Render the Scene

Curious about the geometry? Render the scene to see the room layout and propagation paths:

```bash
uv run sine render examples/for_user/04_through_the_wall/network.yaml -o scene.png --clip-at 3.0
```

## Destroy

```bash
UV_PATH=$(which uv) sudo -E $(which uv) run sine destroy examples/for_user/04_through_the_wall/network.yaml
```

## Next

**[Example 5: Moving Node](../05_moving_node/)** — add node mobility to this same scene. Watch iperf3 throughput climb in real-time as the client walks through the doorway.
