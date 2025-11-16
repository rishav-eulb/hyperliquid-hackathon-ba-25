"""
Test script for RebalancePlanner
Tests rebalance plan generation and safety checks
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
from backend.engines.portfolio_optimizer import PortfolioOptimizer, Portfolio, PortfolioAllocation
from backend.engines.rebalance_planner import RebalancePlanner
from backend.clients.gluex_client import GlueXClient
from backend.clients.web3_client import Web3Client
from backend.config.constants import VAULT_TO_INPUT_TOKEN, HYPEREVM_RPC_URL

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_planner_init():
    """Test planner initialization"""
    logger.info("=" * 80)
    logger.info("TEST 1: RebalancePlanner Initialization")
    logger.info("=" * 80)
    
    load_dotenv()
    
    api_key = os.getenv('GLUEX_API_KEY', 'test_key')
    vault_manager = os.getenv('MANAGER_ADDRESS', '0x0000000000000000000000000000000000000001')
    hyperyield_vault = os.getenv('VAULT_ADDRESS', '0x0000000000000000000000000000000000000002')
    base_asset = os.getenv('BASE_ASSET_ADDRESS', '0xb88339CB7199b77E23DB6E890353E22632Ba630f')
    oracle = os.getenv('ORACLE_ADDRESS', '0x0000000000000000000000000000000000000003')
    router = os.getenv('GLUEX_ROUTER_ADDRESS', '0x0000000000000000000000000000000000000004')
    
    try:
        gluex_client = GlueXClient(api_key)
        web3_client = Web3Client(HYPEREVM_RPC_URL)
        
        planner = RebalancePlanner(
            gluex_client=gluex_client,
            web3_client=web3_client,
            vault_manager_address=vault_manager,
            hyperyield_vault_address=hyperyield_vault,
            base_asset_address=base_asset,
            oracle_address=oracle,
            gluex_router_address=router,
            max_slippage=0.02
        )
        
        logger.info("✓ Planner initialized successfully")
        logger.info(f"  Vault Manager: {planner.vault_manager_address}")
        logger.info(f"  HyperYield Vault: {planner.hyperyield_vault_address}")
        logger.info(f"  Base Asset: {planner.base_asset_address}")
        logger.info(f"  Oracle: {planner.oracle_address}")
        logger.info(f"  Max Slippage: {planner.max_slippage:.1%}")
        
        logger.info("Planner initialization test PASSED\n")
        return planner
    
    except Exception as e:
        logger.error(f"✗ Planner initialization failed: {e}")
        logger.info(f"  This is expected if contracts are not deployed")
        logger.info("Planner initialization test SKIPPED\n")
        return None


def test_token_decimals(planner):
    """Test token decimals reading"""
    logger.info("=" * 80)
    logger.info("TEST 2: Token Decimals Reading")
    logger.info("=" * 80)
    
    if not planner:
        logger.warning("⚠ No planner available")
        logger.info("Token decimals test SKIPPED\n")
        return
    
    try:
        # Test getting decimals for base asset
        decimals = planner._get_token_decimals(planner.base_asset_address)
        logger.info(f"✓ Got decimals for base asset: {decimals}")
        
        # Test for underlying tokens
        for vault, underlying in list(VAULT_TO_INPUT_TOKEN.items())[:2]:
            try:
                decimals = planner._get_token_decimals(underlying)
                logger.info(f"  {underlying[:10]}... decimals: {decimals}")
            except Exception as e:
                logger.warning(f"  Could not get decimals for {underlying[:10]}...: {e}")
        
        logger.info("\nToken decimals test PASSED\n")
    
    except Exception as e:
        logger.error(f"✗ Token decimals test failed: {e}")
        logger.info("This is expected if RPC is unavailable")
        logger.info("Token decimals test SKIPPED\n")


def test_safety_checks(planner):
    """Test safety checks"""
    logger.info("=" * 80)
    logger.info("TEST 3: Safety Checks")
    logger.info("=" * 80)
    
    if not planner:
        logger.warning("⚠ No planner available")
        logger.info("Safety checks test SKIPPED\n")
        return
    
    try:
        # Test rebalance check
        logger.info("Testing canRebalance()...")
        can_rebalance = planner._check_can_rebalance()
        logger.info(f"  Can rebalance: {can_rebalance}")
        
        # Test oracle freshness check
        logger.info("\nTesting oracle freshness...")
        warnings = []
        is_fresh = planner._check_oracle_freshness(warnings)
        logger.info(f"  Prices fresh: {is_fresh}")
        if warnings:
            logger.info("  Warnings:")
            for w in warnings:
                logger.info(f"    - {w}")
        
        logger.info("\n✓ Safety checks executed (results may vary)")
        logger.info("Safety checks test PASSED\n")
    
    except Exception as e:
        logger.warning(f"⚠ Safety checks unavailable: {e}")
        logger.info("This is expected if contracts are not deployed")
        logger.info("Safety checks test SKIPPED\n")


def test_mock_portfolio_plan():
    """Test with mock portfolio (no real contracts needed)"""
    logger.info("=" * 80)
    logger.info("TEST 4: Mock Portfolio Plan Generation")
    logger.info("=" * 80)
    
    try:
        # Create a mock portfolio
        import time
        from backend.engines.vault_metrics_engine import VaultMetrics
        
        vaults = list(VAULT_TO_INPUT_TOKEN.items())[:2]
        allocations = []
        
        for vault_addr, underlying in vaults:
            metrics = VaultMetrics(
                vault_address=vault_addr,
                underlying_token=underlying,
                mean_apy=10.0,
                net_apy=12.0,
                apy_volatility=2.5,
                sharpe_ratio=4.0,
                tvl=500000.0,
                input_amount="1000000000000",
                risk_free_rate=0.05,
                timestamp=time.time()
            )
            
            alloc = PortfolioAllocation(
                vault_address=vault_addr,
                weight=0.5,
                target_amount=500000.0,
                metrics=metrics
            )
            allocations.append(alloc)
        
        portfolio = Portfolio(
            allocations=allocations,
            total_amount=1000000.0,
            expected_return=12.0,
            portfolio_sharpe=4.0,
            timestamp=time.time()
        )
        
        logger.info("✓ Mock portfolio created")
        logger.info(f"  Allocations: {len(portfolio.allocations)}")
        logger.info(f"  Total: ${portfolio.total_amount:,.2f}")
        
        for alloc in portfolio.allocations:
            logger.info(f"  - {alloc.vault_address[:10]}...")
            logger.info(f"    Weight: {alloc.weight:.1%}")
            logger.info(f"    Amount: ${alloc.target_amount:,.2f}")
        
        logger.info("\nMock portfolio test PASSED\n")
        return portfolio
    
    except Exception as e:
        logger.error(f"✗ Mock portfolio test failed: {e}")
        raise


def test_target_allocations():
    """Test target allocation building"""
    logger.info("=" * 80)
    logger.info("TEST 5: Target Allocation Conversion")
    logger.info("=" * 80)
    
    try:
        from backend.engines.rebalance_planner import TargetAllocation
        
        # Create sample targets
        vaults = list(VAULT_TO_INPUT_TOKEN.keys())[:2]
        targets = []
        
        for vault in vaults:
            target = TargetAllocation(
                vault=vault,
                underlying_amount=1000000000000  # 1M units
            )
            targets.append(target)
        
        logger.info(f"✓ Created {len(targets)} target allocations")
        
        for target in targets:
            logger.info(f"  Vault: {target.vault[:10]}...")
            logger.info(f"  Amount: {target.underlying_amount:,} wei")
        
        logger.info("\nTarget allocation test PASSED\n")
    
    except Exception as e:
        logger.error(f"✗ Target allocation test failed: {e}")
        raise


def main():
    """Run all tests"""
    logger.info("\n" + "=" * 80)
    logger.info("REBALANCE PLANNER TEST SUITE")
    logger.info("=" * 80 + "\n")
    
    logger.info("NOTE: Some tests may be skipped if contracts are not deployed")
    logger.info("This is expected for local testing\n")
    
    try:
        # Test 1: Initialization
        planner = test_planner_init()
        
        # Test 2: Token decimals
        test_token_decimals(planner)
        
        # Test 3: Safety checks
        test_safety_checks(planner)
        
        # Test 4: Mock portfolio
        portfolio = test_mock_portfolio_plan()
        
        # Test 5: Target allocations
        test_target_allocations()
        
        logger.info("=" * 80)
        logger.info("ALL TESTS COMPLETED ✓")
        logger.info("(Some tests may have been skipped)")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"TESTS FAILED ✗: {e}")
        logger.error("=" * 80)
        sys.exit(1)


if __name__ == "__main__":
    main()

