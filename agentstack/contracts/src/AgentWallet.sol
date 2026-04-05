// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title AgentWallet
 * @dev Implementation contract for EIP-7702 delegated EOAs.
 * Gives backend agent a scoped, time-limited session key to call whitelisted DeFi protocols.
 */
contract AgentWallet {
    error Unauthorized();
    error NotWhitelisted();
    error SessionExpired();
    error DailyLimitExceeded();

    struct AgentStorage {
        address agent;
        uint40 validUntil;
        uint256 dailySpendLimit;
        uint256 dailySpentAmount;
        uint40 lastSpendDay;
    }

    // ERC-7201 storage slot: keccak256(abi.encode(uint256(keccak256("agentstack.storage.AgentWallet")) - 1)) & ~bytes32(uint256(0xff))
    bytes32 private constant AGENT_STORAGE_LOCATION =
        0x56a46cd2d7f3fb8fba9003c20d75a6c38827f3114d5ce290da4b8c9c72c2fc00;

    function _getAgentStorage() private pure returns (AgentStorage storage $) {
        assembly {
            $.slot := AGENT_STORAGE_LOCATION
        }
    }

    // Hardcoded whitelist (for demo purposes)
    // Replace with actual protocol addresses for Arbitrum Sepolia
    // Example Aave Pool Address on Arb Sepolia: 0xB5020155268d7b32BF0F03BF01f41026e2390F56
    function isWhitelisted(address target) public pure returns (bool) {
        if (target == 0xB5020155268d7b32BF0F03BF01f41026e2390F56) return true; // Aave Pool
        if (target == 0x0000000000000000000000000000000000000000) return false; // placeholder
        return false;
    }

    function setupSession(address _agent, uint40 _validUntil, uint256 _dailySpendLimit) external {
        // Only the owner (the EOA itself) can set up the session
        if (msg.sender != address(this)) revert Unauthorized();
        
        AgentStorage storage $ = _getAgentStorage();
        $.agent = _agent;
        $.validUntil = _validUntil;
        $.dailySpendLimit = _dailySpendLimit;
        $.dailySpentAmount = 0;
        $.lastSpendDay = uint40(block.timestamp / 86400);
    }

    function execute(address target, uint256 value, bytes calldata data) external payable returns (bytes memory) {
        AgentStorage storage $ = _getAgentStorage();

        // Check caller is the agent
        if (msg.sender != $.agent) revert Unauthorized();

        // Check expiration
        if (block.timestamp > $.validUntil) revert SessionExpired();

        // Check whitelist
        if (!isWhitelisted(target)) revert NotWhitelisted();

        // Check daily spend limit
        uint40 currentDay = uint40(block.timestamp / 86400);
        if (currentDay > $.lastSpendDay) {
            $.dailySpentAmount = 0;
            $.lastSpendDay = currentDay;
        }

        if ($.dailySpentAmount + value > $.dailySpendLimit) revert DailyLimitExceeded();
        $.dailySpentAmount += value;

        // Execute the call
        (bool success, bytes memory returnData) = target.call{value: value}(data);
        if (!success) {
            assembly {
                revert(add(returnData, 32), mload(returnData))
            }
        }
        return returnData;
    }

    function revokeSession() external {
        if (msg.sender != address(this)) revert Unauthorized();
        AgentStorage storage $ = _getAgentStorage();
        $.agent = address(0);
        $.validUntil = 0;
        $.dailySpendLimit = 0;
    }
}
