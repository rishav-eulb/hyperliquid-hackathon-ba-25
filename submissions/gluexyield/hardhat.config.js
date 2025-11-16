require("@nomiclabs/hardhat-waffle");
require("@nomiclabs/hardhat-ethers");

// Load environment variables
require('dotenv').config();

const PRIVATE_KEY = process.env.PRIVATE_KEY || "0x0000000000000000000000000000000000000000000000000000000000000000";
const RPC_URL = process.env.RPC_URL || "https://api.hyperliquid-testnet.xyz/evm";

/**
 * @type import('hardhat/config').HardhatUserConfig
 */
module.exports = {
  solidity: {
    version: "0.8.20",
    settings: {
      optimizer: {
        enabled: true,
        runs: 200
      },
      viaIR: false
    }
  },
  
  networks: {
    hardhat: {
      chainId: 31337
    },
    
    // HyperEVM Testnet
    hyperEVM: {
      url: RPC_URL,
      accounts: [PRIVATE_KEY],
      chainId: 998, // Update with actual HyperEVM chain ID
      gasPrice: "auto",
      gas: "auto",
      timeout: 60000
    },
    
    // HyperEVM Mainnet (when available)
    hyperEVMMainnet: {
      url: process.env.RPC_URL_MAINNET || "https://api.hyperliquid.xyz/evm",
      accounts: [PRIVATE_KEY],
      chainId: 999, // Update with actual mainnet chain ID
      gasPrice: "auto",
      gas: "auto",
      timeout: 60000
    }
  },
  
  paths: {
    sources: "./contracts",
    tests: "./test",
    cache: "./cache",
    artifacts: "./artifacts"
  },
  
  mocha: {
    timeout: 60000
  }
};

