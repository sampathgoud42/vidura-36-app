"""Cash on Kalshi's exchange shards, and moving it between them.

Kalshi keeps an account's cash per exchange shard (``exchange_index``), and an
order spends only the cash on the shard its market settles on. Every
fifteen-minute market settles on shard 2, combos on shard 1, most else on 0 --
so with the whole balance on shard 0, a 15-minute order is refused as
insufficient_balance on a funded account. Kalshi moves cash to the combo
shard on its own; nothing moves it to shard 2 but a transfer.

This is that transfer: Kalshi's intra-account transfer, event contract to
event contract, one shard to another, inside the operator's own account. The
Bot Station's MOVE MONEY form asks for the amount and the direction and
confirms before calling it.

NEVER RETRIED. The exchange's transfer takes no idempotency key, so a retry
after a lost response could move the money twice. Instead each confirmation
is idempotent here, by its own key, for as long as this process lives -- and a
transfer whose answer was lost is reported as UNKNOWN, with the history to
check, rather than sent again.

Amounts: the transfer takes CENTICENTS ($1 = 10,000), while balances and the
transfer history report dollars. Everything this module accepts and returns
is dollars; the conversion happens in one place.
"""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

CENTICENTS_PER_USD = 10_000
TRANSFER_PATH = "/portfolio/intra_exchange_instance_transfer"
HISTORY_PATH = "/portfolio/intra_exchange_instance_transfers"
MAX_SHARD = 100

# What each shard is for, as far as this desk is concerned. Shown on the form
# so "why would I move money to 2" answers itself.
PURPOSE = {0: "default", 1: "combos (parlays, luck)", 2: "15-minute markets"}

# (owner, confirmation key) -> (when, result). One answer per confirmation.
_DONE: dict[tuple[str, str], tuple[float, dict]] = {}
_LOCK = threading.Lock()
DONE_TTL_S = 3600.0


class TransferRefused(ValueError):
    """Refused before anything was sent, with the reason in words."""


def _usd(raw) -> float:
    try:
        return round(float(raw or 0), 4)
    except (TypeError, ValueError):
        return 0.0


def balances(client) -> list[dict]:
    """Cash per shard, in dollars, lowest shard first."""
    data = client.request("GET", "/portfolio/balance")
    rows = []
    for row in data.get("balance_breakdown") or []:
        try:
            shard = int(row.get("exchange_index"))
        except (TypeError, ValueError):
            continue
        rows.append({"shard": shard, "usd": _usd(row.get("balance")),
                     "purpose": PURPOSE.get(shard, "")})
    return sorted(rows, key=lambda r: r["shard"])


def recent(client, limit: int = 8) -> list[dict]:
    """The account's latest shard transfers -- Kalshi's own included."""
    data = client.request("GET", HISTORY_PATH, params={"limit": limit})
    out = []
    for row in data.get("transfers") or []:
        out.append({"id": row.get("transfer_id") or row.get("id"),
                    "from": row.get("source_exchange_shard"),
                    "to": row.get("destination_exchange_shard"),
                    "usd": _usd(row.get("amount")), "status": row.get("status"),
                    "at": row.get("created_ts")})
    return out


def snapshot(cred) -> dict:
    from app.domains.botstation import venue

    client = venue._client(cred)
    try:
        shards = balances(client)
        try:
            history = recent(client)
        except Exception:                               # noqa: BLE001
            history = []                                # the balances still answer
        return {"shards": shards, "transfers": history}
    finally:
        client.close()


def _sweep() -> None:
    now = time.time()
    with _LOCK:
        for key in [k for k, (at, _) in _DONE.items() if now - at > DONE_TTL_S]:
            _DONE.pop(key, None)


def transfer(cred, *, usd: float, source: int, destination: int, key: str,
             owner: str) -> dict:
    """Move ``usd`` dollars from shard ``source`` to shard ``destination``.
    REAL MONEY, inside the operator's own account."""
    from app.domains.botstation import venue

    key = (key or "").strip()
    _sweep()
    with _LOCK:
        seen = _DONE.get((owner, key))
    if seen is not None:
        return {**seen[1], "repeat": True}

    amount = round(float(usd), 2)
    if not amount > 0:
        raise TransferRefused("the amount must be more than $0")
    if source == destination:
        raise TransferRefused("the source and the destination are the same shard")
    for shard in (source, destination):
        if not 0 <= int(shard) <= MAX_SHARD:
            raise TransferRefused(f"shard {shard} does not exist")

    client = venue._client(cred)
    try:
        before = balances(client)
        held = next((r["usd"] for r in before if r["shard"] == source), None)
        if held is None:
            raise TransferRefused(f"this account has no shard {source}")
        if held < amount:
            raise TransferRefused(
                f"shard {source} holds ${held:,.2f}, less than ${amount:,.2f}")
        body = {"source": "event_contract", "destination": "event_contract",
                "amount": int(round(amount * CENTICENTS_PER_USD)),
                "source_exchange_shard": int(source),
                "destination_exchange_shard": int(destination),
                "source_subaccount": 0, "destination_subaccount": 0}
        try:
            # ONE attempt. A second is a second transfer.
            answer = client.request("POST", TRANSFER_PATH, json_body=body, retries=1)
        except Exception as exc:                        # noqa: BLE001
            status = getattr(exc, "status_code", None)
            if status is not None and status < 500:
                # Refused outright: nothing moved, and it is safe to say so.
                result = {"moved": False, "usd": amount, "source": source,
                          "destination": destination,
                          "detail": f"Kalshi refused the transfer ({status}): "
                                    f"{str(getattr(exc, 'body', '') or exc)[:200]}"}
            else:
                # No answer, or a server error: it may or may not have moved.
                result = {"moved": None, "usd": amount, "source": source,
                          "destination": destination,
                          "detail": "Kalshi did not answer, so it is not known "
                                    "whether the money moved. Check the transfer "
                                    "list and the balances before trying again."}
            with _LOCK:
                _DONE[(owner, key)] = (time.time(), result)
            logger.warning("shard transfer $%.2f %s->%s: %s", amount, source,
                           destination, result["detail"])
            return result

        transfer_id = (answer or {}).get("transfer_id") or ""
        logger.info("shard transfer $%.2f %s->%s accepted: %s", amount, source,
                    destination, transfer_id)
        # Processed asynchronously; a moment later the balances usually show it.
        time.sleep(1.0)
        try:
            after = balances(client)
            history = recent(client)
        except Exception:                               # noqa: BLE001
            after, history = before, []
        status = next((t["status"] for t in history if t["id"] == transfer_id), None)
        result = {"moved": True, "usd": amount, "source": source,
                  "destination": destination, "transfer_id": transfer_id,
                  "status": status or "accepted", "shards": after,
                  "transfers": history}
        with _LOCK:
            _DONE[(owner, key)] = (time.time(), result)
        return result
    finally:
        client.close()


def reset_for_tests() -> None:
    with _LOCK:
        _DONE.clear()
