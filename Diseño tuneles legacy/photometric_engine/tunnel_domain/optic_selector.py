"""
Optic Selector — Optimal APHEX Photometry for Tunnel Design
============================================================
Selects the best combination of:
  • APHEX optic  (F2MD / F2M2 / F151)
  • APHEX model  (S / M / L)
  • Operating current (350–750 mA, continuous)
  • Luminaire spacing S [m]
  • Mounting arrangement (single row, staggered, bilateral)

Optimisation objective:
  1. Normative compliance (L_avg ≥ L_req, U0 ≥ 0.40, Ul ≥ 0.60) — HARD constraint
  2. Minimise energy (W × N_luminaires) as primary objective
  3. Minimise capital cost (N_luminaires) as secondary objective

Strategy: coarse parametric sweep → fine refinement around best candidate.

The selector calls TunnelCalculator for each candidate to verify compliance
with the actual CIE 140 photometric calculation.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from ..salvi_photometry.ldt_parser  import Photometry, load_ldt
from ..salvi_photometry.calculator  import TunnelCalculator, LuminaireInstance, ZoneResult
from ..salvi_photometry.geometry    import LuminaireOrientation, Observer
from ..tunnel_domain.grid           import make_grid
from ..tunnel_domain.cie88          import TunnelZone, transition_luminance_at_s


# ── APHEX Catalog ──────────────────────────────────────────────────────────────
# Flux and power at each operating point (350 / 500 / 750 mA).
# Source: APHEX technical datasheet (as validated in previous sessions).

APHEX_CATALOG = {
    "S": {
        "pcb":   "50G",
        "label": "APHEX S",
        "operating_points": {
            "4000K": [
                {"mA": 350, "W":  97, "lm": 20_186},
                {"mA": 500, "W": 136, "lm": 27_503},
                {"mA": 750, "W": 194, "lm": 36_874},
            ],
            "3000K": [
                {"mA": 350, "W":  97, "lm": 18_941},
                {"mA": 500, "W": 136, "lm": 25_803},
                {"mA": 750, "W": 194, "lm": 34_584},
            ],
        },
    },
    "M": {
        "pcb":   "100G",
        "label": "APHEX M",
        "operating_points": {
            "4000K": [
                {"mA": 350, "W": 200, "lm": 42_503},
                {"mA": 500, "W": 280, "lm": 57_876},
                {"mA": 750, "W": 410, "lm": 78_123},
            ],
            "3000K": [
                {"mA": 350, "W": 200, "lm": 39_847},
                {"mA": 500, "W": 280, "lm": 54_263},
                {"mA": 750, "W": 410, "lm": 73_305},
            ],
        },
    },
    "L": {
        "pcb":   "200G",
        "label": "APHEX L",
        "operating_points": {
            "4000K": [
                {"mA": 350, "W": 395, "lm": 60_559},
                {"mA": 500, "W": 546, "lm": 82_449},
                {"mA": 750, "W": 790, "lm": 110_611},
            ],
            "3000K": [
                {"mA": 350, "W": 395, "lm": 56_825},
                {"mA": 500, "W": 546, "lm": 77_322},
                {"mA": 750, "W": 790, "lm": 103_712},
            ],
        },
    },
}

APHEX_MODEL_ORDER = ["S", "M", "L"]

# Available optic files (keys match optic_id() of Photometry)
OPTIC_IDS = ["F2MD", "F2M2", "F151"]


def _interp_op(ops: list[dict], target_lm: float) -> dict:
    """Piecewise-linear interpolation between catalogue operating points."""
    if target_lm <= ops[0]["lm"]:
        return dict(ops[0])
    if target_lm >= ops[-1]["lm"]:
        return dict(ops[-1])
    for i in range(len(ops) - 1):
        lo, hi = ops[i], ops[i + 1]
        if lo["lm"] <= target_lm <= hi["lm"]:
            t = (target_lm - lo["lm"]) / (hi["lm"] - lo["lm"])
            return {
                "mA": round(lo["mA"] + t * (hi["mA"] - lo["mA"])),
                "W":  round(lo["W"]  + t * (hi["W"]  - lo["W"]),  1),
                "lm": target_lm,
            }
    return dict(ops[-1])


# ── Candidate result ──────────────────────────────────────────────────────────

@dataclass
class DesignCandidate:
    optic_id:     str
    model:        str
    cct:          str
    current_mA:   int
    flux_lm:      float
    power_w:      float
    spacing_m:    float
    arrangement:  str        # 'single', 'staggered', 'bilateral'
    mounting_H:   float
    n_luminaires: int
    power_total_w: float
    zone_result:  Optional[ZoneResult] = None
    compliant:    bool = False
    score:        float = float("inf")  # lower = better


# ── Selector ──────────────────────────────────────────────────────────────────

class OpticSelector:
    """
    Selects the optimal APHEX photometry configuration for a tunnel zone.

    Parameters
    ----------
    ldt_paths     : dict mapping optic_id → path to .ldt file
    rtable_name   : CIE 144 r-table (e.g. 'R2')
    mf            : maintenance factor
    I_max_mA      : maximum allowed operating current [mA]
    cct           : correlated colour temperature '4000K' or '3000K'
    """

    def __init__(
        self,
        ldt_paths:    dict[str, str | Path],
        rtable_name:  str   = "R2",
        mf:           float = 0.80,
        I_max_mA:     int   = 750,
        cct:          str   = "4000K",
    ):
        self.photometries: dict[str, Photometry] = {
            optic_id: load_ldt(p) for optic_id, p in ldt_paths.items()
        }
        self.rtable_name = rtable_name
        self.mf          = mf
        self.I_max_mA    = I_max_mA
        self.cct         = cct
        self.calculator  = TunnelCalculator(rtable_name, mf)

    def select_for_zone(
        self,
        zone:         TunnelZone,
        road_width_m: float,
        n_lanes:      int   = 2,
        H_options:    list[float] | None = None,
        S_options:    list[float] | None = None,
        arrangements: list[str]  | None  = None,
        observer:     Observer   | None  = None,
        speed_kmh:    float = 80.0,
        Lth:          float = 0.0,
        Lin:          float = 0.0,
    ) -> DesignCandidate:
        """
        Sweep all optic/model/spacing combinations and return the best compliant
        candidate (min energy, then min luminaires).
        """
        H_opts  = H_options   or [6.0, 7.0, 8.0, 9.0, 10.0]
        S_opts  = S_options   or [4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 12.0]
        arr_opts = arrangements or ["single"]
        obs      = observer or Observer(lane_y_m=road_width_m / 4)

        best: Optional[DesignCandidate] = None

        for optic_id, model, H, S, arr in itertools.product(
            OPTIC_IDS, APHEX_MODEL_ORDER, H_opts, S_opts, arr_opts
        ):
            ops = APHEX_CATALOG[model]["operating_points"].get(self.cct, [])
            if not ops:
                continue

            # Filter by I_max
            valid_ops = [op for op in ops if op["mA"] <= self.I_max_mA] or [ops[0]]
            flux_max  = valid_ops[-1]["lm"]

            # Build luminaire grid for this spacing
            lum_list = self._build_luminaires(
                zone, road_width_m, H, S, arr,
                optic_id=optic_id, flux_lm=flux_max
            )
            if not lum_list:
                continue

            # Quick flux-balance check before full calculation
            # (skip obviously undersized combinations)
            if not self._flux_check(zone, road_width_m, H, S, flux_max, arr):
                continue

            # Full CIE 140 calculation
            calc_pts = make_grid(
                zone_name=zone.zone_type,
                zone_type=zone.zone_type,
                s_start=zone.s_start,
                s_end=zone.s_end,
                luminaire_spacing=S,
                road_width=road_width_m,
                n_lanes=n_lanes,
            )
            if not calc_pts:
                continue

            zr = self.calculator.calculate_zone(
                zone_name=zone.zone_type,
                zone_type=zone.zone_type,
                s_start=zone.s_start,
                s_end=zone.s_end,
                L_req=zone.L_req,
                calc_points=calc_pts,
                luminaires=lum_list,
                observer=obs,
            )

            if not zr.compliant:
                continue

            # Find minimum current needed (reduce flux to meet L_req exactly)
            op_opt = self._optimise_current(
                zr, zone, calc_pts, lum_list, valid_ops, obs
            )

            n_lum = len(lum_list)
            pwr   = n_lum * op_opt["W"]

            cand = DesignCandidate(
                optic_id=optic_id,
                model=model,
                cct=self.cct,
                current_mA=op_opt["mA"],
                flux_lm=op_opt["lm"],
                power_w=op_opt["W"],
                spacing_m=S,
                arrangement=arr,
                mounting_H=H,
                n_luminaires=n_lum,
                power_total_w=pwr,
                zone_result=zr,
                compliant=True,
                score=self._score(pwr, n_lum),
            )

            if best is None or cand.score < best.score:
                best = cand

        if best is None:
            # Return non-compliant fallback (best effort at max current)
            best = self._fallback(zone, road_width_m, H_opts[0], S_opts[0],
                                  arr_opts[0], obs, n_lanes)

        return best

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _build_luminaires(
        self,
        zone:         TunnelZone,
        road_width_m: float,
        H:            float,
        S:            float,
        arrangement:  str,
        optic_id:     str,
        flux_lm:      float,
    ) -> list[LuminaireInstance]:
        """Build list of LuminaireInstance for this zone and arrangement."""
        phot = self.photometries.get(optic_id)
        if phot is None:
            return []

        n_lum = max(1, math.ceil(zone.length / S))
        d_actual = zone.length / n_lum

        lums = []
        orient = LuminaireOrientation(nu_deg=0.0)

        for i in range(n_lum):
            x_lum = zone.s_start + (i + 0.5) * d_actual
            if arrangement == "single":
                y_lum = road_width_m / 2.0
                lums.append(LuminaireInstance(
                    x=x_lum, y=y_lum, H=H,
                    photometry=phot, flux_lm=flux_lm, orientation=orient,
                    label=f"{optic_id}_lum{i+1}",
                ))
            elif arrangement == "staggered":
                y_lum = 0.0 if i % 2 == 0 else road_width_m
                lums.append(LuminaireInstance(
                    x=x_lum, y=y_lum, H=H,
                    photometry=phot, flux_lm=flux_lm, orientation=orient,
                    label=f"{optic_id}_lum{i+1}",
                ))
            elif arrangement == "bilateral":
                for y_lum in [0.0, road_width_m]:
                    lums.append(LuminaireInstance(
                        x=x_lum, y=y_lum, H=H,
                        photometry=phot, flux_lm=flux_lm, orientation=orient,
                        label=f"{optic_id}_lum{i+1}",
                    ))
        return lums

    def _flux_check(
        self, zone: TunnelZone, w: float, H: float, S: float,
        flux_lm: float, arrangement: str
    ) -> bool:
        """
        Quick flux-balance pre-filter: estimated L_avg ≥ 0.5 × L_req.
        UF ≈ 0.55 (rough), MF already in self.mf.
        """
        UF_est = 0.55
        rho_est = 0.070   # R2 Qd
        n_rows = 2 if arrangement == "bilateral" else 1
        L_est = (flux_lm * UF_est * self.mf * rho_est) / (math.pi * S * w / n_rows)
        return L_est >= 0.5 * zone.L_req

    def _optimise_current(
        self,
        zr:        ZoneResult,
        zone:      TunnelZone,
        calc_pts:  list[tuple[float, float]],
        lums:      list[LuminaireInstance],
        valid_ops: list[dict],
        obs:       Observer,
    ) -> dict:
        """
        Binary-search for minimum flux that still satisfies compliance.
        Returns operating point dict {mA, W, lm}.
        """
        lo_lm = valid_ops[0]["lm"]
        hi_lm = valid_ops[-1]["lm"]
        best_op = valid_ops[-1]

        for _ in range(12):   # 12 bisections → ≈0.02% accuracy
            mid_lm = (lo_lm + hi_lm) / 2.0
            op     = _interp_op(valid_ops, mid_lm)

            # Scale luminaires to mid_lm
            for lum in lums:
                lum.flux_lm = mid_lm

            test = self.calculator.calculate_zone(
                zone_name=zone.zone_type, zone_type=zone.zone_type,
                s_start=zone.s_start, s_end=zone.s_end,
                L_req=zone.L_req, calc_points=calc_pts,
                luminaires=lums, observer=obs,
            )
            if test.compliant:
                best_op = op
                hi_lm   = mid_lm
            else:
                lo_lm   = mid_lm

        # Restore max flux
        for lum in lums:
            lum.flux_lm = valid_ops[-1]["lm"]

        return best_op

    @staticmethod
    def _score(power_w: float, n_lum: int) -> float:
        """Lower score = better.  Weighted: energy (80%) + unit count (20%)."""
        return 0.80 * power_w + 0.20 * n_lum * 1000

    def _fallback(
        self, zone, road_width_m, H, S, arrangement, obs, n_lanes
    ) -> DesignCandidate:
        """Non-compliant best-effort at max current with first available optic."""
        optic_id = next(iter(self.photometries), OPTIC_IDS[0])
        ops = APHEX_CATALOG["L"]["operating_points"].get(self.cct, [])
        op  = ops[-1] if ops else {"mA": 750, "W": 790, "lm": 110_611}
        lums = self._build_luminaires(zone, road_width_m, H, S, arrangement,
                                       optic_id, op["lm"])
        return DesignCandidate(
            optic_id=optic_id, model="L", cct=self.cct,
            current_mA=op["mA"], flux_lm=op["lm"], power_w=op["W"],
            spacing_m=S, arrangement=arrangement, mounting_H=H,
            n_luminaires=len(lums),
            power_total_w=len(lums) * op["W"],
            compliant=False,
            score=float("inf"),
        )
