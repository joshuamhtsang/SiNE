## Lesson Learned 1 - Real-Time Scene Viewer Design: Avoid Redundant Computation

**Problem**: Claude Code initially proposed adding a `POST /api/paths/all` endpoint that would re-compute ray-traced paths on-demand when the visualization viewer queries (every 1 second). This approach completely missed that the channel server already computes these paths during normal emulation operation when setting netem parameters. The result would have been expensive ray tracing (100-500ms per link) repeated every second despite the paths already being computed.

**User Intervention**: The user recognized this inefficiency immediately and asked: "Can we just query the channel server for the latest node positions?" This led to discovering that paths were already being computed for netem configuration and could simply be cached.

**Solution**: Instead of on-demand computation, the channel server now caches paths during normal operation in a global `_path_cache` dictionary. A new `GET /api/visualization/state` endpoint returns these pre-computed paths instantly (~1-2ms instead of 100-500ms). Memory overhead is negligible (~10-50KB per link), and paths are guaranteed to match current netem parameters since they're from the same computation.

**Key Lesson**: Before adding features that require expensive computed data, always investigate whether that data is already being generated elsewhere in the system. AI code assistants can generate plausible architectures but may miss system-wide optimization opportunities. A 5-minute human review prevented implementing a fundamentally inefficient design that would have been expensive to fix later. The best code is often the code you don't write - or in this case, the computation you avoid repeating.




## Lesson Learned 2 - Containerlab Bridge Modes: Self-Contained Deployment

**Problem**: Claude Code initially assumed containerlab could directly create Linux bridges as part of topology deployment, but containerlab documentation (https://containerlab.dev/manual/kinds/bridge/) reveals it cannot. Containerlab only manages container lifecycle and veth pair creation - bridges must be handled separately. This is a subtle limitation that's easy to miss when working with container orchestration tools.

**Options Available**:
1. **Pre-creation of bridges in host namespace**: Requires running separate scripts before `containerlab deploy`, breaking the single-command deployment model. Users would need to manually create bridges, track their lifecycle, and clean them up separately.
2. **Container-Namespace Bridges**: Create bridges inside container network namespaces as part of the deployment itself, making the bridge lifecycle tied to the container.

**User Decision**: Chose option 2 (container-namespace bridges) because it maintains SiNE's principle of having `network.yaml` as a complete, self-contained deployment description. With this approach, `sine deploy network.yaml` handles everything - no separate bridge setup scripts, no manual cleanup, no state outside the containerlab topology. When the topology is destroyed, bridges are automatically cleaned up with their containers.

**Key Lesson**: When integrating third-party orchestration tools like containerlab, carefully read documentation to understand limitations in resource management. Even seemingly basic operations (like creating bridges) may not be supported. Design decisions should favor self-contained, atomic deployments where a single command creates all necessary resources and cleanup is automatic. This reduces operational complexity and prevents orphaned resources from incomplete deployments.



## Lesson Learned 3 - Integration Tests Drive Development and Expose Design Flaws

**Problem**: Implementing SINR and MAC protocols (CSMA, TDMA) was difficult and required extensive steering. Claude Code struggled with spatial reasoning (hidden node problems, carrier sensing ranges) and created circular dependencies. More critically, basic Linux networking errors went unnoticed - SiNE was using `/32` host routes instead of proper subnet routes for bridge connectivity, breaking multi-hop communication.

**Solution**: Comprehensive integration tests codified human requirements and exposed issues early. Refining tests required domain knowledge to identify common Linux networking pitfalls. A complete overhaul of `examples/` and `tests/` directories organized by key parameters (topology: shared_bridge vs p2p, engine: sionna vs fallback, interference: SNR vs SINR) made test coverage gaps immediately visible.

**Discovery**: The reorganization revealed that SINR computation was implicitly coupled to MAC protocol configuration - SINR wasn't computed unless CSMA or TDMA was defined in `network.yaml`. This was a hidden architectural flaw that only became obvious when test coverage was systematically mapped. The fix was implementing an explicit `topology.enable_sinr: true` flag to decouple interference modeling from MAC protocols.

**Key Lesson**: Integration tests are not just validation - they're design tools that expose architectural assumptions and missing requirements. Claude Code can generate sophisticated algorithms but may miss basic operational details (like routing table configuration). Systematic test organization helps identify coupling and coverage gaps that are invisible in ad-hoc testing. "So smart, but so stupid, like Jan in Love is Blind" - AI can handle complexity but miss fundamentals without comprehensive tests.


## Lesson Learned 4 - Build Simplified "Unphysical" Models First, Then Add Realism

**Problem**: Implementing physically accurate wireless interference modeling all at once creates overwhelming complexity. Multiple interacting features (frequency separation, spectral masks, MAC protocols, time-domain scheduling) must work together, making debugging nearly impossible.

**Approach**: SiNE's SINR implementation started with a deliberately simplified "unphysical" model - all peer nodes contributed interference to a receiver regardless of frequency overlap. This meant a 2.4 GHz transmitter would interfere with a 5.18 GHz receiver, which is physically incorrect but computationally simple. This baseline allowed testing the core SINR calculation pipeline (signal power summation, noise floor, interference aggregation) without the added complexity of spectral filtering.

**Progression**: Once the basic SINR pipeline worked, realism was added incrementally: (1) MAC protocols (TDMA, CSMA) to model time-domain interference probability (`tx_probability`), (2) Adjacent-Channel Leakage Ratio (ACLR) filtering based on IEEE 802.11ax spectral masks to handle multi-frequency scenarios, (3) Carrier sensing for CSMA to model hidden node problems. Each addition was testable in isolation against the working baseline.

**Key Lesson**: When implementing complex physical models, start with intentionally simplified "wrong but simple" versions to establish working infrastructure. Add realism incrementally, validating each addition against previous behavior. This prevents the "everything is broken and I don't know why" problem common in complex system development. It's faster to build a simple working system and then add complexity than to debug a comprehensive but non-functional implementation. Accept temporary unphysical behavior as a development aid, not a failure.

## Lesson Learned 5 - Granularity Matters: Interface-Level vs Node-Level Configuration

**Problem**: Claude Code initially proposed placing the `is_active` flag at the node level, which would enable/disable all radios on a node simultaneously. This seemed logical for simple single-radio nodes but breaks down for multi-radio scenarios common in real wireless systems.

**User Insight**: The `is_active` flag should be at the wireless interface level (on `WirelessParams`), not the node level. This provides crucial flexibility for realistic scenarios: (1) **Dual-band radios**: disable 2.4 GHz radio for power saving while keeping 5 GHz active, (2) **Hardware failures**: one radio fails while others remain operational, (3) **Regulatory compliance**: disable specific frequency bands in certain regions, (4) **Adaptive radio selection**: dynamically enable/disable radios based on channel conditions or traffic load.

**Consistency Argument**: The interface-level placement aligns with SiNE's existing architecture - wireless parameters (position, frequency, power, antenna, MCS) are already per-interface. Each interface can have different modulation schemes and antenna configurations. Even position is per-interface to support antenna arrays at different physical locations on the same node. Making `is_active` node-level would be an architectural inconsistency.

**Key Lesson**: Configuration granularity decisions should match the finest-grained control needed in realistic use cases, not just the simplest implementation. AI assistants may default to coarser granularity (node-level) because it's simpler, but domain knowledge reveals why finer granularity (interface-level) is necessary. Always consider multi-instance scenarios (multiple radios, multiple antennas) when deciding where to place configuration parameters.

## Lesson Learned 6 - Strategic Grep Usage Accelerates Claude Code Collaboration

**Problem**: Claude Code spends significant time searching codebases to understand where changes are needed or verify completions. When you already know patterns or locations, providing grep results upfront can save multiple round-trips and accelerate development.

**When to Grep Yourself**:
1. **Understanding usage patterns**: Want to know how a pytest fixture is used across test files? `grep -r "channel_server" tests/integration/*.py` shows all invocations instantly, faster than opening multiple files in VS Code.
2. **Finding implementation locations**: `grep "def compute_sinr" src/sine/**/*.py` locates function definitions across nested directories.
3. **Tracking configuration patterns**: `grep "enable_sinr" examples/**/*.yaml` reveals how features are configured in existing examples.
4. **Verifying naming conventions**: `grep "class.*Engine" src/sine/channel/*.py` shows engine class naming patterns before implementing new ones.

**Advanced Grep Patterns**:
- **Wildcard matching**: `grep "node.*:.*192.168" *.py` finds lines with node-to-IP mappings (the `.*` acts as regex wildcard).
- **Function definitions**: `grep "^def " src/sine/channel/modulation.py` finds all function definitions (^ anchors to line start).
- **Class usage**: `grep -r "SionnaEngine\(" .` finds instantiation sites, not just imports.

**Key Lesson**: Claude Code is powerful at navigating codebases, but providing targeted grep results as context can reduce search time from minutes to seconds. Use grep when you already know what you're looking for - it's often faster than waiting for Claude to search, especially in large codebases. Think of grep as preprocessing context for Claude, making conversations more efficient.

## Lesson Learned 7 - Simple Tools Beat Complex Tools for Unidirectional Testing

**Problem**: Claude Code initially used iperf3 for UDP throughput testing, but iperf3 requires bidirectional control traffic even for UDP tests (server sends acknowledgments back to client). In SiNE's asymmetric netem scenarios (where TX and RX directions have different channel conditions), this control traffic could fail or distort results. The client-server handshake assumes symmetric connectivity, which doesn't match real wireless links with different noise figures or path losses per direction.

**First Solution**: Switch from iperf3 to dd piped into netcat (`dd if=/dev/zero bs=1M count=100 | nc <destination_ip> <port>`). This provides truly unidirectional data flow - dd generates data, nc sends it, and the receiver just writes to disk. No control traffic, no handshaking, no bidirectional assumptions.

**New Challenge**: How to know when the transfer completes? The test duration depends on netem throughput parameters (100 MB at 10 Mbps takes 80 seconds, but at 1 Mbps takes 800 seconds). Claude Code initially used fixed timeouts (sleep commands), but these either waste time (timeout too long) or fail to capture completion (timeout too short).

**User Insight**: Instead of guessing completion time, directly monitor the output file size in the destination container: `watch -n 1 'docker exec <container> du -sh /tmp/received_data'`. When the file size stops growing for a few seconds, the transfer is complete. This works regardless of throughput - you observe the actual result rather than predicting when it should finish.

**Key Lesson**: Sophisticated tools aren't always better for specific testing needs. Iperf3 is excellent for general network testing but its protocol assumptions (bidirectional control, TCP for setup) can interfere with edge-case scenarios like asymmetric wireless links. Simple Unix tools (dd, nc, du) composed together often provide more control and transparency. More importantly, direct observation (monitoring file size) beats prediction (fixed timeouts) when test duration is variable or unknown. Design tests to be self-evident in their completion rather than requiring accurate timing estimates.

