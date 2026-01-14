Implementation Plan: True Broadcast Medium for MANET
Overview
Migrate SiNE's MANET emulation from point-to-point veth pairs to a shared broadcast domain using a Linux bridge with per-destination netem filtering. This enables realistic MANET behavior including broadcast medium, hidden node problems, and single-interface-per-node architecture.

Key Decisions
Based on user input, the implementation will:

Coexistence Model: Both point-to-point and shared bridge modes will coexist

Shared bridge is opt-in via shared_bridge.enabled: true in YAML
Existing topologies continue using P2P model (backward compatible)
Users can choose which model fits their use case
TC Filter Technology: flower filters for Phase 1 (MVP)

Hash-based O(1) lookup (better than u32's O(N) linear search)
Supports 30+ nodes efficiently (vs. u32's 10-node practical limit)
Minimal complexity overhead, standard on modern kernels (4.2+)
Future: eBPF for extreme scale (1000+ nodes)
IP Address Assignment: User-specified in YAML

Each interface gets explicit ip_address field
Schema validates uniqueness at load time
More flexible than auto-assignment, prevents hidden magic
Clear error messages for IP conflicts
Link Types: Wireless-only for Phase 1

Shared bridge only supports wireless interfaces (simpler implementation)
Mixed wireless + fixed_netem nodes not supported initially
Wired links continue using separate P2P model
Future: Support mixed mode after wireless-only is proven
Current vs. Proposed Architecture
Current (Point-to-Point)

Node1:eth1 ═══════ Node2:eth1    3 nodes = 3 veth pairs
Node1:eth2 ═══════ Node3:eth1    Each node has N-1 interfaces
Node2:eth2 ═══════ Node3:eth2    Simple netem (one per interface)
Pros: Simple, accurate per-link conditions
Cons: Not broadcast, no hidden node, multiple interfaces per node

Proposed (Shared Bridge)

         Linux Bridge (br0)
              ├── Node1:eth1 (HTB + per-dest filters)
              ├── Node2:eth1 (HTB + per-dest filters)
              └── Node3:eth1 (HTB + per-dest filters)
Pros: True broadcast, hidden node modeling, single interface
Cons: Complex tc filter rules, requires HTB hierarchy

Technical Approach
Per-Destination Netem Architecture
Each node interface requires a 3-layer TC hierarchy:


Root HTB qdisc
  └── Parent class (1:1, unlimited)
       ├── Class 1:10 → Netem (to Node2) → Filter (dst 192.168.1.2)
       ├── Class 1:20 → Netem (to Node3) → Filter (dst 192.168.1.3)
       └── Class 1:99 → Netem (broadcast)  → Default (no filter)
Example commands (using flower filters):


# 1. HTB root + parent class
tc qdisc add dev eth1 root handle 1: htb default 99
tc class add dev eth1 parent 1: classid 1:1 htb rate 1000mbit

# 2. Default class for broadcast/multicast (MANET routing)
tc class add dev eth1 parent 1:1 classid 1:99 htb rate 1000mbit
tc qdisc add dev eth1 parent 1:99 handle 99: netem delay 1ms

# 3. Per-destination class + netem + flower filter (hash-based)
tc class add dev eth1 parent 1:1 classid 1:10 htb rate 200mbit
tc qdisc add dev eth1 parent 1:10 handle 10: netem delay 10ms 1ms loss 0.1%
tc filter add dev eth1 protocol ip parent 1:0 prio 1 \
    flower dst_ip 192.168.100.2 action pass flowid 1:10
Why flower instead of u32:

O(1) hash lookup vs. O(N) linear search
Supports 1000+ destinations efficiently
Same syntax complexity as u32
Better performance at scale (< 2 μs per packet)
Filter Technology Selection
Filter Type	Complexity	Max Destinations	Recommendation
u32	O(N) linear	100-500	Simple but slower
flower	O(1) hash	1000+	Phase 1 (MVP): Hash-based, scalable
eBPF	O(1) hashmap	10,000+	Phase 2: Dynamic updates
Using flower filters for Phase 1 - Hash-based lookup provides better scalability (supports 30+ nodes) with minimal complexity overhead. Requires kernel 4.2+ (standard on modern systems).

Implementation Plan
Phase 1: Schema and YAML Changes
Goal: Extend topology schema to support shared bridge domains

1.1 Update Topology Schema
File: src/sine/config/schema.py

Add new schema elements:


class SharedBridgeDomain(BaseModel):
    """Shared broadcast domain for MANET."""
    enabled: bool = Field(description="Enable shared bridge mode")
    name: str = Field(description="Bridge name (e.g., 'manet-br0')")
    nodes: list[str] = Field(description="Nodes in this domain")
    interface_name: str = Field(default="eth1", description="Interface to attach")

    @model_validator(mode='after')
    def validate_all_wireless(self) -> 'SharedBridgeDomain':
        """Ensure all nodes in bridge have wireless interfaces (no mixed mode in Phase 1)."""
        # Validation happens in TopologyConfig after nodes are loaded
        return self

class InterfaceConfig(BaseModel):
    """Interface configuration (add ip_address field)."""
    ip_address: str | None = Field(default=None, description="IP address for tc filter matching (required for shared bridge)")
    wireless: WirelessParams | None = None
    fixed_netem: FixedNetemParams | None = None

    @model_validator(mode='after')
    def validate_params(self) -> 'InterfaceConfig':
        """Ensure exactly one of wireless or fixed_netem is provided."""
        if self.wireless and self.fixed_netem:
            raise ValueError("Interface cannot have both wireless and fixed_netem params")
        if not self.wireless and not self.fixed_netem:
            raise ValueError("Interface must have either wireless or fixed_netem params")
        return self

class TopologyConfig(BaseModel):
    name: str
    scene: SceneConfig | None = None
    shared_bridge: SharedBridgeDomain | None = None  # NEW
    links: list[LinkConfig] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_bridge_or_links(self) -> 'TopologyConfig':
        """Ensure either shared_bridge OR explicit links, not both."""
        has_bridge = self.shared_bridge and self.shared_bridge.enabled
        has_links = len(self.links) > 0

        if has_bridge and has_links:
            raise ValueError("Cannot use both shared_bridge and explicit links")
        if not has_bridge and not has_links:
            raise ValueError("Must specify either shared_bridge or links")

        # If shared bridge, validate IP addresses and wireless-only
        if has_bridge:
            self._validate_shared_bridge()

        return self

    def _validate_shared_bridge(self) -> None:
        """Validate shared bridge configuration."""
        bridge = self.shared_bridge
        interface_name = bridge.interface_name

        for node_name in bridge.nodes:
            if node_name not in self.nodes:
                raise ValueError(f"Bridge node '{node_name}' not defined in nodes section")

            node = self.nodes[node_name]
            if interface_name not in node.interfaces:
                raise ValueError(f"Node '{node_name}' missing interface '{interface_name}'")

            iface = node.interfaces[interface_name]

            # Phase 1: Only wireless interfaces allowed
            if not iface.wireless:
                raise ValueError(
                    f"Node '{node_name}' interface '{interface_name}' must be wireless "
                    f"(mixed wireless + fixed_netem not supported in Phase 1)"
                )

            # IP address required for tc filter matching
            if not iface.ip_address:
                raise ValueError(
                    f"Node '{node_name}' interface '{interface_name}' must have ip_address "
                    f"(required for tc flower filters)"
                )

            # Validate IP format
            try:
                import ipaddress
                ipaddress.ip_address(iface.ip_address)
            except ValueError:
                raise ValueError(f"Invalid IP address for {node_name}:{interface_name}: {iface.ip_address}")

        # Check for IP conflicts
        ip_map = {}
        for node_name in bridge.nodes:
            ip = self.nodes[node_name].interfaces[interface_name].ip_address
            if ip in ip_map:
                raise ValueError(
                    f"IP address conflict: {ip} used by both {ip_map[ip]} and {node_name}"
                )
            ip_map[ip] = node_name
Validation rules:

If shared_bridge.enabled=true: Links are auto-generated (all-to-all mesh)
If shared_bridge not present: Use current explicit link model
Nodes in shared_bridge.nodes must have wireless params on specified interface
1.2 Example YAML Changes
Current format (point-to-point):


# examples/manet_triangle/network.yaml (current)
topology:
  name: manet-triangle
  scene:
    file: scenes/vacuum.xml
  links:
    - endpoints: [node1:eth1, node2:eth1]
    - endpoints: [node1:eth2, node3:eth1]
    - endpoints: [node2:eth2, node3:eth2]

nodes:
  node1:
    kind: linux
    image: alpine:latest
    interfaces:
      eth1:
        wireless: {position: {x: 0, y: 0, z: 1}, ...}
      eth2:
        wireless: {position: {x: 0, y: 0, z: 1}, ...}
  # ... similar for node2, node3
Proposed format (shared bridge):


# examples/manet_triangle_shared/network.yaml (new)
topology:
  name: manet-triangle-shared
  scene:
    file: scenes/vacuum.xml
  shared_bridge:
    enabled: true
    name: manet-br0
    nodes: [node1, node2, node3]
    interface_name: eth1  # Single interface per node

nodes:
  node1:
    kind: linux
    image: alpine:latest
    interfaces:
      eth1:
        ip_address: 192.168.100.1  # User-specified IP for tc filters
        wireless:
          position: {x: 0, y: 0, z: 1}
          frequency_ghz: 5.18
          rf_power_dbm: 20.0
          # ... other wireless params
  node2:
    kind: linux
    image: alpine:latest
    interfaces:
      eth1:
        ip_address: 192.168.100.2
        wireless: {position: {x: 10, y: 0, z: 1}, ...}
  node3:
    kind: linux
    image: alpine:latest
    interfaces:
      eth1:
        ip_address: 192.168.100.3
        wireless: {position: {x: 5, y: 8.66, z: 1}, ...}
Key differences:

✅ Single interface per node (eth1 only)
✅ User-specified IP addresses for tc filter matching
✅ No explicit link endpoints
✅ shared_bridge section defines domain membership
✅ Links auto-generated from node list (all-to-all)
✅ Simpler, more readable for MANET topologies
Phase 2: Containerlab Integration
Goal: Generate bridge-based containerlab topology instead of veth pairs

2.1 Add Bridge Topology Generator
File: src/sine/topology/manager.py

Add new method to ContainerlabManager:


def generate_shared_bridge_topology(
    self,
    bridge_config: SharedBridgeDomain
) -> dict[str, Any]:
    """
    Generate containerlab topology with shared bridge.

    Returns containerlab YAML with bridge + node connections:
    {
        "topology": {
            "nodes": {...},
            "links": [
                {"endpoints": ["br0", "node1:eth1"]},
                {"endpoints": ["br0", "node2:eth1"]},
                {"endpoints": ["br0", "node3:eth1"]}
            ]
        }
    }
    """
    topology = {
        "name": self.config.name,
        "topology": {
            "nodes": {},
            "links": []
        }
    }

    # Add all nodes
    for node_name in bridge_config.nodes:
        node_config = self.config.nodes[node_name]
        topology["topology"]["nodes"][node_name] = {
            "kind": node_config.kind,
            "image": node_config.image
        }

    # Add bridge node
    bridge_name = bridge_config.name
    topology["topology"]["nodes"][bridge_name] = {
        "kind": "bridge"
    }

    # Connect each node to bridge
    for node_name in bridge_config.nodes:
        interface = bridge_config.interface_name
        topology["topology"]["links"].append({
            "endpoints": [bridge_name, f"{node_name}:{interface}"]
        })

    return topology
2.2 Update Deployment Logic
File: src/sine/topology/manager.py

Modify deploy() method to detect bridge mode:


def deploy(self) -> None:
    """Deploy containerlab topology (point-to-point OR shared bridge)."""
    if self.config.shared_bridge:
        clab_topology = self.generate_shared_bridge_topology(
            self.config.shared_bridge
        )
    else:
        # Current point-to-point logic
        clab_topology = self.generate_clab_topology()

    # Write to .sine_clab_topology.yaml
    with open(".sine_clab_topology.yaml", "w") as f:
        yaml.dump(clab_topology, f)

    # Deploy with containerlab
    subprocess.run(
        ["containerlab", "deploy", "-t", ".sine_clab_topology.yaml"],
        check=True
    )
Phase 3: Per-Destination Netem Implementation
Goal: Apply per-destination netem using HTB + tc filters

3.1 New Netem Configuration Module
File: src/sine/topology/shared_netem.py (new file)


from dataclasses import dataclass
from typing import Dict
from sine.topology.netem import NetemParams

@dataclass
class PerDestinationConfig:
    """Per-destination netem configuration."""
    node: str
    interface: str
    default_params: NetemParams  # For broadcast/multicast
    dest_params: Dict[str, NetemParams]  # {dest_ip: NetemParams}

class SharedNetemConfigurator:
    """Configure per-destination netem on shared bridge."""

    def __init__(self, container_manager):
        self.container_manager = container_manager

    def apply_per_destination_netem(
        self,
        config: PerDestinationConfig
    ) -> None:
        """
        Apply HTB + per-destination netem to interface.

        Creates:
        1. HTB root qdisc (handle 1:)
        2. Parent class 1:1
        3. Default class 1:99 with broadcast netem
        4. Per-destination classes 1:10, 1:20, ... with netem
        5. Filters to classify traffic by dest IP
        """
        container = self.container_manager.get_container(config.node)
        pid = container.pid
        interface = config.interface

        commands = []

        # 1. HTB root (default to class 1:99 for broadcast)
        commands.append(
            f"tc qdisc add dev {interface} root handle 1: htb default 99"
        )

        # 2. Parent class (unlimited)
        commands.append(
            f"tc class add dev {interface} parent 1: classid 1:1 htb rate 1000mbit"
        )

        # 3. Default class for broadcast/multicast
        default = config.default_params
        commands.append(
            f"tc class add dev {interface} parent 1:1 classid 1:99 htb rate 1000mbit"
        )
        commands.append(
            f"tc qdisc add dev {interface} parent 1:99 handle 99: "
            f"netem delay {default.delay_ms}ms"
        )

        # 4. Per-destination classes + netem + filters
        classid = 10
        for dest_ip, params in config.dest_params.items():
            # HTB class
            commands.append(
                f"tc class add dev {interface} parent 1:1 classid 1:{classid} "
                f"htb rate {params.rate_mbps}mbit"
            )

            # Netem qdisc
            netem_opts = [f"delay {params.delay_ms}ms"]
            if params.jitter_ms > 0:
                netem_opts.append(f"{params.jitter_ms}ms")
            if params.loss_percent > 0:
                netem_opts.append(f"loss {params.loss_percent}%")

            commands.append(
                f"tc qdisc add dev {interface} parent 1:{classid} handle {classid}: "
                f"netem {' '.join(netem_opts)}"
            )

            # flower filter (hash-based IP destination match)
            commands.append(
                f"tc filter add dev {interface} protocol ip parent 1:0 prio 1 "
                f"flower dst_ip {dest_ip} action pass flowid 1:{classid}"
            )

            classid += 10

        # Execute all commands in container namespace
        for cmd in commands:
            subprocess.run(
                ["sudo", "nsenter", "-t", str(pid), "-n", "sh", "-c", cmd],
                check=True
            )
3.2 IP Address Application
Solution: Read user-specified IPs from YAML and apply to container interfaces.

File: src/sine/topology/manager.py

Add IP application logic:


def apply_bridge_ips(self, bridge_config: SharedBridgeDomain) -> Dict[str, str]:
    """
    Apply user-specified IPs to container interfaces.

    Returns: {node_name: ip_address}
    """
    ip_assignments = {}
    interface_name = bridge_config.interface_name

    for node_name in bridge_config.nodes:
        node_config = self.config.nodes[node_name]
        ip_address = node_config.interfaces[interface_name].ip_address

        # Store mapping
        ip_assignments[node_name] = ip_address

        # Apply IP to container interface
        container = self.container_manager.get_container(node_name)
        subprocess.run([
            "sudo", "nsenter", "-t", str(container.pid), "-n",
            "ip", "addr", "add", f"{ip_address}/24", "dev", interface_name
        ], check=True)

    return ip_assignments
Phase 4: Channel Computation for Shared Bridge
Goal: Compute all-to-all link conditions and build per-destination netem configs

4.1 Update Controller Logic
File: src/sine/emulation/controller.py

Add shared bridge handling:


def _update_shared_bridge_links(self) -> None:
    """Compute and apply per-destination netem for shared bridge."""
    bridge_config = self.config.shared_bridge
    nodes = bridge_config.nodes
    interface = bridge_config.interface_name

    # 1. Apply user-specified IPs to all nodes
    ip_map = self.clab_manager.apply_bridge_ips(bridge_config)

    # 2. Build all-to-all link list for channel computation
    wireless_links = []
    for tx_node in nodes:
        for rx_node in nodes:
            if tx_node == rx_node:
                continue  # Skip self-links

            tx_iface_config = self.config.nodes[tx_node].interfaces[interface]
            rx_iface_config = self.config.nodes[rx_node].interfaces[interface]

            wireless_links.append({
                "tx_node": tx_node,
                "rx_node": rx_node,
                "tx_params": tx_iface_config.wireless,
                "rx_params": rx_iface_config.wireless
            })

    # 3. Batch compute all link conditions
    results = self.channel_client.compute_batch(wireless_links)

    # 4. Build per-node destination maps
    per_node_config: Dict[str, PerDestinationConfig] = {}
    for tx_node in nodes:
        per_node_config[tx_node] = PerDestinationConfig(
            node=tx_node,
            interface=interface,
            default_params=NetemParams(delay_ms=1.0, jitter_ms=0, loss_percent=0, rate_mbps=1000),
            dest_params={}
        )

    for result in results:
        tx_node = result["tx_node"]
        rx_node = result["rx_node"]
        rx_ip = ip_map[rx_node]

        per_node_config[tx_node].dest_params[rx_ip] = NetemParams(
            delay_ms=result["delay_ms"],
            jitter_ms=result["jitter_ms"],
            loss_percent=result["loss_percent"],
            rate_mbps=result["rate_mbps"]
        )

    # 5. Apply per-destination netem to all nodes
    from sine.topology.shared_netem import SharedNetemConfigurator
    configurator = SharedNetemConfigurator(self.clab_manager.container_manager)

    for node_name, config in per_node_config.items():
        configurator.apply_per_destination_netem(config)
Phase 5: Testing and Validation
Goal: Verify shared bridge implementation works correctly

5.1 Create Test Topology
File: examples/manet_triangle_shared/network.yaml


topology:
  name: manet-triangle-shared
  scene:
    file: scenes/vacuum.xml
  shared_bridge:
    enabled: true
    name: manet-br0
    nodes: [node1, node2, node3]
    interface_name: eth1

nodes:
  node1:
    kind: linux
    image: alpine:latest
    interfaces:
      eth1:
        wireless:
          position: {x: 0, y: 0, z: 1}
          frequency_ghz: 5.18
          rf_power_dbm: 20.0
          antenna_pattern: dipole
          antenna_polarization: V
          bandwidth_mhz: 80
          modulation: 64qam
          fec_type: ldpc
          fec_code_rate: 0.5
  node2:
    kind: linux
    image: alpine:latest
    interfaces:
      eth1:
        wireless:
          position: {x: 10, y: 0, z: 1}
          frequency_ghz: 5.18
          rf_power_dbm: 20.0
          antenna_pattern: dipole
          antenna_polarization: V
          bandwidth_mhz: 80
          modulation: 64qam
          fec_type: ldpc
          fec_code_rate: 0.5
  node3:
    kind: linux
    image: alpine:latest
    interfaces:
      eth1:
        wireless:
          position: {x: 5, y: 8.66, z: 1}
          frequency_ghz: 5.18
          rf_power_dbm: 20.0
          antenna_pattern: dipole
          antenna_polarization: V
          bandwidth_mhz: 80
          modulation: 64qam
          fec_type: ldpc
          fec_code_rate: 0.5
5.2 Validation Tests
Test 1: TC Configuration Verification


# Deploy
sudo $(which uv) run sine deploy examples/manet_triangle_shared/network.yaml

# Verify HTB hierarchy on each node
for node in node1 node2 node3; do
    echo "=== $node ==="
    docker exec clab-manet-triangle-shared-$node tc qdisc show dev eth1
    docker exec clab-manet-triangle-shared-$node tc class show dev eth1
    docker exec clab-manet-triangle-shared-$node tc filter show dev eth1
done
Expected output:

HTB root qdisc with default 99
Classes: 1:1 (parent), 1:99 (default), 1:10 (dest1), 1:20 (dest2)
Netem qdiscs on each class
Filters matching destination IPs
Test 2: Ping RTT Verification


# Node1 → Node2 (should match 2× delay_ms)
docker exec clab-manet-triangle-shared-node1 ping -c 5 192.168.100.2

# Node1 → Node3
docker exec clab-manet-triangle-shared-node1 ping -c 5 192.168.100.3

# Node2 → Node3
docker exec clab-manet-triangle-shared-node2 ping -c 5 192.168.100.3
Test 3: Filter Match Statistics


# Verify packets are hitting correct filters
docker exec clab-manet-triangle-shared-node1 tc -s filter show dev eth1
Look for non-zero "Sent" counters on each filter.

Test 4: Throughput Testing


# Start iperf3 server on node2
docker exec -d clab-manet-triangle-shared-node2 iperf3 -s

# Test from node1 (should cap at rate_mbps)
docker exec clab-manet-triangle-shared-node1 iperf3 -c 192.168.100.2 -t 10
Test 5: Broadcast Traffic


# Test broadcast (should use default class 1:99)
docker exec clab-manet-triangle-shared-node1 ping -b -c 5 192.168.100.255

# Verify with filter stats (should NOT hit per-dest filters)
docker exec clab-manet-triangle-shared-node1 tc -s class show dev eth1 | grep "class 1:99"
5.3 MANET Routing Protocol Testing
Goal: Verify shared bridge works with real MANET protocols

Example: OLSR (Optimized Link State Routing)


# Install olsrd in containers
for node in node1 node2 node3; do
    docker exec clab-manet-triangle-shared-$node apk add olsrd
done

# Configure and start OLSR
for node in node1 node2 node3; do
    docker exec clab-manet-triangle-shared-$node sh -c '
        cat > /etc/olsrd.conf << EOF
Interface "eth1" {
    HelloInterval 2.0
    TcInterval 5.0
}
EOF
        olsrd -f /etc/olsrd.conf -d 0
    '
done

# Wait for route convergence
sleep 10

# Verify routing tables
docker exec clab-manet-triangle-shared-node1 ip route
Expected: Routes to 192.168.100.2 and 192.168.100.3 via eth1

Phase 6: Deployment Summary and Visualization
Goal: Update deployment output to show shared bridge info

6.1 Update Deployment Summary
File: src/sine/emulation/controller.py

Modify get_deployment_summary():


def get_deployment_summary(self) -> str:
    """Generate deployment summary (point-to-point OR shared bridge)."""
    if self.config.shared_bridge:
        return self._get_shared_bridge_summary()
    else:
        # Existing point-to-point summary
        return self._get_p2p_summary()

def _get_shared_bridge_summary(self) -> str:
    """Summary for shared bridge deployment."""
    lines = []
    lines.append("=" * 80)
    lines.append("MANET DEPLOYMENT SUMMARY (Shared Broadcast Domain)")
    lines.append("=" * 80)

    bridge_config = self.config.shared_bridge

    # Bridge info
    lines.append(f"\nBridge: {bridge_config.name}")
    lines.append(f"Nodes: {', '.join(bridge_config.nodes)}")
    lines.append(f"Interface: {bridge_config.interface_name}")

    # Per-node configuration
    for node_name in bridge_config.nodes:
        lines.append(f"\n{node_name} ({ip_map[node_name]}):")

        config = self._get_per_dest_config(node_name)
        for dest_ip, params in config.dest_params.items():
            dest_node = self._ip_to_node(dest_ip)
            lines.append(
                f"  → {dest_node} ({dest_ip}): "
                f"delay={params.delay_ms:.2f}ms, "
                f"jitter={params.jitter_ms:.2f}ms, "
                f"loss={params.loss_percent:.2f}%, "
                f"rate={params.rate_mbps:.1f}Mbps"
            )

    lines.append("=" * 80)
    return "\n".join(lines)
Example output:


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
Critical Files to Modify
File	Changes	Lines Est.
src/sine/config/schema.py	Add SharedBridgeDomain, validators	+50
src/sine/topology/manager.py	Add generate_shared_bridge_topology(), assign_bridge_ips()	+80
src/sine/topology/shared_netem.py	NEW FILE - SharedNetemConfigurator	+150
src/sine/emulation/controller.py	Add _update_shared_bridge_links(), update deploy logic	+120
examples/manet_triangle_shared/network.yaml	NEW FILE - Example shared bridge topology	+60
Total: ~460 lines of new code

Migration Strategy
Backward Compatibility
Both modes must coexist:

Existing topologies continue using point-to-point model
New topologies opt-in with shared_bridge.enabled: true
Schema validation prevents mixing modes
Detection logic:


if config.shared_bridge and config.shared_bridge.enabled:
    # Use shared bridge path
    deploy_shared_bridge()
else:
    # Use existing point-to-point path
    deploy_point_to_point()
User Migration Path
Keep existing examples unchanged (backward compatible)
Add new _shared variants for MANET examples
Document both approaches in README
Recommend shared bridge for new MANET topologies
Feature Parity
Phase 1 (MVP): Shared bridge for wireless-only MANET

All nodes must have wireless interfaces
No mixed wireless + fixed_netem in same bridge
Simple u32 filters
Phase 2: Advanced features

Mixed wireless + wired nodes (bridge + P2P links)
flower filters for > 10 nodes
Mobility updates for per-destination netem
Phase 3: Scale and optimization

eBPF classifiers for > 30 nodes
Hidden node modeling
Collision simulation
Performance Considerations
TC Filter Overhead
Scenario	Filter Type	Nodes	CPU Overhead	Recommendation
Small MANET	flower	3-10	< 2%	✅ Phase 1 MVP
Medium MANET	flower	10-30	< 3%	✅ Phase 1 MVP
Large MANET	eBPF	30+	< 1%	Future phase
Latency Impact
Filter lookup: 1-20 μs (negligible vs. emulated delays)
Bridge forwarding: ~10 μs
Total overhead: < 30 μs (acceptable for MANET emulation)
Scalability Limits
flower filters (Phase 1):

Hash-based O(1) lookup per packet
Supports 30+ nodes (900+ destination filters) with < 5% CPU
Max practical: 100+ nodes before noticeable overhead
Well-suited for typical MANET research scenarios
eBPF classifiers (Future):

Dynamic map updates (no tc restart)
Custom logic for complex scenarios
Supports 1000+ destinations efficiently
Testing Checklist
Unit Tests
 Schema validation (shared_bridge vs links mutual exclusion)
 IP assignment uniqueness
 TC command generation
 Filter syntax validation
Integration Tests
 3-node MANET deployment
 Ping RTT matches expected delay
 Filter match statistics correct
 Throughput caps at configured rate
 Broadcast traffic uses default class
End-to-End Tests
 OLSR routing protocol convergence
 BATMAN-adv mesh networking
 Mobility updates (future)
 Mixed wireless + fixed nodes (future)
Performance Tests
 CPU usage with 10 nodes (90 filters)
 Latency overhead measurement
 Throughput comparison vs. P2P model
Documentation Updates
README.md
 Add "Shared Bridge Model" section to MANET Support
 Update example commands with _shared variant
 Document shared_bridge YAML schema
 Add migration guide for existing MANET topologies
Examples
 Create examples/manet_triangle_shared/
 Add README explaining differences vs. P2P
 Include validation and testing commands
CLAUDE.md
 Update architecture diagram
 Document per-destination netem pipeline
 Add troubleshooting guide for TC filters
Risk Mitigation
Risk 1: TC Complexity
Impact: Users struggle with debugging TC filter issues
Mitigation:

Comprehensive error messages
Validation before deployment
Debug command examples in docs
Risk 2: IP Address Conflicts
Impact: User assigns duplicate IPs to different nodes
Mitigation:

Schema validation detects IP conflicts at load time
Clear error messages showing conflicting nodes
Suggest IP range in documentation (192.168.100.0/24)
Deployment summary shows all IP assignments for verification
Risk 3: Broadcast/Multicast Handling
Impact: MANET routing protocols fail due to missing default class
Mitigation:

Always create default class (1:99)
Test with real MANET protocols (OLSR, BATMAN)
Monitor default class traffic in debug mode
Risk 4: Performance Degradation
Impact: Large MANETs (> 30 nodes) have high CPU usage
Mitigation:

Using flower filters from Phase 1 (hash-based, scalable to 100+ nodes)
Document performance characteristics (CPU overhead vs. node count)
Provide eBPF migration path in Phase 2 for extreme scale (1000+ nodes)
Benchmark and publish performance metrics
Success Metrics
Functionality
✅ 3-node MANET deploys successfully
✅ Ping RTT matches expected values (within 10%)
✅ OLSR routing protocol converges
✅ Broadcast traffic uses default class
Performance
✅ CPU overhead < 5% for 10-node MANET
✅ Latency overhead < 50 μs
✅ Throughput matches configured rate limits
Usability
✅ YAML schema simpler than P2P (fewer lines)
✅ Deployment summary clearly shows per-dest config
✅ Error messages guide users to fix TC issues
Next Steps After Implementation
Community feedback: Test with real MANET researchers
flower migration: Phase 2 for > 10 nodes
Mobility support: Dynamic per-dest netem updates
Hidden node modeling: Collision simulation
O-RAN integration: gNB mesh networks
References
TC Guide: /tmp/per_destination_netem_guide.md (500+ lines, comprehensive)
Test Script: /tmp/test_per_dest_netem.sh (executable demo)
Research Agent: ae3dd51 (MANET implementation exploration)
Networking Agent: ac00d9c (TC filter research)
