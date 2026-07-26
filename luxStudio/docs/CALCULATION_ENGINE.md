# Calculation Engine

> Read `../ARCHITECTURE.md` first. This file describes the CIE 140 / EN 13201
> calculation engine, where the math lives, and the assumptions that ship with
> the current implementation. It is the reference you need when you change
> photometric behaviour, add a new criterion, or debug calc accuracy.

All math lives in `backend/app/salvi_lighting/`. The package is pure
Python: no I/O, no HTTP, no DB. This makes it the easiest layer to unit-test.

## 1. Inputs and outputs

- **Inputs:**
  - A `CalculationConfig` (Pydantic) — geometry, arrangement, class, MF, pavement,
    luminaire selection (LDT + power + CCT + CRI), and a `language` tag.
  - A `Photometry` object — in-memory wrapper around a parsed LDT dict
    (`salvi_lighting/calc.py::Photometry`).
- **Output:** a result dict (or `CalculationResult` Pydantic) with
  `Lavg, Uo, Ul, TI, SR, ok_*, compliant, mode` (ME classes) or
  `Eavg, Emin, ok_Eavg, ok_Emin, compliant, mode` (P classes).

The conversion between the user-facing `CalculationConfig` and the
engine-internal config dict is done by `services/calculator.py::_config_to_cfg`.

## 2. LDT (EULUMDAT) parsing

`salvi_lighting/eulumdat.py::parse_ldt(path) -> dict` reads an EULUMDAT file and
returns a dict with:

| Key | Meaning |
|---|---|
| `Mc` | number of C planes |
| `Dc` | C step in degrees |
| `Ng` | number of gamma angles |
| `Dg` | gamma step in degrees |
| `I[C][G]` | intensity in cd/klm, indexed by C plane and gamma angle |
| `lamp_sets` | list of lamp sets; we use `lamp_sets[0]` for the reference flux/power |
| `LORL` | light output ratio of the luminaire (0..1, decimal) |
| `Isym` | symmetry index (0 = none, 1 = about vertical axis, 2 = C0-C180, 3 = C90-C270, 4 = both) |
| `conv` | conversion factor (typically 1.0) |
| `lum_name` | human name from the LDT |
| `company` | manufacturer from the LDT |

Sampling is bilinear between C planes and gamma angles
(`Photometry.intensity(C_deg, gamma_deg)`).

### Photometry wrapper

`Photometry.__init__(d)` stores the parsed dict and precomputes
`self.flux = lamp_sets[0]["flux_lm"]` and `self.power = lamp_sets[0]["wattage"]`.
The `intensity` method applies the conversion factor and clamps negative
interpolated values to zero (a safety net for malformed LDTS).

## 3. Coordinate system

```
                 z ↑
                   |
                   |
       luminaire   |   +x along the direction of travel
         *---------+--------------------→
        /|         | 0
       / |         |
      h  |       W |
     /   |         |
    *----+---------+----------→ y
   pole  0         (road edge at y=0; right edge at y=W)
```

- `x` — longitudinal, along the direction of travel.
- `y` — transverse, `y=0` is the left edge of the carriageway, `y=W` is the
  right edge.
- `z` — vertical, positive up. The road plane is `z=0`.

LDT convention (kept identical to the EULUMDAT standard):

- `C=0°` along `+x` (direction of travel).
- `C=90°` across the road toward the road interior.
- `gamma=0°` straight down.

## 4. Luminaire placement

`salvi_lighting/calc.py::build_luminaires(cfg, photometry, flux_scale)` returns
11 × N luminaire instances (k = -5..5 periods of the calculation field) where
N depends on the arrangement:

| Arrangement | Poles per period | Position | Mirror Y? |
|---|---|---|---|
| `Lineal` | 1 | side from `cfg.pole_side` | `right` ⇒ mirror |
| `Bilateral` | 2 (offset by S/2) | first side = `cfg.pole_side`, second = opposite | per-side |
| `Central Doble` | 2 (same x) | middle of carriageway, one mirrored | both |
| `En Isleta` | 1 | middle of carriageway | per config |

Each `Luminaire` instance is `(x, y, h, aim=0, tilt, flux_scale, mf, mirror_y)`.
The pole offset (`cfg.arm` after geometry pre-processing) and the road width
set the transverse position; tilt rotates the photometry in the luminaire's
own frame; mirror flips the Y axis of the photometry for right-side poles.

## 5. Grid

`_make_grid(cfg)` builds an EN 13201-3 / CIE 140 evaluation grid:

- Longitudinal: `N = 10` if `S ≤ 30 m`; otherwise the smallest `N` with
  `D = S/N ≤ 3 m`.
- Luminance: 3 transverse points per lane.
- Illuminance: at least 3 points per lane and spacing `≤ 1.5 m`.

This matches the density rules in UNE-EN 13201-3:2015 §7.2 rather than the
legacy fixed `12 x 3` simplification.

## 6. Illuminance (E) and luminance (L)

`Luminaire.E_at(x, y)` (lux) and `Luminaire.L_at(x, y, observer_xy, road)`
(cd/m²) compute the contribution of one luminaire at one grid point.

`E_at`:

```
d² = (x − x0)² + (y − y0)² + h²       # squared distance
cd = I_cd(γ, C) · flux/1000 · scale · mf
E  = cd · (h/d) / d²                  # cos(incidence)/d²
```

`L_at` follows CIE 140 / CIE 144:

```
tg = √((x−x0)² + (y−y0)²) / h        # tan(γ) from world geometry
β  = 180° − θ                         # θ = angle between observer→P and luminaire→P
r  = r_value(tg, β, road)             # CIE 144 r-table
L  = r · cd / h²
```

`evaluate(cfg, photometry, flux_scale, road)` orchestrates the three
calculation steps and the class check:

- `M*` class → `calc_luminance` (which internally runs the TI loop) +
  REI check.
- `P*` class → `calc_road` (illuminance grid) + illuminance criterion check.

`mode` is `"ME"` for M classes and `"P"` for P classes.

For luminance, the observer is placed 60 m before the field. One observer is
placed at the centre of each lane; the worst operative value is reported for
`Lavg`, `Uo` and `TI`, and the worst `Ul` across lanes is reported.

## 7. TI (threshold increment)

Implemented inside `calc_luminance` (CIE 88 / EN 13201-3):

- Observer at `(-60, obs_y, 1.5)` (eye height 1.5 m, CIE 140).
- For each luminaire, compute the eye direction `(lum→eye)` in the
  luminaire's frame, sample `I(C, γ)`, and skip angles `≤ 1.5°` or `> 60°`.
- Veiling luminance uses the age-23 UNE formula (small-angle and far-angle
  branches) with the 20° screening plane.
- `TI = 65 · Lv / Lavg^0.8` for `0.05 ≤ Lavg ≤ 5 cd/m²`;
  `TI = 95 · Lv / Lavg^1.05` for `Lavg > 5 cd/m²`.

The Lavg here is the average luminance across the full grid, so the loop and
the Lavg are tied to the same calculation step.

## 8. REI (surround ratio) — EN 13201-3 8.6

`calc_EIR` measures the ratio of outer-strip illuminance to inner-strip
illuminance on each side of the carriageway and returns the minimum of the two
ratios:

```
REI = min( outer_L / inner_L , outer_R / inner_R )
```

The strip width equals the lane width, and the illuminance in each strip is
sampled with the same `≤ 1.5 m` transverse density used for the illuminance
grid. This is the value used for ME-class compliance.

The legacy aggregate ratio `SR = (outer_L + outer_R) / (inner_L + inner_R)`
is still computed and reported for information.

## 9. Class requirements

`ME_REQ` (M1..M6) and `P_REQ` (P1..P6) are literal dicts in
`salvi_lighting/calc.py`. The criteria are:

| Class | L (cd/m²) | Uo | Ul | TI (%) | SR |
|---|---|---|---|---|---|
| M1 | 2.00 | 0.40 | 0.70 | 10 | 0.5 |
| M2 | 1.50 | 0.40 | 0.70 | 10 | 0.5 |
| M3 | 1.00 | 0.40 | 0.60 | 15 | 0.5 |
| M4 | 0.75 | 0.40 | 0.60 | 15 | 0.5 |
| M5 | 0.50 | 0.35 | 0.40 | 15 | 0.5 |
| M6 | 0.30 | 0.35 | 0.40 | 20 | 0.5 |

| Class | Eavg (lux) | Emin (lux) |
|---|---|---|
| P1 | 15.0 | 3.0 |
| P2 | 10.0 | 2.0 |
| P3 | 7.5  | 1.5 |
| P4 | 5.0  | 1.0 |
| P5 | 3.0  | 0.6 |
| P6 | 2.0  | 0.4 |

## 10. Flux estimation and scaling

`services/calculator.py::_target_luminaire_info` is the bridge between
"what the user typed" (any power, CCT, CRI) and "what the engine needs"
(flux scale relative to the reference LDT). The algorithm is:

1. **If the request includes the structured catalog 4-tuple
   (`gama`, `difusor`, `lente`, `led_type`):** use the selected LDT as
   the photometric shape and scale its flux linearly from
   `photometry.power` to `config.power`, then apply CCT/CRI LED flux scaling
   against the reference LDT's CCT/CRI. Do not apply lens/diffuser efficiency
   again here: the selected LDT already represents that optical assembly. The
   BBDD workbook chooses the curve; `Referencias_productos_pcb_go.xlsx`
   provides the valid LED power range through `pmax_ajustada`, and the
   selected power sets the actual calculation scale.
2. **If `config.power ≈ photometry.power` (within 1%):** use the reference
   flux scaled by CCT/CRI only (no power-law extrapolation).
3. **Otherwise:** interpolate target flux from sibling DB records that share
   the same `(manufacturer, model_family, optic_family, cri)`:
   - For each matching CCT, interpolate/extrapolate flux at `config.power`
     using the available power points.
   - If a CCT has only one power point, fall back to `_power_law_flux`
     (`exponent = 0.832`).
   - Then interpolate across CCT to `config.cct`.
4. **If no siblings exist:** fall back to `efficiency × power` (using the
   reference efficiency), or to the power-law extrapolation as a last resort.
5. **CCT/CRI scaling:** apply `_led_flux_factor(config.cct, config.cri, reference_cct, reference_cri)`
   which interpolates a per-LED flux table (LUXEON 5050 Round typical
   luminous flux at rated current) for target and reference CCT/CRI and
   returns the ratio.

The `flux_scale = target_flux / photometry.flux` is passed to
`evaluate(...)` and applied multiplicatively inside `Luminaire._candela`.

### Sibling matching with new catalog fields

When the FE sends `gama`, `difusor`, `lente` and `led_type`, the engine
uses the structured catalog path above and scales the selected LDT linearly
to `config.power`. The sibling interpolation path below is kept only for
legacy requests that do not carry the 4-tuple and therefore cannot be tied
back to the Salvi LED/PCB reference workbook.

### Power-law constant

`POWER_LAW_EXPONENT = 0.832` is a luminous-efficacy approximation. It is
consistent with the LED regime where efficacy improves sub-linearly with
power. When the catalog has only one power point per optic/CCT, this exponent
extrapolates flux to the requested power.

## 11. Pole Offset

EN 13201 cares about the actual on-road geometry. When the user moves the
pole **away from the road** (`pole_offset > 0`), the luminaire moves away
from the carriageway unless the arm compensates for it. The effective
horizontal projection over the road is therefore `arm_projection - pole_offset`.
The same geometry is used for illuminance, luminance and uniformity.

## 12. Optimizer v1 (simple)

`routers/calculate.py::_optimize_power_for_config(config, ldt_id, max_power)`
is a bounded search for the lowest compliant power:

1. Start at the current power.
2. Halve the power repeatedly until either we drop below `OPTIMIZATION_MIN_POWER = 1.0`
   or the first non-compliant value is found. The last compliant value is the
   upper bound; the first non-compliant value is the lower bound.
3. Binary-search between lower and upper with `OPTIMIZATION_PRECISION = 0.1 W`
   resolution.
4. If the result sits just below the threshold after rounding, nudge up
   step-by-step until it complies (safety margin).

The same primitive backs the advanced optimizer's inner loop.

## 13. Optimizer v1 (advanced)

`routers/calculate.py::_run_advanced_search` is a discrete Cartesian product
over the unlocked variables (`spacing`, `height`, `arm_length`, `tilt`),
combined with the simple power-search per cell. The score function
(`_advanced_score`) depends on the objective:

| Objective | Score tuple (lower is better) |
|---|---|
| `technical_limits` | Σ(margin² over criteria), max margin, total movement |
| `min_power` | power, power/spacing, movement |
| `max_spacing` | -spacing, power/spacing, power |

`margin` is `(value - required)/required` for "min" criteria (Lavg, Uo, Ul,
SR) and `(required - value)/required` for "max" criteria (TI). Cells where
any criterion fails are skipped.

For `optic_family` unlocked, the frontend sends a list of allowed families
and `_run_advanced_search` is invoked once per lens
(`routers/calculate.py::optimize_advanced_batch`).

## 14. LDT matching

`services/ldt_matcher.py::find_ldt_for_config` resolves a `CalculationConfig`
to an `ldt_id` (which is `str(Fotometria.id)` for catalog rows, or
`temp-<uuid>` for session-only uploads). The matching is, in order:

1. If `config.ldt_id` is set and resolves, use it as-is.
2. Restrict to `(manufacturer, model_family)`.
3. Try the synthetic key `<optic>_<power>W` and check the candidate is in
   the scope.
4. Try exact `(optic, power, cri, cct)`.
5. Try exact `(optic, power, cct)`.
6. Try `(optic, power)` with the closest CCT.
7. Try the same optic family with the closest power/CCT.
8. Fall back to the closest power within the scope.
9. Raise 404 with a helpful message including available families.

## 15. Report rendering

- **PDF:** `services/pdf_generator.py` uses WeasyPrint on the Jinja2 template
  `templates/report.html`. The template embeds the result, photometric
  metadata, and several SVG diagrams (`salvi_lighting/render.py` for
  polar/plan/section/isolines). All strings are translated via
  `services/i18n.py::translator(language)`.
- **Excel:** `services/excel_generator.py` builds a DIALux-style worksheet
  with one row per luminaire. Header cells are translated; column layout is
  fixed. Use the same translation table.

## 16. Testing the engine

The engine is pure Python and is tested in `backend/tests/`. Relevant suites:

- `test_cie140_geometry.py` — grid density, observer placement, TI formula.
- `test_luminance_observer.py` — per-lane observer positions.
- `test_arrangements.py` — bilateral/central doble symmetry and REI behavior.
- `test_cie140_pipeline.py` — end-to-end trace with real LDTs.

Run: `cd backend && python -m pytest tests/`

## 17. Known limits

- **Luminaire inclusion uses a simplified H-based window.** UNE-EN 13201-3
  defines exact lateral limits for luminance (`5H/12H/5H`) and illuminance
  (`±5H`). The code uses a longitudinal window of `±5H` and includes all
  poles built from the arrangement; this is close for normal geometries but
  not a pixel-perfect DIALux match.
- **No maintenance of the road surface reflection.** Pavement type is one
  of R1..R4 with a fixed r-table; we do not model wear or wet conditions.
- **TI phase/observer longitudinal sweep is implemented.** The observer is
  swept across the field; the worst TI per lane is reported. DIALux may use
  additional convergence refinements, so reference-case validation is still
  recommended.
- **Pole side affects drawing and uniformity re-eval but not the rest of the
  geometry.** Documented in `PRODUCT_DECISIONS.md`; this is a deliberate
  scope cut.
- **P classes do not compute fTI / C classes are not supported.** The schema
  currently only covers M1-M6 and P1-P6.
