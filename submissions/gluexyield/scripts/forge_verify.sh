#!/bin/bash

#################################################################
# Forge Contract Verification Script
# 
# Prerequisites:
# 1. Contracts must be deployed (run deploy.sh first)
# 2. Block explorer API must be available for HyperEVM
# 3. Set ETHERSCAN_API_KEY in .env if required
#
# Usage:
# chmod +x scripts/forge_verify.sh
# ./scripts/forge_verify.sh
#################################################################

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Load environment variables
if [ -f .env ]; then
    set -a
    source .env
    set +a
else
    echo -e "${RED}❌ .env file not found${NC}"
    exit 1
fi

# Load deployment data
DEPLOYMENT_FILE="deployments.json"
if [ ! -f "$DEPLOYMENT_FILE" ]; then
    echo -e "${RED}❌ deployments.json not found. Run deploy.sh first.${NC}"
    exit 1
fi

# Extract addresses from deployment file
ORACLE_ADDRESS=$(jq -r '.contracts.oracle' $DEPLOYMENT_FILE)
VAULT_ADDRESS=$(jq -r '.contracts.vault' $DEPLOYMENT_FILE)
MANAGER_ADDRESS=$(jq -r '.contracts.manager' $DEPLOYMENT_FILE)
USDC=$(jq -r '.config.baseAsset' $DEPLOYMENT_FILE)
VAULT_NAME=$(jq -r '.config.vaultName' $DEPLOYMENT_FILE)
VAULT_SYMBOL=$(jq -r '.config.vaultSymbol' $DEPLOYMENT_FILE)

echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}🔍 Forge Contract Verification Script${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}Contracts to verify:${NC}"
echo -e "   Oracle:  $ORACLE_ADDRESS"
echo -e "   Vault:   $VAULT_ADDRESS"
echo -e "   Manager: $MANAGER_ADDRESS"
echo ""

# Check if etherscan API key is set (may not be needed for all explorers)
if [ -z "$ETHERSCAN_API_KEY" ]; then
    echo -e "${YELLOW}⚠️  ETHERSCAN_API_KEY not set in .env${NC}"
    echo -e "${YELLOW}   Verification may fail if the explorer requires an API key${NC}"
    echo ""
fi

# Step 1: Verify GlueXOffchainOracle
echo -e "${BLUE}📍 Step 1: Verifying GlueXOffchainOracle...${NC}"
echo -e "${YELLOW}Command:${NC}"
echo "forge verify-contract \\"
echo "  $ORACLE_ADDRESS \\"
echo "  contracts/GlueXOffchainOracle.sol:GlueXOffchainOracle \\"
echo "  --rpc-url \$RPC_URL \\"
echo "  --etherscan-api-key \$ETHERSCAN_API_KEY \\"
echo "  --watch"
echo ""

forge verify-contract \
  $ORACLE_ADDRESS \
  contracts/GlueXOffchainOracle.sol:GlueXOffchainOracle \
  --rpc-url "$RPC_URL" \
  --etherscan-api-key "${ETHERSCAN_API_KEY:-none}" \
  --watch || echo -e "${YELLOW}⚠️  Oracle verification failed or already verified${NC}"

echo ""

# Step 2: Verify HyperYieldVault
echo -e "${BLUE}📍 Step 2: Verifying HyperYieldVault...${NC}"
echo -e "${YELLOW}Constructor args:${NC}"
echo "  - USDC: $USDC"
echo "  - Name: $VAULT_NAME"
echo "  - Symbol: $VAULT_SYMBOL"
echo ""
echo -e "${YELLOW}Command:${NC}"
echo "forge verify-contract \\"
echo "  $VAULT_ADDRESS \\"
echo "  contracts/HyperYieldVault.sol:HyperYieldVault \\"
echo "  --rpc-url \$RPC_URL \\"
echo "  --etherscan-api-key \$ETHERSCAN_API_KEY \\"
echo "  --constructor-args \$(cast abi-encode \"constructor(address,string,string)\" \"$USDC\" \"$VAULT_NAME\" \"$VAULT_SYMBOL\") \\"
echo "  --watch"
echo ""

VAULT_CONSTRUCTOR_ARGS=$(cast abi-encode "constructor(address,string,string)" "$USDC" "$VAULT_NAME" "$VAULT_SYMBOL")

forge verify-contract \
  $VAULT_ADDRESS \
  contracts/HyperYieldVault.sol:HyperYieldVault \
  --rpc-url "$RPC_URL" \
  --etherscan-api-key "${ETHERSCAN_API_KEY:-none}" \
  --constructor-args "$VAULT_CONSTRUCTOR_ARGS" \
  --watch || echo -e "${YELLOW}⚠️  Vault verification failed or already verified${NC}"

echo ""

# Step 3: Verify VaultManagerMultiAsset
echo -e "${BLUE}📍 Step 3: Verifying VaultManagerMultiAsset...${NC}"
echo -e "${YELLOW}Constructor args:${NC}"
echo "  - Vault: $VAULT_ADDRESS"
echo "  - Base Asset (USDC): $USDC"
echo "  - Oracle: $ORACLE_ADDRESS"
echo ""
echo -e "${YELLOW}Command:${NC}"
echo "forge verify-contract \\"
echo "  $MANAGER_ADDRESS \\"
echo "  contracts/VaultManagerMultiAsset.sol:VaultManagerMultiAsset \\"
echo "  --rpc-url \$RPC_URL \\"
echo "  --etherscan-api-key \$ETHERSCAN_API_KEY \\"
echo "  --constructor-args \$(cast abi-encode \"constructor(address,address,address)\" \"$VAULT_ADDRESS\" \"$USDC\" \"$ORACLE_ADDRESS\") \\"
echo "  --watch"
echo ""

MANAGER_CONSTRUCTOR_ARGS=$(cast abi-encode "constructor(address,address,address)" "$VAULT_ADDRESS" "$USDC" "$ORACLE_ADDRESS")

forge verify-contract \
  $MANAGER_ADDRESS \
  contracts/VaultManagerMultiAsset.sol:VaultManagerMultiAsset \
  --rpc-url "$RPC_URL" \
  --etherscan-api-key "${ETHERSCAN_API_KEY:-none}" \
  --constructor-args "$MANAGER_CONSTRUCTOR_ARGS" \
  --watch || echo -e "${YELLOW}⚠️  Manager verification failed or already verified${NC}"

echo ""

# Summary
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ Verification process complete!${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}📋 Verified Contracts:${NC}"
echo -e "   Oracle:  https://explorer.hyperliquid.xyz/address/$ORACLE_ADDRESS"
echo -e "   Vault:   https://explorer.hyperliquid.xyz/address/$VAULT_ADDRESS"
echo -e "   Manager: https://explorer.hyperliquid.xyz/address/$MANAGER_ADDRESS"
echo ""
echo -e "${YELLOW}💡 Note:${NC}"
echo -e "   If verification failed, the contract may already be verified,"
echo -e "   or the block explorer may not support verification yet."
echo -e "   Check the explorer links above to confirm verification status."
echo ""

