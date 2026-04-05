# AgentStack — DeFAI Agent Hosting Platform
## Progressive Implementation Guide

> **What you're building:** A hosted DeFAI platform on Arbitrum where users pay SterlingStack a monthly USDC fee to keep an AI trading agent running, and unlock protocol integrations ("skills") à la carte. Each user's funds stay in their own EIP-7702 smart account. The agent (Python / LangGraph / Claude Sonnet) runs on your infra, polls every 5 minutes, and executes via scoped session keys.

---

## Architecture Overview

```
[User Chat UI + Dashboard]
        │
        ▼
[FastAPI Backend + WebSocket]
        │
        ├── [PostgreSQL] — user goals, agent config, tx history
        ├── [Redis] — heartbeat queue, session cache, rate limiting
        └── [Celery Workers] — 5-min agent heartbeat loop (horizontal scale)
                │
                ├── [LangGraph Agent Core]  ← Claude Sonnet (strategy decisions only)
                │       │
                │       └── [Skill Registry] — loads only unlocked skills per user
                │               ├── aave_v4_skill.py
                │               ├── gmx_v2_skill.py
                │               ├── uniswap_v4_skill.py
                │               └── pendle_skill.py
                │
                └── [Web3 Executor]
                        ├── EIP-7702 session key signing
                        ├── Arbitrum RPC (Alchemy / Infura)
                        └── Chainlink oracle reads

[Billing Contract on Arbitrum]
  ├── SubscriptionManager.sol  — monthly USDC pull, tier gating
  ├── SkillRegistry.sol        — on-chain skill unlock mapping per user
  └── AgentWallet.sol          — EIP-7702 delegation contract (shared implementation)
```

---

## Issue 1 — Monorepo Setup and Project Vault

**What this is:** Creating the repo structure, tooling, secrets management, and environment separation from day one. Getting this wrong cascades into every future issue.

**The structure:**

```
agentstack/
├── contracts/          # Solidity (Foundry)
│   ├── src/
│   ├── test/
│   └── foundry.toml
├── backend/            # Python (FastAPI + Celery)
│   ├── app/
│   │   ├── api/        # REST + WebSocket routes
│   │   ├── agent/      # LangGraph agent core
│   │   ├── skills/     # Pluggable skill modules
│   │   ├── executor/   # Web3 tx signing
│   │   └── billing/    # On-chain billing checker
│   ├── workers/        # Celery heartbeat tasks
│   ├── pyproject.toml
│   └── .env.example
├── frontend/           # Next.js 14 (App Router)
│   ├── app/
│   ├── components/
│   └── package.json
├── infra/              # Docker Compose + later K8s
│   ├── docker-compose.dev.yml
│   └── docker-compose.prod.yml
└── .github/
    └── workflows/      # CI/CD
```

**Key decisions:**
- Use **Foundry** for contracts (faster tests, better fork support than Hardhat for Arbitrum)
- Use **uv** (not pip) for Python dependency management — significantly faster, lockfile-based
- Use **dotenv-vault** or **Doppler** for secrets across environments — never commit private keys
- PostgreSQL for persistent state, Redis for ephemeral agent state and job queues
- Environment separation: `local` → `arbitrum-sepolia` → `arbitrum-mainnet`

**Where to learn:**
- Foundry book: https://book.getfoundry.sh/getting-started/installation
- uv docs: https://docs.astral.sh/uv/
- Doppler secrets: https://docs.doppler.com/docs/start
- Docker Compose for Python + Redis + Postgres: https://docs.docker.com/compose/

**Acceptance criteria:**
- `docker compose up` starts backend, worker, postgres, redis
- `forge test` runs on Arbitrum Sepolia fork
- No secrets in git history

---

## Issue 2 — EIP-7702 Smart Account (AgentWallet Contract)

**What this is:** The custody architecture. Users delegate their EOA to your `AgentWallet` implementation contract. Your backend agent gets a session key with scoped permissions — it can call specific protocols up to defined spend limits, but cannot withdraw funds to external addresses.

**How EIP-7702 works:**
EIP-7702 (live on Ethereum mainnet since Pectra, May 2025) introduces transaction type `0x04`. An EOA signs an `authorization_list` entry: `[chain_id, implementation_address, nonce, signature]`. This stores a "delegation designator" (`0xef0100 || address`) on the EOA — making the EOA behave like the implementation contract until revoked.

**Your `AgentWallet.sol` needs:**

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

// Shared implementation — one deployment, many EOA delegators
contract AgentWallet {
    // Per-EOA storage (via delegatecall context — storage lives on EOA)
    mapping(address => SessionKey) public sessionKeys;
    
    struct SessionKey {
        address agent;          // your backend signer
        uint256 spendLimitUSDC; // max per-tx
        uint256 validUntil;     // unix timestamp
        address[] allowedProtocols; // Aave, GMX, Uniswap routers only
    }
    
    // Owner = the EOA itself (address(this) in delegatecall context)
    modifier onlyOwner() {
        require(msg.sender == address(this), "not owner");
        _;
    }
    
    function setSessionKey(address agent, uint256 limitUSDC, uint256 duration, address[] calldata protocols) 
        external onlyOwner {
        sessionKeys[address(this)] = SessionKey(agent, limitUSDC, block.timestamp + duration, protocols);
    }
    
    function execute(address target, uint256 value, bytes calldata data) external returns (bytes memory) {
        SessionKey memory key = sessionKeys[address(this)];
        require(msg.sender == key.agent, "not agent");
        require(block.timestamp <= key.validUntil, "session expired");
        require(_isAllowedProtocol(target, key.allowedProtocols), "protocol not allowed");
        // No withdrawals to unknown addresses
        (bool ok, bytes memory result) = target.call{value: value}(data);
        require(ok, "call failed");
        return result;
    }
    
    function revokeSession() external onlyOwner {
        delete sessionKeys[address(this)];
    }
    
    function _isAllowedProtocol(address target, address[] memory allowed) internal pure returns (bool) {
        for (uint i = 0; i < allowed.length; i++) {
            if (allowed[i] == target) return true;
        }
        return false;
    }
}
```

**Storage collision warning:** EIP-7702 storage lives on the EOA. If you change your implementation contract's storage layout, existing delegators break. Use ERC-7201 namespaced storage from day one:
```solidity
bytes32 private constant STORAGE_SLOT = keccak256("agentstack.agentWallet.v1");
```

**Session key flow:**
1. User signs EIP-7702 authorization on frontend (using Viem's `signAuthorization`)
2. Your backend submits a type-0x04 transaction with the authorization
3. User's EOA now delegates to `AgentWallet` implementation
4. User calls `setSessionKey()` granting your agent address limited access
5. Agent signs txs using a hot wallet (the "agent key") — stored in Doppler/AWS KMS

**Where to learn:**
- EIP-7702 spec: https://eips.ethereum.org/EIPS/eip-7702
- Viem EIP-7702 guide: https://viem.sh/experimental/eip7702/signAuthorization
- OpenZeppelin EIP-7702 EOA Delegation: https://docs.openzeppelin.com/contracts/5.x/eoa-delegation
- Attack surfaces to avoid: https://www.nethermind.io/blog/eip-7702-attack-surfaces-what-developers-should-know
- QuickNode implementation walkthrough: https://www.quicknode.com/guides/ethereum-development/smart-contracts/eip-7702-smart-accounts

**Security non-negotiables:**
- Never store the agent's private key in plaintext — use AWS KMS or Hashicorp Vault
- Always validate `allowedProtocols` against a contract-level whitelist, not just a session-level list
- Add a `maxSpendPerDay` counter to prevent session key abuse
- Audit with Certik or OpenZeppelin before mainnet

---

## Issue 3 — On-Chain Billing (SubscriptionManager + SkillRegistry)

**What this is:** The revenue smart contract. Users approve USDC allowance once. Chainlink Automation triggers monthly pulls. SkillRegistry maps which skills each address has unlocked.

**`SubscriptionManager.sol` design:**

```solidity
contract SubscriptionManager {
    IERC20 public immutable USDC;
    address public treasury; // SterlingStack multisig
    
    struct Subscription {
        uint8 tier;          // 0=free, 1=starter($10), 2=pro($25), 3=elite($50)
        uint256 paidUntil;   // unix timestamp
        bool active;
    }
    
    mapping(address => Subscription) public subscriptions;
    
    uint256[4] public tierPrices = [0, 10e6, 25e6, 50e6]; // USDC (6 decimals)
    
    // User pre-approves USDC allowance once
    function subscribe(uint8 tier) external {
        require(tier >= 1 && tier <= 3, "invalid tier");
        USDC.transferFrom(msg.sender, treasury, tierPrices[tier]);
        subscriptions[msg.sender] = Subscription({
            tier: tier,
            paidUntil: block.timestamp + 30 days,
            active: true
        });
        emit Subscribed(msg.sender, tier, block.timestamp + 30 days);
    }
    
    // Called by Chainlink Automation monthly
    function renewSubscription(address user) external onlyAutomation {
        Subscription storage sub = subscriptions[user];
        require(sub.active, "no active sub");
        require(block.timestamp >= sub.paidUntil - 1 days, "too early");
        // Pull payment — fails gracefully if allowance exhausted (user churns)
        bool ok = USDC.transferFrom(user, treasury, tierPrices[sub.tier]);
        if (ok) {
            sub.paidUntil += 30 days;
        } else {
            sub.active = false;
            emit SubscriptionLapsed(user);
        }
    }
    
    function isActive(address user) public view returns (bool) {
        return subscriptions[user].active && subscriptions[user].paidUntil > block.timestamp;
    }
}
```

**`SkillRegistry.sol` design:**

```solidity
contract SkillRegistry {
    // skillId → price in USDC/month
    mapping(uint8 => uint256) public skillPrices;
    // user → skillId → paid until
    mapping(address => mapping(uint8 => uint256)) public skillUnlocks;
    
    function unlockSkill(uint8 skillId) external {
        require(skillPrices[skillId] > 0, "unknown skill");
        USDC.transferFrom(msg.sender, treasury, skillPrices[skillId]);
        skillUnlocks[msg.sender][skillId] = block.timestamp + 30 days;
        emit SkillUnlocked(msg.sender, skillId);
    }
    
    function hasSkill(address user, uint8 skillId) public view returns (bool) {
        return skillUnlocks[user][skillId] > block.timestamp;
    }
}
```

**Skill IDs (start simple):**
| ID | Skill | Price/month |
|---|---|---|
| 1 | Aave V4 lend/borrow | included in Starter |
| 2 | Uniswap V4 LP management | Pro |
| 3 | GMX V2 perpetuals | Pro |
| 4 | Pendle yield trading | Elite |
| 5 | Multi-strategy rebalancing | Elite |

**Renewal automation:** Use **Chainlink Automation** (upkeep) with a `checkUpkeep` / `performUpkeep` pattern. Your upkeep contract keeps a list of users due for renewal and calls `renewSubscription()` in batches.

**Where to learn:**
- Chainlink Automation: https://docs.chain.link/chainlink-automation
- ERC-4337 recurring payments with session keys: https://technorely.com/insights/recurring-payments-in-web-3-via-account-abstraction-erc-4337
- Superfluid streaming alternative: https://docs.superfluid.finance/
- OpenZeppelin ERC1155 for NFT subscription tokens: https://docs.openzeppelin.com/contracts/5.x/erc1155

---

## Issue 4 — Pluggable Skill Architecture (Backend)

**What this is:** The most important backend design decision. Skills must be loadable/unloadable at runtime per user without restarting the agent. Each skill is a self-contained Python module exposing LangGraph-compatible tools.

**The skill interface contract:**

```python
# backend/skills/base.py
from abc import ABC, abstractmethod
from langchain_core.tools import BaseTool
from typing import List

class BaseSkill(ABC):
    SKILL_ID: int           # matches on-chain SkillRegistry ID
    SKILL_NAME: str         # human readable
    REQUIRED_TIER: int      # minimum subscription tier
    
    @abstractmethod
    def get_tools(self) -> List[BaseTool]:
        """Return LangGraph-compatible tool list for this skill."""
        pass
    
    @abstractmethod
    async def get_position_summary(self, user_address: str) -> dict:
        """Return current positions/balances for this protocol."""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Verify protocol is reachable and responding."""
        pass
```

**Example skill implementation:**

```python
# backend/skills/aave_v4_skill.py
from langchain_core.tools import tool
from .base import BaseSkill
from ..executor import sign_and_send

class AaveV4Skill(BaseSkill):
    SKILL_ID = 1
    SKILL_NAME = "Aave V4"
    REQUIRED_TIER = 1

    def get_tools(self):
        @tool
        def aave_supply(asset: str, amount_usdc: float, user_address: str) -> str:
            """Supply an asset to Aave V4 to earn lending yield on Arbitrum."""
            # Build calldata, validate against session key limits, execute
            calldata = self._build_supply_calldata(asset, amount_usdc)
            tx_hash = sign_and_send(user_address, AAVE_POOL_ARBITRUM, calldata)
            return f"Supplied {amount_usdc} USDC to Aave. TX: {tx_hash}"
        
        @tool
        def aave_withdraw(asset: str, amount_usdc: float, user_address: str) -> str:
            """Withdraw supplied assets from Aave V4."""
            calldata = self._build_withdraw_calldata(asset, amount_usdc)
            tx_hash = sign_and_send(user_address, AAVE_POOL_ARBITRUM, calldata)
            return f"Withdrew {amount_usdc} USDC from Aave. TX: {tx_hash}"
        
        @tool
        def aave_get_health_factor(user_address: str) -> str:
            """Get current Aave health factor for liquidation risk monitoring."""
            hf = self._read_health_factor(user_address)
            return f"Health factor: {hf}. {'WARNING: below 1.5' if hf < 1.5 else 'Safe'}"
        
        return [aave_supply, aave_withdraw, aave_get_health_factor]
    
    async def get_position_summary(self, user_address: str) -> dict:
        # Read from Aave Data Provider contract
        return {"protocol": "Aave V4", "supplied": ..., "borrowed": ..., "health_factor": ...}
```

**Skill Registry (runtime loader):**

```python
# backend/skills/registry.py
from typing import Dict, List
from .aave_v4_skill import AaveV4Skill
from .gmx_v2_skill import GmxV2Skill
from .uniswap_v4_skill import UniswapV4Skill
from .pendle_skill import PendleSkill

ALL_SKILLS = {
    1: AaveV4Skill,
    2: UniswapV4Skill,
    3: GmxV2Skill,
    4: PendleSkill,
}

def load_skills_for_user(user_address: str, skill_ids: List[int]) -> List:
    """Instantiate only the skills this user has unlocked on-chain."""
    return [ALL_SKILLS[sid]() for sid in skill_ids if sid in ALL_SKILLS]

def get_tools_for_user(skill_instances: List) -> List:
    """Flatten all tools from all loaded skills."""
    tools = []
    for skill in skill_instances:
        tools.extend(skill.get_tools())
    return tools
```

**Adding a new skill (zero downtime):**
1. Create `backend/skills/new_skill.py` implementing `BaseSkill`
2. Add to `ALL_SKILLS` dict in `registry.py`
3. Deploy to backend workers (rolling restart)
4. Add `skillId` and price to `SkillRegistry.sol` via admin tx
5. Done — no contract redeployment, no user disruption

**Where to learn:**
- LangGraph tools guide: https://langchain-ai.github.io/langgraph/how-tos/tool-calling/
- LangChain `@tool` decorator: https://python.langchain.com/docs/concepts/tools/
- Aave V4 contract interfaces (Arbitrum): https://docs.aave.com/developers/deployed-contracts/v3-mainnet/arbitrum
- GMX V2 SDK: https://github.com/gmx-io/gmx-synthetics
- Uniswap V4 hook documentation: https://docs.uniswap.org/contracts/v4/overview

---

## Issue 5 — LangGraph Agent Core

**What this is:** The brain of each user's agent. LangGraph (not plain LangChain) is used because it provides stateful execution graphs, persistent checkpointing, and human-in-the-loop interrupts — critical for a production financial agent.

**Why LangGraph over AgentExecutor:** LangGraph is now the recommended production framework for agents requiring state persistence, retry logic, and conditional branching. The graph-based architecture maps directly to the agent's decision cycle: observe → reason → plan → execute → report.

**Agent graph design:**

```python
# backend/agent/graph.py
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver
from typing import TypedDict, List

class AgentState(TypedDict):
    user_address: str
    user_goals: dict          # loaded from DB: {"max_risk": "medium", "target_yield": 0.08}
    positions: dict           # current protocol positions
    utilisation_rate: float   # % of capital deployed
    pending_actions: List[str]
    messages: List            # LangGraph message history
    last_error: str | None

def build_agent_graph(tools: list, checkpointer: PostgresSaver):
    graph = StateGraph(AgentState)
    
    graph.add_node("fetch_positions", fetch_positions_node)
    graph.add_node("analyze", analyze_node)     # Claude called here
    graph.add_node("execute", execute_node)     # tx signing
    graph.add_node("report", report_node)       # write to DB for dashboard
    
    graph.set_entry_point("fetch_positions")
    graph.add_edge("fetch_positions", "analyze")
    
    # Conditional: only execute if agent decided action is needed
    graph.add_conditional_edges("analyze", should_execute, {
        "execute": "execute",
        "skip": "report"
    })
    graph.add_edge("execute", "report")
    graph.add_edge("report", END)
    
    return graph.compile(checkpointer=checkpointer, tools=tools)

def should_execute(state: AgentState) -> str:
    return "execute" if state["pending_actions"] else "skip"
```

**System prompt for Claude (critical — this controls behavior):**

```python
AGENT_SYSTEM_PROMPT = """
You are an autonomous DeFi portfolio manager on Arbitrum for user {user_address}.

USER GOALS:
{user_goals}

CURRENT POSITIONS:
{positions}

UTILISATION RATE: {utilisation_rate}%

RULES (NEVER VIOLATE):
1. Never deploy more than {max_position_pct}% of capital in a single protocol
2. Never execute if Aave health factor < 1.5
3. Never execute transactions larger than {max_tx_usdc} USDC
4. Always prefer stablecoin positions unless user explicitly opted into volatile assets
5. Do not trade purely on price speculation — only rebalance for yield or risk management

AVAILABLE TOOLS: {tool_names}

Analyze the current state and determine if any rebalancing is needed. 
Be conservative. If uncertain, do nothing and explain why.
"""
```

**Checkpointing:** Use `PostgresSaver` so each user's agent state persists across worker restarts. Each run is stored with `thread_id = user_address`, allowing the agent to "remember" previous decisions and positions.

**Where to learn:**
- LangGraph official docs: https://langchain-ai.github.io/langgraph/
- LangGraph + PostgreSQL checkpointing: https://langchain-ai.github.io/langgraph/how-tos/persistence-postgres/
- Production agent patterns (50+ deployments): https://www.digitalapplied.com/blog/langchain-ai-agents-guide-2025
- LangGraph vs AgentExecutor comparison: https://www.leanware.co/insights/langchain-agents-complete-guide-in-2025

---

## Issue 6 — 5-Minute Heartbeat Loop (Celery + Redis, 1000+ Users)

**What this is:** The scheduling backbone. Every user's agent must tick every 5 minutes. At 1000 users, that's ~3.3 agent runs per second continuously. This requires proper job queue design from the start.

**Why Celery + Redis (not cron):**
- Cron jobs don't scale horizontally and have no retry logic
- Celery tasks can be distributed across multiple worker processes/machines
- Redis as broker gives sub-millisecond task dispatch
- Beat scheduler handles the 5-minute cadence
- Each task is stateless — the agent state is in PostgreSQL (LangGraph checkpoint)

**Core heartbeat task:**

```python
# backend/workers/heartbeat.py
from celery import Celery
from celery.utils.log import get_task_logger
import asyncio

app = Celery('agentstack', broker='redis://redis:6379/0', backend='redis://redis:6379/1')
logger = get_task_logger(__name__)

@app.task(bind=True, max_retries=3, default_retry_delay=30)
def run_agent_heartbeat(self, user_address: str):
    """Single user agent tick. Stateless — all state in Postgres."""
    try:
        # 1. Check subscription is active (Redis cache, refresh every 5 min)
        if not billing_cache.is_active(user_address):
            logger.info(f"Skipping {user_address} — subscription lapsed")
            return
        
        # 2. Load user goals and unlocked skill IDs from DB
        user_config = db.get_user_config(user_address)
        skill_ids = onchain.get_unlocked_skills(user_address)  # cached in Redis
        
        # 3. Build agent with correct tools
        skills = load_skills_for_user(user_address, skill_ids)
        tools = get_tools_for_user(skills)
        agent = build_agent_graph(tools, checkpointer)
        
        # 4. Run the graph
        asyncio.run(agent.ainvoke(
            {"user_address": user_address, "user_goals": user_config.goals},
            config={"configurable": {"thread_id": user_address}}
        ))
        
    except Exception as exc:
        logger.error(f"Agent error for {user_address}: {exc}")
        self.retry(exc=exc)

# Celery Beat schedule — dispatches all active users every 5 min
@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(300.0, dispatch_all_agents.s(), name='heartbeat-5min')

@app.task
def dispatch_all_agents():
    """Fetch all active users and dispatch individual heartbeat tasks."""
    active_users = db.get_active_subscribers()
    for user in active_users:
        run_agent_heartbeat.delay(user.address)
```

**Scaling math for 1000 users:**
- 1000 users ÷ 300 seconds = 3.3 tasks/second sustained
- Each agent run: ~10-30 seconds (mostly RPC calls, LLM ~5s)
- Peak concurrent tasks: ~30-100 at any time
- Target: 4 Celery workers × 8 concurrency = 32 concurrent tasks
- Scale: Add more worker containers as user count grows

**Worker configuration:**

```bash
# Start workers with concurrency tuned for I/O-bound agent tasks
celery -A backend.workers.heartbeat worker \
  --loglevel=info \
  --concurrency=8 \
  --pool=gevent \     # gevent for I/O-bound (RPC + LLM calls)
  -Q heartbeat

# Beat scheduler (single instance — not replicated)
celery -A backend.workers.heartbeat beat --loglevel=info
```

**Redis key design:**
```
billing:active:{user_address}       → "1" (TTL 310s, refreshed each heartbeat)
skills:unlocked:{user_address}      → JSON list of skill IDs (TTL 3600s)
agent:last_run:{user_address}       → unix timestamp
agent:lock:{user_address}           → distributed lock (prevents double-run)
rate:llm:{user_address}             → LLM call count (daily limit enforcement)
```

**Distributed lock (prevents double-execution):**
```python
def run_with_lock(user_address: str):
    lock_key = f"agent:lock:{user_address}"
    with redis.lock(lock_key, timeout=290):  # 290s < 300s tick
        run_agent_heartbeat(user_address)
```

**Where to learn:**
- Celery docs: https://docs.celeryq.dev/en/stable/
- Celery Beat periodic tasks: https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html
- Gevent worker pool for I/O tasks: https://docs.celeryq.dev/en/stable/userguide/concurrency/gevent.html
- Redis distributed locks (Redlock): https://redis.io/docs/latest/develop/use/patterns/distributed-locks/
- LangChain + Celery + Redis orchestration: https://www.jellyfishtechnologies.com/llm-driven-api-orchestration-using-langchain-celery-redis-queue/

---

## Issue 7 — Web3 Executor and Transaction Signing

**What this is:** The module that takes the agent's decisions and turns them into signed Arbitrum transactions using the session key. Security is paramount — the agent private key is a hot wallet, scoped by the on-chain session key to only allowed protocols and spend limits.

**Executor design:**

```python
# backend/executor/executor.py
from web3 import Web3
from eth_account import Account
import boto3  # For AWS KMS signing

class AgentExecutor:
    def __init__(self, rpc_url: str, agent_private_key: str):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.agent_account = Account.from_key(agent_private_key)
    
    async def execute(self, 
                      user_address: str, 
                      target_contract: str, 
                      calldata: bytes,
                      value: int = 0) -> str:
        """
        Sign and send a transaction via the user's EIP-7702 AgentWallet.
        The AgentWallet.execute() validates session key constraints on-chain.
        """
        # Pre-flight validation (fast fail before spending gas)
        self._validate_session_key_active(user_address)
        
        # Encode the AgentWallet.execute(target, value, calldata) call
        agent_wallet_abi = [...] 
        agent_wallet = self.w3.eth.contract(address=user_address, abi=agent_wallet_abi)
        tx_data = agent_wallet.functions.execute(target_contract, value, calldata).build_transaction({
            'from': self.agent_account.address,
            'gas': 500_000,
            'maxFeePerGas': self._get_base_fee() * 2,
            'nonce': self.w3.eth.get_transaction_count(self.agent_account.address),
        })
        
        # Sign with agent hot wallet
        signed = self.w3.eth.account.sign_transaction(tx_data, self.agent_account.key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        
        # Wait for receipt (with timeout)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        if receipt['status'] == 0:
            raise Exception(f"Transaction reverted: {tx_hash.hex()}")
        
        # Log to DB for user dashboard
        db.log_transaction(user_address, tx_hash.hex(), target_contract, calldata)
        return tx_hash.hex()
    
    def _validate_session_key_active(self, user_address: str):
        """Read on-chain session key before spending any gas."""
        session = agent_wallet_contract.functions.sessionKeys(user_address).call()
        if session['agent'] != self.agent_account.address:
            raise Exception("Session key not set for this user")
        if session['validUntil'] < time.time():
            raise Exception("Session key expired — user must renew")
```

**For production — use AWS KMS instead of raw private key:**
```python
# backend/executor/kms_signer.py
# Sign transactions with AWS KMS — private key never leaves KMS
import boto3
from eth_account._utils.signing import sign_transaction_hash

class KMSSigner:
    def __init__(self, key_id: str):
        self.kms = boto3.client('kms', region_name='us-east-1')
        self.key_id = key_id
    
    def sign(self, tx_hash: bytes) -> bytes:
        response = self.kms.sign(
            KeyId=self.key_id,
            Message=tx_hash,
            MessageType='DIGEST',
            SigningAlgorithm='ECDSA_SHA_256'
        )
        return response['Signature']
```

**Circuit breakers (mandatory):**
```python
# Refuse to execute if any of these are true
CIRCUIT_BREAKERS = [
    lambda state: state["aave_health_factor"] < 1.3,  # Too close to liquidation
    lambda state: state["gas_price_gwei"] > 50,        # Gas spike
    lambda state: state["pending_tx_count"] > 2,       # Queue backup
    lambda state: state["daily_loss_pct"] > 5,         # Daily loss limit hit
]
```

**Where to learn:**
- Web3.py transaction signing: https://web3py.readthedocs.io/en/stable/web3.eth.account.html
- AWS KMS Ethereum signing: https://aws.amazon.com/blogs/database/how-to-sign-ethereum-eip-1559-transactions-using-aws-kms/
- Arbitrum RPC via Alchemy: https://docs.alchemy.com/reference/arbitrum-api-quickstart
- Aave V4 Arbitrum contract addresses: https://docs.aave.com/developers/deployed-contracts/v3-mainnet/arbitrum
- GMX V2 Synthetics contracts: https://github.com/gmx-io/gmx-synthetics#deployments

---

## Issue 8 — FastAPI Backend and WebSocket Dashboard

**What this is:** The REST + WebSocket API that the frontend consumes. Users chat with their agent through this layer. The chat is stored, and the agent's decisions + transaction history are streamed in real time.

**API structure:**

```python
# backend/app/api/
# POST /auth/connect        — sign message to authenticate (no passwords)
# GET  /user/dashboard      — current positions, utilisation, recent txs
# GET  /user/subscription   — tier, paid_until, unlocked skills
# POST /user/goals          — update agent parameters (risk, yield target, etc.)
# WS   /agent/chat          — real-time chat with the agent
# POST /billing/subscribe   — initiate on-chain subscription (returns tx calldata)
# POST /billing/unlock-skill — unlock a skill (returns tx calldata)
# GET  /agent/history       — tx history with agent reasoning
```

**Chat endpoint (WebSocket):**

```python
@router.websocket("/agent/chat")
async def agent_chat(websocket: WebSocket, user_address: str):
    await websocket.accept()
    
    # Load user's agent instance with their unlocked tools
    skill_ids = await onchain.get_unlocked_skills(user_address)
    skills = load_skills_for_user(user_address, skill_ids)
    tools = get_tools_for_user(skills)
    agent = build_agent_graph(tools, checkpointer)
    
    async for message in websocket.iter_text():
        # Stream agent response back token by token
        async for chunk in agent.astream(
            {"messages": [{"role": "user", "content": message}]},
            config={"configurable": {"thread_id": f"chat-{user_address}"}}
        ):
            await websocket.send_text(json.dumps(chunk))
```

**Auth:** Use **Sign-In with Ethereum (SIWE / EIP-4361)** — no passwords, no emails required. User signs a nonce message with their wallet, backend verifies the signature, issues a JWT. This is the standard Web3 auth pattern.

**Where to learn:**
- FastAPI docs: https://fastapi.tiangolo.com/
- SIWE (Sign-In with Ethereum): https://docs.login.xyz/
- LangGraph streaming: https://langchain-ai.github.io/langgraph/how-tos/streaming/
- FastAPI WebSockets: https://fastapi.tiangolo.com/advanced/websockets/

---

## Issue 9 — Frontend (Next.js 14 Dashboard + Chat)

**What this is:** The user-facing product. Three main screens: onboarding (connect wallet, subscribe), dashboard (positions, utilisation, recent txs), and chat (talk to your agent).

**Key pages:**

```
/                     → landing page + subscribe CTA
/app/dashboard        → positions overview, utilisation rate chart, recent txs
/app/chat             → chat with agent, set goals
/app/skills           → skill marketplace, unlock/manage
/app/billing          → subscription management
```

**Stack:** Next.js 14 (App Router), Wagmi v2 + Viem for wallet connectivity, Tailwind CSS, shadcn/ui components, Recharts for position charts.

**EIP-7702 delegation flow on frontend:**

```typescript
import { signAuthorization } from 'viem/experimental'
import { useWalletClient } from 'wagmi'

async function delegateToAgentWallet() {
  const walletClient = useWalletClient()
  
  // 1. Sign EIP-7702 authorization
  const authorization = await walletClient.signAuthorization({
    contractAddress: AGENT_WALLET_IMPL_ADDRESS, // your deployed impl
    chainId: 42161, // Arbitrum
  })
  
  // 2. Send to backend — backend submits the 0x04 transaction
  await fetch('/api/user/delegate', {
    method: 'POST',
    body: JSON.stringify({ authorization, userAddress: walletClient.account.address })
  })
}
```

**Utilisation rate display:** Show a live gauge (updated every 30s via polling or WebSocket):
- 0-40%: "Underutilised" (orange) — agent will deploy capital
- 40-85%: "Optimal" (green) — target zone
- 85-100%: "Fully deployed" (blue) — agent monitors for rebalance signals

**Where to learn:**
- Viem EIP-7702 `signAuthorization`: https://viem.sh/experimental/eip7702/signAuthorization
- Wagmi v2 setup: https://wagmi.sh/react/getting-started
- SIWE with Next.js: https://docs.login.xyz/sign-in-with-ethereum/quickstart-guide/nextjs
- shadcn/ui: https://ui.shadcn.com/

---

## Issue 10 — Observability, Monitoring and Alerting

**What this is:** At 1000 users, silent failures kill the business. You need visibility into every agent run, every failed transaction, every subscription lapse, and every LLM call cost.

**Stack:**
- **Sentry** — Python error tracking (agent crashes, tx failures)
- **Grafana + Prometheus** — Celery worker metrics, queue depth, task duration
- **LangSmith** — LLM call tracing, token usage, latency per user
- **Uptime Robot** — endpoint availability (free tier covers basics)
- **PagerDuty** / Telegram bot — on-call alerts for critical errors

**Key metrics to track:**

```python
# Custom Prometheus metrics
agent_runs_total = Counter('agentstack_agent_runs_total', ['user_tier', 'outcome'])
agent_run_duration = Histogram('agentstack_agent_run_duration_seconds', ['skill_count'])
tx_executed_total = Counter('agentstack_tx_executed_total', ['skill', 'status'])
llm_tokens_used = Counter('agentstack_llm_tokens_total', ['user_address'])
queue_depth = Gauge('agentstack_celery_queue_depth', ['queue_name'])
active_sessions = Gauge('agentstack_active_sessions_total')
```

**LangSmith integration (cost tracking):**
```python
from langsmith import traceable

@traceable(name="agent_heartbeat", tags=["production"])
async def run_agent_tick(user_address: str, ...):
    # All LLM calls inside are automatically traced
    pass
```

**Automated alerts:**
- Celery queue depth > 500 → scale up workers immediately
- Agent failure rate > 5% in 10 min → page on-call
- Any user loses > 3% capital in a single tx → pause their agent, notify them
- Session key expired for > 10% of users → email campaign to renew

**Where to learn:**
- LangSmith: https://docs.smith.langchain.com/
- Celery monitoring with Flower: https://docs.celeryq.dev/en/stable/userguide/monitoring.html
- Prometheus + FastAPI: https://github.com/trallnag/prometheus-fastapi-instrumentator
- Sentry Python SDK: https://docs.sentry.io/platforms/python/

---

## Issue 11 — Security Hardening

**What this is:** A product handling user funds with an autonomous agent requires systematic security — not just "don't commit private keys."

**Smart contract security:**
- [ ] All contracts audited before mainnet (Certik, OpenZeppelin, or Spearbit)
- [ ] Immutable core logic — upgrades via new contract + migration, not proxies (proxies + EIP-7702 = storage collision risk)
- [ ] Emergency pause on `SubscriptionManager` and `SkillRegistry` (Ownable + Pausable)
- [ ] Multi-sig (3-of-5 Gnosis Safe) as `treasury` address — not an EOA
- [ ] `AgentWallet.sol` has a `maxSpendPerDay` counter resets at UTC midnight
- [ ] Protocol address whitelist is immutable after deployment

**Backend security:**
- [ ] Agent private key in AWS KMS — never in env vars or code
- [ ] All RPC calls through Alchemy/Infura with rate-limited API keys per environment
- [ ] Input validation on all user goal parameters (max position %, yield target ranges)
- [ ] Rate limit LLM calls per user (max 300/day to prevent cost abuse)
- [ ] DB connection pooling with max 100 connections (prevent Postgres overwhelm at scale)
- [ ] Redis AUTH enabled, not exposed publicly

**Operational security:**
- [ ] Bug bounty program before public launch (Immunefi or private)
- [ ] Incident response runbook: how to pause all agents in < 5 minutes
- [ ] Separate hot wallet per environment (dev/staging/prod agent keys never share)
- [ ] All admin actions require 2FA + multi-sig confirmation

**Where to learn:**
- Smart contract security checklist: https://github.com/nascentxyz/simple-security-toolkit
- Immunefi bug bounties: https://immunefi.com/
- AWS KMS for Ethereum: https://aws.amazon.com/blogs/database/how-to-sign-ethereum-eip-1559-transactions-using-aws-kms/
- EIP-7702 attack surfaces: https://www.nethermind.io/blog/eip-7702-attack-surfaces-what-developers-should-know

---

## Issue 12 — Deployment Infrastructure (Production)

**What this is:** Moving from Docker Compose to production-grade infra that can handle 1000+ concurrent agent users without downtime.

**Infrastructure:**
```
AWS / GCP / Railway
├── Load Balancer (ALB)
│   └── FastAPI containers (2+ replicas, auto-scaling)
├── Celery Workers (4+ containers, scale by queue depth)
├── Celery Beat (single container — use Redis lock for HA)
├── Redis (ElastiCache or Upstash)
├── PostgreSQL (RDS or Supabase)
└── Arbitrum RPC (Alchemy or QuickNode — redundant endpoints)
```

**Deployment on Railway (cheapest start, scales to ~500 users):**

```yaml
# railway.toml
[build]
builder = "DOCKERFILE"

[[services]]
name = "api"
healthcheckPath = "/health"
replicas = 2

[[services]]
name = "worker"
startCommand = "celery -A backend.workers.heartbeat worker --concurrency=8 --pool=gevent -Q heartbeat"
replicas = 4

[[services]]
name = "beat"
startCommand = "celery -A backend.workers.heartbeat beat"
replicas = 1
```

**Kubernetes (for 500+ users):**
- HPA (Horizontal Pod Autoscaler) on Celery worker deployment, scaling on queue depth
- PodDisruptionBudget to prevent all workers restarting simultaneously
- Secrets via AWS Secrets Manager or GCP Secret Manager (not K8s Secrets)

**RPC redundancy:**
```python
# backend/executor/rpc.py
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

RPC_ENDPOINTS = [
    "https://arb-mainnet.g.alchemy.com/v2/{KEY}",
    "https://arbitrum-mainnet.infura.io/v3/{KEY}",
    "https://arb1.arbitrum.io/rpc",  # public fallback
]

def get_w3() -> Web3:
    for endpoint in RPC_ENDPOINTS:
        try:
            w3 = Web3(Web3.HTTPProvider(endpoint, request_kwargs={'timeout': 10}))
            if w3.is_connected():
                return w3
        except Exception:
            continue
    raise Exception("All RPC endpoints failed")
```

**Where to learn:**
- Railway deployment: https://docs.railway.com/
- Celery auto-scaling on K8s (KEDA): https://keda.sh/docs/2.16/scalers/redis-lists/
- Alchemy Arbitrum setup: https://docs.alchemy.com/reference/arbitrum-api-quickstart
- PostgreSQL connection pooling (PgBouncer): https://www.pgbouncer.org/

---

## Issue 13 — Multi-Chain Expansion (Post-MVP)

**What this is:** Once Arbitrum is running, the skill plugin architecture makes multi-chain expansion straightforward — you add chain-specific skill variants and a chain selector in the user config.

**Chain expansion order (recommended):**
1. **Base** — lowest fees, Coinbase backing, x402 ecosystem, strong EIP-7702 support
2. **Polygon** — established Aave markets, low fees
3. **Optimism** — Velodrome (strong DEX), Synthetix perps

**What changes per chain:**
- New contract deployments (AgentWallet, SubscriptionManager are EVM-compatible)
- New RPC endpoint per chain
- Chain-specific skill variants (e.g., `AaveV4SkillBase` vs `AaveV4SkillArbitrum`) — different contract addresses
- User config gains `preferred_chain` field

**Skill versioning for multi-chain:**
```python
class AaveV4SkillArbitrum(BaseSkill):
    SKILL_ID = 1
    CHAIN_ID = 42161
    POOL_ADDRESS = "0x794a61358D6845594F94dc1DB02A252b5b4814aD"

class AaveV4SkillBase(BaseSkill):
    SKILL_ID = 1
    CHAIN_ID = 8453
    POOL_ADDRESS = "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5"
```

**Where to learn:**
- Aave deployed contracts across chains: https://docs.aave.com/developers/deployed-contracts/v3-mainnet
- Base network developer docs: https://docs.base.org/
- Cross-chain wallet management: https://www.coinbase.com/developer-platform/products/smart-wallet

---

## Launch Sequence

| Phase | Milestone | Target |
|---|---|---|
| 0 | Monorepo + Docker setup | Week 1 |
| 1 | AgentWallet deployed to Arbitrum Sepolia | Week 2 |
| 2 | Aave V4 skill + 5-min loop working for 1 test user | Week 3 |
| 3 | Chat UI + goal setting working end to end | Week 4 |
| 4 | Billing contract + subscription flow | Week 5 |
| 5 | GMX + Uniswap V4 skills | Week 6 |
| 6 | Security hardening + private beta (10 users) | Week 7-8 |
| 7 | Audit + mainnet launch | Week 10-12 |

---

## Estimated Costs (at 100 users)

| Item | Monthly |
|---|---|
| Railway (API + 4 workers + beat) | ~$60 |
| Redis (Upstash) | ~$20 |
| PostgreSQL (Supabase) | ~$25 |
| Alchemy RPC (1M calls/day) | ~$50 |
| Claude Sonnet (300 calls/user/month) | ~$90 |
| Chainlink Automation (renewal upkeep) | ~$20 |
| **Total infra** | **~$265/month** |
| **Revenue at 100 users avg $25/mo** | **$2,500/month** |
| **Gross margin** | **~89%** |
