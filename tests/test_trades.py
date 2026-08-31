from __future__ import annotations


def _mock_trade(**overrides) -> dict:
    body = {
        "bot_key": "manual",
        "ticker": "KXBTCD-26JUL27H21-T118000",
        "side": "yes",
        "action": "buy",
        "contracts": 5,
        "price_cents": 62,
        "cost_usd": 3.10,
        "status": "open",
        "is_mock": True,
    }
    body.update(overrides)
    return body


def test_record_and_list_trades(client, user):
    uid = user["user_id"]
    resp = client.post(f"/api/v1/users/{uid}/trades", json=_mock_trade())
    assert resp.status_code == 201, resp.text
    trade = resp.json()
    assert trade["id"] > 0
    assert trade["is_mock"] is True

    resp = client.get(f"/api/v1/users/{uid}/trades")
    assert resp.status_code == 200
    page = resp.json()
    assert page["total"] == 1
    assert page["items"][0]["ticker"].startswith("KXBTCD")


def test_trade_filters(client, user):
    uid = user["user_id"]
    client.post(f"/api/v1/users/{uid}/trades", json=_mock_trade(bot_key="btc15"))
    client.post(
        f"/api/v1/users/{uid}/trades",
        json=_mock_trade(bot_key="sports", ticker="KXATPMATCH-X", status="won", pnl_usd=4.2),
    )

    resp = client.get(f"/api/v1/users/{uid}/trades", params={"bot_key": "sports"})
    assert resp.json()["total"] == 1
    resp = client.get(f"/api/v1/users/{uid}/trades", params={"status": "won"})
    assert resp.json()["total"] == 1


def test_sports_active_bets_and_performance(client, user):
    uid = user["user_id"]
    client.post(
        f"/api/v1/users/{uid}/trades",
        json=_mock_trade(bot_key="sports", ticker="KXATPMATCH-OPEN", status="open"),
    )
    client.post(
        f"/api/v1/users/{uid}/trades",
        json=_mock_trade(bot_key="sports", ticker="KXATPMATCH-WON", status="won", pnl_usd=10.0),
    )
    client.post(
        f"/api/v1/users/{uid}/trades",
        json=_mock_trade(bot_key="sports", ticker="KXATPMATCH-LOST", status="lost", pnl_usd=-4.0),
    )

    resp = client.get("/api/v1/bots/sports/active-bets", params={"user_id": uid})
    assert resp.status_code == 200
    bets = resp.json()
    assert len(bets) == 1
    assert bets[0]["ticker"] == "KXATPMATCH-OPEN"

    # These are mock rows, so is_live is False. The summary defaults to LIVE
    # for the same reason the history table does — the scoreboard must total
    # exactly the rows it lists, not a wider set.
    resp = client.get("/api/v1/bots/sports/performance", params={"user_id": uid})
    assert resp.status_code == 200
    assert resp.json()["trades"] == 0, "paper rows must not reach the live scoreboard"

    resp = client.get(
        "/api/v1/bots/sports/performance", params={"user_id": uid, "mode": "all"}
    )
    assert resp.status_code == 200
    perf = resp.json()
    assert perf["trades"] == 3
    assert perf["wins"] == 1
    assert perf["losses"] == 1
    assert perf["win_rate"] == 0.5
    assert perf["total_pnl_usd"] == 6.0

    # ...and asking for paper explicitly finds the same rows.
    resp = client.get(
        "/api/v1/bots/sports/performance", params={"user_id": uid, "mode": "paper"}
    )
    assert resp.json()["trades"] == 3


def test_btc_trades_endpoint(client, user):
    uid = user["user_id"]
    client.post(f"/api/v1/users/{uid}/trades", json=_mock_trade(bot_key="btc15"))
    client.post(f"/api/v1/users/{uid}/trades", json=_mock_trade(bot_key="btc60"))

    # the ledger defaults to LIVE only, and _mock_trade is paper
    resp = client.get("/api/v1/bots/btc/trades", params={"user_id": uid})
    assert resp.status_code == 200
    assert resp.json()["total"] == 0

    resp = client.get("/api/v1/bots/btc/trades", params={"user_id": uid, "mode": "all"})
    assert resp.json()["total"] == 2

    resp = client.get(
        "/api/v1/bots/btc/trades", params={"user_id": uid, "bot": "btc60", "mode": "all"}
    )
    assert resp.json()["total"] == 1


def test_csv_sync_ingests_sports_history(client, user, user_folder):
    # Legacy sports CSV: OPEN row then in-place CLOSED update on re-sync.
    csv_path = user_folder / "trade_history" / "trade_history_sports.csv"
    header = (
        "ts_epoch,ts,ticker,player,situation,confidence,reason,set_num,"
        "signal_bid,buy_price,fill_price,contracts,tp_price,pv_entry,status,"
        "ts_close,pv_close,realized_pnl,pv_delta_pct"
    )
    open_row = (
        "1783482910.30,2026-07-07 22:55:10 CST,KXITFMATCH-26JUL07-CHE,Xing Dao Chen,"
        "E,high,double-break,2,52,57,54,50,68,378.25,OPEN,,,,"
    )
    csv_path.write_text(f"{header}\n{open_row}\n", encoding="utf-8")

    uid = user["user_id"]
    resp = client.post("/api/v1/bots/sports/sync-trades", params={"user_id": uid})
    assert resp.status_code == 200, resp.text
    assert resp.json()["inserted"] == 1

    resp = client.get("/api/v1/bots/sports/trades", params={"user_id": uid})
    assert resp.json()["items"][0]["status"] == "open"

    closed_row = open_row.replace("OPEN,,,,", "CLOSED,2026-07-07 23:50:32,401.25,50.0,6.08")
    csv_path.write_text(f"{header}\n{closed_row}\n", encoding="utf-8")
    resp = client.post("/api/v1/bots/sports/sync-trades", params={"user_id": uid})
    assert resp.json()["updated"] == 1
    assert resp.json()["inserted"] == 0

    resp = client.get("/api/v1/bots/sports/trades", params={"user_id": uid})
    item = resp.json()["items"][0]
    assert item["status"] == "won"
    assert item["pnl_usd"] == 50.0
