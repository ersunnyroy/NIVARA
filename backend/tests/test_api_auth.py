def test_first_run_registration_then_closed(client):
    assert client.get("/api/auth/status").json()["registration_open"] is True
    r = client.post("/api/auth/register", json={"email": "a@example.com", "password": "Sup3rSecretPw"})
    assert r.status_code == 201
    assert client.get("/api/auth/me").json()["role"] == "admin"
    r2 = client.post("/api/auth/register", json={"email": "b@example.com", "password": "Sup3rSecretPw"})
    assert r2.status_code == 403


def test_weak_password_rejected(client):
    r = client.post("/api/auth/register", json={"email": "a@example.com", "password": "short"})
    assert r.status_code == 422


def test_csrf_required_for_cookie_mutations(auth_client):
    csrf = auth_client.headers.pop("x-csrf-token")
    r = auth_client.post("/api/portfolios", json={"name": "Main"})
    assert r.status_code == 403
    auth_client.headers["x-csrf-token"] = csrf
    assert auth_client.post("/api/portfolios", json={"name": "Main"}).status_code == 201


def test_login_logout_and_revocation(auth_client):
    auth_client.post("/api/auth/logout")
    assert auth_client.get("/api/auth/me").status_code == 401
    r = auth_client.post("/api/auth/login", json={"email": "admin@example.com", "password": "wrong-Passw0rd"})
    assert r.status_code == 401
    r = auth_client.post("/api/auth/login", json={"email": "admin@example.com", "password": "Sup3rSecretPw"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    auth_client.cookies.clear()
    r = auth_client.get("/api/auth/me", headers={"authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_login_rate_limited(client):
    client.post("/api/auth/register", json={"email": "a@example.com", "password": "Sup3rSecretPw"})
    codes = [client.post("/api/auth/login", json={"email": "a@example.com", "password": "nope-Nope1"}).status_code
             for _ in range(12)]
    assert 429 in codes


def test_protected_routes_require_auth(client):
    for path in ("/api/market/overview", "/api/opportunities", "/api/portfolios", "/api/tax/summary"):
        assert client.get(path).status_code == 401, path


def test_admin_only(auth_client):
    from app.core.db import SessionLocal
    from app.core.security import hash_password
    from app.models import User

    s = SessionLocal()
    s.add(User(email="u@example.com", password_hash=hash_password("Sup3rSecretPw"), role="user"))
    s.commit()
    s.close()
    auth_client.cookies.clear()
    r = auth_client.post("/api/auth/login", json={"email": "u@example.com", "password": "Sup3rSecretPw"})
    auth_client.headers["x-csrf-token"] = r.json()["csrf_token"]
    assert auth_client.get("/api/admin/system-health").status_code == 403
    assert auth_client.put("/api/settings/scoring_weights", json={"technical": 30}).status_code == 403
