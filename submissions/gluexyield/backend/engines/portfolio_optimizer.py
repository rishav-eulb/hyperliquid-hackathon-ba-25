"""
Portfolio Optimizer using Sharpe ratio and Risk-Parity weighting
"""

import numpy as np
import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict

from .vault_metrics_engine import VaultMetricsEngine, VaultMetrics

logger = logging.getLogger(__name__)


@dataclass
class PortfolioAllocation:
    """Represents target portfolio allocation"""
    vault_address: str
    weight: float  # Portfolio weight (0-1, sums to 1)
    target_amount: float  # Target base asset amount
    metrics: VaultMetrics
    
    def to_dict(self) -> dict:
        return {
            'vault_address': self.vault_address,
            'weight': self.weight,
            'target_amount': self.target_amount,
            'net_apy': self.metrics.net_apy,
            'sharpe': self.metrics.sharpe_ratio,
            'tvl': self.metrics.tvl
        }


@dataclass
class Portfolio:
    """Complete portfolio with allocations and stats"""
    allocations: List[PortfolioAllocation]
    total_amount: float
    expected_return: float  # Weighted average APY
    portfolio_sharpe: float
    timestamp: float
    
    def to_dict(self) -> dict:
        return {
            'allocations': [a.to_dict() for a in self.allocations],
            'total_amount': self.total_amount,
            'expected_return': self.expected_return,
            'portfolio_sharpe': self.portfolio_sharpe,
            'timestamp': self.timestamp
        }


class PortfolioOptimizer:
    """
    Optimizes portfolio allocation using Sharpe-based selection
    and risk-parity weighting
    """
    
    def __init__(
        self,
        metrics_engine: VaultMetricsEngine,
        min_tvl: float = 0.1,  # $100k minimum TVL
        min_sharpe: float = 0.0,  # Minimum Sharpe ratio
        max_vaults: int = 3,  # Top N vaults to include
        min_net_apy: float = None,  # Minimum net APY (default: risk_free_rate)
        deploy_fraction: float = 0.9  # Deploy 90% of idle
    ):
        """
        Initialize portfolio optimizer
        
        Args:
            metrics_engine: VaultMetricsEngine instance
            min_tvl: Minimum TVL threshold
            min_sharpe: Minimum Sharpe ratio
            max_vaults: Maximum number of vaults in portfolio
            min_net_apy: Minimum net APY (defaults to risk_free_rate)
            deploy_fraction: Fraction of idle assets to deploy
        """
        self.engine = metrics_engine
        self.min_tvl = min_tvl
        self.min_sharpe = min_sharpe
        self.max_vaults = max_vaults
        self.min_net_apy = min_net_apy or metrics_engine.risk_free_rate
        self.deploy_fraction = deploy_fraction
        
        self.current_portfolio: Optional[Portfolio] = None
        
        logger.info(f"PortfolioOptimizer initialized: min_tvl=${min_tvl:,.0f}, "
                   f"min_sharpe={min_sharpe:.2f}, max_vaults={max_vaults}")
    
    def optimize(
        self,
        vault_addresses: List[str],
        total_investable_base: float,
        input_amount: str,
        force_refresh: bool = False
    ) -> Portfolio:
        """
        Optimize portfolio allocation
        
        Args:
            vault_addresses: List of candidate vault addresses
            total_investable_base: Total base assets available
            input_amount: Amount for APY calculations
            force_refresh: Force metrics refresh
            
        Returns:
            Optimized Portfolio
        """
        import time
        
        logger.info(f"Starting portfolio optimization with "
                   f"${total_investable_base:,.2f} total investable")
        
        # Step 1: Get metrics for all vaults
        all_metrics = self.engine.get_multiple_metrics(
            vault_addresses, 
            input_amount, 
            force_refresh
        )
        
        if not all_metrics:
            logger.error("No vault metrics available")
            return self._empty_portfolio(time.time())
        
        logger.info(f"Retrieved metrics for {len(all_metrics)} vaults")
        
        # Step 2: Filter vaults by safety criteria
        filtered = self._filter_vaults(all_metrics)
        
        if not filtered:
            logger.warning("No vaults passed filtering criteria")
            return self._empty_portfolio(time.time())
        
        logger.info(f"{len(filtered)} vaults passed filtering")
        
        # Step 3: Select top N by Sharpe ratio
        selected = self._select_top_vaults(filtered)
        
        logger.info(f"Selected top {len(selected)} vaults for portfolio")
        
        # Step 4: Compute risk-parity weights
        weights = self._compute_risk_parity_weights(selected)
        
        # Step 5: Calculate target allocations
        target_deploy = total_investable_base * self.deploy_fraction
        allocations = []
        
        for vault_addr, weight in weights.items():
            target_amount = weight * target_deploy
            allocations.append(PortfolioAllocation(
                vault_address=vault_addr,
                weight=weight,
                target_amount=target_amount,
                metrics=selected[vault_addr]
            ))
        
        # Step 6: Compute portfolio statistics
        expected_return = sum(a.weight * a.metrics.net_apy for a in allocations)
        
        # Portfolio Sharpe (simplified - assumes uncorrelated vaults)
        portfolio_sharpe = self._compute_portfolio_sharpe(allocations)
        
        portfolio = Portfolio(
            allocations=allocations,
            total_amount=target_deploy,
            expected_return=expected_return,
            portfolio_sharpe=portfolio_sharpe,
            timestamp=time.time()
        )
        
        # Don't set current_portfolio here - it should only be set after successful rebalance
        # This allows should_rebalance() to properly compare old vs new portfolio
        
        self._log_portfolio(portfolio)
        
        return portfolio
    
    def _filter_vaults(
        self, 
        metrics_dict: Dict[str, VaultMetrics]
    ) -> Dict[str, VaultMetrics]:
        """
        Filter vaults by safety criteria
        
        Removes:
        - Low TVL vaults
        - Negative or low Sharpe ratios
        - APY below risk-free rate
        """
        filtered = {}
        
        for vault_addr, metrics in metrics_dict.items():
            # Check TVL
            if metrics.tvl < self.min_tvl:
                logger.debug(f"Filtering {vault_addr[:10]}... - Low TVL: ${metrics.tvl:,.0f}")
                continue
            
            # Check Sharpe
            if metrics.sharpe_ratio < self.min_sharpe:
                logger.debug(f"Filtering {vault_addr[:10]}... - Low Sharpe: {metrics.sharpe_ratio:.3f}")
                continue
            
            # Check APY vs risk-free rate
            if metrics.net_apy / 100.0 < self.min_net_apy:
                logger.debug(f"Filtering {vault_addr[:10]}... - Low APY: {metrics.net_apy:.2f}%")
                continue
            
            # Passed all filters
            filtered[vault_addr] = metrics
            logger.debug(f"Vault {vault_addr[:10]}... passed filtering - "
                        f"Sharpe: {metrics.sharpe_ratio:.3f}, APY: {metrics.net_apy:.2f}%, "
                        f"TVL: ${metrics.tvl:,.0f}")
        
        return filtered
    
    def _select_top_vaults(
        self, 
        filtered_metrics: Dict[str, VaultMetrics]
    ) -> Dict[str, VaultMetrics]:
        """
        Select top N vaults by Sharpe ratio
        """
        # Sort by Sharpe ratio descending
        sorted_vaults = sorted(
            filtered_metrics.items(),
            key=lambda x: x[1].sharpe_ratio,
            reverse=True
        )
        
        # Take top N
        top_n = sorted_vaults[:self.max_vaults]
        
        return dict(top_n)
    
    def _compute_risk_parity_weights(
        self, 
        selected_metrics: Dict[str, VaultMetrics]
    ) -> Dict[str, float]:
        """
        Compute risk-parity weights (inverse volatility)
        
        Lower volatility → higher weight
        Higher volatility → lower weight
        
        Formula:
            inv_sigma_i = 1 / sigma_i
            weight_i = inv_sigma_i / sum(inv_sigma_j for all j)
        """
        if not selected_metrics:
            return {}
        
        # Compute inverse volatilities
        inv_vols = {}
        for vault_addr, metrics in selected_metrics.items():
            # Use volatility in decimal form (not percentage)
            vol = max(metrics.apy_volatility / 100.0, 1e-6)  # Avoid division by zero
            inv_vols[vault_addr] = 1.0 / vol
        
        # Normalize to sum to 1
        total_inv_vol = sum(inv_vols.values())
        weights = {
            vault_addr: inv_vol / total_inv_vol 
            for vault_addr, inv_vol in inv_vols.items()
        }
        
        # Log weights
        for vault_addr, weight in weights.items():
            metrics = selected_metrics[vault_addr]
            logger.info(
                f"Vault {vault_addr[:10]}... weight: {weight:.2%} "
                f"(vol: {metrics.apy_volatility:.2f}%)"
            )
        
        return weights
    
    def _compute_portfolio_sharpe(
        self, 
        allocations: List[PortfolioAllocation]
    ) -> float:
        """
        Compute portfolio Sharpe ratio
        
        Simplified calculation assuming uncorrelated returns
        """
        if not allocations:
            return 0.0
        
        # Weighted average excess return
        excess_returns = [
            a.weight * ((a.metrics.net_apy / 100.0) - a.metrics.risk_free_rate)
            for a in allocations
        ]
        portfolio_excess_return = sum(excess_returns)
        
        # Portfolio volatility (assuming uncorrelated - simplified)
        portfolio_variance = sum(
            (a.weight * a.metrics.apy_volatility / 100.0) ** 2
            for a in allocations
        )
        portfolio_vol = np.sqrt(portfolio_variance)
        
        if portfolio_vol == 0:
            return 0.0
        
        return portfolio_excess_return / portfolio_vol
    
    def should_rebalance(
        self,
        new_portfolio: Portfolio,
        drift_threshold: float = 0.10,  # 10% drift
        min_sharpe_improvement: float = 0.05  # 5% improvement
    ) -> Tuple[bool, str]:
        """
        Determine if portfolio should be rebalanced
        
        Args:
            new_portfolio: Newly optimized portfolio
            drift_threshold: Minimum drift to trigger rebalance (fraction)
            min_sharpe_improvement: Minimum Sharpe improvement to trigger
            
        Returns:
            (should_rebalance, reason)
        """
        if self.current_portfolio is None:
            return True, "No current portfolio"
        
        # Check 1: Sharpe improvement
        sharpe_change = (
            new_portfolio.portfolio_sharpe - self.current_portfolio.portfolio_sharpe
        )
        sharpe_pct_change = sharpe_change / max(abs(self.current_portfolio.portfolio_sharpe), 1e-6)
        
        if sharpe_pct_change > min_sharpe_improvement:
            return True, f"Sharpe improved by {sharpe_pct_change:.2%}"
        
        # Check 2: Allocation drift
        drift = self._compute_drift(new_portfolio)
        
        if drift > drift_threshold:
            return True, f"Allocation drift {drift:.2%} exceeds threshold"
        
        # Check 3: Risk boundary crossed (simplified)
        # You could add more sophisticated checks here
        
        return False, f"No rebalance needed (drift={drift:.2%}, sharpe_change={sharpe_pct_change:.2%})"
    
    def _compute_drift(self, new_portfolio: Portfolio) -> float:
        """
        Compute total allocation drift
        
        drift = sum(|new_weight_i - old_weight_i|) / 2
        """
        if self.current_portfolio is None:
            return 1.0  # 100% drift if no current portfolio
        
        # Build weight maps
        old_weights = {
            a.vault_address: a.weight 
            for a in self.current_portfolio.allocations
        }
        new_weights = {
            a.vault_address: a.weight 
            for a in new_portfolio.allocations
        }
        
        # Get all vaults (union)
        all_vaults = set(old_weights.keys()) | set(new_weights.keys())
        
        # Compute drift
        total_drift = sum(
            abs(new_weights.get(v, 0) - old_weights.get(v, 0))
            for v in all_vaults
        )
        
        return total_drift / 2.0  # Normalize
    
    def _empty_portfolio(self, timestamp: float) -> Portfolio:
        """Create an empty portfolio"""
        return Portfolio(
            allocations=[],
            total_amount=0.0,
            expected_return=0.0,
            portfolio_sharpe=0.0,
            timestamp=timestamp
        )
    
    def _log_portfolio(self, portfolio: Portfolio):
        """Log portfolio details"""
        logger.info("=" * 80)
        logger.info("OPTIMIZED PORTFOLIO")
        logger.info("=" * 80)
        logger.info(f"Total Amount: ${portfolio.total_amount:,.2f}")
        logger.info(f"Expected Return: {portfolio.expected_return:.2f}%")
        logger.info(f"Portfolio Sharpe: {portfolio.portfolio_sharpe:.3f}")
        logger.info(f"Number of Vaults: {len(portfolio.allocations)}")
        logger.info("-" * 80)
        
        for alloc in portfolio.allocations:
            logger.info(
                f"  {alloc.vault_address[:10]}... | "
                f"Weight: {alloc.weight:6.2%} | "
                f"Amount: ${alloc.target_amount:10,.0f} | "
                f"APY: {alloc.metrics.net_apy:5.2f}% | "
                f"Sharpe: {alloc.metrics.sharpe_ratio:5.3f}"
            )
        
        logger.info("=" * 80)

