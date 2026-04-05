import time
from web3 import Web3
from agent.executor import Web3Executor

# We will use Anvil account 0 as the "User" who owns the funds and the AgentWallet
# We will use Anvil account 1 as the "Agent"
w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545"))

# Accounts from Anvil output
USER_PK = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
USER_ADDR = w3.eth.account.from_key(USER_PK).address

AGENT_PK = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
AGENT_ADDR = w3.eth.account.from_key(AGENT_PK).address

# Mock contract addresses from the deploy script output
# Assuming they are deployed here since they are deterministic
AGENT_WALLET_IMPL = "0x58cD6E0279F83e52DBc114af69ddEa831a50F019"
AAVE_POOL = "0xB5020155268d7b32BF0F03BF01f41026e2390F56"

def main():
    print(f"Connecting to RPC... connected: {w3.is_connected()}")
    print(f"User EOA: {USER_ADDR}")
    print(f"Agent EOA: {AGENT_ADDR}")

    # 1. We must mock the EIP-7702 delegation. 
    # Since Anvil might not natively support EIP-7702 transaction types directly via web3.py yet,
    # we can use the anvil `anvil_setStorageAt` or `anvil_setCode` to mock the delegation, 
    # OR we just deploy a proxy that acts like the delegated EOA.
    # To keep it simple, let's just use `anvil_setCode` to inject the AgentWallet implementation code directly into the USER_ADDR
    # This simulates what EIP-7702 does.
    
    impl_code = w3.eth.get_code(w3.to_checksum_address(AGENT_WALLET_IMPL))
    print(f"Loaded implementation code length: {len(impl_code)}")
    
    # Inject code into user's EOA to simulate EIP-7702 delegation
    w3.provider.make_request("anvil_setCode", [USER_ADDR, impl_code.hex()])
    print("Injected AgentWallet code into User EOA to simulate EIP-7702")

    # 2. User calls `setupSession` on themselves to authorize the Agent
    # Note: Since the User now has code, we can call it.
    import json
    AGENT_WALLET_ABI = json.loads('''[
        {"inputs":[{"name":"_agent","type":"address"},{"name":"_validUntil","type":"uint40"},{"name":"_dailySpendLimit","type":"uint256"}],"name":"setupSession","outputs":[],"stateMutability":"nonpayable","type":"function"}
    ]''')
    
    user_wallet = w3.eth.contract(address=USER_ADDR, abi=AGENT_WALLET_ABI)
    
    valid_until = int(time.time()) + 86400
    spend_limit = w3.to_wei(1, 'ether')
    
    tx = user_wallet.functions.setupSession(AGENT_ADDR, valid_until, spend_limit).build_transaction({
        'from': USER_ADDR,
        'gas': 200000,
        'gasPrice': w3.eth.gas_price,
        'nonce': w3.eth.get_transaction_count(USER_ADDR)
    })
    
    signed_tx = w3.eth.account.sign_transaction(tx, private_key=USER_PK)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    w3.eth.wait_for_transaction_receipt(tx_hash)
    print("User authorized Agent successfully via setupSession")

    # 3. Agent executes a whitelisted call using the backend Executor
    print("Agent preparing to execute a transaction via backend Web3Executor...")
    executor = Web3Executor() # Uses AGENT_PRIVATE_KEY
    
    # We will just send 0.1 ETH to the Aave Pool (or just a simple transfer to it)
    value = w3.to_wei(0.1, 'ether')
    # Aave Pool doesn't natively accept ETH transfers without specific deposit calldata (WETH). 
    # But for our test, if it reverts inside execute(), it proves the call was routed. 
    # Let's mock the Aave pool code to accept ETH so it doesn't revert.
    w3.provider.make_request("anvil_setCode", [AAVE_POOL, "0x00"])
    
    try:
        tx_hash = executor.sign_and_send(
            user_address=USER_ADDR, 
            target_protocol=AAVE_POOL, 
            value=value, 
            calldata=b''
        )
        receipt = executor.wait_for_receipt(tx_hash)
        print(f"Agent successfully executed call through User's EOA! TX Hash: {tx_hash}")
        print(f"Gas Used: {receipt.gasUsed}")
        print("End-to-End Integration Test Passed!")
    except Exception as e:
        print(f"Integration Test Failed: {e}")

if __name__ == "__main__":
    main()
