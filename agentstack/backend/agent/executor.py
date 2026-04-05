import os
import json
from web3 import Web3
from web3.exceptions import TimeExhausted
import logging

logger = logging.getLogger(__name__)

# Constants (Could be env vars)
RPC_URL = os.getenv("RPC_URL", "https://sepolia-rollup.arbitrum.io/rpc")
AGENT_PRIVATE_KEY = os.getenv("AGENT_PRIVATE_KEY") # The backend's funded key

# Standard ABIs
ERC20_ABI = json.loads('[{"constant":false,"inputs":[{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"payable":false,"stateMutability":"nonpayable","type":"function"},{"constant":true,"inputs":[{"name":"account","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"payable":false,"stateMutability":"view","type":"function"}]')

# AgentWallet ABI - only the functions we need to call
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
        """Helper to build, sign, and send a transaction."""
        if not self.account:
            raise ValueError("No private key configured for executor")

        # Estimate gas
        try:
            gas_estimate = contract_function.estimate_gas({
                'from': self.agent_address,
                'to': to_address,
                'value': value
            })
        except Exception as e:
            logger.error(f"Gas estimation failed: {e}")
            raise e

        # Add 20% buffer to gas
        gas_limit = int(gas_estimate * 1.2)
        
        # Get dynamic fee parameters for EIP-1559
        base_fee = self.w3.eth.get_block('latest')['baseFeePerGas']
        max_priority_fee = self.w3.eth.max_priority_fee
        max_fee_per_gas = (base_fee * 2) + max_priority_fee

        nonce = self.w3.eth.get_transaction_count(self.agent_address, 'pending')

        tx = contract_function.build_transaction({
            'chainId': self.w3.eth.chain_id,
            'gas': gas_limit,
            'maxFeePerGas': max_fee_per_gas,
            'maxPriorityFeePerGas': max_priority_fee,
            'nonce': nonce,
            'value': value
        })

        signed_tx = self.w3.eth.account.sign_transaction(tx, private_key=self.private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        
        return tx_hash.hex()

    def sign_and_send(self, user_address: str, target_protocol: str, value: int, calldata: bytes) -> str:
        """
        Executes a transaction on behalf of the user via their EIP-7702 AgentWallet.
        user_address: The EOA that delegated to AgentWallet.sol
        target_protocol: The DeFi contract to interact with (must be whitelisted).
        value: Native ETH value.
        calldata: The encoded function call to the target protocol.
        """
        # Load the AgentWallet interface at the user's address
        agent_wallet = self.w3.eth.contract(address=self.w3.to_checksum_address(user_address), abi=AGENT_WALLET_ABI)
        
        target = self.w3.to_checksum_address(target_protocol)
        
        # Build the execute() call
        contract_func = agent_wallet.functions.execute(target, value, calldata)
        
        tx_hash = self._build_and_send(contract_func, to_address=agent_wallet.address, value=value)
        return tx_hash

    def approve_token(self, user_address: str, token_address: str, spender: str, amount: int) -> str:
        """
        Approves a token for a whitelisted protocol via AgentWallet.
        """
        agent_wallet = self.w3.eth.contract(address=self.w3.to_checksum_address(user_address), abi=AGENT_WALLET_ABI)
        token = self.w3.to_checksum_address(token_address)
        spender_addr = self.w3.to_checksum_address(spender)
        
        contract_func = agent_wallet.functions.approveToken(token, spender_addr, amount)
        tx_hash = self._build_and_send(contract_func, to_address=agent_wallet.address, value=0)
        return tx_hash

    def wait_for_receipt(self, tx_hash: str, timeout: int = 120):
        """Wait for transaction confirmation."""
        try:
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
            return receipt
        except TimeExhausted:
            logger.error(f"Transaction {tx_hash} timed out after {timeout} seconds")
            raise
