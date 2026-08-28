"""Small Keycloak Admin API client used by the protected user-management routes."""
from __future__ import annotations

import logging
import os

import httpx


log = logging.getLogger(__name__)


class KeycloakAdminError(RuntimeError):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _config() -> tuple[str, str, str, str, str]:
    return (
        os.getenv("KEYCLOAK_ADMIN_URL", "http://keycloak:8080").rstrip("/"),
        os.getenv("KEYCLOAK_ADMIN_REALM", "master"),
        os.getenv("KEYCLOAK_USER_REALM", "salvi"),
        os.getenv("KEYCLOAK_ADMIN_USERNAME", "admin"),
        os.getenv("KEYCLOAK_ADMIN_PASSWORD", "admin123"),
    )


async def _admin_token(client: httpx.AsyncClient, base_url: str, admin_realm: str, username: str, password: str) -> str:
    try:
        response = await client.post(
            f"{base_url}/realms/{admin_realm}/protocol/openid-connect/token",
            data={
                "client_id": "admin-cli",
                "username": username,
                "password": password,
                "grant_type": "password",
            },
        )
    except httpx.HTTPError as exc:
        raise KeycloakAdminError(503, "No se puede conectar con Keycloak.") from exc

    if response.status_code != 200:
        raise KeycloakAdminError(503, "No se pudo autenticar el administrador de Keycloak.")
    token = response.json().get("access_token")
    if not token:
        raise KeycloakAdminError(503, "Keycloak no devolvió un token de administración.")
    return token


async def create_user(name: str, email: str, password: str) -> str | None:
    base_url, admin_realm, user_realm, username, admin_password = _config()
    first_name, _, last_name = name.partition(" ")
    last_name = last_name or first_name
    async with httpx.AsyncClient(timeout=10) as client:
        token = await _admin_token(client, base_url, admin_realm, username, admin_password)
        try:
            response = await client.post(
                f"{base_url}/admin/realms/{user_realm}/users",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "username": email,
                    "email": email,
                    "firstName": first_name,
                    "lastName": last_name,
                    "enabled": True,
                    "emailVerified": True,
                    "credentials": [{
                        "type": "password",
                        "value": password,
                        "temporary": False,
                    }],
                },
            )
        except httpx.HTTPError as exc:
            raise KeycloakAdminError(503, "No se puede conectar con Keycloak.") from exc

        if response.status_code == 409:
            raise KeycloakAdminError(409, "Ya existe un usuario con ese email.")
        if response.status_code not in (200, 201, 204):
            raise KeycloakAdminError(503, "Keycloak no pudo crear el usuario.")

        location = response.headers.get("location", "")
        return location.rsplit("/", 1)[-1] if location else None


async def delete_user(user_id: str) -> None:
    """Best-effort rollback when local persistence fails after Keycloak creation."""
    base_url, admin_realm, user_realm, username, admin_password = _config()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            token = await _admin_token(client, base_url, admin_realm, username, admin_password)
            response = await client.delete(
                f"{base_url}/admin/realms/{user_realm}/users/{user_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            if response.status_code not in (204, 404):
                log.warning("Could not roll back Keycloak user %s (HTTP %s)", user_id, response.status_code)
    except Exception:
        log.exception("Could not roll back Keycloak user %s", user_id)
