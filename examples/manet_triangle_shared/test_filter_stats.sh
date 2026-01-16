#!/bin/bash
# Filter Statistics Verification Test for Shared Bridge Mode
#
# This script generates traffic and verifies that flower filters are
# correctly classifying packets to their respective destinations.

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
echo "Filter Statistics Verification Test"
echo "========================================"
echo ""

# Function to get current filter packet count
get_filter_packet_count() {
    local node=$1
    local dst_ip=$2
    local container_name="clab-${LAB_NAME}-${node}"

    # Get filter stats for this destination (need more context lines to reach packet count)
    local stats=$(docker exec "$container_name" tc -s filter show dev "$INTERFACE" | \
        grep -A10 "dst_ip ${dst_ip}")

    # Extract packet count (look for "Sent X bytes Y pkt")
    local pkt_count=$(echo "$stats" | grep -oP 'Sent \d+ bytes \K\d+(?= pkt)' | head -1)

    if [ -z "$pkt_count" ]; then
        echo "0"
    else
        echo "$pkt_count"
    fi
}

# Function to get qdisc packet count for a specific class
get_qdisc_packet_count() {
    local node=$1
    local dst_ip=$2
    local container_name="clab-${LAB_NAME}-${node}"

    # Find the classid for this destination IP (it's on the line with "handle")
    local flowid=$(docker exec "$container_name" tc filter show dev "$INTERFACE" | \
        grep -B2 "dst_ip ${dst_ip}" | grep "classid" | grep -oP 'classid \K\S+' | head -1)

    if [ -z "$flowid" ]; then
        echo "0"
        return
    fi

    # Extract class ID (e.g., 1:10 -> 10)
    local classid=$(echo "$flowid" | cut -d: -f2)

    # Get packet count from qdisc attached to this class
    local stats=$(docker exec "$container_name" tc -s qdisc show dev "$INTERFACE" | \
        grep -A2 "parent 1:${classid}")

    local pkt_count=$(echo "$stats" | grep -oP 'Sent \d+ bytes \K\d+(?= pkt)' | head -1)

    if [ -z "$pkt_count" ]; then
        echo "0"
    else
        echo "$pkt_count"
    fi
}

# Generate traffic between all node pairs
echo "Generating test traffic (100 pings per pair)..."
echo ""

for src_node in "${!NODE_IPS[@]}"; do
    for dst_node in "${!NODE_IPS[@]}"; do
        if [ "$src_node" = "$dst_node" ]; then
            continue
        fi

        dst_ip="${NODE_IPS[$dst_node]}"
        container_name="clab-${LAB_NAME}-${src_node}"

        echo -n "  ${src_node} → ${dst_node} (${dst_ip}): "

        # Send 100 pings with small interval
        if docker exec "$container_name" ping -c 100 -i 0.01 -q "$dst_ip" &>/dev/null; then
            echo -e "${GREEN}100 packets sent${NC}"
        else
            echo -e "${RED}Failed${NC}"
        fi
    done
done

echo ""
echo "Verifying filter statistics..."
echo ""

pass_count=0
fail_count=0

for src_node in "${!NODE_IPS[@]}"; do
    for dst_node in "${!NODE_IPS[@]}"; do
        if [ "$src_node" = "$dst_node" ]; then
            continue
        fi

        dst_ip="${NODE_IPS[$dst_node]}"

        # Get filter packet count (should match sent packets)
        filter_count=$(get_filter_packet_count "$src_node" "$dst_ip")

        # Get qdisc packet count
        qdisc_count=$(get_qdisc_packet_count "$src_node" "$dst_ip")

        echo "${src_node} → ${dst_node} (${dst_ip}):"
        echo "  Filter matched: ${filter_count} packets"
        echo "  Qdisc processed: ${qdisc_count} packets"

        # Check if filter matched packets
        if [ "$filter_count" -gt 0 ]; then
            echo -e "  ${GREEN}✓ Filter is classifying packets${NC}"
            ((pass_count++))
        else
            echo -e "  ${RED}✗ Filter matched 0 packets${NC}"
            ((fail_count++))
        fi

        # Check if qdisc processed packets
        if [ "$qdisc_count" -gt 0 ]; then
            echo -e "  ${GREEN}✓ Qdisc is processing packets${NC}"
        else
            echo -e "  ${YELLOW}⚠ Qdisc processed 0 packets (may indicate issue)${NC}"
        fi

        echo ""
    done
done

# Show detailed stats for first node
echo "========================================"
echo "Detailed Filter Statistics for node1:"
echo "========================================"
container_name="clab-${LAB_NAME}-node1"
docker exec "$container_name" tc -s filter show dev "$INTERFACE"
echo ""

echo "========================================"
echo "Detailed Qdisc Statistics for node1:"
echo "========================================"
docker exec "$container_name" tc -s qdisc show dev "$INTERFACE"
echo ""

echo "========================================"
echo "Test Results:"
echo "  Passed: ${pass_count}"
echo "  Failed: ${fail_count}"

if [ "$fail_count" -eq 0 ]; then
    echo -e "${GREEN}All filter statistics tests passed!${NC}"
    echo "========================================"
    exit 0
else
    echo -e "${RED}Some filter statistics tests failed!${NC}"
    echo "========================================"
    exit 1
fi
