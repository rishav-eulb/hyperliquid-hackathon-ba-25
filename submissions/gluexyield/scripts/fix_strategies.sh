#!/bin/bash

# Fix VaultManager strategies to match constants.py
# This script removes incorrect vaults and adds the correct ones

set -e

# Load environment
source .env

# Contract addresses
VAULT_MANAGER="0xb920E976496Af7C585DD7e87a545B51a68e7FCa7"
RPC_URL="https://rpc.hyperliquid.xyz/evm"

# Base asset (USDC)
BASE_ASSET="0xb88339CB7199b77E23DB6E890353E22632Ba630f"

echo "=================================="
echo "Fixing VaultManager Strategies"
echo "=================================="
echo "Manager: $VAULT_MANAGER"
echo ""

# OLD (incorrect) vault addresses currently registered
OLD_HYPE="0x18c9705b3bAeBCfe2Fb1EC6AE1a4D7A3BE0E9dD1"
OLD_USDH="0x5D6C7f1d03a7b26b11BD3F9FbF42FE34ec86bEE2"
OLD_USDE="0x2C7AdEd7ca12d9F2F09f0A8Bb39F1234Dd23A0FF"

# CORRECT vault addresses from constants.py
CORRECT_HYPE="0x8f9291606862eef771a97e5b71e4b98fd1fa216a"
CORRECT_HYPE_TOKEN="0x5555555555555555555555555555555555555555"

CORRECT_USDH="0x9f75eac57d1c6f7248bd2aede58c95689f3827f7"
CORRECT_USDH_TOKEN="0x111111a1a0667d36bD57c0A9f569b98057111111"

CORRECT_USDE="0x63cf7ee583d9954febf649ad1c40c97a6493b1be"
CORRECT_USDE_TOKEN="0x5d3a1Ff2b6BAb83b63cd9AD0787074081a52ef34"

echo "Step 1: Removing old/incorrect vaults..."
echo ""

# Remove old HYPE vault
echo "Removing old HYPE vault ($OLD_HYPE)..."
cast send $VAULT_MANAGER \
  "removeStrategy(address)" \
  $OLD_HYPE \
  --rpc-url $RPC_URL \
  --private-key $PRIVATE_KEY \
  --gas-limit 200000

echo "✓ Removed old HYPE vault"
echo ""

# Remove old USDH vault
echo "Removing old USDH vault ($OLD_USDH)..."
cast send $VAULT_MANAGER \
  "removeStrategy(address)" \
  $OLD_USDH \
  --rpc-url $RPC_URL \
  --private-key $PRIVATE_KEY \
  --gas-limit 200000

echo "✓ Removed old USDH vault"
echo ""

# Remove old USDE vault
echo "Removing old USDE vault ($OLD_USDE)..."
cast send $VAULT_MANAGER \
  "removeStrategy(address)" \
  $OLD_USDE \
  --rpc-url $RPC_URL \
  --private-key $PRIVATE_KEY \
  --gas-limit 200000

echo "✓ Removed old USDE vault"
echo ""

echo "Step 2: Adding correct vaults from constants.py..."
echo ""

# Add correct HYPE vault
echo "Adding HYPE vault ($CORRECT_HYPE)..."
cast send $VAULT_MANAGER \
  "addStrategy(address,address)" \
  $CORRECT_HYPE \
  $CORRECT_HYPE_TOKEN \
  --rpc-url $RPC_URL \
  --private-key $PRIVATE_KEY \
  --gas-limit 200000

echo "✓ Added HYPE vault"
echo ""

# Add correct USDH vault
echo "Adding USDH vault ($CORRECT_USDH)..."
cast send $VAULT_MANAGER \
  "addStrategy(address,address)" \
  $CORRECT_USDH \
  $CORRECT_USDH_TOKEN \
  --rpc-url $RPC_URL \
  --private-key $PRIVATE_KEY \
  --gas-limit 200000

echo "✓ Added USDH vault"
echo ""

# Add correct USDE vault
echo "Adding USDE vault ($CORRECT_USDE)..."
cast send $VAULT_MANAGER \
  "addStrategy(address,address)" \
  $CORRECT_USDE \
  $CORRECT_USDE_TOKEN \
  --rpc-url $RPC_URL \
  --private-key $PRIVATE_KEY \
  --gas-limit 200000

echo "✓ Added USDE vault"
echo ""

echo "=================================="
echo "✓ All strategies updated!"
echo "=================================="
echo ""
echo "Current strategies:"
cast call $VAULT_MANAGER "getStrategies()(address[])" --rpc-url $RPC_URL

echo ""
echo "Strategies now match constants.py ✓"

