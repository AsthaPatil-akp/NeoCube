import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.main import app
from app.models import User


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def register_payload(**overrides):
    data = {
        "email": "client@example.com",
        "password": "password123",
        "role": "CLIENT",
        "full_name": "Ada Client",
        "company_name": "Ada Co",
        "phone": "555-0100",
    }
    data.update(overrides)
    return data


def test_register_client(client):
    response = client.post("/auth/register", json=register_payload())
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "client@example.com"
    assert body["role"] == "CLIENT"
    assert body["full_name"] == "Ada Client"
    assert body["company_name"] == "Ada Co"
    assert "password" not in body
    assert "password_hash" not in body


def test_register_supplier(client):
    response = client.post(
        "/auth/register",
        json=register_payload(email="supplier@example.com", role="SUPPLIER", full_name="Sam Supplier"),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "SUPPLIER"
    assert body["email"] == "supplier@example.com"


def test_duplicate_email(client):
    payload = register_payload(email="dup@example.com")
    assert client.post("/auth/register", json=payload).status_code == 201
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 409
    assert response.json()["detail"] == "Email already registered"


def test_invalid_email(client):
    response = client.post("/auth/register", json=register_payload(email="not-an-email"))
    assert response.status_code == 422


def test_invalid_role(client):
    response = client.post("/auth/register", json=register_payload(email="role@example.com", role="MANAGER"))
    assert response.status_code == 422


def test_admin_registration_rejected(client):
    response = client.post("/auth/register", json=register_payload(email="admin@example.com", role="ADMIN"))
    assert response.status_code == 422


def test_short_password(client):
    response = client.post("/auth/register", json=register_payload(email="short@example.com", password="short"))
    assert response.status_code == 422


def test_login_success_and_session(client):
    client.post("/auth/register", json=register_payload(email="login@example.com"))
    response = client.post(
        "/auth/login",
        json={"email": "login@example.com", "password": "password123"},
    )
    assert response.status_code == 200
    assert response.json()["email"] == "login@example.com"
    me = client.get("/users/me")
    assert me.status_code == 200
    assert me.json()["email"] == "login@example.com"
    assert me.json()["role"] == "CLIENT"


def test_login_wrong_password(client):
    client.post("/auth/register", json=register_payload(email="wrongpass@example.com"))
    response = client.post(
        "/auth/login",
        json={"email": "wrongpass@example.com", "password": "incorrect1"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_login_unknown_account(client):
    response = client.post(
        "/auth/login",
        json={"email": "missing@example.com", "password": "password123"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_me_unauthenticated(client):
    response = client.get("/users/me")
    assert response.status_code == 401


def test_profile_update_own_record_only(client):
    client.post("/auth/register", json=register_payload(email="owner@example.com", full_name="Owner One"))
    client.post("/auth/register", json=register_payload(email="other@example.com", full_name="Other User"))

    client.post("/auth/login", json={"email": "owner@example.com", "password": "password123"})
    updated = client.put(
        "/users/me",
        json={"full_name": "Owner Updated", "company_name": "New Co", "phone": "111"},
    )
    assert updated.status_code == 200
    assert updated.json()["full_name"] == "Owner Updated"
    assert updated.json()["company_name"] == "New Co"
    assert updated.json()["email"] == "owner@example.com"

    client.post("/auth/logout")
    client.post("/auth/login", json={"email": "other@example.com", "password": "password123"})
    assert client.get("/users/me").json()["full_name"] == "Other User"


def test_profile_update_cannot_change_role_or_email(client):
    client.post("/auth/register", json=register_payload(email="locked@example.com"))
    client.post("/auth/login", json={"email": "locked@example.com", "password": "password123"})
    response = client.put(
        "/users/me",
        json={"email": "hacker@example.com", "role": "ADMIN", "password_hash": "x"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "locked@example.com"
    assert body["role"] == "CLIENT"


TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


def test_profile_photo_upload_and_fetch(client):
    client.post("/auth/register", json=register_payload(email="photo@example.com"))
    client.post("/auth/login", json={"email": "photo@example.com", "password": "password123"})
    assert client.get("/users/me/photo").status_code == 404
    assert client.get("/users/me").json()["profile_photo_url"] is None

    uploaded = client.post("/users/me/photo", files={"file": ("avatar.png", TINY_PNG, "image/png")})
    assert uploaded.status_code == 200
    url = uploaded.json()["profile_photo_url"]
    assert url.startswith("/users/me/photo")

    photo = client.get("/users/me/photo")
    assert photo.status_code == 200
    assert photo.headers["content-type"].startswith("image/")
    assert photo.content.startswith(b"\x89PNG")


def test_profile_photo_rejects_non_image(client):
    client.post("/auth/register", json=register_payload(email="nophoto@example.com"))
    client.post("/auth/login", json={"email": "nophoto@example.com", "password": "password123"})
    response = client.post("/users/me/photo", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert response.status_code == 400


def test_put_me_unauthenticated(client):
    response = client.put("/users/me", json={"full_name": "Nope"})
    assert response.status_code == 401


def test_logout_clears_session(client):
    client.post("/auth/register", json=register_payload(email="logout@example.com"))
    client.post("/auth/login", json={"email": "logout@example.com", "password": "password123"})
    assert client.get("/users/me").status_code == 200

    response = client.post("/auth/logout")
    assert response.status_code == 204
    assert client.get("/users/me").status_code == 401


def test_inactive_account_cannot_login(client):
    created = client.post("/auth/register", json=register_payload(email="inactive@example.com"))
    user_id = created.json()["id"]

    db: Session = SessionLocal()
    try:
        user = db.get(User, user_id)
        user.is_active = False
        db.commit()
    finally:
        db.close()

    response = client.post(
        "/auth/login",
        json={"email": "inactive@example.com", "password": "password123"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Account is inactive"
