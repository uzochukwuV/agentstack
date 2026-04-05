import time
from web3 import Web3
from agent.executor import Web3Executor
from skills.aave import AaveV4Skill
from skills.uniswap import UniswapV3Skill

w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545"))

USER_PK = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
USER_ADDR = w3.eth.account.from_key(USER_PK).address
AGENT_PK = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
AGENT_ADDR = w3.eth.account.from_key(AGENT_PK).address

# The newly deployed implementation contract address from the logs
AGENT_WALLET_IMPL = "0x58c7CA8effEDDEdD5178bc76509dEC0f278Dd0eE"
USDC = "0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d"

def setup_eoa_delegation():
    # Inject code
    impl_code = w3.eth.get_code(w3.to_checksum_address(AGENT_WALLET_IMPL))
    w3.provider.make_request("anvil_setCode", [USER_ADDR, impl_code.hex()])
    
    # Give User some USDC to test with
    # USDC slot 9 usually holds balances. We can just use anvil_setStorageAt to mint USDC
    # Alternatively, we can impersonate a whale, but setting storage is easier
    # Mapping slot calculation: keccak256(abi.encode(USER_ADDR, 9))
    user_padded = USER_ADDR.lower().replace('0x', '').rjust(64, '0')
    slot_padded = hex(9).replace('0x', '').rjust(64, '0')
    storage_slot = w3.keccak(hexstr=user_padded + slot_padded).hex()
    
    # Mint 100,000 USDC (6 decimals) -> 100000000000 -> hex 0x174876e800
    w3.provider.make_request("anvil_setStorageAt", [USDC, storage_slot, "0x174876e800"])
    
    # Authorize Agent
    import json
    AGENT_WALLET_ABI = json.loads('[{"inputs":[{"name":"_agent","type":"address"},{"name":"_validUntil","type":"uint40"},{"name":"_dailySpendLimit","type":"uint256"}],"name":"setupSession","outputs":[],"stateMutability":"nonpayable","type":"function"}]')
    user_wallet = w3.eth.contract(address=USER_ADDR, abi=AGENT_WALLET_ABI)
    
    valid_until = int(time.time()) + 86400
    tx = user_wallet.functions.setupSession(AGENT_ADDR, valid_until, w3.to_wei(1, 'ether')).build_transaction({
        'from': USER_ADDR,
        'gas': 200000,
        'gasPrice': w3.eth.gas_price,
        'nonce': w3.eth.get_transaction_count(USER_ADDR)
    })
    
    signed_tx = w3.eth.account.sign_transaction(tx, private_key=USER_PK)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    w3.eth.wait_for_transaction_receipt(tx_hash)

def main():
    print(f"Connected to RPC: {w3.is_connected()}")
    setup_eoa_delegation()
    print("User EOA delegated and minted 100,000 mock USDC")

    executor = Web3Executor()
    
    print("\n--- Testing Aave V3 Skill ---")
    aave_skill = AaveV4Skill(web3_provider=w3, executor=executor)
    aave_tools = aave_skill.get_tools()
    supply_tool = aave_tools[0]
    
    res = supply_tool.invoke({"user_address": USER_ADDR, "amount_in_usdc": 10.0})
    print(f"Aave Result: {res}")

    print("\n--- Testing Uniswap V3 Skill ---")
    uni_skill = UniswapV3Skill(web3_provider=w3, executor=executor)
    uni_tools = uni_skill.get_tools()
    swap_tool = uni_tools[0]
    
    res = swap_tool.invoke({"user_address": USER_ADDR, "amount_in_usdc": 5.0})
    print(f"Uniswap Result: {res}")

if __name__ == "__main__":
    main()
