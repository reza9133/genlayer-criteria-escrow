# Criteria Escrow on GenLayer

Intelligent escrow contract that releases funds based on AI + web evaluation of deliverables.

## Overview

Client locks GEN and defines acceptance criteria.  
Worker submits a public URL.  
Anyone can trigger `judge()`, which:
- Fetches the page (`gl.nondet.web.render`)
- Evaluates it with LLM
- Reaches consensus via independent validator re-execution (`gl.vm.run_nondet_unsafe`)

If criteria are satisfied → `APPROVED_PENDING` (with challenge window) → `release` to worker.  
Otherwise → `REJECTED` → client can `reclaim`.

## Key Features

- Fully on-chain intelligent judgment (no centralized oracle)
- Independent leader + validator evaluation (true consensus, not leader-output-only)
- Challenge/dispute window for client
- Cooldown + max judgment attempts protection
- Support for top-up, cancel, reclaim

## Deployed Contract (Bradbury Testnet)

- Address: `0xc0bd9f43697A004162AaEBBAd99834C34C410cDA`  
  *(replace with your final deployed address if different)*

## How it works

1. **create(worker, criteria)** – Client locks funds
2. **submit(bounty_id, url)** – Worker provides deliverable
3. **judge(bounty_id)** – AI evaluation + consensus
4. **dispute** (optional) – Client can reject during challenge window
5. **release** – After challenge window, funds go to worker
6. **reclaim** – Client recovers funds on rejection/expiry

## Test Results

Successfully tested on Bradbury:
- Deploy
- create → OPEN
- submit → SUBMITTED
- judge → APPROVED_PENDING (confidence: high)
- dispute → REJECTED

## Tech Stack

- GenLayer (Python contracts)
- Equivalence Principle with `run_nondet_unsafe`
- Web rendering + LLM evaluation

## License

MIT
