from __future__ import annotations

from pathlib import Path


def test_kalshi_client_fails_dependency_without_env(client, user):
    """User folder has no .env -> 424 with a clear message, no crash."""
    resp = client.post(f"/api/v1/users/{user['user_id']}/kalshi-client")
    assert resp.status_code == 424
    assert ".env" in resp.json()["detail"]


def test_kalshi_client_bad_pem_rejected(client, tmp_path: Path):
    folder = tmp_path / "creds"
    folder.mkdir()
    (folder / ".env").write_text(
        "KALSHI_API_KEY_ID=00000000-0000-0000-0000-000000000000\n"
        "KALSHI_PRIVATE_KEY=kalshi_private.pem\n",
        encoding="utf-8",
    )
    (folder / "kalshi_private.pem").write_text("not a real pem", encoding="utf-8")
    resp = client.post(
        "/api/v1/users",
        json={"username": "badpem", "user_root_folder": str(folder)},
    )
    uid = resp.json()["user_id"]
    resp = client.post(f"/api/v1/users/{uid}/kalshi-client")
    assert resp.status_code == 422
    assert "PEM" in resp.json()["detail"] or "key" in resp.json()["detail"].lower()


def test_verify_password_against_sam(client, user):
    uid = user["user_id"]
    ok = client.post(
        f"/api/v1/users/{uid}/verify-password", json={"password": "test-pass-123"}
    )
    assert ok.status_code == 200
    assert ok.json()["verified"] is True

    bad = client.post(
        f"/api/v1/users/{uid}/verify-password", json={"password": "wrong"}
    )
    assert bad.status_code == 401
