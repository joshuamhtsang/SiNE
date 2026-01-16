# Fixed Link - Direct Netem Parameters Example

## Overview

This example demonstrates **fixed netem links** where network parameters (delay, jitter, loss, rate) are specified directly instead of being computed from wireless channel conditions. This is useful for simulating wired links or when you need precise, reproducible link characteristics.

## Scenario Details

- **Link Type**: Fixed netem (non-wireless)
- **Delay**: 10ms one-way (20ms RTT)
- **Jitter**: 1ms
- **Loss**: 0.1% packet loss
- **Rate**: 100 Mbps bandwidth limit
- **Correlation**: 25% (loss correlation)

## Key Features

**No channel server needed!** Fixed links don't require ray tracing or wireless channel computation.

**No scene file needed!** Since there's no RF propagation to model, you can skip scene configuration.

**Direct control**: Specify exactly the link characteristics you need for testing.

## Deployment

```bash
# Deploy (no channel server needed, but requires sudo for netem)
sudo $(which uv) run sine deploy examples/fixed_link/network.yaml

# Configure IP addresses
docker exec -it clab-fixed-link-node1 ip addr add 192.168.1.1/24 dev eth1
docker exec -it clab-fixed-link-node2 ip addr add 192.168.1.2/24 dev eth1

# Test delay/jitter with ping (expect ~20ms RTT with variation)
docker exec -it clab-fixed-link-node1 ping -c 10 192.168.1.2

# Test bandwidth with iperf3 (expect ~100 Mbps)
# Terminal 1 (server):
docker exec -it clab-fixed-link-node1 iperf3 -s

# Terminal 2 (client):
docker exec -it clab-fixed-link-node2 iperf3 -c 192.168.1.1

# Cleanup
sudo $(which uv) run sine destroy examples/fixed_link/network.yaml
```

## Use Cases

### 1. **Wired Link Simulation**
Emulate Ethernet, fiber, or other wired connections with specific latency and loss characteristics.

### 2. **Reproducible Testing**
Create deterministic test environments where link conditions don't change based on position or scene geometry.

### 3. **Quick Prototyping**
Test application behavior without setting up Sionna scenes or running the channel server.

### 4. **WAN/Internet Emulation**
Simulate long-distance connections with appropriate delay and loss profiles:
- Local network: 1-5ms delay
- Regional: 10-30ms delay
- Cross-country: 50-100ms delay
- Intercontinental: 100-300ms delay

### 5. **Mixed Topologies**
Combine fixed links (wired backhaul) with wireless links (last mile) in hybrid network scenarios.

## Configuration Options

All fixed_netem parameters are optional. Omit any parameter to skip that aspect of emulation:

```yaml
fixed_netem:
  delay_ms: 10.0              # One-way delay (optional)
  jitter_ms: 1.0              # Delay variation (optional)
  loss_percent: 0.1           # Packet loss probability (optional)
  rate_mbps: 100.0            # Bandwidth limit (optional)
  correlation_percent: 25.0   # Loss correlation (optional, default: 25)
```

## Expected Results

- **Ping RTT**: ~20ms (2 × 10ms one-way delay) ± 2ms (jitter)
- **Packet Loss**: ~0.1% (1 in 1000 packets)
- **Throughput**: Up to 100 Mbps (rate limited by tbf qdisc)

## Comparison with Wireless Links

| Feature | Fixed Netem | Wireless |
|---------|-------------|----------|
| **Channel server** | Not required | Required |
| **Scene file** | Not required | Required |
| **Parameters** | Explicitly specified | Computed from RF |
| **Dynamic updates** | No (static) | Yes (with mobility) |
| **Realism** | Deterministic | Physics-based |

## Notes

- Fixed links use the same netem implementation as wireless links, just with directly specified parameters
- Both endpoints can have different parameters for asymmetric links (e.g., ADSL)
- Loss correlation models burst losses (consecutive packet drops)
