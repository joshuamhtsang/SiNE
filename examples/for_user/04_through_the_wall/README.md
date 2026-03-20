# Example 4: Through the Wall

Sionna's ray tracer finds the doorway path between two concrete rooms. Wall attenuation drops SNR by ~15-20 dB compared to free space — the radio automatically selects a more robust modulation.

## Room Layout

```
y=40 ─────────────────────────────────────────
     │           Room 1       │    Room 2      │
y=20 │                       (doorway 1.3m wide)
     │    node1 (10,10,1)    │  node2 (30,10,1)│
y=0  ─────────────────────────────────────────
     x=0         x=10     x=20    x=30      x=40
                              wall at x=20
```

Both nodes sit south of the doorway (y=10). Signal must travel through the concrete wall or find the long path up through the doorway. Sionna RT computes the actual multipath propagation.

## Impact of Indoor Propagation

| Scenario | Path | SNR | MCS | Rate |
|----------|------|-----|-----|------|
| Free space (Example 3, 20m) | Direct LOS | ~36 dB | 10 | ~480 Mbps |
| Two rooms (this example) | Via doorway / wall | ~18-22 dB | 4-7 | ~100-300 Mbps |

The link remains usable — NLOS degrades quality but doesn't kill it. The radio adapts automatically.

## Prerequisites

```bash
uv run sine channel-server
```

## Deploy

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

The exact MCS depends on Sionna's ray tracing result for the two-rooms scene.

## Test

```bash
# Check connectivity
docker exec clab-through-the-wall-04-node1 ping -c 5 10.0.0.2

# Measure throughput
docker exec -d clab-through-the-wall-04-node2 iperf3 -s
docker exec clab-through-the-wall-04-node1 iperf3 -c 10.0.0.2 -t 5
```

## Render the Scene

Visualize the room geometry and propagation paths:

```bash
uv run sine render examples/for_user/04_through_the_wall/network.yaml -o scene.png --clip-at 3.0
```

## Destroy

```bash
UV_PATH=$(which uv) sudo -E $(which uv) run sine destroy examples/for_user/04_through_the_wall/network.yaml
```

## Next

**[Example 5: Moving Node](../05_moving_node/)** — add node mobility to this same scene. Watch iperf3 throughput climb in real-time as the client walks through the doorway.
