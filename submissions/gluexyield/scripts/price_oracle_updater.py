"""
Price Oracle Updater
Fetches prices from GlueX API and updates the on-chain GlueXOffchainOracle contract
"""

import os
import sys
import time
import logging
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from dotenv import load_dotenv
from web3 import Web3
from web3.exceptions import ContractLogicError

# Add parent directory to path for imports
parent_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, parent_dir)

from backend.clients.gluex_client import GlueXClient
from backend.config.constants import VAULT_TO_INPUT_TOKEN, HYPEREVM_RPC_URL

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('price_oracle_updater.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


class PriceOracleUpdater:
    """Updates on-chain oracle with prices from GlueX API"""
    
    # Base asset is USDC (6 decimals)
    BASE_ASSET = "0xb88339CB7199b77E23DB6E890353E22632Ba630f"
    BASE_ASSET_DECIMALS = 6
    
    # Token decimals mapping
    TOKEN_DECIMALS = {
        "0xb88339CB7199b77E23DB6E890353E22632Ba630f": 6,   # USDC
        "0xB8CE59FC3717ada4C02eaDF9682A9e934F625ebb": 6,   # USDT0
        "0x5555555555555555555555555555555555555555": 18,  # HYPE
        "0x111111a1a0667d36bD57c0A9f569b98057111111": 6,  # USDH
        "0x5d3a1Ff2b6BAb83b63cd9AD0787074081a52ef34": 18,  # USDE
    }
    
    # Oracle contract ABI (minimal - just what we need)
    ORACLE_ABI = [
        {
            "inputs": [
                {"name": "underlyingToken", "type": "address"},
                {"name": "baseAsset", "type": "address"},
                {"name": "price1e18", "type": "uint256"}
            ],
            "name": "setPrice",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [
                {"name": "underlyingToken", "type": "address"},
                {"name": "baseAsset", "type": "address"}
            ],
            "name": "getPrice",
            "outputs": [
                {"name": "price1e18", "type": "uint256"},
                {"name": "lastUpdate", "type": "uint256"}
            ],
            "stateMutability": "view",
            "type": "function"
        }
    ]
    
    def __init__(
        self,
        gluex_api_key: str,
        oracle_address: str,
        private_key: str,
        rpc_url: str = None,
        update_interval: int = 300,  # 5 minutes default
        max_price_deviation: float = 10.0  # 10x max change
    ):
        """
        Initialize the price oracle updater
        
        Args:
            gluex_api_key: GlueX API key
            oracle_address: Address of the GlueXOffchainOracle contract
            private_key: Private key for signing transactions
            rpc_url: RPC URL (defaults to HyperEVM)
            update_interval: Time between updates in seconds
            max_price_deviation: Maximum allowed price change multiplier
        """
        self.gluex_client = GlueXClient(gluex_api_key, rpc_url)
        self.oracle_address = Web3.to_checksum_address(oracle_address)
        self.update_interval = update_interval
        self.max_price_deviation = max_price_deviation
        
        # Initialize Web3
        self.rpc_url = rpc_url or HYPEREVM_RPC_URL
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        
        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to RPC: {self.rpc_url}")
        
        # Set up account
        self.account = self.w3.eth.account.from_key(private_key)
        logger.info(f"Updater address: {self.account.address}")
        
        # Initialize oracle contract
        self.oracle_contract = self.w3.eth.contract(
            address=self.oracle_address,
            abi=self.ORACLE_ABI
        )
        
        # Cache for last known prices (for deviation checking)
        self.last_prices: Dict[Tuple[str, str], int] = {}
        
        logger.info(f"Initialized PriceOracleUpdater")
        logger.info(f"Oracle: {self.oracle_address}")
        logger.info(f"Base Asset: {self.BASE_ASSET} (USDC)")
        logger.info(f"Update Interval: {self.update_interval}s")
    
    def get_underlying_tokens(self) -> List[str]:
        """
        Get list of underlying tokens to update prices for
        
        Returns:
            List of token addresses
        """
        # Get unique input tokens from vault mappings (excluding USDC itself)
        tokens = set(VAULT_TO_INPUT_TOKEN.values())
        
        # Remove base asset (USDC) if present
        base_lower = self.BASE_ASSET.lower()
        tokens = {t for t in tokens if t.lower() != base_lower}
        
        return list(tokens)
    
    def get_token_decimals(self, token_address: str) -> int:
        """
        Get decimals for a token
        
        Args:
            token_address: Token address
            
        Returns:
            Number of decimals
        """
        token_lower = token_address.lower()
        
        # Check our mapping first
        for addr, decimals in self.TOKEN_DECIMALS.items():
            if addr.lower() == token_lower:
                return decimals
        
        # Default to 18 if not found
        logger.warning(f"Decimals not found for {token_address}, defaulting to 18")
        return 18
    
    def fetch_price_from_gluex(
        self,
        underlying_token: str,
        base_asset: str
    ) -> Optional[int]:
        """
        Fetch price from GlueX API and convert to price1e18 format
        
        Args:
            underlying_token: Address of the underlying token
            base_asset: Address of the base asset (USDC)
            
        Returns:
            Price in 1e18 format, or None on error
        """
        # Get decimals for the underlying token
        underlying_decimals = self.get_token_decimals(underlying_token)
        
        # Calculate input amount (1 full token)
        input_amount = str(10 ** underlying_decimals)
        
        logger.info(f"Fetching price: {underlying_token} -> {base_asset}")
        logger.info(f"  Input amount: {input_amount} ({underlying_decimals} decimals)")
        
        # Get price quote from GlueX
        price_quote = self.gluex_client.get_asset_price(
            input_token=underlying_token,
            output_token=base_asset,
            input_amount=input_amount,
            chain_id="hyperevm"
        )
        
        if not price_quote:
            logger.error(f"Failed to fetch price for {underlying_token}")
            return None
        
        # Parse the output amount
        try:
            raw_out = int(price_quote.output_amount)
            logger.info(f"  Output amount: {raw_out} (base asset units)")
            
            # Convert to price1e18
            # price1e18 = raw_out * 10^(18 - BASE_ASSET_DECIMALS)
            price1e18 = raw_out * (10 ** (18 - self.BASE_ASSET_DECIMALS))
            
            logger.info(f"  Price1e18: {price1e18}")
            logger.info(f"  USD value: ${price_quote.output_amount_usd}")
            
            return price1e18
            
        except (ValueError, AttributeError) as e:
            logger.error(f"Error parsing price response: {e}")
            return None
    
    def check_price_sanity(
        self,
        underlying_token: str,
        base_asset: str,
        new_price: int
    ) -> bool:
        """
        Check if price change is reasonable
        
        Args:
            underlying_token: Token address
            base_asset: Base asset address
            new_price: New price to check
            
        Returns:
            True if price is reasonable, False otherwise
        """
        key = (underlying_token.lower(), base_asset.lower())
        
        # If we don't have a previous price, try to get it from the oracle
        if key not in self.last_prices:
            try:
                price1e18, last_update = self.oracle_contract.functions.getPrice(
                    Web3.to_checksum_address(underlying_token),
                    Web3.to_checksum_address(base_asset)
                ).call()
                
                if price1e18 > 0:
                    self.last_prices[key] = price1e18
                    logger.info(f"Loaded existing oracle price: {price1e18}")
            except Exception as e:
                logger.warning(f"Could not fetch existing oracle price: {e}")
        
        # If we still don't have a previous price, accept the new one
        if key not in self.last_prices:
            logger.info("No previous price found, accepting new price")
            return True
        
        last_price = self.last_prices[key]
        
        # Check deviation
        if last_price > 0:
            ratio = new_price / last_price
            if ratio > self.max_price_deviation or ratio < (1 / self.max_price_deviation):
                logger.error(
                    f"Price deviation too large! "
                    f"Last: {last_price}, New: {new_price}, Ratio: {ratio:.2f}x"
                )
                return False
        
        return True
    
    def update_oracle_price(
        self,
        underlying_token: str,
        base_asset: str,
        price1e18: int
    ) -> bool:
        """
        Update price on the oracle contract
        
        Args:
            underlying_token: Token address
            base_asset: Base asset address
            price1e18: Price in 1e18 format
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Convert addresses to checksum format
            underlying_checksum = Web3.to_checksum_address(underlying_token)
            base_checksum = Web3.to_checksum_address(base_asset)
            
            # Build transaction
            tx = self.oracle_contract.functions.setPrice(
                underlying_checksum,
                base_checksum,
                price1e18
            ).build_transaction({
                'from': self.account.address,
                'nonce': self.w3.eth.get_transaction_count(self.account.address),
                'gas': 200000,  # Estimate, adjust if needed
                'gasPrice': self.w3.eth.gas_price,
            })
            
            # Sign transaction
            signed_tx = self.account.sign_transaction(tx)
            
            # Send transaction
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            logger.info(f"Sent tx: {tx_hash.hex()}")
            
            # Wait for receipt
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if receipt['status'] == 1:
                logger.info(f"✓ Price updated successfully!")
                logger.info(f"  Gas used: {receipt['gasUsed']}")
                
                # Update cache
                key = (underlying_token.lower(), base_asset.lower())
                self.last_prices[key] = price1e18
                
                return True
            else:
                logger.error(f"✗ Transaction failed!")
                return False
                
        except ContractLogicError as e:
            logger.error(f"Contract logic error: {e}")
            return False
        except Exception as e:
            logger.error(f"Error updating oracle: {e}")
            return False
    
    def update_all_prices(self) -> Dict[str, bool]:
        """
        Update prices for all underlying tokens
        
        Returns:
            Dict mapping token addresses to success status
        """
        results = {}
        underlying_tokens = self.get_underlying_tokens()
        
        # Add USDC itself (price = 1)
        all_tokens = [self.BASE_ASSET] + underlying_tokens
        
        logger.info(f"Updating prices for {len(all_tokens)} tokens (including USDC)")
        
        for token in all_tokens:
            try:
                logger.info(f"\n{'='*60}")
                logger.info(f"Processing: {token}")
                
                # Special handling for USDC (base asset): price is always 1
                if token.lower() == self.BASE_ASSET.lower():
                    logger.info("Base asset (USDC): setting price to 1.0")
                    # Price of USDC in USDC = 1.0
                    # In 1e18 format: 1 * 10^18 = 1000000000000000000
                    price1e18 = 10 ** 18
                    logger.info(f"  Price1e18: {price1e18}")
                else:
                    # Fetch price from GlueX for other tokens
                    price1e18 = self.fetch_price_from_gluex(token, self.BASE_ASSET)
                    
                    if price1e18 is None:
                        logger.error(f"Failed to fetch price for {token}")
                        results[token] = False
                        continue
                
                # Sanity check
                if not self.check_price_sanity(token, self.BASE_ASSET, price1e18):
                    logger.error(f"Price sanity check failed for {token}")
                    results[token] = False
                    continue
                
                # Update oracle
                success = self.update_oracle_price(token, self.BASE_ASSET, price1e18)
                results[token] = success
                
                if success:
                    logger.info(f"✓ Successfully updated {token}")
                else:
                    logger.error(f"✗ Failed to update {token}")
                
                # Small delay between updates
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"Error processing {token}: {e}")
                results[token] = False
        
        return results
    
    def run_forever(self):
        """
        Run the updater in a loop
        """
        logger.info("Starting price oracle updater loop...")
        logger.info(f"Will update every {self.update_interval} seconds")
        
        iteration = 0
        
        while True:
            try:
                iteration += 1
                logger.info(f"\n{'#'*60}")
                logger.info(f"Update iteration #{iteration}")
                logger.info(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
                logger.info(f"{'#'*60}\n")
                
                # Update all prices
                results = self.update_all_prices()
                
                # Summary
                successful = sum(1 for v in results.values() if v)
                total = len(results)
                logger.info(f"\nUpdate summary: {successful}/{total} successful")
                
                # Log failures
                failures = [k for k, v in results.items() if not v]
                if failures:
                    logger.warning(f"Failed tokens: {failures}")
                
                # Wait for next iteration
                logger.info(f"\nWaiting {self.update_interval} seconds until next update...")
                time.sleep(self.update_interval)
                
            except KeyboardInterrupt:
                logger.info("\n\nShutting down gracefully...")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                logger.info(f"Waiting {self.update_interval} seconds before retry...")
                time.sleep(self.update_interval)
    
    def run_once(self):
        """
        Run the updater once (useful for testing)
        """
        logger.info("Running price oracle updater (single iteration)...")
        results = self.update_all_prices()
        
        # Summary
        successful = sum(1 for v in results.values() if v)
        total = len(results)
        logger.info(f"\nFinal summary: {successful}/{total} successful")
        
        return results


def main():
    """Main entry point"""
    # Load configuration from environment
    gluex_api_key = os.getenv('GLUEX_API_KEY')
    oracle_address = os.getenv('ORACLE_ADDRESS')
    private_key = os.getenv('PRIVATE_KEY')
    rpc_url = os.getenv('RPC_URL', HYPEREVM_RPC_URL)
    
    # Validate required variables
    if not gluex_api_key:
        logger.error("GLUEX_API_KEY not found in environment")
        sys.exit(1)
    
    if not oracle_address:
        logger.error("ORACLE_ADDRESS not found in environment")
        sys.exit(1)
    
    if not private_key:
        logger.error("PRIVATE_KEY not found in environment")
        sys.exit(1)
    
    # Optional configuration
    update_interval = int(os.getenv('UPDATE_INTERVAL', '300'))  # 5 minutes default
    max_price_deviation = float(os.getenv('MAX_PRICE_DEVIATION', '10.0'))
    run_once = os.getenv('RUN_ONCE', 'false').lower() == 'true'
    
    # Create updater
    updater = PriceOracleUpdater(
        gluex_api_key=gluex_api_key,
        oracle_address=oracle_address,
        private_key=private_key,
        rpc_url=rpc_url,
        update_interval=update_interval,
        max_price_deviation=max_price_deviation
    )
    
    # Run
    if run_once:
        updater.run_once()
    else:
        updater.run_forever()


if __name__ == "__main__":
    main()

