# SINR Implementation Plan for SiNE

## Executive Summary

This plan implements Signal-to-Interference-plus-Noise Ratio (SINR) support for SiNE's wireless channel computation, enabling realistic multi-node interference modeling for MANET topologies. The implementation extends the current SNR-only pipeline with:

- **Multi-transmitter interference**: Calculate how simultaneous transmissions affect each link
- **Adjacent-channel interference**: Model partial interference from nearby frequencies using ACLR
- **Dynamic transmission states**: Track which nodes are actively transmitting (Phase 3)
- **Per-node frequency assignment**: Support centralized radio planning with different frequencies

**Key Insight**: Sionna's `RadioMapSolver` natively computes received signal strength (RSS) from multiple transmitters, which we'll use to calculate interference power at each receiver position.

## Current State Analysis

### Current SNR-Only Pipeline

```
SNR_dB = P_rx - N_dBm
where:
  P_rx = P_tx - path_loss_db  (from Sionna RT)
  N_dBm = thermal noise floor
  NO interference component
```

**Limitation**: Each link computed in isolation. For 3-node MANET with all nodes transmitting:
- Node1→Node2 link ignores interference from Node3's transmission
- Results in optimistic link quality estimates

### Shared Bridge Architecture

The recently implemented shared bridge (`examples/manet_triangle_shared/`) provides:
- All-to-all link computation: N×(N-1) directional links for N nodes
- Per-destination netem via tc flower filters
- Single broadcast domain (realistic MANET)

**Perfect foundation for SINR**: Already computes all links, just needs interference awareness.

## Architecture Design

### SINR Formula

```
SINR_dB = P_signal - 10×log10(P_noise_linear + P_interference_linear)

where:
  P_signal = desired TX→RX received power (from Sionna PathSolver)
  P_noise_linear = 10^(N_dBm / 10)
  P_interference_linear = Σ(10^((P_interferer - ACLR(Δf)) / 10))
```

### Adjacent-Channel Leakage Ratio (ACLR)

Based on WiFi 6 (802.11ax) specifications:

| Frequency Separation | ACLR (dB) | Interference Level |
|----------------------|-----------|-------------------|
| 0-10 MHz (co-channel) | 0 dB | Full interference |
| 10-30 MHz (adjacent) | 20 dB | -20 dB reduction |
| 30-50 MHz (2nd adj) | 40 dB | -40 dB reduction |
| >50 MHz (orthogonal) | 60 dB | Negligible |

**Example**: Node1 at 5.18 GHz receives:
- Node2 at 5.18 GHz (co-channel): Full interference power
- Node3 at 5.20 GHz (20 MHz away): Interference reduced by 20 dB

### Multi-Transmitter Ray Tracing Approach

**Hybrid RadioMapSolver + PathSolver**:

1. **PathSolver** (existing): Compute detailed CIR for TX→RX link
   - Extract path loss, delay, delay spread
   - Used for netem parameters (delay, jitter)

2. **RadioMapSolver** (new): Compute RSS from all transmitters at RX position
   - Get interference power from each peer node
   - Apply ACLR based on frequency separation
   - Aggregate interference in linear domain

**Why hybrid?** RadioMapSolver gives interference but not detailed CIR for jitter calculation. PathSolver gives CIR but only for single TX. We need both.

### Frequency Grouping Strategy

Group nodes by frequency to reduce computational complexity:

```python
# Example: 5 nodes
node_freqs = {
    "node1": 5.18e9,  # Group 1 (co-channel)
    "node2": 5.18e9,  # Group 1
    "node3": 5.20e9,  # Group 1 (adjacent)
    "node4": 5.50e9,  # Group 2 (orthogonal)
    "node5": 5.52e9,  # Group 2 (orthogonal from group 1)
}

# Grouping with 60 MHz threshold:
groups = [
    FrequencyGroup([node1, node2, node3]),  # 5.18-5.20 GHz
    FrequencyGroup([node4, node5])          # 5.50-5.52 GHz
]
```

**Benefits**:
- Only compute interference within groups (nodes >60 MHz apart don't interfere)
- Complexity: O(G × N_g²) instead of O(N²) where G = num groups, N_g = nodes per group
- Typical MANET: 3-5 frequency groups, 5-10 nodes per group

## Implementation Phases

### Phase 1: Same-Frequency Interference (Static TX States)

**Goal**: Basic SINR for co-channel interference, assuming all nodes transmit simultaneously

**New Components**:

1. **`src/sine/channel/sinr.py`** (NEW)
   ```python
   class SINRCalculator:
       def calculate_sinr(
           signal_power_dbm: float,
           interference_terms: list[InterferenceTerm]
       ) -> tuple[float, dict]

       def calculate_aclr(delta_f_mhz: float) -> float
   ```

2. **`src/sine/channel/interference_engine.py`** (NEW)
   ```python
   class InterferenceEngine:
       def compute_interference_for_frequency_group(
           transmitters: list[TransmitterInfo],
           rx_positions: dict[str, tuple]
       ) -> dict[str, InterferenceResult]
   ```

3. **`src/sine/channel/frequency_groups.py`** (NEW)
   ```python
   def group_nodes_by_frequency(
       node_frequencies: dict[str, float],
       adjacent_threshold_hz: float = 20e6
   ) -> list[FrequencyGroup]
   ```

**Modified Components**:

4. **`src/sine/channel/server.py`** (MODIFIED)
   - Add `/compute/sinr` endpoint
   - SINRLinkRequest/SINRResponse models
   - Integration with InterferenceEngine

5. **`src/sine/emulation/controller.py`** (MODIFIED)
   - Add `_update_all_links_with_sinr()` method
   - Frequency grouping logic
   - SINR-aware orchestration

6. **`src/sine/config/schema.py`** (MODIFIED)
   - Add `enable_sinr: bool` field to TopologyConfig
   - Add `TransmissionState` config

**Testing**:
- Unit tests: SINR calculation, ACLR formula, frequency grouping
- Integration: 3-node same-frequency topology (`examples/sinr_basic/`)
- Validation: SINR < SNR, ~5-10 dB reduction with 2 interferers

**Expected Output**:
```
Deployment Summary:
  Link: node1→node2 [wireless]
    SNR: 35.2 dB | SINR: 28.4 dB | Interferers: 1 (node3)
    Delay: 0.10 ms | Jitter: 0.00 ms | Loss: 0.00% | Rate: 450 Mbps
```

### Phase 2: Adjacent-Channel Interference

**Goal**: Model partial interference from nearby frequencies with ACLR rejection

**New Components**:

1. **ACLR calculation** in `SINRCalculator`
   - Piecewise linear ACLR model (0, 20, 40, 60 dB)
   - Configurable per-topology

**Modified Components**:

2. **`src/sine/channel/interference_engine.py`** (MODIFIED)
   - Multi-frequency support in RadioMapSolver
   - ACLR application to interference terms

3. **`src/sine/emulation/controller.py`** (MODIFIED)
   - Process multiple frequency groups
   - Cross-group interference calculation (with ACLR)

**Testing**:
- Unit tests: ACLR for various Δf values
- Integration: 3-node mixed-frequency (`examples/sinr_adjacent/`)
  - Node1: 5.18 GHz, Node2: 5.20 GHz (adjacent, 20 dB rejection)
  - Node3: 5.26 GHz (2nd adjacent, 40 dB rejection)
- Validation: Graded interference based on frequency separation

**Example Configuration** (`examples/sinr_adjacent/network.yaml`):
```yaml
topology:
  enable_sinr: true

  nodes:
    node1:
      interfaces:
        eth1:
          wireless:
            frequency_ghz: 5.18  # Channel 36
    node2:
      interfaces:
        eth1:
          wireless:
            frequency_ghz: 5.20  # Channel 40 (adjacent)
    node3:
      interfaces:
        eth1:
          wireless:
            frequency_ghz: 5.26  # Channel 52 (2nd adjacent)
```

### Phase 3: Dynamic Transmission State Tracking

**Goal**: Automatically track which nodes are transmitting and update SINR dynamically

This phase implements three complementary approaches for detecting transmission states:
- **3A: Manual API Control** (baseline, always available)
- **3B: Rate-Based Auto-Detection** (optional, for autonomous operation)
- **3C: Application-Layer Signaling** (advanced, for MANET protocol integration)

---

#### Phase 3A: Manual API Control (Baseline)

**Goal**: External control of transmission states for controlled experiments

**New Components**:

1. **Transmission state API** in `server.py`
   ```python
   class TransmissionStateUpdate(BaseModel):
       states: dict[str, bool]  # {node_name: is_transmitting}

   @app.post("/api/transmission/state")
   async def update_transmission_state(request: TransmissionStateUpdate):
       """Manually set transmission states for specific nodes."""
       updated_nodes = []
       for node_name, is_tx in request.states.items():
           if _transmission_states.get(node_name) != is_tx:
               _transmission_states[node_name] = is_tx
               updated_nodes.append(node_name)

       if updated_nodes:
           await _recompute_sinr_for_affected_links(updated_nodes)

       return {"status": "ok", "updated": updated_nodes}

   @app.get("/api/transmission/state")
   async def get_transmission_state():
       """Get current transmission states for all nodes."""
       return {"states": _transmission_states}
   ```

2. **Rate limiting** (`src/sine/topology/netem_scheduler.py`)
   ```python
   class NetemUpdateScheduler:
       """Rate-limit netem updates to prevent thrashing."""

       def __init__(self, min_interval_sec=1.0, sinr_hysteresis_db=3.0):
           self.min_interval_sec = min_interval_sec
           self.sinr_hysteresis_db = sinr_hysteresis_db
           self._last_update: dict[tuple[str, str], float] = {}
           self._last_sinr: dict[tuple[str, str], float] = {}

       def should_update(self, tx_node: str, rx_node: str, new_sinr_db: float) -> bool:
           """Check if netem should be updated for this link."""
           link_key = (tx_node, rx_node)
           now = time.time()

           # Check time interval
           last_time = self._last_update.get(link_key, 0)
           if now - last_time < self.min_interval_sec:
               return False

           # Check SINR hysteresis
           last_sinr = self._last_sinr.get(link_key)
           if last_sinr is not None:
               sinr_delta = abs(new_sinr_db - last_sinr)
               if sinr_delta < self.sinr_hysteresis_db:
                   return False

           # Update allowed
           self._last_update[link_key] = now
           self._last_sinr[link_key] = new_sinr_db
           return True
   ```

**Modified Components**:

3. **`src/sine/channel/interference_engine.py`** (MODIFIED)
   ```python
   def compute_interference_for_frequency_group(
       self,
       transmitters: list[TransmitterInfo],
       rx_positions: dict[str, tuple],
       active_tx_states: dict[str, bool]  # NEW parameter
   ):
       """Compute interference only from active transmitters."""
       # Filter to only active transmitters
       active_transmitters = [
           tx for tx in transmitters
           if active_tx_states.get(tx.node_name, True)  # Default: transmitting
       ]

       if not active_transmitters:
           logger.warning("No active transmitters in frequency group")
           return {}

       # ... rest of RadioMapSolver computation with active_transmitters only
   ```

4. **`src/sine/emulation/controller.py`** (MODIFIED)
   ```python
   async def _recompute_sinr_for_affected_links(
       self, changed_nodes: list[str]
   ) -> None:
       """Incrementally recompute SINR for links affected by state change."""
       # Identify affected links (where changed_node is TX or neighbor of RX)
       affected_links = []
       for tx_node, rx_node in self._all_links:
           if tx_node in changed_nodes or rx_node in changed_nodes:
               affected_links.append((tx_node, rx_node))

       logger.info(f"State change affects {len(affected_links)} links")

       # Recompute SINR for affected links only
       for tx_node, rx_node in affected_links:
           result = await self._compute_sinr_for_link(
               tx_node, rx_node, self._current_tx_states
           )

           # Check rate limiting before applying netem
           if self.netem_scheduler.should_update(tx_node, rx_node, result.sinr_db):
               await self._apply_netem_update(tx_node, rx_node, result)
   ```

**Testing**:
- Unit tests: State update API, rate limiting, hysteresis
- Integration: Toggle node TX states, verify SINR updates
- Stress: Rapid state changes (>10 Hz), verify no thrashing

**Usage Example**:
```bash
# Deploy with dynamic state API enabled
sudo $(which uv) run sine deploy examples/sinr_dynamic/network.yaml

# Check current states
curl http://localhost:8000/api/transmission/state

# Node2 stops transmitting
curl -X POST http://localhost:8000/api/transmission/state \
  -H "Content-Type: application/json" \
  -d '{"states": {"node2": false}}'

# SINR for node1→node3 improves (one less interferer)
# Netem updates automatically (rate-limited to 1 Hz, 3 dB hysteresis)

# Resume node2 transmission
curl -X POST http://localhost:8000/api/transmission/state \
  -d '{"states": {"node2": true}}'
```

---

#### Phase 3B: Rate-Based Auto-Detection (Optional)

**Goal**: Automatically detect transmission state from interface traffic rates

This eliminates manual intervention for autonomous MANET operation.

**New Components**:

1. **Traffic monitor** (`src/sine/channel/transmission_detector.py`, NEW)
   ```python
   class RateBasedTransmissionDetector:
       """Detect transmission state from interface traffic rate."""

       def __init__(
           self,
           clab_manager: ContainerlabManager,
           tx_threshold_kbps: float = 10.0,
           poll_interval_sec: float = 0.1,
       ):
           self.clab_manager = clab_manager
           self.threshold_kbps = tx_threshold_kbps
           self.poll_interval = poll_interval_sec
           self._prev_tx_bytes: dict[str, int] = {}
           self._current_states: dict[str, bool] = {}
           self._state_change_callbacks: list[Callable] = []

       def register_callback(self, callback: Callable[[dict[str, bool]], None]):
           """Register callback for state changes."""
           self._state_change_callbacks.append(callback)

       async def start_monitoring(self, nodes: list[str], interface: str = "eth1"):
           """Start monitoring interface statistics."""
           logger.info(f"Starting transmission detection for {len(nodes)} nodes")

           while True:
               changed_states = {}

               for node_name in nodes:
                   # Read TX byte counter from container
                   current_bytes = await self._get_tx_bytes(node_name, interface)
                   prev_bytes = self._prev_tx_bytes.get(node_name, current_bytes)

                   # Calculate rate over poll interval
                   bytes_delta = current_bytes - prev_bytes
                   rate_kbps = (bytes_delta / self.poll_interval) * 8 / 1000

                   # Determine new state
                   is_transmitting = rate_kbps > self.threshold_kbps
                   prev_state = self._current_states.get(node_name)

                   # Detect state change
                   if prev_state is None or is_transmitting != prev_state:
                       self._current_states[node_name] = is_transmitting
                       changed_states[node_name] = is_transmitting
                       logger.debug(
                           f"{node_name}: {'TX' if is_transmitting else 'IDLE'} "
                           f"({rate_kbps:.1f} kbps)"
                       )

                   self._prev_tx_bytes[node_name] = current_bytes

               # Notify callbacks of state changes
               if changed_states:
                   for callback in self._state_change_callbacks:
                       await callback(changed_states)

               await asyncio.sleep(self.poll_interval)

       async def _get_tx_bytes(self, node_name: str, interface: str) -> int:
           """Get TX byte counter from container interface."""
           container = self.clab_manager.get_container_info(node_name)
           cmd = f"cat /sys/class/net/{interface}/statistics/tx_bytes"

           result = subprocess.run(
               ["sudo", "nsenter", "-t", str(container.pid), "-n", "sh", "-c", cmd],
               capture_output=True,
               text=True,
           )

           return int(result.stdout.strip())
   ```

**Modified Components**:

2. **`src/sine/emulation/controller.py`** (MODIFIED)
   ```python
   async def start(self):
       """Start emulation with optional auto-detection."""
       # ... existing deployment code ...

       # Start auto-detection if enabled
       if self.config.topology.transmission_state.enable_auto_detection:
           self.tx_detector = RateBasedTransmissionDetector(
               self.clab_manager,
               tx_threshold_kbps=self.config.topology.transmission_state.tx_threshold_kbps,
           )

           # Register callback for state changes
           self.tx_detector.register_callback(self._on_transmission_state_change)

           # Start monitoring in background
           nodes = list(self.config.topology.nodes.keys())
           asyncio.create_task(
               self.tx_detector.start_monitoring(nodes, interface_name="eth1")
           )
           logger.info("Transmission auto-detection started")

   async def _on_transmission_state_change(self, changed_states: dict[str, bool]):
       """Callback when transmission states change."""
       logger.info(f"Auto-detected state change: {changed_states}")

       # Update internal state
       self._current_tx_states.update(changed_states)

       # Recompute SINR for affected links
       await self._recompute_sinr_for_affected_links(list(changed_states.keys()))
   ```

**Configuration Schema**:
```yaml
topology:
  transmission_state:
    enable_auto_detection: bool = false  # Enable rate-based detection
    tx_threshold_kbps: float = 10.0      # Rate threshold (kbps)
    poll_interval_sec: float = 0.1       # Polling frequency (100ms)
```

**Testing**:
- Unit tests: Byte counter reading, rate calculation, state detection
- Integration: Generate traffic with iperf, verify auto-detection
- Validation: Compare auto-detected states vs actual traffic patterns

**Usage Example**:
```bash
# Deploy with auto-detection enabled
sudo $(which uv) run sine deploy examples/sinr_auto/network.yaml

# topology.transmission_state.enable_auto_detection: true

# Start traffic on node1
docker exec clab-sinr-auto-node1 iperf3 -c 192.168.100.2 -t 10 &

# SiNE automatically detects node1 transmitting
# SINR for node2→node3 degrades (interference from node1)
# When iperf finishes, node1 detected as idle
# SINR for node2→node3 improves back
```

**Pros**:
- Fully automatic, no manual intervention
- Works with any traffic source (routing protocols, apps, tests)
- Robust to packet bursts (rate averaging)

**Cons**:
- 100ms detection latency
- Requires defining "transmitting" threshold (configurable)
- Doesn't capture MAC-layer scheduling details

---

#### Phase 3C: Application-Layer Signaling (Advanced)

**Goal**: Explicit signaling from MANET routing protocols for accurate transmission windows

This is most accurate for scheduled access protocols (TDMA, polling, etc.).

**Integration Approach**:

MANET routing daemons (OLSR, BATMAN, Babel) or custom applications explicitly signal transmission windows:

```python
# Example: OLSR daemon integration
import requests

class SiNETransmissionSignaler:
    """Signal transmission state to SiNE channel server."""

    def __init__(self, node_name: str, channel_server_url: str = "http://localhost:8000"):
        self.node_name = node_name
        self.server_url = channel_server_url

    def start_transmission(self):
        """Signal that this node is about to transmit."""
        try:
            requests.post(
                f"{self.server_url}/api/transmission/state",
                json={"states": {self.node_name: True}},
                timeout=0.1,
            )
        except Exception as e:
            logger.debug(f"Failed to signal TX start: {e}")

    def stop_transmission(self):
        """Signal that this node finished transmitting."""
        try:
            requests.post(
                f"{self.server_url}/api/transmission/state",
                json={"states": {self.node_name: False}},
                timeout=0.1,
            )
        except Exception as e:
            logger.debug(f"Failed to signal TX stop: {e}")

# Usage in OLSR route update
def broadcast_hello():
    signaler.start_transmission()
    send_hello_packet()
    signaler.stop_transmission()
```

**Docker Image Integration**:

Include signaler library in `docker/sine-node/Dockerfile`:
```dockerfile
FROM alpine:latest

# Install Python for signaling
RUN apk add --no-cache python3 py3-requests

# Copy SiNE signaler library
COPY sine_signaler.py /usr/local/lib/python3.12/site-packages/
```

**Configuration**:
```yaml
topology:
  transmission_state:
    enable_app_signaling: bool = true
    fallback_to_auto_detection: bool = true  # Use rate-based if no signals
```

**Testing**:
- Integration: Modified OLSR daemon with signaling
- Validation: Compare signaled states vs actual packet transmission
- Timing: Measure signaling latency (<1ms)

**Usage Example**:
```bash
# Deploy with app signaling
sudo $(which uv) run sine deploy examples/sinr_olsr/network.yaml

# Inside container, OLSR daemon uses signaler
docker exec clab-sinr-olsr-node1 cat /etc/olsrd/olsrd.conf
# ... plugin "sine_signaler.so" enabled

# OLSR broadcasts use explicit TX windows
# SINR computed with precise interference timing
```

**Pros**:
- Most accurate (protocol knows exactly when transmitting)
- Low overhead (only API call on TX start/stop)
- Works perfectly with scheduled protocols (TDMA, polling)

**Cons**:
- Requires application/protocol modification
- Not transparent
- Doesn't work for arbitrary traffic (need auto-detection fallback)

---

### Phase 3 Summary: Hybrid Approach

**Recommended Configuration**:

```yaml
topology:
  enable_sinr: true

  transmission_state:
    # Phase 3A: Manual API (always available)
    default_all_transmitting: bool = false  # Start with all idle

    # Phase 3B: Auto-detection (optional)
    enable_auto_detection: bool = true      # Enable for autonomous operation
    tx_threshold_kbps: float = 10.0
    poll_interval_sec: float = 0.1

    # Phase 3C: App signaling (advanced)
    enable_app_signaling: bool = false      # Enable if apps support it
    fallback_to_auto_detection: bool = true  # Fall back if no signals
```

**Decision Logic**:
1. If app sends explicit signal → use signaled state (most accurate)
2. Else if auto-detection enabled → use rate-based state
3. Else → use manual API state (default: all transmitting if not set)

**Implementation Priority**:
1. **Phase 3A** (Week 4): Manual API - baseline functionality
2. **Phase 3B** (Week 5): Auto-detection - autonomous operation
3. **Phase 3C** (Future): App signaling - when MANET protocols integrated

## Critical Files

### Phase 1: Same-Frequency SINR

| File | Type | Purpose |
|------|------|---------|
| [src/sine/channel/sinr.py](src/sine/channel/sinr.py) | NEW | SINR calculation with interference aggregation |
| [src/sine/channel/interference_engine.py](src/sine/channel/interference_engine.py) | NEW | Multi-TX interference using RadioMapSolver |
| [src/sine/channel/frequency_groups.py](src/sine/channel/frequency_groups.py) | NEW | Frequency grouping utilities |
| [src/sine/channel/server.py](src/sine/channel/server.py) | MODIFIED | Add `/compute/sinr` endpoint |
| [src/sine/emulation/controller.py](src/sine/emulation/controller.py) | MODIFIED | SINR-aware link orchestration |
| [src/sine/config/schema.py](src/sine/config/schema.py) | MODIFIED | Add `enable_sinr` config field |

### Phase 2: Adjacent-Channel

| File | Type | Purpose |
|------|------|---------|
| [src/sine/channel/sinr.py](src/sine/channel/sinr.py) | MODIFIED | Add ACLR calculation |
| [src/sine/channel/interference_engine.py](src/sine/channel/interference_engine.py) | MODIFIED | Multi-frequency support |
| [src/sine/emulation/controller.py](src/sine/emulation/controller.py) | MODIFIED | Multi-frequency group processing |

### Phase 3: Dynamic State

| File | Type | Purpose |
|------|------|---------|
| [src/sine/channel/server.py](src/sine/channel/server.py) | MODIFIED | State API + storage |
| [src/sine/topology/netem_scheduler.py](src/sine/topology/netem_scheduler.py) | NEW | Rate limiting wrapper |
| [src/sine/emulation/controller.py](src/sine/emulation/controller.py) | MODIFIED | State change event handling |

## Configuration Schema Changes

### New Fields in `network.yaml`

```yaml
topology:
  # Enable SINR computation (default: false, use SNR only)
  enable_sinr: bool

  # Transmission state configuration
  transmission_state:
    # Phase 1: All nodes transmit simultaneously (worst-case)
    default_all_transmitting: bool = true

    # Phase 3: Enable dynamic state tracking via API
    enable_dynamic_state: bool = false

  # ACLR configuration (optional, WiFi 6 defaults)
  aclr_config:
    co_channel_db: 0.0
    adjacent_db: 20.0
    second_adjacent_db: 40.0
    orthogonal_db: 60.0

  nodes:
    node1:
      interfaces:
        eth1:
          wireless:
            # Per-node frequency assignment (existing field)
            frequency_ghz: 5.18
            # ... other wireless params
```

## Testing Strategy

### Unit Tests

**`tests/test_sinr_calculator.py`**:
- SINR == SNR when no interferers
- SINR < SNR with co-channel interferer
- SINR reduction ~3 dB for equal-power interferer
- ACLR calculation for various Δf

**`tests/test_interference_engine.py`**:
- RadioMapSolver integration
- Multi-TX RSS extraction
- Interference aggregation (linear domain)

**`tests/test_frequency_groups.py`**:
- Same-frequency nodes in one group
- Orthogonal channels in separate groups
- Adjacent-channel grouping logic

### Integration Tests

**`tests/integration/test_sinr_manet.py`**:
- 3-node same-frequency: SINR ~5-10 dB lower than SNR
- 3-node mixed-frequency: Graded interference by ACLR
- Dynamic state: TX toggle changes SINR

**`examples/sinr_basic/`**:
- 3-node equilateral triangle, all 5.18 GHz
- Verify symmetric SINR (all links ~same quality)

**`examples/sinr_adjacent/`**:
- 3-node with frequencies [5.18, 5.20, 5.26] GHz
- Verify ACLR rejection (20 dB, 40 dB)

**`examples/sinr_dynamic/`**:
- 4-node with state API
- Toggle scripts for TX states

## Verification

### End-to-End Test

```bash
# 1. Start channel server
uv run sine channel-server

# 2. Deploy with SINR enabled
sudo $(which uv) run sine deploy examples/sinr_basic/network.yaml

# Expected deployment summary:
# Link: node1→node2 [wireless]
#   SNR: 35.2 dB | SINR: 28.4 dB | Interferers: 1
#   Delay: 0.10 ms | Loss: 0.05% | Rate: 450 Mbps

# 3. Verify tc configuration shows higher loss than SNR-only
docker exec clab-sinr-basic-node1 tc -s qdisc show dev eth1

# 4. Test connectivity (should work despite interference)
docker exec clab-sinr-basic-node1 ping -c 5 192.168.100.2

# 5. Cleanup
sudo $(which uv) run sine destroy examples/sinr_basic/network.yaml
```

### Success Criteria

**Phase 1**:
- ✓ SINR < SNR for all links with interferers
- ✓ 3-node same-freq shows ~5-10 dB SINR reduction
- ✓ Deployment summary displays both SNR and SINR
- ✓ Netem parameters use SINR (not SNR) for BER/PER calculation
- ✓ Unit + integration tests pass

**Phase 2**:
- ✓ Adjacent-channel shows ~20 dB ACLR rejection
- ✓ Orthogonal channels (>60 MHz) have negligible interference
- ✓ Frequency grouping works correctly
- ✓ Mixed-frequency topology shows graded interference

**Phase 3**:
- ✓ State API updates transmission states
- ✓ SINR recomputation only for affected links
- ✓ Rate limiting prevents thrashing (<1 Hz updates)
- ✓ TX toggle causes expected SINR change
- ✓ Stable under rapid state changes

## Edge Cases

### 1. No Interferers → Graceful Degradation
```python
# Single link, no other nodes
assert abs(result.sinr_db - result.snr_db) < 0.1
```

### 2. All Interferers Orthogonal
```yaml
# node1: 5.18 GHz, node2: 5.50 GHz (320 MHz apart)
# ACLR ≥ 60 dB, interference negligible
assert result.total_interference_dbm < result.signal_power_dbm - 60
```

### 3. Frequency Overlap Validation
```python
def validate_frequency_separation(f1, f2, bw):
    delta = abs(f1 - f2)
    if delta < bw/2: return "overlapping"  # ERROR
    elif delta < bw: return "adjacent"
    else: return "orthogonal"
```

### 4. Zero Active Transmitters
```python
# Phase 3: All nodes set to is_transmitting=false
# Response: Warning + use default params
logger.warning("No active transmitters, using SNR-only mode")
```

## Implementation Order

### Week 1: Phase 1 Core Infrastructure
1. Create `SINRCalculator` class (sinr.py)
2. Create `InterferenceEngine` class (interference_engine.py)
3. Create `FrequencyGroup` utilities (frequency_groups.py)
4. Unit tests for SINR calculation

### Week 2: Phase 1 Integration
5. Add `/compute/sinr` endpoint to channel server
6. Modify controller for SINR orchestration
7. Add `enable_sinr` config field
8. Integration test for 3-node same-frequency

### Week 3: Phase 2 Adjacent-Channel
9. Implement ACLR calculation
10. Multi-frequency support in InterferenceEngine
11. Frequency grouping in controller
12. Integration test for mixed-frequency

### Week 4: Phase 3 Dynamic State (Optional)
13. State storage + API endpoint
14. Rate limiting scheduler
15. State change event handling
16. Stress testing

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| RadioMapSolver performance slow | High | Optimize cell_size, samples_per_tx; cache results |
| Sionna doesn't support multi-freq in single scene | Medium | Use separate scenes per frequency group |
| Netem update thrashing | Medium | Rate limiting + hysteresis (1 Hz, 3 dB) |
| ACLR model inaccurate | Low | Make ACLR configurable per-topology |
| Backward compatibility breaks | High | Feature flag: `enable_sinr=false` by default |

## Backward Compatibility

- `enable_sinr=false` (default): Use existing SNR-only pipeline, no changes
- `enable_sinr=true`: Opt-in to SINR mode
- All existing examples work unchanged
- Deployment summary shows both SNR and SINR when enabled

## Future Enhancements

- **Per-destination ACLR**: Different rejection ratios per node pair
- **Directional antennas**: Spatial interference rejection
- **Frequency hopping**: Time-varying frequency assignments
- **Interference whitening**: Advanced receiver modeling
- **Multi-cell scenarios**: Inter-cell interference for cellular topologies
