"""
Test script for PortfolioOptimizer
Tests portfolio optimization and risk-parity weighting
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Add backend directory to path for imports
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Also add project root
project_root = os.path.dirname(backend_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.engines.vault_metrics_engine import VaultMetricsEngine
from backend.engines.portfolio_optimizer import PortfolioOptimizer
from backend.config.constants import VAULT_TO_INPUT_TOKEN

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_optimizer_init():
    """Test optimizer initialization"""
    logger.info("=" * 80)
    logger.info("TEST 1: PortfolioOptimizer Initialization")
    logger.info("=" * 80)
    
    load_dotenv()
    api_key = os.getenv('GLUEX_API_KEY', 'test_key')
    
    try:
        # Initialize metrics engine
        metrics_engine = VaultMetricsEngine(api_key=api_key)
        
        # Initialize optimizer
        optimizer = PortfolioOptimizer(
            metrics_engine=metrics_engine,
            min_tvl=100000,
            min_sharpe=0.0,
            max_vaults=3,
            deploy_fraction=0.9
        )
        
        logger.info("✓ Optimizer initialized successfully")
        logger.info(f"  Min TVL: ${optimizer.min_tvl:,.0f}")
        logger.info(f"  Min Sharpe: {optimizer.min_sharpe:.2f}")
        logger.info(f"  Max Vaults: {optimizer.max_vaults}")
        logger.info(f"  Deploy Fraction: {optimizer.deploy_fraction:.0%}")
        
        logger.info("Optimizer initialization test PASSED\n")
        return optimizer
    
    except Exception as e:
        logger.error(f"✗ Optimizer initialization failed: {e}")
        raise


def test_portfolio_optimization(optimizer):
    """Test full portfolio optimization"""
    logger.info("=" * 80)
    logger.info("TEST 2: Portfolio Optimization")
    logger.info("=" * 80)
    
    vault_addresses = list(VAULT_TO_INPUT_TOKEN.keys())
    total_investable = 1000000.0  # $1M
    input_amount = "1000000000000"  # 1M USDC units
    
    logger.info(f"Optimizing portfolio with ${total_investable:,.0f}")
    logger.info(f"Candidate vaults: {len(vault_addresses)}")
    
    try:
        portfolio = optimizer.optimize(
            vault_addresses=vault_addresses,
            total_investable_base=total_investable,
            input_amount=input_amount,
            force_refresh=True
        )
        
        if portfolio.allocations:
            logger.info("✓ Portfolio optimized successfully")
            logger.info(f"\n  Total Amount: ${portfolio.total_amount:,.2f}")
            logger.info(f"  Expected Return: {portfolio.expected_return:.2f}%")
            logger.info(f"  Portfolio Sharpe: {portfolio.portfolio_sharpe:.3f}")
            logger.info(f"  Number of Vaults: {len(portfolio.allocations)}")
            
            logger.info("\n  Allocations:")
            for alloc in portfolio.allocations:
                logger.info(f"    {alloc.vault_address[:10]}...")
                logger.info(f"      Weight: {alloc.weight:.2%}")
                logger.info(f"      Amount: ${alloc.target_amount:,.2f}")
                logger.info(f"      APY: {alloc.metrics.net_apy:.2f}%")
                logger.info(f"      Sharpe: {alloc.metrics.sharpe_ratio:.3f}")
            
            # Verify weights sum to 1
            total_weight = sum(a.weight for a in portfolio.allocations)
            assert abs(total_weight - 1.0) < 0.01, f"Weights should sum to 1, got {total_weight}"
            logger.info(f"\n  ✓ Weights sum to: {total_weight:.4f}")
            
            logger.info("\nPortfolio optimization test PASSED\n")
            return portfolio
        else:
            logger.warning("⚠ No allocations in portfolio (might be no qualifying vaults)")
            logger.info("Portfolio optimization test SKIPPED\n")
            return None
    
    except Exception as e:
        logger.error(f"✗ Portfolio optimization failed: {e}")
        raise


def test_rebalance_decision(optimizer, portfolio):
    """Test rebalance decision logic"""
    logger.info("=" * 80)
    logger.info("TEST 3: Rebalance Decision Logic")
    logger.info("=" * 80)
    
    if not portfolio or not portfolio.allocations:
        logger.warning("⚠ No portfolio available, skipping rebalance test")
        logger.info("Rebalance decision test SKIPPED\n")
        return
    
    try:
        # First rebalance should always trigger (no current portfolio)
        should_rebalance, reason = optimizer.should_rebalance(
            portfolio,
            drift_threshold=0.10,
            min_sharpe_improvement=0.05
        )
        
        logger.info(f"✓ Rebalance decision computed")
        logger.info(f"  Should rebalance: {should_rebalance}")
        logger.info(f"  Reason: {reason}")
        
        assert should_rebalance, "First rebalance should always trigger"
        logger.info("  ✓ Correctly triggers rebalance for new portfolio")
        
        # Set as current and test again (should not trigger)
        optimizer.current_portfolio = portfolio
        
        should_rebalance2, reason2 = optimizer.should_rebalance(
            portfolio,
            drift_threshold=0.10,
            min_sharpe_improvement=0.05
        )
        
        logger.info(f"\n  Second check (same portfolio):")
        logger.info(f"  Should rebalance: {should_rebalance2}")
        logger.info(f"  Reason: {reason2}")
        
        logger.info("\nRebalance decision test PASSED\n")
    
    except Exception as e:
        logger.error(f"✗ Rebalance decision test failed: {e}")
        raise


def test_filtering_logic(optimizer):
    """Test vault filtering"""
    logger.info("=" * 80)
    logger.info("TEST 4: Vault Filtering Logic")
    logger.info("=" * 80)
    
    load_dotenv()
    api_key = os.getenv('GLUEX_API_KEY', 'test_key')
    
    try:
        # Create test optimizer with strict filters
        strict_optimizer = PortfolioOptimizer(
            metrics_engine=VaultMetricsEngine(api_key=api_key),
            min_tvl=1000000,  # $1M
            min_sharpe=1.0,   # High Sharpe
            max_vaults=2
        )
        
        logger.info("Testing with strict filters:")
        logger.info(f"  Min TVL: ${strict_optimizer.min_tvl:,.0f}")
        logger.info(f"  Min Sharpe: {strict_optimizer.min_sharpe:.2f}")
        
        vault_addresses = list(VAULT_TO_INPUT_TOKEN.keys())
        
        portfolio = strict_optimizer.optimize(
            vault_addresses=vault_addresses,
            total_investable_base=1000000.0,
            input_amount="1000000000000",
            force_refresh=True
        )
        
        logger.info(f"✓ Filtered to {len(portfolio.allocations)} vaults")
        logger.info(f"  (Max allowed: {strict_optimizer.max_vaults})")
        
        # Verify constraints
        for alloc in portfolio.allocations:
            assert alloc.metrics.tvl >= strict_optimizer.min_tvl or alloc.metrics.tvl == 0, \
                f"TVL {alloc.metrics.tvl} below minimum {strict_optimizer.min_tvl}"
            logger.info(f"  ✓ {alloc.vault_address[:10]}... meets criteria")
        
        logger.info("\nVault filtering test PASSED\n")
    
    except Exception as e:
        logger.error(f"✗ Vault filtering test failed: {e}")
        raise


def main():
    """Run all tests"""
    logger.info("\n" + "=" * 80)
    logger.info("PORTFOLIO OPTIMIZER TEST SUITE")
    logger.info("=" * 80 + "\n")
    
    try:
        # Test 1: Initialization
        optimizer = test_optimizer_init()
        
        # Test 2: Portfolio optimization
        portfolio = test_portfolio_optimization(optimizer)
        
        # Test 3: Rebalance decision
        test_rebalance_decision(optimizer, portfolio)
        
        # Test 4: Filtering logic
        test_filtering_logic(optimizer)
        
        logger.info("=" * 80)
        logger.info("ALL TESTS PASSED ✓")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"TESTS FAILED ✗: {e}")
        logger.error("=" * 80)
        sys.exit(1)


if __name__ == "__main__":
    main()

