# Development Guide

> Read `architecture.md` first. This file is the practical reference: setup,
> module guide, conventions, recipes, deployment, troubleshooting.

## 1. Local setup

### Backend
```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate  |  Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8750
```
The backend requires PostgreSQL through `DATABASE_URL`. Docker creates the
database volume and loads the local PostgreSQL-native seed on its first boot.
If the seed has no users, startup creates the admin from env vars (defaults:
`admin@salvi.lighting` / `Admin123!` / `Admin SALVI`).

### Frontend
```bash
cd frontend
npm install
npm run dev    # http://localhost:5173, proxies /api to :8750
```

### Docker
```bash
docker compose up --build
# backend :8750, frontend :5173
```

## 2. Scripts

| Where | Command | What it does |
|---|---|---|
| `backend/` | `uvicorn app.main:app --reload` | Dev server with hot reload |
| `backend/` | `alembic revision --autogenerate -m "..."` | Generate migration |
| `backend/` | `alembic upgrade head` | Apply migrations |
| `backend/` | `alembic downgrade -1` | Roll back one step |
| `backend/` | `python scripts/import_bbdd_fotometrias.py` | Import `BBDD_Fotometrias.xlsx` into dimension tables |
| `backend/` | `python scripts/migrate_existing_ldts.py` | Parse LDT files → create/update `fotometrias` with FKs |
| `backend/` | `python scripts/import_salvi_leds.py` | UPSERT LED/PCB/driver data from Salvi xlsx |
| `frontend/` | `npm run dev` | Dev server |
| `frontend/` | `npm run build` | Production build → `dist/` |

## 3. Backend module reference

All paths relative to `backend/`.

### Routers

| File | Prefix | Purpose |
|---|---|---|
| `routers/auth.py` | `/api/auth` | Login, me, change-password. Defines `current_user` + `require_admin`. |
| `routers/users.py` | `/api/admin/users` | Admin-only user CRUD. |
| `routers/admin.py` | `/api/admin` | LDT upload/parse/update, list manufacturers. |
| `routers/catalog.py` | `/api/admin/*` | Dimension CRUD (gamas, difusores, lentes, led-types). |
| `routers/ldt.py` | `/api/ldt` | Read-only catalog: list, families, photometric data. |
| `routers/calculate.py` | `/api` | Calculate, optimize/*, batch-excel. |
| `routers/report.py` | `/api/report` | PDF and Excel generation. |
| `routers/projects.py` | `/api/projects` | Project CRUD + documents + duplicate. |
| `routers/tramos.py` | `/api/projects/{pid}/tramos` | Tramo CRUD + documents + duplicate. |

### Services

| File | Responsibility | Key functions |
|---|---|---|
| `services/auth.py` | Password hashing, JWT, seed admin | `hash_password`, `verify_password`, `create_token`, `decode_token`, `ensure_initial_admin` |
| `services/ldt_loader.py` | DB catalog + temp LDTs + photometry cache | `get_ldt_by_id`, `get_photometry` (lru_cache), `save_temporary_ldt` |
| `services/ldt_matcher.py` | Config → ldt_id resolution | `find_ldt_for_config`, `require_ldt_for_config` |
| `services/geometry.py` | Pure geometry helpers | `arm_projection`, `luminaire_mounting_height`, `effective_overhang` |
| `services/calculator.py` | Calc orchestrator | `run_calculation`, `_target_luminaire_info`, `_estimate_flux_for_config` |
| `services/catalog_service.py` | Dimension CRUD | One function per CRUD op × 4 entities |
| `services/i18n.py` | es/en for reports | `translator(lang)`, `SUPPORTED_LANGUAGES` |
| `services/excel_generator.py` | DIALux-style .xlsx | `generate_excel(result, payload)` |
| `services/pdf_generator.py` | WeasyPrint .pdf | `generate_pdf(result, payload)` (uses `templates/report.html`) |
| `services/admin_service.py` | LDT CRUD on DB + filesystem | `parse_ldt_preview`, `create_fotometria`, `update_fotometria`, `delete_fotometria` |
| `services/luminaire_catalog.py` | Power cap (pmax) | `get_pmax_for_selection`, `clamp_power_to_pmax`, `max_power_for_optimizer` |

### Domain layer (`app/salvi_lighting/`)

| File | Exports | Notes |
|---|---|---|
| `eulumdat.py` | `parse_ldt(path) -> dict` | EULUMDAT parser. |
| `r_table.py` | `r_value(tg, beta, road)` | CIE 144 r-table (R1–R4). |
| `calc.py` | `Photometry`, `Luminaire`, `evaluate`, `ME_REQ`, `P_REQ` | Photometric math engine. |
| `solver.py` | `evaluate_row`, `lm_to_W` | Legacy optimizer helpers. |
| `batch.py` | – | Parallel batch runner (ThreadPoolExecutor). |
| `render.py` | – | SVG renderers (polar, plan, section, isolines) for PDF. |

### Persistence

| File | Purpose |
|---|---|
| `app/database.py` | Engine, SessionLocal, get_db(), Base. |
| `app/models/user.py` | User (auth). |
| `app/models/project.py` | Project + ProjectDocument (legacy). |
| `app/models/tramo.py` | Tramo + TramoDocument (current working unit). |
| `app/models/luminaire.py` | Manufacturer + Fotometria. |
| `app/models/catalog.py` | Gama, Difusor, Lente, LedType, ValidCombination, LED, PCB, Driver, LuminaireLED. |

### Flux estimation (calculator.py)

`_target_luminaire_info` is the most subtle piece:

1. If `config.power ≈ photometry.power` (within 1%): use `photometry.flux` × CCT/CRI factor.
2. Otherwise: interpolate across sibling DB records sharing `(manufacturer, model_family, optic_family, cri)`.
3. If no siblings: power-law extrapolation (`POWER_LAW_EXPONENT = 0.832`).
4. Always apply CCT/CRI scaling via `_led_flux_factor` and `LUXEON_5050_CRI_FLUX` table.

When FE sends the 4-tuple (`gama`, `difusor`, `lente`, `led_type`), the engine
scales selected LDT linearly to `config.power` then applies CCT/CRI. The sibling
interpolation path is kept for legacy requests without the 4-tuple.

## 4. Frontend module reference

All paths relative to `frontend/src/`.

### Entry & routing
```
main.tsx          → <AuthProvider><I18nProvider><App/>
App.tsx           → Routes only (login gate, MainLayout wrapper)
auth/AuthContext   → JWT login/logout/changePassword/authFetch
store/useConfigStore → Zustand: CalculationConfig + results + dirty tracking
i18n.tsx           → useI18n hook + es/en tables
```

| Route | Component | Access |
|---|---|---|
| `/` | Redirect → `/projects` | Authenticated |
| `/projects` | `ProjectsListPage` | Authenticated |
| `/projects/:id` | `ProjectTramosPage` | Authenticated + owner/admin |
| `/projects/:pid/tramos/:tid` | `TramoEditorPage` | Authenticated |
| `/admin` | `AdminPage` | ADMIN only |
| `/users` | `AdminUsersPage` | ADMIN only |

### Key components

| Component | What it does |
|---|---|
| `panels/GeometryPanel` | Road width, sidewalks, lanes, arrangement, class, pavement, MF |
| `panels/ArrangementPanel` | Height, spacing, arm, tilt, pole offset, pole side |
| `panels/LuminairePanel` | Catalog cascading selects + external LDT upload + power cap |
| `panels/AutoOptimizePanel` | Simple + advanced optimizer UI |
| `panels/ResultsPanel` | Per-calc results + PDF/Excel download |
| `panels/BatchExcelPanel` | DIALux-style .xlsx upload |
| `canvas/RoadPlanView` | 2D plan (Konva) |
| `canvas/RoadSectionView` | 2D cross-section (Konva) |
| `canvas/RoadScene3D` | 3D scene (Three.js) |

### State

`useConfigStore` (Zustand) is the single source of truth. Mirrors
`CalculationConfig` 1:1 plus `results`, `loading`, `error`. Key setters:
`setGeometry`, `setArrangement`, `setLuminaire`, `calculate()`, `reset()`.

`dirty: boolean` tracks unsaved changes. `lastSavedSnapshot` + `lastEditedTramoId`
support the unsaved-changes guard (`useUnsavedChangesGuard` hook).

### Types (`types/index.ts`)

Mirrors backend Pydantic schemas. Notable: `FotometriaInfo`, `CalculationResult`,
`OptimizationResponse`, `AdvancedOptimization*`, `ArrangementType`,
`LightingClass`, `PavementType`, `PoleSide`, catalog dimension types.

### Auth helpers

- `useAuth().authFetch(url, opts)` injects Bearer token. Use for all
  authenticated calls.
- For `/api/projects/*`: prefer `lib/projects.ts` helpers over raw authFetch
  (typed, one-liners).
- For `/api/projects/*/tramos/*`: use `lib/tramos.ts` helpers.

## 5. Conventions

### Python
- Layered: `routers → services → salvi_lighting`. Inner layers don't import outer.
- Type hints on all function signatures.
- Pydantic v2 for all request/response/service contracts.
- Raise `HTTPException` from routers, `ValueError` from services.
- `strip().upper()` for all catalog dimension comparisons.

### TypeScript
- Single Zustand store (`useConfigStore`). Local UI state via `useState`.
- PascalCase for components, camelCase for setters.
- Dotted lowercase for i18n keys (`results.compliant`).
- Add i18n keys to **both** `es` and `en` in same commit.
- Mirror backend schema changes in `types/index.ts` in same commit.

### Git
- Imperative commit messages ("Add …", "Fix …", "Refactor …").
- Never commit secrets. `AUTH_SECRET_KEY` and `ADMIN_*` come from env.
- Don't push large binary assets (`.ldt` files in production).

## 6. Recipes

### Add a new HTTP endpoint
1. Create `app/routers/<resource>.py` with `APIRouter()`.
2. Register in `app/main.py`.
3. Add Pydantic model in `app/schemas/models.py`.
4. Mirror types in `frontend/src/types/index.ts`.
5. Use `current_user` (or `require_admin`) if auth needed.
6. Add to `docs/api.md`.

### Change DB schema
1. Update ORM class in `app/models/`.
2. Import new model in `alembic/env.py` if new entity.
3. `alembic revision --autogenerate -m "msg"` — review the generated migration.
4. `alembic upgrade head`.
5. Update `frontend/src/types/index.ts` if column exposed.

### Add a new dimension table
1. ORM in `app/models/catalog.py`.
2. Import in `app/models/__init__.py` and `alembic/env.py`.
3. Alembic migration.
4. CRUD service in `app/services/catalog_service.py`.
5. Endpoints in `app/routers/catalog.py` + register in `main.py`.
6. Frontend types + admin UI.

### Add a new EN 13201 criterion
1. Add entry in `salvi_lighting/calc.py` (`ME_REQ` / `P_REQ`).
2. Compute in `evaluate`, set `ok_<name>` in result dict.
3. Update `calculator.py::_build_criteria`.
4. Update `i18n.py` (both `es` and `en`).

### Add a new language
1. Add `'xx'` to `Language` literal in both `frontend/i18n.tsx` and `services/i18n.py`.
2. Add translations dict with every key.
3. Add selector in `layouts/MainLayout.tsx`.

### Add a new panel
1. Create `components/panels/MyPanel.tsx`. Read/write via `useConfigStore`.
2. Drop into editor page sidebar.
3. Extend store and types if new state.

## 7. Testing

No automated test suite yet. Recommended layout:

- `backend/tests/salvi_lighting/` — unit tests (pure Python, synthetic Photometry)
- `backend/tests/services/` — service tests (isolated PostgreSQL schemas, dependency-overrides)
- `backend/tests/api/` — API tests (FastAPI TestClient)
- `frontend/` — Vitest + RTL (no existing tests)

Quick smoke test: `/api/health` + manual login through UI.

## 8. Deployment

### Docker
```bash
docker compose up --build -d
```
Backend: `python:3.12-slim`, uvicorn. Frontend: multi-stage build → nginx.

### Pre-prod checklist
- [ ] Generate strong `AUTH_SECRET_KEY` (don't ship the default)
- [ ] Override `ADMIN_EMAIL` / `ADMIN_PASSWORD` / `ADMIN_NAME`
- [ ] Lock CORS in `app/main.py`
- [x] Persist PostgreSQL and backend-generated data in Docker volumes
- [ ] Wire `alembic upgrade head` into entrypoint
- [ ] Gate `/api/admin/luminaires/*` behind `Depends(require_admin)`
- [ ] Front with HTTPS (nginx / LB)

### Production backlog
- Move document data to S3-compatible storage
- Add queue for long-running batch calculations
- Add CI (lint, type-check, test, build)
- Add pre-commit hooks (ruff, eslint, prettier)
- Add `/api/v1` prefix to all routes
- Structured logging (structlog/loguru)

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Login 401 after seeding | PostgreSQL volume was replaced | Restore the PostgreSQL backup or native seed |
| CORS error | `allow_origins` locked with wrong origin | Add exact origin |
| LDT upload 404 but file exists | File on disk but not in DB | Upload again through admin |
| PDF/Excel timeout | Heavy grid (10 periods × many luminaires) | Reduce S/W for test; long-term: queue |
| Optimizer "no feasible" for valid config | Temp LDT (can't be re-scaled) | Switch to catalog LDT before optimizing |
| Optimizer slow on tall config | Many bisection steps | Reduce `OPTIMIZATION_MAX_POWER` or tighten `OPTIMIZATION_PRECISION` |

## 10. Known code smells (intentional)

- `cors allow_origins=["*"]` — fix before public deploy.
- `services/auth.py` has pbkdf2_sha256 legacy branch for old hashes.
- `Fotometria.cri` defaults to 70 but legacy DBs may have `None` — code
  defensively falls back via `getattr(lum, "cri", 70) or 70`.
- Routers call `__table__.create(checkfirst=True)` at runtime instead of
  relying solely on migrations (dev convenience).
