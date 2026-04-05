import os
from web3 import Web3
from web3.exceptions import TimeExhausted
import logging
import json

logger = logging.getLogger(__name__)

RPC_URL = os.getenv("RPC_URL", "http://127.0.0.1:8545")
AGENT_PRIVATE_KEY = os.getenv("AGENT_PRIVATE_KEY", "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d")

AGENT_WALLET_ABI = json.loads('''[
    {"inputs":[{"name":"target","type":"address"},{"name":"value","type":"uint256"},{"name":"data","type":"bytes"}],"name":"execute","outputs":[{"name":"","type":"bytes"}],"stateMutability":"payable","type":"function"},
    {"inputs":[{"name":"token","type":"address"},{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],"name":"approveToken","outputs":[],"stateMutability":"nonpayable","type":"function"}
]''')

class Web3Executor:
    def __init__(self, rpc_url: str = None):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url or RPC_URL))
        if not self.w3.is_connected():
            logger.error("Failed to connect to RPC")
        self.account = self.w3.eth.account.from_key(AGENT_PRIVATE_KEY)
        self.agent_address = self.account.address
        # We track nonce manually to avoid "nonce too low" in rapid succession
        self.nonce = None

    def _get_nonce(self) -> int:
        if self.nonce is None:
            self.nonce = self.w3.eth.get_transaction_count(self.agent_address)
        else:
            self.nonce += 1
        return self.nonce

    def sign_and_send(self, user_address: str, target_protocol: str, value: int, calldata: bytes) -> str:
        contract = self.w3.eth.contract(address=self.w3.to_checksum_address(user_address), abi=AGENT_WALLET_ABI)
        
        nonce = self._get_nonce()
        
        tx = contract.functions.execute(
            self.w3.to_checksum_address(target_protocol),
            value,
            calldata if isinstance(calldata, bytes) else bytes.fromhex(calldata.replace('0x', ''))
        ).build_transaction({
            'from': self.agent_address,
            'nonce': nonce,
            'maxFeePerGas': self.w3.eth.gas_price * 2,
            'maxPriorityFeePerGas': self.w3.eth.max_priority_fee,
        })
        
        signed_tx = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        return tx_hash.hex()

    def approve_token(self, user_address: str, token_address: str, spender: str, amount: int) -> str:
        contract = self.w3.eth.contract(address=self.w3.to_checksum_address(user_address), abi=AGENT_WALLET_ABI)
        
        nonce = self._get_nonce()
        
        tx = contract.functions.approveToken(
            self.w3.to_checksum_address(token_address),
            self.w3.to_checksum_address(spender),
            amount
        ).build_transaction({
            'from': self.agent_address,
            'nonce': nonce,
            'maxFeePerGas': self.w3.eth.gas_price * 2,
            'maxPriorityFeePerGas': self.w3.eth.max_priority_fee,
        })
        
        signed_tx = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        return tx_hash.hex()

    def wait_for_receipt(self, tx_hash: str, timeout: int = 120):
        try:
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
            return receipt
        except TimeExhausted:
            logger.error(f"Transaction {tx_hash} timed out after {timeout} seconds")
            raise

