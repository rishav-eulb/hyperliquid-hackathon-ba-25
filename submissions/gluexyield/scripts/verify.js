/**
 * Post-Deployment Verification Script
 * 
 * Verifies that all contracts are correctly deployed and configured
 * 
 * Usage:
 * npx hardhat run scripts/verify.js --network hyperEVM
 */

const hre = require("hardhat");
const fs = require("fs");
const path = require("path");

async function main() {
  console.log("🔍 Starting deployment verification...\n");

  // Load deployment data
  const deploymentFile = path.join(__dirname, "../deployments.json");
  
  if (!fs.existsSync(deploymentFile)) {
    console.error("❌ deployments.json not found. Run deploy.js first.");
    process.exit(1);
  }

  const deployment = JSON.parse(fs.readFileSync(deploymentFile, "utf8"));
  const { oracle, vault, manager } = deployment.contracts;

  console.log("📋 Checking deployed contracts:");
  console.log("   Oracle: ", oracle);
  console.log("   Vault:  ", vault);
  console.log("   Manager:", manager);
  console.log();

  const [signer] = await hre.ethers.getSigners();
  let allPassed = true;

  // ===== Test 1: Contract Code Exists =====
  console.log("Test 1: Checking contract code exists...");
  try {
    const oracleCode = await hre.ethers.provider.getCode(oracle);
    const vaultCode = await hre.ethers.provider.getCode(vault);
    const managerCode = await hre.ethers.provider.getCode(manager);

    if (oracleCode === "0x" || vaultCode === "0x" || managerCode === "0x") {
      console.log("❌ FAILED: One or more contracts have no code");
      allPassed = false;
    } else {
      console.log("✅ PASSED: All contracts have code deployed");
    }
  } catch (error) {
    console.log("❌ FAILED:", error.message);
    allPassed = false;
  }
  console.log();

  // ===== Test 2: Vault Configuration =====
  console.log("Test 2: Checking vault configuration...");
  try {
    const Vault = await hre.ethers.getContractAt("HyperYieldVault", vault);
    
    const asset = await Vault.asset();
    const vaultManager = await Vault.vaultManager();
    const name = await Vault.name();
    const symbol = await Vault.symbol();

    console.log("   Asset:", asset);
    console.log("   Manager:", vaultManager);
    console.log("   Name:", name);
    console.log("   Symbol:", symbol);

    if (vaultManager.toLowerCase() !== manager.toLowerCase()) {
      console.log("❌ FAILED: Vault manager not set correctly");
      allPassed = false;
    } else if (asset.toLowerCase() !== deployment.config.USDC.toLowerCase()) {
      console.log("❌ FAILED: Vault asset not set correctly");
      allPassed = false;
    } else {
      console.log("✅ PASSED: Vault configured correctly");
    }
  } catch (error) {
    console.log("❌ FAILED:", error.message);
    allPassed = false;
  }
  console.log();

  // ===== Test 3: Manager Configuration =====
  console.log("Test 3: Checking manager configuration...");
  try {
    const Manager = await hre.ethers.getContractAt("VaultManagerMultiAsset", manager);
    
    const hyperYieldVault = await Manager.hyperYieldVault();
    const baseAsset = await Manager.baseAsset();
    const priceOracle = await Manager.priceOracle();
    const strategies = await Manager.getStrategies();
    const botAddress = deployment.botAddress;
    const isAuthorized = await Manager.authorizedBots(botAddress);

    console.log("   Vault:", hyperYieldVault);
    console.log("   Base Asset:", baseAsset);
    console.log("   Oracle:", priceOracle);
    console.log("   Strategies:", strategies.length);
    console.log("   Bot authorized:", isAuthorized);

    if (hyperYieldVault.toLowerCase() !== vault.toLowerCase()) {
      console.log("❌ FAILED: Manager vault reference incorrect");
      allPassed = false;
    } else if (priceOracle.toLowerCase() !== oracle.toLowerCase()) {
      console.log("❌ FAILED: Manager oracle reference incorrect");
      allPassed = false;
    } else if (strategies.length !== 5) {
      console.log("❌ FAILED: Expected 5 strategies, got", strategies.length);
      allPassed = false;
    } else if (!isAuthorized) {
      console.log("❌ FAILED: Bot not authorized");
      allPassed = false;
    } else {
      console.log("✅ PASSED: Manager configured correctly");
    }
  } catch (error) {
    console.log("❌ FAILED:", error.message);
    allPassed = false;
  }
  console.log();

  // ===== Test 4: Oracle Configuration =====
  console.log("Test 4: Checking oracle configuration...");
  try {
    const Oracle = await hre.ethers.getContractAt("GlueXOffchainOracle", oracle);
    
    const owner = await Oracle.owner();
    const maxStaleness = await Oracle.maxStaleness();

    console.log("   Owner:", owner);
    console.log("   Max Staleness:", maxStaleness.toString(), "seconds");

    if (maxStaleness.toNumber() !== 3600) {
      console.log("⚠️  WARNING: Max staleness is not 1 hour (default)");
    }
    console.log("✅ PASSED: Oracle configured");
  } catch (error) {
    console.log("❌ FAILED:", error.message);
    allPassed = false;
  }
  console.log();

  // ===== Test 5: Strategies =====
  console.log("Test 5: Checking strategy details...");
  try {
    const Manager = await hre.ethers.getContractAt("VaultManagerMultiAsset", manager);
    const strategies = await Manager.getStrategies();

    for (let i = 0; i < strategies.length; i++) {
      const strategyAddr = strategies[i];
      const strategy = await Manager.strategies(strategyAddr);
      
      console.log(`   Strategy ${i + 1}:`);
      console.log(`      Vault: ${strategyAddr}`);
      console.log(`      Underlying: ${strategy.underlying}`);
      console.log(`      Active: ${strategy.active}`);

      if (!strategy.active) {
        console.log("⚠️  WARNING: Strategy is not active");
      }
    }
    console.log("✅ PASSED: All strategies configured");
  } catch (error) {
    console.log("❌ FAILED:", error.message);
    allPassed = false;
  }
  console.log();

  // ===== Test 6: Rebalancing Status =====
  console.log("Test 6: Checking rebalancing status...");
  try {
    const Manager = await hre.ethers.getContractAt("VaultManagerMultiAsset", manager);
    
    const canRebalance = await Manager.canRebalance();
    const isRebalancing = await Manager.isRebalancing();

    console.log("   Can rebalance:", canRebalance);
    console.log("   Is rebalancing:", isRebalancing);

    if (!canRebalance) {
      console.log("⚠️  WARNING: Cannot rebalance yet (cooldown may be active)");
    }
    if (isRebalancing) {
      console.log("⚠️  WARNING: Currently rebalancing");
    }
    console.log("✅ PASSED: Rebalancing status checked");
  } catch (error) {
    console.log("❌ FAILED:", error.message);
    allPassed = false;
  }
  console.log();

  // ===== Test 7: Initial State =====
  console.log("Test 7: Checking initial state...");
  try {
    const Vault = await hre.ethers.getContractAt("HyperYieldVault", vault);
    const Manager = await hre.ethers.getContractAt("VaultManagerMultiAsset", manager);
    
    const totalAssets = await Vault.totalAssets();
    const totalManaged = await Manager.getTotalManagedBaseAssets();

    console.log("   Vault total assets:", totalAssets.toString());
    console.log("   Manager total managed:", totalManaged.toString());

    if (totalAssets.toNumber() !== 0 || totalManaged.toNumber() !== 0) {
      console.log("⚠️  WARNING: Expected zero balances for fresh deployment");
    }
    console.log("✅ PASSED: Initial state is clean");
  } catch (error) {
    console.log("❌ FAILED:", error.message);
    allPassed = false;
  }
  console.log();

  // ===== Summary =====
  console.log("═".repeat(60));
  if (allPassed) {
    console.log("🎉 ALL TESTS PASSED!");
    console.log("═".repeat(60));
    console.log("\n✅ Deployment is valid and ready to use");
    console.log("\n📝 Next steps:");
    console.log("   1. Update backend bot with contract addresses");
    console.log("   2. Start bot to update oracle prices");
    console.log("   3. Make test deposits");
    console.log("   4. Monitor rebalancing");
  } else {
    console.log("❌ SOME TESTS FAILED");
    console.log("═".repeat(60));
    console.log("\n⚠️  Please review the failures above");
    console.log("   You may need to redeploy or fix configuration");
  }
  console.log();
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });

