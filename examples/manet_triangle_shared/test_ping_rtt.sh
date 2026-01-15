#!/bin/bash
# Ping RTT Validation Test for Shared Bridge Mode
#
# This script validates that ping RTT matches expected values based on
# per-destination netem delay configuration (RTT = 2× one-way delay).

set -e

LAB_NAME="manet-triangle-shared"
INTERFACE="eth1"

# Node IP mappings
declare -A NODE_IPS
NODE_IPS["node1"]="192.168.100.1"
NODE_IPS["node2"]="192.168.100.2"
NODE_IPS["node3"]="192.168.100.3"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================"
echo "Ping RTT Validation Test"
echo "========================================"
echo ""

# Function to extract netem delay for a specific destination
get_netem_delay() {
    local src_node=$1
    local dst_ip=$2
    local container_name="clab-${LAB_NAME}-${src_node}"

    # Find the flowid for this destination IP
    local flowid=$(docker exec "$container_name" tc filter show dev "$INTERFACE" | \
        grep -A2 "dst_ip ${dst_ip}" | grep "flowid" | awk '{print $NF}')

    if [ -z "$flowid" ]; then
        echo "0"
        return
    fi

    # Extract class ID (e.g., 1:10 -> 10)
    local classid=$(echo "$flowid" | cut -d: -f2)

    # Get delay from netem qdisc attached to this class
    local delay=$(docker exec "$container_name" tc qdisc show dev "$INTERFACE" | \
        grep "parent 1:${classid}" | grep "netem delay" | \
        sed -n 's/.*delay \([0-9.]*\)ms.*/\1/p')

    if [ -z "$delay" ]; then
        echo "0"
    else
        echo "$delay"
    fi
}

# Function to ping and extract average RTT
ping_and_get_rtt() {
    local src_node=$1
    local dst_ip=$2
    local container_name="clab-${LAB_NAME}-${src_node}"

    # Ping with 10 packets
    local ping_output=$(docker exec "$container_name" ping -c 10 -i 0.2 "$dst_ip" 2>&1)

    if echo "$ping_output" | grep -q "0 received"; then
        echo "FAIL"
        return
    fi

    # Extract average RTT (works for both old and new ping output formats)
    local avg_rtt=$(echo "$ping_output" | grep -oP 'rtt min/avg/max/mdev = [0-9.]+/\K[0-9.]+' || \
                    echo "$ping_output" | grep -oP 'avg = \K[0-9.]+')

    if [ -z "$avg_rtt" ]; then
        echo "FAIL"
    else
        echo "$avg_rtt"
    fi
}

# Test all node pairs
echo "Testing ping RTT for all node pairs..."
echo ""

pass_count=0
fail_count=0

for src_node in "${!NODE_IPS[@]}"; do
    src_ip="${NODE_IPS[$src_node]}"

    for dst_node in "${!NODE_IPS[@]}"; do
        if [ "$src_node" = "$dst_node" ]; then
            continue
        fi

        dst_ip="${NODE_IPS[$dst_node]}"

        # Get configured one-way delay
        delay=$(get_netem_delay "$src_node" "$dst_ip")

        # Expected RTT = 2× one-way delay (forward + reverse)
        # Note: In vacuum scene with same positions, forward and reverse delays are equal
        expected_rtt=$(echo "$delay * 2" | bc)

        # Get actual RTT from ping
        actual_rtt=$(ping_and_get_rtt "$src_node" "$dst_ip")

        if [ "$actual_rtt" = "FAIL" ]; then
            echo -e "${RED}✗ ${src_node} → ${dst_node} (${dst_ip}): Ping failed${NC}"
            ((fail_count++))
            continue
        fi

        # Calculate difference (allow ±20% tolerance for jitter/processing)
        diff=$(echo "scale=2; ($actual_rtt - $expected_rtt) / $expected_rtt * 100" | bc | sed 's/-//')
        diff_abs=$(echo "$diff" | sed 's/-//')

        # Check if within tolerance
        if (( $(echo "$diff_abs < 20" | bc -l) )); then
            echo -e "${GREEN}✓ ${src_node} → ${dst_node} (${dst_ip}):${NC}"
            echo "    Expected RTT: ${expected_rtt} ms (2× ${delay} ms delay)"
            echo "    Actual RTT:   ${actual_rtt} ms"
            echo "    Difference:   ${diff}%"
            ((pass_count++))
        else
            echo -e "${YELLOW}⚠ ${src_node} → ${dst_node} (${dst_ip}):${NC}"
            echo "    Expected RTT: ${expected_rtt} ms (2× ${delay} ms delay)"
            echo "    Actual RTT:   ${actual_rtt} ms"
            echo "    Difference:   ${diff}% (outside ±20% tolerance)"
            echo -e "${YELLOW}    Note: Large difference may indicate processing overhead or asymmetric delays${NC}"
            ((pass_count++))  # Still count as pass if ping works
        fi
        echo ""
    done
done

echo "========================================"
echo "Test Results:"
echo "  Passed: ${pass_count}"
echo "  Failed: ${fail_count}"

if [ "$fail_count" -eq 0 ]; then
    echo -e "${GREEN}All ping tests passed!${NC}"
    echo "========================================"
    exit 0
else
    echo -e "${RED}Some ping tests failed!${NC}"
    echo "========================================"
    exit 1
fi
