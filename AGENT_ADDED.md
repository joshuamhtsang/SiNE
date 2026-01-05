# New Claude Code Agent: linux-networking-specialist

**Date**: 2026-01-05
**Agent File**: `.claude/agents/linux-networking-specialist.md`

## Summary

A comprehensive Linux networking specialist agent has been added to the SiNE project. This agent provides deep expertise in the Linux kernel networking stack, Software-Defined Networking (SDN), Open Network Foundation (ONF) technologies, and Mobile Ad-hoc Network (MANET) implementations.

## Agent Capabilities

### 1. Linux Kernel Networking Stack (35% of expertise)
- **Network Namespaces**: nsenter, veth pairs, container isolation
- **Traffic Control (tc/netem)**: qdisc hierarchy, netem parameters, rate limiting (tbf/htb)
- **Linux Bridge**: MAC learning, FDB, bridge vs veth, containerlab integration
- **IP Routing**: Policy-based routing, ECMP, RPF
- **Packet Filtering**: iptables/nftables, NAT, eBPF/XDP
- **Interface Management**: MTU, offloading, statistics
- **Socket Programming**: Raw sockets, netlink, system calls

### 2. Software-Defined Networking (30% of expertise)
- **OpenFlow**: Flow tables, match-action, versions 1.0-1.5
- **Open vSwitch (OVS)**: Architecture, OVSDB, datapath types (kernel/DPDK)
- **ONF ONOS**: Distributed SDN OS, intent framework, clustering
- **ONF Stratum**: P4Runtime, gNMI, gNOI, white-box switches
- **P4 Programming**: Match-action tables, bmv2, hardware targets
- **SDN Controllers**: OpenDaylight, Ryu, Floodlight
- **NFV**: VNF design, service chaining, MANO

### 3. Mobile Ad-hoc Networks (20% of expertise)
- **Routing Protocols**:
  - OLSR (Optimized Link State Routing) - proactive, MPR optimization
  - BATMAN-adv (Better Approach To Mobile Adhoc Networking) - layer 2 routing
  - AODV (Ad-hoc On-Demand Distance Vector) - reactive routing
  - DSR (Dynamic Source Routing) - source routing with caching
  - Babel - distance-vector with DUAL-like loop avoidance
- **Linux Implementation**: Ad-hoc mode, IEEE 802.11s mesh, wireless metrics
- **Performance Metrics**: ETX, ETT, PDR, route stability
- **Security**: SAODV, SOLSR, attack detection

### 4. Container Networking (10% of expertise)
- **Containerlab Integration**: Topology YAML, node kinds, link creation
- **Docker Networking**: Bridge networks, namespaces, CNI plugins
- **Network Namespaces**: nsenter patterns, PID discovery, persistent namespaces
- **Performance**: iperf3, tcpdump in containers, resource limits

### 5. Network Emulation & Testing (3% of expertise)
- **Advanced netem**: Correlation models, distribution-based delay, slot scheduling
- **Performance Testing**: iperf3, netperf, latency/jitter measurement
- **Traffic Generation**: hping3, mausezahn, TRex, D-ITG
- **Topology Emulation**: Mininet, GNS3, CORE

### 6. Troubleshooting & Debugging (2% of expertise)
- **Diagnosis Tools**: ip, ss, ethtool, mtr, tcpdump, bpftrace
- **Kernel Debugging**: /proc/net/, /sys/class/net/, dmesg, ftrace
- **Common Issues**: veth failures, netem not applying, MTU mismatches, routing loops

## Key Use Cases for SiNE

### High Priority (Core SiNE Operations)

1. **Debugging netem in Containerlab**
   - Why netem parameters not applying
   - How to use nsenter with correct PID
   - Verifying qdisc configuration
   - Testing with iperf3

2. **MANET Routing Protocol Integration**
   - Setting up OLSR for triangle topology
   - Configuring BATMAN-adv in containers
   - Multi-hop connectivity testing
   - Route convergence validation

3. **Per-Destination Traffic Control**
   - Using tc filters for destination-based netem
   - HTB + netem hierarchy
   - eBPF classifiers for complex logic

### Medium Priority (Advanced Features)

4. **SDN Controller Integration**
   - Connecting OVS to ONOS
   - OpenFlow flow management
   - P4 programmable data planes

5. **Network Performance Debugging**
   - Analyzing unexpected packet loss
   - Identifying rate limiting vs netem loss
   - TCP vs UDP throughput differences
   - Bidirectional netem effects

### Low Priority (Future Enhancements)

6. **Shared Broadcast Medium for MANET**
   - Linux bridge for true broadcast domain
   - Per-destination filtering with eBPF
   - Hidden node problem modeling

## Agent Invocation

The agent can be invoked in Claude Code using the Task tool:

```python
Task(
    subagent_type="linux-networking-specialist",
    prompt="Debug why netem parameters are not being applied to containerlab interfaces",
    description="Troubleshoot netem configuration"
)
```

## Documentation Updates

### CLAUDE.md Changes

Added new section: "Claude Code Specialized Agents" after "MCP Server Setup"

**Content**:
- Table listing both agents (wireless-comms-engineer, linux-networking-specialist)
- When to use each agent
- Example invocation syntax

**Location**: Lines 128-169 in CLAUDE.md

## Integration with Existing Agent

The new **linux-networking-specialist** agent complements the existing **wireless-comms-engineer** agent:

| Aspect | wireless-comms-engineer | linux-networking-specialist |
|--------|-------------------------|----------------------------|
| **Focus** | RF/PHY layer | Network/Transport layer |
| **Sionna** | Expert (ray tracing, link simulation) | User (understands abstraction) |
| **Channel Modeling** | SNR, BER, BLER, PER computation | Uses netem loss% from channel server |
| **MANET** | Physical layer (fading, mobility) | Routing protocols (OLSR, BATMAN) |
| **Key Tools** | Sionna RT, PathSolver, OFDM | tc/netem, OVS, nsenter, containerlab |
| **Typical Questions** | "What SNR for 64-QAM at 1% PER?" | "Why isn't netem applying to eth1?" |
| **Domain** | Wireless communications engineering | Linux kernel networking |
| **MCP Access** | sionna-docs, context7 | (none specific, uses general tools) |

## Example Collaboration

When debugging a complete SiNE deployment issue:

1. **wireless-comms-engineer**: Validates that channel computation is correct
   - SNR calculation uses from_sionna=True correctly
   - PER at given SNR matches expected value
   - Coding gains are realistic

2. **linux-networking-specialist**: Verifies netem application is working
   - tc qdisc shows correct parameters
   - nsenter uses correct container PID
   - Interface is in UP state
   - Packet counters increasing

Together, they ensure the full pipeline from RF simulation to network emulation is functioning correctly.

## Response Style

The agent provides:
- **Specific command-line examples** with exact syntax
- **Kernel version dependencies** when relevant
- **Troubleshooting steps** with diagnostic commands
- **Validation methods** (tcpdump, ping, iperf3)
- **Trade-offs** (performance vs flexibility)
- **RFC references** (OLSR: RFC 3626, AODV: RFC 3561)
- **Container/namespace context** awareness
- **eBPF/XDP alternatives** for performance

## Files Created/Modified

### Created:
- `.claude/agents/linux-networking-specialist.md` (311 lines)

### Modified:
- `CLAUDE.md` - Added "Claude Code Specialized Agents" section (lines 128-169)

### New Documentation:
- `AGENT_ADDED.md` (this file) - Summary of agent addition

## Testing Recommendations

To validate the agent works correctly:

1. **Basic Invocation Test**:
   ```
   Ask: "How do I debug netem not applying in containerlab?"
   Expected: Agent provides nsenter commands, tc qdisc checks, PID discovery
   ```

2. **MANET Protocol Test**:
   ```
   Ask: "Set up OLSR routing for a 3-node MANET"
   Expected: OLSRd config, interface setup, topology verification steps
   ```

3. **SDN Integration Test**:
   ```
   Ask: "Connect OVS to ONOS controller"
   Expected: ovs-vsctl commands, OpenFlow version setup, verification steps
   ```

4. **Advanced tc Test**:
   ```
   Ask: "Apply different netem params per destination IP"
   Expected: HTB + netem + tc filter hierarchy with examples
   ```

## Future Enhancements

Potential additions to the agent:

1. **eBPF/XDP Programming**: Deeper expertise in writing custom eBPF programs for packet processing
2. **DPDK Integration**: High-performance userspace networking
3. **Kubernetes Networking**: CNI plugins, service meshes, network policies
4. **Linux Wireless Stack**: cfg80211, mac80211, nl80211 APIs
5. **Time-Sensitive Networking (TSN)**: IEEE 802.1 TSN standards, Linux implementation

## Conclusion

The **linux-networking-specialist** agent provides comprehensive Linux networking expertise that is essential for SiNE's network emulation capabilities. It complements the wireless-comms-engineer agent by focusing on the Linux kernel networking stack, SDN integration, and MANET routing protocols.

Key benefits:
- ✅ Domain-specific expertise for netem/tc troubleshooting
- ✅ MANET routing protocol knowledge (OLSR, BATMAN, AODV, Babel)
- ✅ SDN controller integration guidance (ONOS, OVS, P4)
- ✅ Container networking and namespace operations
- ✅ Practical command-line examples with validation steps

This agent will be particularly valuable when:
- Debugging netem configuration issues in containerlab
- Implementing MANET routing protocols for multi-node topologies
- Integrating SDN controllers for dynamic traffic steering
- Optimizing container network performance
- Troubleshooting Linux networking stack issues
