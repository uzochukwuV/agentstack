// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@chainlink/contracts/automation/AutomationCompatible.sol";

contract SubscriptionManager is AutomationCompatibleInterface, Ownable {
    using SafeERC20 for IERC20;

    IERC20 public immutable usdc;
    address public treasury;

    struct Subscription {
        uint8 tier; // 1 = Starter, 2 = Pro, 3 = Elite
        uint40 paidUntil;
        bool active;
    }

    mapping(address => Subscription) public subscriptions;
    address[] public activeUsers;
    mapping(address => uint256) public activeUserIndex; // To manage array efficiently

    uint256 public constant SECONDS_PER_MONTH = 31 days; // Simple assumption

    mapping(uint8 => uint256) public tierPrices;

    event Subscribed(address indexed user, uint8 tier, uint256 amount);
    event SubscriptionRenewed(address indexed user, uint256 amount);
    event SubscriptionLapsed(address indexed user);
    event TreasuryUpdated(address newTreasury);

    error InvalidTier();
    error AlreadyActive();
    error TransferFailed();

    constructor(address _usdc, address _treasury) Ownable(msg.sender) {
        usdc = IERC20(_usdc);
        treasury = _treasury;

        tierPrices[1] = 50 * 10**6;  // 50 USDC
        tierPrices[2] = 100 * 10**6; // 100 USDC
        tierPrices[3] = 250 * 10**6; // 250 USDC
    }

    function setTreasury(address _treasury) external onlyOwner {
        treasury = _treasury;
        emit TreasuryUpdated(_treasury);
    }

    function subscribe(uint8 tier) external {
        if (tier < 1 || tier > 3) revert InvalidTier();
        if (isActive(msg.sender)) revert AlreadyActive();

        uint256 price = tierPrices[tier];
        usdc.safeTransferFrom(msg.sender, treasury, price);

        subscriptions[msg.sender] = Subscription({
            tier: tier,
            paidUntil: uint40(block.timestamp + SECONDS_PER_MONTH),
            active: true
        });

        _addActiveUser(msg.sender);

        emit Subscribed(msg.sender, tier, price);
    }

    function isActive(address user) public view returns (bool) {
        return subscriptions[user].active && subscriptions[user].paidUntil > block.timestamp;
    }

    function renewSubscription(address user) public {
        Subscription storage sub = subscriptions[user];
        if (!sub.active) return; // already lapsed or never active

        // Only renew if less than 1 day remaining or already expired
        if (sub.paidUntil > block.timestamp + 1 days) return;

        uint256 price = tierPrices[sub.tier];
        
        // Check allowance and balance
        if (usdc.allowance(user, address(this)) >= price && usdc.balanceOf(user) >= price) {
            usdc.safeTransferFrom(user, treasury, price);
            sub.paidUntil = uint40(block.timestamp + SECONDS_PER_MONTH);
            emit SubscriptionRenewed(user, price);
        } else {
            // Lapsed
            sub.active = false;
            _removeActiveUser(user);
            emit SubscriptionLapsed(user);
        }
    }

    function _addActiveUser(address user) private {
        if (activeUserIndex[user] == 0 && (activeUsers.length == 0 || activeUsers[0] != user)) {
            activeUsers.push(user);
            activeUserIndex[user] = activeUsers.length - 1;
        }
    }

    function _removeActiveUser(address user) private {
        uint256 index = activeUserIndex[user];
        if (activeUsers.length > 0 && activeUsers[index] == user) {
            address lastUser = activeUsers[activeUsers.length - 1];
            activeUsers[index] = lastUser;
            activeUserIndex[lastUser] = index;
            activeUsers.pop();
            activeUserIndex[user] = 0; // Or arbitrary since we verify by value
        }
    }

    // Chainlink Automation
    function checkUpkeep(bytes calldata /* checkData */) external view override returns (bool upkeepNeeded, bytes memory performData) {
        address[] memory needsRenewal = new address[](activeUsers.length);
        uint256 count = 0;

        for (uint256 i = 0; i < activeUsers.length; i++) {
            address user = activeUsers[i];
            if (subscriptions[user].paidUntil <= block.timestamp + 1 days) {
                needsRenewal[count] = user;
                count++;
            }
        }

        if (count > 0) {
            upkeepNeeded = true;
            // Trim array
            address[] memory finalNeedsRenewal = new address[](count);
            for (uint256 i = 0; i < count; i++) {
                finalNeedsRenewal[i] = needsRenewal[i];
            }
            performData = abi.encode(finalNeedsRenewal);
        }
    }

    function performUpkeep(bytes calldata performData) external override {
        address[] memory users = abi.decode(performData, (address[]));
        for (uint256 i = 0; i < users.length; i++) {
            renewSubscription(users[i]);
        }
    }
}
