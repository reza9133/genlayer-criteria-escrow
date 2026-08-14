# Intelligent Criteria Escrow

An intelligent escrow contract on GenLayer that releases funds only when a public deliverable satisfies the client's acceptance criteria — evaluated by AI with true validator consensus.

## Problem

Traditional escrow relies on human judgment or centralized oracles.  
This is slow, expensive, and not trustless.

## Solution

Client locks GEN and defines clear acceptance criteria.  
Worker submits a public URL.  
Anyone can call `judge()`:

1. The page is fetched on-chain (`gl.nondet.web.render`)
2. An LLM evaluates whether the content meets the criteria
3. Validators independently re-fetch and re-evaluate
4. Consensus is reached only on the binary decision (`satisfies`)

If approved → challenge window → funds released to worker.  
If rejected → client can reclaim.

## Key Features

- Fully on-chain AI judgment (no external oracle)
- True consensus via independent leader + validator execution (`gl.vm.run_nondet_unsafe`)
- Client challenge/dispute window
- Judgment cooldown + max attempts protection
- Support for top-up, cancel, and reclaim

## Deployed Contract (Bradbury Testnet)

**Address:** `0xab4a89519790AF9746472Bc16095071abDAda3E7`

## How It Works

| Step | Method | Who | Description |
|------|--------|-----|-------------|
| 1 | `create(worker, criteria)` | Client | Locks funds and sets criteria |
| 2 | `submit(bounty_id, url)` | Worker | Submits public deliverable URL |
| 3 | `judge(bounty_id)` | Anyone | AI evaluation + consensus |
| 4 | `dispute(bounty_id)` | Client | Rejects during challenge window |
| 5 | `release(bounty_id)` | Anyone | Sends funds to worker after window |
| 6 | `reclaim(bounty_id)` | Client | Recovers funds on rejection/expiry |

## Tested Flows

Successfully tested on Bradbury testnet:

- Deploy
- Create bounty → `OPEN`
- Submit deliverable → `SUBMITTED`
- Judge → `APPROVED_PENDING` (confidence: high)
- Dispute → `REJECTED`

## Tech Stack

- GenLayer (Python smart contracts)
- Equivalence Principle with `run_nondet_unsafe`
- Web rendering + LLM evaluation
- Deterministic storage and state machine

## Project Structure
contracts/
  criteria_escrow.py    # Main contract (v1.4.0)

## License

MIT

