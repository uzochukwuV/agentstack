# Mock configuration for testing
RPC_EXCEPTIONS = []

def simulate_rpc_exception(user_address: str) -> bool:
    if user_address in RPC_EXCEPTIONS:
        return True
    return False
