"""
Real-Time Vault Metrics Engine with Caching
Calculates yield/risk metrics on-demand and caches results
"""

import time
import numpy as np
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

from ..clients.gluex_client import GlueXClient
from ..config.constants import VAULT_TO_INPUT_TOKEN, HYPEREVM_RPC_URL

logger = logging.getLogger(__name__)


@dataclass
class VaultMetrics:
    """Complete risk/yield metrics for a vault"""
    vault_address: str
    underlying_token: str
    
    # APY Metrics
    mean_apy: float  # μᵢ from historical
    net_apy: float   # forward-looking from diluted
    
    # Risk Metrics
    apy_volatility: float  # σᵢ = stddev of APY
    sharpe_ratio: float    # (net_apy - rf) / volatility
    
    # Context
    tvl: float
    input_amount: str
    risk_free_rate: float
    
    # Metadata
    timestamp: float
    cache_ttl: int = 1800  # 30 minutes default
    
    def is_stale(self, max_age: int = None) -> bool:
        """Check if metrics are stale"""
        max_age = max_age or self.cache_ttl
        age = time.time() - self.timestamp
        return age > max_age
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return asdict(self)


class VaultMetricsCache:
    """In-memory cache for vault metrics"""
    
    def __init__(self, default_ttl: int = 1800):
        """
        Initialize cache
        
        Args:
            default_ttl: Default time-to-live in seconds (30 min)
        """
        self._cache: Dict[str, VaultMetrics] = {}
        self.default_ttl = default_ttl
        self.stats = {
            'hits': 0,
            'misses': 0,
            'updates': 0
        }
    
    def get(self, vault_address: str) -> Optional[VaultMetrics]:
        """Get metrics from cache if fresh"""
        vault_address = vault_address.lower()
        
        if vault_address in self._cache:
            metrics = self._cache[vault_address]
            if not metrics.is_stale():
                self.stats['hits'] += 1
                logger.debug(f"Cache HIT for {vault_address[:10]}...")
                return metrics
            else:
                logger.debug(f"Cache STALE for {vault_address[:10]}...")
        
        self.stats['misses'] += 1
        return None
    
    def set(self, vault_address: str, metrics: VaultMetrics):
        """Store metrics in cache"""
        vault_address = vault_address.lower()
        self._cache[vault_address] = metrics
        self.stats['updates'] += 1
        logger.debug(f"Cache UPDATE for {vault_address[:10]}...")
    
    def invalidate(self, vault_address: str = None):
        """Invalidate cache for specific vault or all"""
        if vault_address:
            self._cache.pop(vault_address.lower(), None)
        else:
            self._cache.clear()
    
    def get_all_fresh(self) -> Dict[str, VaultMetrics]:
        """Get all fresh metrics from cache"""
        return {
            addr: metrics 
            for addr, metrics in self._cache.items() 
            if not metrics.is_stale()
        }


class VaultMetricsEngine:
    """
    Real-time vault metrics computation with caching
    """
    
    def __init__(
        self, 
        api_key: str, 
        rpc_url: str = None,
        cache_ttl: int = 1800,
        risk_free_rate: float = 0.05
    ):
        """
        Initialize metrics engine
        
        Args:
            api_key: GlueX API key
            rpc_url: RPC URL for blockchain
            cache_ttl: Cache time-to-live in seconds
            risk_free_rate: Risk-free rate for Sharpe calculation
        """
        self.client = GlueXClient(api_key, rpc_url or HYPEREVM_RPC_URL)
        self.cache = VaultMetricsCache(cache_ttl)
        self.risk_free_rate = risk_free_rate
        logger.info("VaultMetricsEngine initialized")
    
    def get_metrics(
        self, 
        vault_address: str, 
        input_amount: str,
        force_refresh: bool = False
    ) -> Optional[VaultMetrics]:
        """
        Get vault metrics (from cache or compute fresh)
        
        Args:
            vault_address: Vault address
            input_amount: Deployment size for diluted APY
            force_refresh: Force recomputation even if cached
            
        Returns:
            VaultMetrics or None on error
        """
        vault_address = vault_address.lower()
        
        # Check cache first
        if not force_refresh:
            cached = self.cache.get(vault_address)
            if cached:
                return cached
        
        # Compute fresh metrics
        logger.info(f"Computing fresh metrics for {vault_address[:10]}...")
        metrics = self._compute_metrics(vault_address, input_amount)
        
        if metrics:
            self.cache.set(vault_address, metrics)
        
        return metrics
    
    def get_multiple_metrics(
        self,
        vault_addresses: List[str],
        input_amount: str,
        force_refresh: bool = False
    ) -> Dict[str, VaultMetrics]:
        """
        Get metrics for multiple vaults
        
        Args:
            vault_addresses: List of vault addresses
            input_amount: Deployment size
            force_refresh: Force refresh all
            
        Returns:
            Dictionary mapping vault addresses to metrics
        """
        results = {}
        
        for vault in vault_addresses:
            metrics = self.get_metrics(vault, input_amount, force_refresh)
            if metrics:
                results[vault.lower()] = metrics
        
        return results
    
    def _compute_metrics(
        self, 
        vault_address: str, 
        input_amount: str
    ) -> Optional[VaultMetrics]:
        """
        Compute fresh metrics for a vault
        
        Args:
            vault_address: Vault address
            input_amount: Deployment size
            
        Returns:
            VaultMetrics or None on error
        """
        try:
            # Step 1: Get historical APY
            hist_data = self.client.get_historical_apy(vault_address)
            if not hist_data:
                logger.warning(f"No historical data for {vault_address}")
                return None
            
            # Step 2: Extract time series and compute statistics
            apy_series = self._extract_apy_time_series(hist_data)
            
            if len(apy_series) == 0:
                logger.warning(f"No APY time series for {vault_address}")
                return None
            
            mean_apy = float(np.mean(apy_series))
            volatility = float(np.std(apy_series))
            
            # Handle single data point (no historical variance)
            if len(apy_series) == 1:
                logger.warning(f"Only single APY data point for {vault_address[:10]}... - using assumed volatility")
                # Use assumed volatility of 2.5% for single data point
                # This is a reasonable estimate for yield-bearing stablecoins
                volatility = 2.5
            
            # Step 3: Get diluted APY (forward-looking)
            diluted_data = self.client.get_diluted_apy(vault_address, input_amount)
            if not diluted_data:
                logger.warning(f"No diluted APY for {vault_address}")
                return None
            
            net_apy = self._extract_net_apy(diluted_data)
            
            # Step 4: Compute Sharpe ratio
            excess_return = (net_apy / 100.0) - self.risk_free_rate
            # Use minimum volatility of 0.5% to avoid unrealistic Sharpe ratios
            min_volatility = 0.5  # 0.5% minimum
            effective_volatility = max(volatility / 100.0, min_volatility / 100.0)
            sharpe = excess_return / effective_volatility
            
            # Step 5: Get TVL from chain
            tvl = self.client.web3_client.get_vault_tvl(vault_address)
            if tvl is None:
                tvl = 0.0
            
            # Step 6: Get underlying token
            underlying = VAULT_TO_INPUT_TOKEN.get(vault_address.lower(), "unknown")
            
            metrics = VaultMetrics(
                vault_address=vault_address,
                underlying_token=underlying,
                mean_apy=mean_apy,
                net_apy=net_apy,
                apy_volatility=volatility,
                sharpe_ratio=sharpe,
                tvl=tvl,
                input_amount=input_amount,
                risk_free_rate=self.risk_free_rate,
                timestamp=time.time()
            )
            
            logger.info(
                f"Metrics computed for {vault_address[:10]}... | "
                f"APY: {net_apy:.2f}% | Vol: {volatility:.2f}% | "
                f"Sharpe: {sharpe:.3f} | TVL: ${tvl:,.0f}"
            )
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error computing metrics for {vault_address}: {e}")
            return None
    
    def _extract_apy_time_series(self, hist_data: dict) -> np.ndarray:
        """
        Extract APY time series from historical data
        
        Args:
            hist_data: Historical APY response from API
            
        Returns:
            NumPy array of APY values
        """
        try:
            # Try to find time series in response
            historic_yield = hist_data.get('historic_yield', hist_data)
            
            # Look for time_series, data, or apy_history
            time_series = (
                historic_yield.get('time_series') or 
                historic_yield.get('data') or 
                historic_yield.get('apy_history') or
                []
            )
            
            # Extract APY values
            if isinstance(time_series, list):
                apys = []
                for point in time_series:
                    if isinstance(point, dict):
                        # Try different keys
                        apy = (
                            point.get('net_apy') or 
                            point.get('apy') or 
                            point.get('value')
                        )
                        if apy is not None:
                            apys.append(float(apy))
                    elif isinstance(point, (int, float)):
                        apys.append(float(point))
                
                if apys:
                    return np.array(apys)
            
            # Fallback: if no time series, use current APY as single point
            apy_data = historic_yield.get('apy', {})
            if isinstance(apy_data, dict):
                apy = apy_data.get('net_apy', apy_data.get('apy', 0))
            else:
                apy = apy_data
            
            # Return single value (will have 0 volatility)
            logger.warning(f"Using single APY value: {apy}")
            return np.array([float(apy)])
            
        except Exception as e:
            logger.error(f"Error extracting APY time series: {e}")
            return np.array([])
    
    def _extract_net_apy(self, diluted_data: dict) -> float:
        """Extract net APY from diluted APY response"""
        try:
            diluted_yield = diluted_data.get('diluted_yield', {})
            apy_data = diluted_yield.get('apy', {})
            
            if isinstance(apy_data, dict):
                return float(apy_data.get('net_apy', apy_data.get('apy', 0)))
            return float(apy_data)
            
        except Exception as e:
            logger.error(f"Error extracting net APY: {e}")
            return 0.0
    
    def get_cache_stats(self) -> dict:
        """Get cache statistics"""
        stats = self.cache.stats.copy()
        stats['cached_vaults'] = len(self.cache._cache)
        stats['fresh_vaults'] = len(self.cache.get_all_fresh())
        
        total_requests = stats['hits'] + stats['misses']
        if total_requests > 0:
            stats['hit_rate'] = stats['hits'] / total_requests
        else:
            stats['hit_rate'] = 0.0
        
        return stats

