# HTTP API Reference

> Read `architecture.md` first. All endpoints JSON in/out except report
> endpoints (binary). Base URL: `http://<host>:8750`.

## Conventions
- Authenticated endpoints require `Authorization: Bearer <OIDC access token>` from Keycloak.
- Errors: `{ "detail": "..." }` with 4xx/5xx.
- Tokens are issued by the `salvi` Keycloak realm through the Portal.
- Roles: `"ADMIN"` / `"USER"`.

## Auth & users

| Method | Path | Auth | Body | Response |
|---|---|---|---|---|
| GET | `/api/auth/me` | bearer | – | `UserInfo` |
| POST | `/api/admin/users` | admin | `{ name, email, password }` | `UserInfo` |

`POST /api/admin/users` creates the account in Keycloak and links the local
`users` row to its OIDC identity. The password is managed by Keycloak; the
endpoint never stores it in LuxStudio.

## Luminaire catalog (admin)

| Method | Path | Auth | Body | Response |
|---|---|---|---|---|
| POST | `/api/admin/parse-ldt` | none* | `multipart: file` | parsed fields |
| POST | `/api/admin/luminaires/upload` | none* | `multipart: file + form` | `FotometriaInfo` |
| GET | `/api/admin/luminaires` | none* | – | `FotometriaInfo[]` |
| GET | `/api/admin/luminaires/{id}` | none* | – | `FotometriaInfo` |
| PUT | `/api/admin/luminaires/{id}` | none* | `UpdateLuminaireBody` | `FotometriaInfo` |
| DELETE | `/api/admin/luminaires/{id}` | none* | – | `{ ok }` |
| GET | `/api/admin/manufacturers` | none* | – | `{ id, name }[]` |

> *Admin-only by intent (frontend `/admin` route is protected). Wrap in
> `Depends(require_admin)` before public deploy.

Upload form fields: `file` + `manufacturer`, `model_family`, `optic_family`,
`luminaire_name`, `power`, `cct`, `cri` (default 70), `flux`, `efficiency`,
`LORL`, `isym`.

## Luminaire catalog (read)

| Method | Path | Auth | Response |
|---|---|---|---|
| GET | `/api/ldt/list` | none | `FotometriaInfo[]` |
| GET | `/api/ldt/families` | none | `LDTFamily[]` |
| GET | `/api/ldt/catalog` | none | `FotometriaInfo[]` (full) |
| POST | `/api/ldt/upload` | none | `FotometriaInfo` (temp, id starts with `temp-`) |
| GET | `/api/ldt/{ldt_id}` | none | `FotometriaInfo` |
| GET | `/api/ldt/{ldt_id}/curve` | none | `{ id, gamma, C0, C90, Mc, Ng }` |
| GET | `/api/ldt/{ldt_id}/photometric` | none | full intensity data |

## Dimension tables (catalog admin)

All follow the same CRUD pattern:
- `GET /api/admin/<table>` → `{ id, name }[]`
- `POST /api/admin/<table>` → `{ name }` → `{ id, name }`
- `PUT /api/admin/<table>/{id}` → `{ name }` → `{ id, name }`
- `DELETE /api/admin/<table>/{id}` → `{ ok }`

Tables: `gamas`, `difusores`, `lentes`, `led-types`, `valid-combinations`.
`valid-combinations` POST body: `{ gama_id, difusor_id, lente_id, led_type_id? }`.

## Calculation

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/api/calculate` | `CalculationConfig` | `CalculationResult` |
| POST | `/api/optimize/simple` | `CalculationConfig` | `OptimizationResponse` |
| POST | `/api/optimize/advanced` | `AdvancedOptimizationRequest` | `OptimizationResponse` |
| POST | `/api/optimize/advanced-batch` | `AdvancedOptimizationRequest` | `BatchCalculationResponse` |
| POST | `/api/batch-excel` | `multipart: file` (.xlsx) | `BatchCalculationResponse` |

Pydantic aliases accepted: `arm_length`/`armLength`, `tilt`/`armTiltAngle`.

### `CalculationResult`
```json
{
  "config": {},
  "compliant": true, "mode": "ME",
  "luminaire": {},
  "criteria": [{ "name": "Lavg (cd/m²)", "value": 1.21, "required": 1.0, "passed": true }],
  "Lavg": 1.21, "Uo": 0.46, "Ul": 0.78, "TI": 8.2, "SR": 0.62, "Eavg": null, "Emin": null
}
```

### `OptimizationResponse`
```json
{
  "feasible": true,
  "message": "Potencia minima conforme encontrada: 78.0 W.",
  "checked": 11,
  "config": {}, "result": {}
}
```

### `AdvancedOptimizationRequest`
```json
{
  "config": {},
  "variables": { "power": true, "spacing": false, "height": false },
  "limits": { "power": 200, "spacing": 40, "height": 12 },
  "objective": "technical_limits",
  "optic_families": ["F151", "F2MD"]
}
```

## Reports

| Method | Path | Auth | Response |
|---|---|---|---|
| POST | `/api/report/generate?tramo_id=&project_id=` | none | `application/pdf` |
| POST | `/api/report/excel?tramo_id=&project_id=` | none | `.xlsx` |

Returns `Content-Disposition: attachment`. When `tramo_id` provided, document
stored in `tramo_documents`. `project_id` kept for backward compat.

## Projects

| Method | Path | Auth | Body | Response |
|---|---|---|---|---|
| GET | `/api/projects?owner_user_id=` | bearer | – | `ProjectInfo[]` |
| POST | `/api/projects` | bearer | `ProjectBody` | `ProjectInfo` |
| GET | `/api/projects/{id}` | bearer | – | `ProjectInfo` |
| PUT | `/api/projects/{id}` | bearer | `ProjectBody` | `ProjectInfo` |
| DELETE | `/api/projects/{id}` | bearer | – | `{ ok }` |
| POST | `/api/projects/{id}/duplicate` | bearer | – | `ProjectInfo` |
| GET | `/api/projects/{id}/documents` | bearer | – | `ProjectDocumentInfo[]` |
| GET | `/api/projects/{id}/documents/{did}/download` | bearer | – | binary |

## Tramos

| Method | Path | Auth | Body | Response |
|---|---|---|---|---|
| GET | `/api/projects/{pid}/tramos` | bearer | – | `TramoInfo[]` |
| POST | `/api/projects/{pid}/tramos` | bearer | `TramoBody` | `TramoInfo` |
| GET | `/api/projects/{pid}/tramos/{tid}` | bearer | – | `TramoInfo` |
| PUT | `/api/projects/{pid}/tramos/{tid}` | bearer | `TramoBody` | `TramoInfo` |
| DELETE | `/api/projects/{pid}/tramos/{tid}` | bearer | – | `{ ok }` |
| POST | `/api/projects/{pid}/tramos/{tid}/duplicate` | bearer | – | `TramoInfo` |
| GET | `/api/projects/{pid}/tramos/{tid}/documents` | bearer | – | `TramoDocumentInfo[]` |
| GET | `/api/projects/{pid}/tramos/{tid}/documents/{did}/download` | bearer | – | binary |

`TramoBody`: `{ name?, description?, config_json?, result_json? }`

`TramoInfo` includes `has_pdf`, `has_excel`, `document_ids`, `compliance_summary`.

## Health & meta

| Method | Path | Auth | Response |
|---|---|---|---|
| GET | `/api/health` | none | `{ "status": "ok" }` |

FastAPI at `/docs` (Swagger) and `/openapi.json`.

## CORS
`allow_origins=["*"]` in `app/main.py`. Lock before public deploy.

## Common errors
| Status | When |
|---|---|
| 400 | Malformed body, invalid LDT, password too short |
| 401 | Missing/invalid/expired token, inactive user |
| 403 | Insufficient role, access denied |
| 404 | Resource not found |
| 422 | Pydantic validation |
| 500 | Unexpected (check server logs) |
