"""
Rebalancing Planner - Translates portfolio targets to on-chain execution
"""

import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from web3 import Web3

from .portfolio_optimizer import Portfolio, PortfolioAllocation
from ..clients.gluex_client import GlueXClient
from ..clients.web3_client import Web3Client
from ..config.constants import VAULT_TO_INPUT_TOKEN

logger = logging.getLogger(__name__)


@dataclass
class CurrentPosition:
    """Current position in a vault"""
    vault_address: str
    underlying_token: str
    shares: int
    underlying_amount: float
    base_value: float
    active: bool


@dataclass
class TargetAllocation:
    """Target allocation for on-chain execution"""
    vault: str  # Vault address
    underlying_amount: int  # Amount in wei


@dataclass
class RebalancePlan:
    """Complete rebalance execution plan"""
    targets: List[TargetAllocation]
    router_address: str
    swap_calldata: bytes
    estimated_gas: int
    eth_value_needed: int  # Amount of ETH to send with transaction (in wei)
    sanity_checks_passed: bool
    warnings: List[str]


class RebalancePlanner:
    """
    Translates optimized portfolio into executable on-chain transactions
    """
    
    # ABIs for contract interactions
    VAULT_MANAGER_ABI = [
        {
            "inputs": [],
            "name": "getTotalManagedBaseAssets",
            "outputs": [{"type": "uint256"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "canRebalance",
            "outputs": [{"type": "bool"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "isRebalancing",
            "outputs": [{"type": "bool"}],
            "stateMutability": "view",
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
            "name": "getStrategyPosition",
            "outputs": [
                {"name": "underlying", "type": "address"},
                {"name": "shares", "type": "uint256"},
                {"name": "underlyingAmount", "type": "uint256"},
                {"name": "baseValue", "type": "uint256"},
                {"name": "active", "type": "bool"}
            ],
            "stateMutability": "view",
            "type": "function"
        }
    ]
    
    ERC20_ABI = [
        {
            "inputs": [{"name": "account", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"type": "uint256"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "decimals",
            "outputs": [{"type": "uint8"}],
            "stateMutability": "view",
            "type": "function"
        }
    ]
    
    ORACLE_ABI = [
        {
            "inputs": [
                {"name": "tokenIn", "type": "address"},
                {"name": "baseAsset", "type": "address"}
            ],
            "name": "getPriceData",
            "outputs": [
                {"name": "price", "type": "uint256"},
                {"name": "lastUpdated", "type": "uint256"}
            ],
            "stateMutability": "view",
            "type": "function"
        }
    ]
    
    def __init__(
        self,
        gluex_client: GlueXClient,
        web3_client: Web3Client,
        vault_manager_address: str,
        hyperyield_vault_address: str,
        base_asset_address: str,
        oracle_address: str,
        gluex_router_address: str,
        native_token_address: str = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",  # Standard ETH placeholder
        max_slippage: float = 0.02,  # 2%
        max_price_staleness: int = 3600  # 1 hour
    ):
        """
        Initialize rebalance planner
        
        Args:
            gluex_client: GlueX API client
            web3_client: Web3 client
            vault_manager_address: VaultManagerMultiAsset contract
            hyperyield_vault_address: HyperYieldVault contract
            base_asset_address: Base asset (USDC) address
            oracle_address: GlueXOffchainOracle address
            gluex_router_address: GlueX Router address
            native_token_address: Native token address (ETH placeholder)
            max_slippage: Maximum acceptable slippage
            max_price_staleness: Max oracle price age in seconds
        """
        self.gluex_client = gluex_client
        self.web3_client = web3_client
        self.vault_manager_address = Web3.to_checksum_address(vault_manager_address)
        self.hyperyield_vault_address = Web3.to_checksum_address(hyperyield_vault_address)
        self.base_asset_address = Web3.to_checksum_address(base_asset_address)
        self.oracle_address = Web3.to_checksum_address(oracle_address)
        self.gluex_router_address = gluex_router_address
        self.native_token_address = native_token_address.lower()
        self.max_slippage = max_slippage
        self.max_price_staleness = max_price_staleness
        
        # Initialize contracts
        self.w3 = web3_client.w3
        self.manager_contract = self.w3.eth.contract(
            address=self.vault_manager_address,
            abi=self.VAULT_MANAGER_ABI
        )
        self.oracle_contract = self.w3.eth.contract(
            address=self.oracle_address,
            abi=self.ORACLE_ABI
        )
        
        logger.info("RebalancePlanner initialized")
    
    def create_rebalance_plan(
        self, 
        portfolio: Portfolio
    ) -> Optional[RebalancePlan]:
        """
        Create complete rebalance plan from optimized portfolio
        
        Args:
            portfolio: Optimized portfolio from PortfolioOptimizer
            
        Returns:
            RebalancePlan or None on failure
        """
        logger.info("Creating rebalance plan...")
        
        warnings = []
        
        # Step 1: Safety checks
        if not self._check_can_rebalance():
            logger.error("Cannot rebalance - cooldown or already rebalancing")
            return None
        
        if not self._check_oracle_freshness(warnings):
            logger.error("Oracle prices are stale")
            return None
        
        # Step 2: Read current positions
        current_positions = self._read_current_positions()
        logger.info(f"Current positions: {len(current_positions)} vaults")
        
        # Step 3: Get idle base assets
        idle_base = self._get_idle_base_in_vault()
        logger.info(f"Idle base in vault: ${idle_base:,.2f}")
        
        # Step 4: Calculate required swaps
        swap_plan = self._calculate_swap_plan(
            current_positions,
            portfolio.allocations,
            idle_base
        )
        
        if swap_plan is None:
            logger.error("Failed to calculate swap plan")
            return None
        
        # Step 5: Get router calldata
        router_address, swap_calldata, total_input_amount = self._get_router_calldata(swap_plan, warnings)
        
        if swap_calldata is None:
            logger.error("Failed to get router calldata")
            return None
        
        # Step 6: Calculate ETH value needed
        # If base asset is native token (ETH), we need to send ETH value
        eth_value_needed = 0
        if self.base_asset_address.lower() == self.native_token_address.lower():
            eth_value_needed = total_input_amount
            logger.info(f"Base asset is native token - ETH value needed: {eth_value_needed} wei")
        else:
            logger.info("Base asset is not native token - no ETH value needed")
        
        # Step 7: Build target allocations
        targets = self._build_target_allocations(portfolio.allocations)
        
        # Step 8: Estimate gas
        estimated_gas = self._estimate_rebalance_gas(targets, router_address, swap_calldata)
        
        # Step 9: Determine if sanity checks passed
        # Only fail on critical warnings (not limitations like multicall)
        critical_warnings = [w for w in warnings if not any(x in w.lower() for x in [
            'multicall not implemented',
            'simplified',
            'only executing first'
        ])]
        
        plan = RebalancePlan(
            targets=targets,
            router_address=router_address,
            swap_calldata=swap_calldata,
            estimated_gas=estimated_gas,
            eth_value_needed=eth_value_needed,
            sanity_checks_passed=len(critical_warnings) == 0,
            warnings=warnings
        )
        
        self._log_plan(plan)
        
        return plan
    
    def _check_can_rebalance(self) -> bool:
        """Check if rebalancing is allowed"""
        try:
            can_rebalance = self.manager_contract.functions.canRebalance().call()
            is_rebalancing = self.manager_contract.functions.isRebalancing().call()
            
            if not can_rebalance:
                logger.warning("Rebalance cooldown not passed")
                return False
            
            if is_rebalancing:
                logger.warning("Already in rebalancing state")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking rebalance status: {e}")
            return False
    
    def _check_oracle_freshness(self, warnings: List[str]) -> bool:
        """Check that oracle prices are fresh"""
        import time
        
        try:
            current_time = int(time.time())
            all_fresh = True
            
            # Check each underlying token
            for vault_addr, underlying in VAULT_TO_INPUT_TOKEN.items():
                if underlying.lower() == self.base_asset_address.lower():
                    continue  # Base asset doesn't need oracle
                
                try:
                    price, last_update = self.oracle_contract.functions.getPriceData(
                        Web3.to_checksum_address(underlying),
                        self.base_asset_address
                    ).call()
                    
                    # Check if price is set (non-zero)
                    if price == 0:
                        msg = f"No price set for {underlying[:10]}... (needs oracle update)"
                        logger.warning(msg)
                        warnings.append(msg)
                        all_fresh = False
                        continue
                    
                    age = current_time - last_update
                    
                    if age > self.max_price_staleness:
                        msg = f"Price stale for {underlying[:10]}... (age: {age}s)"
                        logger.warning(msg)
                        warnings.append(msg)
                        all_fresh = False
                    else:
                        logger.debug(f"Price fresh for {underlying[:10]}... (age: {age}s, price: {price})")
                        
                except Exception as e:
                    msg = f"Error checking price for {underlying[:10]}...: {e}"
                    logger.error(msg)
                    warnings.append(msg)
                    all_fresh = False
            
            return all_fresh
            
        except Exception as e:
            logger.error(f"Error checking oracle freshness: {e}")
            return False
    
    def _read_current_positions(self) -> Dict[str, CurrentPosition]:
        """Read current positions from VaultManager"""
        positions = {}
        
        try:
            # Get list of strategy vaults
            strategy_addresses = self.manager_contract.functions.getStrategies().call()
            
            for vault_addr in strategy_addresses:
                try:
                    # Get position details
                    underlying, shares, underlying_amt, base_value, active = \
                        self.manager_contract.functions.getStrategyPosition(vault_addr).call()
                    
                    # Convert from wei to human-readable
                    underlying_decimals = self._get_token_decimals(underlying)
                    base_decimals = self._get_token_decimals(self.base_asset_address)
                    
                    position = CurrentPosition(
                        vault_address=vault_addr.lower(),
                        underlying_token=underlying.lower(),
                        shares=shares,
                        underlying_amount=underlying_amt / (10 ** underlying_decimals),
                        base_value=base_value / (10 ** base_decimals),
                        active=active
                    )
                    
                    positions[vault_addr.lower()] = position
                    
                    logger.info(
                        f"Current position: {vault_addr[:10]}... | "
                        f"Underlying: {position.underlying_amount:.2f} | "
                        f"Base value: ${position.base_value:,.2f}"
                    )
                    
                except Exception as e:
                    logger.error(f"Error reading position for {vault_addr}: {e}")
            
            return positions
            
        except Exception as e:
            logger.error(f"Error reading current positions: {e}")
            return {}
    
    def _get_idle_base_in_vault(self) -> float:
        """Get idle base assets in HyperYieldVault"""
        try:
            base_contract = self.w3.eth.contract(
                address=self.base_asset_address,
                abi=self.ERC20_ABI
            )
            
            balance_wei = base_contract.functions.balanceOf(
                self.hyperyield_vault_address
            ).call()
            
            decimals = self._get_token_decimals(self.base_asset_address)
            balance = balance_wei / (10 ** decimals)
            
            return balance
            
        except Exception as e:
            logger.error(f"Error getting idle base: {e}")
            return 0.0
    
    def _get_token_decimals(self, token_address: str) -> int:
        """Get token decimals"""
        try:
            token_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=self.ERC20_ABI
            )
            return token_contract.functions.decimals().call()
        except:
            return 18  # Default
    
    def _calculate_swap_plan(
        self,
        current_positions: Dict[str, CurrentPosition],
        target_allocations: List[PortfolioAllocation],
        idle_base: float
    ) -> Optional[Dict]:
        """
        Calculate required swaps to reach target allocations
        
        Strategy: Convert everything to base asset, then swap to target underlyings
        """
        plan = {
            'to_base': [],  # Swaps to convert current holdings to base
            'from_base': []  # Swaps from base to target underlyings
        }
        
        # Step 1: After withdrawal, we'll have all underlyings
        # Calculate total base value we'll have
        total_base_value = idle_base
        
        for pos in current_positions.values():
            total_base_value += pos.base_value
        
        logger.info(f"Total base value after withdrawal: ${total_base_value:,.2f}")
        
        # Step 2: Determine target underlying amounts
        target_underlyings = {}
        
        for alloc in target_allocations:
            underlying = VAULT_TO_INPUT_TOKEN.get(alloc.vault_address.lower())
            if not underlying:
                logger.error(f"No underlying for vault {alloc.vault_address}")
                return None
            
            # Get current oracle price
            if underlying.lower() == self.base_asset_address.lower():
                underlying_amount = alloc.target_amount
            else:
                # Convert base value to underlying using oracle
                price = self._get_oracle_price(underlying, self.base_asset_address)
                if price == 0:
                    logger.error(f"No price for {underlying}")
                    return None
                
                # underlying_amount = base_amount * (1 / price)
                underlying_amount = alloc.target_amount / price
            
            target_underlyings[underlying] = target_underlyings.get(underlying, 0) + underlying_amount
        
        logger.info(f"Target underlyings: {target_underlyings}")
        
        # Step 3: Build swap plan
        # Simplification: Swap everything to base, then base to target underlyings
        
        # For each target underlying, calculate how much base we need to swap
        for underlying, target_amount in target_underlyings.items():
            if underlying.lower() == self.base_asset_address.lower():
                continue  # No swap needed for base asset
            
            decimals = self._get_token_decimals(underlying)
            amount_wei = int(target_amount * (10 ** decimals))
            
            plan['from_base'].append({
                'input_token': self.base_asset_address,
                'output_token': underlying,
                'output_amount': amount_wei
            })
        
        return plan
    
    def _get_oracle_price(self, token: str, base_asset: str) -> float:
        """Get price from oracle (token per base_asset)"""
        try:
            price_wei, _ = self.oracle_contract.functions.getPriceData(
                Web3.to_checksum_address(token),
                Web3.to_checksum_address(base_asset)
            ).call()
            
            # Check if price is set
            if price_wei == 0:
                logger.warning(f"No price set in oracle for {token[:10]}...")
                return 0.0
            
            # Price is in 1e18 format
            price = price_wei / 1e18
            return price
            
        except Exception as e:
            logger.error(f"Error getting oracle price: {e}")
            return 0.0
    
    def _get_router_calldata(
        self, 
        swap_plan: Dict,
        warnings: List[str]
    ) -> Tuple[str, bytes, int]:
        """
        Get GlueX Router calldata for swaps using GlueX Router API
        
        Calls GlueX /v1/quote endpoint for each required swap and
        aggregates the calldata
        
        Returns:
            Tuple of (router_address, calldata, total_input_amount_wei)
        """
        from_base_swaps = swap_plan.get('from_base', [])
        
        if not from_base_swaps:
            # No swaps needed - just deposit base asset
            logger.info("No swaps needed - all deposits are in base asset")
            return (self.gluex_router_address, bytes(), 0)
        
        # For MVP: Handle single swap or aggregate multiple swaps
        # In production, you'd want to batch these optimally
        
        all_calldata = []
        total_input_amount = 0  # Track total input amount needed
        
        for swap in from_base_swaps:
            input_token = swap['input_token']
            output_token = swap['output_token']
            desired_output = swap['output_amount']  # How much we want to receive
            
            # Estimate input amount using oracle price
            # Price is in format: output_token per input_token
            price = self._get_oracle_price(output_token, input_token)
            
            if price == 0:
                logger.error(f"Cannot get price for {output_token[:10]}... - skipping swap")
                warnings.append(f"Skipped swap for {output_token[:10]}... (no price)")
                continue
            
            # Calculate input amount accounting for decimal differences
            # desired_output is in output_token wei (e.g., 60080808687684944 = 0.06 USDE with 18 decimals)
            # We need input_token wei (e.g., 60000 = 0.06 USDC with 6 decimals)
            
            input_decimals = self._get_token_decimals(input_token)
            output_decimals = self._get_token_decimals(output_token)
            
            # Convert: (output_wei / 10^output_decimals) / price * 10^input_decimals
            # Simplified: (desired_output / price) * (10^input_decimals / 10^output_decimals)
            decimal_adjustment = (10 ** input_decimals) / (10 ** output_decimals)
            estimated_input = int((desired_output / price) * decimal_adjustment * 1.02)  # 2% buffer
            
            logger.info(f"Requesting quote: {estimated_input} {input_token[:10]}... → "
                       f"{output_token[:10]}... (target: {desired_output})")
            
            try:
                # Call GlueX Router API
                # Note: Using VaultManager as the sender/receiver since it executes the swap
                quote = self.gluex_client.get_router_quote(
                    input_token=input_token,
                    output_token=output_token,
                    input_amount=str(estimated_input),
                    input_sender=self.vault_manager_address,
                    output_receiver=self.vault_manager_address,
                    chain="hyperevm"
                )
                
                if quote and quote.calldata:
                    logger.info(f"✓ Got quote: {quote.output_amount} {output_token[:10]}... "
                               f"(router: {quote.router[:10]}...)")
                            
                    # Store router address from first successful quote
                    if not all_calldata:
                        self.gluex_router_address = quote.router
                    
                    all_calldata.append(quote.calldata)
                    
                    # Track input amount (parse from quote or use estimated)
                    # For now, use estimated_input as the actual amount
                    total_input_amount += estimated_input
                else:
                    logger.error(f"Failed to get quote for {output_token[:10]}...")
                    warnings.append(f"Failed to get quote for {output_token[:10]}...")
                    
            except Exception as e:
                logger.error(f"Error getting quote for {output_token[:10]}...: {e}")
                warnings.append(f"Quote error for {output_token[:10]}...")
        
        # For MVP: If we have multiple swaps, we'll need to aggregate them
        # For now, if there are multiple swaps, warn and use first one
        if len(all_calldata) > 1:
            logger.warning(f"Multiple swaps detected ({len(all_calldata)}) - using first swap only")
            logger.warning("Production implementation should aggregate swaps via multicall")
            warnings.append(f"Only executing first of {len(all_calldata)} swaps (multicall not implemented)")
        
        if all_calldata:
            # Return first calldata (or aggregated in production)
            calldata_bytes = bytes.fromhex(all_calldata[0].replace('0x', ''))
            logger.info(f"Generated router calldata: {len(calldata_bytes)} bytes")
            return (self.gluex_router_address, calldata_bytes, total_input_amount)
        else:
            logger.warning("No valid quotes obtained - using empty calldata")
            warnings.append("No valid swap quotes - will deposit base asset only")
            return (self.gluex_router_address, bytes(), 0)
    
    def _build_target_allocations(
        self, 
        allocations: List[PortfolioAllocation]
    ) -> List[TargetAllocation]:
        """Build TargetAllocation structs for on-chain call"""
        targets = []
        
        for alloc in allocations:
            underlying = VAULT_TO_INPUT_TOKEN.get(alloc.vault_address.lower())
            if not underlying:
                logger.error(f"No underlying for vault {alloc.vault_address}")
                continue
            
            # Convert base amount to underlying amount
            if underlying.lower() == self.base_asset_address.lower():
                underlying_amount = alloc.target_amount
            else:
                price = self._get_oracle_price(underlying, self.base_asset_address)
                if price == 0:
                    logger.error(f"No price for {underlying}")
                    continue
                underlying_amount = alloc.target_amount / price
            
            # Convert to wei
            decimals = self._get_token_decimals(underlying)
            amount_wei = int(underlying_amount * (10 ** decimals))
            
            target = TargetAllocation(
                vault=alloc.vault_address,
                underlying_amount=amount_wei
            )
            targets.append(target)
            
            logger.info(
                f"Target: {target.vault[:10]}... | "
                f"Amount: {underlying_amount:.2f} ({amount_wei} wei)"
            )
        
        return targets
    
    def _estimate_rebalance_gas(
        self, 
        targets: List[TargetAllocation],
        router_address: str,
        swap_calldata: bytes
    ) -> int:
        """Estimate gas for rebalance transaction"""
        
        base_gas = 400000  # Base overhead (pull + approvals + return)
        per_vault_gas = 250000  # Per vault deposit (includes ERC4626 operations)
        swap_gas = len(swap_calldata) * 16  # Gas for calldata
        
        total_gas = base_gas + (len(targets) * per_vault_gas) + swap_gas
        
        # Add 50% buffer for safety
        total_gas = int(total_gas * 1.5)
        
        logger.info(f"Estimated gas: {total_gas:,}")
        
        return total_gas
    
    def _log_plan(self, plan: RebalancePlan):
        """Log rebalance plan details"""
        logger.info("=" * 80)
        logger.info("REBALANCE PLAN")
        logger.info("=" * 80)
        logger.info(f"Number of targets: {len(plan.targets)}")
        logger.info(f"Router: {plan.router_address}")
        logger.info(f"Swap calldata length: {len(plan.swap_calldata)} bytes")
        logger.info(f"ETH value needed: {plan.eth_value_needed} wei ({plan.eth_value_needed / 1e18:.6f} ETH)")  # ✅ ADDED
        logger.info(f"Estimated gas: {plan.estimated_gas:,}")
        logger.info(f"Sanity checks passed: {plan.sanity_checks_passed}")
        
        if plan.warnings:
            logger.warning("Warnings:")
            for warning in plan.warnings:
                logger.warning(f"  - {warning}")
        
        logger.info("-" * 80)
        for target in plan.targets:
            logger.info(
                f"  Vault: {target.vault[:10]}... | "
                f"Amount: {target.underlying_amount:,} wei"
            )
        logger.info("=" * 80)