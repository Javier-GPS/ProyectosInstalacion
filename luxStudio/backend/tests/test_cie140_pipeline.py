"""CIE 140 pipeline verification — full calculation trace with intermediate values.

This test exercises the real calculation engine (salvi_lighting.evaluate,
run_calculation, _target_luminaire_info) and dumps every intermediate value
so discrepancies with reference values can be isolated step by step.

Run:  python -m pytest tests/test_cie140_pipeline.py -v -s
"""
from __future__ import annotations

import logging
import math
from pathlib import Path

import pytest

from app.schemas.models import CalculationConfig
from app.services import calculator
from app.services.geometry import effective_overhang, luminaire_mounting_height
from app.salvi_lighting import parse_ldt, Photometry, evaluate, ME_REQ

LDT_DIR = Path(__file__).resolve().parent.parent / "ldt" / "Salvi"
_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Synthetic LDT info (matches what ldt_loader.get_ldt_by_id would return)
# ---------------------------------------------------------------------------

def _ldt_info(path: Path) -> dict:
    return {
        "id": path.stem,
        "filename": path.name,
        "luminaire_name": path.stem.replace("_", " "),
        "manufacturer": "Salvi",
        "model_family": path.stem.split("_")[0],
        "optic_family": next((s for s in path.stem.split("_") if s.startswith("F")), "F151"),
        "power": 100.0,
        "flux": 0,
        "efficiency": 0,
        "cct": 4000,
        "cri": 70,
        "LORL": 100,
        "isym": 0,
        "mf_origen": 1.0,
    }


# ---------------------------------------------------------------------------
# Pipeline steps — each dumps intermediates
# ---------------------------------------------------------------------------


def _dump(step: str, **values):
    print(f"\n--- {step} ---")
    for k, v in values.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.6g}")
        elif isinstance(v, CalculationConfig):
            print(f"  {k}: power={v.power}, flux_target={v.target_flux}, mf={v.mf}")
        else:
            print(f"  {k}: {v}")


def _full_pipeline(config: CalculationConfig, ldt_path: Path, lente_eff: float = 1.0, difusor_eff: float = 1.0):
    _dump("INPUT CONFIG", config=config, ldt_file=ldt_path.name,
          lente_eficiencia=lente_eff, difusor_eficiencia=difusor_eff)

    # 1. Parse LDT
    parsed = parse_ldt(ldt_path)
    photometry = Photometry(parsed)
    _dump("LDT PARSED", power=photometry.power, flux=photometry.flux,
          eff=photometry.flux / photometry.power if photometry.power else 0,
          Mc=photometry.Mc, Ng=photometry.Ng, conv=photometry.conv)

    # 2. Effective maintenance factor
    ldt_info = _ldt_info(ldt_path)
    ldt_info.update(power=photometry.power, flux=photometry.flux,
                    efficiency=round(photometry.flux / max(photometry.power, 0.01), 1))
    effective_mf = calculator._effective_mf(config.mf, ldt_info)
    _dump("MAINTENANCE FACTOR", config_mf=config.mf, mf_origen=ldt_info.get("mf_origen", 1.0),
          effective_mf=effective_mf)

    # 3. Config > Cfg (what the engine receives)
    cfg = calculator._config_to_cfg(config, photometry, ldt_info)
    _dump("CONFIG>CFG", arrangement=cfg["arrangement"], height=cfg["h"],
          spacing=cfg["S"], road_width=cfg["W"], mf=cfg["mf"],
          tilt=cfg["tilt"], lanes=cfg["lanes"])

    # 4. Target luminaire info (flux scaling, efficiency)
    target = calculator._target_luminaire_info(config, photometry, ldt_info,
                                                lente_eficiencia=lente_eff,
                                                difusor_eficiencia=difusor_eff)
    flux_scale = target["flux"] / photometry.flux if photometry.flux else 1.0
    _dump("TARGET LUMINAIRE", power=target["power"],
          led_flux=target["flux"], effective_flux=target["flux"],
          efficiency=target["efficiency"], flux_scale=flux_scale,
          cct_cri=f"{config.cct}/{config.cri}",
          ref_cct_cri=f"{ldt_info.get('cct', 4000)}/{ldt_info.get('cri', 70)}")

    # 5. Evaluate (CIE 140 engine)
    result = evaluate(cfg, photometry, flux_scale=flux_scale, road=config.pavement)
    _dump("EVALUATE RESULT", mode=result.get("mode"),
          compliant=result.get("compliant"),
          Lavg=result.get("Lavg"), Uo=result.get("Uo"), Ul=result.get("Ul"),
          TI=result.get("TI"), SR=result.get("SR"),
          Eavg=result.get("Eavg"), Emin=result.get("Emin"))

    # 6. Requirements (EN 13201 class)
    req = result.get("req", {})
    _dump("CLASS REQUIREMENTS", lighting_class=config.lighting_class,
          L_target=req.get("L"), Uo_target=req.get("Uo"),
          Ul_target=req.get("Ul"), TI_target=req.get("TI"),
          SR_target=req.get("SR"))

    # 7. Criteria
    criteria = calculator._build_criteria(result)
    for c in criteria:
        status = "PASS" if c.passed else "FAIL"
        print(f"  {status} {c.name}: {c.value:.4g} / required {c.required:.4g}")

    # 8. Full CalculationResult
    calc_result = calculator.run_calculation_with_photometry(
        config, photometry, ldt_info, flux_scale=flux_scale,
    )
    return calc_result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_pipeline_with_clap_m_f151():
    """Run the full pipeline with a real CLAP M 100W F151 LDT.

    This is the reference case — trace each step when debugging discrepancies.
    """
    ldt_path = LDT_DIR / "CLAP_M_C35_30K_F151_VDR_SPUW_100W.ldt"
    assert ldt_path.exists(), f"LDT not found: {ldt_path}"

    config = CalculationConfig(
        road_width=7.0, sidewalk_left=0, sidewalk_right=0,
        lanes=2, arrangement="Lineal", height=10.0, spacing=35.0,
        arm_length=1.5, pole_offset=0.5, tilt=5.0,
        optic_family="F151", power=100.0,
        gama="CLAP M", difusor="VDR SPUW", lente="F151", led_type="LUXEON HOP 5050",
        lighting_class="M3", mf=0.85, pavement="R3", cct=4000, cri=70,
    )

    result = _full_pipeline(config, ldt_path)

    assert result.criteria is not None
    assert len([c for c in result.criteria if c.passed]) > 0


def test_pipeline_with_clap_m_f2m2():
    """Variant with F2M2 optic — catches assembly-specific issues."""
    ldt_path = LDT_DIR / "CLAP_M_C35_30K_F2M2_VDR_SPUW_100W.ldt"
    assert ldt_path.exists(), f"LDT not found: {ldt_path}"

    config = CalculationConfig(
        road_width=11.0, sidewalk_left=1.5, sidewalk_right=0,
        lanes=3, arrangement="Bilateral", height=12.0, spacing=40.0,
        arm_length=2.0, pole_offset=1.0, tilt=5.0,
        optic_family="F2M2", power=100.0,
        gama="CLAP M", difusor="VDR SPUW", lente="F2M2", led_type="LUXEON HOP 5050",
        lighting_class="M3", mf=0.85, pavement="R3", cct=4000, cri=70,
    )

    result = _full_pipeline(config, ldt_path)
    assert result.criteria is not None
