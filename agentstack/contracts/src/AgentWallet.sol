// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

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

    bytes32 private constant AGENT_STORAGE_LOCATION =
        0x56a46cd2d7f3fb8fba9003c20d75a6c38827f3114d5ce290da4b8c9c72c2fc00;

    function _getAgentStorage() private pure returns (AgentStorage storage $) {
        assembly {
            $.slot := AGENT_STORAGE_LOCATION
        }
    }

    function isWhitelisted(address target) public pure returns (bool) {
        if (target == 0xB5020155268d7b32BF0F03BF01f41026e2390F56) return true; // Aave V3 Pool
        if (target == 0x101F443B4d1b059569D643917553c771E1b9663E) return true; // Uniswap V3 SwapRouter02
        if (target == 0x980B62Da83eFf3D4576C647993b0c1D7faf17c73) return true; // WETH9
        return false;
    }

    function isWhitelistedToken(address token) public pure returns (bool) {
        if (token == 0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d) return true; // USDC
        if (token == 0x980B62Da83eFf3D4576C647993b0c1D7faf17c73) return true; // WETH9
        return false;
    }

    function setupSession(address _agent, uint40 _validUntil, uint256 _dailySpendLimit) external {
        if (msg.sender != address(this)) revert Unauthorized();
        
        AgentStorage storage $ = _getAgentStorage();
        $.agent = _agent;
        $.validUntil = _validUntil;
        $.dailySpendLimit = _dailySpendLimit;
        $.dailySpentAmount = 0;
        $.lastSpendDay = uint40(block.timestamp / 86400);
    }

    function approveToken(address token, address spender, uint256 amount) external {
        AgentStorage storage $ = _getAgentStorage();
        if (msg.sender != $.agent) revert Unauthorized();
        if (block.timestamp > $.validUntil) revert SessionExpired();
        
        if (!isWhitelistedToken(token)) revert UnapprovedToken();
        if (!isWhitelisted(spender)) revert NotWhitelisted();

        IERC20(token).approve(spender, amount);
    }

    function execute(address target, uint256 value, bytes calldata data) external payable returns (bytes memory) {
        AgentStorage storage $ = _getAgentStorage();

        if (msg.sender != $.agent) revert Unauthorized();
        if (block.timestamp > $.validUntil) revert SessionExpired();
        if (!isWhitelisted(target)) revert NotWhitelisted();

        uint40 currentDay = uint40(block.timestamp / 86400);
        if (currentDay > $.lastSpendDay) {
            $.dailySpentAmount = 0;
            $.lastSpendDay = currentDay;
        }

        if ($.dailySpentAmount + value > $.dailySpendLimit) revert DailyLimitExceeded();
        $.dailySpentAmount += value;

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
