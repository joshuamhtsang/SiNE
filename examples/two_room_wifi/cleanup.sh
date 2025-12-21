#!/bin/bash
# SiNE Cleanup Script
# Auto-generated - do not edit manually
# Topology: two-room-wifi
# Generated at: 2025-12-21T12:37:39.479220

set -e

echo "=== SiNE Cleanup: two-room-wifi ==="

# Stop and remove Docker containers
echo "Removing containers..."
docker stop "clab-two-room-wifi-server" 2>/dev/null || true
docker rm "clab-two-room-wifi-server" 2>/dev/null || true
docker stop "clab-two-room-wifi-client" 2>/dev/null || true
docker rm "clab-two-room-wifi-client" 2>/dev/null || true

# Call containerlab destroy if topology file exists
if [ -f "examples/two_room_wifi/.sine_clab_topology.yaml" ]; then
    echo "Destroying containerlab topology..."
    containerlab destroy -t "examples/two_room_wifi/.sine_clab_topology.yaml" --cleanup 2>/dev/null || true
fi

# Clean up temporary files
echo "Cleaning up temporary files..."
rm -f "examples/two_room_wifi/.sine_clab_topology.yaml" 2>/dev/null || true

echo "=== Cleanup complete ==="
