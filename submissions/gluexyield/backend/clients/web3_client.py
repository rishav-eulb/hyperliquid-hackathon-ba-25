"""
Web3 Client for interacting with vault contracts
"""

from web3 import Web3
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# ERC4626 Vault ABI (minimal - just what we need)
ERC4626_ABI = [
    {
        "inputs": [],
        "name": "totalAssets",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "asset",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function"
    }
]

# ERC20 Token ABI (for getting decimals)
ERC20_ABI = [
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function"
    }
]


class Web3Client:
    """Client for Web3 interactions with vault contracts"""
    
    def __init__(self, rpc_url: str):
        """
        Initialize Web3 client
        
        Args:
            rpc_url: RPC endpoint URL for the blockchain
        """
        try:
            self.w3 = Web3(Web3.HTTPProvider(
                rpc_url,
                request_kwargs={'timeout': 60}
            ))
            
            if not self.w3.is_connected():
                logger.warning(f"Failed to connect to RPC at {rpc_url}")
            else:
                logger.info(f"Connected to Web3 RPC at {rpc_url}")
                # Try to get chain ID to verify connection
                try:
                    chain_id = self.w3.eth.chain_id
                    logger.info(f"Connected to chain ID: {chain_id}")
                except Exception as e:
                    logger.warning(f"Connected but couldn't get chain ID: {e}")
        except Exception as e:
            logger.error(f"Error initializing Web3 client: {e}")
            self.w3 = None
    
    def get_vault_tvl(self, vault_address: str) -> Optional[float]:
        """
        Fetch Total Value Locked (TVL) from a vault contract
        
        Args:
            vault_address: Address of the ERC4626 vault
            
        Returns:
            TVL in USD (assuming stablecoin backing) or None on error
        """
        try:
            if self.w3 is None or not self.w3.is_connected():
                logger.error("Web3 not connected")
                return None
            
            # Create contract instance
            vault_address = Web3.to_checksum_address(vault_address)
            vault_contract = self.w3.eth.contract(
                address=vault_address,
                abi=ERC4626_ABI
            )
            
            # Get total assets in the vault
            total_assets = vault_contract.functions.totalAssets().call()
            
            # Get the underlying asset address
            asset_address = vault_contract.functions.asset().call()
            
            # Get decimals from the underlying asset
            asset_contract = self.w3.eth.contract(
                address=asset_address,
                abi=ERC20_ABI
            )
            decimals = asset_contract.functions.decimals().call()
            
            # Convert to human-readable value
            tvl = total_assets / (10 ** decimals)
            
            logger.debug(f"Vault {vault_address[:10]}... TVL: ${tvl:,.2f}")
            logger.info(f"Vault {vault_address[:10]}... TVL: ${tvl:,.2f}")
            return tvl
            
        except Exception as e:
            logger.error(f"Error fetching TVL for vault {vault_address}: {e}")
            return None
    
    def get_multiple_vault_tvls(self, vault_addresses: list) -> dict:
        """
        Fetch TVL for multiple vaults
        
        Args:
            vault_addresses: List of vault addresses
            
        Returns:
            Dictionary mapping vault addresses to TVL values
        """
        tvls = {}
        
        for vault_address in vault_addresses:
            tvl = self.get_vault_tvl(vault_address)
            if tvl is not None:
                tvls[vault_address.lower()] = tvl
        
        return tvls
    
    def is_connected(self) -> bool:
        """Check if Web3 is connected"""
        return self.w3 is not None and self.w3.is_connected()

