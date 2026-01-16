# MANET Triangle - Shared Bridge Example

This example demonstrates SiNE's **shared broadcast domain** mode for MANET emulation.

## Overview

Unlike traditional point-to-point links, this topology uses a **single Linux bridge** connecting all nodes, creating a true broadcast medium with per-destination netem filtering. 


## A Word on Implementation

SiNE uses the capability of Containerlab to create a Linux bridge in a container ([see Containerlab docs - "Bridges in container namespace"](https://containerlab.dev/manual/kinds/bridge/#bridges-in-container-namespace)). An alternative architecture for a shared bridge would have been the pre-creation of a Linux bridge in the host's namespace, but it was decided this created a more difficult user workflow. It is desirable to have all the SiNE emulation conponents explicitly represented in the network YAML file i.e. [network.yaml](./network.yaml).

## Architecture

```
         Linux Bridge (manet-br0)
              ├── node1:eth1 (192.168.100.1)
              ├── node2:eth1 (192.168.100.2)
              └── node3:eth1 (192.168.100.3)
```

Each node has:
- **Single interface** (eth1) attached to the bridge
- **User-specified IP address** for tc flower filter matching
- **Per-destination netem rules** applied via HTB + flower filters

## Key Features

- **True broadcast medium**: All nodes share the same network segment
- **Per-destination channel conditions**: Ray-traced conditions applied per destination IP
- **Single interface per node**: More realistic MANET architecture
- **MANET routing protocol support**: Broadcast/multicast traffic uses default class

## Configuration

The topology uses:
- **3 nodes** in a triangle formation (equilateral, ~10m sides)
- **5.18 GHz** frequency (WiFi 5 GHz band)
- **64-QAM** modulation with LDPC FEC (rate 1/2)
- **80 MHz** bandwidth
- **Vacuum scene** (free-space propagation)

## Usage

```bash
# Start channel server
uv run sine channel-server

# Deploy (in another terminal, requires sudo for netem)
sudo $(which uv) run sine deploy examples/manet_triangle_shared/network.yaml

# Test connectivity
./test_ping_rtt.sh

# Cleanup
sudo $(which uv) run sine destroy examples/manet_triangle_shared/network.yaml
```

Deployment summary:
```
================================================================================
MANET DEPLOYMENT SUMMARY (Shared Broadcast Domain)
================================================================================

Bridge: manet-br0
Nodes: node1, node2, node3
Interface: eth1

node1 (192.168.100.1):
  → node2 (192.168.100.2): delay=0.07ms, jitter=0.00ms, loss=0.00%, rate=532.5Mbps
  → node3 (192.168.100.3): delay=0.10ms, jitter=0.00ms, loss=0.00%, rate=532.5Mbps

node2 (192.168.100.2):
  → node1 (192.168.100.1): delay=0.07ms, jitter=0.00ms, loss=0.00%, rate=532.5Mbps
  → node3 (192.168.100.3): delay=0.10ms, jitter=0.00ms, loss=0.00%, rate=532.5Mbps

node3 (192.168.100.3):
  → node1 (192.168.100.1): delay=0.10ms, jitter=0.00ms, loss=0.00%, rate=532.5Mbps
  → node2 (192.168.100.2): delay=0.10ms, jitter=0.00ms, loss=0.00%, rate=532.5Mbps
================================================================================
```

## Containers Created

Note that this example spins up 4 containers in total: 3 for the wireless nodes and 1 for for the Linux bridge. Example `docker ps` output:

~~~
$ docker ps
CONTAINER ID   IMAGE           COMMAND     CREATED         STATUS         PORTS     NAMES
ef17147914d9   alpine:latest   "/bin/sh"   9 seconds ago   Up 9 seconds             clab-manet-triangle-shared-node3
840027edada3   alpine:latest   "/bin/sh"   9 seconds ago   Up 9 seconds             clab-manet-triangle-shared-node2
275864d888ca   alpine:latest   "/bin/sh"   9 seconds ago   Up 9 seconds             clab-manet-triangle-shared-bridge-host
c6ec82e03169   alpine:latest   "/bin/sh"   9 seconds ago   Up 9 seconds             clab-manet-triangle-shared-node1
~~~

## Comparison with Point-to-Point

| Aspect | Point-to-Point (current) | Shared Bridge (this example) |
|--------|--------------------------|------------------------------|
| **Interfaces per node** | N-1 (for N nodes) | 1 |
| **Broadcast medium** | No | Yes |
| **Hidden node problem** | Cannot model | Can model |
| **TC complexity** | Simple (one netem per interface) | Complex (HTB + per-dest filters) |
| **Scalability** | Good (< 10 nodes) | Excellent (30+ nodes with flower) |

## YAML Structure

```yaml
topology:
  shared_bridge:
    enabled: true           # Opt-in to shared bridge mode
    name: manet-br0        # Bridge name
    nodes: [node1, ...]    # Nodes in broadcast domain
    interface_name: eth1   # Interface to attach

  nodes:
    node1:
      interfaces:
        eth1:
          ip_address: 192.168.100.1  # Required for tc filters
          wireless:
            position: {x: 0, y: 0, z: 1}
            # ... other wireless params
```

## Implementation Status

- ✅ **Phase 1-6**: Complete and working!
  - ✅ Schema validation
  - ✅ Containerlab bridge integration
  - ✅ Per-destination netem (HTB + tc flower filters)
  - ✅ Channel computation (all-to-all ray tracing)
  - ✅ Routing configuration (bridge subnet routes)
  - ✅ Testing suite (`test_*.sh` scripts)

## Testing

This example includes comprehensive test scripts:

```bash
# Run all tests
sudo ./run_all_tests.sh

# Individual tests:
sudo ./test_ping_rtt.sh          # Verify ping RTT matches netem config
sudo ./test_tc_config.sh         # Verify tc qdisc/class/filter setup
sudo ./test_filter_stats.sh      # Check packet counters on filters
```

See [TESTING.md](TESTING.md) for detailed test documentation.
