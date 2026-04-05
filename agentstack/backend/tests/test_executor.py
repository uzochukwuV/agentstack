import pytest
from unittest.mock import MagicMock, patch
from web3 import Web3
from agent.executor import Web3Executor

@pytest.fixture
def mock_w3():
    with patch("agent.executor.Web3") as MockWeb3:
        w3_instance = MagicMock()
        w3_instance.eth.chain_id = 421614 # Arb Sepolia
        w3_instance.eth.get_block.return_value = {'baseFeePerGas': 1000000000}
        w3_instance.eth.max_priority_fee = 1000000000
        w3_instance.eth.get_transaction_count.return_value = 0
        
        # We need to make sure to_checksum_address returns a string
        w3_instance.to_checksum_address = lambda x: Web3.to_checksum_address(x)
        
        # Mock contract function
        mock_contract = MagicMock()
        mock_contract.functions.execute.return_value = mock_contract
        mock_contract.functions.approveToken.return_value = mock_contract
        mock_contract.estimate_gas.return_value = 100000
        mock_contract.build_transaction.return_value = {'to': '0x123', 'data': '0x'}
        
        w3_instance.eth.contract.return_value = mock_contract
        
        # Mock signed tx
        mock_signed_tx = MagicMock()
        mock_signed_tx.raw_transaction = b'raw_tx'
        w3_instance.eth.account.sign_transaction.return_value = mock_signed_tx
        
        # Mock send_raw_transaction
        w3_instance.eth.send_raw_transaction.return_value = b'mock_hash'
        
        MockWeb3.return_value = w3_instance
        # Also mock Web3.to_checksum_address on the class so the executor sees it
        MockWeb3.to_checksum_address = Web3.to_checksum_address
        
        yield w3_instance

def test_executor_initialization():
    executor = Web3Executor(rpc_url="http://mock", private_key="0x" + "1"*64)
    assert executor.agent_address is not None

def test_sign_and_send(mock_w3):
    executor = Web3Executor(rpc_url="http://mock", private_key="0x" + "1"*64)
    executor.w3 = mock_w3 # Inject mock instance
    
    # Use real checksum addresses for validation
    user_address = Web3.to_checksum_address("0x1111111111111111111111111111111111111111")
    target_protocol = Web3.to_checksum_address("0x2222222222222222222222222222222222222222")
    calldata = b'\x00\x01'
    
    tx_hash = executor.sign_and_send(user_address, target_protocol, 0, calldata)
    
    # Assert contract was loaded at user address
    # We use ANY for ABI because we don't care about the exact dictionary in the test
    from unittest.mock import ANY
    mock_w3.eth.contract.assert_called_with(address=user_address, abi=ANY)
    
    # Assert gas estimation was called
    mock_w3.eth.contract().estimate_gas.assert_called_once()
    
    # Assert sign transaction was called
    mock_w3.eth.account.sign_transaction.assert_called_once()
    
    # Assert send raw transaction was called
    mock_w3.eth.send_raw_transaction.assert_called_with(b'raw_tx')
    assert tx_hash == b'mock_hash'.hex()

def test_approve_token(mock_w3):
    executor = Web3Executor(rpc_url="http://mock", private_key="0x" + "1"*64)
    executor.w3 = mock_w3
    
    user_address = Web3.to_checksum_address("0x1111111111111111111111111111111111111111")
    token_address = Web3.to_checksum_address("0x3333333333333333333333333333333333333333")
    spender = Web3.to_checksum_address("0x4444444444444444444444444444444444444444")
    
    tx_hash = executor.approve_token(user_address, token_address, spender, 1000)
    
    # Check that the ABI call went to approveToken
    mock_w3.eth.contract().functions.approveToken.assert_called_with(token_address, spender, 1000)
    assert tx_hash == b'mock_hash'.hex()

def test_gas_buffer_applied(mock_w3):
    executor = Web3Executor(rpc_url="http://mock", private_key="0x" + "1"*64)
    executor.w3 = mock_w3
    
    user_address = Web3.to_checksum_address("0x1111111111111111111111111111111111111111")
    target_protocol = Web3.to_checksum_address("0x2222222222222222222222222222222222222222")
    
    executor.sign_and_send(user_address, target_protocol, 0, b'')
    
    # Estimate was 100000, build_transaction should receive 120000 (1.2x)
    build_tx_args = mock_w3.eth.contract().build_transaction.call_args[0][0]
    assert build_tx_args['gas'] == 120000
    
def test_missing_private_key_raises_error():
    executor = Web3Executor(rpc_url="http://mock")
    user_address = Web3.to_checksum_address("0x1111111111111111111111111111111111111111")
    target_protocol = Web3.to_checksum_address("0x2222222222222222222222222222222222222222")
    # private_key defaults to None if AGENT_PRIVATE_KEY env var is not set
    with pytest.raises(ValueError, match="No private key configured"):
        executor.sign_and_send(user_address, target_protocol, 0, b'')
