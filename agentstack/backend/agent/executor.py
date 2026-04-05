import os
import httpx
from web3 import Web3
from web3.exceptions import TimeExhausted
import logging

logger = logging.getLogger(__name__)

RPC_URL = os.getenv("RPC_URL", "http://127.0.0.1:8545")
SIGNER_URL = os.getenv("SIGNER_URL", "http://127.0.0.1:3001")

class Web3Executor:
    def __init__(self, rpc_url: str = None, signer_url: str = None):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url or RPC_URL))
        self.signer_url = signer_url or SIGNER_URL
        
        try:
            res = httpx.get(f"{self.signer_url}/health")
            if res.status_code == 200:
                self.agent_address = res.json().get("address")
            else:
                self.agent_address = None
        except Exception as e:
            logger.error(f"Failed to connect to Ethers.js Signer service: {e}")
            self.agent_address = None

    def sign_and_send(self, user_address: str, target_protocol: str, value: int, calldata: bytes) -> str:
        if not self.agent_address:
            raise ValueError("Signer service unavailable")

        payload = {
            "user_address": user_address,
            "target_protocol": target_protocol,
            "value": str(value),
            "calldata": calldata.hex() if isinstance(calldata, bytes) else calldata
        }
        
        if not payload["calldata"].startswith("0x"):
            payload["calldata"] = "0x" + payload["calldata"]

        res = httpx.post(f"{self.signer_url}/execute", json=payload, timeout=30.0)
        
        if res.status_code == 200:
            return res.json().get("tx_hash")
        else:
            raise Exception(f"Ethers.js execution failed: {res.text}")

    def approve_token(self, user_address: str, token_address: str, spender: str, amount: int) -> str:
        if not self.agent_address:
            raise ValueError("Signer service unavailable")

        payload = {
            "user_address": user_address,
            "token_address": token_address,
            "spender": spender,
            "amount": str(amount)
        }

        res = httpx.post(f"{self.signer_url}/approveToken", json=payload, timeout=30.0)
        
        if res.status_code == 200:
            return res.json().get("tx_hash")
        else:
            raise Exception(f"Ethers.js approve failed: {res.text}")

    def wait_for_receipt(self, tx_hash: str, timeout: int = 120):
        try:
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
            return receipt
        except TimeExhausted:
            logger.error(f"Transaction {tx_hash} timed out after {timeout} seconds")
            raise
