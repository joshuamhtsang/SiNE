# Example 2: Co-Channel Interference

Same three nodes as [Example 1](../01_wireless_mesh/), same positions, same hardware — but now SiNE models co-channel interference. The node1↔node2 link drops from ~480 Mbps to ~50 Mbps. The outer links go completely silent.

The only difference from Example 1: `enable_sinr: true`.

## What Changes

| Link | Without Interference (Ex. 1) | With Interference (Ex. 2) |
|------|------------------------------|--------------------------|
| node1 ↔ node2 (30m) | ~480 Mbps | ~50 Mbps |
| node1 ↔ node3 (91m) | ~320 Mbps | **0 Mbps (dead)** |
| node2 ↔ node3 (91m) | ~320 Mbps | **0 Mbps (dead)** |

## Why the Outer Links Die

On the node1↔node3 link, node3's desired signal travels 91.2m from node1. But node2 is only 91.2m from node3 too, transmitting at the same power on the same frequency. The desired signal and the interference arrive at nearly equal power — and the SINR drops to ~-3 dB.

At negative SINR, the receiver cannot distinguish the desired signal from noise. Result: 100% packet loss. No manual configuration required; geometry determines who interferes with whom.

## Interference Model

This example uses `enable_sinr: true` with no MAC protocol (no CSMA or TDMA). SiNE treats this as the **worst-case scenario**: every node is assumed to be transmitting at all times (`tx_probability = 1.0`). This is the most conservative interference model — real networks with carrier sensing or time-division scheduling would see lower interference.

## Topology

```
node1 (0, 0, 1) ------- 30m ------- node2 (30, 0, 1)
        \                                  /
       91.2m                           91.2m
             \  [interference crushes]  /
               node3 (15, 90, 1)
```

## Prerequisites

Run all commands from the **SiNE root directory** — you'll need four terminals open.

**Terminal 1** — Start the channel server:
```bash
uv run sine channel-server
```

## Deploy

**Terminal 2** — Deploy the emulation:
```bash
UV_PATH=$(which uv) sudo -E $(which uv) run sine deploy examples/for_user/02_co_channel_interference/network.yaml
```

### Expected deployment summary

```
Link Parameters:
  node1:eth1 → node2:eth1 [wireless, SINR]
    SINR: ~9-10 dB | MCS: 1 (qpsk, rate-0.5)
    Delay: 0.10 ms | Loss: ~5% | Rate: ~50 Mbps

  node1:eth1 → node3:eth1 [wireless, SINR]
    SINR: ~-3 dB | MCS: 0 (bpsk, rate-0.5)
    Delay: 0.30 ms | Loss: 100% | Rate: 0 Mbps

  node2:eth1 → node3:eth1 [wireless, SINR]
    SINR: ~-3 dB | MCS: 0 (bpsk, rate-0.5)
    Delay: 0.30 ms | Loss: 100% | Rate: 0 Mbps
```

## Test

**Terminal 3** — node2 (ping test + iperf3 server):
```bash
docker exec -it clab-co-channel-interference-02-node2 sh
```

```sh
# node2 → node3: should time out (100% loss)
ping -c 5 192.168.100.3

# Start iperf3 server for throughput test
iperf3 -s
```

**Terminal 4** — node1 (ping tests + iperf3 client):
```bash
docker exec -it clab-co-channel-interference-02-node1 sh
```

```sh
# node1 → node2: should succeed
ping -c 5 192.168.100.2

# node1 → node3: should time out (100% loss)
ping -c 5 192.168.100.3

# Throughput on the surviving link (~50 Mbps)
iperf3 -c 192.168.100.2 -t 5
```

## Destroy

```bash
UV_PATH=$(which uv) sudo -E $(which uv) run sine destroy examples/for_user/02_co_channel_interference/network.yaml
```

## Next

**[Example 3: Adaptive WiFi Link](../03_adaptive_wifi_link/)** — a point-to-point WiFi 6 link demonstrating automatic MCS selection from 1024-QAM down to BPSK as distance increases.
