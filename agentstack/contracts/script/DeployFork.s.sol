// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Script.sol";
import "../src/AgentWallet.sol";
import "../src/SubscriptionManager.sol";
import "../src/SkillRegistry.sol";

contract DeployForkScript is Script {
    function run() external {
        // Arbitrum Sepolia USDC
        address usdc = 0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d;
        
        // We use anvil account 0 to deploy
        uint256 deployerPrivateKey = 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80;
        address deployer = vm.addr(deployerPrivateKey);

        vm.startBroadcast(deployerPrivateKey);

        // 1. Deploy AgentWallet implementation
        AgentWallet agentWallet = new AgentWallet();
        console.log("AgentWallet deployed at:", address(agentWallet));

        // 2. Deploy SubscriptionManager
        address treasury = deployer; // Use deployer as treasury for tests
        SubscriptionManager subManager = new SubscriptionManager(usdc, treasury);
        console.log("SubscriptionManager deployed at:", address(subManager));

        // 3. Deploy SkillRegistry
        SkillRegistry registry = new SkillRegistry(address(subManager));
        console.log("SkillRegistry deployed at:", address(registry));

        vm.stopBroadcast();
    }
}
