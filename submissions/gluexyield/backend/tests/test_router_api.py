#!/usr/bin/env python3
"""
Test GlueX Router API to verify our implementation
"""

import os
import sys
import requests
from dotenv import load_dotenv

# Add parent directories to path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
project_root = os.path.dirname(backend_dir)
sys.path.insert(0, backend_dir)
sys.path.insert(0, project_root)

load_dotenv()

def test_reference_implementation():
    """Test using the exact reference code from GlueX docs"""
    print("=" * 80)
    print("TEST 1: Reference Implementation (Ethereum mainnet)")
    print("=" * 80)
    
    url = "https://router.gluex.xyz/v1/quote"
    
    payload = {
        "chainID": "ethereum",
        "inputToken": "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
        "outputToken": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        "inputAmount": "1000000000000000000",
        "orderType": "SELL",
        "userAddress": "0x174F75176b73124627116653085Ce9585E261388",
        "outputReceiver": "0x9A6D76cB905Df126832AEB1802A27a1b37a6e872",
        "uniquePID": "866a61811189692e8eccae5d2759724a812fa6f8703ebffe90c29dc1f886bbc1"
    }
    
    api_key = os.getenv('GLUEX_API_KEY')
    if not api_key:
        print("❌ ERROR: GLUEX_API_KEY not set in .env")
        return False
    
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json"
    }
    
    print(f"API Key: {api_key[:10]}...")
    print(f"Request: {payload}")
    print()
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ SUCCESS!")
            print(f"Router: {data['result']['router']}")
            print(f"Output Amount: {data['result']['outputAmount']}")
            print(f"Calldata length: {len(data['result']['calldata'])} chars")
            return True
        else:
            print(f"❌ FAILED!")
            print(f"Response: {response.text[:500]}")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False


def test_hyperevm_implementation():
    """Test with HyperEVM (our actual use case)"""
    print("\n" + "=" * 80)
    print("TEST 2: HyperEVM Implementation (USDC → USDE)")
    print("=" * 80)
    
    url = "https://router.gluex.xyz/v1/quote"
    
    # Use actual HyperEVM tokens
    payload = {
        "chainID": "hyperevm",
        "inputToken": "0xb88339CB7199b77E23DB6E890353E22632Ba630f",  # USDC
        "outputToken": "0x5d3a1Ff2b6BAb83b63cd9AD0787074081a52ef34",  # USDE
        "inputAmount": "60000",  # 0.06 USDC (6 decimals)
        "orderType": "SELL",
        "userAddress": "0x3C66E7C924eEA10AaFec0f3932B04C980D335AEb",  # VaultManager
        "outputReceiver": "0x3C66E7C924eEA10AaFec0f3932B04C980D335AEb",
        "uniquePID": os.getenv('UNIQUE_PID', '')
    }
    
    api_key = os.getenv('GLUEX_API_KEY')
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json"
    }
    
    print(f"Request: {payload}")
    print()
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ SUCCESS!")
            print(f"Status: {data.get('statusCode')}")
            if data.get('statusCode') == 200:
                result = data['result']
                print(f"Router: {result['router']}")
                print(f"Input Amount: {result['inputAmount']}")
                print(f"Output Amount: {result['outputAmount']}")
                print(f"Calldata length: {len(result['calldata'])} chars")
                print(f"Value: {result.get('value', '0')}")
                return True
            else:
                print(f"❌ API Error: {data}")
                return False
        else:
            print(f"❌ HTTP ERROR!")
            print(f"Response: {response.text[:500]}")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_our_client():
    """Test using our GlueXClient implementation"""
    print("\n" + "=" * 80)
    print("TEST 3: Our GlueXClient Implementation")
    print("=" * 80)
    
    try:
        from backend.clients.gluex_client import GlueXClient
        
        api_key = os.getenv('GLUEX_API_KEY')
        if not api_key:
            print("❌ ERROR: GLUEX_API_KEY not set")
            return False
        
        client = GlueXClient(api_key=api_key)
        
        # Test with HyperEVM tokens
        quote = client.get_router_quote(
            input_token="0xb88339CB7199b77E23DB6E890353E22632Ba630f",  # USDC
            output_token="0x5d3a1Ff2b6BAb83b63cd9AD0787074081a52ef34",  # USDE
            input_amount="60000",
            input_sender="0x3C66E7C924eEA10AaFec0f3932B04C980D335AEb",
            output_receiver="0x3C66E7C924eEA10AaFec0f3932B04C980D335AEb",
            chain="hyperevm"
        )
        
        if quote:
            print(f"✅ SUCCESS!")
            print(f"Router: {quote.router}")
            print(f"Input Amount: {quote.input_amount}")
            print(f"Output Amount: {quote.output_amount}")
            print(f"Calldata length: {len(quote.calldata)} chars")
            return True
        else:
            print(f"❌ FAILED: No quote returned")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("\n🔍 GlueX Router API Testing Suite\n")
    
    # Check API key
    api_key = os.getenv('GLUEX_API_KEY')
    if not api_key:
        print("❌ ERROR: GLUEX_API_KEY not found in .env")
        print("   Please set your GlueX API key in .env file")
        return
    
    print(f"Using API Key: {api_key[:15]}...")
    print()
    
    # Run tests
    results = []
    
    # Test 1: Reference implementation
    results.append(("Reference (Ethereum)", test_reference_implementation()))
    
    # Test 2: HyperEVM direct
    results.append(("HyperEVM Direct", test_hyperevm_implementation()))
    
    # Test 3: Our client
    results.append(("Our GlueXClient", test_our_client()))
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {name}")
    
    all_passed = all(result[1] for result in results)
    if all_passed:
        print("\n✅ All tests passed!")
    else:
        print("\n❌ Some tests failed - check logs above")


if __name__ == "__main__":
    main()

