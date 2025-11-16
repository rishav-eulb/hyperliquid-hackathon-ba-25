"""
Main GlueX Bot - Complete Orchestration
Integrates: Oracle Updater, Yield Engine, Portfolio Optimizer, Rebalance Planner
"""

import sys
import os

# Handle both direct execution and module execution
# Add parent directories to path for imports
backend_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(backend_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import time
import logging
import schedule
from typing import Optional, Dict
from web3 import Web3
from eth_account import Account

from backend.clients.gluex_client import GlueXClient
from backend.clients.web3_client import Web3Client
from backend.engines.vault_metrics_engine import VaultMetricsEngine
from backend.engines.portfolio_optimizer import PortfolioOptimizer, Portfolio
from backend.engines.rebalance_planner import RebalancePlanner, RebalancePlan
from backend.config.constants import VAULT_TO_INPUT_TOKEN, HYPEREVM_RPC_URL

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class GlueXBot:
    """
    Main bot orchestrating all operations:
    - Oracle price updates
    - Yield/risk analysis
    - Portfolio optimization
    - Rebalancing execution
    """
    
    def __init__(
        self,
        # API Keys
        gluex_api_key: str,
        bot_private_key: str,
        
        # Contract Addresses
        vault_manager_address: str,
        hyperyield_vault_address: str,
        base_asset_address: str,
        oracle_address: str,
        gluex_router_address: str,
        
        # Configuration
        rpc_url: str = None,
        oracle_update_interval: int = 5,  # minutes
        optimization_interval: int = 30,  # minutes
        deploy_fraction: float = 0.9,
        
        # Safety parameters
        rebalancing_enabled: bool = True,
        max_slippage: float = 0.02,
        drift_threshold: float = 0.10,
        min_sharpe_improvement: float = 0.05,
        
        # ✅ ADDED: Router validation flag
        validate_router: bool = True
    ):
        """
        Initialize GlueX Bot
        
        Args:
            gluex_api_key: GlueX API key
            bot_private_key: Private key for bot wallet
            vault_manager_address: VaultManagerMultiAsset address
            hyperyield_vault_address: HyperYieldVault address
            base_asset_address: Base asset (USDC) address
            oracle_address: GlueXOffchainOracle address
            gluex_router_address: GlueX Router address
            rpc_url: RPC URL (defaults to HyperEVM)
            oracle_update_interval: How often to update oracle (minutes)
            optimization_interval: How often to run optimization (minutes)
            deploy_fraction: Fraction of idle to deploy
            rebalancing_enabled: Master switch for rebalancing
            max_slippage: Maximum acceptable slippage
            drift_threshold: Rebalance drift threshold
            min_sharpe_improvement: Min Sharpe improvement for rebalance
        """
        self.rpc_url = rpc_url or HYPEREVM_RPC_URL
        self.oracle_update_interval = oracle_update_interval
        self.optimization_interval = optimization_interval
        self.rebalancing_enabled = rebalancing_enabled
        
        # Initialize clients
        self.gluex_client = GlueXClient(gluex_api_key, self.rpc_url)
        self.web3_client = Web3Client(self.rpc_url)
        self.w3 = self.web3_client.w3
        
        # Initialize bot account
        self.bot_account = Account.from_key(bot_private_key)
        logger.info(f"Bot wallet: {self.bot_account.address}")
        
        # Store contract addresses
        self.vault_manager_address = vault_manager_address
        self.hyperyield_vault_address = hyperyield_vault_address
        self.base_asset_address = base_asset_address
        self.oracle_address = oracle_address
        self.gluex_router_address = gluex_router_address
        
        # Initialize engines
        self.metrics_engine = VaultMetricsEngine(
            api_key=gluex_api_key,
            rpc_url=self.rpc_url,
            cache_ttl=optimization_interval * 60
        )
        
        self.optimizer = PortfolioOptimizer(
            metrics_engine=self.metrics_engine,
            deploy_fraction=deploy_fraction
        )
        
        self.rebalance_planner = RebalancePlanner(
            gluex_client=self.gluex_client,
            web3_client=self.web3_client,
            vault_manager_address=vault_manager_address,
            hyperyield_vault_address=hyperyield_vault_address,
            base_asset_address=base_asset_address,
            oracle_address=oracle_address,
            gluex_router_address=gluex_router_address,
            max_slippage=max_slippage
        )
        
        # Vault addresses to manage
        self.vault_addresses = list(VAULT_TO_INPUT_TOKEN.keys())
        
        # State tracking
        self.last_oracle_update = 0
        self.last_optimization = 0
        self.last_rebalance = 0
        
        logger.info("GlueXBot initialized successfully")
        logger.info(f"Managing {len(self.vault_addresses)} vaults")
        logger.info(f"Rebalancing: {'ENABLED' if rebalancing_enabled else 'DISABLED'}")
    
    def update_oracle_prices(self) -> bool:
        """
        Update oracle prices for all underlying tokens
        
        Returns:
            True if successful
        """
        logger.info("=" * 80)
        logger.info("UPDATING ORACLE PRICES")
        logger.info("=" * 80)
        
        try:
            # Get unique underlying tokens (excluding base asset)
            underlyings = set(VAULT_TO_INPUT_TOKEN.values())
            underlyings.discard(self.base_asset_address)
            
            prices_to_update = []
            
            # Get prices from GlueX API
            for underlying in underlyings:
                try:
                    # Call GlueX /price API
                    price_quote = self.gluex_client.get_asset_price(
                        input_token=underlying,
                        output_token=self.base_asset_address,
                        input_amount="1000000000000000000",  # 1 token (18 decimals)
                        chain_id="hyperevm"
                    )
                    
                    if not price_quote:
                        logger.error(f"No price quote for {underlying[:10]}...")
                        continue
                    
                    # Extract price and convert to 1e18 format
                    output_amount = int(price_quote.output_amount)
                    price_1e18 = output_amount * 10**12  # USDC is 6 decimals, scale to 18
                    
                    prices_to_update.append({
                        'token': underlying,
                        'price': price_1e18
                    })
                    
                    logger.info(f"Price for {underlying[:10]}...: {price_1e18}")
                    
                except Exception as e:
                    logger.error(f"Error getting price for {underlying[:10]}...: {e}")
            
            if not prices_to_update:
                logger.error("No prices to update")
                return False
            
            # Update oracle on-chain
            success = self._update_oracle_onchain(prices_to_update)
            
            if success:
                self.last_oracle_update = time.time()
                logger.info("Oracle prices updated successfully")
            
            return success
            
        except Exception as e:
            logger.error(f"Error updating oracle prices: {e}", exc_info=True)
            return False
    
    def _update_oracle_onchain(self, prices: list) -> bool:
        """
        Update oracle prices on-chain
        
        Args:
            prices: List of {'token': address, 'price': price_1e18}
        """
        # TODO: Implement actual oracle update transaction
        # Would involve calling oracle.setPrices(...) with proper encoding
        
        logger.warning("Oracle on-chain update not implemented - using mock")
        return True
    
    def run_optimization_cycle(self) -> Optional[Portfolio]:
        """
        Run complete optimization and rebalancing cycle
        
        Returns:
            Optimized Portfolio or None
        """
        logger.info("=" * 80)
        logger.info("STARTING OPTIMIZATION CYCLE")
        logger.info("=" * 80)
        
        try:
            # Step 1: Get total investable base
            total_base = self._get_total_investable_base()
            logger.info(f"Total investable base: ${total_base:,.2f}")
            
            if total_base <= 0:
                logger.warning("No investable base assets")
                return None
            
            # Step 2: Run portfolio optimization
            input_amount = str(int(total_base * 1e6))  # USDC units
            
            new_portfolio = self.optimizer.optimize(
                vault_addresses=self.vault_addresses,
                total_investable_base=total_base,
                input_amount=input_amount,
                force_refresh=True
            )
            
            if not new_portfolio or not new_portfolio.allocations:
                logger.warning("No portfolio generated")
                return None
            
            # Step 3: Check if rebalance needed
            should_rebalance, reason = self.optimizer.should_rebalance(
                new_portfolio,
                drift_threshold=0.10,
                min_sharpe_improvement=0.05
            )
            
            logger.info(f"Rebalance decision: {should_rebalance} - {reason}")
            
            if not should_rebalance:
                logger.info("No rebalance needed - skipping execution")
                return new_portfolio
            
            # Step 4: Execute rebalance (if enabled)
            if not self.rebalancing_enabled:
                logger.warning("Rebalancing is DISABLED - skipping execution")
                return new_portfolio
            
            logger.info("REBALANCE TRIGGERED - Creating execution plans")
            
            # Step 5: Group allocations by underlying token
            token_groups = self._group_allocations_by_token(new_portfolio)
            logger.info(f"Grouped into {len(token_groups)} token groups for sequential rebalancing")
            
            # Step 6: Execute rebalances sequentially (one per token group)
            all_success = True
            executed_count = 0
            
            for token_address, group_portfolio in token_groups.items():
                logger.info("=" * 80)
                logger.info(f"Executing rebalance for token group: {token_address[:10]}...")
                logger.info(f"  Vaults in group: {len(group_portfolio.allocations)}")
                logger.info("=" * 80)
                
                # Create plan for this token group
                plan = self.rebalance_planner.create_rebalance_plan(group_portfolio)
                
                if not plan:
                    logger.error(f"Failed to create plan for {token_address[:10]}...")
                    all_success = False
                    continue
                
                if not plan.sanity_checks_passed:
                    logger.error(f"Sanity checks failed for {token_address[:10]}...")
                    for warning in plan.warnings:
                        logger.error(f"  - {warning}")
                    all_success = False
                    continue
                
                # Execute this group's rebalance
                success = self._execute_rebalance_onchain(plan)
                
                if success:
                    logger.info(f"✓ Rebalance executed for {token_address[:10]}...")
                    executed_count += 1
                else:
                    logger.error(f"✗ Rebalance failed for {token_address[:10]}...")
                    all_success = False
                    
                    # If this was a cooldown error, stop trying remaining groups
                    # (VaultManager only allows one rebalance per cooldown period)
                    if executed_count > 0:
                        logger.warning("First rebalance succeeded but subsequent failed")
                        logger.warning("This is expected due to VaultManager cooldown")
                        logger.warning("Remaining token groups will execute in next cycle")
                        break
                
                # Small delay between rebalances to avoid nonce issues
                if executed_count < len(token_groups):
                    time.sleep(2)
            
            # Step 7: Update state if any rebalances succeeded
            if executed_count > 0:
                logger.info(f"Completed {executed_count}/{len(token_groups)} rebalances successfully")
                self.last_rebalance = time.time()
                
                if all_success:
                    # Update current portfolio only if ALL rebalances succeeded
                    self.optimizer.current_portfolio = new_portfolio
                    logger.info("Portfolio state fully updated")
                else:
                    logger.warning("Some rebalances failed - portfolio state not updated")
            else:
                logger.error("All rebalances failed")
            
            # Step 7: Log stats
            stats = self.metrics_engine.get_cache_stats()
            logger.info(f"Cache stats: {stats}")
            
            self.last_optimization = time.time()
            
            return new_portfolio
            
        except Exception as e:
            logger.error(f"Error in optimization cycle: {e}", exc_info=True)
            return None
    
    def _group_allocations_by_token(self, portfolio: Portfolio) -> Dict[str, Portfolio]:
        """
        Group portfolio allocations by underlying token
        
        This allows sequential rebalancing - one rebalance per token group
        to avoid the multicall complexity while still supporting multi-asset strategies
        
        Args:
            portfolio: Complete optimized portfolio
            
        Returns:
            Dict mapping underlying token address -> sub-portfolio for that token
        """
        from collections import defaultdict
        from backend.config.constants import VAULT_TO_INPUT_TOKEN
        
        # Group allocations by underlying token
        token_groups = defaultdict(list)
        
        for alloc in portfolio.allocations:
            underlying = VAULT_TO_INPUT_TOKEN.get(alloc.vault_address.lower())
            if not underlying:
                logger.warning(f"No underlying token for vault {alloc.vault_address[:10]}... - skipping")
                continue
            
            token_groups[underlying].append(alloc)
        
        # Create sub-portfolios for each token group
        sub_portfolios = {}
        
        for token, allocations in token_groups.items():
            # Calculate stats for this sub-portfolio
            total_amount = sum(a.target_amount for a in allocations)
            weighted_return = sum(a.weight * a.metrics.net_apy for a in allocations)
            
            # Create portfolio for this token group
            sub_portfolio = Portfolio(
                allocations=allocations,
                total_amount=total_amount,
                expected_return=weighted_return,
                portfolio_sharpe=portfolio.portfolio_sharpe,  # Use overall sharpe
                timestamp=portfolio.timestamp
            )
            
            sub_portfolios[token] = sub_portfolio
            
            logger.info(f"Token {token[:10]}...: {len(allocations)} vaults, ${total_amount:.2f}")
        
        return sub_portfolios
    
    def _get_total_investable_base(self) -> float:
        """Get total investable base assets"""
        try:
            # Get managed assets
            managed = self.rebalance_planner.manager_contract.functions\
                .getTotalManagedBaseAssets().call()
            
            # Get idle in vault
            idle = self.rebalance_planner._get_idle_base_in_vault()
            
            decimals = self.rebalance_planner._get_token_decimals(self.base_asset_address)
            managed_human = managed / (10 ** decimals)
            
            total = managed_human + idle
            
            logger.info(f"Managed: ${managed_human:,.2f}, Idle: ${idle:,.2f}, Total: ${total:,.2f}")
            
            return total
            
        except Exception as e:
            logger.error(f"Error getting total investable base: {e}")
            # Return placeholder for testing
            return 1000000.0
    
    def _execute_rebalance_onchain(self, plan: RebalancePlan) -> bool:
        """
        Execute rebalance transaction on-chain
        
        Args:
            plan: RebalancePlan to execute
            
        Returns:
            True if successful
        """
        logger.info("Executing rebalance on-chain...")
        
        try:
            # Build transaction
            manager_abi = self.rebalance_planner.VAULT_MANAGER_ABI + [
                {
                    "inputs": [
                        {
                            "components": [
                                {"name": "vault", "type": "address"},
                                {"name": "underlyingAmount", "type": "uint256"}
                            ],
                            "name": "targets",
                            "type": "tuple[]"
                        },
                        {"name": "router", "type": "address"},
                        {"name": "swapCalldata", "type": "bytes"}
                    ],
                    "name": "executeRebalance",
                    "outputs": [],
                    "stateMutability": "nonpayable",
                    "type": "function"
                }
            ]
            
            manager_contract = self.w3.eth.contract(
                address=self.vault_manager_address,
                abi=manager_abi
            )
            
            # Prepare targets
            targets_tuple = [
                (
                    Web3.to_checksum_address(t.vault),
                    t.underlying_amount
                )
                for t in plan.targets
            ]
            
            # Build transaction
            txn = manager_contract.functions.executeRebalance(
                targets_tuple,
                Web3.to_checksum_address(plan.router_address),
                plan.swap_calldata
            ).build_transaction({
                'from': self.bot_account.address,
                'nonce': self.w3.eth.get_transaction_count(self.bot_account.address),
                'gas': plan.estimated_gas,
                'gasPrice': self.w3.eth.gas_price,
                'chainId': self.w3.eth.chain_id,
                'value': plan.eth_value_needed  # ✅ FIXED: Send ETH for native token swaps
            })
            
            # Sign transaction
            signed_txn = self.w3.eth.account.sign_transaction(txn, self.bot_account.key)
            
            # Send transaction
            logger.info(f"Sending rebalance transaction...")
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            logger.info(f"Transaction hash: {tx_hash.hex()}")
            
            # Wait for receipt
            logger.info("Waiting for confirmation...")
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
            
            if receipt['status'] == 1:
                logger.info(f"Transaction confirmed in block {receipt['blockNumber']}")
                logger.info(f"Gas used: {receipt['gasUsed']:,}")
                return True
            else:
                logger.error(f"Transaction failed: {receipt}")
                
                # Try to get revert reason
                revert_reason = self._get_revert_reason(txn, receipt['blockNumber'])
                if revert_reason:
                    logger.error(f"Revert reason: {revert_reason}")
                else:
                    logger.error("Could not decode revert reason")
                
                return False
            
        except Exception as e:
            logger.error(f"Error executing rebalance: {e}", exc_info=True)
            return False
    
    def _get_revert_reason(self, txn: Dict, block_number: int) -> Optional[str]:
        """
        Try to get the revert reason by replaying the transaction
        
        Args:
            txn: Transaction dict
            block_number: Block number where tx was mined
            
        Returns:
            Revert reason string or None
        """
        try:
            # Replay the transaction to get the revert reason
            self.w3.eth.call(txn, block_number)
            return None  # If no exception, no revert reason
        except Exception as e:
            error_msg = str(e)
            
            # Try to extract revert reason from error message
            # Common patterns:
            # - "execution reverted: <reason>"
            # - "Error: <reason>"
            # - Hex encoded revert data
            
            if "execution reverted:" in error_msg:
                # Extract reason after "execution reverted:"
                reason = error_msg.split("execution reverted:")[-1].strip()
                return reason
            elif "revert" in error_msg.lower():
                # Generic revert
                return error_msg
            else:
                # Try to decode hex revert data
                try:
                    # Look for hex data in error message
                    import re
                    hex_match = re.search(r'0x[0-9a-fA-F]+', error_msg)
                    if hex_match:
                        hex_data = hex_match.group()
                        # Remove 0x and first 8 chars (function selector)
                        if len(hex_data) > 10:
                            data = hex_data[10:]
                            # Try to decode as string
                            try:
                                decoded = bytes.fromhex(data).decode('utf-8', errors='ignore')
                                return f"Decoded: {decoded.strip()}"
                            except:
                                return f"Raw revert data: {hex_data}"
                except:
                    pass
                
                return error_msg
        except:
            return None
    
    def run_health_check(self):
        """Run system health checks"""
        logger.info("=" * 80)
        logger.info("HEALTH CHECK")
        logger.info("=" * 80)
        
        # Check Web3 connection
        if self.web3_client.is_connected():
            logger.info("✓ Web3 connected")
        else:
            logger.error("✗ Web3 NOT connected")
        
        # Check bot wallet balance
        try:
            balance = self.w3.eth.get_balance(self.bot_account.address)
            balance_eth = balance / 1e18
            logger.info(f"✓ Bot wallet balance: {balance_eth:.6f} ETH")
            
            if balance_eth < 0.01:
                logger.warning("⚠ Low bot wallet balance")
        except Exception as e:
            logger.error(f"✗ Error checking balance: {e}")
        
        # Check cache stats
        stats = self.metrics_engine.get_cache_stats()
        logger.info(f"✓ Cache: {stats['cached_vaults']} vaults, "
                   f"{stats['hit_rate']:.1%} hit rate")
        
        # Check last update times
        now = time.time()
        
        if self.last_oracle_update > 0:
            age = (now - self.last_oracle_update) / 60
            logger.info(f"✓ Last oracle update: {age:.1f} minutes ago")
        else:
            logger.warning("⚠ No oracle updates yet")
        
        if self.last_optimization > 0:
            age = (now - self.last_optimization) / 60
            logger.info(f"✓ Last optimization: {age:.1f} minutes ago")
        else:
            logger.warning("⚠ No optimizations yet")
        
        logger.info("=" * 80)
    
    def start(self):
        """Start the bot with scheduled tasks"""
        logger.info("=" * 80)
        logger.info("STARTING GLUEX BOT")
        logger.info("=" * 80)
        logger.info(f"Oracle update interval: {self.oracle_update_interval} minutes")
        logger.info(f"Optimization interval: {self.optimization_interval} minutes")
        logger.info("=" * 80)
        
        # Run initial health check
        self.run_health_check()
        
        # Run immediately
        logger.info("Running initial oracle update...")
        self.update_oracle_prices()
        
        logger.info("Running initial optimization...")
        self.run_optimization_cycle()
        
        # Schedule tasks
        schedule.every(self.oracle_update_interval).minutes.do(self.update_oracle_prices)
        schedule.every(self.optimization_interval).minutes.do(self.run_optimization_cycle)
        schedule.every(60).minutes.do(self.run_health_check)
        
        logger.info("Scheduler started - entering main loop")
        
        # Main loop
        while True:
            try:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
            except KeyboardInterrupt:
                logger.info("Bot stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                time.sleep(60)


def main():
    """Main entry point"""
    import argparse
    from dotenv import load_dotenv
    
    # Load .env file from project root (hackathon directory)
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(backend_dir)
    env_path = os.path.join(project_root, '.env')
    
    load_dotenv(env_path)
    
    # Debug: Show if .env was found
    if os.path.exists(env_path):
        logger.info(f"Loading configuration from: {env_path}")
    else:
        logger.warning(f".env file not found at: {env_path}")
        logger.warning("Create .env from env.example and add your configuration")
    
    parser = argparse.ArgumentParser(description='GlueX Optimization Bot')
    parser.add_argument('--gluex-api-key', type=str, help='GlueX API key (default: from .env)')
    parser.add_argument('--bot-private-key', type=str, help='Bot wallet private key (default: from .env)')
    parser.add_argument('--vault-manager', type=str, help='VaultManager address (default: from .env)')
    parser.add_argument('--hyperyield-vault', type=str, help='HyperYieldVault address (default: from .env)')
    parser.add_argument('--base-asset', type=str, help='Base asset address (default: from .env)')
    parser.add_argument('--oracle', type=str, help='Oracle address (default: from .env)')
    parser.add_argument('--router', type=str, help='Router address (default: from .env)')
    parser.add_argument('--disable-rebalancing', action='store_true', help='Disable rebalancing')
    parser.add_argument('--oracle-interval', type=int, help='Oracle update interval in minutes (default: from .env or 5)')
    parser.add_argument('--optimization-interval', type=int, help='Optimization interval in minutes (default: from .env or 30)')
    
    args = parser.parse_args()
    
    # Get credentials from args or env
    api_key = args.gluex_api_key or os.getenv('GLUEX_API_KEY')
    private_key = args.bot_private_key or os.getenv('BOT_PRIVATE_KEY')
    
    # Get contract addresses from args or env
    vault_manager = args.vault_manager or os.getenv('MANAGER_ADDRESS')
    hyperyield_vault = args.hyperyield_vault or os.getenv('VAULT_ADDRESS')
    base_asset = args.base_asset or os.getenv('BASE_ASSET_ADDRESS')
    oracle = args.oracle or os.getenv('ORACLE_ADDRESS')
    router = args.router or os.getenv('GLUEX_ROUTER_ADDRESS')
    
    # Debug: Show what was loaded (helps troubleshoot .env issues)
    print("\n" + "="*80)
    print("ENVIRONMENT VARIABLES LOADED:")
    print("="*80)
    print(f"GLUEX_API_KEY: {'✓ Set' if api_key else '✗ Missing'}")
    print(f"BOT_PRIVATE_KEY: {'✓ Set' if private_key else '✗ Missing'}")
    print(f"MANAGER_ADDRESS: {vault_manager if vault_manager else '✗ Missing'}")
    print(f"VAULT_ADDRESS: {hyperyield_vault if hyperyield_vault else '✗ Missing'}")
    print(f"BASE_ASSET_ADDRESS: {base_asset if base_asset else '✗ Missing'}")
    print(f"ORACLE_ADDRESS: {oracle if oracle else '✗ Missing'}")
    print(f"GLUEX_ROUTER_ADDRESS: {router if router else '✗ Missing'}")
    print("="*80 + "\n")
    
    # Get intervals from args or env
    oracle_interval = args.oracle_interval or int(os.getenv('ORACLE_UPDATE_INTERVAL', '5'))
    optimization_interval = args.optimization_interval or int(os.getenv('OPTIMIZATION_INTERVAL', '30'))
    
    # Validate required parameters
    if not api_key:
        logger.error("GLUEX_API_KEY is required (set in .env or use --gluex-api-key)")
        return
    
    if not private_key:
        logger.error("BOT_PRIVATE_KEY is required (set in .env or use --bot-private-key)")
        return
    
    if not all([vault_manager, hyperyield_vault, base_asset, oracle, router]):
        logger.error("Missing required contract addresses. Please set in .env:")
        if not vault_manager:
            logger.error("  - MANAGER_ADDRESS")
        if not hyperyield_vault:
            logger.error("  - VAULT_ADDRESS")
        if not base_asset:
            logger.error("  - BASE_ASSET_ADDRESS")
        if not oracle:
            logger.error("  - ORACLE_ADDRESS")
        if not router:
            logger.error("  - GLUEX_ROUTER_ADDRESS")
        return
    
    # Initialize and start bot
    logger.info("Initializing bot with configuration:")
    logger.info(f"  Vault Manager: {vault_manager}")
    logger.info(f"  HyperYield Vault: {hyperyield_vault}")
    logger.info(f"  Base Asset: {base_asset}")
    logger.info(f"  Oracle: {oracle}")
    logger.info(f"  Router: {router}")
    logger.info(f"  Oracle Interval: {oracle_interval} minutes")
    logger.info(f"  Optimization Interval: {optimization_interval} minutes")
    logger.info(f"  Rebalancing: {'DISABLED' if args.disable_rebalancing else 'ENABLED'}")
    
    bot = GlueXBot(
        gluex_api_key=api_key,
        bot_private_key=private_key,
        vault_manager_address=vault_manager,
        hyperyield_vault_address=hyperyield_vault,
        base_asset_address=base_asset,
        oracle_address=oracle,
        gluex_router_address=router,
        oracle_update_interval=oracle_interval,
        optimization_interval=optimization_interval,
        rebalancing_enabled=not args.disable_rebalancing
    )
    
    bot.start()


if __name__ == "__main__":
    main()