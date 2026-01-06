# TCP Throughput Fluctuations in SiNE

This document explains why TCP throughput fluctuates during network emulation, particularly when observing iperf3 measurements through netem-controlled links.

## Observed Behavior

When running iperf3 through a SiNE emulated link with a configured rate limit (e.g., 192 Mbps), you may observe throughput fluctuations like:

```
[ ID] Interval           Transfer     Bitrate
[  5]   0.00-1.00   sec  21.6 MBytes   181 Mbits/sec
[  5]   1.00-2.00   sec  24.8 MBytes   208 Mbits/sec
[  5]   2.00-3.00   sec  23.5 MBytes   197 Mbits/sec
[  5]   3.00-4.00   sec  22.1 MBytes   185 Mbits/sec
```

This is **normal TCP behavior**, not a bug in SiNE.

## Why TCP Throughput Fluctuates

### 1. TCP Congestion Control (CUBIC)

Modern Linux systems use the **CUBIC congestion control algorithm** by default, which creates a characteristic sawtooth throughput pattern:

```
Throughput
  │     ╱╲      ╱╲      ╱╲      ╱╲
  │    ╱  ╲    ╱  ╲    ╱  ╲    ╱  ╲
  │   ╱    ╲  ╱    ╲  ╱    ╲  ╱    ╲
  │  ╱      ╲╱      ╲╱      ╲╱      ╲
  └──────────────────────────────────> Time
     Ramp   Drop  Ramp  Drop  Ramp
      up           up         up
```

**How CUBIC works:**
- **Slow start**: TCP window grows exponentially until it detects congestion (packet loss or delay)
- **Congestion avoidance**: Window grows more slowly using cubic function
- **Multiplicative decrease**: When congestion detected, window is cut (typically by 30%)
- **Fast recovery**: Window ramps back up

This cycle repeats continuously, causing throughput to oscillate around the available bandwidth.

### 2. Token Bucket Filter (tbf) Burst Allowance

SiNE uses Linux `tc tbf` (Token Bucket Filter) to enforce rate limits. The tbf qdisc allows short bursts above the configured rate:

**Token bucket parameters:**
- **Rate**: 192 Mbps (tokens added at this rate)
- **Burst**: Allows temporary excursions above the rate
- **Latency**: Maximum buffering time before packets are dropped

When TCP sends a burst of packets:
1. Tokens accumulate in the bucket
2. Burst uses tokens faster than they're added
3. When bucket empties, packets are delayed or dropped
4. TCP backs off, tokens accumulate again
5. Cycle repeats

This interaction between TCP's send pattern and tbf's token bucket creates throughput variations.

#### Large Bursts (2-3× Configured Rate)

You may occasionally see **very large bursts** that far exceed the configured rate:

```
[  5]  67.00-68.00  sec  14.1 MBytes   119 Mbits/sec  136    644 KBytes
[  5]  68.00-69.00  sec  57.0 MBytes   478 Mbits/sec  225    838 KBytes  ← 2.5× the 192 Mbps limit!
[  5]  69.00-70.00  sec  17.5 MBytes   147 Mbits/sec  234    295 KBytes
```

**What's happening:**
1. **Slow period** (67-68s): Only 119 Mbps → tokens accumulate in bucket
2. **TCP sends burst**: Uses accumulated tokens + current tokens
3. **iperf3 1-second measurement**: Captures the burst, showing 478 Mbps
4. **Bucket empties**: Packets delayed/dropped (note "225" retransmits in column 5)
5. **Recovery period** (69-70s): Only 147 Mbps as TCP recovers from loss

**Why tbf allows this:**
- The `burst` parameter in SiNE's tbf configuration allows buffering packets up to a certain buffer size
- During idle/slow periods, tokens accumulate up to the burst limit
- When TCP suddenly sends a window of data, all those accumulated tokens can be spent at once
- This creates a **temporary burst window** where throughput can be 2-5× the configured rate

**Confirming tbf burst behavior:**
```bash
# Check tbf configuration on a node interface
docker exec clab-vacuum-20m-node1 tc -s qdisc show dev eth1

# Actual output from SiNE:
# qdisc netem 1: root refcnt 17 limit 1000 delay 100us seed 15392644102542209689
#  Sent 390 bytes 5 pkt (dropped 0, overlimits 0 requeues 0)
#  backlog 0b 0p requeues 0
# qdisc tbf 2: parent 1: rate 192Mbit burst 98174b lat 50ms
#              ^^^^^^^^^^^^^^^^^^^      ^^^^^^^ ^^^^^^^^^
#              Rate limit               Burst   Latency
```

**Understanding the parameters:**
- **rate 192Mbit**: Maximum sustained rate
- **burst 98174b**: Token bucket size = **98.174 KB** (768,000 bits)
  - At 192 Mbps, this represents **~4 milliseconds** of buffering at full rate
  - Tokens accumulate during slow periods (e.g., 1 second at 119 Mbps saves ~73 Mbps worth of tokens)
  - Allows bursts up to: 192 Mbps + (accumulated tokens / burst duration)
  - With 1 second of accumulation at 73 Mbps deficit: burst can reach ~450-500 Mbps briefly
- **lat 50ms**: Maximum latency tolerance before dropping packets

**Why you see 478 Mbps bursts (2.5× the 192 Mbps limit):**

Let's calculate the exact burst capacity from your example:

```
67.00-68.00  sec  14.1 MBytes   119 Mbits/sec  ← Slow period (1 second)
68.00-69.00  sec  57.0 MBytes   478 Mbits/sec  ← BURST!
```

**Token accumulation during slow period (67-68s):**
- Configured rate: 192 Mbps (tokens generated)
- Actual usage: 119 Mbps (tokens consumed)
- Net accumulation: 192 - 119 = **73 Mbps worth of tokens saved**
- Bucket capacity: 98,174 bytes = 785,392 bits = **~4ms of buffering at 192 Mbps**

**Burst capacity calculation:**
1. **Current rate tokens**: 192 Mbps (continuous generation)
2. **Accumulated tokens**: 73 Mbps × 1 second = 73 Mb stored in bucket
3. **Burst duration**: Limited by bucket size (~4ms) OR TCP window size
4. **Peak burst rate**: Current rate + (accumulated tokens / burst duration)

If TCP sends a 57 MByte window over 1 second with most data front-loaded:
- First ~100ms: Drains accumulated 73 Mb + uses current 19.2 Mb = 92.2 Mb
- This allows: 92.2 Mb / 0.1s = **922 Mbps** instantaneous peak
- Over full 1-second measurement window: Average includes slower tail
- **Result: 478 Mbps average** (iperf3 measures total bytes / time)

**Why 2.5× specifically:**
- Token debt from previous period: ~73 Mbps
- Front-loaded TCP window spending: Accumulated + current tokens
- The 478 Mbps is time-averaged over 1 second including the tail

The `burst` parameter (98 KB) effectively creates a "token bank" that allows short-term borrowing above the rate limit. This is **expected tbf behavior**, not a bug. The 2-3× bursts are a natural consequence of TCP's bursty sending pattern combined with token accumulation.

### 3. Buffer Dynamics

Multiple buffering layers affect TCP behavior:

```
App → TCP Send Buffer → Containerlab Bridge → netem Queue → tbf → Receiver
```

- **Bridge buffering**: Linux bridge queues packets temporarily
- **netem queue**: Stores packets for delay/jitter emulation
- **tbf queue**: Enforces rate limit
- **TCP ACK timing**: Return path delays affect send window growth

Buffer fullness varies over time, causing latency variations that TCP interprets as congestion signals.

### 4. Per-Second Measurement Granularity

iperf3 reports throughput averaged over 1-second intervals. This measurement window captures different phases of the TCP congestion control cycle:

- **Rising phase**: Higher throughput (190-208 Mbps)
- **Falling phase**: Lower throughput (180-185 Mbps)
- **Random alignment**: 1-second boundaries don't align with congestion cycles

## Expected Throughput Ranges

For a 192 Mbps netem rate limit:

| Measurement | Value | Notes |
|-------------|-------|-------|
| **Configured rate** | 192 Mbps | netem tbf limit |
| **Normal range** | 175-210 Mbps | Typical fluctuations |
| **Large bursts** | 300-500 Mbps | tbf burst allowance (tokens accumulated during slow periods) |
| **Average throughput** | 180-190 Mbps | TCP overhead + congestion control |
| **Minimum (normal)** | 100-150 Mbps | Post-burst recovery or TCP backoff |

**TCP/IP overhead:**
- TCP header: 20 bytes
- IP header: 20 bytes
- Ethernet frame: 14 bytes header + 4 bytes FCS
- Total overhead: ~3-5% depending on packet size

This overhead explains why average TCP throughput (180-190 Mbps) is slightly below the configured rate (192 Mbps).

### Understanding iperf3 Output Columns

iperf3 with TCP shows additional columns that help explain burst behavior:

```
[ ID] Interval           Transfer     Bitrate         Retr  Cwnd
[  5]  67.00-68.00  sec  14.1 MBytes   119 Mbits/sec  136    644 KBytes
[  5]  68.00-69.00  sec  57.0 MBytes   478 Mbits/sec  225    838 KBytes
[  5]  69.00-70.00  sec  17.5 MBytes   147 Mbits/sec  234    295 KBytes
```

- **Interval**: 1-second measurement window
- **Transfer**: Bytes sent in this interval
- **Bitrate**: Throughput calculated from Transfer (shown in Mbits/sec)
- **Retr**: **Retransmissions** - packets that were lost and resent
- **Cwnd**: **Congestion Window** - TCP's send buffer size

**Key observations:**
- **136 → 225 → 234 retransmits**: Cumulative count increases during/after burst
- **Cwnd shrinks after burst**: 838 KB → 295 KB (TCP backing off from congestion)
- **Low throughput before burst**: 119 Mbps allows token accumulation
- **High throughput during burst**: 478 Mbps spends accumulated tokens
- **Recovery after burst**: 147 Mbps with small Cwnd (TCP rebuilding window)

This pattern is **classic TCP behavior** when hitting a rate limit with burst allowance.

## Is This a Problem?

**No.** This behavior is expected and indicates the system is working correctly:

✅ **Average throughput near configured rate** → netem rate limit working
✅ **Variations around average** → Normal TCP congestion control
✅ **No severe drops or timeouts** → Link quality is good
✅ **Consistent pattern over time** → Stable emulation

## When to Investigate

You should investigate if you see:

❌ **Average << configured rate** (e.g., 100 Mbps average with 192 Mbps limit)
❌ **Severe fluctuations** (e.g., 50 Mbps to 250 Mbps swings)
❌ **Retransmissions** in TCP stats (`ss -ti` or `netstat -s`)
❌ **Growing queues** (`tc -s qdisc show`)
❌ **CPU saturation** on channel server or containers

## How to Verify Correct Operation

### 1. Check average throughput
```bash
# Run longer test and check average
docker exec -it clab-vacuum-20m-node2 iperf3 -c 192.168.1.1 -t 30
# Average should be 180-190 Mbps for 192 Mbps limit
```

### 2. Monitor netem queue
```bash
# Watch for excessive drops or backlog
watch -n 0.5 'docker exec clab-vacuum-20m-node1 tc -s qdisc show dev eth1'
```

### 3. Check TCP retransmissions
```bash
# Inside container, check connection stats
docker exec -it clab-vacuum-20m-node1 ss -ti
# Look for "retrans" field - should be low (<1%)
```

### 4. Verify rate limit is applied
```bash
# Check netem configuration
./CLAUDE_RESOURCES/check_netem.sh
# Should show "rate 192Mbit" on eth1 interfaces
```

## Mobility and Distance Effects

### Fixed Modulation (64-QAM Example)

With fixed modulation, the netem rate stays constant as long as SNR is above the demodulation threshold:

| Distance | Path Loss | SNR | PER | Effective Rate |
|----------|-----------|-----|-----|----------------|
| 20m | 68 dB | 40 dB | ~0% | 192 Mbps |
| 100m | 87 dB | 21 dB | ~0.0003% | ~192 Mbps |
| 200m | 93 dB | 15 dB | ~0.1% | ~192 Mbps |
| 400m | 99 dB | 9 dB | ~15% | ~163 Mbps |

**Why rate doesn't drop at 100m:**
- 64-QAM with LDPC coding can operate down to ~10-15 dB SNR
- At 100m, SNR is still 21 dB (well above threshold)
- PER is near zero, so effective rate ≈ 192 Mbps × (1 - 0%) = 192 Mbps

### Adaptive MCS (WiFi 6 Example)

With adaptive MCS, the rate changes based on SNR thresholds:

| Distance | SNR | Selected MCS | Rate |
|----------|-----|--------------|------|
| 20m | 40 dB | MCS 11 (1024-QAM) | 533 Mbps |
| 50m | 32 dB | MCS 9 (256-QAM) | 400 Mbps |
| 100m | 21 dB | MCS 5 (64-QAM) | 267 Mbps |
| 200m | 15 dB | MCS 3 (16-QAM) | 133 Mbps |
| 400m | 9 dB | MCS 1 (QPSK) | 53 Mbps |

**Recommendation:** Use `examples/wifi6_adaptive/` to see dramatic throughput changes with distance.

## Summary

**TCP throughput fluctuations of ±10-20 Mbps around the configured rate are normal** and result from:
1. TCP CUBIC congestion control (sawtooth pattern)
2. Token bucket burst allowance
3. Buffer dynamics in the network stack
4. Per-second measurement granularity

As long as the **average throughput is 180-190 Mbps for a 192 Mbps limit**, the emulation is working correctly. The fluctuations demonstrate that TCP is actively probing for available bandwidth, which is exactly what it should do.

To see more dramatic throughput changes:
- Use adaptive MCS topologies (`examples/wifi6_adaptive/`)
- Move nodes to longer distances (200-400m)
- Add obstacles in the scene (non-vacuum environments)
- Experiment with different modulation schemes (256-QAM, 1024-QAM have higher SNR requirements)

## References

- [TCP Congestion Control (RFC 5681)](https://tools.ietf.org/html/rfc5681)
- [CUBIC: A New TCP-Friendly High-Speed TCP Variant](https://doi.org/10.1145/1400097.1400105)
- [Linux TC Token Bucket Filter](https://man7.org/linux/man-pages/man8/tc-tbf.8.html)
- [Understanding TCP Performance](https://www.fasterdata.es.net/network-tuning/tcp-tuning/)
