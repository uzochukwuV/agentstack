// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";
import "./SubscriptionManager.sol";

contract SkillRegistry is Ownable {
    SubscriptionManager public subscriptionManager;

    struct Skill {
        string name;
        uint8 minTier;
        bool active;
    }

    mapping(uint256 => Skill) public skills;
    mapping(address => mapping(uint256 => bool)) public unlockedSkills;

    event SkillUnlocked(address indexed user, uint256 indexed skillId);
    event SkillAdded(uint256 indexed id, string name, uint8 minTier);

    error InvalidSkill();
    error NotSubscribed();
    error TierTooLow();
    error SkillAlreadyUnlocked();

    constructor(address _subscriptionManager) Ownable(msg.sender) {
        subscriptionManager = SubscriptionManager(_subscriptionManager);

        _addSkill(1, "Aave V4 lend/borrow", 1);
        _addSkill(2, "Uniswap V4 LP", 2);
        _addSkill(3, "GMX V2 perpetuals", 2);
        _addSkill(4, "Pendle yield trading", 3);
        _addSkill(5, "Multi-strategy rebalancing", 3);
    }

    function _addSkill(uint256 id, string memory name, uint8 minTier) internal {
        skills[id] = Skill(name, minTier, true);
        emit SkillAdded(id, name, minTier);
    }

    function addSkill(uint256 id, string memory name, uint8 minTier) external onlyOwner {
        _addSkill(id, name, minTier);
    }

    function unlockSkill(uint256 skillId) external {
        if (!skills[skillId].active) revert InvalidSkill();
        
        bool isActive = subscriptionManager.isActive(msg.sender);
        if (!isActive) revert NotSubscribed();

        (uint8 tier, , ) = subscriptionManager.subscriptions(msg.sender);
        if (tier < skills[skillId].minTier) revert TierTooLow();

        if (unlockedSkills[msg.sender][skillId]) revert SkillAlreadyUnlocked();

        unlockedSkills[msg.sender][skillId] = true;
        emit SkillUnlocked(msg.sender, skillId);
    }

    function hasSkill(address user, uint256 skillId) external view returns (bool) {
        return unlockedSkills[user][skillId] && subscriptionManager.isActive(user);
    }
}
