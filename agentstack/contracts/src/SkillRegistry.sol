// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "./SubscriptionManager.sol";

contract SkillRegistry is Ownable, Pausable {
    using SafeERC20 for IERC20;

    SubscriptionManager public subscriptionManager;
    IERC20 public immutable usdc;

    struct Skill {
        string name;
        uint8 minTier;
        bool active;
        uint256 oneTimePrice; // Add price per the PRD requirement
    }

    mapping(uint256 => Skill) public skills;
    mapping(address => mapping(uint256 => bool)) public unlockedSkills;

    event SkillUnlocked(address indexed user, uint256 indexed skillId, uint256 pricePaid);
    event SkillAdded(uint256 indexed id, string name, uint8 minTier, uint256 price);

    error InvalidSkill();
    error NotSubscribed();
    error TierTooLow();
    error SkillAlreadyUnlocked();
    error TransferFailed();

    constructor(address _subscriptionManager) Ownable(msg.sender) {
        subscriptionManager = SubscriptionManager(_subscriptionManager);
        usdc = subscriptionManager.usdc();

        _addSkill(1, "Aave V4 lend/borrow", 1, 10 * 10**6);
        _addSkill(2, "Uniswap V4 LP", 2, 20 * 10**6);
        _addSkill(3, "GMX V2 perpetuals", 2, 30 * 10**6);
        _addSkill(4, "Pendle yield trading", 3, 50 * 10**6);
        _addSkill(5, "Multi-strategy rebalancing", 3, 100 * 10**6);
    }

    function pause() external onlyOwner {
        _pause();
    }

    function unpause() external onlyOwner {
        _unpause();
    }

    function _addSkill(uint256 id, string memory name, uint8 minTier, uint256 price) internal {
        skills[id] = Skill(name, minTier, true, price);
        emit SkillAdded(id, name, minTier, price);
    }

    function addSkill(uint256 id, string memory name, uint8 minTier, uint256 price) external onlyOwner {
        _addSkill(id, name, minTier, price);
    }

    function unlockSkill(uint256 skillId) external whenNotPaused {
        if (!skills[skillId].active) revert InvalidSkill();
        
        bool isActive = subscriptionManager.isActive(msg.sender);
        if (!isActive) revert NotSubscribed();

        (uint8 tier, , ) = subscriptionManager.subscriptions(msg.sender);
        if (tier < skills[skillId].minTier) revert TierTooLow();

        if (unlockedSkills[msg.sender][skillId]) revert SkillAlreadyUnlocked();

        // Charge the user
        uint256 price = skills[skillId].oneTimePrice;
        if (price > 0) {
            address treasury = subscriptionManager.treasury();
            usdc.safeTransferFrom(msg.sender, treasury, price);
        }

        unlockedSkills[msg.sender][skillId] = true;
        emit SkillUnlocked(msg.sender, skillId, price);
    }

    function hasSkill(address user, uint256 skillId) external view returns (bool) {
        return unlockedSkills[user][skillId] && subscriptionManager.isActive(user);
    }
}
