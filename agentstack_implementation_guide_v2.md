# AgentStack — DeFAI Agent Hosting Platform
## Progressive Implementation Guide (Directions + Resources + Tests)

> **What you are building:** A hosted DeFAI platform on Arbitrum where users pay SterlingStack a monthly USDC subscription to keep an autonomous AI trading agent alive, and unlock protocol integrations (skills) à la carte. All user funds stay in their own wallet via EIP-7702 delegation. The agent (Python / LangGraph / Claude Sonnet) runs on your infrastructure, polls every 5 minutes, and acts via scoped session keys.

---

> **How to use this document:**
> Each issue is one self-contained unit of work. Complete them in order — each one depends on the previous. Every issue ends with a **Testing Gate**: a defined test that must pass before you move to the next issue. Nothing ships without a green test.

---

## Issue 1 — Monorepo Setup and Project Vault

**What you are setting up:**
A clean monorepo structure with clear separation between contracts, backend, and frontend. Secrets management from day one — no private keys ever in git. Environment config that works locally, on Arbitrum Sepolia, and on Arbitrum mainnet without code changes.

**Tooling decisions to make before writing a line of code:**
- Use **Foundry** for Solidity — not Hardhat. Foundry has native fork testing, faster compilation, and built-in EIP-7702 cheatcodes you will need in Issue 2.
- Use **uv** for Python dependencies — not pip or poetry. Lockfile-based, dramatically faster, and reproducible across machines.
- Use **Doppler** or **dotenv-vault** for secrets — not `.env` files. Secrets are fetched at runtime from the vault, never committed.
- Use **Docker Compose** to bring up backend + worker + postgres + redis locally with one command.
- Set up **GitHub Actions** CI from the start — not retrofitted later.

**Folder structure to establish:**
```
agentstack/
├── contracts/     → Foundry project (src/, test/, foundry.toml)
├── backend/       → FastAPI + Celery
│   └── skills/    → pluggable skill modules (Issue 4)
├── frontend/      → Next.js 14
└── infra/         → docker-compose.dev.yml, docker-compose.prod.yml
```

**Resources:**
- Foundry installation and project init: https://book.getfoundry.sh/getting-started/installation
- uv Python package manager: https://docs.astral.sh/uv/
- Doppler secrets management: https://docs.doppler.com/docs/start
- Docker Compose with Python + Postgres + Redis: https://docs.docker.com/compose/gettingstarted/
- GitHub Actions for Python CI: https://docs.github.com/en/actions/use-cases-and-examples/building-and-testing/building-and-testing-python
- Monorepo structure thinking: https://monorepo.tools/

**Testing Gate — Issue 1**

Tool: `bash`, `docker compose`, `forge`

What the test checks:
- `docker compose up` starts all four services (api, worker, postgres, redis) with no errors
- `forge build` inside `contracts/` compiles with zero errors
- `forge test` runs (even with zero test files) without panicking
- `uv sync` installs all Python dependencies from the lockfile cleanly on a fresh machine
- `GET /health` on the FastAPI container returns `{"status": "ok"}`
- `git log --all -- .env` returns nothing — no secrets file in history

A **passing gate** looks like: all six checks succeed after a clean `git clone` on a machine that has only Docker and Foundry installed — nothing else pre-configured.

---

## Issue 2 — EIP-7702 Smart Account (AgentWallet Contract)

**What you are building:**
A single shared Solidity implementation contract (`AgentWallet.sol`) that every user's EOA delegates to. It gives your backend agent a scoped, time-limited session key with permission to call specific DeFi protocol addresses up to a daily spend limit — and no ability to withdraw funds externally.

**Concepts to understand before writing code:**

EIP-7702 went live on Arbitrum with ArbOS 40 "Callisto" in June 2025. It introduces transaction type `0x04`. The user signs an `authorization_list` entry pointing their EOA at your implementation address. The EOA then runs your contract's code until the delegation is cleared. Storage lives on the EOA, not on your implementation — this means your implementation's storage layout must never change after users have delegated to it. Use ERC-7201 namespaced storage slots from day one to prevent this.

**What the contract must enforce:**
- Only the agent address (set by the user) can call `execute()`
- `execute()` only routes to a hardcoded whitelist of protocol addresses — no arbitrary targets
- Session keys expire after a user-defined duration
- A daily spend counter resets at UTC midnight
- The user can always revoke or redelegate

**Resources:**
- EIP-7702 specification: https://eips.ethereum.org/EIPS/eip-7702
- Arbitrum EIP-7702 live guide: https://blog.arbitrum.foundation/the-smartest-wallet-you-already-own-is-on-arbitrum/
- OpenZeppelin EOA Delegation docs: https://docs.openzeppelin.com/contracts/5.x/eoa-delegation
- Foundry EIP-7702 cheatcodes (`signDelegation`, `attachDelegation`, `signAndAttachDelegation`): https://www.quicknode.com/guides/ethereum-development/smart-contracts/eip-7702-smart-accounts
- EIP-7702 security attack surfaces — read before writing Solidity: https://www.nethermind.io/blog/eip-7702-attack-surfaces-what-developers-should-know
- ERC-7201 namespaced storage to prevent storage collision: https://eips.ethereum.org/EIPS/eip-7201
- HackMD deep dive on delegation designator internals: https://hackmd.io/@colinlyguo/SyAZWMmr1x
- Viem `signAuthorization` (frontend sends this to backend): https://viem.sh/experimental/eip7702/signAuthorization

**Testing Gate — Issue 2**

Tool: Foundry (`forge test`) on a local Anvil fork of Arbitrum Sepolia, using `vm.signDelegation` and `vm.attachDelegation` cheatcodes

What the tests check (written in Solidity):
1. A test EOA can delegate to `AgentWallet.sol` — delegation designator is set correctly on the EOA
2. The agent key can call `execute()` to a whitelisted protocol address — call succeeds
3. The agent key calling `execute()` to a non-whitelisted address — reverts with the correct error
4. A spend amount over the daily limit — reverts
5. After `vm.warp` past `validUntil`, all `execute()` calls revert
6. Calling `revokeSession()` from the EOA owner prevents further agent execution
7. A random third address (not agent, not owner) calling `execute()` — reverts

A **passing gate** looks like: `forge test --fork-url $ARBITRUM_SEPOLIA_RPC -vv` — all seven tests green. Gas usage for a basic `execute()` call is logged and under 200,000 gas.

---

## Issue 3 — On-Chain Billing (SubscriptionManager + SkillRegistry)

**What you are building:**
Two Solidity contracts handling all revenue. `SubscriptionManager.sol` handles monthly tier subscriptions in USDC. `SkillRegistry.sol` tracks which protocol skills each user has unlocked. Chainlink Automation triggers renewals — no centralised cron job controls payments.

**Design decisions to understand first:**
- Users pre-approve a USDC allowance once — the contract pulls monthly. If allowance is exhausted, the subscription lapses gracefully (no revert — just deactivation and an event). This is the pull-payment pattern.
- The `treasury` address that receives USDC must be a Gnosis Safe multisig — never a single EOA.
- Skill unlock state lives on-chain. Your backend reads it at each heartbeat from the contract. Do not trust a database as the source of truth for what a user has paid for.
- Chainlink Automation `checkUpkeep` / `performUpkeep` handles renewals. You define which users are due and the upkeep calls your contract.

**Skill ID table — define in the contract, never change IDs:**

| ID | Skill | Available to |
|---|---|---|
| 1 | Aave V4 lend/borrow | Starter+ |
| 2 | Uniswap V4 LP | Pro+ |
| 3 | GMX V2 perpetuals | Pro+ |
| 4 | Pendle yield trading | Elite |
| 5 | Multi-strategy rebalancing | Elite |

**Resources:**
- Chainlink Automation upkeep pattern: https://docs.chain.link/chainlink-automation
- OpenZeppelin USDC pull payment pattern: https://docs.openzeppelin.com/contracts/5.x/api/utils#PullPayment
- ERC-1155 for skill access tokens (optional but portable): https://docs.openzeppelin.com/contracts/5.x/erc1155
- On-chain subscription billing and proration overview: https://subscribeonchain.com/2025/10/15/how-onchain-recurring-payments-with-proration-enhance-web3-subscription-models/
- ERC-4337 recurring payment pattern (session keys for subscriptions): https://technorely.com/insights/recurring-payments-in-web-3-via-account-abstraction-erc-4337
- Gnosis Safe setup: https://help.safe.global/en/articles/40795-what-is-a-multisig-wallet

**Testing Gate — Issue 3**

Tool: Foundry fork test on Arbitrum Sepolia (USDC contract lives there). Include fuzz tests.

What the tests check:
1. User with USDC balance and approved allowance subscribes at tier 2 — stored correctly, USDC transferred to treasury
2. User without allowance tries to subscribe — reverts cleanly
3. `isActive(user)` returns `true` after subscribing and `false` after `vm.warp(31 days)`
4. `renewSubscription(user)` via the Chainlink Automation forwarder address extends `paidUntil` and pulls USDC
5. `renewSubscription` on a user with exhausted allowance sets `active = false` and emits `SubscriptionLapsed`
6. `unlockSkill(skillId=3)` from a Pro subscriber stores the unlock and transfers USDC
7. `hasSkill(user, 3)` returns `true` immediately and `false` after `vm.warp(31 days)`
8. `unlockSkill` with an unknown `skillId` reverts

A **passing gate** looks like: `forge test --match-contract BillingTest --fork-url $ARBITRUM_SEPOLIA_RPC -vv` — all eight tests green. Fuzz test `subscribe(tier)` with random tier values confirms only 1, 2, 3 succeed.

---

## Issue 4 — Pluggable Skill Architecture (Backend)

**What you are building:**
A Python plugin system where each DeFi protocol integration is a self-contained module the agent can load or swap at runtime without restarting. The skill registry reads on-chain unlock state each heartbeat and builds the correct tool set for that specific user.

**The pattern to follow:**
Each skill is a Python class inheriting from a shared `BaseSkill` abstract class. The class exposes a `get_tools()` method returning LangGraph-compatible `@tool`-decorated functions. A `SkillRegistry` in Python dynamically instantiates only the skills a user has unlocked on-chain.

**What each skill must implement:**
- `SKILL_ID` — integer matching the on-chain registry ID
- `get_tools()` — returns a list of LangGraph tools
- `get_position_summary(user_address)` — returns current on-chain positions for the heartbeat dashboard
- `health_check()` — verifies the protocol's contracts are reachable

**Adding a new skill after launch (zero-downtime procedure):**
Write the Python module → add to registry dict → rolling-restart Celery workers → admin-call `addSkill()` on the on-chain `SkillRegistry`. No contract redeployment, no user disruption.

**Resources:**
- LangGraph `@tool` decorator and tool interface: https://python.langchain.com/docs/concepts/tools/
- LangGraph tool-calling how-to: https://langchain-ai.github.io/langgraph/how-tos/tool-calling/
- Python abstract base classes for plugin interfaces: https://docs.python.org/3/library/abc.html
- Skill naming and description best practices (critical for correct LLM tool selection): https://blog.langchain.com/evaluating-skills/
- Aave V4 contract interfaces on Arbitrum: https://docs.aave.com/developers/deployed-contracts/v3-mainnet/arbitrum
- GMX V2 Synthetics contracts and SDK: https://github.com/gmx-io/gmx-synthetics
- Uniswap V4 hook architecture: https://docs.uniswap.org/contracts/v4/overview
- web3-ethereum-defi library (DeFi-specific web3.py helpers): https://pypi.org/project/web3-ethereum-defi/
- Pendle Finance SDK: https://docs.pendle.finance/Developers/SDKs/PendleSDK

**Testing Gate — Issue 4**

Tool: `pytest` with mocked web3 calls — no live RPC needed for unit tests

What the tests check:
1. `BaseSkill` is correctly abstract — instantiating it directly raises `TypeError`
2. `AaveV4Skill` implements all required methods and `get_tools()` returns a non-empty list
3. Each tool returned by `get_tools()` has a name, a description, and is callable (LangGraph tool contract)
4. `load_skills_for_user(user_address, skill_ids=[1, 3])` returns exactly two skill instances of the correct types
5. `load_skills_for_user(user_address, skill_ids=[99])` returns an empty list — unknown ID handled gracefully
6. `get_tools_for_user(skills)` flattens tools from multiple skills into one list with no duplicate tool names
7. `AaveV4Skill.health_check()` returns `False` when web3 is mocked to raise a connection error — skill is resilient
8. `get_position_summary()` returns a dict with keys `protocol`, `supplied`, `borrowed` — schema enforced

A **passing gate** looks like: `pytest tests/test_skills/ -v` — all eight tests green, no live web3 calls made (assert mock was called, not real provider).

---

## Issue 5 — LangGraph Agent Core

**What you are building:**
The decision-making brain for each user's agent. A LangGraph `StateGraph` with four nodes: `fetch_positions` → `analyze` → `execute` → `report`. Claude Sonnet is only invoked in `analyze` — all other nodes are deterministic Python. The `PostgresSaver` checkpointer means agent state survives worker restarts.

**Why LangGraph over plain LangChain AgentExecutor:**
LangGraph is now the recommended production framework. It offers stateful execution graphs, `InMemorySaver` / `PostgresSaver` checkpointing, `interrupt_before` for human-in-the-loop testing, and conditional edge routing. `AgentExecutor` is legacy and harder to test in isolation.

**The system prompt is a first-class engineering artifact:**
The Claude system prompt controls all agent behaviour. It must include: user goals, current positions, available tool names, risk rules (health factor floor, max position size, max tx size in USDC), and a clear instruction to do nothing when uncertain. Version-control it and treat it like production configuration.

**Circuit breaker conditions — hardcoded in Python, not decided by the LLM:**
- Aave health factor below 1.3 → skip execution entirely, log reason
- Gas price above configurable threshold → skip
- Daily loss percentage exceeded → pause agent, alert user
- More than 2 pending unconfirmed transactions → skip

**Resources:**
- LangGraph official documentation: https://langchain-ai.github.io/langgraph/
- LangGraph `StateGraph` with conditional edges tutorial: https://langchain-ai.github.io/langgraph/tutorials/introduction/
- LangGraph PostgreSQL checkpointing: https://langchain-ai.github.io/langgraph/how-tos/persistence-postgres/
- LangGraph streaming (for chat in Issue 8): https://langchain-ai.github.io/langgraph/how-tos/streaming/
- LangGraph testing guide — `MemorySaver`, node isolation, `interrupt_before`: https://docs.langchain.com/oss/python/langgraph/test
- LangSmith tracing for agent observability: https://docs.smith.langchain.com/observability/how_to_guides/trace_with_langgraph
- Production agent evaluation patterns from LangChain: https://www.zenml.io/llmops-database/evaluation-patterns-for-deep-agents-in-production

**Testing Gate — Issue 5**

Tool: `pytest` with `InMemorySaver` checkpointer and mocked LLM (no real Claude API calls)

What the tests check:
1. Graph compiles without error with an empty tool list and `InMemorySaver`
2. `fetch_positions` node updates `AgentState.positions` with a non-empty dict when web3 calls are mocked
3. When mocked positions show utilisation below the target, `analyze` node sets `pending_actions` to a non-empty list
4. When mocked positions are already optimal, `should_execute` routes to `"skip"` — `execute` node never reached (verified via `interrupt_before`)
5. Circuit breaker: when `health_factor` is mocked at 1.2, the `analyze` node routes to `"skip"` regardless of utilisation
6. After a full graph run, `thread_id` state persists in the checkpointer and is retrievable on a second call
7. A full agent tick (all four nodes) completes in under 30 seconds wall clock with a mocked LLM
8. Two ticks with the same `thread_id` produce accumulated state — the second run reads positions written by the first

A **passing gate** looks like: `pytest tests/test_agent/ -v --timeout=60` — all eight tests green. Mock LLM confirmed called (not real Anthropic API). LangSmith trace shows correct node execution order for tests that use `@traceable`.

---

## Issue 6 — 5-Minute Heartbeat Loop (Celery + Redis, 1000+ Users)

**What you are building:**
The scheduling backbone. Celery Beat dispatches a `dispatch_all_agents` task every 300 seconds. That task fetches all active subscribers and fires individual `run_agent_heartbeat` tasks into the queue. Workers consume from the queue with gevent concurrency.

**Scaling math — understand before building:**
At 1,000 users on a 300-second cycle: approximately 3.3 new tasks per second continuously. Each agent run takes 10–30 seconds (RPC calls + one LLM call). You need ~40–100 concurrent task slots across all workers. Four Celery worker containers with 8 gevent concurrency each (32 total slots) covers this, with headroom.

**Implementation details that matter:**
- Redis distributed lock per user prevents the same user's agent running twice if a previous tick is still in progress
- Subscription active status is cached in Redis (TTL 310 seconds) — do not read the blockchain on every heartbeat
- Skill unlock status is cached in Redis (TTL 3,600 seconds) — refreshed hourly
- Celery Beat runs in exactly one container — never replicate it or you get duplicate dispatches
- Use `gevent` worker pool, not `prefork` — the work is I/O-bound (RPC + HTTP), not CPU-bound

**Resources:**
- Celery official testing documentation: https://docs.celeryq.dev/en/stable/userguide/testing.html
- Celery Beat periodic tasks: https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html
- Celery gevent pool: https://docs.celeryq.dev/en/stable/userguide/concurrency/gevent.html
- pytest-celery plugin (Docker-based integration testing): https://pytest-celery.readthedocs.io/en/latest/
- Mocking Celery tasks with `unittest.mock.patch`: https://pytest-with-eric.com/mocking/mock-celery-task-pytest/
- Redis distributed locks (Redlock): https://redis.io/docs/latest/develop/use/patterns/distributed-locks/
- FastAPI + Celery integration tutorial: https://testdriven.io/blog/fastapi-and-celery/
- KEDA autoscaling Celery workers on Kubernetes with Redis: https://keda.sh/docs/2.16/scalers/redis-lists/

**Testing Gate — Issue 6**

Tool: `pytest` with Celery configured for in-memory broker (`broker_url = 'memory://'`) + mocked agent execution

What the tests check:
1. `run_agent_heartbeat` with `task_always_eager = True` runs synchronously and completes without exception when agent execution is mocked
2. A user with `billing_cache.is_active` returning `False` causes the task to return early — mock confirms the agent graph was never invoked
3. Task retries correctly on a simulated RPC exception — `max_retries=3` exhausted raises `MaxRetriesExceededError`
4. The Redis distributed lock prevents a second `run_agent_heartbeat` for the same user from executing while the first lock is held
5. `dispatch_all_agents` fetches the active user list and calls `.delay()` exactly once per active user — mock confirms dispatch count equals active subscriber count
6. With `celery_worker` pytest fixture and 50 users dispatched, all tasks complete within 60 seconds — no deadlock
7. A task that fails three times emits an error log and does not re-queue indefinitely

A **passing gate** looks like: `pytest tests/test_workers/ -v` — all seven tests green with the in-memory broker. Integration tests marked `@pytest.mark.integration` run only in CI with a real Redis container.

---

## Issue 7 — Web3 Executor and Transaction Signing

**What you are building:**
The Python module that translates an agent decision into a signed Arbitrum transaction. The executor calls `AgentWallet.execute(target, value, calldata)` on the user's EOA using the agent session key. The Solidity contract validates all constraints — your executor does a fast pre-flight check before spending gas.

**Key design rule:**
The executor is the last Python-level gate before real money moves. Pre-flight checks (session key active? target on whitelist? daily spend under limit?) run before any signing. These checks also exist in Solidity — but run them in Python first to avoid wasting gas on doomed transactions.

**Agent private key storage:**
- Development: local keystore file
- Staging + production: AWS KMS — the private key never leaves KMS, you sign transaction hashes remotely
- The key ID must never appear in logs, environment variable dumps, or error messages

**RPC redundancy:**
Configure at minimum two providers (Alchemy primary, Infura secondary). The executor tries them in sequence. If all fail, log and skip — the next heartbeat will retry in 5 minutes.

**Resources:**
- web3.py transaction signing: https://web3py.readthedocs.io/en/stable/web3.eth.account.html
- web3.py testing with `EthereumTesterProvider` (in-process, no live RPC): https://web3py.readthedocs.io/en/stable/ethpm.html
- web3-ethereum-defi for DeFi-specific testing helpers: https://pypi.org/project/web3-ethereum-defi/
- web3.py integration test patterns (official repo reference): https://github.com/ethereum/web3.py/blob/main/tests/integration/test_ethereum_tester.py
- AWS KMS Ethereum signing: https://aws.amazon.com/blogs/database/how-to-sign-ethereum-eip-1559-transactions-using-aws-kms/
- Alchemy Arbitrum RPC setup: https://docs.alchemy.com/reference/arbitrum-api-quickstart
- Aave V4 Arbitrum contract addresses (for calldata construction): https://docs.aave.com/developers/deployed-contracts/v3-mainnet/arbitrum
- GMX V2 contract deployments: https://github.com/gmx-io/gmx-synthetics#deployments

**Testing Gate — Issue 7**

Tool: `pytest` with `EthereumTesterProvider` (fully in-process) + one Foundry fork integration test

What the tests check:
1. `executor.execute(user_address, target, calldata)` with a valid mocked session key returns a transaction hash string
2. Pre-flight: mocked session key has wrong agent address → raises `SessionKeyError` before any signing
3. Pre-flight: mocked `validUntil` in the past → raises `SessionExpiredError`
4. First RPC provider raises connection error → executor falls through to the second provider and succeeds
5. Mocked receipt with `status == 0` (revert) → raises `TransactionRevertedError` containing the tx hash
6. A successful execution writes a record to the database with `user_address`, `tx_hash`, `target`, `timestamp`
7. Foundry fork integration test: executor calling Aave V4 supply on Arbitrum Sepolia fork — correct token balance change confirmed

A **passing gate** looks like: `pytest tests/test_executor/ -v` — all six unit tests green in under 5 seconds. `forge test --match-test testExecutorAaveSupply --fork-url $ARBITRUM_SEPOLIA_RPC` passes as the integration gate before staging deploy.

---

## Issue 8 — FastAPI Backend and WebSocket Chat

**What you are building:**
The REST API and WebSocket layer between the frontend and the agent/blockchain. Authentication uses Sign-In with Ethereum (SIWE / EIP-4361) — no passwords, no emails. Users chat with their agent over WebSocket and responses stream back token by token.

**API surface to build:**
- `GET /auth/nonce` — returns a one-time nonce for SIWE
- `POST /auth/verify` — validates SIWE message + signature, returns JWT
- `GET /user/dashboard` — current positions, utilisation rate, last 20 transactions
- `GET /user/subscription` — tier, `paidUntil`, unlocked skill IDs
- `POST /user/goals` — update agent config
- `WS /agent/chat` — bidirectional WebSocket, streams LangGraph responses
- `GET /agent/history` — past decisions with reasoning
- `POST /billing/subscribe` — returns unsigned tx calldata for frontend
- `POST /billing/unlock-skill` — same pattern for skill unlocks

**Auth flow (SIWE):**
Frontend requests nonce → constructs SIWE message → user signs with wallet → POST message + signature → backend verifies signature against stated address using the `siwe` Python library → return short-lived JWT.

**Resources:**
- FastAPI documentation: https://fastapi.tiangolo.com/
- FastAPI WebSockets: https://fastapi.tiangolo.com/advanced/websockets/
- FastAPI testing with `TestClient`: https://fastapi.tiangolo.com/tutorial/testing/
- SIWE Python library: https://pypi.org/project/siwe/
- Sign-In with Ethereum specification (EIP-4361): https://docs.login.xyz/
- Starlette WebSocket testing: https://www.starlette.io/testclient/#websocket-testing
- LangGraph streaming with `astream`: https://langchain-ai.github.io/langgraph/how-tos/streaming/

**Testing Gate — Issue 8**

Tool: FastAPI `TestClient` + `pytest-asyncio` for WebSocket tests

What the tests check:
1. `GET /health` returns `200 {"status": "ok"}` with no auth required
2. `GET /user/dashboard` with no JWT returns `401`
3. `GET /user/dashboard` with a valid JWT returns `200` with `positions`, `utilisation_rate`, `recent_transactions` keys present
4. `POST /auth/verify` with a valid SIWE signature returns a JWT; decoding it reveals the correct Ethereum address
5. `POST /auth/verify` with a tampered signature returns `401`
6. `POST /user/goals` with valid JWT stores goals; subsequent `GET /user/dashboard` reflects the new values
7. WebSocket `/agent/chat`: connect with valid JWT, send a message, receive at least one streamed chunk within 10 seconds (LLM mocked)
8. WebSocket `/agent/chat`: connect without a JWT — connection rejected with code `4001`

A **passing gate** looks like: `pytest tests/test_api/ -v` — all eight tests green. No real blockchain calls or LLM calls made. WebSocket test uses `starlette.testclient` pattern.

---

## Issue 9 — Frontend (Next.js 14 Dashboard + Chat)

**What you are building:**
Three surfaces: onboarding (connect wallet → subscribe → set goals), dashboard (live positions, utilisation gauge, tx history), and chat (talk to agent, update parameters). The frontend never holds private keys and only calls the blockchain for signing — all reads go through the backend API.

**Technology stack:**
- Next.js 14 App Router
- Wagmi v2 + Viem for wallet connectivity and signing
- `siwe` npm package for constructing SIWE messages
- Tailwind CSS + shadcn/ui components
- Recharts for utilisation and position visualisation
- `@tanstack/react-query` for API data fetching

**EIP-7702 delegation flow on the frontend:**
User clicks "Enable Agent" → frontend calls Viem's `signAuthorization({ contractAddress: AGENT_WALLET_IMPL })` → signed authorization is POSTed to backend → backend submits the type-0x04 transaction → frontend polls for confirmation. The user never manually constructs a type-0x04 transaction.

**Utilisation rate display logic:**
- 0–40%: "Underutilised" — agent may deploy capital
- 40–85%: "Optimal" — target zone, no action expected
- 85–100%: "Fully deployed" — agent monitors for rebalance signals

**Resources:**
- Viem experimental EIP-7702 `signAuthorization`: https://viem.sh/experimental/eip7702/signAuthorization
- Wagmi v2 setup and hooks: https://wagmi.sh/react/getting-started
- SIWE with Next.js using Iron Session: https://docs.login.xyz/sign-in-with-ethereum/quickstart-guide/nextjs
- Testing Wagmi + Viem frontend against Anvil local chain: https://www.callstack.com/blog/testing-expo-web3-apps-with-wagmi-and-anvil
- web3-mock for unit testing without live blockchain: https://github.com/DePayFi/web3-mock
- shadcn/ui component library: https://ui.shadcn.com/

**Testing Gate — Issue 9**

Tool: Vitest + React Testing Library + `web3-mock` for unit/component tests; Playwright for E2E

What the tests check:
1. Dashboard page renders without crashing when API returns mock position data
2. Utilisation gauge shows "Optimal" label when `utilisation_rate` prop is 65%
3. "Enable Agent" button click calls `signAuthorization` with the correct `contractAddress` (web3-mock confirms)
4. SIWE flow: after mock wallet connection, a SIWE message is constructed with the correct domain and nonce from the API
5. Chat input is disabled until WebSocket connection state is confirmed open
6. A streamed WebSocket response renders incrementally — not blank until complete
7. Playwright E2E: connect wallet on local Anvil → sign SIWE → reach dashboard → send chat message → receive response. Full flow completes under 20 seconds.

A **passing gate** looks like: `vitest run` — all six unit/component tests green. `playwright test` — E2E test green against local Anvil + Docker Compose backend.

---

## Issue 10 — Observability, Monitoring and Alerting

**What you are building:**
Visibility into every agent run, every failed transaction, every subscription lapse, and every LLM cost. Set this up before onboarding paying users.

**Four layers to instrument:**
- **LangSmith** — trace every LangGraph run, see token counts and latency per user, per node. Use `@traceable` decorator. Primary debugging tool for agent behaviour.
- **Sentry** — Python exception tracking. Every agent crash, failed transaction, and RPC timeout captured with full stack trace. Celery integration is one line.
- **Prometheus + Grafana** — Celery queue depth, task duration histograms, transaction success rates, active agent count.
- **Telegram bot or PagerDuty** — critical alerts: queue depth above 500, error rate above 5%, any user losing more than 3% of capital in a single transaction.

**Key custom metrics to define from day one:**
- Heartbeat run count by outcome (success / skipped / failed)
- LLM tokens used per user per day (enforce a daily cap)
- Transaction execution count by skill and by status
- Celery queue depth (alert above 500)
- Active session key count (should match active subscriber count)

**Resources:**
- LangSmith tracing with LangGraph and `@traceable`: https://docs.smith.langchain.com/observability/how_to_guides/trace_with_langgraph
- LangSmith + pytest for tracked evaluation: https://andrew-larse514.medium.com/evaluating-langgraph-agents-with-langsmiths-pytest-integration-e24695b93ddf
- Sentry Python SDK with built-in Celery integration: https://docs.sentry.io/platforms/python/integrations/celery/
- prometheus-fastapi-instrumentator: https://github.com/trallnag/prometheus-fastapi-instrumentator
- Celery Flower dashboard: https://docs.celeryq.dev/en/stable/userguide/monitoring.html
- Grafana Celery dashboard templates: https://grafana.com/grafana/dashboards/

**Testing Gate — Issue 10**

Tool: `pytest` with Sentry in test mode + Prometheus test client

What the tests check:
1. A deliberate exception in a Celery task is captured by Sentry — Sentry test mode confirms the event was queued
2. After 10 simulated agent heartbeat runs, the Prometheus counter `agentstack_agent_runs_total` equals 10
3. `agentstack_llm_tokens_total` increments by the correct amount after a mocked LLM call returns a known token count
4. A simulated queue depth of 600 triggers the alerting function — mock confirms the alert webhook was called
5. LangSmith trace is created for a full agent run in test mode — trace contains all four correct node names
6. `GET /metrics` returns `200` and the body contains all custom metric names defined in Issue 10

A **passing gate** looks like: `pytest tests/test_observability/ -v` — all six tests green. No real Sentry, Grafana, or LangSmith network calls in unit tests (mocked). Integration test for LangSmith trace uses a test project key in CI.

---

## Issue 11 — Security Hardening

**What you are building:**
A systematic security pass before any real capital is at risk. This is a checklist-driven issue, not a feature. Nothing ships to mainnet until every item is confirmed.

**Smart contract checklist:**
- All three contracts audited by at least one reputable firm before mainnet
- Emergency pause on `SubscriptionManager` and `SkillRegistry` — callable only by the Safe multisig
- Protocol whitelist in `AgentWallet` is immutable — no admin function to add protocols post-deployment
- No proxy pattern on `AgentWallet` — upgrades via new deployment + user re-delegation, not proxies (proxies + EIP-7702 storage = collision risk)
- `treasury` is a verified Gnosis Safe address — confirmed in deployment script output
- Bug bounty programme live on Immunefi before public launch

**Backend checklist:**
- Agent private key in AWS KMS — confirmed by a test that the key ID does not appear anywhere in logs or env variable dumps
- All provider API keys are per-environment (dev / staging / prod keys are different values)
- Daily LLM token cap per user enforced in heartbeat task
- Rate limiting on all public API endpoints
- All user goal inputs validated with Pydantic strict ranges
- Redis `AUTH` enabled, Redis not publicly accessible

**Resources:**
- Nascent simple security toolkit (smart contract checklist): https://github.com/nascentxyz/simple-security-toolkit
- Immunefi bug bounty setup: https://immunefi.com/
- OpenZeppelin Pausable: https://docs.openzeppelin.com/contracts/5.x/api/security#Pausable
- AWS KMS for Ethereum: https://aws.amazon.com/blogs/database/how-to-sign-ethereum-eip-1559-transactions-using-aws-kms/
- EIP-7702 attack surfaces reference: https://www.nethermind.io/blog/eip-7702-attack-surfaces-what-developers-should-know
- fastapi-limiter for rate limiting: https://github.com/long2ice/fastapi-limiter
- Pydantic strict validation: https://docs.pydantic.dev/latest/concepts/strict_mode/
- Foundry invariant testing: https://book.getfoundry.sh/forge/invariant-testing

**Testing Gate — Issue 11**

Tool: Foundry invariant tests + `pytest` for backend security + manual checklist

What the tests check:
1. Foundry invariant: across 1,000 fuzz runs, `AgentWallet.execute()` never reaches a non-whitelisted address
2. Foundry invariant: `SubscriptionManager` treasury balance never decreases across any sequence of calls
3. `POST /user/goals` with `max_position_pct: 150` returns `422 Unprocessable Entity`
4. `POST /user/goals` with `yield_target: -0.1` returns `422`
5. A 301st simulated LLM call for one user in a day is blocked by the rate cap — mock confirms LLM was not called
6. `GET /metrics` output contains no wallet addresses, private key fragments, or API keys
7. Manual checklist: all 12 smart contract and backend items confirmed with date and reviewer name recorded in `SECURITY.md`

A **passing gate** looks like: `forge test --match-contract InvariantTest` — 1,000 runs with no counterexample found. `pytest tests/test_security/ -v` — all five automated tests green. `SECURITY.md` has a completed, signed checklist.

---

## Issue 12 — Deployment Infrastructure (Production)

**What you are building:**
A production deployment that handles 1,000+ active agents with rolling updates and no downtime. Start on Railway for simplicity and cost, with a defined migration path to Kubernetes when usage demands it.

**Service topology:**
```
Load Balancer
└── FastAPI (2+ replicas, auto-restart on crash)

Celery Workers (4+ containers, scale by queue depth)
Celery Beat   (exactly 1 container — never replicate)
Redis         (managed: Upstash or ElastiCache)
PostgreSQL    (managed: Supabase or RDS)
Arbitrum RPC  (Alchemy primary, Infura secondary, public fallback)
```

**Railway stage (up to ~500 users):**
Deploy API, worker, and beat as separate Railway services from the same Docker image with different start commands. Use Railway's private networking for Redis and Postgres.

**Kubernetes migration triggers:**
Move to K8s when queue depth regularly exceeds 500, or when you need more than 8 worker containers, or when worker CPU is consistently above 70%.

**RPC redundancy rule:**
Always maintain three Arbitrum RPC endpoints. Executor rotates through them on connection failure. Never depend on a single provider for uptime.

**Resources:**
- Railway deployment docs: https://docs.railway.com/
- Railway Dockerfile service config: https://docs.railway.com/guides/dockerfiles
- KEDA autoscaling Celery workers on Kubernetes: https://keda.sh/docs/2.16/scalers/redis-lists/
- Alchemy Arbitrum RPC quickstart: https://docs.alchemy.com/reference/arbitrum-api-quickstart
- PgBouncer for PostgreSQL connection pooling: https://www.pgbouncer.org/
- Upstash Redis (serverless, scales to zero in dev): https://upstash.com/
- Locust for load testing: https://docs.locust.io/en/stable/

**Testing Gate — Issue 12**

Tool: GitHub Actions CI/CD pipeline + Locust load test

What the tests check:
1. GitHub Actions workflow on `main` branch: build Docker image → run `pytest` → run `forge test` → deploy to staging on Railway — all steps pass
2. After deploy, `GET /health` on the staging URL returns `200` within 30 seconds
3. Locust load test at 100 simulated users for 60 seconds — P95 latency under 500ms, zero 5xx responses
4. Celery worker container crash and restart — Beat re-dispatches tasks within one 300-second cycle, no tasks permanently lost
5. `alembic upgrade head` on the staging database runs cleanly without locking existing tables
6. Rolling restart of all Celery workers one at a time — no agent heartbeat is missed during the restart window

A **passing gate** looks like: GitHub Actions workflow shows green on `main`. Locust report confirms P95 under 500ms. Staging environment is fully functional end-to-end after automated deploy.

---

## Issue 13 — Multi-Chain Expansion

**What you are building:**
Support for Base (first), then Polygon, then Optimism. The pluggable skill architecture from Issue 4 makes this clean — add chain-specific skill variants and a chain selector in user config. Contracts are standard EVM and redeploy to any chain without modification.

**What changes per chain:**
- New contract deployments for all three contracts
- New RPC endpoint per chain in the executor
- Chain-specific skill variants with the correct protocol addresses (e.g. `AaveV4SkillBase` vs `AaveV4SkillArbitrum`)
- User config gains a `chain_id` field

**What does not change:**
The skill plugin interface, the LangGraph agent graph, the Celery heartbeat loop, and the frontend UI (only add a chain selector dropdown).

**Recommended expansion order:**
1. **Base** — lowest fees, Coinbase ecosystem native, x402 payments, EIP-7702 fully supported
2. **Polygon** — large established user base, Aave V4 live
3. **Optimism** — Velodrome DEX, Synthetix perpetuals (unique skill opportunity not on Arbitrum)

**Resources:**
- Aave deployed contracts across all chains: https://docs.aave.com/developers/deployed-contracts/v3-mainnet
- Base network developer documentation: https://docs.base.org/
- Coinbase Smart Wallet on Base (EIP-7702 native): https://www.coinbase.com/developer-platform/products/smart-wallet
- Uniswap V4 deployment addresses by chain: https://docs.uniswap.org/contracts/v4/deployments
- GMX on Arbitrum and Avalanche: https://gmxio.gitbook.io/gmx/contracts
- Foundry multi-chain fork testing: https://getfoundry.sh/forge/fork-testing

**Testing Gate — Issue 13**

Tool: Foundry fork test on Base Sepolia + `pytest` for backend chain-switching logic

What the tests check:
1. All three contracts deploy without error on a Base Sepolia fork (`forge test --fork-url $BASE_SEPOLIA_RPC`)
2. `AaveV4SkillBase.POOL_ADDRESS` differs from `AaveV4SkillArbitrum.POOL_ADDRESS` — asserted by inequality
3. `load_skills_for_user(user_address, skill_ids=[1], chain_id=8453)` returns an `AaveV4SkillBase` instance, not `AaveV4SkillArbitrum`
4. The executor switches RPC provider when `chain_id` changes — verified by checking the provider URL in the mocked web3 call
5. An agent config with `chain_id=8453` produces a heartbeat that uses Base protocol addresses — confirmed via mock call arguments
6. Full existing Arbitrum test suite still passes with zero regressions after the multi-chain refactor

A **passing gate** looks like: `forge test --fork-url $BASE_SEPOLIA_RPC --match-contract DeployTest` — three tests green. `pytest tests/test_multichain/ -v` — five tests green. `pytest tests/` (full suite) — zero regressions.

---

## Test Summary Reference

| Issue | Primary Test Tool | Test Count | Gate Command |
|---|---|---|---|
| 1 — Monorepo | bash + docker + forge | 6 checks | `docker compose up` + `forge build` |
| 2 — EIP-7702 contract | Foundry fork + cheatcodes | 7 Solidity tests | `forge test --fork-url $ARB_SEPOLIA -vv` |
| 3 — Billing contracts | Foundry fork + fuzz | 8 tests + fuzz | `forge test --match-contract BillingTest` |
| 4 — Skill plugin | pytest + mocks | 8 unit tests | `pytest tests/test_skills/` |
| 5 — LangGraph agent | pytest + InMemorySaver | 8 unit tests | `pytest tests/test_agent/` |
| 6 — Celery heartbeat | pytest + memory broker | 7 unit tests | `pytest tests/test_workers/` |
| 7 — Executor | pytest + EthTester + forge | 6 unit + 1 fork | `pytest tests/test_executor/` + `forge test` |
| 8 — FastAPI | pytest + TestClient | 8 unit tests | `pytest tests/test_api/` |
| 9 — Frontend | Vitest + Playwright | 6 unit + 1 E2E | `vitest run` + `playwright test` |
| 10 — Observability | pytest + Prometheus client | 6 unit tests | `pytest tests/test_observability/` |
| 11 — Security | Foundry invariant + pytest | 5 auto + manual | `forge test --match-contract Invariant` |
| 12 — Deployment | GitHub Actions + Locust | Pipeline + load test | CI green + P95 under 500ms |
| 13 — Multi-chain | Foundry fork (Base) + pytest | 6 tests | `forge test --fork-url $BASE_SEPOLIA` |
