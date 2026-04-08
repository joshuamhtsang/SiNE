# Example 1: Wireless Mesh

Three WiFi nodes in open space. Sionna computes path loss for each pair based on geometry — nodes 30m apart get ~480 Mbps, nodes 91m apart get ~320 Mbps, automatically.

This is the simplest SiNE example: no interference, no walls, no mobility. Just three nodes and the physics of free-space propagation.

## Topology

```
node1 (0, 0, 1) ------- 30m ------- node2 (30, 0, 1)
        \                                  /
       91.2m                           91.2m
             \                        /
               node3 (15, 90, 1)
```

| Link | Distance | Expected SNR | MCS | Rate |
|------|----------|-------------|-----|------|
| node1 ↔ node2 | 30m | ~36 dB | 10 (1024-QAM 3/4) | ~480 Mbps |
| node1 ↔ node3 | 91.2m | ~26 dB | 7 (64-QAM 5/6) | ~320 Mbps |
| node2 ↔ node3 | 91.2m | ~26 dB | 7 (64-QAM 5/6) | ~320 Mbps |

The rate difference is entirely geometry-driven. No manual rate configuration.

## Prerequisites

Run all commands from the **SiNE root directory** — you'll need two terminals open.

**Terminal 1** — Start the channel server:
```bash
uv run sine channel-server
```

## Deploy

**Terminal 2** — Deploy the emulation:
```bash
UV_PATH=$(which uv) sudo -E $(which uv) run sine deploy examples/for_user/01_wireless_mesh/network.yaml
```

### Expected deployment summary

```
Deployed Containers:
  clab-wireless-mesh-01-node1  alpine:latest  eth1  (0.0, 0.0, 1.0)
  clab-wireless-mesh-01-node2  alpine:latest  eth1  (30.0, 0.0, 1.0)
  clab-wireless-mesh-01-node3  alpine:latest  eth1  (15.0, 90.0, 1.0)

Link Parameters:
  node1:eth1 → node2:eth1 [wireless]
    MCS: 10 (1024qam, rate-0.75, ldpc)
    Delay: 0.10 ms | Jitter: 0.00 ms | Loss: 0.00% | Rate: ~480 Mbps

  node1:eth1 → node3:eth1 [wireless]
    MCS: 7 (64qam, rate-0.833, ldpc)
    Delay: 0.30 ms | Jitter: 0.00 ms | Loss: 0.00% | Rate: ~320 Mbps

  node2:eth1 → node3:eth1 [wireless]
    MCS: 7 (64qam, rate-0.833, ldpc)
    Delay: 0.30 ms | Jitter: 0.00 ms | Loss: 0.00% | Rate: ~320 Mbps
```

## Test

Run iperf3 between each node pair to observe the geometry-driven rate difference:

```bash
# Start iperf3 server on node2
docker exec -d clab-wireless-mesh-01-node2 iperf3 -s

# node1 → node2 (30m link): expect ~480 Mbps
docker exec clab-wireless-mesh-01-node1 iperf3 -c 192.168.100.2 -t 5

# node1 → node3 (91.2m link): expect ~320 Mbps
docker exec -d clab-wireless-mesh-01-node3 iperf3 -s
docker exec clab-wireless-mesh-01-node1 iperf3 -c 192.168.100.3 -t 5

# node2 → node3 (91.2m link): expect ~320 Mbps
docker exec clab-wireless-mesh-01-node2 iperf3 -c 192.168.100.3 -t 5
```

## Destroy

```bash
UV_PATH=$(which uv) sudo -E $(which uv) run sine destroy examples/for_user/01_wireless_mesh/network.yaml
```

## Next

**[Example 2: Co-Channel Interference](../02_co_channel_interference/)** — same three nodes, same positions, same hardware. Add `enable_sinr: true` and watch the outer links go completely silent.
