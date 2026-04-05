from typing import List, Dict, Any
from .base import BaseSkill
from langchain_core.tools import tool
import json

# Arb Sepolia Addresses
AAVE_POOL = "0xB5020155268d7b32BF0F03BF01f41026e2390F56"
USDC = "0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d"

AAVE_POOL_ABI = json.loads('''[
    {"inputs":[{"name":"asset","type":"address"},{"name":"amount","type":"uint256"},{"name":"onBehalfOf","type":"address"},{"name":"referralCode","type":"uint16"}],"name":"supply","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"name":"asset","type":"address"},{"name":"amount","type":"uint256"},{"name":"to","type":"address"}],"name":"withdraw","outputs":[{"name":"","type":"uint256"}],"stateMutability":"nonpayable","type":"function"}
]''')

class AaveV4Skill(BaseSkill):
    SKILL_ID = 1
    
    def __init__(self, web3_provider=None, executor=None):
        self.w3 = web3_provider
        self.executor = executor
        if self.w3:
            self.pool_contract = self.w3.eth.contract(address=AAVE_POOL, abi=AAVE_POOL_ABI)
        
    def get_tools(self) -> List[Any]:
        
        @tool
        def supply_usdc_aave(user_address: str, amount_in_usdc: float) -> str:
            """
            Supply USDC to Aave V3 on Arbitrum Sepolia.
            user_address: The user's EOA address
            amount_in_usdc: The amount of USDC to supply (e.g. 10.5)
            """
            if not self.executor or not self.w3:
                return "Error: Executor not initialized"
                
            amount_raw = int(amount_in_usdc * 10**6) 
            
            try:
                print(f"Approving Aave Pool to spend {amount_in_usdc} USDC...")
                appr_tx = self.executor.approve_token(user_address, USDC, AAVE_POOL, amount_raw)
                self.executor.wait_for_receipt(appr_tx)
                
                print(f"Supplying {amount_in_usdc} USDC to Aave Pool...")
                # web3.py proper way to get calldata without using private encodeABI
                calldata = self.pool_contract.encode_abi("supply", args=[USDC, amount_raw, user_address, 0])
                
                tx_hash = self.executor.sign_and_send(user_address, AAVE_POOL, 0, calldata)
                self.executor.wait_for_receipt(tx_hash)
                return f"Successfully supplied {amount_in_usdc} USDC to Aave. TX Hash: {tx_hash}"
            except Exception as e:
                return f"Error executing supply: {str(e)}"
                
        return [supply_usdc_aave]
        
    def get_position_summary(self, user_address: str) -> Dict[str, Any]:
        return {"protocol": "Aave V3", "supplied": 0.0, "borrowed": 0.0}
        
    def health_check(self) -> bool:
        if self.w3 is None: return False
        try: return self.w3.is_connected()
        except Exception: return False
