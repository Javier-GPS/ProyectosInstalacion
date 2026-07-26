# SALVI Portal

Portal común para acceder a LUX Studio y GISVial con una única sesión de
Keycloak.

## Arranque

Desde `C:\Github\estudiosLuminicos`:

```bash
docker compose up --build
```

Accesos:

- `http://localhost` — entrada por el gateway.
- `http://localhost:3000` — entrada directa al portal.

El usuario inicial del realm local es `admin@salvi.lighting` con contraseña
`Admin123!`. Debe cambiarse antes de usar el sistema fuera de desarrollo.

Si el realm `salvi` ya estaba creado en un volumen de Keycloak, el cliente
`portal` debe existir en ese realm. El fichero `auth/realm.json` lo crea en una
instalación nueva; en una instalación existente se puede importar o crear como
cliente público con flujo de credenciales directas habilitado.

Las URLs visibles desde el navegador se configuran con
`PUBLIC_KEYCLOAK_URL`, `PUBLIC_LUXSTUDIO_URL` y `PUBLIC_GISVIAL_URL` en `.env`.
