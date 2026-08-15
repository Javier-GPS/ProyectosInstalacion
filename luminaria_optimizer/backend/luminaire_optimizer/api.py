"""Small HTTP boundary for the independent calculation core."""
from __future__ import annotations

import base64
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .composition import DEFAULT_GROUP_ANGLES_DEG, compose_luminaire
from .hl2x import HL2X_MAX_INPUT_POWER_W, Hl2xModel, calculate_luminaire_operating_point
from .ldt import ldt_diagnostic, ldt_text, parse_ldt_text
from .optimizer import optimize_currents, optimize_currents_symmetric
from .road import RoadScenario, calculate_reference_road, calculate_road, photometric_azimuth_profile
from .r_tables import load_rtable

app = FastAPI(title="SALVI Luminaria Optimizer", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5176", "http://127.0.0.1:5176"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GroupRequest(BaseModel):
    group_ldt_base64: str
    reference_luminaire_ldt_base64: str | None = None
    reference_group_flux_lm: float = Field(default=897.81, gt=0)
    reference_cct_k: int = 4000
    reference_cri: int = 70
    cct_k: int = 4000
    cri: int = 70
    currents_ma: list[float] = Field(min_length=8, max_length=8)
    ambient_temperature_c: float = 25.0
    ts_coefficient_c_per_w: float = Field(default=0.3, ge=0)
    driver_efficiency: float = Field(default=0.9, gt=0, le=1)
    multiplexing_mode: str = "simultaneous"
    display_gamma_deg: float = Field(default=45.0, ge=0, le=180)


class LdtInspectRequest(BaseModel):
    group_ldt_base64: str


class RoadRequest(GroupRequest):
    rtable_base64: str
    rtable_name: str = "C2"
    height_m: float = Field(gt=0)
    spacing_m: float = Field(gt=0)
    carriageway_width_m: float = Field(default=3.5, gt=0)
    lane_widths_m: list[float] = Field(default_factory=lambda: [3.5], min_length=1)
    arrangement: str = "unilateral"
    pole_side: str = "left"
    arm_length_m: float = Field(default=0.0, ge=0)
    edge_offset_m: float = Field(default=0.5, ge=0)
    tilt_deg: float = Field(default=0.0, ge=-10.0, le=10.0)
    maintenance_factor: float = Field(default=0.85, gt=0, le=1)
    lighting_class: str = "M3"
    optimization_mode: str = "independent"
    photometry_symmetry: str = "asymmetric"


def _decode_text(value: str, label: str) -> str:
    try:
        return base64.b64decode(value).decode("latin-1")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"invalid base64 for {label}") from exc


def _reference_ldt(request: GroupRequest):
    if not request.reference_luminaire_ldt_base64:
        return None
    return parse_ldt_text(
        _decode_text(request.reference_luminaire_ldt_base64, "reference_luminaire_ldt"),
    )


def _model(request: GroupRequest, group_ldt):
    return Hl2xModel(
        reference_group_flux_lm=request.reference_group_flux_lm or group_ldt.flux_lm,
        reference_cct_k=request.reference_cct_k,
        reference_cri=request.reference_cri,
        ambient_temperature_c=request.ambient_temperature_c,
        ts_coefficient_c_per_w=request.ts_coefficient_c_per_w,
        driver_efficiency=request.driver_efficiency,
        multiplexing_mode=request.multiplexing_mode,
    )


def _point_response(point):
    return {
        "currents_ma": list(point.currents_ma),
        "groups": [group.__dict__ for group in point.groups],
        "solder_temperature_c": point.solder_temperature_c,
        "total_led_power_w": point.total_led_power_w,
        "total_driver_power_w": point.total_driver_power_w,
        "total_flux_lm": point.total_flux_lm,
        "converged": point.converged,
        "max_input_power_w": HL2X_MAX_INPUT_POWER_W,
        "power_limit_ok": point.power_limit_ok,
    }


def _profile_response(group_ldt, operating_point, gamma_deg, *, symmetric=False):
    return photometric_azimuth_profile(
        group_ldt,
        operating_point,
        gamma_deg=gamma_deg,
        symmetric=symmetric,
    )


def _result_photometry(group_ldt, operating_point, *, cct_k: int, cri: int, symmetric: bool = False) -> dict[str, object]:
    composed = compose_luminaire(
        group_ldt, operating_point, symmetric=symmetric,
        c_step_deg=5.0, gamma_step_deg=5.0, cct_k=cct_k, cri=cri,
    )
    return ldt_diagnostic(composed)


@app.post("/api/ldt/inspect")
def inspect_ldt(request: LdtInspectRequest):
    try:
        return ldt_diagnostic(parse_ldt_text(_decode_text(request.group_ldt_base64, "group_ldt")))
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "salvi-luminaria-optimizer"}


@app.post("/api/group/operating-point")
def operating_point(request: GroupRequest):
    try:
        ldt = parse_ldt_text(_decode_text(request.group_ldt_base64, "group_ldt"))
        point = calculate_luminaire_operating_point(request.currents_ma, _model(request, ldt), request.cct_k, request.cri)
        return _point_response(point)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/luminaire/compose")
def compose(request: GroupRequest):
    try:
        ldt = parse_ldt_text(_decode_text(request.group_ldt_base64, "group_ldt"))
        point = calculate_luminaire_operating_point(request.currents_ma, _model(request, ldt), request.cct_k, request.cri)
        composed = compose_luminaire(ldt, point, cct_k=request.cct_k, cri=request.cri)
        encoded = base64.b64encode(ldt_text(composed).encode("latin-1")).decode("ascii")
        return {
            "operating_point": _point_response(point),
            "ldt_base64": encoded,
            "ldt_metadata": {
                "name": composed.name,
                "flux_lm": composed.flux_lm,
                "power_w": composed.power_w,
                "group_angles_deg": list(DEFAULT_GROUP_ANGLES_DEG),
            },
        }
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/optimize")
def optimize(request: RoadRequest):
    try:
        ldt = parse_ldt_text(_decode_text(request.group_ldt_base64, "group_ldt"))
        reference_ldt = _reference_ldt(request)
        with tempfile.NamedTemporaryFile(suffix=".rtb", delete=False) as handle:
            handle.write(base64.b64decode(request.rtable_base64))
            rtable_path = Path(handle.name)
        try:
            table = load_rtable(rtable_path, name=request.rtable_name)
        finally:
            rtable_path.unlink(missing_ok=True)
        model = _model(request, ldt)
        scenario = RoadScenario(
            height_m=request.height_m,
            spacing_m=request.spacing_m,
            carriageway_width_m=request.carriageway_width_m,
            lane_widths_m=tuple(request.lane_widths_m),
            arrangement=request.arrangement,
            pole_side=request.pole_side,
            arm_length_m=request.arm_length_m,
            edge_offset_m=request.edge_offset_m,
            tilt_deg=request.tilt_deg,
            maintenance_factor=request.maintenance_factor,
            lighting_class=request.lighting_class,
            photometry_symmetry=request.photometry_symmetry,
        )
        if request.optimization_mode == "symmetric":
            result = optimize_currents_symmetric(
                ldt, model, scenario, table, cct_k=request.cct_k, cri=request.cri,
            )
        elif request.optimization_mode == "independent":
            result = optimize_currents(
                ldt, model, scenario, table, cct_k=request.cct_k, cri=request.cri,
            )
        else:
            raise ValueError("optimization_mode must be symmetric or independent")
        reference_road = (
            calculate_reference_road(reference_ldt, scenario, table)
            if reference_ldt is not None else None
        )
        return {
            "feasible": result.feasible,
            "currents_ma": list(result.currents_ma),
            "iterations": result.iterations,
            "message": result.message,
            "operating_point": _point_response(result.calculation.operating_point),
            "metrics": result.calculation.metrics.__dict__,
            "visual_grid": result.calculation.visual_grid,
            "photometric_profile": _profile_response(
                ldt, result.calculation.operating_point, request.display_gamma_deg,
                symmetric=request.photometry_symmetry == "symmetric",
            ),
            "group_ldt": ldt_diagnostic(ldt),
            "luminaire_ldt": _result_photometry(
                ldt, result.calculation.operating_point, cct_k=request.cct_k, cri=request.cri,
                symmetric=request.photometry_symmetry == "symmetric",
            ),
            "reference_luminaire_ldt": ldt_diagnostic(reference_ldt) if reference_ldt else None,
            "reference_road": {
                "metrics": reference_road.metrics.__dict__,
                "visual_grid": reference_road.visual_grid,
            } if reference_road else None,
        }
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/road/calculate")
def road_calculate(request: RoadRequest):
    """Evaluate a supplied eight-channel profile without optimizing it."""
    try:
        ldt = parse_ldt_text(_decode_text(request.group_ldt_base64, "group_ldt"))
        reference_ldt = _reference_ldt(request)
        with tempfile.NamedTemporaryFile(suffix=".rtb", delete=False) as handle:
            handle.write(base64.b64decode(request.rtable_base64))
            rtable_path = Path(handle.name)
        try:
            table = load_rtable(rtable_path, name=request.rtable_name)
        finally:
            rtable_path.unlink(missing_ok=True)
        scenario = RoadScenario(
            height_m=request.height_m, spacing_m=request.spacing_m,
            carriageway_width_m=request.carriageway_width_m,
            lane_widths_m=tuple(request.lane_widths_m), arrangement=request.arrangement,
            pole_side=request.pole_side, arm_length_m=request.arm_length_m,
            edge_offset_m=request.edge_offset_m,
            tilt_deg=request.tilt_deg, maintenance_factor=request.maintenance_factor,
            lighting_class=request.lighting_class,
            photometry_symmetry=request.photometry_symmetry,
        )
        result = calculate_road(
            ldt, _model(request, ldt), request.currents_ma, scenario, table,
            cct_k=request.cct_k, cri=request.cri,
        )
        reference_road = (
            calculate_reference_road(reference_ldt, scenario, table)
            if reference_ldt is not None else None
        )
        return {
            "currents_ma": list(result.operating_point.currents_ma),
            "operating_point": _point_response(result.operating_point),
            "metrics": result.metrics.__dict__,
            "visual_grid": result.visual_grid,
            "photometric_profile": _profile_response(
                ldt, result.operating_point, request.display_gamma_deg,
                symmetric=request.photometry_symmetry == "symmetric",
            ),
            "group_ldt": ldt_diagnostic(ldt),
            "luminaire_ldt": _result_photometry(
                ldt, result.operating_point, cct_k=request.cct_k, cri=request.cri,
                symmetric=request.photometry_symmetry == "symmetric",
            ),
            "reference_luminaire_ldt": ldt_diagnostic(reference_ldt) if reference_ldt else None,
            "reference_road": {
                "metrics": reference_road.metrics.__dict__,
                "visual_grid": reference_road.visual_grid,
            } if reference_road else None,
        }
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
