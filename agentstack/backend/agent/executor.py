import os
import json
from web3 import Web3
from web3.exceptions import TimeExhausted
import logging

logger = logging.getLogger(__name__)

# Defaults to the local Anvil fork
RPC_URL = os.getenv("RPC_URL", "http://127.0.0.1:8545")

# Use Anvil Account 1 as the Agent Private Key
AGENT_PRIVATE_KEY = os.getenv("AGENT_PRIVATE_KEY", "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d")

ERC20_ABI = json.loads('[{"constant":false,"inputs":[{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"payable":false,"stateMutability":"nonpayable","type":"function"},{"constant":true,"inputs":[{"name":"account","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"payable":false,"stateMutability":"view","type":"function"}]')

AGENT_WALLET_ABI = json.loads('''[
    {"inputs":[{"name":"target","type":"address"},{"name":"value","type":"uint256"},{"name":"data","type":"bytes"}],"name":"execute","outputs":[{"name":"","type":"bytes"}],"stateMutability":"payable","type":"function"},
    {"inputs":[{"name":"token","type":"address"},{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],"name":"approveToken","outputs":[],"stateMutability":"nonpayable","type":"function"}
]''')

class Web3Executor:
    def __init__(self, rpc_url: str = None, private_key: str = None):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url or RPC_URL))
        self.private_key = private_key or AGENT_PRIVATE_KEY
        if self.private_key:
            self.account = self.w3.eth.account.from_key(self.private_key)
            self.agent_address = self.account.address
        else:
            self.account = None
            self.agent_address = None

    def _build_and_send(self, contract_function, to_address: str, value: int = 0) -> str:
        if not self.account:
            raise ValueError("No private key configured for executor")

        try:
            # web3.py contract functions don't accept 'to' in estimate_gas because it's inferred
            gas_estimate = contract_function.estimate_gas({
                'from': self.agent_address,
                'value': value
            })
        except Exception as e:
            logger.error(f"Gas estimation failed: {e}")
            raise e

        gas_limit = int(gas_estimate * 1.2)
        
        try:
            base_fee = self.w3.eth.get_block('latest').get('baseFeePerGas', 1000000000)
            max_priority_fee = self.w3.eth.max_priority_fee
            max_fee_per_gas = (base_fee * 2) + max_priority_fee
            
            tx = contract_function.build_transaction({
                'chainId': self.w3.eth.chain_id,
                'gas': gas_limit,
                'maxFeePerGas': max_fee_per_gas,
                'maxPriorityFeePerGas': max_priority_fee,
                'nonce': self.w3.eth.get_transaction_count(self.agent_address, 'pending'),
                'value': value
            })
        except Exception:
            tx = contract_function.build_transaction({
                'chainId': self.w3.eth.chain_id,
                'gas': gas_limit,
                'gasPrice': self.w3.eth.gas_price,
                'nonce': self.w3.eth.get_transaction_count(self.agent_address, 'pending'),
                'value': value
            })

        signed_tx = self.w3.eth.account.sign_transaction(tx, private_key=self.private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        
        return tx_hash.hex()

    def sign_and_send(self, user_address: str, target_protocol: str, value: int, calldata: bytes) -> str:
        agent_wallet = self.w3.eth.contract(address=self.w3.to_checksum_address(user_address), abi=AGENT_WALLET_ABI)
        target = self.w3.to_checksum_address(target_protocol)
        
        contract_func = agent_wallet.functions.execute(target, value, calldata)
        tx_hash = self._build_and_send(contract_func, to_address=agent_wallet.address, value=value)
        return tx_hash

    def wait_for_receipt(self, tx_hash: str, timeout: int = 120):
        try:
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
            return receipt
        except TimeExhausted:
            logger.error(f"Transaction {tx_hash} timed out after {timeout} seconds")
            raise
