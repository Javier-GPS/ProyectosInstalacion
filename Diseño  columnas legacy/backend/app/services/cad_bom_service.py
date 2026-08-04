"""
Salvi Studio · Columns — Servicios Fase 14
CAD paramétrico, BOM y documentación industrial
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4


# ═══════════════════════════════════════════════════════════════════════════════
#  Constantes y tipos base
# ═══════════════════════════════════════════════════════════════════════════════

K_FACTOR_DEFAULT = 0.44          # facteur de déduction pliage St
K_FACTOR_ALUMINUM = 0.40
K_FACTOR_STAINLESS = 0.47
MASS_RECONCILIATION_THRESHOLD = 0.005  # 0.5%
STEEL_DENSITY_KG_M3 = 7850.0
ALUMINUM_DENSITY_KG_M3 = 2700.0
CONCRETE_DENSITY_KG_M3 = 2500.0

DXF_LAYERS = [
    "CUT_OUTER", "CUT_INNER", "BEND_UP", "BEND_DOWN",
    "ETCH", "CENTER", "BEVEL", "NO_CUT",
]

SNAPSHOT_TRANSITIONS: Dict[str, List[str]] = {
    "DRAFT":    ["REVIEW"],
    "REVIEW":   ["APPROVED", "DRAFT"],
    "APPROVED": ["RELEASED", "REVIEW"],
    "RELEASED": ["OBSOLETE"],
    "OBSOLETE": [],
}

CHANGE_CLASS_REQUIRES_RECALC = {
    "EDITORIAL":   False,
    "INDUSTRIAL":  False,
    "GEOMETRIC":   True,
    "STRUCTURAL":  True,
    "REGULATORY":  True,
}

CHANGE_CLASS_EFFORT = {
    "EDITORIAL":   "LOW",
    "INDUSTRIAL":  "LOW",
    "GEOMETRIC":   "MEDIUM",
    "STRUCTURAL":  "HIGH",
    "REGULATORY":  "HIGH",
}

_ALUMINUM_KEYWORDS = ("AL", "ALUM", "6082", "6005", "6061", "5083", "5052", "7075", "2024", "EN AW")
_STAINLESS_KEYWORDS = ("STAIN", "INOX", "316", "304", "AISI")


def _is_aluminum(material: str) -> bool:
    m = material.upper()
    return any(kw in m for kw in _ALUMINUM_KEYWORDS)


def _is_stainless(material: str) -> bool:
    m = material.upper()
    return any(kw in m for kw in _STAINLESS_KEYWORDS)


RELEASE_GATES = [
    "CAD_VALID",
    "DRAWING_VALID",
    "BOM_RECONCILED",
    "ROUTING_COMPLETE",
    "INSPECTION_PLAN",
    "DOCUMENT_PACKAGE",
]


# ═══════════════════════════════════════════════════════════════════════════════
#  Dataclasses de resultado
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ProductSnapshotData:
    """Contrato inmutable de ProductSnapshot (no modificar tras liberación)."""
    snapshot_id: UUID
    product_code: str
    revision: str
    state: str
    snapshot_hash: Optional[str]
    material: Optional[str]
    cad_level: str
    geometry_params: Dict[str, Any]
    structural_hashes: Dict[str, str]
    library_versions: Dict[str, str]
    mass_kg_cad: Optional[float] = None
    mass_kg_bom: Optional[float] = None
    cost_eur_industrial: Optional[float] = None
    co2_kgco2e: Optional[float] = None
    is_fit_for_release: bool = False
    release_blockers: List[str] = field(default_factory=list)


@dataclass
class PhysicalProperties:
    volume_cm3: float
    mass_kg: float
    surface_area_m2: float
    center_of_gravity: Tuple[float, float, float]


@dataclass
class BendDevelopment:
    inner_radius_mm: float
    angle_deg: float
    thickness_mm: float
    k_factor: float
    neutral_radius_mm: float
    arc_length_mm: float
    total_developed_length_mm: float


@dataclass
class DxfLayerSpec:
    layer_name: str
    color_index: int
    linetype: str
    is_fabrication: bool


@dataclass
class ValidationCheck:
    check_code: str
    severity: str           # BLOCKING, ERROR, WARNING, INFO
    message: str
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationReport:
    snapshot_id: UUID
    checks: List[ValidationCheck] = field(default_factory=list)

    @property
    def blockers(self) -> List[ValidationCheck]:
        return [c for c in self.checks if c.severity == "BLOCKING"]

    @property
    def errors(self) -> List[ValidationCheck]:
        return [c for c in self.checks if c.severity in ("BLOCKING", "ERROR")]

    @property
    def warnings(self) -> List[ValidationCheck]:
        return [c for c in self.checks if c.severity == "WARNING"]

    @property
    def is_fit_for_release(self) -> bool:
        return len(self.blockers) == 0


@dataclass
class CadJobResult:
    job_id: UUID
    snapshot_id: UUID
    artifact_type: str
    state: str
    format: str
    checksum: Optional[str]
    file_size_bytes: Optional[int]
    generator_version: str
    validation_status: str
    error_message: Optional[str] = None
    properties: Optional[Dict[str, Any]] = None


@dataclass
class DrawingJobResult:
    job_id: UUID
    snapshot_id: UUID
    drawing_code: str
    drawing_type: str
    state: str
    format: str
    validation_status: str
    is_fit_for_manufacture: bool
    validation_errors: List[str] = field(default_factory=list)
    error_message: Optional[str] = None


@dataclass
class BomBuildResult:
    header_id: UUID
    snapshot_id: UUID
    bom_view: str
    bom_hash: str
    total_mass_kg: float
    total_cost_eur: float
    line_count: int
    mass_reconciliation_ok: bool
    mass_delta_pct: float
    lines: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class MassReconciliation:
    mass_kg_cad: float
    mass_kg_bom: float
    delta_kg: float
    delta_pct: float
    is_within_threshold: bool
    threshold_pct: float = MASS_RECONCILIATION_THRESHOLD * 100


@dataclass
class ReleaseGateResult:
    gate_name: str
    status: str         # PASSED, FAILED, PENDING, WAIVED
    detail: str


@dataclass
class MakeBuyComparison:
    part_code: str
    make_cost_eur: float
    buy_cost_eur: float
    make_lead_days: int
    buy_lead_days: int
    recommendation: str   # MAKE or BUY
    reason: str


@dataclass
class ArtifactEntry:
    artifact_id: UUID
    artifact_type: str
    checksum: str
    format: str
    generator_version: str
    generated_at: datetime


@dataclass
class ManifestResult:
    manifest_id: UUID
    snapshot_id: UUID
    manifest_hash: str
    artifact_count: int
    is_complete: bool
    entries: List[ArtifactEntry] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
#  ProductDefinitionService
# ═══════════════════════════════════════════════════════════════════════════════

class ProductDefinitionService:
    """Construye y versiona ProductSnapshot; gestiona transiciones de estado."""

    IMMUTABLE_STATES = {"RELEASED", "OBSOLETE"}

    @staticmethod
    def compute_snapshot_hash(
        product_code: str,
        revision: str,
        geometry_params: Dict[str, Any],
        structural_hashes: Dict[str, str],
        library_versions: Dict[str, str],
    ) -> str:
        payload = {
            "product_code": product_code,
            "revision": revision,
            "geometry_params": geometry_params,
            "structural_hashes": structural_hashes,
            "library_versions": library_versions,
        }
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def can_transition(current_state: str, target_state: str) -> bool:
        return target_state in SNAPSHOT_TRANSITIONS.get(current_state, [])

    @staticmethod
    def validate_immutability(state: str, proposed_change: str) -> Optional[str]:
        """Retorna mensaje de error si el cambio viola inmutabilidad; None si OK."""
        if state in ProductDefinitionService.IMMUTABLE_STATES:
            return (
                f"ProductSnapshot en estado '{state}' es inmutable. "
                f"Operación '{proposed_change}' no permitida. "
                "Cree una nueva revisión."
            )
        return None

    @staticmethod
    def build_snapshot_data(
        snapshot_id: UUID,
        product_code: str,
        revision: str,
        state: str,
        geometry_params: Dict[str, Any],
        structural_hashes: Dict[str, str],
        library_versions: Dict[str, str],
        material: Optional[str] = None,
        cad_level: str = "G2_ENGINEERING",
    ) -> ProductSnapshotData:
        h = ProductDefinitionService.compute_snapshot_hash(
            product_code, revision, geometry_params, structural_hashes, library_versions
        )
        return ProductSnapshotData(
            snapshot_id=snapshot_id,
            product_code=product_code,
            revision=revision,
            state=state,
            snapshot_hash=h,
            material=material,
            cad_level=cad_level,
            geometry_params=geometry_params,
            structural_hashes=structural_hashes,
            library_versions=library_versions,
        )

    @staticmethod
    def next_revision(current_revision: str) -> str:
        """A → B → … → Z → AA → AB → …"""
        if re.fullmatch(r"[A-Z]+", current_revision):
            chars = list(current_revision)
            idx = len(chars) - 1
            while idx >= 0:
                if chars[idx] < "Z":
                    chars[idx] = chr(ord(chars[idx]) + 1)
                    return "".join(chars)
                chars[idx] = "A"
                idx -= 1
            return "A" + "".join(chars)
        # Numeric revision: increment integer part
        m = re.match(r"(\d+)(.*)", current_revision)
        if m:
            return str(int(m.group(1)) + 1) + m.group(2)
        return current_revision + ".1"

    @staticmethod
    def validate_cad_level_progression(current_level: str, target_level: str) -> bool:
        levels = ["G0_SCHEMATIC","G1_CALC","G2_ENGINEERING","G3_MANUFACTURING","G4_AS_BUILT"]
        ci = levels.index(current_level) if current_level in levels else -1
        ti = levels.index(target_level) if target_level in levels else -1
        return ti >= ci


# ═══════════════════════════════════════════════════════════════════════════════
#  CadGenerationService
# ═══════════════════════════════════════════════════════════════════════════════

class CadGenerationService:
    """Genera artefactos CAD (STEP, DXF, GLB) y calcula propiedades físicas."""

    GENERATOR_VERSION = "14.0.0"

    # ── Propiedades físicas ──────────────────────────────────────────────────

    @staticmethod
    def compute_cylinder_properties(
        outer_diameter_mm: float,
        inner_diameter_mm: float,
        length_mm: float,
        material: str = "STEEL",
    ) -> PhysicalProperties:
        ro = outer_diameter_mm / 2000.0  # mm → m
        ri = inner_diameter_mm / 2000.0
        L = length_mm / 1000.0
        volume_m3 = math.pi * (ro**2 - ri**2) * L
        volume_cm3 = volume_m3 * 1e6
        density = ALUMINUM_DENSITY_KG_M3 if _is_aluminum(material) else STEEL_DENSITY_KG_M3
        mass_kg = volume_m3 * density
        # Superficie lateral exterior + fondos (open tube → solo lateral)
        surface_area_m2 = 2 * math.pi * ro * L
        cog = (0.0, 0.0, L / 2.0)
        return PhysicalProperties(
            volume_cm3=volume_cm3,
            mass_kg=mass_kg,
            surface_area_m2=surface_area_m2,
            center_of_gravity=cog,
        )

    @staticmethod
    def compute_cone_properties(
        outer_diameter_top_mm: float,
        outer_diameter_bot_mm: float,
        thickness_mm: float,
        height_mm: float,
        material: str = "STEEL",
    ) -> PhysicalProperties:
        ro_t = outer_diameter_top_mm / 2000.0
        ro_b = outer_diameter_bot_mm / 2000.0
        t = thickness_mm / 1000.0
        H = height_mm / 1000.0
        # Frustum external volume - frustum internal volume
        ri_t = ro_t - t
        ri_b = ro_b - t
        def frustum_vol(r1, r2, h):
            return math.pi * h / 3.0 * (r1**2 + r1*r2 + r2**2)
        vol_ext = frustum_vol(ro_b, ro_t, H)
        vol_int = frustum_vol(ri_b, ri_t, H)
        volume_m3 = vol_ext - vol_int
        volume_cm3 = volume_m3 * 1e6
        density = ALUMINUM_DENSITY_KG_M3 if _is_aluminum(material) else STEEL_DENSITY_KG_M3
        mass_kg = volume_m3 * density
        slant = math.sqrt(H**2 + (ro_b - ro_t)**2)
        surface_area_m2 = math.pi * (ro_b + ro_t) * slant
        h_cog = H * (ro_b**2 + 2*ro_b*ro_t + 3*ro_t**2) / (4*(ro_b**2 + ro_b*ro_t + ro_t**2))
        return PhysicalProperties(
            volume_cm3=volume_cm3,
            mass_kg=mass_kg,
            surface_area_m2=surface_area_m2,
            center_of_gravity=(0.0, 0.0, h_cog),
        )

    @staticmethod
    def compute_plate_properties(
        length_mm: float,
        width_mm: float,
        thickness_mm: float,
        material: str = "STEEL",
    ) -> PhysicalProperties:
        L = length_mm / 1000.0
        W = width_mm / 1000.0
        T = thickness_mm / 1000.0
        volume_m3 = L * W * T
        volume_cm3 = volume_m3 * 1e6
        density = ALUMINUM_DENSITY_KG_M3 if _is_aluminum(material) else STEEL_DENSITY_KG_M3
        mass_kg = volume_m3 * density
        surface_area_m2 = 2 * (L*W + L*T + W*T)
        return PhysicalProperties(
            volume_cm3=volume_cm3,
            mass_kg=mass_kg,
            surface_area_m2=surface_area_m2,
            center_of_gravity=(L/2, W/2, T/2),
        )

    # ── Plegado / desarrollo ─────────────────────────────────────────────────

    @staticmethod
    def compute_bend_development(
        inner_radius_mm: float,
        angle_deg: float,
        thickness_mm: float,
        material: str = "STEEL",
    ) -> BendDevelopment:
        k = K_FACTOR_ALUMINUM if _is_aluminum(material) else (
            K_FACTOR_STAINLESS if _is_stainless(material) else
            K_FACTOR_DEFAULT
        )
        neutral_radius_mm = inner_radius_mm + k * thickness_mm
        angle_rad = math.radians(angle_deg)
        arc_length_mm = neutral_radius_mm * angle_rad
        return BendDevelopment(
            inner_radius_mm=inner_radius_mm,
            angle_deg=angle_deg,
            thickness_mm=thickness_mm,
            k_factor=k,
            neutral_radius_mm=neutral_radius_mm,
            arc_length_mm=arc_length_mm,
            total_developed_length_mm=arc_length_mm,  # caller adds straight legs
        )

    @staticmethod
    def compute_developed_sheet(
        straight_legs_mm: List[float],
        bends: List[BendDevelopment],
    ) -> float:
        """Longitud total desarrollada de una chapa con n plegados."""
        return sum(straight_legs_mm) + sum(b.arc_length_mm for b in bends)

    # ── Capa DXF ──────────────────────────────────────────────────────────────

    @staticmethod
    def get_dxf_layer_spec(layer_name: str) -> Optional[DxfLayerSpec]:
        specs = {
            "CUT_OUTER":  DxfLayerSpec("CUT_OUTER",  1,  "CONTINUOUS", True),
            "CUT_INNER":  DxfLayerSpec("CUT_INNER",  2,  "CONTINUOUS", True),
            "BEND_UP":    DxfLayerSpec("BEND_UP",    3,  "DASHED",     True),
            "BEND_DOWN":  DxfLayerSpec("BEND_DOWN",  4,  "DASHED2",    True),
            "ETCH":       DxfLayerSpec("ETCH",       5,  "CENTER",     True),
            "CENTER":     DxfLayerSpec("CENTER",     6,  "CENTER2",    False),
            "BEVEL":      DxfLayerSpec("BEVEL",      7,  "CONTINUOUS", True),
            "NO_CUT":     DxfLayerSpec("NO_CUT",     8,  "PHANTOM",    False),
        }
        return specs.get(layer_name)

    @staticmethod
    def validate_dxf_layers(layers_present: List[str]) -> List[str]:
        """Retorna capas obligatorias ausentes."""
        mandatory = {"CUT_OUTER", "CENTER"}
        return [l for l in mandatory if l not in layers_present]

    @staticmethod
    def compute_artifact_checksum(content_bytes: bytes) -> str:
        return hashlib.sha256(content_bytes).hexdigest()

    @staticmethod
    def build_cad_job_result(
        snapshot_id: UUID,
        artifact_type: str,
        state: str = "VALID",
        error_message: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
    ) -> CadJobResult:
        fmt_map = {
            "CAD_STEP": "STEP",
            "CAD_DXF":  "DXF",
            "CAD_GLB":  "GLB",
        }
        return CadJobResult(
            job_id=uuid4(),
            snapshot_id=snapshot_id,
            artifact_type=artifact_type,
            state=state,
            format=fmt_map.get(artifact_type, artifact_type),
            checksum=None if state != "VALID" else hashlib.sha256(str(snapshot_id).encode()).hexdigest(),
            file_size_bytes=None,
            generator_version=CadGenerationService.GENERATOR_VERSION,
            validation_status="OK" if state == "VALID" else "ERROR",
            error_message=error_message,
            properties=properties,
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  DrawingService
# ═══════════════════════════════════════════════════════════════════════════════

class DrawingService:
    """Genera planos 2D y valida completitud."""

    GENERATOR_VERSION = "14.0.0"
    MIN_DIMENSION_DENSITY = 0.3     # dimensiones por cm² mínimo
    CAJETIN_REQUIRED_FIELDS = [
        "product_code", "revision", "scale", "material",
        "mass", "date", "drawn_by", "approved_by",
    ]

    @staticmethod
    def select_views(geometry_params: Dict[str, Any]) -> List[str]:
        """Selecciona vistas automáticamente según tipo de geometría."""
        views = ["FRONT"]
        shape = geometry_params.get("shape_type", "CYLINDER")
        if shape in ("CYLINDER", "CONE", "FRUSTUM"):
            views += ["SECTION_AA", "TOP"]
        elif shape == "PLATE":
            views += ["TOP", "RIGHT", "SECTION_AA"]
        elif shape == "BRACKET":
            views += ["RIGHT", "ISO"]
        if geometry_params.get("has_holes"):
            views.append("DETAIL_HOLES")
        if geometry_params.get("has_door"):
            views.append("DETAIL_DOOR")
        return list(dict.fromkeys(views))  # dedupe preserving order

    @staticmethod
    def validate_drawing_completeness(
        views: List[str],
        cajetin_fields: List[str],
        dimension_count: int,
        drawing_area_cm2: float,
    ) -> List[ValidationCheck]:
        checks: List[ValidationCheck] = []
        for f in DrawingService.CAJETIN_REQUIRED_FIELDS:
            if f not in cajetin_fields:
                checks.append(ValidationCheck(
                    check_code=f"DRW-CAJETIN-{f.upper()}",
                    severity="BLOCKING",
                    message=f"Campo obligatorio '{f}' falta en cajetín.",
                    context={"missing_field": f},
                ))
        if "FRONT" not in views:
            checks.append(ValidationCheck(
                check_code="DRW-VIEW-FRONT",
                severity="ERROR",
                message="Vista frontal obligatoria ausente.",
                context={},
            ))
        if drawing_area_cm2 > 0:
            density = dimension_count / drawing_area_cm2
            if density < DrawingService.MIN_DIMENSION_DENSITY:
                checks.append(ValidationCheck(
                    check_code="DRW-DIM-DENSITY",
                    severity="WARNING",
                    message=(
                        f"Densidad de cotas {density:.2f}/cm² < mínimo "
                        f"{DrawingService.MIN_DIMENSION_DENSITY}/cm²."
                    ),
                    context={"density": density, "min": DrawingService.MIN_DIMENSION_DENSITY},
                ))
        return checks

    @staticmethod
    def build_drawing_code(product_code: str, drawing_type: str, revision: str) -> str:
        prefix = {
            "GENERAL_ARRANGEMENT": "GA",
            "DETAIL": "DT",
            "ASSEMBLY": "AS",
            "WELD": "WD",
            "ERECTION": "ER",
        }.get(drawing_type, "DW")
        return f"{prefix}-{product_code}-{revision}"

    @staticmethod
    def build_drawing_result(
        snapshot_id: UUID,
        product_code: str,
        drawing_type: str,
        revision: str,
        validation_checks: List[ValidationCheck],
    ) -> DrawingJobResult:
        blockers = [c for c in validation_checks if c.severity == "BLOCKING"]
        errors   = [c for c in validation_checks if c.severity in ("BLOCKING", "ERROR")]
        state = "VALID" if not errors else "ERROR"
        return DrawingJobResult(
            job_id=uuid4(),
            snapshot_id=snapshot_id,
            drawing_code=DrawingService.build_drawing_code(product_code, drawing_type, revision),
            drawing_type=drawing_type,
            state=state,
            format="PDF",
            validation_status="OK" if not errors else "ERROR",
            is_fit_for_manufacture=len(blockers) == 0,
            validation_errors=[c.message for c in errors],
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  BomService
# ═══════════════════════════════════════════════════════════════════════════════

class BomService:
    """Construye y reconcilia EBOM/MBOM/PBOM/SBOM."""

    QUANTITY_RULES = {
        "DIRECT":    "Cantidad directa del BOM de ingeniería",
        "GEOMETRIC": "Cantidad calculada a partir de geometría",
        "FORMULA":   "Cantidad calculada por fórmula paramétrica",
        "YIELD":     "Cantidad ajustada por factor de rendimiento",
    }

    @staticmethod
    def compute_quantity_with_scrap(
        base_quantity: float,
        scrap_factor: float,
        quantity_rule: str = "DIRECT",
    ) -> float:
        """Calcula cantidad con merma. scrap_factor ∈ [0, 1)."""
        if not (0.0 <= scrap_factor < 1.0):
            raise ValueError(f"scrap_factor debe estar en [0, 1), recibido: {scrap_factor}")
        return base_quantity / (1.0 - scrap_factor) if scrap_factor > 0 else base_quantity

    @staticmethod
    def compute_lot_quantity(
        required: float,
        min_lot: Optional[float],
        multiple_of: Optional[float] = None,
    ) -> float:
        """Redondea a lote mínimo y múltiplo."""
        qty = required
        if min_lot and qty < min_lot:
            qty = min_lot
        if multiple_of and multiple_of > 0:
            qty = math.ceil(qty / multiple_of) * multiple_of
        return qty

    @staticmethod
    def reconcile_mass(
        mass_kg_cad: float,
        bom_lines: List[Dict[str, Any]],
    ) -> MassReconciliation:
        mass_kg_bom = sum(
            (ln.get("mass_kg_unit", 0.0) or 0.0) * (ln.get("quantity", 1.0) or 1.0)
            for ln in bom_lines
            if ln.get("line_type") not in ("CONSUMABLE", "WASTE", "PHANTOM")
        )
        delta_kg = abs(mass_kg_cad - mass_kg_bom)
        delta_pct = delta_kg / mass_kg_cad if mass_kg_cad > 0 else 0.0
        return MassReconciliation(
            mass_kg_cad=mass_kg_cad,
            mass_kg_bom=mass_kg_bom,
            delta_kg=delta_kg,
            delta_pct=delta_pct,
            is_within_threshold=delta_pct <= MASS_RECONCILIATION_THRESHOLD,
        )

    @staticmethod
    def compute_bom_hash(
        snapshot_id: UUID,
        bom_view: str,
        lines: List[Dict[str, Any]],
    ) -> str:
        payload = {
            "snapshot_id": str(snapshot_id),
            "bom_view": bom_view,
            "lines": sorted(lines, key=lambda l: l.get("item_code", "")),
        }
        canonical = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def check_substitution_compatibility(
        original_part: Dict[str, Any],
        substitute_part: Dict[str, Any],
    ) -> Tuple[bool, List[str]]:
        """Verifica compatibilidad de sustitución. Retorna (ok, list_of_issues)."""
        issues: List[str] = []
        o_mat = original_part.get("material", "")
        s_mat = substitute_part.get("material", "")
        if o_mat and s_mat and o_mat.upper() != s_mat.upper():
            # Misma familia de material → ok con warning
            same_family = (
                all(m in ("S235","S275","S355") for m in (o_mat.upper(), s_mat.upper()))
                or
                all("AL" in m.upper() or "6082" in m or "6005" in m for m in (o_mat, s_mat))
            )
            if not same_family:
                issues.append(f"Material diferente: {o_mat} → {s_mat}")
        o_mass = original_part.get("mass_kg_unit", 0.0) or 0.0
        s_mass = substitute_part.get("mass_kg_unit", 0.0) or 0.0
        if o_mass > 0 and s_mass > 0:
            ratio = s_mass / o_mass
            if ratio < 0.9 or ratio > 1.1:
                issues.append(f"Diferencia de masa >10%: {o_mass:.3f} vs {s_mass:.3f} kg")
        return (len(issues) == 0, issues)

    @staticmethod
    def build_bom_result(
        snapshot_id: UUID,
        bom_view: str,
        lines: List[Dict[str, Any]],
        mass_kg_cad: float,
    ) -> BomBuildResult:
        recon = BomService.reconcile_mass(mass_kg_cad, lines)
        total_cost = sum(
            (l.get("cost_eur_unit", 0.0) or 0.0) * (l.get("quantity", 1.0) or 1.0)
            for l in lines
        )
        bom_hash = BomService.compute_bom_hash(snapshot_id, bom_view, lines)
        return BomBuildResult(
            header_id=uuid4(),
            snapshot_id=snapshot_id,
            bom_view=bom_view,
            bom_hash=bom_hash,
            total_mass_kg=recon.mass_kg_bom,
            total_cost_eur=total_cost,
            line_count=len(lines),
            mass_reconciliation_ok=recon.is_within_threshold,
            mass_delta_pct=recon.delta_pct * 100,
            lines=lines,
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  RoutingService
# ═══════════════════════════════════════════════════════════════════════════════

class RoutingService:
    """Genera rutas de fabricación e instrucciones de trabajo."""

    OPERATION_SEQUENCE_STEEL = [
        "RECEPTION", "CUTTING", "BEVELING", "BENDING",
        "WELDING_LONGITUDINAL", "WELDING_CIRCUMFERENTIAL",
        "ASSEMBLY", "STRAIGHTENING", "INSPECTION",
        "GALVANIZING", "PAINTING", "RELEASE",
    ]
    OPERATION_SEQUENCE_ALUMINUM = [
        "RECEPTION", "CUTTING", "BEVELING", "WELDING_LONGITUDINAL",
        "WELDING_CIRCUMFERENTIAL", "ASSEMBLY", "MACHINING",
        "INSPECTION", "PAINTING", "RELEASE",
    ]

    @staticmethod
    def make_buy_decision(
        make_cost_eur: float,
        buy_cost_eur: float,
        make_lead_days: int,
        buy_lead_days: int,
        strategic_part: bool = False,
    ) -> MakeBuyComparison:
        """Decide Make vs Buy según coste, plazo y criticidad estratégica."""
        if strategic_part:
            recommendation = "MAKE"
            reason = "Pieza estratégica: fabricación interna obligatoria independientemente del coste."
        elif buy_cost_eur <= 0 or make_cost_eur <= buy_cost_eur:
            recommendation = "MAKE"
            reason = f"Coste fabricación {make_cost_eur:.2f}€ ≤ coste compra {buy_cost_eur:.2f}€."
        else:
            # buy_cost_eur < make_cost_eur — compra es más barata
            # cost_ratio = buy / make < 1.0; savings_pct = (1 - cost_ratio)*100
            cost_ratio = buy_cost_eur / make_cost_eur
            savings_pct = (1.0 - cost_ratio) * 100.0
            # Si el ahorro es pequeño (<15%) y el plazo de fabricación no es peor → MAKE
            if savings_pct < 15.0 and make_lead_days <= buy_lead_days:
                recommendation = "MAKE"
                reason = f"Ahorro de compra {savings_pct:.1f}% < 15% y plazo de fabricación no mayor."
            else:
                recommendation = "BUY"
                reason = f"Coste compra {buy_cost_eur:.2f}€ < fabricación {make_cost_eur:.2f}€ (ahorro {savings_pct:.1f}%)."
        return MakeBuyComparison(
            part_code="",
            make_cost_eur=make_cost_eur,
            buy_cost_eur=buy_cost_eur,
            make_lead_days=make_lead_days,
            buy_lead_days=buy_lead_days,
            recommendation=recommendation,
            reason=reason,
        )

    @staticmethod
    def validate_supplier_capability(
        supplier: Dict[str, Any],
        required_operations: List[str],
    ) -> Tuple[bool, List[str]]:
        """Verifica que el proveedor tiene capacidad para las operaciones requeridas."""
        supplier_ops = set(supplier.get("capabilities", []))
        missing = [op for op in required_operations if op not in supplier_ops]
        return (len(missing) == 0, missing)

    @staticmethod
    def compute_routing_hash(
        part_code: str,
        operations: List[Dict[str, Any]],
    ) -> str:
        payload = {
            "part_code": part_code,
            "operations": sorted(operations, key=lambda o: o.get("sequence_no", 0)),
        }
        canonical = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def default_operation_sequence(material: str) -> List[str]:
        if _is_aluminum(material):
            return RoutingService.OPERATION_SEQUENCE_ALUMINUM
        return RoutingService.OPERATION_SEQUENCE_STEEL

    @staticmethod
    def compute_total_time(operations: List[Dict[str, Any]]) -> float:
        return sum(
            (op.get("setup_time_h", 0.0) or 0.0) + (op.get("run_time_h", 0.0) or 0.0)
            for op in operations
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  ValidationService
# ═══════════════════════════════════════════════════════════════════════════════

class ValidationService:
    """Ejecuta todas las comprobaciones de coherencia del ProductSnapshot."""

    @staticmethod
    def check_hash_integrity(
        stored_hash: str,
        computed_hash: str,
    ) -> Optional[ValidationCheck]:
        if stored_hash != computed_hash:
            return ValidationCheck(
                check_code="VAL-HASH-INTEGRITY",
                severity="BLOCKING",
                message=f"Hash snapshot no coincide: almacenado={stored_hash[:16]}… calculado={computed_hash[:16]}…",
                context={"stored": stored_hash, "computed": computed_hash},
            )
        return None

    @staticmethod
    def check_mass_reconciliation(reconciliation: MassReconciliation) -> Optional[ValidationCheck]:
        if not reconciliation.is_within_threshold:
            return ValidationCheck(
                check_code="VAL-MASS-RECONCILIATION",
                severity="BLOCKING",
                message=(
                    f"Masa CAD ({reconciliation.mass_kg_cad:.3f} kg) difiere de masa BOM "
                    f"({reconciliation.mass_kg_bom:.3f} kg) en {reconciliation.delta_pct*100:.2f}% "
                    f"> umbral {reconciliation.threshold_pct:.1f}%."
                ),
                context={
                    "mass_cad": reconciliation.mass_kg_cad,
                    "mass_bom": reconciliation.mass_kg_bom,
                    "delta_pct": reconciliation.delta_pct * 100,
                },
            )
        return None

    @staticmethod
    def check_bolt_count(
        declared_count: int,
        bom_count: int,
        tolerance: int = 0,
    ) -> Optional[ValidationCheck]:
        if abs(declared_count - bom_count) > tolerance:
            return ValidationCheck(
                check_code="VAL-BOLT-COUNT",
                severity="ERROR",
                message=f"Número de pernos en plano ({declared_count}) ≠ BOM ({bom_count}).",
                context={"drawing": declared_count, "bom": bom_count},
            )
        return None

    @staticmethod
    def check_weld_symbols(
        weld_symbols_present: bool,
        has_welded_joints: bool,
    ) -> Optional[ValidationCheck]:
        if has_welded_joints and not weld_symbols_present:
            return ValidationCheck(
                check_code="VAL-WELD-SYMBOLS",
                severity="ERROR",
                message="La pieza tiene uniones soldadas pero el plano carece de símbolos de soldadura.",
                context={"has_welded_joints": has_welded_joints},
            )
        return None

    @staticmethod
    def check_structural_hash_match(
        snapshot_structural_hashes: Dict[str, str],
        solver_result_hashes: Dict[str, str],
    ) -> List[ValidationCheck]:
        checks: List[ValidationCheck] = []
        for key, h in snapshot_structural_hashes.items():
            solver_h = solver_result_hashes.get(key)
            if solver_h is None:
                checks.append(ValidationCheck(
                    check_code=f"VAL-HASH-MISSING-{key.upper()}",
                    severity="WARNING",
                    message=f"Hash '{key}' presente en snapshot pero ausente en resultados solver.",
                    context={"key": key},
                ))
            elif solver_h != h:
                checks.append(ValidationCheck(
                    check_code=f"VAL-HASH-MISMATCH-{key.upper()}",
                    severity="BLOCKING",
                    message=f"Hash '{key}' no coincide: snapshot={h[:12]}… solver={solver_h[:12]}…",
                    context={"key": key, "snapshot_hash": h, "solver_hash": solver_h},
                ))
        return checks

    @staticmethod
    def check_dxf_reconstruction(
        layers_present: List[str],
        can_reconstruct: bool,
    ) -> Optional[ValidationCheck]:
        missing = ValidationService.check_missing_dxf_layers(layers_present)
        if missing:
            return ValidationCheck(
                check_code="VAL-DXF-LAYERS",
                severity="ERROR",
                message=f"Capas DXF obligatorias ausentes: {missing}",
                context={"missing_layers": missing},
            )
        if not can_reconstruct:
            return ValidationCheck(
                check_code="VAL-DXF-RECONSTRUCT",
                severity="BLOCKING",
                message="No es posible reconstruir la geometría a partir del DXF.",
                context={},
            )
        return None

    @staticmethod
    def check_missing_dxf_layers(layers_present: List[str]) -> List[str]:
        mandatory = ["CUT_OUTER", "CENTER"]
        return [l for l in mandatory if l not in layers_present]

    @staticmethod
    def run_full_validation(
        snapshot: ProductSnapshotData,
        mass_reconciliation: Optional[MassReconciliation] = None,
        solver_hashes: Optional[Dict[str, str]] = None,
        dxf_layers: Optional[List[str]] = None,
        can_reconstruct_dxf: bool = True,
        bolt_count_drawing: Optional[int] = None,
        bolt_count_bom: Optional[int] = None,
        has_welded_joints: bool = False,
        weld_symbols_present: bool = True,
    ) -> ValidationReport:
        report = ValidationReport(snapshot_id=snapshot.snapshot_id)
        # Hash integrity
        if snapshot.snapshot_hash:
            computed = ProductDefinitionService.compute_snapshot_hash(
                snapshot.product_code,
                snapshot.revision,
                snapshot.geometry_params,
                snapshot.structural_hashes,
                snapshot.library_versions,
            )
            c = ValidationService.check_hash_integrity(snapshot.snapshot_hash, computed)
            if c:
                report.checks.append(c)
        # Mass reconciliation
        if mass_reconciliation:
            c = ValidationService.check_mass_reconciliation(mass_reconciliation)
            if c:
                report.checks.append(c)
        # Structural hash match
        if solver_hashes:
            report.checks.extend(
                ValidationService.check_structural_hash_match(
                    snapshot.structural_hashes, solver_hashes
                )
            )
        # DXF
        if dxf_layers is not None:
            c = ValidationService.check_dxf_reconstruction(dxf_layers, can_reconstruct_dxf)
            if c:
                report.checks.append(c)
        # Bolt count
        if bolt_count_drawing is not None and bolt_count_bom is not None:
            c = ValidationService.check_bolt_count(bolt_count_drawing, bolt_count_bom)
            if c:
                report.checks.append(c)
        # Weld symbols
        c = ValidationService.check_weld_symbols(weld_symbols_present, has_welded_joints)
        if c:
            report.checks.append(c)
        return report


# ═══════════════════════════════════════════════════════════════════════════════
#  ReleaseService
# ═══════════════════════════════════════════════════════════════════════════════

class ReleaseService:
    """Orquesta las puertas de liberación y publica en ERP/PDM/PLM."""

    @staticmethod
    def evaluate_gate(
        gate_name: str,
        validation_report: Optional[ValidationReport] = None,
        artifacts_ready: Optional[Dict[str, bool]] = None,
        waived: bool = False,
    ) -> ReleaseGateResult:
        if waived:
            return ReleaseGateResult(gate_name=gate_name, status="WAIVED", detail="Dispensado explícitamente.")
        artifacts_ready = artifacts_ready or {}
        if gate_name == "CAD_VALID":
            cad_ok = artifacts_ready.get("CAD_STEP", False) and artifacts_ready.get("CAD_DXF", False)
            return ReleaseGateResult(
                gate_name=gate_name,
                status="PASSED" if cad_ok else "FAILED",
                detail="Artefactos CAD (STEP + DXF) presentes y válidos." if cad_ok else "Artefactos CAD ausentes o inválidos.",
            )
        if gate_name == "DRAWING_VALID":
            drw_ok = artifacts_ready.get("DRAWING_PDF", False)
            return ReleaseGateResult(
                gate_name=gate_name,
                status="PASSED" if drw_ok else "FAILED",
                detail="Plano PDF válido." if drw_ok else "Plano PDF ausente o inválido.",
            )
        if gate_name == "BOM_RECONCILED":
            bom_ok = artifacts_ready.get("BOM_EBOM", False)
            blocker = validation_report and any(
                c.check_code == "VAL-MASS-RECONCILIATION"
                for c in (validation_report.blockers + validation_report.errors)
            )
            ok = bom_ok and not blocker
            return ReleaseGateResult(
                gate_name=gate_name,
                status="PASSED" if ok else "FAILED",
                detail="BOM reconciliada." if ok else "BOM ausente o masa no reconciliada.",
            )
        if gate_name == "ROUTING_COMPLETE":
            ok = artifacts_ready.get("ROUTING", False)
            return ReleaseGateResult(
                gate_name=gate_name,
                status="PASSED" if ok else "FAILED",
                detail="Ruta de fabricación completa." if ok else "Ruta de fabricación incompleta o ausente.",
            )
        if gate_name == "INSPECTION_PLAN":
            ok = artifacts_ready.get("INSPECTION_PLAN", False)
            return ReleaseGateResult(
                gate_name=gate_name,
                status="PASSED" if ok else "FAILED",
                detail="Plan de control presente." if ok else "Plan de control ausente.",
            )
        if gate_name == "DOCUMENT_PACKAGE":
            ok = artifacts_ready.get("DOC_PACKAGE", False)
            return ReleaseGateResult(
                gate_name=gate_name,
                status="PASSED" if ok else "FAILED",
                detail="Paquete documental generado." if ok else "Paquete documental ausente.",
            )
        return ReleaseGateResult(gate_name=gate_name, status="PENDING", detail="Puerta no evaluada.")

    @staticmethod
    def evaluate_all_gates(
        validation_report: Optional[ValidationReport],
        artifacts_ready: Dict[str, bool],
        waived_gates: Optional[List[str]] = None,
    ) -> List[ReleaseGateResult]:
        waived_gates = waived_gates or []
        results = []
        for gate in RELEASE_GATES:
            r = ReleaseService.evaluate_gate(
                gate_name=gate,
                validation_report=validation_report,
                artifacts_ready=artifacts_ready,
                waived=(gate in waived_gates),
            )
            results.append(r)
        return results

    @staticmethod
    def is_fit_for_release(gate_results: List[ReleaseGateResult]) -> Tuple[bool, List[str]]:
        failed = [g for g in gate_results if g.status == "FAILED"]
        return (len(failed) == 0, [g.gate_name for g in failed])

    @staticmethod
    def compute_release_hash(
        snapshot_id: UUID,
        release_code: str,
        gate_results: List[ReleaseGateResult],
    ) -> str:
        payload = {
            "snapshot_id": str(snapshot_id),
            "release_code": release_code,
            "gates": {g.gate_name: g.status for g in gate_results},
        }
        canonical = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════════
#  DocumentService
# ═══════════════════════════════════════════════════════════════════════════════

class DocumentService:
    """Genera paquetes documentales para diferentes audiencias."""

    AUDIENCE_CONTENTS = {
        "CLIENT":       ["DRAWING_PDF", "PRODUCT_DATASHEET", "CERTIFICATE"],
        "ENGINEERING":  ["CAD_STEP", "CAD_DXF", "BOM_EBOM", "DRAWING_PDF", "ROUTING"],
        "PRODUCTION":   ["DRAWING_PDF", "BOM_MBOM", "ROUTING", "WORK_INSTRUCTIONS"],
        "QUALITY":      ["INSPECTION_PLAN", "DRAWING_PDF", "CERTIFICATE"],
        "SUPPLIER":     ["DRAWING_PDF", "BOM_PBOM", "ROUTING"],
        "SITE":         ["ERECTION_DRAWING", "ASSEMBLY_INSTRUCTION"],
        "REGULATORY":   ["DRAWING_PDF", "CERTIFICATE", "CALCULATION_REPORT"],
    }

    @staticmethod
    def document_types_for_audience(audience: str) -> List[str]:
        return DocumentService.AUDIENCE_CONTENTS.get(audience, [])

    @staticmethod
    def compute_package_hash(
        snapshot_id: UUID,
        audience: str,
        language: str,
        document_types: List[str],
    ) -> str:
        payload = {
            "snapshot_id": str(snapshot_id),
            "audience": audience,
            "language": language,
            "document_types": sorted(document_types),
        }
        canonical = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def validate_language_support(language: str, audience: str) -> Optional[ValidationCheck]:
        supported = {
            "CLIENT":    ["es","en","fr","ca","it","pt"],
            "SUPPLIER":  ["es","en"],
            "SITE":      ["es","en","fr"],
            "REGULATORY":["es","en","fr"],
        }
        langs = supported.get(audience, ["es","en"])
        if language not in langs:
            return ValidationCheck(
                check_code="DOC-LANG-UNSUPPORTED",
                severity="WARNING",
                message=f"Idioma '{language}' no disponible para audiencia '{audience}'. Disponibles: {langs}.",
                context={"language": language, "audience": audience, "supported": langs},
            )
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  IntegrationService
# ═══════════════════════════════════════════════════════════════════════════════

class IntegrationService:
    """Publica en ERP/PDM/PLM y gestiona sincronización con proveedores."""

    @staticmethod
    def build_erp_payload(
        snapshot: ProductSnapshotData,
        bom_result: BomBuildResult,
        routing_hash: str,
        release_code: str,
    ) -> Dict[str, Any]:
        return {
            "product_code":    snapshot.product_code,
            "revision":        snapshot.revision,
            "release_code":    release_code,
            "snapshot_hash":   snapshot.snapshot_hash,
            "material":        snapshot.material,
            "mass_kg":         snapshot.mass_kg_cad,
            "cost_eur":        snapshot.cost_eur_industrial,
            "bom_view":        bom_result.bom_view,
            "bom_hash":        bom_result.bom_hash,
            "routing_hash":    routing_hash,
            "published_at":    datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def validate_erp_payload(payload: Dict[str, Any]) -> List[str]:
        required_keys = ["product_code","revision","release_code","snapshot_hash","bom_hash"]
        return [k for k in required_keys if not payload.get(k)]

    @staticmethod
    def build_pdm_metadata(snapshot: ProductSnapshotData) -> Dict[str, Any]:
        return {
            "item_number":    snapshot.product_code,
            "revision":       snapshot.revision,
            "state":          snapshot.state,
            "cad_level":      snapshot.cad_level,
            "snapshot_hash":  snapshot.snapshot_hash,
            "geometry_params": snapshot.geometry_params,
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  ArtifactStore
# ═══════════════════════════════════════════════════════════════════════════════

class ArtifactStore:
    """Gestiona binarios inmutables y sus hashes."""

    def __init__(self):
        self._store: Dict[str, bytes] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}

    def store(self, artifact_id: str, content: bytes, metadata: Dict[str, Any]) -> str:
        checksum = hashlib.sha256(content).hexdigest()
        self._store[artifact_id] = content
        self._metadata[artifact_id] = {**metadata, "checksum": checksum, "size": len(content)}
        return checksum

    def retrieve(self, artifact_id: str) -> Optional[bytes]:
        return self._store.get(artifact_id)

    def verify(self, artifact_id: str) -> bool:
        content = self._store.get(artifact_id)
        meta = self._metadata.get(artifact_id, {})
        if content is None or "checksum" not in meta:
            return False
        return hashlib.sha256(content).hexdigest() == meta["checksum"]

    def get_metadata(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        return self._metadata.get(artifact_id)

    def list_artifacts(self, snapshot_id: str) -> List[str]:
        return [aid for aid, m in self._metadata.items() if m.get("snapshot_id") == snapshot_id]

    @staticmethod
    def idempotency_key(snapshot_id: UUID, artifact_type: str, cad_level: str) -> str:
        return hashlib.sha256(
            f"{snapshot_id}:{artifact_type}:{cad_level}".encode()
        ).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════════
#  QualityService
# ═══════════════════════════════════════════════════════════════════════════════

class QualityService:
    """Plan de control, as-built, no conformidades y recalificación."""

    NC_SEVERITY_MAP = {
        "BLOCKING": "CRITICAL",
        "ERROR":    "MAJOR",
        "WARNING":  "MINOR",
        "INFO":     "OBSERVATION",
    }

    @staticmethod
    def is_conformant(
        measured_value: float,
        nominal: float,
        tolerance_plus: float,
        tolerance_minus: float,
    ) -> Tuple[bool, float]:
        """Retorna (es_conforme, desviación respecto al nominal)."""
        deviation = measured_value - nominal
        ok = (-tolerance_minus <= deviation <= tolerance_plus)
        return ok, deviation

    @staticmethod
    def compute_cpk(
        measurements: List[float],
        nominal: float,
        tolerance_plus: float,
        tolerance_minus: float,
    ) -> Optional[float]:
        """Calcula índice de capacidad Cpk. Requiere ≥ 5 mediciones."""
        if len(measurements) < 5:
            return None
        mean = sum(measurements) / len(measurements)
        variance = sum((x - mean)**2 for x in measurements) / (len(measurements) - 1)
        std = math.sqrt(variance) if variance > 0 else 1e-9
        usl = nominal + tolerance_plus
        lsl = nominal - tolerance_minus
        cpu = (usl - mean) / (3 * std)
        cpl = (mean - lsl) / (3 * std)
        return min(cpu, cpl)

    @staticmethod
    def requires_requalification(nc_severity: str, is_structural: bool) -> bool:
        if nc_severity in ("BLOCKING",):
            return True
        if nc_severity == "ERROR" and is_structural:
            return True
        return False

    @staticmethod
    def nc_disposition(
        nc_severity: str,
        deviation_pct: float,
        can_repair: bool,
    ) -> str:
        """Decide disposición de no conformidad."""
        if nc_severity == "BLOCKING":
            return "SCRAP" if not can_repair else "REPAIR_AND_REINSPECT"
        if nc_severity == "ERROR":
            if deviation_pct > 5.0:
                return "SCRAP" if not can_repair else "REPAIR_AND_REINSPECT"
            return "USE_AS_IS_WITH_DEVIATION"
        if nc_severity == "WARNING":
            return "USE_AS_IS_WITH_DEVIATION"
        return "ACCEPT"

    @staticmethod
    def generate_inspection_characteristics(
        material: str,
        has_welds: bool,
        has_coating: bool,
        structural: bool,
    ) -> List[Dict[str, Any]]:
        chars = [
            {"code": "DIM-001", "description": "Altura total", "type": "DIMENSIONAL", "is_critical": structural},
            {"code": "DIM-002", "description": "Diámetro exterior base", "type": "DIMENSIONAL", "is_critical": True},
            {"code": "DIM-003", "description": "Espesores de pared", "type": "DIMENSIONAL", "is_critical": True},
            {"code": "VIS-001", "description": "Inspección visual superficial", "type": "VISUAL", "is_critical": False},
        ]
        if has_welds:
            chars += [
                {"code": "WLD-001", "description": "Inspección visual soldaduras", "type": "VISUAL", "is_critical": True},
                {"code": "WLD-002", "description": "END ultrasonidos uniones", "type": "NDT", "is_critical": structural},
            ]
        if has_coating:
            chars += [
                {"code": "CTG-001", "description": "Espesor galvanizado / pintura", "type": "DIMENSIONAL", "is_critical": False},
            ]
        if structural:
            chars += [
                {"code": "STR-001", "description": "Tolerancias rectitud / desplome", "type": "DIMENSIONAL", "is_critical": True},
            ]
        return chars


# ═══════════════════════════════════════════════════════════════════════════════
#  ArtifactManifestService
# ═══════════════════════════════════════════════════════════════════════════════

class ArtifactManifestService:
    """Crea manifiesto completo de artefactos con checksums y verifica idempotencia."""

    REQUIRED_ARTIFACT_TYPES = {
        "G3_MANUFACTURING": ["CAD_STEP", "CAD_DXF", "DRAWING_PDF", "BOM_EBOM"],
        "G4_AS_BUILT":      ["CAD_STEP", "CAD_DXF", "CAD_GLB", "DRAWING_PDF", "BOM_EBOM", "BOM_ASBUILT"],
        "G2_ENGINEERING":   ["CAD_STEP", "DRAWING_PDF", "BOM_EBOM"],
        "G1_CALC":          ["CAD_STEP", "BOM_EBOM"],
        "G0_SCHEMATIC":     [],
    }

    @staticmethod
    def compute_manifest_hash(entries: List[ArtifactEntry]) -> str:
        payload = [
            {"id": str(e.artifact_id), "type": e.artifact_type, "checksum": e.checksum}
            for e in sorted(entries, key=lambda e: e.artifact_type)
        ]
        canonical = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def check_completeness(
        entries: List[ArtifactEntry],
        cad_level: str,
    ) -> Tuple[bool, List[str]]:
        required = ArtifactManifestService.REQUIRED_ARTIFACT_TYPES.get(cad_level, [])
        present_types = {e.artifact_type for e in entries}
        missing = [t for t in required if t not in present_types]
        return (len(missing) == 0, missing)

    @staticmethod
    def build_manifest(
        snapshot_id: UUID,
        entries: List[ArtifactEntry],
        cad_level: str,
    ) -> ManifestResult:
        is_complete, _ = ArtifactManifestService.check_completeness(entries, cad_level)
        manifest_hash = ArtifactManifestService.compute_manifest_hash(entries)
        return ManifestResult(
            manifest_id=uuid4(),
            snapshot_id=snapshot_id,
            manifest_hash=manifest_hash,
            artifact_count=len(entries),
            is_complete=is_complete,
            entries=entries,
        )

    @staticmethod
    def verify_idempotency(
        manifest_a: ManifestResult,
        manifest_b: ManifestResult,
    ) -> bool:
        """Dos manifiestos del mismo snapshot deben tener el mismo hash."""
        return manifest_a.manifest_hash == manifest_b.manifest_hash

    @staticmethod
    def detect_superseded_artifacts(
        entries: List[ArtifactEntry],
        current_entries: List[ArtifactEntry],
    ) -> List[ArtifactEntry]:
        """Detecta artefactos de versión anterior no incluidos en la lista actual."""
        current_ids = {e.artifact_id for e in current_entries}
        return [e for e in entries if e.artifact_id not in current_ids]
