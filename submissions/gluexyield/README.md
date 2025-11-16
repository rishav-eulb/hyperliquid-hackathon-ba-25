---

# **Command Line Guide: Deployment to Bot Operations**

🎥 **Demo Video:**
**[Watch on Loom](https://loom.com/share/e115472886834dcdadd14d5b556525f9)**

---

This guide provides **complete, step-by-step command-line instructions** for:

* Deploying smart contracts
* Running the **GlueX Optimization Bot**
* Managing rebalancing and operational workflows

Follow this document to ensure a smooth deployment from development to production.

---

## Prerequisites

### 1. Install Node.js and Foundry

```bash
# Install Node.js (if not installed)
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Install Foundry (for smart contract deployment)
curl -L https://foundry.paradigm.xyz | bash
foundryup
```

### 2. Install Python 3.8+

```bash
# Check Python version
python3 --version

# Install pip if needed
sudo apt-get install python3-pip
```

### 3. Install Project Dependencies

```bash
# Navigate to project root
cd /Users/rj39/Desktop/NexusNetwork/GLUEX/hackathon

# Install Node.js dependencies
npm install

# Install Python dependencies
cd backend
pip install -r requirements.txt
cd ..
```

---

## Part 1: Environment Setup

### Step 1: Create Environment File

```bash
# Copy example environment file
cp env.example .env

# Edit the environment file
nano .env
```

### Step 2: Configure Required Variables

Edit `.env` with your values:

```bash
# Network Configuration
RPC_URL=https://api.hyperliquid-testnet.xyz/evm

# Your private key (with 0x prefix)
PRIVATE_KEY=0xyour_private_key_here

# Bot private key (can be same as PRIVATE_KEY or different)
BOT_PRIVATE_KEY=0xyour_bot_private_key_here

# GlueX API Key
GLUEX_API_KEY=your_gluex_api_key_here

# Base Asset (USDC on HyperEVM)
BASE_ASSET_ADDRESS=0xb88339CB7199b77E23DB6E890353E22632Ba630f
```

**Important**: Save and close the file (Ctrl+X, then Y, then Enter in nano)

---

## Part 2: Deploy Smart Contracts

### Step 1: Make Deployment Script Executable

```bash
chmod +x scripts/deploy.sh
```

### Step 2: Run Deployment

```bash
# Deploy all contracts (Oracle, Vault, Manager)
./scripts/deploy.sh
```

**Expected Output:**
```
🚀 HyperYield Vault Deployment Script (Foundry)
═══════════════════════════════════════════════════════
✅ Oracle deployed to: 0x...
✅ Vault deployed to: 0x...
✅ Manager deployed to: 0x...
✅ All strategies configured
💾 Deployment data saved to: deployments.json
💾 Bot environment saved to: .env.deployed
```

### Step 3: Update Environment with Deployed Addresses

```bash
# The script creates .env.deployed with contract addresses
# Merge these into your .env file

cat .env.deployed >> .env
```

Or manually update `.env`:

```bash
nano .env
```

Add the deployed addresses:
```bash
ORACLE_ADDRESS=0x... # From deployment output
VAULT_ADDRESS=0x...  # From deployment output
MANAGER_ADDRESS=0x... # From deployment output
```

---

## Part 3: Verify Deployment (Optional)

### Check Contract Deployment

```bash
# Check Oracle
cast call $ORACLE_ADDRESS "owner()" --rpc-url $RPC_URL

# Check Vault
cast call $VAULT_ADDRESS "name()" --rpc-url $RPC_URL

# Check Manager is set on Vault
cast call $VAULT_ADDRESS "vaultManager()" --rpc-url $RPC_URL

# Check bot is authorized
cast call $MANAGER_ADDRESS "isAuthorizedBot(address)" $BOT_ADDRESS --rpc-url $RPC_URL
```

### View Deployment Details

```bash
# View saved deployment info
cat deployments.json | jq
```

---

## Part 4: Configure Bot Environment

### Step 1: Get GlueX Router Address

The GlueX Router address should be obtained from GlueX API or documentation. Update your `.env`:

```bash
# Add to .env
GLUEX_ROUTER_ADDRESS=0x... # From GlueX documentation
```

### Step 2: Verify All Required Environment Variables

```bash
# Check all required variables are set
grep -E "^(RPC_URL|PRIVATE_KEY|BOT_PRIVATE_KEY|GLUEX_API_KEY|ORACLE_ADDRESS|VAULT_ADDRESS|MANAGER_ADDRESS|BASE_ASSET_ADDRESS|GLUEX_ROUTER_ADDRESS)=" .env
```

---

## Part 5: Run the Bot

### Option 1: Basic Run (Default Settings)

```bash
cd backend

python3 -m backend.gluex_bot \
  --vault-manager $MANAGER_ADDRESS \
  --hyperyield-vault $VAULT_ADDRESS \
  --base-asset $BASE_ASSET_ADDRESS \
  --oracle $ORACLE_ADDRESS \
  --router $GLUEX_ROUTER_ADDRESS
```

### Option 2: Run with Custom Intervals

```bash
python3 -m backend.gluex_bot \
  --vault-manager $MANAGER_ADDRESS \
  --hyperyield-vault $VAULT_ADDRESS \
  --base-asset $BASE_ASSET_ADDRESS \
  --oracle $ORACLE_ADDRESS \
  --router $GLUEX_ROUTER_ADDRESS \
  --oracle-interval 10 \
  --optimization-interval 60
```

### Option 3: Run in Test Mode (No Rebalancing)

```bash
python3 -m backend.gluex_bot \
  --vault-manager $MANAGER_ADDRESS \
  --hyperyield-vault $VAULT_ADDRESS \
  --base-asset $BASE_ASSET_ADDRESS \
  --oracle $ORACLE_ADDRESS \
  --router $GLUEX_ROUTER_ADDRESS \
  --disable-rebalancing
```

### Option 4: Using Environment Variables

```bash
# Load environment variables
source .env

# Run with env vars
python3 -m backend.gluex_bot \
  --vault-manager $MANAGER_ADDRESS \
  --hyperyield-vault $VAULT_ADDRESS \
  --base-asset $BASE_ASSET_ADDRESS \
  --oracle $ORACLE_ADDRESS \
  --router $GLUEX_ROUTER_ADDRESS
```

### Option 5: Run in Background

```bash
# Run bot in background with nohup
nohup python3 -m backend.gluex_bot \
  --vault-manager $MANAGER_ADDRESS \
  --hyperyield-vault $VAULT_ADDRESS \
  --base-asset $BASE_ASSET_ADDRESS \
  --oracle $ORACLE_ADDRESS \
  --router $GLUEX_ROUTER_ADDRESS \
  > ../logs/bot.log 2>&1 &

# Save the process ID
echo $! > bot.pid

# View logs
tail -f ../logs/bot.log
```

---

## Part 6: Monitor the Bot

### Check Bot Status

```bash
# View real-time logs
tail -f ../logs/bot.log

# Check if bot is running
ps aux | grep gluex_bot

# View recent bot activity
tail -n 100 ../logs/bot.log
```

### Stop the Bot

```bash
# If running in foreground: Ctrl+C

# If running in background:
kill $(cat bot.pid)
```

### Check Bot Balance

```bash
# Check bot wallet ETH balance (for gas)
cast balance $BOT_ADDRESS --rpc-url $RPC_URL

# Check bot USDC balance
cast call $BASE_ASSET_ADDRESS "balanceOf(address)" $BOT_ADDRESS --rpc-url $RPC_URL
```

---

## Part 7: Production Deployment with Systemd

### Step 1: Create Systemd Service File

```bash
sudo nano /etc/systemd/system/gluex-bot.service
```

Add the following content:

```ini
[Unit]
Description=GlueX Portfolio Optimization Bot
After=network.target

[Service]
Type=simple
User=yourusername
WorkingDirectory=/Users/rj39/Desktop/NexusNetwork/GLUEX/hackathon
Environment=PYTHONPATH=/Users/rj39/Desktop/NexusNetwork/GLUEX/hackathon
EnvironmentFile=/Users/rj39/Desktop/NexusNetwork/GLUEX/hackathon/.env
ExecStart=/usr/bin/python3 -m backend.gluex_bot \
  --vault-manager ${MANAGER_ADDRESS} \
  --hyperyield-vault ${VAULT_ADDRESS} \
  --base-asset ${BASE_ASSET_ADDRESS} \
  --oracle ${ORACLE_ADDRESS} \
  --router ${GLUEX_ROUTER_ADDRESS}
Restart=always
RestartSec=10
StandardOutput=append:/Users/rj39/Desktop/NexusNetwork/GLUEX/hackathon/logs/bot.log
StandardError=append:/Users/rj39/Desktop/NexusNetwork/GLUEX/hackathon/logs/bot-error.log

[Install]
WantedBy=multi-user.target
```

### Step 2: Enable and Start Service

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable gluex-bot

# Start the service
sudo systemctl start gluex-bot

# Check status
sudo systemctl status gluex-bot
```

### Step 3: Monitor Service Logs

```bash
# View live logs
sudo journalctl -u gluex-bot -f

# View recent logs
sudo journalctl -u gluex-bot -n 100

# View logs since boot
sudo journalctl -u gluex-bot -b
```

### Step 4: Service Management

```bash
# Stop the service
sudo systemctl stop gluex-bot

# Restart the service
sudo systemctl restart gluex-bot

# Disable service
sudo systemctl disable gluex-bot

# View service status
sudo systemctl status gluex-bot
```

---

## Part 8: Testing & Debugging

### Test Database Setup

```bash
cd backend/db

# Run database migrations
alembic upgrade head

# Collect initial vault data
python3 collect_vault_data.py
```

### Run Individual Tests

```bash
cd backend/tests

# Test portfolio optimizer
python3 test_portfolio_optimizer.py

# Test rebalance planner
python3 test_rebalance_planner.py

# Test vault metrics engine
python3 test_vault_metrics_engine.py

# Run all tests
bash run_all_tests.sh
```

### Debug Mode

```bash
# Set debug logging level
export LOG_LEVEL=DEBUG

# Run bot with verbose output
python3 -m backend.gluex_bot \
  --vault-manager $MANAGER_ADDRESS \
  --hyperyield-vault $VAULT_ADDRESS \
  --base-asset $BASE_ASSET_ADDRESS \
  --oracle $ORACLE_ADDRESS \
  --router $GLUEX_ROUTER_ADDRESS
```

### Manual Oracle Update

```bash
# Run oracle updater script once
cd scripts
python3 price_oracle_updater.py
```

### Simulate Rebalance

```bash
# Dry run rebalance without executing
cd scripts
python3 simulate_rebalance.py
```

---

## Quick Reference: Common Commands

### Deployment
```bash
# Deploy everything
./scripts/deploy.sh

# View deployment
cat deployments.json | jq
```

### Bot Operations
```bash
# Start bot (foreground)
python3 -m backend.gluex_bot --vault-manager $MANAGER_ADDRESS --hyperyield-vault $VAULT_ADDRESS --base-asset $BASE_ASSET_ADDRESS --oracle $ORACLE_ADDRESS --router $GLUEX_ROUTER_ADDRESS

# Start bot (background)
nohup python3 -m backend.gluex_bot --vault-manager $MANAGER_ADDRESS --hyperyield-vault $VAULT_ADDRESS --base-asset $BASE_ASSET_ADDRESS --oracle $ORACLE_ADDRESS --router $GLUEX_ROUTER_ADDRESS > logs/bot.log 2>&1 &

# Stop bot
pkill -f gluex_bot

# View logs
tail -f logs/bot.log
```

### Systemd Service
```bash
# Start/stop/restart
sudo systemctl start gluex-bot
sudo systemctl stop gluex-bot
sudo systemctl restart gluex-bot

# View logs
sudo journalctl -u gluex-bot -f
```

### Monitoring
```bash
# Check bot is running
ps aux | grep gluex_bot

# Check bot balance
cast balance $BOT_ADDRESS --rpc-url $RPC_URL

# Check vault state
cast call $VAULT_ADDRESS "totalAssets()" --rpc-url $RPC_URL

# Check last rebalance time
cast call $MANAGER_ADDRESS "lastRebalanceTime()" --rpc-url $RPC_URL
```

---

## Troubleshooting

### Issue: "API key and private key required"
```bash
# Verify environment variables are set
echo $GLUEX_API_KEY
echo $BOT_PRIVATE_KEY

# If empty, load .env
source .env
```

### Issue: "Contract not found"
```bash
# Verify addresses are correct
cast code $MANAGER_ADDRESS --rpc-url $RPC_URL
cast code $VAULT_ADDRESS --rpc-url $RPC_URL
cast code $ORACLE_ADDRESS --rpc-url $RPC_URL
```

### Issue: "Insufficient funds for gas"
```bash
# Check bot balance
cast balance $BOT_ADDRESS --rpc-url $RPC_URL

# Send gas to bot wallet
cast send $BOT_ADDRESS --value 0.1ether --rpc-url $RPC_URL --private-key $PRIVATE_KEY
```

### Issue: "Bot not authorized"
```bash
# Check authorization
cast call $MANAGER_ADDRESS "isAuthorizedBot(address)" $BOT_ADDRESS --rpc-url $RPC_URL

# Authorize bot (if not authorized)
cast send $MANAGER_ADDRESS "authorizeBot(address)" $BOT_ADDRESS --rpc-url $RPC_URL --private-key $PRIVATE_KEY
```

### Issue: "Rebalance cooldown"
```bash
# Check if rebalancing is allowed
cast call $MANAGER_ADDRESS "canRebalance()" --rpc-url $RPC_URL

# Check last rebalance time
cast call $MANAGER_ADDRESS "lastRebalanceTime()" --rpc-url $RPC_URL

# Wait 1 hour (3600 seconds) after last rebalance
```

---

## Environment Variables Reference

### Required
- `RPC_URL` - HyperEVM RPC endpoint
- `PRIVATE_KEY` - Deployer private key
- `BOT_PRIVATE_KEY` - Bot private key
- `GLUEX_API_KEY` - GlueX API key
- `ORACLE_ADDRESS` - Oracle contract address
- `VAULT_ADDRESS` - HyperYield Vault address
- `MANAGER_ADDRESS` - Vault Manager address
- `BASE_ASSET_ADDRESS` - USDC address
- `GLUEX_ROUTER_ADDRESS` - GlueX Router address

### Optional (with defaults)
- `OPTIMIZATION_INTERVAL=30` - Minutes between optimization cycles
- `ORACLE_UPDATE_INTERVAL=5` - Minutes between oracle updates
- `MAX_VAULTS=3` - Maximum vaults in portfolio
- `MIN_TVL=100000` - Minimum TVL threshold
- `DEPLOY_FRACTION=0.9` - Fraction of idle to deploy
- `REBALANCING_ENABLED=true` - Enable/disable rebalancing
- `LOG_LEVEL=INFO` - Logging level (DEBUG, INFO, WARNING, ERROR)

---

## Summary: Complete Workflow

```bash
# 1. Setup
cd /Users/rj39/Desktop/NexusNetwork/GLUEX/hackathon
cp env.example .env
nano .env  # Edit with your values

# 2. Deploy contracts
chmod +x scripts/deploy.sh
./scripts/deploy.sh
cat .env.deployed >> .env

# 3. Run bot
cd backend
python3 -m backend.gluex_bot \
  --vault-manager $MANAGER_ADDRESS \
  --hyperyield-vault $VAULT_ADDRESS \
  --base-asset $BASE_ASSET_ADDRESS \
  --oracle $ORACLE_ADDRESS \
  --router $GLUEX_ROUTER_ADDRESS

# 4. Monitor
tail -f logs/bot.log
```

---

**🎉 You're all set!** The bot will now:
- Update oracle prices every 5 minutes
- Run portfolio optimization every 30 minutes
- Execute rebalances when beneficial (drift >10% or Sharpe improvement >5%)
- Log all activities to `logs/bot.log`

