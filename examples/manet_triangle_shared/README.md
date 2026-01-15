# MANET Triangle - Shared Bridge Example

This example demonstrates SiNE's **shared broadcast domain** mode for MANET emulation.

## Overview

Unlike traditional point-to-point links, this topology uses a **single Linux bridge** connecting all nodes, creating a true broadcast medium with per-destination netem filtering.

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

**Note**: This example requires Phase 2-4 implementation (not yet complete). The schema validation (Phase 1) is functional.

Once implemented, deployment will be:

```bash
# Start channel server
uv run sine channel-server

# Deploy (in another terminal)
sudo $(which uv) run sine deploy examples/manet_triangle_shared/network.yaml
```

Expected deployment summary:
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

- ✅ **Phase 1**: Schema validation (complete)
- ⏳ **Phase 2**: Containerlab integration (pending)
- ⏳ **Phase 3**: Per-destination netem (pending)
- ⏳ **Phase 4**: Channel computation (pending)
- ⏳ **Phase 5**: Testing (pending)

See [PLAN.md](../../PLAN.md#true-broadcast-medium-shared-bridge-model-implementation-plan) for full implementation plan.
