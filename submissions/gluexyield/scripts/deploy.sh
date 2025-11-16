#!/bin/bash

#################################################################
# Foundry Deployment Script for HyperYield Vault System
# 
# Usage:
# chmod +x scripts/deploy.sh
# ./scripts/deploy.sh
#################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Load environment variables
if [ -f .env ]; then
    set -a  # automatically export all variables
    source .env
    set +a  # stop automatically exporting
else
    echo -e "${RED}❌ .env file not found${NC}"
    echo "Please create a .env file with required variables (see .env.example)"
    exit 1
fi

# Check required environment variables
if [ -z "$RPC_URL" ] || [ -z "$PRIVATE_KEY" ]; then
    echo -e "${RED}❌ Missing required environment variables${NC}"
    echo "Please set RPC_URL and PRIVATE_KEY in .env"
    exit 1
fi

# Configuration
USDC="0xb88339CB7199b77E23DB6E890353E22632Ba630f"
VAULT_NAME="HyperYield Vault"
VAULT_SYMBOL="hyUSDC"

# GlueX Vaults and Underlying Tokens
VAULT_NAMES=("USDC" "USDT0" "HYPE" "USDH" "USDE")
VAULT_ADDRESSES=(
  "0xe25514992597786e07872e6C5517FE1906C0CAdD"
  "0xCdc3975df9D1cf054F44ED238Edfb708880292EA"
  "0x18c9705b3bAeBCfe2Fb1EC6AE1a4D7A3BE0E9dD1"
  "0x5D6C7f1d03a7b26b11BD3F9FbF42FE34ec86bEE2"
  "0x2C7AdEd7ca12d9F2F09f0A8Bb39F1234Dd23A0FF"
)
UNDERLYING_ADDRESSES=(
  "0xb88339CB7199b77E23DB6E890353E22632Ba630f"
  "0xB8CE59FC3717ada4C02eaDF9682A9e934F625ebb"
  "0x5555555555555555555555555555555555555555"
  "0x111111a1a0667d36bD57c0A9f569b98057111111"
  "0x5d3a1Ff2b6BAb83b63cd9AD0787074081a52ef34"
)

# Use BOT_ADDRESS from env or deployer address
BOT_ADDRESS=${BOT_ADDRESS:-$(cast wallet address --private-key $PRIVATE_KEY)}

echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}🚀 HyperYield Vault Deployment Script (Foundry)${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}Network:${NC} $RPC_URL"
echo -e "${YELLOW}Bot Address:${NC} $BOT_ADDRESS"
echo ""

# Step 1: Deploy GlueXOffchainOracle with explicit gas
echo -e "${BLUE}📍 Step 1: Deploying GlueXOffchainOracle...${NC}"

ORACLE_ADDRESS=$(forge create contracts/GlueXOffchainOracle.sol:GlueXOffchainOracle \
  --rpc-url "$RPC_URL" \
  --private-key "$PRIVATE_KEY" \
  --broadcast \
  2>&1 | grep "Deployed to:" | awk '{print $3}')

if [ -z "$ORACLE_ADDRESS" ]; then
    echo -e "${RED}❌ Failed to deploy Oracle${NC}"
    echo -e "${YELLOW}Trying with --json flag for better error output...${NC}"
    forge create contracts/GlueXOffchainOracle.sol:GlueXOffchainOracle \
      --rpc-url "$RPC_URL" \
      --private-key "$PRIVATE_KEY" \
      --legacy \
      --json
    exit 1
fi

echo -e "${GREEN}✅ Oracle deployed to: $ORACLE_ADDRESS${NC}"
echo ""

# Step 2: Deploy HyperYieldVault
echo -e "${BLUE}📍 Step 2: Deploying HyperYieldVault...${NC}"

VAULT_ADDRESS=$(forge create contracts/HyperYieldVault.sol:HyperYieldVault \
  --rpc-url "$RPC_URL" \
  --private-key "$PRIVATE_KEY" \
  --broadcast \
  --constructor-args "$USDC" "$VAULT_NAME" "$VAULT_SYMBOL" \
  2>&1 | grep "Deployed to:" | awk '{print $3}')

if [ -z "$VAULT_ADDRESS" ]; then
    echo -e "${RED}❌ Failed to deploy Vault${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Vault deployed to: $VAULT_ADDRESS${NC}"
echo -e "   Name: $VAULT_NAME"
echo -e "   Symbol: $VAULT_SYMBOL"
echo ""

# Step 3: Deploy VaultManagerMultiAsset
echo -e "${BLUE}📍 Step 3: Deploying VaultManagerMultiAsset...${NC}"

MANAGER_ADDRESS=$(forge create contracts/VaultManagerMultiAsset.sol:VaultManagerMultiAsset \
  --rpc-url "$RPC_URL" \
  --private-key "$PRIVATE_KEY" \
  --broadcast \
  --constructor-args "$VAULT_ADDRESS" "$USDC" "$ORACLE_ADDRESS" \
  2>&1 | grep "Deployed to:" | awk '{print $3}')

if [ -z "$MANAGER_ADDRESS" ]; then
    echo -e "${RED}❌ Failed to deploy Manager${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Manager deployed to: $MANAGER_ADDRESS${NC}"
echo ""

# Step 4: Configure HyperYieldVault
echo -e "${BLUE}📍 Step 4: Configuring HyperYieldVault...${NC}"
cast send "$VAULT_ADDRESS" "setVaultManager(address)" "$MANAGER_ADDRESS" \
  --rpc-url "$RPC_URL" \
  --private-key "$PRIVATE_KEY" > /dev/null

echo -e "${GREEN}✅ Vault manager set${NC}"
echo ""

# Step 5: Configure VaultManagerMultiAsset
echo -e "${BLUE}📍 Step 5: Configuring VaultManagerMultiAsset...${NC}"

# Authorize bot
echo -e "   Authorizing bot: $BOT_ADDRESS"
cast send "$MANAGER_ADDRESS" "authorizeBot(address)" "$BOT_ADDRESS" \
  --rpc-url "$RPC_URL" \
  --private-key "$PRIVATE_KEY" > /dev/null

echo -e "${GREEN}   ✅ Bot authorized${NC}"
echo ""

# Add strategies
echo -e "   Adding strategies:"
for i in 0 1 2 3 4; do
    TOKEN_NAME=${VAULT_NAMES[$i]}
    VAULT_ADDR=${VAULT_ADDRESSES[$i]}
    UNDERLYING_ADDR=${UNDERLYING_ADDRESSES[$i]}
    
    echo -e "   - Adding $TOKEN_NAME vault..."
    cast send "$MANAGER_ADDRESS" "addStrategy(address,address)" \
      "$VAULT_ADDR" "$UNDERLYING_ADDR" \
      --rpc-url "$RPC_URL" \
      --private-key "$PRIVATE_KEY" > /dev/null
    
    echo -e "${GREEN}     ✅ $TOKEN_NAME strategy added${NC}"
done

echo ""
echo -e "${GREEN}✅ All strategies configured${NC}"
echo ""

# Step 6: Save deployment info
echo -e "${BLUE}📍 Step 6: Saving deployment information...${NC}"

DEPLOYMENT_FILE="deployments.json"
cat > $DEPLOYMENT_FILE <<EOF
{
  "network": "hyperEVM",
  "rpcUrl": "$RPC_URL",
  "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "botAddress": "$BOT_ADDRESS",
  "contracts": {
    "oracle": "$ORACLE_ADDRESS",
    "vault": "$VAULT_ADDRESS",
    "manager": "$MANAGER_ADDRESS"
  },
  "config": {
    "baseAsset": "$USDC",
    "vaultName": "$VAULT_NAME",
    "vaultSymbol": "$VAULT_SYMBOL",
    "strategies": {
      "USDC": {
        "vault": "${VAULT_ADDRESSES[0]}",
        "underlying": "${UNDERLYING_ADDRESSES[0]}"
      },
      "USDT0": {
        "vault": "${VAULT_ADDRESSES[1]}",
        "underlying": "${UNDERLYING_ADDRESSES[1]}"
      },
      "HYPE": {
        "vault": "${VAULT_ADDRESSES[2]}",
        "underlying": "${UNDERLYING_ADDRESSES[2]}"
      },
      "USDH": {
        "vault": "${VAULT_ADDRESSES[3]}",
        "underlying": "${UNDERLYING_ADDRESSES[3]}"
      },
      "USDE": {
        "vault": "${VAULT_ADDRESSES[4]}",
        "underlying": "${UNDERLYING_ADDRESSES[4]}"
      }
    }
  }
}
EOF

echo -e "${GREEN}💾 Deployment data saved to: $DEPLOYMENT_FILE${NC}"
echo ""

# Create environment file for bot
BOT_ENV_FILE=".env.deployed"
cat > $BOT_ENV_FILE <<EOF
# Generated by deployment script - $(date -u +"%Y-%m-%dT%H:%M:%SZ")
RPC_URL=$RPC_URL
ORACLE_ADDRESS=$ORACLE_ADDRESS
VAULT_ADDRESS=$VAULT_ADDRESS
MANAGER_ADDRESS=$MANAGER_ADDRESS
BOT_ADDRESS=$BOT_ADDRESS
USDC_ADDRESS=$USDC
EOF

echo -e "${GREEN}💾 Bot environment saved to: $BOT_ENV_FILE${NC}"
echo ""

# Final summary
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}🎉 DEPLOYMENT COMPLETE!${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}📋 Deployed Contract Addresses:${NC}"
echo -e "   Oracle:  $ORACLE_ADDRESS"
echo -e "   Vault:   $VAULT_ADDRESS"
echo -e "   Manager: $MANAGER_ADDRESS"
echo ""
echo -e "${YELLOW}🔧 Configuration:${NC}"
echo -e "   Base Asset (USDC): $USDC"
echo -e "   Authorized Bot:    $BOT_ADDRESS"
echo -e "   Strategies:        5 GlueX vaults"
echo ""
echo -e "${YELLOW}🔗 Block Explorer Links:${NC}"
echo -e "   Oracle:  https://explorer.hyperliquid.xyz/address/$ORACLE_ADDRESS"
echo -e "   Vault:   https://explorer.hyperliquid.xyz/address/$VAULT_ADDRESS"
echo -e "   Manager: https://explorer.hyperliquid.xyz/address/$MANAGER_ADDRESS"
echo ""
echo -e "${YELLOW}📝 Next Steps:${NC}"
echo -e "   1. Update backend bot with deployed addresses (see $BOT_ENV_FILE)"
echo -e "   2. Configure bot to update oracle prices"
echo -e "   3. Fund the vault with initial deposits"
echo -e "   4. Start the backend bot for rebalancing"
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"