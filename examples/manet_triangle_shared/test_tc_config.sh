#!/bin/bash
# TC Configuration Verification Test for Shared Bridge Mode
#
# This script verifies that per-destination netem is correctly configured
# on all nodes in the shared bridge topology.

set -e

LAB_NAME="manet-triangle-shared"
NODES=("node1" "node2" "node3")
INTERFACE="eth1"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================"
echo "TC Configuration Verification Test"
echo "========================================"
echo ""

# Check if containers are running
echo "Checking containers..."
for node in "${NODES[@]}"; do
    container_name="clab-${LAB_NAME}-${node}"
    if ! docker ps --format '{{.Names}}' | grep -q "^${container_name}$"; then
        echo -e "${RED}✗ Container ${container_name} not found${NC}"
        echo "  Run: sudo \$(which uv) run sine deploy examples/manet_triangle_shared/network.yaml"
        exit 1
    fi
    echo -e "${GREEN}✓ Container ${container_name} is running${NC}"
done
echo ""

# Verify HTB qdisc on each node
echo "Verifying HTB qdisc configuration..."
for node in "${NODES[@]}"; do
    container_name="clab-${LAB_NAME}-${node}"

    # Check for HTB root qdisc
    if docker exec "$container_name" tc qdisc show dev "$INTERFACE" | grep -q "qdisc htb 1: root"; then
        echo -e "${GREEN}✓ ${node}: HTB root qdisc present${NC}"
    else
        echo -e "${RED}✗ ${node}: HTB root qdisc NOT found${NC}"
        exit 1
    fi

    # Check for default class 99
    if docker exec "$container_name" tc qdisc show dev "$INTERFACE" | grep -q "default 99"; then
        echo -e "${GREEN}✓ ${node}: Default class 99 configured${NC}"
    else
        echo -e "${RED}✗ ${node}: Default class 99 NOT found${NC}"
        exit 1
    fi
done
echo ""

# Verify HTB classes
echo "Verifying HTB classes..."
for node in "${NODES[@]}"; do
    container_name="clab-${LAB_NAME}-${node}"

    # Check for parent class 1:1
    if docker exec "$container_name" tc class show dev "$INTERFACE" | grep -q "class htb 1:1"; then
        echo -e "${GREEN}✓ ${node}: Parent class 1:1 present${NC}"
    else
        echo -e "${RED}✗ ${node}: Parent class 1:1 NOT found${NC}"
        exit 1
    fi

    # Check for default class 1:99
    if docker exec "$container_name" tc class show dev "$INTERFACE" | grep -q "class htb 1:99"; then
        echo -e "${GREEN}✓ ${node}: Default class 1:99 present${NC}"
    else
        echo -e "${RED}✗ ${node}: Default class 1:99 NOT found${NC}"
        exit 1
    fi

    # Count per-destination classes (should be N-1 for N nodes)
    num_dest_classes=$(docker exec "$container_name" tc class show dev "$INTERFACE" | grep -c "class htb 1:[1-9][0-9]" || true)
    # Subtract 1 for the default class 1:99
    num_dest_classes=$((num_dest_classes - 1))
    expected_classes=$((${#NODES[@]} - 1))

    if [ "$num_dest_classes" -eq "$expected_classes" ]; then
        echo -e "${GREEN}✓ ${node}: ${num_dest_classes} per-destination classes (expected ${expected_classes})${NC}"
    else
        echo -e "${RED}✗ ${node}: ${num_dest_classes} per-destination classes (expected ${expected_classes})${NC}"
        exit 1
    fi
done
echo ""

# Verify netem qdiscs
echo "Verifying netem qdiscs..."
for node in "${NODES[@]}"; do
    container_name="clab-${LAB_NAME}-${node}"

    # Count netem qdiscs (should be N for N nodes, including default)
    num_netem=$(docker exec "$container_name" tc qdisc show dev "$INTERFACE" | grep -c "qdisc netem" || true)
    expected_netem=${#NODES[@]}

    if [ "$num_netem" -eq "$expected_netem" ]; then
        echo -e "${GREEN}✓ ${node}: ${num_netem} netem qdiscs (expected ${expected_netem})${NC}"
    else
        echo -e "${RED}✗ ${node}: ${num_netem} netem qdiscs (expected ${expected_netem})${NC}"
        exit 1
    fi
done
echo ""

# Verify flower filters
echo "Verifying flower filters..."
for node in "${NODES[@]}"; do
    container_name="clab-${LAB_NAME}-${node}"

    # Count flower filters (should be N-1 for N nodes)
    num_filters=$(docker exec "$container_name" tc filter show dev "$INTERFACE" | grep -c "flower" || true)
    expected_filters=$((${#NODES[@]} - 1))

    if [ "$num_filters" -eq "$expected_filters" ]; then
        echo -e "${GREEN}✓ ${node}: ${num_filters} flower filters (expected ${expected_filters})${NC}"
    else
        echo -e "${RED}✗ ${node}: ${num_filters} flower filters (expected ${expected_filters})${NC}"
        exit 1
    fi

    # Verify dst_ip match in filters
    if docker exec "$container_name" tc filter show dev "$INTERFACE" | grep -q "dst_ip"; then
        echo -e "${GREEN}✓ ${node}: Flower filters use dst_ip matching${NC}"
    else
        echo -e "${RED}✗ ${node}: Flower filters missing dst_ip match${NC}"
        exit 1
    fi
done
echo ""

# Display detailed TC configuration for first node (as example)
echo "Detailed TC configuration for ${NODES[0]}:"
echo "=========================================="
container_name="clab-${LAB_NAME}-${NODES[0]}"

echo ""
echo "Qdiscs:"
docker exec "$container_name" tc qdisc show dev "$INTERFACE"

echo ""
echo "Classes:"
docker exec "$container_name" tc class show dev "$INTERFACE"

echo ""
echo "Filters:"
docker exec "$container_name" tc filter show dev "$INTERFACE"
echo ""

echo "========================================"
echo -e "${GREEN}All TC configuration tests passed!${NC}"
echo "========================================"
