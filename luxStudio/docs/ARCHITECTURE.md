# LUX Studio — Technical Architecture

> **Canonical reference for any code change.** Read this before touching code.
> Practical guides for each layer live in `development.md` (back-end, front-end,
> setup, recipes) and `data_model.md` (schema, catalog, migrations).

## 1. System overview

```
┌───────────────────────────────────────────────────────────────────────┐
│                              Browser                                   │
│  React 18 SPA  ·  Vite dev / nginx prod  ·  Tailwind                  │
│  Three.js (3D)  ·  Konva (2D)  ·  Zustand (state)                     │
└───────────────────────────────────────────────────────────────────────┘
                              ▲  JSON over HTTP (Bearer JWT)
                              ▼
┌───────────────────────────────────────────────────────────────────────┐
│                       FastAPI backend  :8750                           │
│  Routers → Services → Calculation engine → Repositories               │
│  PostgreSQL · LDT files (backend/ldt/) · PDF/Excel generators         │
│  JWT auth · i18n (es/en)                                              │
└───────────────────────────────────────────────────────────────────────┘
```

The frontend never holds business logic: submits a `CalculationConfig`, receives
a `CalculationResult`, and renders. Anything requiring photometric math,
validation against EN 13201, or document generation goes through the backend.

## 2. Layered model

**Code in an inner layer must never import from an outer layer.**

```
HTTP layer:       app/main.py + app/routers/*.py     ← validate I/O, auth
Service layer:    app/services/*.py                   ← business rules, orchestration
Domain layer:     app/salvi_lighting/*.py             ← pure photometric math, no I/O
Persistence:      app/database.py + app/models/*.py   ← SQLAlchemy + ORM
```

- **Routers** know about HTTP. They convert request bodies to Pydantic, call
  services, shape responses. No math.
- **Services** orchestrate the domain. Accept Pydantic models, talk to domain
  layer and repositories. No HTTP.
- **`salvi_lighting`** is pure math. No DB, no HTTP, no I/O. Easiest layer to
  unit-test.
- **Models** are SQLAlchemy ORM classes. Single source of truth for columns.

Services receive and return Pydantic models. Routers map Pydantic ↔ HTTP.
Repositories (future) return ORM models and services convert to Pydantic.

## 3. Data flow for a calculation

```
React         1. user edits panels → useConfigStore.setX(...)
 FastAPI      2. POST /api/calculate { config }
   calculator 3. resolve ldt_id (ldt_matcher.py)
   loader     4. load photometry (lru_cache 128)
   calculator 5. flux scaling (power/CCT/CRI → target flux)
   calc.py    6. evaluate(cfg, photometry, flux_scale, road)
                  → { Lavg, Uo, Ul, TI, SR, ok_*, compliant, mode }
   calculator 7. wrap into CalculationResult Pydantic
React         8. JSON response → store.results → panels/canvas re-render
```

The same flow applies to optimize (simple/advanced) and batch-excel — see
`calculation_engine.md`.

## 4. Auth flow

- HS256 JWT in `Authorization: Bearer <token>`. 12 h TTL. `AUTH_SECRET_KEY` env.
- Token payload: `{ sub, email, role, iat, exp }`.
- Dependencies in `routers/auth.py`:
  - `current_user` — requires valid token → User (401 if missing/invalid/inactive)
  - `require_admin` — current_user + role == "ADMIN" (403 otherwise)
- `ensure_initial_admin` runs on app startup; if `users` is empty, seeds from
  `ADMIN_EMAIL` / `ADMIN_PASSWORD` / `ADMIN_NAME` env vars.
- Bypassed routes: `/api/health`, `/api/auth/login`, `/docs`, `/openapi.json`.

## 5. Luminaire selection flow

1. FE loads dimensions from `/api/ldt/catalog` and `/api/admin/gamas`, etc.
2. User cascading selects: **Gama → Difusor → Lente → LED Type**. Each
   selection filters available options via `valid_combinations`.
3. Selected 4-tuple identifies reference LDT(s). First match is calc base.
4. `power`, `cct`, `cri` are free parameters. CRI: 70/80/90, default 70.
5. The slider and numeric input always share the same state.
6. An external `.ldt` can be uploaded for the current session only — it does
   **not** persist in the catalog.
7. When external LDT is active, `power` and `cct` are locked (uses file-as-is).

## 6. Key invariants (do not break)

1. **The DB is the only source of truth for the catalog.** No code may scan
   `backend/ldt/` at startup. LDTs reachable only through `Fotometria` rows.
2. **`ldt_id` is a string** in Pydantic but `str(lum.id)` in DB. `temp-…`
   prefix = session-local LDT (never persisted).
3. **`Photometry` is process-cached** with `lru_cache(128)`. After updating
   the catalog, call `ldt_loader.refresh_ldt_cache()`.
4. **`CalculationConfig` is the only FE↔calc contract.** Pydantic aliases
   (`armLength`, `armTiltAngle`) accepted for backward compat.
5. **Pole offset**: positive `pole_offset` moves pole away from carriageway,
   so effective overhang = `arm_projection - pole_offset`. Same geometry for
   all calculations.
6. **i18n is two parallel dicts** (`services/i18n.py` + `frontend/i18n.tsx`).
   Not auto-synced; add keys to both in the same commit.
7. **Config/result JSON on `Tramo` is opaque** to the backend — preserved for
   client-side state restore. Not read by backend code.
8. **`ldt_id` starting with `temp-`** bypasses the power cap (user uploaded
   the file and explicitly accepts the result).

## 7. Optimization design

| Aspect | v1 Simple | v1 Advanced |
|---|---|---|
| Endpoint | `POST /api/optimize/simple` | `POST /api/optimize/advanced` |
| Objective | Min power (1–500 W, bisection, 0.1 W precision) | `Closest to limits` / `Lowest power` / `Maximum spacing` |
| Variables | Power only | Power (always free) + spacing/height/optic_family (unlockable) |
| Road geometry | Fixed | Fixed |
| External LDTs | Not optimised (calculated as-is) | Same |
| Optic sweep | — | `advanced-batch` returns one row per lens |

The simple optimizer halves power until non-compliant, then binary-searches
between bounds. Nudges up if rounding makes it just non-compliant.

The advanced optimizer does a Cartesian product over unlocked variables
(spacing, height, arm, tilt) with power bisection per cell. Score function
(`_advanced_score`) depends on objective:
- `technical_limits`: Σ(margin²), max margin, total movement
- `min_power`: power, power/spacing, movement
- `max_spacing`: -spacing, power/spacing, power

## 8. Extension points

| You want to… | Touch this | Don't touch |
|---|---|---|
| Add a new EN 13201 criterion | `salvi_lighting/calc.py`, `calculator.py`, schema `CriterionResult`, i18n | routers |
| Add luminaire metadata field | `models/luminaire.py`, admin service/router, frontend type | `salvi_lighting/` |
| Add dimension table | `models/catalog.py`, `routers/catalog.py`, catalog service, admin UI | fotometrias model |
| Add optimisation variable | `schemas/models.py`, `routers/calculate.py`, frontend panel | `salvi_lighting/` |
| Add optimization objective | `schemas/models.py`, `routers/calculate.py`, i18n keys | domain layer |
| Add report section | `pdf_generator.py` + `report.html` + i18n | result shape |
| Add HTTP endpoint | `routers/<resource>.py`, register in `main.py`, mirror types | `salvi_lighting/` |
| Add panel in studio UI | `components/panels/`, drop into editor page | backend |
| Change DB schema | new Alembic migration, update ORM, regenerate requirements | routers |
| Add language | add to both `services/i18n.py` and `frontend/i18n.tsx` | Language literal |

## 9. Configuration

| Var | Where | Default | Notes |
|---|---|---|---|
| `AUTH_SECRET_KEY` | `services/auth.py` | `"lux-studio-local-dev-secret-change-me"` | **Change in production** |
| `ADMIN_EMAIL` | `services/auth.py` | `admin@salvi.lighting` | first startup only |
| `ADMIN_PASSWORD` | `services/auth.py` | `Admin123!` | first startup only |
| `ADMIN_NAME` | `services/auth.py` | `Admin SALVI` | first startup only |
| `DATABASE_URL` | `app/database.py` | local PostgreSQL URL | SQLAlchemy PostgreSQL connection |

Backend: `0.0.0.0:8750`. Frontend dev: `:5173` (proxies `/api/*` to backend).
Docker: nginx proxies `/api/*` to backend container.

## 10. Glossary

- **LDT (EULUMDAT)** — photometric file format. Parsed by `eulumdat.py`.
- **CIE 140** — road-lighting calculation standard (observer, grid, formulas).
- **EN 13201** — European road lighting standard (M1–M6, P1–P6 classes).
- **CIE 144** — r-table for pavement reflection (R1–R4).
- **Photometry** — in-memory wrapper around parsed LDT (`calc.py:Photometry`).
- **Luminaire** — an instance: photometry + position + orientation + scale.
- **Flux scale** — multiplier applied to reference flux for target power/CCT/CRI.
- **Compliant** — every active EN 13201 criterion passes.

## 11. What is *not* in this architecture (yet)

- Routers call `__table__.create()` on startup (idempotent, dev convenience).
  Migrations not wired into Docker entrypoint.
- `cors allow_origins=["*"]` — fine for dev, lock before public deploy.
- `secret_key` default is committed. Production must inject `AUTH_SECRET_KEY`.
- Backend regression tests live under `backend/tests/`; frontend behavior tests
  live under `frontend/tests/` and run through the npm test scripts.
- No CI / pre-commit hooks.
