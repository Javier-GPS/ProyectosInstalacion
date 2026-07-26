# Data Model & Catalog Reference

> Read `architecture.md` first. This file covers every table, Alembic workflow,
> the photometric catalog model, and the import scripts.

The application database is PostgreSQL. Docker persists it in the
`postgres_data` volume and the backend connects through `DATABASE_URL`.

## 1. Entity relationships

```
manufacturers ──1:N── fotometrias ──FKs── gamas, difusores, lentes, led_types
users         ──1:N── projects ──1:N── tramos
                                    ──1:N── tramo_documents
                        ──1:N── project_documents (legacy, no longer written to)

valid_combinations: FK→gamas, difusores, lentes, led_types (UNIQUE 4-tuple)

leds (*)       ──1:N── luminaire_leds ──N:1── fotometria
pcbs (*)                                        ↑
drivers (*)                                     |
(* = Salvi catalog: LED/PCB/Driver power caps)
```

## 2. Tables

### `manufacturers`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `name` | VARCHAR(100) UNIQUE | |

### `fotometrias`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | exposed as `str(id)` |
| `manufacturer_id` | INTEGER FK → manufacturers | NOT NULL |
| `gama_id` | INTEGER FK → gamas | NULLable (legacy LDTs) |
| `difusor_id` | INTEGER FK → difusores | NOT NULL (`__LEGACY__` for legacy) |
| `lente_id` | INTEGER FK → lentes | NOT NULL |
| `led_type_id` | INTEGER FK → led_types | NULLable |
| `fotometria` | VARCHAR(255) UNIQUE NULL | alias from ENSAYO ORIGEN |
| `photometric_path` | VARCHAR(255) NULL | path relative to `backend/ldt/` |
| `type` | VARCHAR(100) | legacy model family string |
| `optic_family` | VARCHAR(50) | legacy lens code string |
| `name` | VARCHAR(255) | human label |
| `power` | FLOAT | W |
| `cct` | INTEGER | K |
| `cri` | INTEGER DEFAULT 70 | |
| `flux` | FLOAT | lm |
| `efficiency` | FLOAT | lm/W |
| `LORL` | FLOAT | light output ratio (0..1) |
| `isym` | INTEGER | photometric symmetry |
| `ldt_path` | VARCHAR(255) UNIQUE | legacy, renamed to photometric_path |
| `created_at` / `updated_at` | DATETIME | UTC |

### Catalog dimensions
`gamas`, `difusores`, `lentes`, `led_types` — all have `id` (PK) + `name`
(VARCHAR(100) UNIQUE, normalised with `strip().upper()`).

`difusores` has a `__LEGACY__` sentinel row for legacy LDTs whose diffuser
can't be extracted from the filename.

### `valid_combinations`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `gama_id` | INTEGER FK → gamas ON DELETE CASCADE | |
| `difusor_id` | INTEGER FK → difusores ON DELETE CASCADE | |
| `lente_id` | INTEGER FK → lentes ON DELETE CASCADE | |
| `led_type_id` | INTEGER FK → led_types ON DELETE CASCADE | NULL allowed |
| `created_at` | DATETIME | |
| UNIQUE | `(gama_id, difusor_id, lente_id, led_type_id)` | |

### `users`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `company_name` | VARCHAR(100) DEFAULT 'SALVI LIGHTING' | |
| `email` | VARCHAR(255) UNIQUE INDEX | |
| `name` | VARCHAR(255) | |
| `password_hash` | VARCHAR(255) | bcrypt; legacy pbkdf2 accepted |
| `role` | VARCHAR(20) DEFAULT 'USER' | 'ADMIN' \| 'USER' |
| `is_active` | BOOLEAN DEFAULT 1 | |
| `must_reset_password` | BOOLEAN DEFAULT 1 | |
| `last_login_at` | DATETIME NULL | set by `/api/auth/login` |
| + timestamps | | |

### `projects`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `owner_user_id` | INTEGER FK → users | |
| `project_name` | VARCHAR(255) | |
| `client`, `location`, `designer`, `reference` | VARCHAR(255) NULL | |
| `study_date` | VARCHAR(50) NULL | free-form display string |
| `status` | VARCHAR(50) DEFAULT 'draft' | |
| `config_json` | TEXT NULL | opaque client snapshot (legacy) |
| `result_json` | TEXT NULL | opaque client snapshot (legacy) |
| `last_opened_at` | DATETIME NULL | set on GET /projects/{id} |
| + timestamps | | |

### `project_documents` (legacy)
`id`, `project_id` FK, `filename`, `document_type` ('pdf'/'excel'),
`content_type`, `data` (LargeBinary), `created_at`. Not written to anymore.

### `tramos`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `project_id` | INTEGER FK → projects ON DELETE CASCADE | |
| `name` | VARCHAR(255) | editable inline |
| `description` | TEXT NULL | reserved |
| `config_json` | TEXT NULL | opaque snapshot |
| `result_json` | TEXT NULL | opaque snapshot; `compliant` derived here |
| `last_calculated_at` | DATETIME NULL | set automatically on PUT with result_json |
| + timestamps | | |

### `tramo_documents`
Same as `project_documents` but FK → `tramos.id`. Current storage for PDF/Excel.

### Salvi catalog tables (power caps)

`leds`, `pcbs`, `drivers`, `luminaire_leds` — imported from
`Referencias_productos_pcb_go.xlsx`. Source of `pmax_ajustada` (max LED power).
The `luminaire_leds` table maps 4-tuples (via fotometria_id) to LED refs and caps.

## 3. Cascading logic (catalog selection)

When user selects a gama, UI queries `valid_combinations` for that gama and
shows only distinct difusores. Each subsequent selection further filters.
Any change in any dropdown triggers a fresh filter — no assumed order.

Deleting a dimension value that `fotometrias` references is **blocked**
(RESTRICT). Deleting one referenced by `valid_combinations` **cascades**.

## 4. Import workflow

### Step 1: Dimension tables
```bash
cd backend
python scripts/import_bbdd_fotometrias.py
```
Reads `BBDD_Fotometrias.xlsx`, UPSERTs distinct values into gamas/difusores/
lentes/led_types, fills `valid_combinations`. Idempotent. Generates
`fotometria_mapping.csv`. Optional `--xlsx path/to/file.xlsx`.

### Step 2: Migrate existing LDTs
```bash
cd backend
python scripts/migrate_existing_ldts.py
```
Parses `.ldt` files in `backend/ldt/Salvi/`, extracts gama/difusor/lente from
filename, creates/updates `fotometrias` rows with FKs. Idempotent.

### Step 3: LED / PCB / Driver data
```bash
cd backend
python scripts/import_salvi_leds.py
```
Reads `Referencias_productos_pcb_go.xlsx`, UPSERTs into `leds`, `pcbs`,
`drivers`, `luminaire_leds`. Idempotent. Maps lens codes via `Lentes` sheet.

### Verify
```bash
cd backend
python -c "
from app.database import SessionLocal
from app.models import Gama, Difusor, Lente, LedType, ValidCombination, Fotometria
db = SessionLocal()
print(f'Gamas: {db.query(Gama).count()}, Difus: {db.query(Difusor).count()}, '
      f'Lentes: {db.query(Lente).count()}, LEDs: {db.query(LedType).count()}, '
      f'VCs: {db.query(ValidCombination).count()}, Lums: {db.query(Fotometria).count()}')
"
```

## 5. File naming convention (Salvi LDTs)

```
<GAMA>[_<MODULE>]_<CCT>K_<LENTE>_<DIFUSOR>_<POWER>W.ldt
```
Examples:
- `CLAP_M_C35_30K_F151_VDR_SPUW_100W.ldt`
- `KRONOS_28C_40K_F151_VDR_SPUW_45W.ldt`

The module segment (`C35`, `28C`, etc.) is a manufacturing detail, ignored.

## 6. Alembic workflow

```bash
cd backend
alembic revision --autogenerate -m "add <thing>"
alembic upgrade head
alembic downgrade -1
```

- `alembic.ini` defaults to the local PostgreSQL URL; `DATABASE_URL` overrides it.
- `alembic/env.py` imports all models for autogenerate. **Import new models here.**
- Versions live in `alembic/versions/`.

Docker runs PostgreSQL schema initialization followed by `alembic upgrade head`
before starting the API.

### How to add a column
1. Update ORM in `app/models/<entity>.py`.
2. Import new model in `alembic/env.py` if new entity.
3. `alembic revision --autogenerate -m "add <col>"`.
4. **Review** the generated migration (autogenerate is not always right).
5. `alembic upgrade head`.
6. Update `frontend/src/types/index.ts` if exposed.

### How to add a dimension table
1. ORM in `app/models/catalog.py`.
2. Import in `app/models/__init__.py` and `alembic/env.py`.
3. Create migration.
4. CRUD service in `app/services/catalog_service.py`.
5. Endpoints in `app/routers/catalog.py`.
6. Frontend types + admin UI (`DimensionTable`).

## 7. File-system layout (LDTs)

```
backend/ldt/<manufacturer>/<filename>.ldt
```

Enforced by `admin_service`. `photometric_path` is UNIQUE in the DB. Renaming a
file on disk is safe only if the DB row is updated in the same transaction.
