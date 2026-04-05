require('dotenv').config();
const express = require('express');
const cors = require('cors');
const { ethers } = require('ethers');

const app = express();
app.use(cors());
app.use(express.json());

const RPC_URL = process.env.RPC_URL || "http://127.0.0.1:8545";
const AGENT_PRIVATE_KEY = process.env.AGENT_PRIVATE_KEY || "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d";

const provider = new ethers.JsonRpcProvider(RPC_URL);
const wallet = new ethers.Wallet(AGENT_PRIVATE_KEY, provider);

const AGENT_WALLET_ABI = [
    "function execute(address target, uint256 value, bytes calldata data) external payable returns (bytes memory)",
    "function approveToken(address token, address spender, uint256 amount) external"
];

let localNonce = null;

async function getNextNonce() {
    if (localNonce === null) {
        localNonce = await provider.getTransactionCount(wallet.address, "latest");
        console.log("Initialized localNonce to", localNonce);
    }
    const nonceToUse = localNonce;
    localNonce++;
    console.log("Returning nonce", nonceToUse);
    return nonceToUse;
}

app.post('/execute', async (req, res) => {
    try {
        const { user_address, target_protocol, value, calldata } = req.body;
        
        const agentWalletContract = new ethers.Contract(user_address, AGENT_WALLET_ABI, wallet);
        
        const gasEstimate = await agentWalletContract.execute.estimateGas(
            target_protocol, 
            value || 0, 
            calldata || "0x"
        );
        const gasLimit = (gasEstimate * 120n) / 100n;
        const feeData = await provider.getFeeData();
        
        const nonce = await getNextNonce();
        
        const tx = await agentWalletContract.execute(
            target_protocol, 
            value || 0, 
            calldata || "0x", 
            {
                gasLimit,
                maxFeePerGas: feeData.maxFeePerGas,
                maxPriorityFeePerGas: feeData.maxPriorityFeePerGas,
                nonce
            }
        );
        
        await tx.wait(1);
        res.json({ tx_hash: tx.hash });
    } catch (error) {
        localNonce = null; // reset nonce on error
        console.error("Execute error:", error);
        res.status(500).json({ error: error.message });
    }
});

app.post('/approveToken', async (req, res) => {
    try {
        const { user_address, token_address, spender, amount } = req.body;
        
        const agentWalletContract = new ethers.Contract(user_address, AGENT_WALLET_ABI, wallet);
        
        const gasEstimate = await agentWalletContract.approveToken.estimateGas(token_address, spender, amount);
        const gasLimit = (gasEstimate * 120n) / 100n;
        const feeData = await provider.getFeeData();
        
        const nonce = await getNextNonce();
        
        const tx = await agentWalletContract.approveToken(
            token_address, 
            spender, 
            amount, 
            {
                gasLimit,
                maxFeePerGas: feeData.maxFeePerGas,
                maxPriorityFeePerGas: feeData.maxPriorityFeePerGas,
                nonce
            }
        );
        
        await tx.wait(1);
        res.json({ tx_hash: tx.hash });
    } catch (error) {
        localNonce = null; // reset nonce on error
        console.error("Approve error:", error);
        res.status(500).json({ error: error.message });
    }
});

app.get('/health', (req, res) => {
    res.json({ status: "ok", address: wallet.address });
});

const PORT = process.env.PORT || 3001;
app.listen(PORT, () => {
    console.log(`Ethers.js Signer service running on port ${PORT}`);
    console.log(`Agent Address: ${wallet.address}`);
});
