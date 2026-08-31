from __future__ import annotations

from pathlib import Path


def test_create_and_list_users(client, user_folder):
    resp = client.post(
        "/api/v1/users",
        json={
            "username": "sampath",
            "email": "sampath@example.com",
            "user_root_folder": str(user_folder),
        },
    )
    assert resp.status_code == 201
    created = resp.json()
    assert created["username"] == "sampath"
    assert created["user_id"]
    assert created["root_folder_exists"] is True

    resp = client.get("/api/v1/users")
    assert resp.status_code == 200
    users = resp.json()
    assert len(users) == 1
    assert users[0]["username"] == "sampath"


def test_duplicate_username_rejected(client, user_folder):
    body = {"username": "dupe", "user_root_folder": str(user_folder)}
    assert client.post("/api/v1/users", json=body).status_code == 201
    assert client.post("/api/v1/users", json=body).status_code == 409


def test_get_missing_user_404(client):
    assert client.get("/api/v1/users/does-not-exist").status_code == 404


def test_windows_path_canonicalized(client, user_folder):
    # Windows notation in, canonical forward-slash form stored.
    win_style = str(user_folder).replace("/", "\\")
    resp = client.post(
        "/api/v1/users",
        json={"username": "winuser", "user_root_folder": win_style},
    )
    assert resp.status_code == 201
    assert "\\" not in resp.json()["user_root_folder"]


def test_posix_path_accepted_but_flagged_missing(client):
    resp = client.post(
        "/api/v1/users",
        json={"username": "linuxuser", "user_root_folder": "/home/linuxuser/secrets"},
    )
    assert resp.status_code == 201
    assert resp.json()["root_folder_exists"] is False


def test_nonexistent_folder_flagged(client, tmp_path: Path):
    resp = client.post(
        "/api/v1/users",
        json={"username": "ghost", "user_root_folder": str(tmp_path / "nope")},
    )
    assert resp.status_code == 201
    assert resp.json()["root_folder_exists"] is False
