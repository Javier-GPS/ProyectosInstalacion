# AGENTS.md — Project notes for AI/code agents

This file is the entry point for any agent touching the project. It
captures the non-obvious facts that an LLM (or a new contributor)
needs to avoid breaking the build.

> **Read [`docs/README.md`](./docs/README.md) first.** The canonical
> architecture doc is `docs/architecture.md`; the notes below are
> project-specific gotchas layered on top of it.

## Stack

- **Backend**: FastAPI + SQLAlchemy 2.0 + Alembic + PostgreSQL. Python 3.12.
- **Frontend**: React 18 + Vite + Tailwind + TypeScript.
- **DB migrations**: `cd backend && alembic upgrade head`. Never edit
  the DB by hand; always write a migration.
- **Tests**: `cd backend && python -m pytest tests/`.

## Power cap (4-tuple → LED max power)

The configurator must never let a `Tramo` be calculated at a power
the LED cannot support. The implementation spans every layer:

1. **Source of truth**: `LED.pmax_ajustada` (the conservative ceiling
   of `LED_Pot Max Ajustada` in the Salvi xlsx). The schema lives in
   `backend/app/models/luminaire_catalog.py`.
2. **Seed**: `cd backend && python scripts/import_salvi_leds.py` —
   reads `Referencias_productos_pcb_go.xlsx` once and UPSERTs into
   `leds`, `pcbs`, `drivers`, `luminaire_leds`. **Idempotent**, safe
   to re-run. The xlsx is the temporary source; once imported the
   application does not read the xlsx at runtime.
3. **Service**: `backend/app/services/luminaire_catalog.py` exposes
   `get_pmax_for_selection`, `clamp_power_to_pmax` and
   `max_power_for_optimizer`. The clamp returns the config
   unchanged for external/temporary LDTs and for unknown 4-tuples.
4. **Endpoints**:
   - `GET /api/ldt/dimensions` now also returns `pmax_by_combo` so
     the FE caches every cap in one fetch.
   - `POST /api/admin/luminaire-pmax` (admin) returns the cap for a
     specific 4-tuple.
   - `POST /api/calculate` returns HTTP 400 when `power > pmax`.
   - `POST /api/optimize/simple` and `.../advanced` and
     `.../advanced-batch` cap the search at `pmax`.
5. **FE**: `frontend/src/components/panels/LuminairePanel.tsx` reads
   the cap from the `pmax_by_combo` map and applies it as the
   `EditableSlider`'s `max`. A small banner shows the cap. If the
   user switches to a luminaire with a lower cap, the slider's value
   is clamped and the tramo is marked dirty (re-calculate required).

### Lens code mapping

`BBDD_Fotometrias.xlsx` uses F151/F2M2-style codes while
`Variantes SALVI` uses short codes (M3, 2D, …). The seed reads the
`Lentes` sheet to translate Variantes → BBDD codes so the
`luminaire_leds` table keys off the same names the rest of the
application uses.

### Highest-cap LED selection

When a 4-tuple maps to several `LED_REF`s, the seed keeps the LED with
the highest `pmax_ajustada`, because that is the maximum supported
configuration for that luminaria. It emits a `warnings.warn` +
`logging.warning` listing the alternatives it dropped. The warnings
appear in the seed's stdout **and** in `warnings.warn` so a notebook /
CI / service worker all see them.

## Other gotchas

- The four catalog dimension tables (`gamas`, `difusores`, `lentes`,
  `led_types`) are normalised with `strip().upper()` everywhere.
  Never compare without normalising.
- The `CalculationConfig` Pydantic model accepts the 4-tuple fields
  (`gama`, `difusor`, `lente`, `led_type`) as optional. When the FE
  sends them, they flow through to the cap check; when omitted, the
  cap is not enforced.
- `ldt_id` starting with `temp-` means an external LDT. External
  LDTs bypass the cap (intentional — the user uploaded the file
  and explicitly accepts the result).
- `OPTIMIZATION_MAX_POWER` in `routers/calculate.py` is a hard
  500 W ceiling. The cap service lowers it per-4-tuple; the
  default stays in place for the "no 4-tuple selected" case.

### pmax_ajustada — max, not last-write-wins

The same ``LED_REF`` can appear on several rows in ``Param_ Configura``
(e.g. C42 appears 3 times with 260, 240, 160 W).  The import script
(``scripts/import_salvi_leds.py:205``) now keeps the **maximum**
``pmax_ajustada`` rather than the last value read.  This was a bug:
before the fix, C42 was stored as 160.0 W instead of 260.0 W.

## Admin — catalog tables

The admin panel (``/admin``) now has read-only tabs for **LEDs**,
**PCBs**, **Drivers** and **4-tupla → LED** (``LuminaireLED``)
so operators can inspect the power caps and bindings without
querying the DB directly.  Backend endpoints live in
``routers/catalog.py`` under ``/api/admin/leds``, ``/pcbs``,
``/drivers``, ``/luminaire-leds``.

### Codebase search (semántico, plugin)

Hay un índice semántico (`codebase-search` skill). Antes de leer archivos
a ver qué hay, mandate `codebase_peek` o `codebase_search` con lenguaje
natural. Si ya sabés el nombre exacto, usá `grep`. Buscar acá primero
ahorra leer cosas irrelevantes.

<!-- headroom:rtk-instructions -->
# RTK (Rust Token Killer) - Token-Optimized Commands

When running shell commands, **always prefix with `rtk`**. This reduces context
usage by 60-90% with zero behavior change. If rtk has no filter for a command,
it passes through unchanged — so it is always safe to use.

## Key Commands
```bash
# Git (59-80% savings)
rtk git status          rtk git diff            rtk git log

# Files & Search (60-75% savings)
rtk ls <path>           rtk read <file>         rtk grep <pattern>
rtk find <pattern>      rtk diff <file>

# Test (90-99% savings) — shows failures only
rtk pytest tests/       rtk cargo test          rtk test <cmd>

# Build & Lint (80-90% savings) — shows errors only
rtk tsc                 rtk lint                rtk cargo build
rtk prettier --check    rtk mypy                rtk ruff check

# Analysis (70-90% savings)
rtk err <cmd>           rtk log <file>          rtk json <file>
rtk summary <cmd>       rtk deps                rtk env

# GitHub (26-87% savings)
rtk gh pr view <n>      rtk gh run list         rtk gh issue list

# Infrastructure (85% savings)
rtk docker ps           rtk kubectl get         rtk docker logs <c>

# Package managers (70-90% savings)
rtk pip list            rtk pnpm install        rtk npm run <script>
```

## Rules
- In command chains, prefix each segment: `rtk git add . && rtk git commit -m "msg"`
- For debugging, use raw command without rtk prefix
- `rtk proxy <cmd>` runs command without filtering but tracks usage
<!-- /headroom:rtk-instructions -->
