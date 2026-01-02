#!/bin/bash
# Check netem configuration on vacuum_20m containers
#
# This script verifies that netem (network emulation) is properly configured
# on the container interfaces. If netem is not applied, iperf3 will show
# 10+ Gbps instead of the expected ~192 Mbps wireless rate.
#
# Expected configuration for vacuum_20m example:
# - Rate limit: ~192 Mbps (80 MHz, 64-QAM, rate-1/2 LDPC)
# - Delay: ~0.07 ms (propagation delay for 20m)
# - Loss: ~0% (high SNR in free space)
#
# Usage:
#   ./examples/vacuum_20m/check_netem.sh

set -e

CONTAINER1="clab-vacuum-20m-node1"
CONTAINER2="clab-vacuum-20m-node2"
INTERFACE="eth1"

echo "=== Checking netem configuration for vacuum_20m ==="
echo ""

# Check if containers exist
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER1}$"; then
    echo "ERROR: Container $CONTAINER1 not found"
    echo "       Deploy first: sudo \$(which uv) run sine deploy examples/vacuum_20m/network.yaml"
    exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER2}$"; then
    echo "ERROR: Container $CONTAINER2 not found"
    exit 1
fi

echo "Containers found: $CONTAINER1, $CONTAINER2"
echo ""

# Function to check netem on a container
check_netem() {
    local container=$1
    local iface=$2

    echo "--- $container ($iface) ---"

    # Get container PID
    local pid=$(docker inspect --format '{{.State.Pid}}' "$container")

    if [ -z "$pid" ] || [ "$pid" == "0" ]; then
        echo "ERROR: Could not get PID for $container"
        return 1
    fi

    # Check qdisc configuration using nsenter
    echo "Qdisc configuration:"
    if sudo nsenter -t "$pid" -n tc qdisc show dev "$iface" 2>/dev/null; then
        # Extract key parameters
        local output=$(sudo nsenter -t "$pid" -n tc qdisc show dev "$iface" 2>/dev/null)

        # Check for netem
        if echo "$output" | grep -q "netem"; then
            echo ""
            echo "netem: CONFIGURED"

            # Extract delay
            if echo "$output" | grep -qoP 'delay \K[0-9.]+[mu]?s'; then
                local delay=$(echo "$output" | grep -oP 'delay \K[0-9.]+[mu]?s')
                echo "  Delay: $delay"
            fi

            # Extract loss
            if echo "$output" | grep -qoP 'loss \K[0-9.]+%'; then
                local loss=$(echo "$output" | grep -oP 'loss \K[0-9.]+%')
                echo "  Loss: $loss"
            fi
        else
            echo ""
            echo "netem: NOT CONFIGURED"
            echo "  WARNING: No netem found - did you deploy with sudo?"
        fi

        # Check for tbf (rate limiting)
        if echo "$output" | grep -q "tbf"; then
            echo ""
            echo "tbf (rate limit): CONFIGURED"

            # Extract rate
            if echo "$output" | grep -qoP 'rate \K[0-9.]+[KMG]?bit'; then
                local rate=$(echo "$output" | grep -oP 'rate \K[0-9.]+[KMG]?bit')
                echo "  Rate: $rate"
            fi
        else
            echo ""
            echo "tbf (rate limit): NOT CONFIGURED"
            echo "  WARNING: No rate limit - throughput will be unlimited"
        fi
    else
        echo "ERROR: Could not query qdisc (need sudo?)"
        return 1
    fi

    echo ""
}

# Check both containers
check_netem "$CONTAINER1" "$INTERFACE"
check_netem "$CONTAINER2" "$INTERFACE"

echo "=== Summary ==="
echo ""
echo "Expected for vacuum_20m (80 MHz, 64-QAM, rate-1/2 LDPC):"
echo "  - Rate: ~192 Mbit (may show as 192000Kbit)"
echo "  - Delay: ~0.07ms (propagation delay)"
echo "  - Loss: ~0% (high SNR)"
echo ""
echo "If netem is NOT configured:"
echo "  1. Destroy: uv run sine destroy examples/vacuum_20m/network.yaml"
echo "  2. Redeploy with sudo: sudo \$(which uv) run sine deploy examples/vacuum_20m/network.yaml"
echo ""
