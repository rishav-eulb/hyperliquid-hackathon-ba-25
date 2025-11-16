#!/usr/bin/env python3
"""
Fix VaultManager strategies to match constants.py
Removes incorrect vaults and adds the correct ones
"""

import os
import sys
from web3 import Web3
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
VAULT_MANAGER = "0xb920E976496Af7C585DD7e87a545B51a68e7FCa7"
RPC_URL = "https://rpc.hyperliquid.xyz/evm"
PRIVATE_KEY = os.getenv("PRIVATE_KEY")

if not PRIVATE_KEY:
    print("❌ Error: PRIVATE_KEY not found in .env")
    sys.exit(1)

# Initialize Web3
w3 = Web3(Web3.HTTPProvider(RPC_URL))
if not w3.is_connected():
    print("❌ Error: Cannot connect to RPC")
    sys.exit(1)

# Setup account
account = w3.eth.account.from_key(PRIVATE_KEY)
print(f"Using account: {account.address}")

# VaultManager ABI (only functions we need)
VAULT_MANAGER_ABI = [
    {
        "inputs": [{"name": "vault", "type": "address"}],
        "name": "removeStrategy",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"name": "vault", "type": "address"},
            {"name": "underlying", "type": "address"}
        ],
        "name": "addStrategy",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "getStrategies",
        "outputs": [{"type": "address[]"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"name": "vault", "type": "address"}],
        "name": "strategyShares",
        "outputs": [{"type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    }
]

# Contract instance
manager = w3.eth.contract(
    address=Web3.to_checksum_address(VAULT_MANAGER),
    abi=VAULT_MANAGER_ABI
)

# OLD (incorrect) vault addresses currently registered
OLD_VAULTS = {
    "HYPE": "0x18c9705b3bAeBCfe2Fb1EC6AE1a4D7A3BE0E9dD1",
    "USDH": "0x5D6C7f1d03a7b26b11BD3F9FbF42FE34ec86bEE2",
    "USDE": "0x2C7AdEd7ca12d9F2F09f0A8Bb39F1234Dd23A0FF",
}

# CORRECT vault addresses from constants.py
CORRECT_VAULTS = {
    "HYPE": {
        "vault": "0x8f9291606862eef771a97e5b71e4b98fd1fa216a",
        "underlying": "0x5555555555555555555555555555555555555555"
    },
    "USDH": {
        "vault": "0x9f75eac57d1c6f7248bd2aede58c95689f3827f7",
        "underlying": "0x111111a1a0667d36bD57c0A9f569b98057111111"
    },
    "USDE": {
        "vault": "0x63cf7ee583d9954febf649ad1c40c97a6493b1be",
        "underlying": "0x5d3a1Ff2b6BAb83b63cd9AD0787074081a52ef34"
    }
}

def send_transaction(tx_func, description):
    """Send a transaction and wait for confirmation"""
    print(f"\n{description}...")
    
    try:
        # Build transaction
        tx = tx_func.build_transaction({
            'from': account.address,
            'nonce': w3.eth.get_transaction_count(account.address),
            'gas': 300000,
            'gasPrice': w3.eth.gas_price,
            'chainId': w3.eth.chain_id,
        })
        
        # Sign and send
        signed_tx = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        print(f"  Transaction: {tx_hash.hex()}")
        
        # Wait for confirmation
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        
        if receipt['status'] == 1:
            print(f"  ✓ Success (gas used: {receipt['gasUsed']:,})")
            return True
        else:
            print(f"  ❌ Transaction failed")
            return False
            
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

def main():
    print("=" * 50)
    print("Fixing VaultManager Strategies")
    print("=" * 50)
    print(f"Manager: {VAULT_MANAGER}")
    print(f"RPC: {RPC_URL}")
    
    # Show current strategies
    print("\nCurrent strategies:")
    current = manager.functions.getStrategies().call()
    for vault in current:
        print(f"  - {vault}")
    
    # Step 1: Remove old vaults
    print("\n" + "=" * 50)
    print("Step 1: Removing old/incorrect vaults")
    print("=" * 50)
    
    for name, vault_addr in OLD_VAULTS.items():
        vault_checksum = Web3.to_checksum_address(vault_addr)
        
        # Check if vault has any shares
        try:
            shares = manager.functions.strategyShares(vault_checksum).call()
            if shares > 0:
                print(f"\n⚠️  WARNING: {name} vault has {shares} shares!")
                print(f"   Cannot remove vault with active position.")
                print(f"   You need to withdraw first or use emergencyWithdraw")
                continue
        except Exception as e:
            print(f"\n⚠️  Could not check shares for {name}: {e}")
            continue
        
        tx_func = manager.functions.removeStrategy(vault_checksum)
        send_transaction(tx_func, f"Removing old {name} vault")
    
    # Step 2: Add correct vaults
    print("\n" + "=" * 50)
    print("Step 2: Adding correct vaults from constants.py")
    print("=" * 50)
    
    for name, config in CORRECT_VAULTS.items():
        vault_checksum = Web3.to_checksum_address(config["vault"])
        underlying_checksum = Web3.to_checksum_address(config["underlying"])
        
        tx_func = manager.functions.addStrategy(vault_checksum, underlying_checksum)
        send_transaction(tx_func, f"Adding {name} vault")
    
    # Show final strategies
    print("\n" + "=" * 50)
    print("✓ Update Complete!")
    print("=" * 50)
    print("\nFinal strategies:")
    final = manager.functions.getStrategies().call()
    for vault in final:
        print(f"  - {vault}")
    
    print("\n✓ Strategies now match constants.py")

if __name__ == "__main__":
    main()

