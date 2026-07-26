# LUX Studio — Documentation Index

LUX Studio is a professional road-lighting design tool. It runs CIE 140 / EN 13201
photometric calculations from EULUMDAT (.ldt) files, generates technical reports
(PDF/Excel), and exposes a managed luminaire catalog behind authentication.

> **For any code change, read `architecture.md` first.** It is the canonical
> reference: layers, data flow, invariants, extension points. The other files
> are deep-dives into specific areas.

## Documents

| File | What it covers | When to read it |
|---|---|---|
| **[`architecture.md`](./architecture.md)** | System architecture, layered model, data/auth flows, invariants, extension points, design decisions. | **Always**, before touching any code. |
| **[`development.md`](./development.md)** | Setup, backend & frontend module guide, conventions, recipes, deployment, troubleshooting. | When coding — every layer. |
| **[`data_model.md`](./data_model.md)** | All tables, columns, catalog model, import scripts, Alembic migrations. | When changing DB schema or working with the catalog. |
| **[`api.md`](./api.md)** | Every HTTP endpoint: method, path, auth, body, response. | When adding/changing an endpoint or debugging HTTP. |
| **[`calculation_engine.md`](./calculation_engine.md)** | CIE 140 / EN 13201 engine: LDT parsing, photometry, luminance/TI/SR, flux scaling, optimizers. | When changing photometric math or debugging calc accuracy. |
| **[`README.md`](./README.md)** (this file) | Index and one-paragraph mental model. | First stop. |

## Quick reference — where to find what

| Si buscas… | Ve a |
|---|---|
| ¿Qué archivo tocar para añadir un endpoint/ruta? | `development.md § 3` (backend routers) + `development.md § 4` (frontend pages) |
| ¿Cómo añadir una columna a la BD? | `data_model.md § 6` (Alembic workflow) |
| ¿Dónde está el cálculo de flujo/potencia/CRI? | `development.md § 3` (Flux estimation) + `calculation_engine.md § 10` |
| ¿Qué endpoints necesita auth? | `api.md` (columna Auth) + `architecture.md § 4` |
| ¿Cómo funciona el optimizador? | `architecture.md § 7` + `calculation_engine.md § 12-13` |
| ¿Dónde está la lógica de power cap (pmax)? | `development.md § 3` (`luminaire_catalog.py`) |
| ¿Qué tablas hay y sus columnas? | `data_model.md § 2` |
| ¿Cómo funciona la selección en cascada (gama→difusor→…)? | `data_model.md § 3` + `architecture.md § 5` |
| ¿Cómo importar datos del catálogo? | `data_model.md § 4` |
| ¿Qué convenciones de código seguir? | `development.md § 5` |
| ¿Primera vez que ejecuto el proyecto? | `development.md § 1` |
| ¿Error raro en cálculo/optimización? | `development.md § 9` (Troubleshooting) |
| ¿Qué NO está implementado aún? | `architecture.md § 11` + `development.md § 8` (production backlog) |

## One-paragraph mental model

- **Backend (FastAPI + SQLAlchemy + PostgreSQL)** owns the photometry engine, the
  luminaire catalog, the project store, and all document generation. Exposes
  everything as REST under `/api/*`.
- **Frontend (React 18 + Vite + Tailwind)** is a single-page app that talks to
  the backend. Owns no business logic — captures config, calls `/api/calculate`,
  renders results in 2D (Konva) and 3D (Three.js).
- **Auth (JWT)** wraps the API except health, login, and static LDT routes.
- **Reports (WeasyPrint + openpyxl)** render PDF and Excel from the same
  `CalculationResult` produced by the engine.
