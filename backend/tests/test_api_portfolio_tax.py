from datetime import timedelta

from tests.helpers import add_index, add_stock, last_date


def test_portfolio_fifo_pnl_charges_tax_flow(auth_client, db):
    add_stock(db, "ABC", n=300)
    add_index(db, n=300)
    d = last_date(db)
    pid = auth_client.post("/api/portfolios", json={"name": "Main"}).json()["id"]
    # Two buys then a partial sell (FIFO consumes the first lot).
    for qty, price, day in ((100, 400, 200), (100, 440, 150)):
        r = auth_client.post(f"/api/portfolios/{pid}/transactions", json={
            "symbol": "ABC", "side": "BUY", "quantity": qty, "price": price,
            "trade_date": str(d - timedelta(days=day))})
        assert r.status_code == 201, r.text
    r = auth_client.post(f"/api/portfolios/{pid}/transactions", json={
        "symbol": "ABC", "side": "SELL", "quantity": 50, "price": 480, "trade_date": str(d - timedelta(days=10))})
    assert r.status_code == 201, r.text
    h = auth_client.get(f"/api/portfolios/{pid}").json()
    pos = h["positions"][0]
    assert pos["quantity"] == 150
    # Remaining lots: 50 @ 400 + 100 @ 440 → avg 426.67
    assert abs(pos["avg_cost"] - 426.6667) < 0.01
    assert pos["price_kind"] == "eod_close" and pos["price_as_of"]
    for k in ("gross_pnl", "est_exit_charges", "est_tax_if_sold", "net_pnl"):
        assert k in pos
    assert pos["monitor"]["action"] in ("HOLD", "ADD ONLY ON DIP", "PARTIAL PROFIT", "TRAIL STOP", "EXIT", "WAIT")
    assert h["labels"]["tax"] == "ESTIMATED"
    rl = auth_client.get(f"/api/portfolios/{pid}/realized").json()
    if rl["lines"]:  # sale within current FY
        line = rl["lines"][0]
        assert line["term"] == "STCG" and float(line["quantity"]) == 50
    # Oversell rejected
    r = auth_client.post(f"/api/portfolios/{pid}/transactions", json={
        "symbol": "ABC", "side": "SELL", "quantity": 1000, "price": 480, "trade_date": str(d)})
    assert r.status_code == 422
    # Tax center works and is labelled
    t = auth_client.get("/api/tax/summary").json()
    assert t["label"] == "ESTIMATED" and "disclaimer" in t
    assert auth_client.get("/api/portfolio/dashboard").status_code == 200
    assert auth_client.get("/api/portfolio/exits").status_code == 200
    assert auth_client.get("/api/tax/harvesting").status_code == 200


def test_future_trade_date_rejected(auth_client, db):
    add_stock(db, "ABC", n=50)
    pid = auth_client.post("/api/portfolios", json={"name": "Main"}).json()["id"]
    r = auth_client.post(f"/api/portfolios/{pid}/transactions", json={
        "symbol": "ABC", "side": "BUY", "quantity": 1, "price": 10, "trade_date": "2999-01-01"})
    assert r.status_code == 422


def test_other_users_portfolio_hidden(auth_client, db):
    from app.models import Portfolio, User

    u = User(email="x@example.com", password_hash="x", role="user")
    db.add(u)
    db.flush()
    p = Portfolio(user_id=u.id, name="theirs", kind="live")
    db.add(p)
    db.commit()
    assert auth_client.get(f"/api/portfolios/{p.id}").status_code == 404


def test_tools(auth_client):
    r = auth_client.post("/api/tools/position-size", json={"capital": 1000000, "risk_pct": 1, "entry": 1240,
                                                           "stop": 1190, "targets": [1290, 1340]})
    assert r.json()["quantity"] == 200
    r = auth_client.post("/api/tools/charges", json={"side": "BUY", "quantity": 100, "price": 1000,
                                                     "trade_date": "2026-09-01"})
    body = r.json()
    assert r.status_code == 200 and float(body["stt"]) == 100.0  # 0.1% of ₹1,00,000
