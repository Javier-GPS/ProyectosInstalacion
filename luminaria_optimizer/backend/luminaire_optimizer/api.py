"""Small HTTP boundary for the independent calculation core."""
from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from zipfile import BadZipFile, ZipFile

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .composition import compose_luminaire, scale_ldt_runtime
from .assistant import advise
from .geometry import GeometryError, load_step_geometry
from .hl2x import HL2X_MAX_INPUT_POWER_W, Hl2xModel, calculate_luminaire_operating_point
from .ldt import ldt_diagnostic, ldt_text, parse_ldt_text
from .optimizer import optimize_currents_and_tilt
from .optical import MAX_PREVIEW_RAY_COUNT, trace_tm25
from .ray_photometry import rays_to_ldt
from .rayset import Tm25Error, parse_tm25
from .road import RoadScenario, calculate_reference_road, calculate_road, photometric_azimuth_profile
from .r_tables import load_rtable
from .solidworks_session import SolidWorksError, SolidWorksSessionManager

app = FastAPI(title="SALVI Luminaria Optimizer", version="0.1.0")
cad_sessions = SolidWorksSessionManager()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5176", "http://127.0.0.1:5176", "http://[::1]:5176"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GroupRequest(BaseModel):
    group_ldt_base64: str
    reference_luminaire_ldt_base64: str | None = None
    reference_group_flux_lm: float | None = Field(default=None, gt=0)
    reference_cct_k: int = 4000
    reference_cri: int = 70
    cct_k: int = 4000
    cri: int = 70
    currents_ma: list[float] = Field(min_length=1, max_length=32)
    module_count: int = Field(default=8, ge=1, le=32)
    module_angle_step_deg: float = Field(default=22.5, gt=0, le=180)
    luminaire_mode: Literal["modular", "fixed"] = "modular"
    global_current_ma: float = Field(default=700.0, ge=0, le=2000)
    leds_per_group: int = Field(default=1, ge=1, le=3)
    ambient_temperature_c: float = 25.0
    ts_coefficient_c_per_w: float = Field(default=0.3, ge=0)
    driver_efficiency: float = Field(default=0.9, gt=0, le=1)
    multiplexing_mode: str = "simultaneous"
    display_gamma_deg: float = Field(default=45.0, ge=0, le=180)


class LdtInspectRequest(BaseModel):
    group_ldt_base64: str


class GeometryTraceRequest(BaseModel):
    step_base64: str
    rayset_base64: str | None = None
    step_filename: str = "lens.step"
    rayset_filename: str = "source.tm25ray"
    sample_count: int = Field(default=10_000, gt=0, le=5_000_000)
    chunk_size: int = Field(default=10_000, gt=0, le=100_000)
    lens_index: float = Field(default=1.49, gt=1.0, le=3.0)
    preview_ray_count: int = Field(default=5_000, gt=0, le=MAX_PREVIEW_RAY_COUNT)
    c_mirror: bool = True
    c_offset_deg: float = 0.0


class CadOpenRequest(BaseModel):
    cad_base64: str
    cad_filename: str = "lens.SLDPRT"


class CadUpdateRequest(BaseModel):
    session_id: str
    parameter_values: dict[str, float] = Field(default_factory=dict)


class CadPreviewRequest(CadUpdateRequest):
    sample_count: int = Field(default=10_000, gt=0, le=5_000_000)
    chunk_size: int = Field(default=10_000, gt=0, le=100_000)
    lens_index: float = Field(default=1.49, gt=1.0, le=3.0)
    preview_ray_count: int = Field(default=5_000, gt=0, le=MAX_PREVIEW_RAY_COUNT)
    c_mirror: bool = True
    c_offset_deg: float = 0.0


class AutonomousCadRequest(CadOpenRequest):
    """Bounded, unattended CAD exploration before the road-current stage."""

    lens_index: float = Field(default=1.49, gt=1.0, le=3.0)
    height_m: float = Field(default=1.0, gt=0)
    carriageway_width_m: float = Field(default=3.5, gt=0)
    edge_offset_m: float = Field(default=0.5, ge=0)
    exploration_ray_count: int = Field(default=500, ge=500, le=20_000)
    final_ray_count: int = Field(default=20_000, ge=10_000, le=5_000_000)
    parameter_budget: int = Field(default=4, ge=1, le=12)
    focus_recent_feature: bool = False
    show_in_solidworks: bool = True
    keep_solidworks_open: bool = True


class OptimizerChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=40)
    context: dict[str, Any] = Field(default_factory=dict)
    image_base64: str | None = Field(default=None, max_length=7_000_000)
    image_name: str | None = Field(default=None, max_length=255)


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


def _decode_binary(value: str, label: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"invalid base64 for {label}") from exc


def _default_rayset_path() -> Path:
    configured = os.environ.get("SALVI_DEFAULT_RAYSET_PATH")
    candidates = [
        Path(configured) if configured else None,
        Path(__file__).resolve().parents[2] / "LUXEON HL2Z_5000000Rays_IESTM25.tm25ray",
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate
    raise GeometryError("default HL2Z TM-25 ray file was not found")


def _models_lenses_path() -> Path:
    return Path(__file__).resolve().parents[2] / "modelos lentes"


def _default_cad_path() -> Path:
    path = _models_lenses_path() / "ensamblaje lente dot led.SLDASM"
    if not path.is_file():
        raise GeometryError("default SolidWorks assembly was not found")
    return path


def _default_rtable_path() -> Path:
    path = Path(__file__).resolve().parents[2] / "C2 je_Gerli__edited.rtb"
    if not path.is_file():
        raise GeometryError("default C2 reflection table was not found")
    return path


def _history_path(root: Path, stem: str, suffix: str) -> Path:
    """Return a unique timestamped candidate path without overwriting history."""
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Avoid recursively appending candidate timestamps: SolidWorks rejects long
    # SaveAs paths with swFileSaveAsNameExceedsMaxPathLength (2048).
    base_stem = re.sub(r"(?:_candidate_\d{8}_\d{6}(?:_\d{2})?)+$", "", stem, flags=re.IGNORECASE)
    base_stem = (base_stem[:64].rstrip(" .") or "lens")
    candidate = root / f"{base_stem}_candidate_{stamp}{suffix}"
    counter = 2
    while candidate.exists():
        candidate = root / f"{base_stem}_candidate_{stamp}_{counter:02d}{suffix}"
        counter += 1
    return candidate


def _reference_ldt(request: GroupRequest):
    if not request.reference_luminaire_ldt_base64:
        return None
    return parse_ldt_text(
        _decode_text(request.reference_luminaire_ldt_base64, "reference_luminaire_ldt"),
    )


def _model(request: GroupRequest, group_ldt):
    if request.luminaire_mode == "modular" and request.leds_per_group != 3:
        raise ValueError("La variante angular requiere una lente de grupo con 3 LED")
    group_count = request.module_count
    if request.luminaire_mode == "fixed":
        currents = [request.global_current_ma] * group_count
    else:
        currents = request.currents_ma
    if len(currents) != group_count:
        raise ValueError("currents_ma length must match module_count")
    return Hl2xModel(
        reference_group_flux_lm=request.reference_group_flux_lm or group_ldt.flux_lm,
        reference_cct_k=request.reference_cct_k,
        reference_cri=request.reference_cri,
        ambient_temperature_c=request.ambient_temperature_c,
        ts_coefficient_c_per_w=request.ts_coefficient_c_per_w,
        driver_efficiency=request.driver_efficiency,
        multiplexing_mode=request.multiplexing_mode,
        group_count=group_count,
        leds_per_group=request.leds_per_group,
    )


def _currents(request: GroupRequest) -> list[float]:
    return [request.global_current_ma] * request.module_count if request.luminaire_mode == "fixed" else request.currents_ma


def _module_angles(request: GroupRequest) -> tuple[float, ...]:
    if request.luminaire_mode == "fixed":
        return (90.0,) * request.module_count
    last_angle = (request.module_count - 0.5) * request.module_angle_step_deg
    if last_angle > 180.0 + 1e-9:
        raise ValueError("module_count and module_angle_step_deg must fit within C0-C180")
    return tuple(
        (index + 0.5) * request.module_angle_step_deg
        for index in range(request.module_count)
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


def _profile_response(group_ldt, operating_point, gamma_deg, *, angles_deg, symmetric=False):
    return photometric_azimuth_profile(
        group_ldt,
        operating_point,
        gamma_deg=gamma_deg,
        symmetric=symmetric,
        angles_deg=angles_deg,
    )


def _result_luminaire_ldt(group_ldt, operating_point, *, angles_deg, cct_k: int, cri: int, symmetric: bool = False, fixed: bool = False):
    if fixed:
        return scale_ldt_runtime(group_ldt, operating_point.total_flux_lm, operating_point.total_driver_power_w)
    return compose_luminaire(
        group_ldt, operating_point, angles_deg=angles_deg, symmetric=symmetric,
        c_step_deg=1.0, gamma_step_deg=1.0, cct_k=cct_k, cri=cri,
    )


def _result_luminaire_response(group_ldt, operating_point, *, angles_deg, cct_k: int, cri: int, symmetric: bool = False, fixed: bool = False) -> dict[str, object]:
    luminaire_ldt = _result_luminaire_ldt(
        group_ldt, operating_point, angles_deg=angles_deg, cct_k=cct_k, cri=cri,
        symmetric=symmetric, fixed=fixed,
    )
    return {
        "luminaire_ldt": ldt_diagnostic(luminaire_ldt),
        "luminaire_ldt_base64": base64.b64encode(ldt_text(luminaire_ldt).encode("latin-1")).decode("ascii"),
        "luminaire_ldt_metadata": {
            "name": luminaire_ldt.name,
            "flux_lm": luminaire_ldt.flux_lm,
            "power_w": luminaire_ldt.power_w,
            "group_angles_deg": list(angles_deg),
        },
    }


def _trace_geometry_paths(step_path: Path, rayset_path: Path, request: GeometryTraceRequest) -> dict[str, object]:
    return _trace_geometry(load_step_geometry(step_path), rayset_path, request)


def _trace_geometry(geometry, rayset_path: Path, request: GeometryTraceRequest) -> dict[str, object]:
    """Trace any geometry implementing the lens-mesh contract."""
    ray_set = parse_tm25(rayset_path)
    try:
        trace = trace_tm25(
            ray_set,
            geometry,
            sample_count=request.sample_count,
            chunk_size=request.chunk_size,
            lens_index=request.lens_index,
            preview_ray_count=request.preview_ray_count,
            c_mirror=request.c_mirror,
            c_offset_deg=request.c_offset_deg,
        )
        photometry = rays_to_ldt(
            trace,
            c_step_deg=5.0,
            gamma_step_deg=1.0,
            c_offset_deg=request.c_offset_deg,
            c_mirror=request.c_mirror,
            enforce_c_symmetry=True,
        )
        preview = trace.transmitted_rays
        if len(preview) > request.preview_ray_count:
            indices = np.linspace(0, len(preview) - 1, request.preview_ray_count, dtype=int)
            preview = preview[indices]
        return {
            "geometry": geometry.diagnostic(),
            "trace": trace.diagnostic(),
            "ldt": ldt_diagnostic(photometry),
            "ldt_base64": base64.b64encode(ldt_text(photometry).encode("latin-1")).decode("ascii"),
            "preview_rays": preview.tolist(),
            "preview_rays_detail": list(trace.preview_rays_detail),
            "preview_geometry_mesh": geometry.mesh_payload(),
            "ray_angle_config": {
                "c_mirror": request.c_mirror,
                "c_offset_deg": request.c_offset_deg,
                "gamma_flip": False,
                "c_convention": "canonical optical frame: projected world X is C0, then c_mirror and c_offset_deg",
                "gamma_convention": "canonical optical frame: LED emission normal is +Z, gamma=acos(z)",
            },
        }
    finally:
        ray_set.close()


def _road_target_direction(request: AutonomousCadRequest) -> np.ndarray:
    """Aim the lens at the useful half of the configured carriageway."""
    lateral_distance = request.edge_offset_m + request.carriageway_width_m / 2.0
    elevation = float(np.arctan2(request.height_m, lateral_distance))
    return np.array([0.0, np.cos(elevation), np.sin(elevation)], dtype=float)


def _road_direction_score(trace_response: dict[str, object], target: np.ndarray) -> float:
    """Rank candidates by transmitted flux concentrated toward the road target."""
    rays = trace_response.get("preview_rays_detail", [])
    aligned_flux = 0.0
    transmitted_flux = 0.0
    for ray in rays if isinstance(rays, list) else []:
        if not isinstance(ray, dict) or ray.get("status") != "transmitted":
            continue
        direction = ray.get("direction_xyz")
        if not isinstance(direction, list) or len(direction) != 3:
            continue
        vector = np.asarray(direction, dtype=float)
        norm = float(np.linalg.norm(vector))
        if norm <= 1e-9:
            continue
        flux = float(ray.get("transmitted_power_lm", 0.0))
        transmitted_flux += flux
        aligned_flux += flux * max(0.0, float(np.dot(vector / norm, target))) ** 4
    alignment = aligned_flux / transmitted_flux if transmitted_flux else 0.0
    transmission = float((trace_response.get("trace") or {}).get("transmission_pct", 0.0)) / 100.0
    return 0.8 * alignment + 0.2 * transmission


def _build_sldprt_assembly(lens_path: Path, target_path: Path) -> None:
    """Place a native L8 part into the established three-LED STEP frame."""
    try:
        import cadquery as cq
    except ImportError as exc:
        raise SolidWorksError("La previsualización CAD requiere las dependencias de geometría.") from exc
    assembly_path = Path(__file__).resolve().parents[2] / "ensamblaje lente dot led.STEP"
    if not assembly_path.is_file():
        raise SolidWorksError(f"No se encuentra el ensamblaje de referencia: {assembly_path}")
    source = cq.importers.importStep(str(assembly_path))
    solids = tuple(source.solids().vals())
    old_lens = max(solids, key=lambda solid: solid.Volume())
    leds = [solid for solid in solids if solid is not old_lens]
    imported_lens = cq.importers.importStep(str(lens_path))
    lens = max(tuple(imported_lens.solids().vals()), key=lambda solid: solid.Volume())
    lens = lens.transformGeometry(cq.Matrix([[0, 0, 1, 0], [0, 1, 0, 0], [-1, 0, 0, 0]]))
    cq.exporters.export(cq.Compound.makeCompound([lens, *leds]), str(target_path))


def _extract_cad_archive(archive_path: Path, target_root: Path, extension: str) -> None:
    """Extract a CAD package while rejecting archive path traversal."""
    if extension == ".zip":
        archive_factory = ZipFile
    else:
        try:
            import rarfile
        except ImportError as exc:
            raise SolidWorksError("La carga RAR requiere instalar la dependencia rarfile.") from exc
        archive_factory = rarfile.RarFile
    try:
        with archive_factory(archive_path) as archive:
            members = archive.infolist()
            for member in members:
                name = Path(member.filename)
                if name.is_absolute() or ".." in name.parts:
                    raise SolidWorksError("El archivo comprimido contiene rutas no válidas.")
            try:
                archive.extractall(target_root)
            except Exception:
                if extension != ".rar":
                    raise
                _extract_rar_with_7zip(archive_path, target_root)
    except SolidWorksError:
        raise
    except Exception as exc:
        raise SolidWorksError(f"No se pudo extraer el paquete CAD: {exc}") from exc


def _extract_rar_with_7zip(archive_path: Path, target_root: Path) -> None:
    tools = [
        shutil.which("7z"),
        shutil.which("7z.exe"),
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
    ]
    tool = next((candidate for candidate in tools if candidate and Path(candidate).is_file()), None)
    if tool is None:
        raise SolidWorksError("No se encuentra 7-Zip/UnRAR para extraer el archivo RAR.")
    result = subprocess.run(
        [tool, "x", str(archive_path), f"-o{target_root}", "-y"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "error desconocido"
        raise SolidWorksError(f"7-Zip no pudo extraer el paquete RAR: {detail}")


@app.post("/api/ldt/inspect")
def inspect_ldt(request: LdtInspectRequest):
    try:
        return ldt_diagnostic(parse_ldt_text(_decode_text(request.group_ldt_base64, "group_ldt")))
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/optimizer/chat")
def optimizer_chat(request: OptimizerChatRequest):
    """Discuss optical strategies with an optional annotated CAD sketch."""
    try:
        context = {
            **request.context,
            "image_attached": bool(request.image_base64),
            "image_name": request.image_name or "croquis adjunto",
        }
        return advise(request.message, context)
    except (TypeError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/geometry/trace")
def geometry_trace(request: GeometryTraceRequest):
    """Trace a STEP lens and return a generated group LDT plus preview rays."""
    try:
        step_data = _decode_binary(request.step_base64, "step")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            step_path = root / Path(request.step_filename).name
            step_path.write_bytes(step_data)
            if request.rayset_base64:
                rayset_path = root / Path(request.rayset_filename).name
                rayset_path.write_bytes(_decode_binary(request.rayset_base64, "rayset"))
            else:
                rayset_path = _default_rayset_path()
            return _trace_geometry_paths(step_path, rayset_path, request)
    except (GeometryError, Tm25Error, ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _cad_open(request: CadOpenRequest, *, visible: bool = False):
    """Open a native SLDPRT/SLDASM package in a persistent SolidWorks session."""
    extension = Path(request.cad_filename).suffix.lower()
    if extension not in {".sldprt", ".sldasm", ".zip", ".rar"}:
        raise HTTPException(status_code=422, detail="El modo CAD requiere SLDPRT, SLDASM, ZIP o RAR.")
    source_root: Path | None = None
    try:
        source_root = Path(tempfile.mkdtemp(prefix="salvi-cad-upload-"))
        upload_path = source_root / Path(request.cad_filename).name
        upload_path.write_bytes(_decode_binary(request.cad_base64, "cad"))
        document_root: Path = source_root
        if extension in {".zip", ".rar"}:
            package_root = source_root / "package"
            package_root.mkdir()
            _extract_cad_archive(upload_path, package_root, extension)
            candidates = sorted(
                (path for path in package_root.rglob("*") if path.is_file() and path.suffix.lower() == ".sldasm"),
                key=lambda path: (len(path.parts), path.name.lower()),
            )
            if not candidates:
                candidates = sorted(
                    (path for path in package_root.rglob("*") if path.is_file() and path.suffix.lower() == ".sldprt"),
                    key=lambda path: (len(path.parts), path.name.lower()),
                )
            if not candidates:
                raise SolidWorksError("El archivo comprimido no contiene ningún SLDASM o SLDPRT.")
            source_path = candidates[0]
        elif extension == ".sldasm":
            stored_assembly = _models_lenses_path() / Path(request.cad_filename).name
            if stored_assembly.is_file():
                source_path = stored_assembly
                document_root = _models_lenses_path()
            else:
                source_path = upload_path
        else:
            source_path = upload_path
        if extension in {".zip", ".rar"}:
            document_root = source_root / "package"
        session_id = cad_sessions.open(source_path, document_root, visible=visible)
        description = cad_sessions.describe(session_id)
        return {"session_id": session_id, **description}
    except (SolidWorksError, OSError, ValueError, BadZipFile) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        if source_root is not None:
            shutil.rmtree(source_root, ignore_errors=True)


@app.post("/api/cad/open")
def cad_open(request: CadOpenRequest):
    """Open a native SLDPRT/SLDASM package in a persistent SolidWorks session."""
    return _cad_open(request)


@app.post("/api/cad/update")
def cad_update(request: CadUpdateRequest):
    try:
        return cad_sessions.update(request.session_id, request.parameter_values)
    except (SolidWorksError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/cad/mesh")
def cad_mesh(request: CadUpdateRequest):
    """Apply CAD dimensions and return a viewer mesh without ray tracing."""
    try:
        if request.parameter_values:
            cad_sessions.update(request.session_id, request.parameter_values)
        description = cad_sessions.describe(request.session_id)
        geometry = cad_sessions.native_geometry(
            request.session_id,
            _models_lenses_path() / "ensamblaje lente dot led.SLDASM",
        )
        return {
            "geometry": geometry.diagnostic(),
            "preview_geometry_mesh": geometry.mesh_payload(),
            "parameters": description["parameters"],
        }
    except (SolidWorksError, GeometryError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/cad/optimize-road-target")
def optimize_cad_road_target(request: AutonomousCadRequest):
    """Explore small CAD changes and retain only a better road-facing lens."""
    session_id = ""
    session_kept_open = False
    try:
        opened = _cad_open(
            CadOpenRequest(cad_base64=request.cad_base64, cad_filename=request.cad_filename),
            visible=request.show_in_solidworks,
        )
        session_id = str(opened["session_id"])
        parameters = list(opened.get("parameters") or [])
        baseline_values = {str(item["name"]): float(item["value"]) for item in parameters}
        target = _road_target_direction(request)

        def trace_current(sample_count: int) -> dict[str, object]:
            geometry = cad_sessions.native_geometry(
                session_id,
                _models_lenses_path() / "ensamblaje lente dot led.SLDASM",
            )
            return _trace_geometry(
                geometry,
                _default_rayset_path(),
                GeometryTraceRequest(
                    step_base64="",
                    step_filename="solidworks-native",
                    sample_count=sample_count,
                    chunk_size=min(10_000, sample_count),
                    lens_index=request.lens_index,
                    # Keep the interactive viewer responsive. The full sample
                    # is still used for LDT generation; only its 3D overlay is bounded.
                    preview_ray_count=min(5_000, sample_count),
                    c_mirror=True,
                ),
            )

        baseline = trace_current(request.exploration_ray_count)
        baseline_score = _road_direction_score(baseline, target)
        best_score = baseline_score
        best_values = dict(baseline_values)
        current_values = dict(baseline_values)
        history: list[dict[str, object]] = []
        # SolidWorks exposes feature dimensions but not a dependable dimension-to-
        # face map. Screen bounded perturbations instead of guessing a label.
        eligible = [
            item for item in parameters
            if float(item.get("value", 0.0)) != 0.0 and str(item.get("unit")) in {"mm", "deg"}
        ]
        if request.focus_recent_feature:
            # A new wedge is normally appended to the SLDPRT feature tree.
            # Its sketch/extrusion dimensions therefore appear at the end.
            eligible = eligible[-request.parameter_budget:]
        else:
            eligible = eligible[:request.parameter_budget]
        for parameter in eligible:
            name = str(parameter["name"])
            base_value = baseline_values[name]
            delta = (
                np.deg2rad(2.0)
                if parameter.get("unit") == "deg"
                else max(abs(base_value) * 0.03, 0.0001)
            )
            for direction in (-1.0, 1.0):
                candidate_value = base_value + direction * float(delta)
                try:
                    candidate_values = {**baseline_values, name: candidate_value}
                    changes = {
                        key: value for key, value in candidate_values.items()
                        if current_values.get(key) != value
                    }
                    if changes:
                        cad_sessions.update(session_id, changes)
                        current_values = candidate_values
                    candidate = trace_current(request.exploration_ray_count)
                    score = _road_direction_score(candidate, target)
                    history.append({
                        "parameter": name,
                        "feature": parameter.get("feature"),
                        "display_value": candidate_value * (180.0 / np.pi if parameter.get("unit") == "deg" else 1000.0),
                        "unit": parameter.get("unit"),
                        "score": score,
                        "transmission_pct": (candidate.get("trace") or {}).get("transmission_pct", 0.0),
                        "accepted": score > best_score,
                    })
                    if score > best_score:
                        best_score = score
                        best_values = {**baseline_values, name: candidate_value}
                except (SolidWorksError, GeometryError, Tm25Error, ValueError) as exc:
                    history.append({"parameter": name, "feature": parameter.get("feature"), "error": str(exc), "accepted": False})

        changes = {
            key: value for key, value in best_values.items()
            if current_values.get(key) != value
        }
        if changes:
            cad_sessions.update(session_id, changes)
        final_trace = trace_current(request.final_ray_count)
        saved_files: list[str] = []
        save_warning: str | None = None
        if best_values != baseline_values:
            source = Path(str(opened.get("source_filename") or request.cad_filename))
            target_path = _history_path(_models_lenses_path(), source.stem, source.suffix.upper())
            try:
                cad_sessions.export_native_copy(session_id, target_path)
                saved_files.append(str(target_path))
            except SolidWorksError as exc:
                # The optical result is valid even if SolidWorks rejects SaveAs.
                # Return it so the user can inspect and compare the candidate.
                save_warning = str(exc)
        final_trace["saved_cad_files"] = saved_files
        session_kept_open = request.keep_solidworks_open
        return {
            "objective": {
                "target_direction_xyz": target.tolist(),
                "baseline_score": baseline_score,
                "best_score": best_score,
                "baseline_transmission_pct": (baseline.get("trace") or {}).get("transmission_pct", 0.0),
                "best_transmission_pct": (final_trace.get("trace") or {}).get("transmission_pct", 0.0),
                "improved": best_values != baseline_values,
            },
            "history": history,
            "baseline_geometry_trace": baseline,
            "geometry_trace": final_trace,
            "save_warning": save_warning,
            "solidworks_session_id": session_id if session_kept_open else None,
        }
    except HTTPException:
        raise
    except (SolidWorksError, GeometryError, Tm25Error, ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        if session_id and not session_kept_open:
            try:
                cad_sessions.close(session_id)
            except KeyError:
                pass


@app.post("/api/cad/close")
def cad_close(request: CadUpdateRequest):
    try:
        cad_sessions.close(request.session_id)
        return {"closed": True}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/cad/preview")
def cad_preview(request: CadPreviewRequest):
    try:
        if request.parameter_values:
            cad_sessions.update(request.session_id, request.parameter_values)
        description = cad_sessions.describe(request.session_id)
        models_root = _models_lenses_path()
        source_name = Path(str(description["source_filename"]))
        saved_files: list[str] = []
        if description["document_type"] == "part":
            native_lens_path = _history_path(models_root, source_name.stem, source_name.suffix.upper())
            cad_sessions.export_native_copy(request.session_id, native_lens_path)
            saved_files.append(str(native_lens_path))
        geometry = cad_sessions.native_geometry(
            request.session_id,
            models_root / "ensamblaje lente dot led.SLDASM",
        )
        trace_request = GeometryTraceRequest(
            step_base64="",
            step_filename="solidworks-native",
            rayset_base64=None,
            rayset_filename=_default_rayset_path().name,
            sample_count=request.sample_count,
            chunk_size=request.chunk_size,
            lens_index=request.lens_index,
            preview_ray_count=request.preview_ray_count,
            c_mirror=request.c_mirror,
            c_offset_deg=request.c_offset_deg,
        )
        response = _trace_geometry(geometry, _default_rayset_path(), trace_request)
        response["saved_cad_files"] = saved_files
        return response
    except (SolidWorksError, GeometryError, Tm25Error, ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.on_event("shutdown")
def close_cad_sessions() -> None:
    cad_sessions.shutdown()


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "salvi-luminaria-optimizer"}


@app.get("/api/default-resources")
def default_resources():
    """Expose the local road defaults without sending native CAD over HTTP."""
    try:
        cad_path = _default_cad_path()
        rayset_path = _default_rayset_path()
        rtable_path = _default_rtable_path()
        return {
            "cad": {"name": cad_path.name},
            "rayset": {"name": rayset_path.name},
            "rtable": {
                "name": rtable_path.name,
                "base64": base64.b64encode(rtable_path.read_bytes()).decode("ascii"),
            },
        }
    except (GeometryError, OSError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/group/operating-point")
def operating_point(request: GroupRequest):
    try:
        ldt = parse_ldt_text(_decode_text(request.group_ldt_base64, "group_ldt"))
        point = calculate_luminaire_operating_point(_currents(request), _model(request, ldt), request.cct_k, request.cri)
        return _point_response(point)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/luminaire/compose")
def compose(request: GroupRequest):
    try:
        ldt = parse_ldt_text(_decode_text(request.group_ldt_base64, "group_ldt"))
        point = calculate_luminaire_operating_point(_currents(request), _model(request, ldt), request.cct_k, request.cri)
        angles_deg = _module_angles(request)
        composed = (
            scale_ldt_runtime(ldt, point.total_flux_lm, point.total_driver_power_w)
            if request.luminaire_mode == "fixed"
            else compose_luminaire(ldt, point, angles_deg=angles_deg, cct_k=request.cct_k, cri=request.cri)
        )
        encoded = base64.b64encode(ldt_text(composed).encode("latin-1")).decode("ascii")
        return {
            "operating_point": _point_response(point),
            "ldt_base64": encoded,
            "ldt_metadata": {
                "name": composed.name,
                "flux_lm": composed.flux_lm,
                "power_w": composed.power_w,
                "group_angles_deg": list(angles_deg),
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
        angles_deg = _module_angles(request)
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
        result = optimize_currents_and_tilt(
            ldt, model, scenario, table,
            cct_k=request.cct_k, cri=request.cri,
            optimization_mode=request.optimization_mode,
            angles_deg=angles_deg,
            uniform=request.luminaire_mode == "fixed",
        )
        reference_road = (
            calculate_reference_road(reference_ldt, result.calculation.scenario, table)
            if reference_ldt is not None else None
        )
        return {
            "feasible": result.feasible,
            "currents_ma": list(result.currents_ma),
            "relative_currents_ma": list(result.relative_currents_ma),
            "iterations": result.iterations,
            "message": result.message,
            "tilt_deg": result.calculation.scenario.tilt_deg,
            "operating_point": _point_response(result.calculation.operating_point),
            "metrics": result.calculation.metrics.__dict__,
            "visual_grid": result.calculation.visual_grid,
            "photometric_profile": _profile_response(
                ldt, result.calculation.operating_point, request.display_gamma_deg,
                angles_deg=angles_deg,
                symmetric=request.photometry_symmetry == "symmetric",
            ),
            "group_ldt": ldt_diagnostic(ldt),
            **_result_luminaire_response(
                ldt, result.calculation.operating_point, angles_deg=angles_deg, cct_k=request.cct_k, cri=request.cri,
                fixed=request.luminaire_mode == "fixed",
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
    """Evaluate a supplied repeated-module profile without optimizing it."""
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
        angles_deg = _module_angles(request)
        result = calculate_road(
            ldt, _model(request, ldt), _currents(request), scenario, table,
            cct_k=request.cct_k, cri=request.cri,
            angles_deg=angles_deg,
        )
        reference_road = (
            calculate_reference_road(reference_ldt, scenario, table)
            if reference_ldt is not None else None
        )
        return {
            "currents_ma": list(result.operating_point.currents_ma),
            "tilt_deg": result.scenario.tilt_deg,
            "operating_point": _point_response(result.operating_point),
            "metrics": result.metrics.__dict__,
            "visual_grid": result.visual_grid,
            "photometric_profile": _profile_response(
                ldt, result.operating_point, request.display_gamma_deg,
                angles_deg=angles_deg,
                symmetric=request.photometry_symmetry == "symmetric",
            ),
            "group_ldt": ldt_diagnostic(ldt),
            **_result_luminaire_response(
                ldt, result.operating_point, angles_deg=angles_deg, cct_k=request.cct_k, cri=request.cri,
                fixed=request.luminaire_mode == "fixed",
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
