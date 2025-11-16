#!/bin/bash
# Run all test suites for the GlueX bot

set -e

echo "========================================"
echo "GlueX Bot Test Suite Runner"
echo "========================================"
echo ""

# Get the directory of this script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Check for .env file
if [ ! -f "$DIR/../../.env" ]; then
    echo "WARNING: .env file not found"
    echo "Create one from env.example and add your GLUEX_API_KEY"
    echo ""
fi

# Detect python command
if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    PYTHON=python
else
    echo "ERROR: Python not found"
    exit 1
fi

echo "Using: $PYTHON"
echo ""

# Test 1: Vault Metrics Engine
echo "========================================"
echo "TEST 1: Vault Metrics Engine"
echo "========================================"
$PYTHON "$DIR/test_vault_metrics_engine.py"
echo ""

# Test 2: Portfolio Optimizer
echo "========================================"
echo "TEST 2: Portfolio Optimizer"
echo "========================================"
$PYTHON "$DIR/test_portfolio_optimizer.py"
echo ""

# Test 3: Rebalance Planner
echo "========================================"
echo "TEST 3: Rebalance Planner"
echo "========================================"
$PYTHON "$DIR/test_rebalance_planner.py"
echo ""

echo "========================================"
echo "ALL TEST SUITES COMPLETED"
echo "========================================"

