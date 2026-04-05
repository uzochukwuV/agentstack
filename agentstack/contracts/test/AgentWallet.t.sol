// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/AgentWallet.sol";

contract AgentWalletTest is Test {
    AgentWallet implementation;
    
    address user;
    uint256 userPk;
    
    address agent;
    uint256 agentPk;
    
    address randomThird;
    
    address aavePool = 0xB5020155268d7b32BF0F03BF01f41026e2390F56;
    
    function setUp() public {
        implementation = new AgentWallet();
        (user, userPk) = makeAddrAndKey("user");
        (agent, agentPk) = makeAddrAndKey("agent");
        randomThird = makeAddr("randomThird");
        
        vm.deal(user, 100 ether);
        vm.deal(agent, 100 ether);
    }
    
    function _setupSession() internal {
        Vm.SignedDelegation memory del = vm.signDelegation(address(implementation), userPk);
        vm.attachDelegation(del);
        
        vm.prank(user);
        AgentWallet(user).setupSession(agent, uint40(block.timestamp + 1 days), 1 ether);
    }

    function test_1_DelegationDesignatorIsSet() public {
        _setupSession();
    }

    function test_2_AgentCanCallWhitelisted() public {
        _setupSession();
        
        vm.etch(aavePool, hex"00");

        vm.prank(agent);
        // User's balance is 100 ether. We ask it to send 0.1 ether to aavePool
        AgentWallet(user).execute(aavePool, 0.1 ether, "");
    }

    function test_3_AgentCannotCallNonWhitelisted() public {
        _setupSession();
        
        address nonWhitelisted = makeAddr("nonWhitelisted");
        vm.prank(agent);
        vm.expectRevert(AgentWallet.NotWhitelisted.selector);
        AgentWallet(user).execute(nonWhitelisted, 0, "");
    }

    function test_4_SpendOverDailyLimitReverts() public {
        _setupSession();
        
        vm.etch(aavePool, hex"00");

        vm.prank(agent);
        vm.expectRevert(AgentWallet.DailyLimitExceeded.selector);
        AgentWallet(user).execute(aavePool, 2 ether, "");
    }

    function test_5_ExpiredSessionReverts() public {
        _setupSession();
        
        vm.warp(block.timestamp + 2 days);
        
        vm.prank(agent);
        vm.expectRevert(AgentWallet.SessionExpired.selector);
        AgentWallet(user).execute(aavePool, 0, "");
    }

    function test_6_RevokeSessionPreventsExecution() public {
        _setupSession();
        
        vm.prank(user);
        AgentWallet(user).revokeSession();
        
        vm.prank(agent);
        vm.expectRevert(AgentWallet.Unauthorized.selector);
        AgentWallet(user).execute(aavePool, 0, "");
    }

    function test_7_ThirdPartyCannotExecute() public {
        _setupSession();
        
        vm.prank(randomThird);
        vm.expectRevert(AgentWallet.Unauthorized.selector);
        AgentWallet(user).execute(aavePool, 0, "");
    }
}
