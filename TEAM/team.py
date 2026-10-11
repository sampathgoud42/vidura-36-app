#!/usr/bin/env python
"""TEAM: review trades, propose versioned rules, backtest them, apply on approval.

    python TEAM/team.py review [--bot KEY]       personas review the ledger -> proposals + report
    python TEAM/team.py list [--all]             proposals (pending by default)
    python TEAM/team.py show P-0001              one proposal, its evidence and backtest
    python TEAM/team.py backtest P-0001          re-run a proposal's backtest on today's ledger
    python TEAM/team.py approve P-0001 [--note]  -> active ruleset version N+1, enforced live
    python TEAM/team.py reject P-0001 [--note]
    python TEAM/team.py retire P-0001 [--note]   remove an approved rule (version N+1)
    python TEAM/team.py rollback N               make ruleset version N active again (as N+1)
    python TEAM/team.py status                   active rules, gate hits, live results since approval

The ledger is opened read-only. The only files this writes are under TEAM/.
Rule semantics come from backend/app/domains/botstation/team_gate.py, the same
module that enforces them live, so a backtest and the gate cannot disagree.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

TEAM = Path(__file__).resolve().parent
ROOT = TEAM.parent
DB = ROOT / "var" / "app-v2.db"
PROPOSALS = TEAM / "proposals"
RULES = TEAM / "rules"
ACTIVE = RULES / "active.json"
HISTORY = RULES / "history"
REVIEWS = TEAM / "reviews"
GATE_LOG = RULES / "gate_log.jsonl"

TRAIN_FRAC = 0.70      # first 70% of each bot's trades by time; the rest is holdout
MIN_CELL = 10          # QA-R1: a cell under 10 trades can't produce a rule
QA_FLOOR = 30          # QA-R1: a cell of 30+ meets the full change floor
MIN_TEST_TOUCH = 3     # holdout trades a rule must touch before its verdict counts

_spec = importlib.util.spec_from_file_location(
    "team_gate", ROOT / "backend" / "app" / "domains" / "botstation" / "team_gate.py")
gate = importlib.util.module_from_spec(_spec)
sys.modules["team_gate"] = gate
_spec.loader.exec_module(gate)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, data) -> None:
    """Atomic: the live gate may be reading this file at the same moment."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)


# ---- ledger ------------------------------------------------------------------

def load_trades(db: Path = DB) -> list[dict]:
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    rows = con.execute(
        "select id, bot_key, bot_version, ticker, opened_at, entry_price, "
        "realized_pnl, entry_usd, contracts, raw from bot_trade "
        "where realized_pnl is not null and entry_price is not null "
        "order by opened_at").fetchall()
    con.close()
    out = []
    for rid, bot, ver, tk, opened, price, pnl, usd, n, raw in rows:
        try:
            raw = json.loads(raw or "{}")
        except ValueError:
            raw = {}
        price_c = price * 100 if price <= 1 else price
        legs = raw.get("tickers")
        out.append({
            "id": rid, "bot": bot, "version": ver, "ticker": tk,
            "when": datetime.fromisoformat(str(opened)).replace(tzinfo=timezone.utc),
            "price_c": round(price_c, 2), "pnl": float(pnl),
            "stake_usd": float(usd) if usd else (n or 0) * price_c / 100,
            "legs": len(legs) if isinstance(legs, list) else None,
        })
    return out


def split(trades: list[dict]) -> tuple[list[dict], list[dict]]:
    k = int(len(trades) * TRAIN_FRAC)
    return trades[:k], trades[k:]


# ---- metrics & replay -----------------------------------------------------------

def metrics(trades: list[dict]) -> dict:
    n = len(trades)
    wins = [t["pnl"] for t in trades if t["pnl"] > 0]
    losses = [t["pnl"] for t in trades if t["pnl"] <= 0]
    aw = sum(wins) / len(wins) if wins else 0.0
    al = sum(losses) / len(losses) if losses else 0.0
    eq = peak = dd = 0.0
    for t in trades:
        eq += t["pnl"]
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return {"n": n, "wins": len(wins),
            "win_rate": round(len(wins) / n, 3) if n else None,
            "implied": round(sum(t["price_c"] for t in trades) / n / 100, 3) if n else None,
            "breakeven": round(abs(al) / (aw + abs(al)), 3) if (aw or al) else None,
            "pnl": round(sum(t["pnl"] for t in trades), 2),
            "max_dd": round(dd, 2)}


def replay(trades: list[dict], rules: list[dict]) -> dict:
    """Run trades through the rules exactly as the live gate would."""
    kept, touched, blocked = [], 0, []
    for t in trades:
        v = gate.evaluate(rules, bot=t["bot"], price_c=t["price_c"],
                          stake_usd=t["stake_usd"], legs=t["legs"], when=t["when"])
        if not v.allowed:
            blocked.append(t)
            touched += 1
            continue
        if v.stake_usd is not None and t["stake_usd"] and v.stake_usd < t["stake_usd"]:
            touched += 1
            t = {**t, "pnl": t["pnl"] * v.stake_usd / t["stake_usd"]}
        kept.append(t)
    base, after = metrics(trades), metrics(kept)
    return {"baseline": base, "with_rules": after, "touched": touched,
            "blocked": len(blocked),
            "blocked_pnl": round(sum(t["pnl"] for t in blocked), 2),
            "winners_blocked": sum(t["pnl"] > 0 for t in blocked),
            "delta_pnl": round(after["pnl"] - base["pnl"], 2)}


def backtest(trades: list[dict], rules: list[dict]) -> dict:
    by_bot = defaultdict(list)
    for t in trades:
        by_bot[t["bot"]].append(t)
    train, test = [], []
    for ts in by_bot.values():
        a, b = split(ts)
        train += a
        test += b
    return {"train": replay(train, rules), "test": replay(test, rules),
            "all": replay(trades, rules)}


def recommend(v: str, floor_met: bool, bt: dict) -> bool:
    """PASS is "the holdout didn't contradict it". RECOMMEND is the stronger
    claim: the cell meets QA-R1's 30-trade floor and the holdout touched
    enough trades to mean something."""
    return v == "PASS" and floor_met and bt["test"]["touched"] >= 5


def verdict(bt: dict) -> str:
    tr, te = bt["train"], bt["test"]
    if tr["delta_pnl"] <= 0:
        return "FAIL"
    if te["touched"] < MIN_TEST_TOUCH:
        return "INSUFFICIENT"
    return "PASS" if te["delta_pnl"] > 0 else "FAIL"


# ---- the personas' reviews (each proposes from TRAIN data only) -----------------------

def _cell(trades):
    m = metrics(trades)
    return {"n": m["n"], "win_rate": m["win_rate"], "implied": m["implied"],
            "pnl": m["pnl"]}


def quant_price_bands(bot, train):
    """Quant Strategist: 10c buckets where realised < implied and money was lost."""
    buckets = defaultdict(list)
    for t in train:
        buckets[int(t["price_c"] // 10) * 10].append(t)
    bad = sorted(b for b, ts in buckets.items()
                 if len(ts) >= MIN_CELL and sum(x["pnl"] for x in ts) < 0
                 and metrics(ts)["win_rate"] < metrics(ts)["implied"])
    out, run = [], []
    for b in bad + [None]:
        if run and (b is None or b != run[-1] + 10):
            lo, hi = run[0], run[-1] + 10
            cell = [t for t in train if lo <= t["price_c"] < hi]
            out.append({"bot": bot, "type": "block_price_band",
                        "params": {"min_c": lo, "max_c": hi},
                        "persona": "quant_strategist", "evidence": _cell(cell),
                        "rationale": f"{lo}-{hi}c realised win rate below the price paid, and lost money"})
            run = []
        if b is not None:
            run.append(b)
    return out


def pm_suspend(bot, train):
    """Project Manager: a bot far below its own break-even is stopped."""
    m = metrics(train)
    if m["n"] >= MIN_CELL and m["pnl"] < 0 and m["breakeven"] \
            and m["win_rate"] < m["breakeven"] - 0.15:
        return [{"bot": bot, "type": "suspend", "params": {},
                 "persona": "project_manager", "evidence": _cell(train),
                 "rationale": f"win rate {m['win_rate']:.0%} is >15 pts under break-even {m['breakeven']:.0%}"}]
    return []


def pm_stake_cap(bot, train):
    """Project Manager: losses concentrated in the larger stakes."""
    stakes = sorted(t["stake_usd"] for t in train)
    if len(stakes) < 2 * MIN_CELL:
        return []
    med = stakes[len(stakes) // 2]
    hi = [t for t in train if t["stake_usd"] > med]
    lo = [t for t in train if t["stake_usd"] <= med]
    if len(hi) >= MIN_CELL and metrics(hi)["pnl"] < 0 < metrics(lo)["pnl"]:
        return [{"bot": bot, "type": "max_stake_usd", "params": {"usd": round(med, 2)},
                 "persona": "project_manager", "evidence": _cell(hi),
                 "rationale": f"stakes above ${med:.2f} lost money; stakes at or below made money"}]
    return []


def sports_max_legs(bot, train):
    """Sports & Parlay Specialist: too many legs."""
    legged = [t for t in train if t["legs"]]
    best = None
    for k in sorted({t["legs"] for t in legged}):
        over = [t for t in legged if t["legs"] > k]
        if len(over) >= MIN_CELL and metrics(over)["pnl"] < 0:
            gain = -metrics(over)["pnl"]
            if best is None or gain > best[0]:
                best = (gain, k, over)
    if not best:
        return []
    _, k, over = best
    return [{"bot": bot, "type": "max_legs", "params": {"n": k},
             "persona": "sports_parlay_specialist", "evidence": _cell(over),
             "rationale": f"combos with more than {k} legs lost money"}]


def sentinel_hours(bot, train):
    """Regime Sentinel: 4-hour CT windows that lose."""
    blocks = defaultdict(list)
    for t in train:
        blocks[gate._hour_ct(t["when"]) // 4].append(t)
    out = []
    for blk, ts in sorted(blocks.items()):
        m = metrics(ts)
        if m["n"] >= MIN_CELL and m["pnl"] < 0 and m["win_rate"] < (m["breakeven"] or 1):
            hrs = list(range(blk * 4, blk * 4 + 4))
            out.append({"bot": bot, "type": "block_hours", "params": {"hours": hrs},
                        "persona": "regime_sentinel", "evidence": _cell(ts),
                        "rationale": f"{hrs[0]:02d}:00-{hrs[-1]:02d}:59 CT lost money below break-even"})
    return out


REVIEWERS = (pm_suspend, quant_price_bands, sports_max_legs, sentinel_hours, pm_stake_cap)


# ---- proposals --------------------------------------------------------------------

def _key(r) -> str:
    return json.dumps([r["bot"], r["type"], r["params"]], sort_keys=True)


def all_proposals() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(PROPOSALS.glob("P-*.json"))]


def get_proposal(pid: str) -> dict:
    p = PROPOSALS / f"{pid}.json"
    if not p.exists():
        sys.exit(f"no such proposal: {pid}")
    return json.loads(p.read_text(encoding="utf-8"))


def save_proposal(prop: dict) -> None:
    write_json(PROPOSALS / f"{prop['id']}.json", prop)


def next_id() -> str:
    ids = [int(p["id"][2:]) for p in all_proposals()]
    return f"P-{(max(ids) + 1 if ids else 1):04d}"


def active() -> dict:
    if ACTIVE.exists():
        return json.loads(ACTIVE.read_text(encoding="utf-8"))
    return {"version": 0, "updated_at": None, "rules": []}


def as_rule(prop: dict) -> dict:
    return {"id": "R" + prop["id"][1:], "proposal": prop["id"], "bot": prop["bot"],
            "type": prop["type"], "params": prop["params"]}


def publish(rules: list[dict], why: str) -> int:
    cur = active()
    new = {"version": cur["version"] + 1, "updated_at": now_iso(),
           "change": why, "rules": rules}
    write_json(HISTORY / f"v{new['version']:04d}.json", new)
    write_json(ACTIVE, new)
    with (RULES / "CHANGELOG.md").open("a", encoding="utf-8") as fh:
        fh.write(f"- v{new['version']} {new['updated_at']}: {why}\n")
    return new["version"]


# ---- commands ---------------------------------------------------------------------

def _fmt_bt(bt: dict) -> str:
    lines = []
    for part in ("train", "test", "all"):
        r = bt[part]
        b, a = r["baseline"], r["with_rules"]
        lines.append(
            f"  {part:5} n {b['n']:>3}->{a['n']:<3} win {_p(b['win_rate'])}->{_p(a['win_rate'])} "
            f"pnl {b['pnl']:>8.2f}->{a['pnl']:<8.2f} (Δ {r['delta_pnl']:+.2f}) "
            f"blocked {r['blocked']} (winners {r['winners_blocked']}, pnl {r['blocked_pnl']:+.2f}) "
            f"maxDD {b['max_dd']:.2f}->{a['max_dd']:.2f}")
    return "\n".join(lines)


def _p(x):
    return "  -  " if x is None else f"{x * 100:4.1f}%"


def cmd_review(a) -> None:
    trades = load_trades()
    if a.bot:
        trades = [t for t in trades if t["bot"] == a.bot]
    by_bot = defaultdict(list)
    for t in trades:
        by_bot[t["bot"]].append(t)
    existing = {_key(p): p for p in all_proposals()}
    act = active()
    created, refreshed, report = [], [], []

    for bot, ts in sorted(by_bot.items(), key=lambda kv: -len(kv[1])):
        train, _ = split(ts)
        for review in REVIEWERS:
            for cand in review(bot, train):
                bt = backtest(ts, [as_rule({**cand, "id": "P-cand"})])
                v = verdict(bt)
                # Full-data cell size, for QA-R1's 30-trade change floor.
                cell_all = replay([t for t in ts], [as_rule({**cand, "id": "P-cand"})])
                old = existing.get(_key(cand))
                if old and old["status"] in ("approved", "rejected", "retired"):
                    continue
                prop = old or {"id": next_id(), "created_at": now_iso(),
                               "status": "proposed", "history": []}
                prop.update(cand)
                floor = cell_all["touched"] >= QA_FLOOR
                prop.update(backtest=bt, verdict=v, reviewed_at=now_iso(),
                            qa_floor_met=floor, ruleset_base=act["version"],
                            recommend=recommend(v, floor, bt))
                prop["history"].append({"at": now_iso(), "event": "reviewed", "verdict": v})
                save_proposal(prop)
                (refreshed if old else created).append(prop)
                existing[_key(cand)] = prop

    # What the desk would look like with the current rules plus every PASS.
    pending_pass = [as_rule(p) for p in all_proposals()
                    if p["status"] == "proposed" and p.get("recommend")]
    combined = backtest(trades, act["rules"] + pending_pass) if pending_pass else None
    current = backtest(trades, act["rules"]) if act["rules"] else None

    REVIEWS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    path = REVIEWS / f"{stamp}_review.md"
    out = [f"# TEAM review {stamp}", "",
           f"Ledger: {len(trades)} settled trades · active ruleset v{act['version']} "
           f"({len(act['rules'])} rules) · holdout = last {int((1 - TRAIN_FRAC) * 100)}% of each bot by time", ""]
    out += ["## Per-bot baseline", "", "| bot | n | win | implied | break-even | pnl | max DD |",
            "|---|---|---|---|---|---|---|"]
    for bot, ts in sorted(by_bot.items(), key=lambda kv: -len(kv[1])):
        m = metrics(ts)
        out.append(f"| {bot} | {m['n']} | {_p(m['win_rate'])} | {_p(m['implied'])} | "
                   f"{_p(m['breakeven'])} | {m['pnl']:.2f} | {m['max_dd']:.2f} |")
    out += ["", "## Proposals", ""]
    for p in created + refreshed:
        tag = p['verdict'] + (" · RECOMMENDED" if p.get("recommend") else "")
        out += [f"### {p['id']} [{tag}] {p['bot']} · {p['type']} {json.dumps(p['params'])}",
                f"*{p['persona']}*: {p['rationale']}. Train cell: {p['evidence']}. "
                f"QA 30-trade floor met: {'yes' if p['qa_floor_met'] else 'no'}.",
                "```", _fmt_bt(p["backtest"]), "```", ""]
    if not (created or refreshed):
        out.append("No new proposals: no cell cleared the evidence floor.")
    for title, bt in (("Current ruleset", current), ("Current + all RECOMMENDED proposals", combined)):
        if bt:
            out += ["", f"## {title}", "```", _fmt_bt(bt), "```"]
    path.write_text("\n".join(out) + "\n", encoding="utf-8")

    print("\n".join(out))
    print(f"\nreport: {path.relative_to(ROOT)}")
    print("approve with:  python TEAM/team.py approve <ID>")


def cmd_list(a) -> None:
    for p in all_proposals():
        if a.all or p["status"] == "proposed":
            t = p["backtest"]["test"]
            tag = p["verdict"] + ("*" if p.get("recommend") else "")
            print(f"{p['id']}  {p['status']:9} {tag:13} {p['bot']:9} {p['type']:16} "
                  f"{json.dumps(p['params']):30} test Δ {t['delta_pnl']:+8.2f}  all Δ "
                  f"{p['backtest']['all']['delta_pnl']:+8.2f}  [{p['persona']}]")


def cmd_show(a) -> None:
    p = get_proposal(a.id)
    print(json.dumps({k: v for k, v in p.items() if k != "backtest"}, indent=2, default=str))
    print(_fmt_bt(p["backtest"]))


def cmd_backtest(a) -> None:
    p = get_proposal(a.id)
    bt = backtest([t for t in load_trades() if t["bot"] == p["bot"]], [as_rule(p)])
    p.update(backtest=bt, verdict=verdict(bt), reviewed_at=now_iso(),
             recommend=recommend(verdict(bt), p.get("qa_floor_met", False), bt))
    p["history"].append({"at": now_iso(), "event": "re-backtested", "verdict": p["verdict"]})
    save_proposal(p)
    print(f"{p['id']} {p['verdict']}\n{_fmt_bt(bt)}")


def cmd_approve(a) -> None:
    p = get_proposal(a.id)
    if p["status"] != "proposed":
        sys.exit(f"{p['id']} is {p['status']}, not proposed")
    if p["verdict"] == "FAIL" and not a.force:
        sys.exit(f"{p['id']} FAILED its backtest; pass --force to approve anyway")
    rules = [r for r in active()["rules"] if r["proposal"] != p["id"]] + [as_rule(p)]
    ver = publish(rules, f"approve {p['id']} {p['bot']} {p['type']} {json.dumps(p['params'])}"
                         + (f" -- {a.note}" if a.note else ""))
    p.update(status="approved", approved_at=now_iso(), ruleset_version=ver)
    p["history"].append({"at": now_iso(), "event": "approved", "version": ver, "note": a.note})
    save_proposal(p)
    print(f"{p['id']} approved -> ruleset v{ver}; the gate enforces it on the next order")


def _set_status(a, status: str, verb: str) -> None:
    p = get_proposal(a.id)
    if verb == "retire":
        if p["status"] != "approved":
            sys.exit(f"{p['id']} is {p['status']}, not approved")
        rules = [r for r in active()["rules"] if r["proposal"] != p["id"]]
        ver = publish(rules, f"retire {p['id']}" + (f" -- {a.note}" if a.note else ""))
        print(f"{p['id']} retired -> ruleset v{ver}")
    elif p["status"] != "proposed":
        sys.exit(f"{p['id']} is {p['status']}, not proposed")
    p["status"] = status
    p["history"].append({"at": now_iso(), "event": status, "note": a.note})
    save_proposal(p)
    print(f"{p['id']} {status}")


def cmd_rollback(a) -> None:
    snap = HISTORY / f"v{a.version:04d}.json"
    if a.version == 0:
        rules = []
    elif snap.exists():
        rules = json.loads(snap.read_text(encoding="utf-8"))["rules"]
    else:
        sys.exit(f"no ruleset v{a.version}")
    ver = publish(rules, f"rollback to v{a.version}")
    live = {r["proposal"] for r in rules}
    for p in all_proposals():
        if p["status"] == "approved" and p["id"] not in live:
            p["status"] = "retired"
            p["history"].append({"at": now_iso(), "event": f"retired by rollback to v{a.version}"})
            save_proposal(p)
        elif p["id"] in live and p["status"] != "approved":
            p["status"] = "approved"
            p["history"].append({"at": now_iso(), "event": f"restored by rollback to v{a.version}"})
            save_proposal(p)
    print(f"ruleset v{a.version} is active again as v{ver}")


def cmd_status(a) -> None:
    act = active()
    print(f"active ruleset v{act['version']}  updated {act.get('updated_at')}  "
          f"({act.get('change', '-')})")
    hits = Counter()
    if GATE_LOG.exists():
        for line in GATE_LOG.read_text(encoding="utf-8").splitlines():
            e = json.loads(line)
            for rid in e["rules"]:
                hits[(rid, "blocked" if not e["allowed"] else "capped")] += 1
    trades = load_trades()
    for r in act["rules"]:
        p = get_proposal(r["proposal"])
        since = datetime.fromisoformat(p["approved_at"])
        after = [t for t in trades if t["bot"] == r["bot"] and t["when"] >= since]
        m = metrics(after)
        print(f"  {r['id']} {r['bot']:9} {r['type']:16} {json.dumps(r['params']):28} "
              f"gate blocked {hits[(r['id'], 'blocked')]} capped {hits[(r['id'], 'capped')]} · "
              f"{r['bot']} since approval: n {m['n']} win {_p(m['win_rate'])} pnl {m['pnl']:+.2f}")
    if not act["rules"]:
        print("  (no rules active)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("review"); s.add_argument("--bot"); s.set_defaults(fn=cmd_review)
    s = sub.add_parser("list"); s.add_argument("--all", action="store_true"); s.set_defaults(fn=cmd_list)
    for name, fn in (("show", cmd_show), ("backtest", cmd_backtest)):
        s = sub.add_parser(name); s.add_argument("id"); s.set_defaults(fn=fn)
    s = sub.add_parser("approve"); s.add_argument("id"); s.add_argument("--note", default="")
    s.add_argument("--force", action="store_true"); s.set_defaults(fn=cmd_approve)
    for name, status in (("reject", "rejected"), ("retire", "retired")):
        s = sub.add_parser(name); s.add_argument("id"); s.add_argument("--note", default="")
        s.set_defaults(fn=lambda a, st=status, v=name: _set_status(a, st, v))
    s = sub.add_parser("rollback"); s.add_argument("version", type=int); s.set_defaults(fn=cmd_rollback)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    a.fn(a)


if __name__ == "__main__":
    main()
