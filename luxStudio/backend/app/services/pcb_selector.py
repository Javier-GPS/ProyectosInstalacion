"""PCB selector: find the smallest PCB that produces a target flux.

Two public entry points:
- ``select_pcb_for_flux`` — flat-parameter flux-driven selector used by the
  optimizer (no user current, optional ``ignore_lm_w_min`` bypass).
- ``select_pcb_for_config`` — config-object selector used by the HTTP
  endpoints (``/api/ldt/flux-detail``, ``/api/calculate``).  Supports both
  flux-driven and power-driven modes and respects ``i_op_ma``.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, joinedload

from ..core.text_utils import norm as _norm
from ..models.catalog import Gama, Difusor, Lente, LedType
from ..models.luminaire_catalog import GamaPCB, LuminaireLED, LED, PCB, TSCoefficient
from ..schemas.models import FluxDetail, PcbOption
from ..core.thermal import TABLA_TS_SLOPE, dif_code
from ..services.led_data import FAMILIES, lookup_curve
from ..services.led_calculator import LedModelError
from ..services.led_efficacy import led_point


def _ts_coef(db: Session, gama_obj: Gama | None, dif_name: str) -> float:
    if gama_obj is not None and dif_name:
        dif_obj = db.query(Difusor).filter(Difusor.name.ilike(dif_name)).first()
        if dif_obj is not None:
            row = (
                db.query(TSCoefficient)
                .filter(
                    TSCoefficient.gama_id == gama_obj.id,
                    TSCoefficient.difusor_id == dif_obj.id,
                )
                .first()
            )
            if row is not None:
                return row.coef_led_c_per_w
    return TABLA_TS_SLOPE.get(
        ((gama_obj.name if gama_obj else "").strip().upper(), dif_code(dif_name)), 0.3
    )


def _query_4tuple(db: Session, gama: str, dif: str, lnt: str, lt: str) -> list[LuminaireLED]:
    return (
        db.query(LuminaireLED)
        .options(joinedload(LuminaireLED.led), joinedload(LuminaireLED.pcb))
        .join(Gama, LuminaireLED.gama_id == Gama.id)
        .join(Difusor, LuminaireLED.difusor_id == Difusor.id)
        .join(Lente, LuminaireLED.lente_id == Lente.id)
        .outerjoin(LedType, LuminaireLED.led_type_id == LedType.id)
        .filter(
            Gama.name.ilike(gama),
            Difusor.name.ilike(dif),
            Lente.name.ilike(lnt),
            (LedType.name.ilike(lt)) if lt else (LedType.id.is_(None)),
            LuminaireLED.pcb_id.isnot(None),
        )
        .all()
    )


def _query_by_gama(db: Session, gama: str) -> list[LuminaireLED]:
    return (
        db.query(LuminaireLED)
        .options(joinedload(LuminaireLED.led), joinedload(LuminaireLED.pcb))
        .join(Gama, LuminaireLED.gama_id == Gama.id)
        .filter(Gama.name.ilike(gama), LuminaireLED.pcb_id.isnot(None))
        .all()
    )


def _available_pcbs(db: Session, gama_obj: Gama | None) -> list[PcbOption]:
    result: list[PcbOption] = []
    if gama_obj:
        for gp in (
            db.query(GamaPCB)
            .options(joinedload(GamaPCB.pcb))
            .filter(GamaPCB.gama_id == gama_obj.id)
            .all()
        ):
            if gp.pcb:
                result.append(
                    PcbOption(
                        pcb_ref=gp.pcb.pcb_ref,
                        pcb_descripcion=gp.pcb.pcb_descripcion,
                        pcb_imax_led=gp.pcb.pcb_imax_led,
                        pcb_v_nominal=gp.pcb.pcb_v_nominal,
                        n_pcbs=None,
                        n_leds_per_pcb=None,
                        total_n_leds=gp.pcb.pcb_no_led,
                        led_ref=None,
                    )
                )
    return result


def _current_for_target_flux(
    led: LED,
    target_flux: float,
    max_i_ma: float,
    *,
    t_amb_c: float,
    ts_coef: float,
    total_n: int,
    lente_eff: float,
    difusor_eff: float,
) -> tuple[float, Any]:
    # Phase 0: evaluate at max current
    hi_point = led_point(led, max_i_ma / 1000.0, t_amb_c=t_amb_c, ts_coef_c_per_w=ts_coef, n_leds_total=total_n)
    hi_flux = hi_point.flux_lm * total_n * lente_eff * difusor_eff
    if hi_flux <= target_flux:
        return max_i_ma, hi_point

    family = FAMILIES[led.family]
    min_i_ma = _min_current_ma(family)

    best_i, best_point, best_err = max_i_ma, hi_point, abs(hi_flux - target_flux)
    lo, hi = min_i_ma, max_i_ma

    # Phase 1: linear estimate seeds the search near the target
    i_est = max(min_i_ma, min(max_i_ma, target_flux / hi_flux * max_i_ma))
    est_point = led_point(led, i_est / 1000.0, t_amb_c=t_amb_c, ts_coef_c_per_w=ts_coef, n_leds_total=total_n, tj_initial_c=hi_point.tj_c)
    est_flux = est_point.flux_lm * total_n * lente_eff * difusor_eff
    err = abs(est_flux - target_flux)
    if err < best_err:
        best_i, best_point, best_err = i_est, est_point, err
    if est_flux >= target_flux:
        hi = i_est
    else:
        lo = i_est

    # Phase 2: binary search with early exit + thermal seed from previous step
    prev_tj = best_point.tj_c
    for _ in range(16):
        if hi - lo < 0.2:
            break
        mid = (lo + hi) / 2.0
        point = led_point(led, mid / 1000.0, t_amb_c=t_amb_c, ts_coef_c_per_w=ts_coef, n_leds_total=total_n, tj_initial_c=prev_tj)
        flux = point.flux_lm * total_n * lente_eff * difusor_eff
        err = abs(flux - target_flux)
        if err < best_err:
            best_i, best_point, best_err = mid, point, err
        prev_tj = point.tj_c
        if flux >= target_flux:
            hi = mid
        else:
            lo = mid

    return best_i, best_point


def _min_current_ma(family) -> float:
    return lookup_curve(family.curve_id)[0].current_a * 1000


def _led_efficacy_before_thermal(point: Any) -> float:
    """Return LED efficacy before the separately reported thermal loss.

    ``LedPoint.efficacy_lm_w`` already includes ``KT``.  ``FluxDetail`` also
    exposes ``thermal_derating`` so the UI can show the full efficiency chain;
    returning the raw value here would apply the thermal loss twice.
    """
    if point.power_w <= 0 or point.kt <= 0:
        return 0.0
    return point.efficacy_lm_w / point.kt


def _valid_led_point_at_or_below(led: LED, max_i_ma: float, **kwargs) -> tuple[float, Any] | None:
    family = FAMILIES[led.family]
    min_i_ma = _min_current_ma(family)
    try:
        return max_i_ma, led_point(led, max_i_ma / 1000.0, **kwargs)
    except LedModelError:
        pass

    try:
        best_i = min_i_ma
        best_point = led_point(led, min_i_ma / 1000.0, **kwargs)
    except LedModelError:
        return None

    lo, hi = min_i_ma, max_i_ma
    for _ in range(16):
        if hi - lo < 0.2:
            break
        mid = (lo + hi) / 2.0
        try:
            point = led_point(led, mid / 1000.0, **kwargs)
        except LedModelError:
            hi = mid
            continue
        best_i, best_point = mid, point
        lo = mid
    return best_i, best_point


def select_pcb_for_flux(
    db: Session,
    gama: str,
    difusor: str,
    lente: str,
    led_type: str,
    target_flux: float,
    *,
    t_amb_c: float = 25.0,
    lm_w_min: float | None = None,
    driver_eficiencia: float = 1.0,
    selected_pcb_ref: str | None = None,
    ignore_lm_w_min: bool = False,
) -> FluxDetail | None:
    """Find the PCB with fewest LEDs that can produce ``target_flux``.

    Uses the V2 LUXEON 5050 model (``led_point``) to evaluate each
    available PCB for the gama.  Selects the smallest PCB (lowest
    ``total_n``) whose max flux at its rated current covers the target.

    ``lm_w_min`` filters out PCBs whose efficiency is below the
    threshold.  When ``ignore_lm_w_min`` is ``True`` the filter is
    bypassed — used by the recursive power adjuster that only cares
    about LAVG compliance.

    Returns ``None`` when no PCB can satisfy the requested flux or
    when the 4-tuple is incomplete.
    """
    gama_n, dif_n, lnt_n, lt_n = map(_norm, (gama, difusor, lente, led_type))
    if not (gama_n and dif_n and lnt_n and lt_n):
        return None

    _cache_key = ("pcb_static", gama_n, dif_n, lnt_n, lt_n)
    if _cache_key in db.info:
        pcb_static = db.info[_cache_key]
    else:
        candidates = _query_4tuple(db, gama_n, dif_n, lnt_n, lt_n)
        if not candidates:
            candidates = _query_by_gama(db, gama_n)
        gama_obj = db.query(Gama).filter(Gama.name.ilike(gama_n)).first()
        ref_led = next((c.led for c in candidates if c.led), None)
        gama_pcbs: list[PCB] = []
        if gama_obj:
            for gp in (
                db.query(GamaPCB)
                .options(joinedload(GamaPCB.pcb))
                .filter(GamaPCB.gama_id == gama_obj.id)
                .all()
            ):
                if gp.pcb:
                    gama_pcbs.append(gp.pcb)
        if not gama_pcbs and candidates:
            gama_pcbs = list({c.pcb for c in candidates if c.pcb})
        lled_by_pcb: dict[int | None, LuminaireLED] = {c.pcb_id: c for c in candidates if c.pcb_id}
        lente_eff_val = db.query(Lente.eficiencia).filter(Lente.name.ilike(lnt_n)).scalar() or 1.0
        difusor_eff_val = db.query(Difusor.eficiencia).filter(Difusor.name.ilike(dif_n)).scalar() or 1.0
        ts_coef = _ts_coef(db, gama_obj, dif_n)
        db.info[_cache_key] = pcb_static = {
            "candidates": candidates,
            "gama_obj": gama_obj,
            "ref_led": ref_led,
            "gama_pcbs": gama_pcbs,
            "lled_by_pcb": lled_by_pcb,
            "lente_eff_val": lente_eff_val,
            "difusor_eff_val": difusor_eff_val,
            "ts_coef": ts_coef,
        }

    candidates = pcb_static["candidates"]
    gama_obj = pcb_static["gama_obj"]
    ref_led = pcb_static["ref_led"]
    gama_pcbs = pcb_static["gama_pcbs"]
    lled_by_pcb = pcb_static["lled_by_pcb"]
    lente_eff_val = pcb_static["lente_eff_val"]
    difusor_eff_val = pcb_static["difusor_eff_val"]
    ts_coef = pcb_static["ts_coef"]

    manual = bool(selected_pcb_ref)
    working: list[dict] = []

    for pcb in gama_pcbs:
        if manual and not (
            pcb.pcb_ref and _norm(pcb.pcb_ref) == _norm(selected_pcb_ref)
        ):
            continue

        lled = lled_by_pcb.get(pcb.id)
        led = lled.led if lled else ref_led
        total_n = (lled.n_leds_per_pcb if lled else None) or pcb.pcb_no_led or 1
        n_pcbs_val = lled.n_pcbs if lled else None
        derived_leds_per_pcb = (total_n // n_pcbs_val) if n_pcbs_val else total_n
        pcb_imax_a = pcb.pcb_imax_led or 1.0
        pcb_imax_ma = pcb_imax_a * 1000

        eval_i_op = pcb_imax_ma

        valid = _valid_led_point_at_or_below(
            led,
            eval_i_op,
            t_amb_c=t_amb_c,
            ts_coef_c_per_w=ts_coef,
            n_leds_total=total_n,
        )
        if valid is None:
            continue
        eval_i_op, v2_eval = valid

        max_flux_at_eval_i = (
            v2_eval.flux_lm * total_n * lente_eff_val * difusor_eff_val
        )

        if max_flux_at_eval_i < target_flux and not manual:
            continue

        if max_flux_at_eval_i >= target_flux:
            try:
                actual_i_op, v2_actual = _current_for_target_flux(
                    led,
                    target_flux,
                    eval_i_op,
                    t_amb_c=t_amb_c,
                    ts_coef=ts_coef,
                    total_n=total_n,
                    lente_eff=lente_eff_val,
                    difusor_eff=difusor_eff_val,
                )
            except LedModelError:
                continue
            actual_v_f = v2_actual.vf_v
            actual_p_led = v2_actual.power_w
            actual_power = actual_p_led * total_n
            actual_flux = (
                v2_actual.flux_lm * total_n * lente_eff_val * difusor_eff_val
            )
            actual_led_efficacy = _led_efficacy_before_thermal(v2_actual)
            i_op_ok = actual_i_op <= pcb_imax_ma
            th2 = v2_actual.kt
            tj2 = v2_actual.tj_c
        elif manual:
            actual_i_op = eval_i_op
            actual_v_f = v2_eval.vf_v
            actual_p_led = v2_eval.power_w
            actual_power = actual_p_led * total_n
            actual_flux = max_flux_at_eval_i
            actual_led_efficacy = _led_efficacy_before_thermal(v2_eval)
            i_op_ok = True
            th2 = v2_eval.kt
            tj2 = v2_eval.tj_c
        else:
            continue

        final_eff = actual_flux / actual_power if actual_power > 0 else 0
        lm_w_ok = lm_w_min is None or final_eff * driver_eficiencia >= lm_w_min

        working.append(
            {
                "lled": lled,
                "pcb": pcb,
                "led": led,
                "total_n": total_n,
                "n_pcbs_val": n_pcbs_val,
                "n_leds_per_pcb_val": derived_leds_per_pcb,
                "i_op": actual_i_op,
                "v_f": actual_v_f,
                "p_led": actual_p_led,
                "power": actual_power,
                "flux": actual_flux,
                "efficiency": final_eff,
                "driver_eff": driver_eficiencia,
                "led_efficacy": actual_led_efficacy,
                "thermal_derating": th2,
                "tj_c": tj2,
                "lente_eff": lente_eff_val,
                "difusor_eff": difusor_eff_val,
                "i_op_ok": i_op_ok,
                "lm_w_ok": lm_w_ok,
            }
        )

    if not working:
        return None

    if manual:
        sel = working[0] if working else None
    else:
        sel = min(
            (w for w in working if ignore_lm_w_min or w["lm_w_ok"]),
            key=lambda w: w["total_n"],
            default=None,
        )
    if sel is None:
        return None

    return FluxDetail(
        gama=gama,
        difusor=difusor,
        lente=lente,
        led_type=led_type,
        pcb_ref=sel["pcb"].pcb_ref,
        pcb_descripcion=sel["pcb"].pcb_descripcion,
        pcb_v_nominal=sel["pcb"].pcb_v_nominal,
        pcb_imax_led=sel["pcb"].pcb_imax_led,
        pcb_no_led=sel["pcb"].pcb_no_led,
        n_pcbs=sel["n_pcbs_val"],
        n_leds_per_pcb=sel["n_leds_per_pcb_val"],
        total_n_leds=sel["total_n"],
        led_ref=sel["led"].led_ref if sel["led"] else None,
        flux=round(sel["flux"], 1),
        efficiency=round(sel["efficiency"], 1),
        led_efficacy=round(sel["led_efficacy"], 2),
        lente_eficiencia=round(sel["lente_eff"], 4) if sel["lente_eff"] is not None else None,
        difusor_eficiencia=round(sel["difusor_eff"], 4) if sel["difusor_eff"] is not None else None,
        thermal_derating=round(sel["thermal_derating"], 4),
        tj_c=round(sel["tj_c"], 2),
        v_f=round(sel["v_f"], 3),
        p_led=round(sel["p_led"], 3),
        p_total=round(sel["power"], 2),
        i_op_ma=round(sel["i_op"], 1),
        user_i_op_ma=None,
        user_lm_w_min=lm_w_min,
        i_op_ok=sel["i_op_ok"],
        lm_w_ok=sel["lm_w_ok"],
        driver_eficiencia=driver_eficiencia,
        available_pcbs=_available_pcbs(db, gama_obj),
    )


def _imax(l: LuminaireLED) -> float:
    return l.pcb.pcb_imax_led if l.pcb and l.pcb.pcb_imax_led else 0.0


def select_pcb_for_config(db: Session, config: Any) -> FluxDetail | None:
    """Resolve PCB + flux + power for a config-like object (HTTP entry point).

    Accepts ``CalculationConfig`` or ``_FluxDetailRequest`` (duck-typed by
    ``gama`` / ``difusor`` / ``lente`` / ``led_type`` / ``target_flux`` /
    ``power`` / ``i_op_ma`` / ``lm_w_min`` / ``driver_eficiencia`` /
    ``selected_pcb_ref`` / ``t_amb_c``).

    Two modes:
    - ``target_flux`` > 0: flux-driven — iterate all gama PCBs and pick the
      smallest one that delivers the requested flux (respecting ``i_op_ma``
      and ``lm_w_min``).
    - otherwise: power-driven — compute flux from the V2 LED model at the
      operating current implied by ``i_op_ma`` or the PCB rated max.

    Raises ``LedModelError`` if the V2 model rejects the operating point;
    callers translate to HTTP 400.  Returns ``None`` when no PCB fits the
    4-tuple.
    """
    gama, dif, lnt, lt = _norm(config.gama), _norm(config.difusor), _norm(config.lente), _norm(config.led_type)
    if not (gama and dif and lnt and lt):
        return None

    candidates = _query_4tuple(db, gama, dif, lnt, lt)
    if not candidates:
        candidates = _query_by_gama(db, gama)

    user_i_op_a = (getattr(config, "i_op_ma", None) or 0) / 1000.0

    gama_obj = db.query(Gama).filter(Gama.name.ilike(gama)).first()
    available_pcbs = _available_pcbs(db, gama_obj)

    if not candidates and not getattr(config, "selected_pcb_ref", None):
        return None

    target_flux = getattr(config, "target_flux", None) or 0
    # --- Flux-driven mode: select PCB from target_flux ---
    # ponytail: max 2 thermal iterations; fine for UI preview
    if target_flux > 0:
        ref_led = next((l.led for l in candidates if l.led), None)
        gama_pcbs: list[PCB] = []
        if gama_obj:
            for gp in db.query(GamaPCB).options(joinedload(GamaPCB.pcb)).filter(GamaPCB.gama_id == gama_obj.id).all():
                if gp.pcb:
                    gama_pcbs.append(gp.pcb)
        elif candidates:
            gama_pcbs = list({l.pcb for l in candidates if l.pcb})
        lled_by_pcb = {l.pcb_id: l for l in candidates if l.pcb_id}
        driver_eff = getattr(config, "driver_eficiencia", None) or 1.0
        working: list[dict] = []
        manual = bool(getattr(config, "selected_pcb_ref", None))
        lente_eff_val = db.query(Lente.eficiencia).filter(Lente.name.ilike(lnt)).scalar() or 1.0
        difusor_eff_val = db.query(Difusor.eficiencia).filter(Difusor.name.ilike(dif)).scalar() or 1.0
        ts_coef = _ts_coef(db, gama_obj, dif)
        for pcb in gama_pcbs:
            if manual and not (pcb.pcb_ref and _norm(pcb.pcb_ref) == _norm(config.selected_pcb_ref)):
                continue
            lled = lled_by_pcb.get(pcb.id)
            led = lled.led if lled else ref_led
            total_n = (lled.n_leds_per_pcb if lled else None) or pcb.pcb_no_led or 1
            n_pcbs_val = lled.n_pcbs if lled else None
            derived_leds_per_pcb = (total_n // n_pcbs_val) if n_pcbs_val else total_n
            pcb_imax_a = pcb.pcb_imax_led or 1.0
            pcb_imax_ma = pcb_imax_a * 1000

            if user_i_op_a > 0 and pcb_imax_ma >= user_i_op_a * 1000:
                eval_i_op = user_i_op_a * 1000
            else:
                eval_i_op = pcb_imax_ma

            valid = _valid_led_point_at_or_below(
                led,
                eval_i_op,
                t_amb_c=getattr(config, "t_amb_c", 25.0) or 25.0,
                ts_coef_c_per_w=ts_coef,
                n_leds_total=total_n,
            )
            if valid is None:
                continue
            eval_i_op, v2_eval = valid
            led_efficacy = _led_efficacy_before_thermal(v2_eval)
            v_f = v2_eval.vf_v
            p_led = v2_eval.power_w
            max_power_at_eval_i = p_led * total_n
            max_flux_per_led = v2_eval.flux_lm
            thermal_derating = v2_eval.kt

            max_flux_at_eval_i = max_flux_per_led * total_n * lente_eff_val * difusor_eff_val

            if max_flux_at_eval_i < target_flux and not manual:
                continue
            lm_w_min = getattr(config, "lm_w_min", None)

            if max_flux_at_eval_i >= target_flux:
                actual_i_op, v2_actual = _current_for_target_flux(
                    led,
                    target_flux,
                    eval_i_op,
                    t_amb_c=getattr(config, "t_amb_c", 25.0) or 25.0,
                    ts_coef=ts_coef,
                    total_n=total_n,
                    lente_eff=lente_eff_val,
                    difusor_eff=difusor_eff_val,
                )
                actual_v_f = v2_actual.vf_v
                actual_p_led = v2_actual.power_w
                actual_power = actual_p_led * total_n
                th2 = v2_actual.kt
                actual_flux_per_led = v2_actual.flux_lm
                actual_flux = actual_flux_per_led * total_n * lente_eff_val * difusor_eff_val
                actual_led_efficacy = _led_efficacy_before_thermal(v2_actual)
            elif manual:
                actual_i_op = eval_i_op
                actual_v_f, actual_p_led = v_f, p_led
                actual_power = max_power_at_eval_i
                th2 = thermal_derating
                actual_flux = max_flux_at_eval_i
                actual_led_efficacy = led_efficacy
            else:
                continue

            i_op_ok = actual_i_op <= pcb_imax_ma
            final_flux = actual_flux
            final_eff = final_flux / actual_power if actual_power > 0 else 0
            lm_w_ok = lm_w_min is None or final_eff * driver_eff >= lm_w_min

            working.append({
                "lled": lled, "pcb": pcb, "led": led,
                "total_n": total_n,
                "n_pcbs_val": n_pcbs_val, "n_leds_per_pcb_val": derived_leds_per_pcb,
                "i_op": actual_i_op, "v_f": actual_v_f,
                "p_led": actual_p_led, "power": actual_power,
                "flux": final_flux, "efficiency": final_eff,
                "driver_eff": driver_eff,
                "led_efficacy": actual_led_efficacy, "thermal_derating": th2,
                "lente_eff": lente_eff_val, "difusor_eff": difusor_eff_val,
                "i_op_ok": i_op_ok, "lm_w_ok": lm_w_ok,
            })

        if not working:
            return None
        sel = min(
            (w for w in working if w["lm_w_ok"] or manual),
            key=lambda w: w["total_n"],
            default=None,
        )
        if sel is None:
            return None

        return FluxDetail(
            gama=config.gama, difusor=config.difusor, lente=config.lente, led_type=config.led_type,
            pcb_ref=sel["pcb"].pcb_ref, pcb_descripcion=sel["pcb"].pcb_descripcion,
            pcb_v_nominal=sel["pcb"].pcb_v_nominal, pcb_imax_led=sel["pcb"].pcb_imax_led,
            pcb_no_led=sel["pcb"].pcb_no_led,
            n_pcbs=sel["n_pcbs_val"], n_leds_per_pcb=sel["n_leds_per_pcb_val"],
            total_n_leds=sel["total_n"],
            led_ref=sel["led"].led_ref if sel["led"] else None,
            flux=round(sel["flux"], 1),
            efficiency=round(sel["efficiency"], 1),
            led_efficacy=round(sel["led_efficacy"], 2),
            lente_eficiencia=round(sel["lente_eff"], 4) if sel["lente_eff"] is not None else None,
            difusor_eficiencia=round(sel["difusor_eff"], 4) if sel["difusor_eff"] is not None else None,
            thermal_derating=round(sel["thermal_derating"], 4),
            v_f=round(sel["v_f"], 3), p_led=round(sel["p_led"], 3),
            p_total=round(sel["power"], 2),
            i_op_ma=round(sel["i_op"], 1),
            user_i_op_ma=getattr(config, "i_op_ma", None), user_lm_w_min=getattr(config, "lm_w_min", None),
            i_op_ok=sel["i_op_ok"], lm_w_ok=sel["lm_w_ok"],
            driver_eficiencia=sel["driver_eff"],
            available_pcbs=available_pcbs,
        )

    # --- Power-driven mode (original behaviour) ---
    selected_pcb_ref = getattr(config, "selected_pcb_ref", None)
    if selected_pcb_ref:
        lled = next(
            (l for l in candidates if l.pcb and _norm(l.pcb.pcb_ref) == _norm(selected_pcb_ref)),
            None,
        )
        if lled is None:
            pcb = db.query(PCB).filter(PCB.pcb_ref.ilike(_norm(selected_pcb_ref))).first()
            if pcb is None or not available_pcbs:
                return None
            lled = candidates[0] if candidates else None
            total_n = pcb.pcb_no_led or 0
            led = lled.led if lled else None
            n_pcbs_val = None
            n_leds_per_pcb_val = None
        else:
            pcb = lled.pcb
            led = lled.led
            total_n = lled.n_leds_per_pcb or pcb.pcb_no_led or 1
            n_pcbs_val = lled.n_pcbs
            n_leds_per_pcb_val = (total_n // n_pcbs_val) if n_pcbs_val else total_n
    else:
        if user_i_op_a > 0:
            fitting = [l for l in candidates if _imax(l) >= user_i_op_a]
            if fitting:
                lled = min(fitting, key=lambda l: _imax(l))
            else:
                lled = max(candidates, key=lambda l: _imax(l))
        else:
            lled = min(candidates, key=lambda l: _imax(l))
        pcb = lled.pcb
        led = lled.led
        if pcb is None or led is None:
            return None
        total_n = lled.n_leds_per_pcb or pcb.pcb_no_led or 1
        n_pcbs_val = lled.n_pcbs
        n_leds_per_pcb_val = (total_n // n_pcbs_val) if n_pcbs_val else total_n

    i_op = getattr(config, "i_op_ma", None) or (pcb.pcb_imax_led * 1000 if pcb.pcb_imax_led else 500)
    driver_eff = getattr(config, "driver_eficiencia", None) or 1.0

    ts_coef = _ts_coef(db, gama_obj, dif)
    valid = _valid_led_point_at_or_below(
        led, i_op,
        t_amb_c=getattr(config, "t_amb_c", 25.0) or 25.0,
        ts_coef_c_per_w=ts_coef,
        n_leds_total=total_n,
    )
    if valid is None:
        return None
    i_op, v2_point = valid
    led_efficacy = _led_efficacy_before_thermal(v2_point)
    thermal_derating = v2_point.kt
    v_f = v2_point.vf_v
    p_led = v2_point.power_w
    flux = v2_point.flux_lm * total_n

    lente_eff = db.query(Lente.eficiencia).filter(Lente.name.ilike(lnt)).scalar()
    if lente_eff is not None:
        flux *= lente_eff
    difusor_eff = db.query(Difusor.eficiencia).filter(Difusor.name.ilike(dif)).scalar()
    if difusor_eff is not None:
        flux *= difusor_eff
    config_power = getattr(config, "power", None) or 0
    efficiency = round(flux / float(config_power), 1) if config_power else 0

    i_op_ok = pcb.pcb_imax_led is None or i_op <= pcb.pcb_imax_led * 1000
    lm_w_min = getattr(config, "lm_w_min", None)
    lm_w_ok = lm_w_min is None or efficiency * driver_eff >= lm_w_min

    return FluxDetail(
        gama=config.gama, difusor=config.difusor, lente=config.lente, led_type=config.led_type,
        pcb_ref=pcb.pcb_ref, pcb_descripcion=pcb.pcb_descripcion,
        pcb_v_nominal=pcb.pcb_v_nominal, pcb_imax_led=pcb.pcb_imax_led,
        pcb_no_led=pcb.pcb_no_led,
        n_pcbs=n_pcbs_val, n_leds_per_pcb=n_leds_per_pcb_val,
        total_n_leds=total_n,
        led_ref=led.led_ref if led else None,
        flux=round(flux, 1), efficiency=efficiency,
        led_efficacy=round(led_efficacy, 2), lente_eficiencia=round(lente_eff, 4) if lente_eff is not None else None,
        difusor_eficiencia=round(difusor_eff, 4) if difusor_eff is not None else None,
        thermal_derating=round(thermal_derating, 4),
        v_f=round(v_f, 3), p_led=round(p_led, 3),
        p_total=round(p_led * total_n, 2),
        i_op_ma=i_op, user_i_op_ma=getattr(config, "i_op_ma", None), user_lm_w_min=lm_w_min,
        i_op_ok=i_op_ok, lm_w_ok=lm_w_ok,
        driver_eficiencia=driver_eff,
        available_pcbs=available_pcbs,
    )
