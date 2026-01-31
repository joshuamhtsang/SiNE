#!/bin/bash
# Debug script to test deployment and capture all output

YAML_PATH="${1:-examples/sinr_tdma_fixed/network.yaml}"

echo "=== Testing deployment of: $YAML_PATH ==="
echo "=== Using uv at: $(which uv) ==="
echo ""

echo "=== Running deployment ==="
sudo $(which uv) run sine deploy "$YAML_PATH"
EXIT_CODE=$?

echo ""
echo "=== Exit code: $EXIT_CODE ==="
