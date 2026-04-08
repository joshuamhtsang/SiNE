# Example 3: Adaptive WiFi Link

A point-to-point WiFi 6 link with automatic rate adaptation. At 20m, Sionna computes ~36 dB SNR and the radio selects 1024-QAM. Move the node farther away and watch MCS degrade gracefully — no manual reconfiguration needed.

## Topology

```
node1 (AP)           node2 (client)
(5, 10, 2.5)  ←20m→  (25, 10, 1.0)
ceiling mount         desk height
```

## MCS Selection Table

| Distance | SNR | Selected MCS | Modulation | Rate |
|----------|-----|-------------|------------|------|
| 20m | ~36 dB | 10 | 1024-QAM 3/4 | ~480 Mbps |
| 50m | ~28 dB | 8 | 256-QAM 3/4 | ~320 Mbps |
| 100m | ~22 dB | 6 | 64-QAM 3/4 | ~192 Mbps |
| 200m | ~16 dB | 4 | 16-QAM 3/4 | ~96 Mbps |
| 400m | ~10 dB | 2 | QPSK 3/4 | ~48 Mbps |

MCS thresholds (from `examples/common_data/wifi6_mcs.csv`):

| MCS | Modulation | Code Rate | Min SNR |
|-----|-----------|-----------|---------|
| 11 | 1024-QAM | 5/6 | 38 dB |
| 10 | 1024-QAM | 3/4 | 35 dB |
| 9 | 256-QAM | 5/6 | 32 dB |
| 8 | 256-QAM | 3/4 | 29 dB |
| 7 | 64-QAM | 5/6 | 26 dB |
| 6 | 64-QAM | 3/4 | 23 dB |
| 5 | 64-QAM | 2/3 | 20 dB |
| 4 | 16-QAM | 3/4 | 17 dB |
| 3 | 16-QAM | 1/2 | 14 dB |
| 2 | QPSK | 3/4 | 11 dB |
| 1 | QPSK | 1/2 | 8 dB |
| 0 | BPSK | 1/2 | 5 dB |

## Prerequisites

Run all commands from the **SiNE root directory** — you'll need two terminals open.

**Terminal 1** — Start the channel server:
```bash
uv run sine channel-server
```

## Deploy

**Terminal 2** — Deploy the emulation:
```bash
UV_PATH=$(which uv) sudo -E $(which uv) run sine deploy examples/for_user/03_adaptive_wifi_link/network.yaml
```

### Expected deployment summary (at 20m)

```
Link Parameters:
  node1:eth1 ↔ node2:eth1 [wireless]
    MCS: 10 (1024qam, rate-0.75, ldpc)
    Delay: 0.07 ms | Jitter: 0.00 ms | Loss: 0.00% | Rate: ~480 Mbps
```

## Test

```bash
# Check connectivity
docker exec clab-adaptive-wifi-link-03-node1 ping -c 5 192.168.1.2

# Measure throughput
docker exec -d clab-adaptive-wifi-link-03-node2 iperf3 -s
docker exec clab-adaptive-wifi-link-03-node1 iperf3 -c 192.168.1.2 -t 5
```

## Try Varying the Distance

Edit `network.yaml` and change node2's `x` position (line with `x: 25`):

```yaml
position:
  x: 105    # Change from 25 to 105 for ~22 dB SNR → MCS 6
  y: 10
  z: 1.0
```

Then redeploy and observe MCS selection in the deployment summary.

## Destroy

```bash
UV_PATH=$(which uv) sudo -E $(which uv) run sine destroy examples/for_user/03_adaptive_wifi_link/network.yaml
```

## Next

**[Example 4: Through the Wall](../04_through_the_wall/)** — add a concrete wall between the nodes and watch Sionna find the doorway path. SNR drops ~15-20 dB and MCS adapts automatically.
