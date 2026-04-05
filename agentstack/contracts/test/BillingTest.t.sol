// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/SubscriptionManager.sol";
import "../src/SkillRegistry.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract MockUSDC is ERC20 {
    constructor() ERC20("USD Coin", "USDC") {}

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}

contract BillingTest is Test {
    SubscriptionManager public subManager;
    SkillRegistry public registry;
    MockUSDC public usdc;

    address public treasury;
    address public user;
    address public nonPayer;

    function setUp() public {
        usdc = new MockUSDC();
        treasury = makeAddr("treasury");
        user = makeAddr("user");
        nonPayer = makeAddr("nonPayer");

        subManager = new SubscriptionManager(address(usdc), treasury);
        registry = new SkillRegistry(address(subManager));

        // Setup user with USDC and allowance
        usdc.mint(user, 10000 * 10**18);
        
        vm.startPrank(user);
        // Approve both the SubscriptionManager and the SkillRegistry to pull USDC
        usdc.approve(address(subManager), type(uint256).max);
        usdc.approve(address(registry), type(uint256).max);
        vm.stopPrank();

        usdc.mint(nonPayer, 10000 * 10**18); // no allowance
    }

    function test_1_SubscribeTier2() public {
        vm.prank(user);
        subManager.subscribe(2);

        assertEq(usdc.balanceOf(treasury), 100 * 10**6);
        (uint8 tier, uint40 paidUntil, bool active) = subManager.subscriptions(user);
        assertEq(tier, 2);
        assertTrue(active);
        assertTrue(paidUntil > block.timestamp);
    }

    function test_2_SubscribeWithoutAllowanceReverts() public {
        vm.prank(nonPayer);
        vm.expectRevert(); 
        subManager.subscribe(2);
    }

    function test_3_IsActiveAfterWarp() public {
        vm.prank(user);
        subManager.subscribe(2);

        assertTrue(subManager.isActive(user));

        vm.warp(block.timestamp + 32 days);
        assertFalse(subManager.isActive(user));
    }

    function test_4_RenewSubscriptionPullsUSDC() public {
        vm.prank(user);
        subManager.subscribe(2);

        vm.warp(block.timestamp + 31 days - 1 hours); 

        uint256 treasuryBalBefore = usdc.balanceOf(treasury);

        address[] memory upkeepData = new address[](1);
        upkeepData[0] = user;

        subManager.performUpkeep(abi.encode(upkeepData));

        assertEq(usdc.balanceOf(treasury), treasuryBalBefore + 100 * 10**6);
        (, uint40 paidUntil, bool active) = subManager.subscriptions(user);
        assertTrue(active);
        assertTrue(paidUntil > block.timestamp);
    }

    function test_5_RenewWithExhaustedAllowance() public {
        vm.prank(user);
        subManager.subscribe(2);

        vm.prank(user);
        usdc.approve(address(subManager), 0);

        vm.warp(block.timestamp + 31 days - 1 hours);

        address[] memory upkeepData = new address[](1);
        upkeepData[0] = user;

        vm.expectEmit(true, false, false, false);
        emit SubscriptionManager.SubscriptionLapsed(user);
        subManager.performUpkeep(abi.encode(upkeepData));

        (, , bool active) = subManager.subscriptions(user);
        assertFalse(active);
    }

    function test_6_UnlockSkillPro() public {
        vm.prank(user);
        subManager.subscribe(2); 

        vm.prank(user);
        registry.unlockSkill(3); 

        assertTrue(registry.hasSkill(user, 3));
    }

    function test_7_HasSkillAfterWarp() public {
        vm.prank(user);
        subManager.subscribe(2);

        vm.prank(user);
        registry.unlockSkill(3);

        assertTrue(registry.hasSkill(user, 3));

        vm.warp(block.timestamp + 32 days);
        assertFalse(registry.hasSkill(user, 3));
    }

    function test_8_UnlockUnknownSkillReverts() public {
        vm.prank(user);
        subManager.subscribe(2);

        vm.prank(user);
        vm.expectRevert(SkillRegistry.InvalidSkill.selector);
        registry.unlockSkill(99);
    }

    function testFuzz_SubscribeRandomTier(uint8 tier) public {
        vm.assume(tier != 1 && tier != 2 && tier != 3);
        vm.prank(user);
        vm.expectRevert(SubscriptionManager.InvalidTier.selector);
        subManager.subscribe(tier);
    }
}
