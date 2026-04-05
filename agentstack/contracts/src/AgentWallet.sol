// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

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
    error UnapprovedToken();

    struct AgentStorage {
        address agent;
        uint40 validUntil;
        uint40 lastSpendDay;
        uint256 dailySpendLimit;
        uint256 dailySpentAmount;
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

    // Allow the agent to approve specific tokens for whitelisted protocols
    // Arbitrum Sepolia USDC: 0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d
    function isWhitelistedToken(address token) public pure returns (bool) {
        if (token == 0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d) return true; // USDC
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

    // Only allow the agent to approve tokens to whitelisted protocols
    function approveToken(address token, address spender, uint256 amount) external {
        AgentStorage storage $ = _getAgentStorage();
        if (msg.sender != $.agent) revert Unauthorized();
        if (block.timestamp > $.validUntil) revert SessionExpired();
        
        if (!isWhitelistedToken(token)) revert UnapprovedToken();
        if (!isWhitelisted(spender)) revert NotWhitelisted();

        // Note: we don't count approvals towards daily spend limit yet, 
        // because the actual spend happens when the protocol pulls the funds.
        // For a more robust limit, we would need to track the actual transfers or limit the approval amount.
        IERC20(token).approve(spender, amount);
    }

    function execute(address target, uint256 value, bytes calldata data) external payable returns (bytes memory) {
        AgentStorage storage $ = _getAgentStorage();

        // Check caller is the agent
        if (msg.sender != $.agent) revert Unauthorized();

        // Check expiration
        if (block.timestamp > $.validUntil) revert SessionExpired();

        // Check whitelist
        if (!isWhitelisted(target)) revert NotWhitelisted();

        // Security: Prevent the agent from calling arbitrary withdraw functions to themselves
        // In a real production system, you'd decode the calldata and ensure 'to' address is the EOA itself.
        // For this demo, we assume the backend python executor does this check.

        // Check daily spend limit (only tracks native ETH value here)
        // Note: to track ERC20 spends, the agent should ideally use a dedicated deposit function
        // that measures token balance before and after.
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
