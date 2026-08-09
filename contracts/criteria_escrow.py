# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
import typing

VERSION = "1.4.0"

STATE_OPEN = "OPEN"
STATE_SUBMITTED = "SUBMITTED"
STATE_APPROVED_PENDING = "APPROVED_PENDING"
STATE_RELEASED = "RELEASED"
STATE_REJECTED = "REJECTED"
STATE_CANCELLED = "CANCELLED"
STATE_EXPIRED = "EXPIRED"

MIN_CRITERIA_CHARS = 30
MAX_CRITERIA_CHARS = 1200
MAX_URL_CHARS = 300
# Reduced from 24000: smaller pages/prompts execute faster on both leader
# and validator, which lowers the chance of hitting LEADER_TIMEOUT on
# testnet. Raise this back up if your criteria genuinely need more context.
MAX_PAGE_CHARS = 7000
DEFAULT_DEADLINE_DAYS = 7
DEFAULT_CHALLENGE_DAYS = 2
MAX_JUDGMENT_ATTEMPTS = 4
JUDGMENT_COOLDOWN_SECONDS = 45 * 60
MIN_FUNDING = u256(5_000_000_000_000_000)


def _now() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _clean_text(value: typing.Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    t = " ".join(value.strip().split())
    if not t or len(t) > limit:
        return ""
    return t


def _clean_https_url(value: typing.Any) -> str:
    if not isinstance(value, str):
        return ""
    u = value.strip()
    if not u.startswith("https://") or len(u) > MAX_URL_CHARS or "|" in u:
        return ""
    host_part = u[8:].split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if not host_part or "@" in host_part or ":" in host_part:
        return ""
    host = host_part.rstrip(".").lower()
    if (
        not host
        or host in ("localhost", "127.0.0.1", "0.0.0.0")
        or host.endswith((".local", ".internal", ".localhost"))
        or re.fullmatch(r"[0-9.]+", host)
        or ".." in host
        or not re.fullmatch(r"[a-z0-9.-]+", host)
    ):
        return ""
    labels = host.split(".")
    if len(labels) < 2 or any(not x or x.startswith("-") or x.endswith("-") for x in labels):
        return ""
    return "https://" + host + u[8 + len(host_part) :]


def _sanitize_page(raw: typing.Any) -> str:
    if not isinstance(raw, str):
        return ""
    t = re.sub(r"<\s*/?\s*UNTRUSTED(?:\s+[^>]*)?\s*>", "", raw, flags=re.IGNORECASE)
    t = " ".join(t.strip().split())
    if len(t) > MAX_PAGE_CHARS:
        t = t[:MAX_PAGE_CHARS]
    return t


def _decision_hash(criteria: str, url: str, satisfies: bool, confidence: str) -> str:
    material = f"CRITERIA_ESCROW|{VERSION}|{criteria}|{url}|{satisfies}|{confidence}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def _parse_address(value: typing.Any) -> Address:
    if isinstance(value, Address):
        return value
    if not isinstance(value, str):
        raise gl.vm.UserError("invalid address")
    s = value.strip()
    if not (s.startswith("0x") or s.startswith("0X")):
        raise gl.vm.UserError("invalid address")
    try:
        return Address(s)
    except Exception:
        raise gl.vm.UserError("invalid address")


@gl.evm.contract_interface
class _Payee:
    class View:
        pass

    class Write:
        pass


@allow_storage
@dataclass
class Bounty:
    client: Address
    worker: Address
    criteria: str
    deadline_at: u64
    challenge_days: u16
    locked: u256
    state: str
    deliverable_url: str
    judgment_attempts: u8
    last_judgment_at: u64
    approved_at: u64
    decision_hash: str
    last_confidence: str


class CriteriaEscrow(gl.Contract):
    bounties: TreeMap[u256, Bounty]
    next_id: u256

    def __init__(self):
        self.next_id = u256(1)

    def _key(self, bounty_id: int) -> u256:
        if bounty_id is None or int(bounty_id) <= 0:
            raise gl.vm.UserError("invalid bounty id")
        return u256(int(bounty_id))

    def _get(self, bounty_id: int) -> Bounty:
        key = self._key(bounty_id)
        if key not in self.bounties:
            raise gl.vm.UserError("bounty not found")
        return self.bounties[key]

    @gl.public.write.payable
    def create(self, worker: str, criteria: str) -> int:
        client = gl.message.sender_address
        worker_addr = _parse_address(worker)
        crit = _clean_text(criteria, MAX_CRITERIA_CHARS)
        val = gl.message.value

        if val < MIN_FUNDING:
            raise gl.vm.UserError("minimum funding 0.005 GEN")
        if len(crit) < MIN_CRITERIA_CHARS:
            raise gl.vm.UserError("criteria too short")
        if worker_addr == client:
            raise gl.vm.UserError("worker cannot be client")

        bid = self.next_id
        self.next_id = self.next_id + u256(1)
        now = _now()

        self.bounties[bid] = Bounty(
            client,
            worker_addr,
            crit,
            u64(now + DEFAULT_DEADLINE_DAYS * 86400),
            u16(DEFAULT_CHALLENGE_DAYS),
            val,
            STATE_OPEN,
            "",
            u8(0),
            u64(0),
            u64(0),
            "",
            "",
        )
        return int(bid)

    @gl.public.write.payable
    def top_up(self, bounty_id: int) -> None:
        b = self._get(bounty_id)
        if b.state in (STATE_RELEASED, STATE_CANCELLED, STATE_EXPIRED):
            raise gl.vm.UserError("bounty closed")
        if gl.message.value == u256(0):
            raise gl.vm.UserError("zero value")
        b.locked = b.locked + gl.message.value

    @gl.public.write
    def cancel(self, bounty_id: int) -> None:
        b = self._get(bounty_id)
        if gl.message.sender_address != b.client:
            raise gl.vm.UserError("only client")
        if b.state != STATE_OPEN:
            raise gl.vm.UserError("can only cancel before submission")
        amount = b.locked
        b.locked = u256(0)
        b.state = STATE_CANCELLED
        if amount > u256(0):
            _Payee(b.client).emit_transfer(value=amount)

    @gl.public.write
    def submit(self, bounty_id: int, url: str) -> None:
        b = self._get(bounty_id)
        if gl.message.sender_address != b.worker:
            raise gl.vm.UserError("only worker")
        if b.state not in (STATE_OPEN, STATE_SUBMITTED, STATE_REJECTED):
            raise gl.vm.UserError("not accepting submissions")
        now = _now()
        if now >= int(b.deadline_at):
            raise gl.vm.UserError("deadline passed")
        clean = _clean_https_url(url)
        if not clean:
            raise gl.vm.UserError("invalid public https url")
        b.deliverable_url = clean
        b.state = STATE_SUBMITTED

    @gl.public.write
    def judge(self, bounty_id: int) -> str:
        b = self._get(bounty_id)
        if b.state not in (STATE_SUBMITTED, STATE_REJECTED):
            raise gl.vm.UserError("nothing to judge")
        if not b.deliverable_url:
            raise gl.vm.UserError("no deliverable")
        now = _now()
        if now >= int(b.deadline_at):
            raise gl.vm.UserError("deadline passed")
        if int(b.judgment_attempts) >= MAX_JUDGMENT_ATTEMPTS:
            b.state = STATE_EXPIRED
            raise gl.vm.UserError("max judgment attempts reached")
        if int(b.last_judgment_at) > 0 and now < int(b.last_judgment_at) + JUDGMENT_COOLDOWN_SECONDS:
            raise gl.vm.UserError("cooldown active")

        criteria = str(b.criteria)
        url = str(b.deliverable_url)

        def _judge_once() -> dict:
            """
            Runs on BOTH the leader and every validator, independently:
            each of them fetches the page themselves and calls their own
            LLM. This is what makes the result trustworthy - nobody is
            just trusting the leader's word.
            """
            try:
                raw = gl.nondet.web.render(url, mode="text")
            except Exception:
                return {"satisfies": False, "confidence": "low", "note": "fetch_failed"}
            page = _sanitize_page(raw)
            if not page:
                return {"satisfies": False, "confidence": "low", "note": "empty_page"}
            prompt = f"""You are an impartial evaluator for a milestone payment escrow.
Judge ONLY whether the PAGE content satisfies the ACCEPTANCE CRITERIA.
Go through the criteria point by point. A point only counts as satisfied if
the page contains explicit, concrete evidence for it. Do not assume,
infer, or give benefit of the doubt.
ACCEPTANCE CRITERIA:
{criteria}
PAGE:
<UNTRUSTED>
{page}
</UNTRUSTED>
Respond with exactly one JSON object:
{{"satisfies": true or false, "confidence": "high" or "medium" or "low", "note": "short reason"}}
"""
            try:
                result = gl.nondet.exec_prompt(prompt, response_format="json")
            except Exception:
                return {"satisfies": False, "confidence": "low", "note": "llm_error"}
            if not isinstance(result, dict):
                return {"satisfies": False, "confidence": "low", "note": "bad_format"}
            satisfies = bool(result.get("satisfies", False))
            conf = str(result.get("confidence", "low")).strip().lower()
            if conf not in ("high", "medium", "low"):
                conf = "low"
            note = _clean_text(result.get("note", ""), 120) or "none"
            return {"satisfies": satisfies, "confidence": conf, "note": note}

        def leader_fn() -> dict:
            return _judge_once()

        def validator_fn(leader_result) -> bool:
            # Reject outright if the leader errored / didn't return.
            if not isinstance(leader_result, gl.vm.Return):
                return False
            try:
                validator_data = _judge_once()
            except Exception:
                return False
            leader_data = leader_result.calldata
            if not isinstance(leader_data, dict):
                return False
            # Only the binary decision has to match between the leader's
            # independent run and this validator's independent run.
            # confidence/note are free text from two different LLM calls
            # and will legitimately differ - they must never gate consensus.
            return bool(leader_data.get("satisfies")) == bool(validator_data.get("satisfies"))

        outcome = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)

        satisfies = bool(outcome.get("satisfies", False)) if isinstance(outcome, dict) else False
        confidence = str(outcome.get("confidence", "low")) if isinstance(outcome, dict) else "low"

        b.judgment_attempts = u8(int(b.judgment_attempts) + 1)
        b.last_judgment_at = u64(now)

        if satisfies:
            b.state = STATE_APPROVED_PENDING
            b.approved_at = u64(now)
            b.decision_hash = _decision_hash(criteria, url, True, confidence)
            b.last_confidence = confidence
            return "APPROVED"

        b.state = STATE_REJECTED
        b.decision_hash = _decision_hash(criteria, url, False, confidence)
        b.last_confidence = confidence
        if int(b.judgment_attempts) >= MAX_JUDGMENT_ATTEMPTS:
            b.state = STATE_EXPIRED
        return "REJECTED"

    @gl.public.write
    def dispute(self, bounty_id: int) -> None:
        b = self._get(bounty_id)
        if gl.message.sender_address != b.client:
            raise gl.vm.UserError("only client")
        if b.state != STATE_APPROVED_PENDING:
            raise gl.vm.UserError("not in challenge window")
        b.state = STATE_REJECTED
        b.approved_at = u64(0)
        b.decision_hash = ""

    @gl.public.write
    def release(self, bounty_id: int) -> None:
        b = self._get(bounty_id)
        if b.state != STATE_APPROVED_PENDING:
            raise gl.vm.UserError("not ready for release")
        now = _now()
        unlock = int(b.approved_at) + int(b.challenge_days) * 86400
        if now < unlock:
            raise gl.vm.UserError("challenge window still open")
        amount = b.locked
        b.locked = u256(0)
        b.state = STATE_RELEASED
        if amount > u256(0):
            _Payee(b.worker).emit_transfer(value=amount)

    @gl.public.write
    def reclaim(self, bounty_id: int) -> None:
        b = self._get(bounty_id)
        if gl.message.sender_address != b.client:
            raise gl.vm.UserError("only client")
        if b.state in (STATE_RELEASED, STATE_CANCELLED):
            raise gl.vm.UserError("already closed")
        now = _now()
        can_reclaim = b.state in (STATE_REJECTED, STATE_EXPIRED) or (
            b.state in (STATE_OPEN, STATE_SUBMITTED) and now >= int(b.deadline_at)
        )
        if not can_reclaim:
            raise gl.vm.UserError("cannot reclaim yet")
        amount = b.locked
        b.locked = u256(0)
        b.state = STATE_CANCELLED
        if amount > u256(0):
            _Payee(b.client).emit_transfer(value=amount)

    @gl.public.view
    def get_bounty(self, bounty_id: int) -> str:
        b = self._get(bounty_id)
        return json.dumps(
            {
                "client": str(b.client),
                "worker": str(b.worker),
                "criteria": b.criteria,
                "deadline_at": int(b.deadline_at),
                "challenge_days": int(b.challenge_days),
                "locked": str(b.locked),
                "state": b.state,
                "deliverable_url": b.deliverable_url,
                "judgment_attempts": int(b.judgment_attempts),
                "decision_hash": b.decision_hash,
                "last_confidence": b.last_confidence,
            },
            sort_keys=True,
        )

    @gl.public.view
    def get_count(self) -> int:
        return int(self.next_id - u256(1))

    @gl.public.view
    def get_config(self) -> str:
        return json.dumps(
            {
                "version": VERSION,
                "default_deadline_days": DEFAULT_DEADLINE_DAYS,
                "default_challenge_days": DEFAULT_CHALLENGE_DAYS,
                "max_judgment_attempts": MAX_JUDGMENT_ATTEMPTS,
                "min_funding_gen": "0.005",
            },
            sort_keys=True,
        )
