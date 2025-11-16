"""
GlueX API Client
Handles interactions with GlueX Yields API and Router API
"""

import requests
import time
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import logging
from ..config import VAULT_TO_INPUT_TOKEN, DEFAULT_CHAIN, HYPEREVM_RPC_URL
from .web3_client import Web3Client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class YieldData:
    """Represents yield information for a vault"""
    vault_address: str
    apy: float
    tvl: float
    risk_score: float
    timestamp: int


@dataclass
class SwapQuote:
    """Represents a swap quote from GlueX Router"""
    input_token: str
    output_token: str
    fee_token: str
    input_sender: str
    output_receiver: str
    input_amount: str
    output_amount: str
    partner_fee: str
    routing_fee: str
    effective_input_amount: str
    effective_output_amount: str
    min_output_amount: str
    liquidity_modules: List[str]
    router: str
    estimated_net_surplus: str
    calldata: str
    is_native_token_input: bool
    value: str
    revert: bool
    computation_units: int
    block_number: int
    low_balance: bool
    input_amount_usd: str
    effective_input_amount_usd: str
    output_amount_usd: str
    effective_output_amount_usd: str


@dataclass
class PriceQuote:
    """Represents a price quote from GlueX Router"""
    input_token: str
    output_token: str
    fee_token: str
    input_sender: str
    output_receiver: str
    input_amount: str
    output_amount: str
    partner_fee: str
    routing_fee: str
    effective_input_amount: str
    effective_output_amount: str
    min_output_amount: str
    liquidity_modules: List[str]
    router: str
    estimated_net_surplus: str
    is_native_token_input: bool
    value: str
    computation_units: int
    input_amount_usd: str
    effective_input_amount_usd: str
    output_amount_usd: str
    effective_output_amount_usd: str


class GlueXClient:
    """Client for interacting with GlueX APIs"""
    
    YIELDS_API_BASE = "https://yield-api.gluex.xyz"
    ROUTER_API_BASE = "https://router.gluex.xyz"
    
    def __init__(self, api_key: str, rpc_url: str = None):
        """
        Initialize GlueX client
        
        Args:
            api_key: GlueX API key
            rpc_url: RPC URL for blockchain interaction (defaults to HyperEVM)
        """
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "x-api-key": api_key
        })
        
        # Initialize Web3 client for on-chain data
        self.rpc_url = rpc_url or HYPEREVM_RPC_URL
        self.web3_client = Web3Client(self.rpc_url)
    
    def get_historical_apy(
        self,
        lp_token_address: str,
        chain: str = None
    ) -> Optional[Dict]:
        """
        Get historical APY for a liquidity pool/vault
        
        Args:
            lp_token_address: Address of the LP token or vault
            chain: Blockchain identifier (default: ethereum)
            
        Returns:
            Dict containing APY data or None on error
        """
        if chain is None:
            chain = DEFAULT_CHAIN
            
        # Normalize address to lowercase for lookup
        lp_token_lower = lp_token_address.lower()
        
        # Get the input token for this vault
        input_token = VAULT_TO_INPUT_TOKEN.get(lp_token_lower)
        if not input_token:
            logger.error(f"No input token mapping found for vault {lp_token_address}")
            return None
        
        endpoint = f"{self.YIELDS_API_BASE}/historical-apy"
        payload = {
            "lp_token_address": lp_token_address,
            "input_token": input_token,
            "chain": chain
        }
        
        try:
            response = self.session.post(endpoint, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching historical APY: {e}")
            return None
    
    def get_diluted_apy(
        self,
        lp_token_address: str,
        amount: str,
        chain: str = None
    ) -> Optional[Dict]:
        """
        Get diluted APY based on deposit amount
        
        Args:
            lp_token_address: Address of the LP token or vault
            amount: Deposit amount in smallest units
            chain: Blockchain identifier (default: ethereum)
            
        Returns:
            Dict containing diluted APY data or None on error
        """
        if chain is None:
            chain = DEFAULT_CHAIN
            
        # Normalize address to lowercase for lookup
        lp_token_lower = lp_token_address.lower()
        
        # Get the input token for this vault
        input_token = VAULT_TO_INPUT_TOKEN.get(lp_token_lower)
        if not input_token:
            logger.error(f"No input token mapping found for vault {lp_token_address}")
            return None
        
        endpoint = f"{self.YIELDS_API_BASE}/diluted-apy"
        payload = {
            "lp_token_address": lp_token_address,
            "input_token": input_token,
            "chain": chain,
            "input_amount": amount
        }
        
        try:
            response = self.session.post(endpoint, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching diluted APY: {e}")
            return None
    
    def get_multiple_vault_yields(
        self,
        vault_addresses: List[str],
        amount: str = "1000000000000",  # Default: 1M USDC (6 decimals = 1e12)
        chain: str = None
    ) -> List[YieldData]:
        """
        Get yield data for multiple vaults
        
        Args:
            vault_addresses: List of vault addresses
            amount: Amount to use for diluted APY calculation
            chain: Blockchain identifier (default: ethereum)
            
        Returns:
            List of YieldData objects
        """
        yield_data_list = []
        
        for vault_address in vault_addresses:
            try:
                # Get historical APY
                hist_data = self.get_historical_apy(vault_address, chain)
                
                # Get diluted APY for given amount
                diluted_data = self.get_diluted_apy(vault_address, amount, chain)
                
                if hist_data and diluted_data:
                    # Extract APY from nested response structure
                    # Using net_apy (after fees) from diluted yield data
                    diluted_yield = diluted_data.get('diluted_yield', {})
                    apy_data = diluted_yield.get('apy', {})
                    apy = apy_data.get('net_apy', apy_data.get('apy', 0))
                    
                    # Fetch TVL from vault contract
                    tvl = self.web3_client.get_vault_tvl(vault_address)
                    if tvl is None:
                        tvl = 0
                        logger.warning(f"Could not fetch TVL for vault {vault_address}")
                    
                    yield_data = YieldData(
                        vault_address=vault_address,
                        apy=float(apy),
                        tvl=float(tvl),
                        risk_score=self._calculate_risk_score(apy, tvl),
                        timestamp=int(time.time())
                    )
                    yield_data_list.append(yield_data)
                    
                    logger.info(f"Vault {vault_address[:10]}...: APY={apy:.2f}%, TVL=${tvl:,.0f}")
                    
            except Exception as e:
                logger.error(f"Error processing vault {vault_address}: {e}")
                continue
        
        return yield_data_list
    
    def get_router_quote(
        self,
        input_token: str,
        output_token: str,
        input_amount: str,
        input_sender: str,
        output_receiver: str,
        chain: str = None,
        slippage: float = 0.5,
        unique_pid: str = None,
        is_permit2: bool = False
    ) -> Optional[SwapQuote]:
        """
        Get a swap quote from GlueX Router
        
        Args:
            input_token: Input token address
            output_token: Output token address (can be vault address for deposits)
            input_amount: Amount to swap (in smallest units)
            input_sender: Address sending the tokens (userAddress)
            output_receiver: Address receiving the tokens
            chain: Blockchain identifier (default: hyperevm)
            slippage: Slippage tolerance in percentage (default: 0.5%)
            unique_pid: Unique partner ID (optional)
            is_permit2: Whether to use Permit2 (default: False)
            
        Returns:
            SwapQuote object or None on error
        """
        import os
        
        if chain is None:
            chain = DEFAULT_CHAIN
        
        if unique_pid is None:
            unique_pid = os.getenv('UNIQUE_PID', '')
        
        endpoint = f"{self.ROUTER_API_BASE}/v1/quote"
        
        # Format payload according to GlueX API spec
        # https://docs.gluex.xyz/api-reference/router-api/post-quote
        payload = {
            "chainID": chain,
            "inputToken": input_token,
            "outputToken": output_token,
            "inputAmount": input_amount,
            "orderType": "SELL",
            "userAddress": input_sender,
            "outputReceiver": output_receiver,
            "uniquePID": unique_pid
        }
        

        logger.debug(f"Router quote request: {payload}")
        
        try:
            response = self.session.post(endpoint, json=payload)
            response.raise_for_status()
            data = response.json()
            
            if data.get('statusCode') == 200:
                result = data['result']
                return SwapQuote(
                    input_token=result['inputToken'],
                    output_token=result['outputToken'],
                    fee_token=result['feeToken'],
                    input_sender=result['inputSender'],
                    output_receiver=result['outputReceiver'],
                    input_amount=result['inputAmount'],
                    output_amount=result['outputAmount'],
                    partner_fee=result['partnerFee'],
                    routing_fee=result['routingFee'],
                    effective_input_amount=result['effectiveInputAmount'],
                    effective_output_amount=result['effectiveOutputAmount'],
                    min_output_amount=result['minOutputAmount'],
                    liquidity_modules=result['liquidityModules'],
                    router=result['router'],
                    estimated_net_surplus=result['estimatedNetSurplus'],
                    calldata=result['calldata'],
                    is_native_token_input=result['isNativeTokenInput'],
                    value=result['value'],
                    revert=result['revert'],
                    computation_units=result['computationUnits'],
                    block_number=result['blockNumber'],
                    low_balance=result['lowBalance'],
                    input_amount_usd=result['inputAmountUSD'],
                    effective_input_amount_usd=result['effectiveInputAmountUSD'],
                    output_amount_usd=result['outputAmountUSD'],
                    effective_output_amount_usd=result['effectiveOutputAmountUSD']
                )
            else:
                logger.error(f"Router API error: {data}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching router quote: {e}")
            return None
    
    def get_asset_price(
        self,
        input_token: str,
        output_token: str,
        input_amount: str = "100000000",
        user_address: str = None,
        output_receiver: str = None,
        unique_pid: str = None,
        chain_id: str = None,
        order_type: str = "SELL"
    ) -> Optional[PriceQuote]:
        """
        Get price quote for an asset swap
        
        Args:
            input_token: Input token address
            output_token: Output token address
            input_amount: Amount to swap (default: 100000000)
            user_address: User address (can be any address)
            output_receiver: Output receiver address (can be any address)
            unique_pid: Unique PID (from environment variable if stored)
            chain_id: Chain identifier (default: hyperevm)
            order_type: Order type (default: SELL)
            
        Returns:
            PriceQuote object or None on error
        """
        import os
        
        # Set defaults
        if chain_id is None:
            chain_id = "hyperevm"
        
        if user_address is None:
            user_address = "0x0000000000000000000000000000000000000001"
        
        if output_receiver is None:
            output_receiver = user_address
        
        if unique_pid is None:
            unique_pid = os.getenv('UNIQUE_PID', '')
        
        endpoint = f"{self.ROUTER_API_BASE}/v1/price"
        payload = {
            "chainID": chain_id,
            "inputToken": input_token,
            "outputToken": output_token,
            "inputAmount": input_amount,
            "orderType": order_type,
            "userAddress": user_address,
            "outputReceiver": output_receiver,
            "uniquePID": unique_pid
        }
        
        logger.debug(f"Price API request payload: {payload}")
        
        try:
            response = self.session.post(endpoint, json=payload)
            response.raise_for_status()
            data = response.json()
            
            if data.get('statusCode') == 200:
                result = data['result']
                
                # Log price information
                input_usd = result.get('inputAmountUSD', '0')
                output_usd = result.get('outputAmountUSD', '0')
                logger.info(f"Price quote: {input_amount} {input_token[:10]}... (${input_usd}) -> "
                          f"{result['outputAmount']} {output_token[:10]}... (${output_usd})")
                
                return PriceQuote(
                    input_token=result['inputToken'],
                    output_token=result['outputToken'],
                    fee_token=result['feeToken'],
                    input_sender=result['inputSender'],
                    output_receiver=result['outputReceiver'],
                    input_amount=result['inputAmount'],
                    output_amount=result['outputAmount'],
                    partner_fee=result['partnerFee'],
                    routing_fee=result['routingFee'],
                    effective_input_amount=result['effectiveInputAmount'],
                    effective_output_amount=result['effectiveOutputAmount'],
                    min_output_amount=result['minOutputAmount'],
                    liquidity_modules=result['liquidityModules'],
                    router=result['router'],
                    estimated_net_surplus=result['estimatedNetSurplus'],
                    is_native_token_input=result['isNativeTokenInput'],
                    value=result['value'],
                    computation_units=result.get('computationUnits', 0),  # Optional field
                    input_amount_usd=result['inputAmountUSD'],
                    effective_input_amount_usd=result['effectiveInputAmountUSD'],
                    output_amount_usd=result['outputAmountUSD'],
                    effective_output_amount_usd=result['effectiveOutputAmountUSD']
                )
            else:
                logger.error(f"Price API error: {data}")
                return None
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching asset price: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            return None


