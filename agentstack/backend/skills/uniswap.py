from typing import List, Dict, Any
from .base import BaseSkill
from langchain_core.tools import tool
import json
import time

# Arb Sepolia Addresses
UNISWAP_V3_ROUTER = "0x101F443B4d1b059569D643917553c771E1b9663E"
USDC = "0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d"
WETH = "0x980B62Da83eFf3D4576C647993b0c1D7faf17c73"

UNISWAP_ROUTER_ABI = json.loads('''[
    {"inputs":[{"components":[{"name":"path","type":"bytes"},{"name":"recipient","type":"address"},{"name":"amountIn","type":"uint256"},{"name":"amountOutMinimum","type":"uint256"}],"name":"params","type":"tuple"}],"name":"exactInput","outputs":[{"name":"amountOut","type":"uint256"}],"stateMutability":"payable","type":"function"}
]''')

class UniswapV3Skill(BaseSkill):
    SKILL_ID = 2
    
    def __init__(self, web3_provider=None, executor=None):
        self.w3 = web3_provider
        self.executor = executor
        if self.w3:
            self.router_contract = self.w3.eth.contract(address=UNISWAP_V3_ROUTER, abi=UNISWAP_ROUTER_ABI)
        
    def get_tools(self) -> List[Any]:
        
        @tool
        def swap_usdc_for_weth(user_address: str, amount_in_usdc: float) -> str:
            """
            Swap USDC for WETH on Uniswap V3 on Arbitrum Sepolia.
            user_address: The user's EOA address
            amount_in_usdc: The amount of USDC to swap (e.g. 5.5)
            """
            if not self.executor or not self.w3:
                return "Error: Executor not initialized"
                
            amount_in_raw = int(amount_in_usdc * 10**6)
            
            try:
                print(f"Approving Uniswap V3 Router to spend {amount_in_usdc} USDC...")
                appr_tx = self.executor.approve_token(user_address, USDC, UNISWAP_V3_ROUTER, amount_in_raw)
                self.executor.wait_for_receipt(appr_tx)
                
                print(f"Swapping {amount_in_usdc} USDC for WETH on Uniswap V3...")
                path = bytes.fromhex(USDC[2:]) + int(3000).to_bytes(3, 'big') + bytes.fromhex(WETH[2:])
                deadline = int(time.time()) + 1800 
                
                params = (
                    path,
                    user_address,
                    amount_in_raw,
                    0 
                )
                
                calldata = self.router_contract.encode_abi("exactInput", args=[params])
                
                tx_hash = self.executor.sign_and_send(user_address, UNISWAP_V3_ROUTER, 0, calldata)
                self.executor.wait_for_receipt(tx_hash)
                return f"Successfully swapped {amount_in_usdc} USDC for WETH. TX Hash: {tx_hash}"
            except Exception as e:
                return f"Error executing swap: {str(e)}"
                
        return [swap_usdc_for_weth]
        
    def get_position_summary(self, user_address: str) -> Dict[str, Any]:
        return {"protocol": "Uniswap V3", "supplied": 0.0, "borrowed": 0.0}
        
    def health_check(self) -> bool:
        if self.w3 is None: return False
        try: return self.w3.is_connected()
        except Exception: return False
