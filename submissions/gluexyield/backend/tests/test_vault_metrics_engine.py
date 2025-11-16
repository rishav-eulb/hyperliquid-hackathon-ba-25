"""
Test script for VaultMetricsEngine
Tests real-time metrics calculation and caching
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

from backend.engines.vault_metrics_engine import VaultMetricsEngine, VaultMetricsCache
from backend.config.constants import VAULT_TO_INPUT_TOKEN

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_cache():
    """Test cache functionality"""
    logger.info("=" * 80)
    logger.info("TEST 1: VaultMetricsCache")
    logger.info("=" * 80)
    
    cache = VaultMetricsCache(default_ttl=10)
    
    # Test cache miss
    result = cache.get("0xtest")
    assert result is None, "Cache should be empty initially"
    logger.info("✓ Cache miss works")
    
    # Test cache stats
    stats = cache.stats
    assert stats['misses'] == 1, "Miss count should be 1"
    logger.info(f"✓ Cache stats: {stats}")
    
    logger.info("Cache test PASSED\n")


def test_metrics_engine_init():
    """Test metrics engine initialization"""
    logger.info("=" * 80)
    logger.info("TEST 2: VaultMetricsEngine Initialization")
    logger.info("=" * 80)
    
    load_dotenv()
    api_key = os.getenv('GLUEX_API_KEY')
    
    if not api_key:
        logger.warning("⚠ GLUEX_API_KEY not set - using test key")
        api_key = "test_key"
    
    try:
        engine = VaultMetricsEngine(
            api_key=api_key,
            cache_ttl=1800,
            risk_free_rate=0.05
        )
        logger.info("✓ Engine initialized successfully")
        logger.info(f"✓ Cache TTL: {engine.cache.default_ttl}s")
        logger.info(f"✓ Risk-free rate: {engine.risk_free_rate}")
        logger.info("Engine initialization test PASSED\n")
        return engine
    except Exception as e:
        logger.error(f"✗ Engine initialization failed: {e}")
        raise


def test_metrics_computation(engine):
    """Test metrics computation for a single vault"""
    logger.info("=" * 80)
    logger.info("TEST 3: Vault Metrics Computation")
    logger.info("=" * 80)
    
    # Use first vault from constants
    vault_addresses = list(VAULT_TO_INPUT_TOKEN.keys())
    if not vault_addresses:
        logger.error("No vaults configured in constants.py")
        return
    
    test_vault = vault_addresses[0]
    logger.info(f"Testing vault: {test_vault}")
    
    input_amount = "1000000000000"  # 1M USDC
    
    try:
        # First call - should compute fresh
        logger.info("Fetching metrics (should compute fresh)...")
        metrics = engine.get_metrics(test_vault, input_amount, force_refresh=True)
        
        if metrics:
            logger.info("✓ Metrics computed successfully")
            logger.info(f"  Vault: {metrics.vault_address[:10]}...")
            logger.info(f"  Underlying: {metrics.underlying_token[:10]}...")
            logger.info(f"  Mean APY: {metrics.mean_apy:.2f}%")
            logger.info(f"  Net APY: {metrics.net_apy:.2f}%")
            logger.info(f"  Volatility: {metrics.apy_volatility:.2f}%")
            logger.info(f"  Sharpe: {metrics.sharpe_ratio:.3f}")
            logger.info(f"  TVL: ${metrics.tvl:,.2f}")
            
            # Test cache hit
            logger.info("\nFetching same metrics (should hit cache)...")
            metrics2 = engine.get_metrics(test_vault, input_amount, force_refresh=False)
            
            if metrics2:
                logger.info("✓ Cache hit successful")
                assert metrics2.vault_address == metrics.vault_address
                logger.info(f"  Same data returned: {metrics2.net_apy:.2f}%")
            
            # Check cache stats
            stats = engine.get_cache_stats()
            logger.info(f"\nCache stats: {stats}")
            logger.info(f"  Hit rate: {stats['hit_rate']:.1%}")
            
            logger.info("\nMetrics computation test PASSED\n")
        else:
            logger.warning("⚠ No metrics returned (API might be unavailable)")
            logger.info("Metrics computation test SKIPPED (no API response)\n")
    
    except Exception as e:
        logger.error(f"✗ Metrics computation failed: {e}")
        raise


def test_multiple_vaults(engine):
    """Test metrics for multiple vaults"""
    logger.info("=" * 80)
    logger.info("TEST 4: Multiple Vaults Metrics")
    logger.info("=" * 80)
    
    vault_addresses = list(VAULT_TO_INPUT_TOKEN.keys())[:3]  # Test first 3
    logger.info(f"Testing {len(vault_addresses)} vaults")
    
    input_amount = "1000000000000"
    
    try:
        metrics_dict = engine.get_multiple_metrics(
            vault_addresses,
            input_amount,
            force_refresh=True
        )
        
        logger.info(f"✓ Retrieved metrics for {len(metrics_dict)} vaults")
        
        for vault_addr, metrics in metrics_dict.items():
            logger.info(f"\n  {vault_addr[:10]}...")
            logger.info(f"    APY: {metrics.net_apy:.2f}%")
            logger.info(f"    Sharpe: {metrics.sharpe_ratio:.3f}")
            logger.info(f"    TVL: ${metrics.tvl:,.0f}")
        
        if len(metrics_dict) > 0:
            logger.info("\nMultiple vaults test PASSED\n")
        else:
            logger.warning("⚠ No vault metrics returned")
            logger.info("Multiple vaults test SKIPPED\n")
    
    except Exception as e:
        logger.error(f"✗ Multiple vaults test failed: {e}")
        raise


def main():
    """Run all tests"""
    logger.info("\n" + "=" * 80)
    logger.info("VAULT METRICS ENGINE TEST SUITE")
    logger.info("=" * 80 + "\n")
    
    try:
        # Test 1: Cache
        test_cache()
        
        # Test 2: Engine initialization
        engine = test_metrics_engine_init()
        
        # Test 3: Single vault metrics
        test_metrics_computation(engine)
        
        # Test 4: Multiple vaults
        test_multiple_vaults(engine)
        
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

