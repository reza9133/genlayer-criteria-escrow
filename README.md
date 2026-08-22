# Intelligent Criteria Escrow

An intelligent escrow contract on GenLayer that releases funds only when an immutable public deliverable satisfies the client's acceptance criteria — evaluated by AI with true validator consensus.

## Problem

Traditional escrow relies on human judgment or centralized oracles.  
This is slow, expensive, and not trustless. Furthermore, traditional systems often suffer from unilateral refund loopholes where clients can lock funds in disputes indefinitely.

## Solution

Client locks GEN and defines clear acceptance criteria.  
Worker submits an **immutable public URL** (e.g., IPFS, Arweave, or raw GitHub commit).  
Anyone can call `judge()`:

1. The page is fetched on-chain via `gl.nondet.web.get`
2. An LLM evaluates whether the content meets the criteria
3. Validators independently re-fetch and re-evaluate
4. Consensus is reached only on the binary decision (`satisfies`)

If approved → challenge window → funds released to worker.  
If rejected → client can reclaim immediately.
If disputed → a binding final re-adjudication (`resolve_dispute`) decisively settles the outcome, preventing indefinitely stuck funds.

## Key Features

- **Fully On-Chain AI Judgment:** No external oracles required.
- **True Consensus:** Independent leader + validator execution (`gl.vm.run_nondet_unsafe`).
- **Immutable Deliverables:** Security requirement ensuring the worker cannot alter the submission post-evaluation.
- **Bulletproof Dispute Resolution:** Guaranteed settlement paths via binding re-adjudication, eliminating unilateral client griefing and stuck funds.

## Deployed Contract (Bradbury Testnet)

**Address:** `0x80F748C8bd41312c7D110B3B5bfDdDA4Ed828100`

## How It Works

| Step | Method | Who | Description |
|------|--------|-----|-------------|
| 1 | `create(worker, criteria)` | Client | Locks funds and sets criteria |
| 2 | `submit(bounty_id, url)` | Worker | Submits an immutable deliverable URL |
| 3 | `judge(bounty_id)` | Anyone | Initial AI evaluation + consensus |
| 4 | `dispute(bounty_id)` | Client | Opens a dispute during the challenge window |
| 5 | `resolve_dispute(id)` | Anyone | **Binding final re-adjudication** to decisively settle disputes |
| 6 | `release(bounty_id)` | Anyone | Sends funds to worker after window (or on timeout outcome) |
| 7 | `reclaim(bounty_id)` | Client | Recovers funds on strict rejection/expiry |

## Tested Flows

Successfully tested on Bradbury testnet:

- **Happy Path:** Create bounty → `OPEN` → Submit deliverable → `SUBMITTED` → Judge → `APPROVED_PENDING` → Release → `RELEASED`
- **Dispute Resolution (The Red Team Test):** Judge → `APPROVED_PENDING` → Client Disputes → `DISPUTED` → Resolve Dispute → `RELEASED` (AI confirms worker's validity) or `CANCELLED` (Funds returned).

## Tech Stack

- GenLayer (Python smart contracts)
- Equivalence Principle with `run_nondet_unsafe`
- Web fetching + LLM evaluation
- Deterministic storage and state machine

## Project Structure
contracts/
criteria_escrow.py    # Main contract (v1.7.0)


## License

MIT
