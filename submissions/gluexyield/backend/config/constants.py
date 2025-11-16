"""
Constants for GlueX integration
"""

# Mapping of vault addresses (LP token addresses) to their corresponding input tokens
VAULT_TO_INPUT_TOKEN = {
    # USDC Vault
    "0xe25514992597786e07872e6c5517fe1906c0cadd": "0xb88339CB7199b77E23DB6E890353E22632Ba630f",
    
    # USDT0 Vault
    "0xcdc3975df9d1cf054f44ed238edfb708880292ea": "0xB8CE59FC3717ada4C02eaDF9682A9e934F625ebb",
    
    # HYPE Vault
    "0x8f9291606862eef771a97e5b71e4b98fd1fa216a": "0x5555555555555555555555555555555555555555",
    
    # USDH Vault
    "0x9f75eac57d1c6f7248bd2aede58c95689f3827f7": "0x111111a1a0667d36bD57c0A9f569b98057111111",
    
    # USDE Vault
    "0x63cf7ee583d9954febf649ad1c40c97a6493b1be": "0x5d3a1Ff2b6BAb83b63cd9AD0787074081a52ef34",
}

# Vault names for reference
VAULT_NAMES = {
    "0xe25514992597786e07872e6c5517fe1906c0cadd": "USDC",
    "0xcdc3975df9d1cf054f44ed238edfb708880292ea": "USDT0",
    "0x8f9291606862eef771a97e5b71e4b98fd1fa216a": "HYPE",
    "0x9f75eac57d1c6f7248bd2aede58c95689f3827f7": "USDH",
    "0x63cf7ee583d9954febf649ad1c40c97a6493b1be": "USDE",
}

# Default chain for HyperEVM
DEFAULT_CHAIN = "hyperevm"

# API Endpoints
GLUEX_ROUTER_API = "https://router.gluex.xyz"
GLUEX_YIELDS_API = "https://yield-api.gluex.xyz"

# RPC Endpoints
HYPEREVM_RPC_URL = "https://rpc.hyperliquid.xyz/evm"  # HyperEVM mainnet
# For testnet, use: "https://api.hyperliquid-testnet.xyz/evm"

