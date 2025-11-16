#!/usr/bin/env python3
"""
Vault Data Collection Script
Fetches yield data from GlueX API and stores it in the database
"""

import os
import sys
import logging
from datetime import datetime
from typing import List, Optional

# Add parent directories to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.clients.gluex_client import GlueXClient
from backend.db.database import Database
from backend.db.models import VaultData
from backend.config.constants import VAULT_TO_INPUT_TOKEN

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class VaultDataCollector:
    """Collects and stores vault yield data"""
    
    def __init__(self, api_key: str, db_path: str = None):
        """
        Initialize data collector
        
        Args:
            api_key: GlueX API key
            db_path: Path to SQLite database (optional)
        """
        self.client = GlueXClient(api_key)
        self.db = Database(db_path)
        self.db.create_tables()
        logger.info("Vault data collector initialized")
    
    def collect_vault_data(
        self,
        vault_addresses: List[str],
        amount: str = "1000000000000"  # Default: 1M USDC
    ) -> int:
        """
        Collect data for multiple vaults and store in database
        
        Args:
            vault_addresses: List of vault addresses to process
            amount: Amount to use for diluted APY calculation
            
        Returns:
            Number of vaults successfully processed
        """
        session = self.db.get_session()
        processed_count = 0
        
        try:
            logger.info(f"Starting data collection for {len(vault_addresses)} vaults")
            
            for vault_address in vault_addresses:
                try:
                    # Normalize address
                    vault_address = vault_address.lower()
                    
                    # Fetch historical APY
                    hist_data = self.client.get_historical_apy(vault_address)
                    if not hist_data:
                        logger.warning(f"No historical APY data for {vault_address}")
                        continue
                    
                    # Fetch diluted APY
                    diluted_data = self.client.get_diluted_apy(vault_address, amount)
                    if not diluted_data:
                        logger.warning(f"No diluted APY data for {vault_address}")
                        continue
                    
                    # Extract APY values
                    historical_apy = self._extract_historical_apy(hist_data)
                    diluted_apy = self._extract_diluted_apy(diluted_data)
                    
                    # Fetch TVL from blockchain
                    tvl = self.client.web3_client.get_vault_tvl(vault_address)
                    if tvl is None:
                        tvl = 0
                        logger.warning(f"Could not fetch TVL for {vault_address}")
                    
                    # Create database record
                    vault_record = VaultData(
                        vault_address=vault_address,
                        historical_apy=historical_apy,
                        diluted_apy=diluted_apy,
                        tvl=float(tvl),
                        created_at=datetime.utcnow()
                    )
                    
                    session.add(vault_record)
                    session.commit()
                    
                    logger.info(
                        f"Stored data for {vault_address[:10]}... - "
                        f"Historical APY: {historical_apy:.2f}%, "
                        f"Diluted APY: {diluted_apy:.2f}%, "
                        f"TVL: ${tvl:,.0f}"
                    )
                    
                    processed_count += 1
                    
                except Exception as e:
                    logger.error(f"Error processing vault {vault_address}: {e}")
                    session.rollback()
                    continue
            
            logger.info(f"Successfully processed {processed_count}/{len(vault_addresses)} vaults")
            return processed_count
            
        except Exception as e:
            logger.error(f"Error during data collection: {e}")
            session.rollback()
            raise
        finally:
            session.close()
    
    def collect_single_vault(self, vault_address: str, amount: str = "1000000000000") -> bool:
        """
        Collect data for a single vault
        
        Args:
            vault_address: Vault address to process
            amount: Amount to use for diluted APY calculation
            
        Returns:
            True if successful, False otherwise
        """
        return self.collect_vault_data([vault_address], amount) > 0
    
    def _extract_historical_apy(self, hist_data: dict) -> float:
        """
        Extract historical APY from API response
        
        Args:
            hist_data: Historical APY response from API
            
        Returns:
            APY as float (percentage)
        """
        try:

            if 'historic_yield' in hist_data:
                apy_data = hist_data['historic_yield'].get('apy', {})
                return float(apy_data.get('net_apy', apy_data.get('apy', 0)))
            elif 'historical_yield' in hist_data:
                apy_data = hist_data['historical_yield'].get('apy', {})
                return float(apy_data.get('net_apy', apy_data.get('apy', 0)))
            elif 'apy' in hist_data:
                apy_data = hist_data['apy']
                if isinstance(apy_data, dict):
                    return float(apy_data.get('net_apy', apy_data.get('apy', 0)))
                return float(apy_data)
            else:
                logger.warning(f"Unexpected historical APY structure: {hist_data}")
                return 0.0
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error extracting historical APY: {e}")
            return 0.0
    
    def _extract_diluted_apy(self, diluted_data: dict) -> float:
        """
        Extract diluted APY from API response
        
        Args:
            diluted_data: Diluted APY response from API
            
        Returns:
            APY as float (percentage)
        """
        try:
            diluted_yield = diluted_data.get('diluted_yield', {})
            apy_data = diluted_yield.get('apy', {})
            return float(apy_data.get('net_apy', apy_data.get('apy', 0)))
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error extracting diluted APY: {e}")
            return 0.0
    
    def get_latest_data(self, vault_address: str = None) -> List[VaultData]:
        """
        Get latest data from database
        
        Args:
            vault_address: Optional vault address to filter by
            
        Returns:
            List of VaultData records
        """
        session = self.db.get_session()
        try:
            query = session.query(VaultData)
            if vault_address:
                query = query.filter(VaultData.vault_address == vault_address.lower())
            
            results = query.order_by(VaultData.created_at.desc()).limit(100).all()
            return results
        finally:
            session.close()
    
    def print_latest_data(self, vault_address: str = None):
        """
        Print latest data from database
        
        Args:
            vault_address: Optional vault address to filter by
        """
        records = self.get_latest_data(vault_address)
        
        if not records:
            print("No data found in database")
            return
        
        print(f"\n{'='*80}")
        print(f"Latest Vault Data ({len(records)} records)")
        print(f"{'='*80}")
        
        for record in records:
            print(f"\nVault: {record.vault_address}")
            print(f"  Historical APY: {record.historical_apy:.2f}%")
            print(f"  Diluted APY: {record.diluted_apy:.2f}%")
            print(f"  TVL: ${record.tvl:,.2f}")
            print(f"  Recorded: {record.created_at}")
        
        print(f"\n{'='*80}\n")
    
    def close(self):
        """Close database connection"""
        self.db.close()


def main():
    """Main function for running as script"""
    import argparse
    from dotenv import load_dotenv
    
    # Load environment variables
    load_dotenv()
    
    parser = argparse.ArgumentParser(description='Collect and store vault yield data')
    parser.add_argument(
        '--vaults',
        nargs='+',
        help='Vault addresses to collect data for (space-separated)',
        default=None
    )
    parser.add_argument(
        '--amount',
        type=str,
        default='1000000000000',
        help='Amount for diluted APY calculation (default: 1M USDC = 1000000000000)'
    )
    parser.add_argument(
        '--api-key',
        type=str,
        default=None,
        help='GlueX API key (defaults to GLUEX_API_KEY env var)'
    )
    parser.add_argument(
        '--db-path',
        type=str,
        default=None,
        help='Path to SQLite database (defaults to backend/db/vaults.db)'
    )
    parser.add_argument(
        '--show-data',
        action='store_true',
        help='Show latest data from database'
    )
    
    args = parser.parse_args()
    
    # Get API key
    api_key = args.api_key or os.getenv('GLUEX_API_KEY')
    if not api_key:
        logger.error("API key not provided. Use --api-key or set GLUEX_API_KEY env var")
        sys.exit(1)
    
    # Initialize collector
    collector = VaultDataCollector(api_key, args.db_path)
    
    try:
        # Show data if requested
        if args.show_data:
            collector.print_latest_data()
            return
        
        # Get vault addresses
        vault_addresses = args.vaults
        if not vault_addresses:
            # Use default vault addresses from constants
            vault_addresses = list(VAULT_TO_INPUT_TOKEN.keys())
            logger.info(f"Using {len(vault_addresses)} default vaults from constants")
        
        # Collect data
        logger.info(f"Collecting data for {len(vault_addresses)} vaults...")
        processed = collector.collect_vault_data(vault_addresses, args.amount)
        
        logger.info(f"Data collection complete. Processed {processed} vaults.")
        
        # Show collected data
        print("\n")
        collector.print_latest_data()
        
    except KeyboardInterrupt:
        logger.info("Data collection interrupted by user")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        collector.close()


if __name__ == "__main__":
    main()

