# MANET SINR - Asymmetric Triangle (Connectivity Test)

## Purpose

This example demonstrates SINR computation with a **non-equilateral triangle** geometry that produces **positive SINR values** suitable for reliable connectivity testing.

## Key Difference from `shared_sionna_sinr_triangle`

| Aspect | Equilateral (original) | Asymmetric (this example) |
|--------|----------------------|--------------------------|
| **Geometry** | 30m × 30m × 30m | 30m × 91.2m × 91.2m |
| **SINR** | 0 dB (worst-case) | 9-10 dB (node1↔node2), -3 to -4 dB (node3 links) |
| **Connectivity** | 100% packet loss | node1↔node2 only (node3 fails) |
| **Purpose** | SINR computation validation | Demonstrates SINR asymmetry |
| **Modulation** | 64-QAM (fails) | QPSK (works for short links) |

## Topology Geometry

```
   node1 (0, 0, 1) ------ 30m ------ node2 (30, 0, 1)
                \                    /
              91.2m              91.2m
                  \              /
                   node3 (15, 90, 1)
```

**Key insight**: Moving node3 much further away (y=90 instead of y=25.98) creates extreme asymmetry:
- **Short links** (node1↔node2): 30m signal, 91.2m interference → SINR ~9-10 dB (works!)
- **Long links** (node1↔node3, node2↔node3): 91.2m signal, 30m interference → SINR ~-3 to -4 dB (fails!)

## Expected SINR Values

### Link node1↔node2 (Positive SINR - Works!)

- **Signal path**: 30m → path loss ~72 dB → power = -52 dBm
- **Interference** (from node3): 91.2m → path loss ~81.7 dB → power = -61.7 dBm
- **SNR**: 36.0 dB
- **SINR**: ~9-10 dB (9.7 dB improvement from weaker interference)
- **Expected packet loss**: 0-5% (QPSK threshold ~8 dB)
- **Expected throughput**: 50-64 Mbps

### Links node1↔node3, node2↔node3 (Negative SINR - Fails!)

- **Signal path**: 91.2m → path loss ~81.7 dB → power = -61.7 dBm
- **Interference**: 30m → path loss ~72 dB → power = -52 dBm
- **SNR**: 26.3 dB
- **SINR**: ~-3 to -4 dB (interference MUCH stronger than signal!)
- **Expected packet loss**: 100% (negative SINR, no connectivity)
- **Expected throughput**: 0 Mbps

## Deployment

```bash
# Start channel server
uv run sine channel-server

# Deploy topology
sudo $(which uv) run sine deploy examples/for_tests/shared_sionna_sinr_asymmetric/network.yaml
```

## Testing

### Connectivity Test

```bash
# Good connectivity expected (SINR ~9-10 dB)
docker exec clab-manet-asymmetric-sinr-node1 ping -c 10 192.168.100.2

# NO connectivity expected (SINR ~-3 to -4 dB, 100% loss)
docker exec clab-manet-asymmetric-sinr-node1 ping -c 10 192.168.100.3
# Expected: 100% packet loss
```

### Throughput Test

```bash
# High-SINR link (node1→node2) - Works!
docker exec -d clab-manet-asymmetric-sinr-node2 iperf3 -s
docker exec clab-manet-asymmetric-sinr-node1 iperf3 -c 192.168.100.2 -t 10
# Expected: 50-64 Mbps

# Negative-SINR link (node1→node3) - Fails!
docker exec -d clab-manet-asymmetric-sinr-node3 iperf3 -s
docker exec clab-manet-asymmetric-sinr-node1 iperf3 -c 192.168.100.3 -t 10
# Expected: 0 Mbps (100% packet loss, no connectivity)
```

## Integration Tests

See `tests/integration/shared_bridge/sionna_engine/sinr/test_sinr_asymmetric_connectivity.py`:

- `test_sinr_asymmetric_connectivity`: Validates node1↔node2 ping connectivity (should pass)
- `test_sinr_asymmetric_throughput`: Validates high-SINR link throughput (40-80 Mbps)
- `test_sinr_asymmetric_low_sinr_link`: Documents negative-SINR behavior (marked xfail, 100% loss expected)

## Cleanup

```bash
sudo $(which uv) run sine destroy examples/for_tests/shared_sionna_sinr_asymmetric/network.yaml
```

## References

- Investigation: [dev_resources/INVESTIGATION_2026-02-04_sinr-antenna-pattern-bug.md](../../../dev_resources/INVESTIGATION_2026-02-04_sinr-antenna-pattern-bug.md)
- Original (equilateral): [../shared_sionna_sinr_triangle/](../shared_sionna_sinr_triangle/)
- CLAUDE.md: SINR Configuration section
