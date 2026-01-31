#!/bin/bash
# Comprehensive Test Runner for Shared Bridge Mode
#
# This script runs all validation tests for the shared bridge implementation.

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "========================================"
echo "Shared Bridge Validation Test Suite"
echo "========================================"
echo ""

# Check if deployment is required
if [ "$1" = "--deploy" ]; then
    echo -e "${BLUE}Deploying shared bridge topology...${NC}"
    echo ""

    # Start channel server in background
    echo "Starting channel server..."
    uv run sine channel-server &
    CHANNEL_SERVER_PID=$!
    echo "Channel server PID: $CHANNEL_SERVER_PID"

    # Wait for channel server to start
    echo "Waiting for channel server to be ready..."
    sleep 3

    # Deploy topology
    echo "Deploying topology..."
    sudo "$(which uv)" run sine deploy "${SCRIPT_DIR}/network.yaml"

    echo ""
    echo -e "${GREEN}Deployment complete!${NC}"
    echo ""

    # Register cleanup on exit
    trap "echo 'Cleaning up...'; sudo $(which uv) run sine destroy ${SCRIPT_DIR}/network.yaml; kill $CHANNEL_SERVER_PID 2>/dev/null || true" EXIT
fi

# Run tests
echo "Running validation tests..."
echo ""

total_tests=0
passed_tests=0
failed_tests=0

# Test 1: TC Configuration
echo -e "${BLUE}Test 1: TC Configuration Verification${NC}"
echo "=========================================="
if bash "${SCRIPT_DIR}/test_tc_config.sh"; then
    echo ""
    echo -e "${GREEN}✓ TC Configuration test passed${NC}"
    ((passed_tests++))
else
    echo ""
    echo -e "${RED}✗ TC Configuration test failed${NC}"
    ((failed_tests++))
fi
((total_tests++))
echo ""
echo ""

# Test 2: Ping RTT
echo -e "${BLUE}Test 2: Ping RTT Validation${NC}"
echo "=========================================="
if bash "${SCRIPT_DIR}/test_ping_rtt.sh"; then
    echo ""
    echo -e "${GREEN}✓ Ping RTT test passed${NC}"
    ((passed_tests++))
else
    echo ""
    echo -e "${RED}✗ Ping RTT test failed${NC}"
    ((failed_tests++))
fi
((total_tests++))
echo ""
echo ""

# Test 3: Filter Statistics
echo -e "${BLUE}Test 3: Filter Statistics Verification${NC}"
echo "=========================================="
if bash "${SCRIPT_DIR}/test_filter_stats.sh"; then
    echo ""
    echo -e "${GREEN}✓ Filter Statistics test passed${NC}"
    ((passed_tests++))
else
    echo ""
    echo -e "${RED}✗ Filter Statistics test failed${NC}"
    ((failed_tests++))
fi
((total_tests++))
echo ""
echo ""

# Final summary
echo "========================================"
echo "Test Suite Summary"
echo "========================================"
echo "Total tests:  ${total_tests}"
echo -e "Passed:       ${GREEN}${passed_tests}${NC}"
if [ "$failed_tests" -gt 0 ]; then
    echo -e "Failed:       ${RED}${failed_tests}${NC}"
else
    echo -e "Failed:       ${failed_tests}"
fi
echo ""

if [ "$failed_tests" -eq 0 ]; then
    echo -e "${GREEN}=========================================${NC}"
    echo -e "${GREEN}All tests passed! ✓${NC}"
    echo -e "${GREEN}=========================================${NC}"
    exit 0
else
    echo -e "${RED}=========================================${NC}"
    echo -e "${RED}Some tests failed! ✗${NC}"
    echo -e "${RED}=========================================${NC}"
    exit 1
fi
