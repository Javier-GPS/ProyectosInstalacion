from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from app.routers.users import CreateUserBody
from app.services import keycloak_admin


def test_create_user_body_normalizes_email_and_rejects_short_password():
    body = CreateUserBody(name=" Ana ", email=" ANA@Example.COM ", password="12345678")
    assert body.name == "Ana"
    assert body.email == "ana@example.com"

    with pytest.raises(ValidationError):
        CreateUserBody(name="Ana", email="ana@example.com", password="short")


def test_keycloak_create_user_sends_non_temporary_password(monkeypatch):
    calls: list[dict] = []

    class Response:
        def __init__(self, status_code: int, payload: dict | None = None, headers: dict | None = None):
            self.status_code = status_code
            self._payload = payload or {}
            self.headers = headers or {}

        def json(self):
            return self._payload

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, **kwargs):
            calls.append({"url": url, **kwargs})
            if url.endswith("/token"):
                return Response(200, {"access_token": "admin-token"})
            return Response(201, headers={"location": "http://keycloak.test/admin/realms/salvi/users/user-1"})

    monkeypatch.setattr(keycloak_admin.httpx, "AsyncClient", Client)
    monkeypatch.setenv("KEYCLOAK_ADMIN_URL", "http://keycloak.test")

    user_id = asyncio.run(keycloak_admin.create_user("Ana", "ana@example.com", "12345678"))

    assert user_id == "user-1"
    assert calls[1]["url"].endswith("/admin/realms/salvi/users")
    assert calls[1]["json"]["firstName"] == "Ana"
    assert calls[1]["json"]["lastName"] == "Ana"
    assert calls[1]["json"]["emailVerified"] is True
    assert calls[1]["json"]["credentials"][0]["temporary"] is False
