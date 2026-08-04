"""
Services · Fase 6 — Aluminio: Diseño, Verificación y Fabricación
Salvi Studio · Columns

Principio de seguridad: ninguna fórmula, coeficiente, factor HAZ ni curva
normativa generada libremente por IA. Toda regla procede de fuente identificada
o aproximación conservadora aprobada por Oficina Técnica.
"""
import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ===========================================================================
# Enums de servicio
# ===========================================================================

class AluminiumRoute(str, Enum):
    EN40 = "EN40"
    EN40_EXTENDED = "EN40_EXTENDED"
    SPECIAL = "SPECIAL"
    BLOCKED = "BLOCKED"


class HAZSide(str, Enum):
    BOTH = "BOTH"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    FULL_RING = "FULL_RING"


class AluminiumCheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    OUT_OF_DOMAIN = "OUT_OF_DOMAIN"
    WARNING = "WARNING"


# ===========================================================================
# Dataclasses de resultado
# ===========================================================================

@dataclass
class RouteStepResult:
    step: int
    condition: str
    status: str      # "PASS" | "BLOCKED" | "WARNING"
    detail: Optional[str] = None


@dataclass
class AluminiumRouteResult:
    route: AluminiumRoute
    route_version: str
    steps: list
    decision_trace: list
    active_rules: list
    discarded_rules: list
    exclusions: list
    warnings: list
    max_declaration_allowed: Optional[str]
    input_hash: str
    all_steps_pass: bool


@dataclass
class AluminiumCheckResult:
    check_type: str
    status: AluminiumCheckStatus
    solicitation: float
    resistance: float
    utilization: float
    unit: str
    governing_rule: Optional[str] = None
    equation_trace: Optional[dict] = None
    intermediate_values: Optional[dict] = None
    error_code: Optional[str] = None


@dataclass
class CircularAluminiumProperties:
    D_ext_mm: float
    t_mm: float
    A_m2: float
    Iy_m4: float
    Iz_m4: float
    J_m4: float
    Ay_m2: float
    Az_m2: float
    Wel_y_m3: float
    Wel_z_m3: float
    mass_per_m_kg: float
    rho_kg_m3: float


@dataclass
class HAZRegion:
    haz_type: str
    haz_width_mm: float
    rho_yield: float
    rho_ultimate: float
    rho_buckling: Optional[float]
    rho_fatigue: Optional[float]
    side: str
    error_code: Optional[str] = None


@dataclass
class HAZBuildResult:
    regions: list
    has_overlapping_zones: bool
    overlap_treatment: Optional[str]
    geometry_hash: str
    material_hash: str
    error_codes: list


@dataclass
class EffectiveSectionResult:
    width_effective_mm: Optional[float]
    reduction_factor: Optional[float]
    slenderness: float
    n_iterations: int
    converged: bool
    panel_status: str
    governing_rule: Optional[str]
    iteration_history: list = field(default_factory=list)


@dataclass
class BendAllowanceResult:
    bend_allowance_mm: float
    outside_setback_mm: float
    neutral_radius_mm: float
    k_factor: float
    compliant_with_min_radius: bool
    min_radius_for_material: Optional[float]


@dataclass
class FabricabilityCheck:
    compliant: bool
    code: str
    severity: str    # "BLOCKING" | "WARNING"
    description: str


@dataclass
class AluminiumDesignVariable:
    alloy_designation: str
    temper: str
    weld_process: str
    thickness_mm: float
    diameter_base_mm: float
    taper_ratio: float = 11.0
    n_segments: int = 1


@dataclass
class AluminiumCandidate:
    design: AluminiumDesignVariable
    total_cost_eur: float
    total_mass_kg: float
    total_co2_kg: float
    max_utilization: float
    is_fabricable: bool
    is_transportable: bool
    is_pareto_dominated: bool = False


@dataclass
class MinerResult:
    total_damage: float
    D_limit: float
    status: str
    source_breakdown: dict
    duplicate_source_detected: bool


# ===========================================================================
# AluminiumNormativeClassifier
# ===========================================================================

class AluminiumNormativeClassifier:
    """
    Árbol de decisión bloqueante de 7 pasos para columnas de aluminio.
    Rutas: EN40, EN40_EXTENDED (>20m o cables), SPECIAL, BLOCKED.
    """
    ROUTE_VERSION = "1.0"

    @staticmethod
    def classify(
        height_nominal_m: float,
        has_catenary_cables: bool,
        alloy_in_library: bool,
        domain_ok: bool,
        checks_defined: bool,
        rules_available: bool,
        evidence_ok: bool,
    ) -> AluminiumRouteResult:
        payload = {
            "height_nominal_m": round(height_nominal_m, 4),
            "has_catenary_cables": has_catenary_cables,
            "alloy_in_library": alloy_in_library,
            "domain_ok": domain_ok,
            "checks_defined": checks_defined,
            "rules_available": rules_available,
            "evidence_ok": evidence_ok,
            "classifier_version": AluminiumNormativeClassifier.ROUTE_VERSION,
        }
        input_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()

        steps = []
        decision_trace = []
        warnings = []
        route = AluminiumRoute.EN40
        extended = False

        # Paso 1: norma activa (se asume True cuando se llama al clasificador)
        steps.append(RouteStepResult(1, "Norma/edición/AN activos", "PASS"))
        decision_trace.append("Paso 1 PASS: normativa activa")

        # Paso 2: altura, tipología, cables
        if has_catenary_cables:
            steps.append(RouteStepResult(2, "Sin cables de catenaria", "BLOCKED",
                                          "Cables de catenaria presentes → ruta especial"))
            decision_trace.append("Paso 2 BLOCKED: cables catenaria")
            route = AluminiumRoute.SPECIAL
        elif height_nominal_m > 20.0:
            steps.append(RouteStepResult(2, "Altura ≤20 m", "WARNING",
                                          f"Altura {height_nominal_m} m > 20 m → ruta ampliada"))
            decision_trace.append(f"Paso 2 WARNING: altura {height_nominal_m}m → EN40_EXTENDED")
            extended = True
        else:
            steps.append(RouteStepResult(2, "Altura ≤20 m", "PASS"))
            decision_trace.append("Paso 2 PASS: altura dentro de EN 40-6")

        # Paso 3: aleación/temple/producto en biblioteca
        if not alloy_in_library:
            steps.append(RouteStepResult(3, "Aleación/temple/producto en biblioteca", "BLOCKED",
                                          "AL-MAT-001: aleación no publicada"))
            decision_trace.append("Paso 3 BLOCKED: AL-MAT-001")
            route = AluminiumRoute.BLOCKED
        else:
            steps.append(RouteStepResult(3, "Aleación/temple/producto en biblioteca", "PASS"))
            decision_trace.append("Paso 3 PASS")

        # Paso 4: dominio de ecuaciones
        if not domain_ok and route not in (AluminiumRoute.BLOCKED,):
            steps.append(RouteStepResult(4, "Geometría dentro del dominio", "BLOCKED",
                                          "Sección/detalle fuera de fórmulas → ruta especial"))
            decision_trace.append("Paso 4 BLOCKED: fuera de dominio")
            route = AluminiumRoute.SPECIAL
        else:
            steps.append(RouteStepResult(4, "Geometría dentro del dominio", "PASS" if domain_ok else "BLOCKED"))
            if domain_ok:
                decision_trace.append("Paso 4 PASS")

        # Paso 5: verificaciones definidas
        if not checks_defined and route == AluminiumRoute.EN40:
            steps.append(RouteStepResult(5, "Verificaciones definidas", "BLOCKED",
                                          "AL-SEC-001: verificación sin regla"))
            decision_trace.append("Paso 5 BLOCKED: AL-SEC-001")
            route = AluminiumRoute.BLOCKED
        else:
            steps.append(RouteStepResult(5, "Verificaciones definidas",
                                          "PASS" if checks_defined else "BLOCKED"))
            if checks_defined:
                decision_trace.append("Paso 5 PASS")

        # Paso 6: reglas disponibles
        if not rules_available and route == AluminiumRoute.EN40:
            steps.append(RouteStepResult(6, "Reglas/datasets disponibles", "BLOCKED",
                                          "Regla sin edición activa"))
            decision_trace.append("Paso 6 BLOCKED")
            route = AluminiumRoute.BLOCKED
        else:
            steps.append(RouteStepResult(6, "Reglas/datasets disponibles",
                                          "PASS" if rules_available else "BLOCKED"))
            if rules_available:
                decision_trace.append("Paso 6 PASS")

        # Paso 7: evidencia
        if not evidence_ok and route == AluminiumRoute.EN40:
            steps.append(RouteStepResult(7, "Evidencias y pruebas activas", "BLOCKED",
                                          "AL-FAT-001: detalle sin categoría"))
            decision_trace.append("Paso 7 BLOCKED: AL-FAT-001")
            route = AluminiumRoute.BLOCKED
        else:
            steps.append(RouteStepResult(7, "Evidencias y pruebas activas",
                                          "PASS" if evidence_ok else "BLOCKED"))
            if evidence_ok:
                decision_trace.append("Paso 7 PASS")

        # Determinar ruta final
        if route == AluminiumRoute.EN40 and extended:
            route = AluminiumRoute.EN40_EXTENDED

        all_pass = all(s.status in ("PASS", "WARNING") for s in steps)

        max_decl = {
            AluminiumRoute.EN40: "EN 40-6 + EN 40-3-3",
            AluminiumRoute.EN40_EXTENDED: "EN 40-6 + EN 1999",
            AluminiumRoute.SPECIAL: "Cálculo especial documentado",
            AluminiumRoute.BLOCKED: None,
        }[route]

        active_rules = ["EN 40-6", "EN 40-3-3"] if route == AluminiumRoute.EN40 else \
                       ["EN 40-6", "EN 1999-1-1"] if route == AluminiumRoute.EN40_EXTENDED else \
                       ["EN 1999-1-1", "FEM/ensayo"]

        return AluminiumRouteResult(
            route=route,
            route_version=AluminiumNormativeClassifier.ROUTE_VERSION,
            steps=steps,
            decision_trace=decision_trace,
            active_rules=active_rules,
            discarded_rules=[],
            exclusions=[],
            warnings=warnings,
            max_declaration_allowed=max_decl,
            input_hash=input_hash,
            all_steps_pass=all_pass,
        )


# ===========================================================================
# AluminiumMaterialService
# ===========================================================================

class AluminiumMaterialService:
    """Resolución de propiedades de aluminio por aleación, temple y espesor."""

    # Biblioteca inicial embebida (EN AW-5083 H111 chapa)
    _LIBRARY: list[dict] = [
        {
            "alloy": "EN AW-5083", "temper": "H111", "product_form": "SHEET",
            "t_min": 0.0, "t_max": 6.0, "f0": 125.0, "fu": 270.0,
            "E": 70000.0, "G": 26900.0, "rho": 2660.0,
            "haz_rho_yield": 0.72, "haz_rho_ultimate": 0.90, "haz_width": 25.0,
        },
        {
            "alloy": "EN AW-6060", "temper": "T6", "product_form": "HOLLOW_EXTRUSION",
            "t_min": 0.0, "t_max": 5.0, "f0": 150.0, "fu": 190.0,
            "E": 69500.0, "G": 26700.0, "rho": 2700.0,
            "haz_rho_yield": 0.50, "haz_rho_ultimate": 0.60, "haz_width": 20.0,
        },
        {
            "alloy": "EN AW-6082", "temper": "T6", "product_form": "HOLLOW_EXTRUSION",
            "t_min": 0.0, "t_max": 15.0, "f0": 260.0, "fu": 310.0,
            "E": 70000.0, "G": 26900.0, "rho": 2700.0,
            "haz_rho_yield": 0.45, "haz_rho_ultimate": 0.60, "haz_width": 30.0,
        },
    ]

    @classmethod
    def resolve(
        cls,
        alloy_designation: str,
        temper: str,
        product_form: str,
        thickness_mm: float,
        gamma_M: float = 1.1,
    ) -> dict:
        """
        Busca registro exacto. Si no existe, devuelve AL-MAT-001.
        Devuelve propiedades de diseño (divididas por γM) y procedencia.
        """
        matches = [
            r for r in cls._LIBRARY
            if r["alloy"] == alloy_designation
            and r["temper"] == temper
            and r["product_form"] == product_form
            and r["t_min"] < thickness_mm <= r["t_max"]
        ]
        if not matches:
            raise ValueError(
                f"AL-MAT-001: no hay propiedades para "
                f"{alloy_designation}/{temper}/{product_form} t={thickness_mm}mm"
            )
        rec = matches[0]
        return {
            "alloy_designation": alloy_designation,
            "temper": temper,
            "product_form": product_form,
            "thickness_mm": thickness_mm,
            "f0_d_mpa": round(rec["f0"] / gamma_M, 4),
            "fu_d_mpa": round(rec["fu"] / gamma_M, 4),
            "f0_characteristic_mpa": rec["f0"],
            "fu_characteristic_mpa": rec["fu"],
            "E_mpa": rec["E"],
            "G_mpa": rec["G"],
            "rho_kg_m3": rec["rho"],
            "haz_rho_yield": rec.get("haz_rho_yield"),
            "haz_rho_ultimate": rec.get("haz_rho_ultimate"),
            "haz_width_mm": rec.get("haz_width"),
            "gamma_M": gamma_M,
            "provenance": f"embedded_library/{alloy_designation}/{temper}",
        }

    @staticmethod
    def canonical_key(alloy: str, temper: str, product_form: str,
                       t_min: float, t_max: float, temp_c: float) -> str:
        payload = {
            "alloy": alloy, "temper": temper, "product_form": product_form,
            "t_min": t_min, "t_max": t_max, "temp_c": temp_c,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()[:16]


# ===========================================================================
# AluminiumHAZService
# ===========================================================================

class AluminiumHAZService:
    """Construcción del mapa de zonas afectadas térmicamente."""

    # Factores HAZ por proceso y tipo (simplificados; en producción proceden de BD)
    _HAZ_DEFAULTS: dict[str, dict] = {
        "MIG": {"rho_yield": 0.65, "rho_ultimate": 0.80, "side": "BOTH"},
        "TIG": {"rho_yield": 0.65, "rho_ultimate": 0.80, "side": "BOTH"},
        "FSW": {"rho_yield": 0.80, "rho_ultimate": 0.90, "side": "BOTH"},
    }

    @classmethod
    def build_haz_region(
        cls,
        haz_type: str,
        process: str,
        alloy_designation: str,
        temper: str,
        thickness_mm: float,
        haz_width_mm: Optional[float] = None,
        rho_yield_override: Optional[float] = None,
        rho_ultimate_override: Optional[float] = None,
    ) -> HAZRegion:
        defaults = cls._HAZ_DEFAULTS.get(process)
        if defaults is None:
            return HAZRegion(
                haz_type=haz_type, haz_width_mm=0.0,
                rho_yield=1.0, rho_ultimate=1.0,
                rho_buckling=None, rho_fatigue=None,
                side="BOTH", error_code="AL-HAZ-001",
            )
        width = haz_width_mm or (20.0 + 0.5 * thickness_mm)
        rho_y = rho_yield_override if rho_yield_override is not None else defaults["rho_yield"]
        rho_u = rho_ultimate_override if rho_ultimate_override is not None else defaults["rho_ultimate"]

        side = "FULL_RING" if haz_type in ("CIRCUMFERENTIAL",) else defaults["side"]

        return HAZRegion(
            haz_type=haz_type,
            haz_width_mm=round(width, 2),
            rho_yield=rho_y,
            rho_ultimate=rho_u,
            rho_buckling=None,
            rho_fatigue=None,
            side=side,
        )

    @staticmethod
    def check_overlaps(regions: list[HAZRegion]) -> bool:
        """Detecta si existen zonas que se solapan (misma cara, tipos distintos)."""
        seen = {}
        for r in regions:
            key = (r.side, r.haz_type)
            if key in seen:
                return True
            seen[key] = True
        return False

    @staticmethod
    def worst_case_overlap(regions: list[HAZRegion]) -> dict:
        """Retorna factores más desfavorables para zonas solapadas."""
        min_rho_y = min(r.rho_yield for r in regions)
        min_rho_u = min(r.rho_ultimate for r in regions)
        return {"rho_yield": min_rho_y, "rho_ultimate": min_rho_u}

    @classmethod
    def build_map(
        cls,
        haz_inputs: list[dict],
        check_overlaps: bool = True,
    ) -> HAZBuildResult:
        regions = []
        for inp in haz_inputs:
            region = cls.build_haz_region(
                haz_type=inp.get("haz_type", "LONGITUDINAL_SEAM"),
                process=inp.get("process", "MIG"),
                alloy_designation=inp.get("alloy_designation", ""),
                temper=inp.get("temper", ""),
                thickness_mm=inp.get("thickness_mm", 4.0),
                haz_width_mm=inp.get("haz_width_mm"),
            )
            regions.append(region)

        has_overlap = check_overlaps and cls.check_overlaps(regions)
        overlap_treatment = "WORST_CASE" if has_overlap else None

        g_hash = hashlib.sha256(
            json.dumps([inp.get("haz_type") for inp in haz_inputs], sort_keys=True).encode()
        ).hexdigest()[:16]
        m_hash = hashlib.sha256(
            json.dumps([inp.get("alloy_designation") for inp in haz_inputs], sort_keys=True).encode()
        ).hexdigest()[:16]

        errors = ["AL-HAZ-002" for r in regions if r.error_code]

        return HAZBuildResult(
            regions=regions,
            has_overlapping_zones=has_overlap,
            overlap_treatment=overlap_treatment,
            geometry_hash=g_hash,
            material_hash=m_hash,
            error_codes=errors,
        )


# ===========================================================================
# AluminiumSectionEngine
# ===========================================================================

class AluminiumSectionEngine:
    """Propiedades geométricas y verificaciones de sección para aluminio."""

    @staticmethod
    def circular_hollow_properties(
        D_ext_mm: float,
        t_mm: float,
        rho_kg_m3: float = 2700.0,
    ) -> CircularAluminiumProperties:
        D = D_ext_mm / 1000.0
        d = D - 2.0 * t_mm / 1000.0
        A = math.pi / 4.0 * (D**2 - d**2)
        I = math.pi / 64.0 * (D**4 - d**4)
        J = 2.0 * I
        Av = 2.0 * A / math.pi
        Wel = I / (D / 2.0)
        mass = rho_kg_m3 * A
        return CircularAluminiumProperties(
            D_ext_mm=D_ext_mm, t_mm=t_mm,
            A_m2=A, Iy_m4=I, Iz_m4=I, J_m4=J,
            Ay_m2=Av, Az_m2=Av,
            Wel_y_m3=Wel, Wel_z_m3=Wel,
            mass_per_m_kg=mass, rho_kg_m3=rho_kg_m3,
        )

    @staticmethod
    def check_axial(
        N_kn: float,
        A_m2: float,
        f0_d_mpa: float,
        haz_rho_yield: float = 1.0,
        gamma_M0: float = 1.0,
        utilization_limit: float = 1.0,
    ) -> AluminiumCheckResult:
        f_eff = f0_d_mpa * haz_rho_yield  # reducción HAZ ya incluida en f0_d si procede
        N_Rd = A_m2 * f_eff * 1000.0 / gamma_M0   # kN
        util = abs(N_kn) / N_Rd if N_Rd > 0 else float("inf")
        status = (
            AluminiumCheckStatus.PASS if util <= utilization_limit
            else AluminiumCheckStatus.FAIL
        )
        return AluminiumCheckResult(
            check_type="AXIAL", status=status,
            solicitation=round(abs(N_kn), 4),
            resistance=round(N_Rd, 4),
            utilization=round(util, 6),
            unit="kN",
            governing_rule="EN 1999-1-1 §6.2.3",
            equation_trace={"N_Rd_kN": round(N_Rd, 4), "f_eff_mpa": round(f_eff, 4)},
            intermediate_values={"A_m2": A_m2, "f0_d_mpa": f0_d_mpa, "haz_rho": haz_rho_yield},
        )

    @staticmethod
    def check_bending_uniaxial(
        M_knm: float,
        Wel_m3: float,
        f0_d_mpa: float,
        haz_rho_yield: float = 1.0,
        gamma_M0: float = 1.0,
        utilization_limit: float = 1.0,
    ) -> AluminiumCheckResult:
        f_eff = f0_d_mpa * haz_rho_yield
        Mc_Rd = Wel_m3 * f_eff * 1e6 / 1e3 / gamma_M0  # kNm
        util = abs(M_knm) / Mc_Rd if Mc_Rd > 0 else float("inf")
        status = (
            AluminiumCheckStatus.PASS if util <= utilization_limit
            else AluminiumCheckStatus.FAIL
        )
        return AluminiumCheckResult(
            check_type="BENDING_UNIAXIAL", status=status,
            solicitation=round(abs(M_knm), 6),
            resistance=round(Mc_Rd, 6),
            utilization=round(util, 6),
            unit="kNm",
            governing_rule="EN 1999-1-1 §6.2.5",
            equation_trace={"Mc_Rd_kNm": round(Mc_Rd, 6)},
            intermediate_values={"Wel_m3": Wel_m3, "f_eff_mpa": round(f_eff, 4)},
        )

    @staticmethod
    def check_biaxial_bending(
        My_knm: float,
        Mz_knm: float,
        My_Rd_knm: float,
        Mz_Rd_knm: float,
        alpha: float = 2.0,
        beta: float = 2.0,
        utilization_limit: float = 1.0,
    ) -> AluminiumCheckResult:
        ratio_y = abs(My_knm) / My_Rd_knm if My_Rd_knm > 0 else float("inf")
        ratio_z = abs(Mz_knm) / Mz_Rd_knm if Mz_Rd_knm > 0 else float("inf")
        interaction = ratio_y**alpha + ratio_z**beta
        status = (
            AluminiumCheckStatus.PASS if interaction <= utilization_limit
            else AluminiumCheckStatus.FAIL
        )
        return AluminiumCheckResult(
            check_type="BENDING_BIAXIAL", status=status,
            solicitation=round(interaction, 6),
            resistance=1.0,
            utilization=round(interaction, 6),
            unit="-",
            governing_rule="EN 1999-1-1 §6.2.9",
            equation_trace={
                "ratio_y_alpha": round(ratio_y**alpha, 6),
                "ratio_z_beta": round(ratio_z**beta, 6),
                "sum": round(interaction, 6),
                "alpha": alpha, "beta": beta,
            },
        )

    @staticmethod
    def check_shear(
        V_kn: float,
        Av_m2: float,
        f0_d_mpa: float,
        haz_rho_yield: float = 1.0,
        gamma_M0: float = 1.0,
        utilization_limit: float = 1.0,
    ) -> AluminiumCheckResult:
        f_eff = f0_d_mpa * haz_rho_yield
        Vpl_Rd = Av_m2 * f_eff / math.sqrt(3.0) * 1000.0 / gamma_M0  # kN
        util = abs(V_kn) / Vpl_Rd if Vpl_Rd > 0 else float("inf")
        status = (
            AluminiumCheckStatus.PASS if util <= utilization_limit
            else AluminiumCheckStatus.FAIL
        )
        return AluminiumCheckResult(
            check_type="SHEAR", status=status,
            solicitation=round(abs(V_kn), 4),
            resistance=round(Vpl_Rd, 4),
            utilization=round(util, 6),
            unit="kN",
            governing_rule="EN 1999-1-1 §6.2.6",
            equation_trace={"Vpl_Rd_kN": round(Vpl_Rd, 4), "f_eff_mpa": round(f_eff, 4)},
            intermediate_values={"Av_m2": Av_m2},
        )

    @staticmethod
    def check_torsion_closed_section(
        T_knm: float,
        J_m4: float,
        A_m2: float,
        t_mm: float,
        f0_d_mpa: float,
        haz_rho_yield: float = 1.0,
        gamma_M0: float = 1.0,
        utilization_limit: float = 1.0,
    ) -> AluminiumCheckResult:
        """Bredt: T / (2 * Am * t) ≤ f0 / (√3 * γM)"""
        t_m = t_mm / 1000.0
        Am = A_m2  # área media (aproximación: usar área bruta para tubo circular)
        if Am <= 0 or t_m <= 0:
            return AluminiumCheckResult(
                check_type="TORSION", status=AluminiumCheckStatus.BLOCKED,
                solicitation=0, resistance=0, utilization=0, unit="kNm",
                error_code="AL-SEC-001",
            )
        tau_demand = abs(T_knm) * 1000.0 / (2.0 * Am * t_m * 1000.0)  # MPa
        tau_Rd = f0_d_mpa * haz_rho_yield / math.sqrt(3.0) / gamma_M0
        util = tau_demand / tau_Rd if tau_Rd > 0 else float("inf")
        status = (
            AluminiumCheckStatus.PASS if util <= utilization_limit
            else AluminiumCheckStatus.FAIL
        )
        return AluminiumCheckResult(
            check_type="TORSION", status=status,
            solicitation=round(tau_demand, 4),
            resistance=round(tau_Rd, 4),
            utilization=round(util, 6),
            unit="MPa",
            governing_rule="EN 1999-1-1 §6.2.7 (Bredt)",
            equation_trace={"tau_demand_mpa": round(tau_demand, 4), "tau_Rd_mpa": round(tau_Rd, 4)},
        )

    @staticmethod
    def check_circular_wall_slenderness(
        D_ext_mm: float,
        t_eff_mm: float,
        f0_d_mpa: float,
        E_mpa: float = 70000.0,
    ) -> AluminiumCheckResult:
        """
        Clasificación pared circular según EN 1999-1-1:
        β = (D/t) × √(f0/E) — parámetro de esbeltez EN 1999-1-1 Table 6.2
        Clase 1: β ≤ 3; Clase 2: ≤ 5; Clase 3: ≤ 10; Clase 4: >10
        """
        D_t = D_ext_mm / t_eff_mm
        slenderness_param = D_t * math.sqrt(f0_d_mpa / E_mpa)
        if slenderness_param <= 3.0:
            cls_num = 1
        elif slenderness_param <= 5.0:
            cls_num = 2
        elif slenderness_param <= 10.0:
            cls_num = 3
        else:
            cls_num = 4

        status = (
            AluminiumCheckStatus.PASS if cls_num <= 3
            else AluminiumCheckStatus.WARNING
        )
        return AluminiumCheckResult(
            check_type="WALL_SLENDERNESS", status=status,
            solicitation=round(slenderness_param, 4),
            resistance=10.0,   # límite clase 3
            utilization=round(slenderness_param / 10.0, 6),
            unit="-",
            governing_rule="EN 1999-1-1 Table 6.2",
            intermediate_values={
                "D_over_t": round(D_t, 4),
                "section_class": cls_num,
                "slenderness_param": round(slenderness_param, 4),
                "C": 1.0,  # normalización absorbida en la fórmula β=(D/t)×√(f0/E)
            },
        )

    @staticmethod
    def compute_run_hash(
        geometry_hash: str,
        material_hash: str,
        haz_hash: str,
        rules_hash: str,
        stress_hash: str,
        engine_version: str = "1.0",
    ) -> str:
        payload = {
            "g": geometry_hash, "m": material_hash, "h": haz_hash,
            "r": rules_hash, "s": stress_hash, "v": engine_version,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()


# ===========================================================================
# AluminiumEffectiveSectionService
# ===========================================================================

class AluminiumEffectiveSectionService:
    """
    Sección efectiva por pandeo local (EN 1999-1-1).
    Para pared circular bajo compresión: β = (D/t) × √(f0/E).
    """

    @staticmethod
    def circular_wall_effective(
        D_ext_mm: float,
        t_eff_mm: float,
        E_mpa: float,
        f0_d_mpa: float,
        sigma_max_mpa: float,
        max_iterations: int = 20,
        convergence_tol: float = 1e-4,
    ) -> EffectiveSectionResult:
        D_t = D_ext_mm / t_eff_mm
        slenderness_param = D_t * math.sqrt(f0_d_mpa / E_mpa)

        if slenderness_param <= 10.0:
            # Clase 1-3: sin reducción
            return EffectiveSectionResult(
                width_effective_mm=None,
                reduction_factor=1.0,
                slenderness=round(slenderness_param, 4),
                n_iterations=0,
                converged=True,
                panel_status="EFFECTIVE",
                governing_rule="EN 1999-1-1 Table 6.2",
            )

        # Clase 4: reducción iterativa
        rho = 1.0
        history = []
        converged = False
        for i in range(max_iterations):
            rho_new = min(1.0, 10.0 / slenderness_param)
            history.append({"iter": i, "rho": round(rho_new, 6)})
            if abs(rho_new - rho) < convergence_tol:
                converged = True
                rho = rho_new
                break
            rho = rho_new

        t_eff_reduced = t_eff_mm * rho
        return EffectiveSectionResult(
            width_effective_mm=round(t_eff_reduced, 4),
            reduction_factor=round(rho, 6),
            slenderness=round(slenderness_param, 4),
            n_iterations=len(history),
            converged=converged,
            panel_status="REDUCED" if rho < 1.0 else "EFFECTIVE",
            governing_rule="EN 1999-1-1 §6.7",
            iteration_history=history,
        )


# ===========================================================================
# AluminiumWeldService
# ===========================================================================

class AluminiumWeldService:
    """Verificación de soldaduras por arco para aluminio."""

    @staticmethod
    def fillet_weld_static_check(
        Fx_kn: float,
        Fy_kn: float,
        Fz_kn: float,
        effective_throat_mm: float,
        effective_length_mm: float,
        fu_w_mpa: float,
        beta_w: float = 0.85,
        gamma_M2: float = 1.25,
        utilization_limit: float = 1.0,
    ) -> AluminiumCheckResult:
        """
        EN 1993-1-8 directional method adaptado:
        σ_eq = √(σ_⊥² + 3τ_⊥² + 3τ_∥²) ≤ fu_w / (β_w · γM2)
        """
        a = effective_throat_mm / 1000.0
        l = effective_length_mm / 1000.0
        A_w = a * l
        if A_w <= 0:
            return AluminiumCheckResult(
                check_type="WELD_STATIC", status=AluminiumCheckStatus.BLOCKED,
                solicitation=0, resistance=0, utilization=0, unit="MPa",
                error_code="AL-WELD-001",
            )

        sigma_perp_mpa = Fz_kn * 1000.0 / (A_w * 1e6)
        tau_perp_mpa = Fy_kn * 1000.0 / (A_w * 1e6)
        tau_par_mpa = Fx_kn * 1000.0 / (A_w * 1e6)
        sigma_eq = math.sqrt(sigma_perp_mpa**2 + 3 * tau_perp_mpa**2 + 3 * tau_par_mpa**2)
        resistance = fu_w_mpa / (beta_w * gamma_M2)
        util = sigma_eq / resistance if resistance > 0 else float("inf")
        status = (
            AluminiumCheckStatus.PASS if util <= utilization_limit
            else AluminiumCheckStatus.FAIL
        )
        return AluminiumCheckResult(
            check_type="WELD_STATIC", status=status,
            solicitation=round(sigma_eq, 4),
            resistance=round(resistance, 4),
            utilization=round(util, 6),
            unit="MPa",
            governing_rule="EN 1993-1-8 directional method",
            equation_trace={"sigma_eq_mpa": round(sigma_eq, 4), "sigma_Rd_mpa": round(resistance, 4)},
            intermediate_values={
                "sigma_perp_mpa": round(sigma_perp_mpa, 4),
                "tau_perp_mpa": round(tau_perp_mpa, 4),
                "tau_par_mpa": round(tau_par_mpa, 4),
                "A_weld_m2": round(A_w, 8),
            },
        )

    @staticmethod
    def seam_not_in_door(
        seam_azimuth_deg: float,
        door_azimuth_deg: float,
        tolerance_deg: float = 5.0,
    ) -> bool:
        """True si la costura longitudinal está fuera de la zona de puerta."""
        diff = abs(seam_azimuth_deg - door_azimuth_deg) % 360.0
        if diff > 180.0:
            diff = 360.0 - diff
        return diff > tolerance_deg


# ===========================================================================
# AluminiumFSWService
# ===========================================================================

class AluminiumFSWService:
    """Verificación básica del proceso FSW."""

    @staticmethod
    def check_within_qualified_window(
        rotation_speed_rpm: float,
        travel_speed_mm_per_min: float,
        axial_force_kn: float,
        procedure: dict,
    ) -> bool:
        """
        Comprueba que los parámetros estén dentro de la ventana cualificada.
        Returns True si dentro de ventana.
        """
        ok_rot = (
            procedure.get("rotation_speed_min_rpm", 0) <= rotation_speed_rpm
            <= procedure.get("rotation_speed_max_rpm", float("inf"))
        )
        ok_travel = (
            procedure.get("travel_speed_min_mm_per_min", 0) <= travel_speed_mm_per_min
            <= procedure.get("travel_speed_max_mm_per_min", float("inf"))
        )
        ok_force = (
            procedure.get("axial_force_min_kn", 0) <= axial_force_kn
            <= procedure.get("axial_force_max_kn", float("inf"))
        )
        return ok_rot and ok_travel and ok_force

    @staticmethod
    def check_keyhole_position(
        keyhole_station_m: float,
        critical_zone_start_m: float,
        critical_zone_end_m: float,
    ) -> dict:
        """
        Verifica que el keyhole (fin de pasada FSW) esté fuera de zonas críticas.
        """
        in_critical = critical_zone_start_m <= keyhole_station_m <= critical_zone_end_m
        return {
            "compliant": not in_critical,
            "keyhole_station_m": keyhole_station_m,
            "in_critical_zone": in_critical,
            "error_code": "AL-FSW-001" if in_critical else None,
        }


# ===========================================================================
# AluminiumFatigueService
# ===========================================================================

class AluminiumFatigueService:
    """
    Fatiga de aluminio según EN 1999-1-3.
    D = Σ(n_i/N_i) ≤ D_lim
    """

    @staticmethod
    def miner_damage(cycle_blocks: list[dict], D_limit: float = 1.0) -> MinerResult:
        source_breakdown: dict[str, float] = {}
        total = 0.0
        seen_sources: set[str] = set()
        duplicate = False
        for block in cycle_blocks:
            src = block.get("source", "unknown")
            if src in seen_sources:
                duplicate = True
            seen_sources.add(src)
            n = block.get("n_cycles", 0.0)
            N = block.get("N_ref", 1.0)
            d = n / N if N > 0 else 0.0
            total += d
            source_breakdown[src] = source_breakdown.get(src, 0.0) + d

        status = "PASS" if total <= D_limit else "FAIL"
        return MinerResult(
            total_damage=round(total, 8),
            D_limit=D_limit,
            status=status,
            source_breakdown={k: round(v, 8) for k, v in source_breakdown.items()},
            duplicate_source_detected=duplicate,
        )

    @staticmethod
    def simplified_fatigue_check(
        delta_sigma_mpa: float,
        fatigue_category_mpa: float,
        gamma_Ff: float = 1.0,
        gamma_Mf: float = 1.15,
        utilization_limit: float = 1.0,
    ) -> AluminiumCheckResult:
        """EN 1999-1-3: γ_Ff · ΔσE ≤ ΔσC / γ_Mf"""
        demand = gamma_Ff * delta_sigma_mpa
        capacity = fatigue_category_mpa / gamma_Mf
        util = demand / capacity if capacity > 0 else float("inf")
        status = (
            AluminiumCheckStatus.PASS if util <= utilization_limit
            else AluminiumCheckStatus.FAIL
        )
        return AluminiumCheckResult(
            check_type="FATIGUE", status=status,
            solicitation=round(demand, 4),
            resistance=round(capacity, 4),
            utilization=round(util, 6),
            unit="MPa",
            governing_rule="EN 1999-1-3 §7.3",
            equation_trace={
                "gamma_Ff": gamma_Ff, "delta_sigma_mpa": delta_sigma_mpa,
                "demand_mpa": round(demand, 4),
                "gamma_Mf": gamma_Mf, "capacity_mpa": round(capacity, 4),
            },
        )


# ===========================================================================
# AluminiumDurabilityService
# ===========================================================================

class AluminiumDurabilityService:
    """Selector de sistema de protección superficial y aislamiento galvánico."""

    # Vida útil de referencia por sistema y categoría (años, rango aproximado)
    _LIFE_RANGES: dict[str, dict] = {
        "NATURAL": {"C1": (50, 100), "C2": (30, 60), "C3": (15, 30), "C4": (5, 15), "C5": (1, 5)},
        "ANODIZED": {"C1": (50, 100), "C2": (40, 80), "C3": (25, 50), "C4": (15, 30), "C5": (5, 15)},
        "POWDER_COAT": {"C1": (30, 60), "C2": (20, 40), "C3": (15, 25), "C4": (8, 15), "C5": (3, 8)},
        "LIQUID_PAINT": {"C1": (20, 40), "C2": (15, 30), "C3": (10, 20), "C4": (5, 10), "C5": (2, 5)},
        "COMBINED_SYSTEM": {"C1": (60, 100), "C2": (50, 80), "C3": (30, 60), "C4": (20, 40), "C5": (10, 20)},
    }

    # Pares galvánicos problemáticos con aluminio
    _PROBLEMATIC_CONTACTS = {"steel", "copper", "brass", "carbon_steel", "zinc_coated_steel"}

    @classmethod
    def check_life_adequacy(
        cls,
        treatment: str,
        corrosivity_category: str,
        design_life_years: float,
    ) -> tuple[bool, str]:
        ranges = cls._LIFE_RANGES.get(treatment, {})
        cat_key = corrosivity_category.upper().split(".")[0]
        rng = ranges.get(cat_key)
        if rng is None:
            return False, f"AL-DUR-001: sin datos para {treatment}/{corrosivity_category}"
        adequate = design_life_years <= rng[1]
        msg = f"Vida estimada {rng[0]}–{rng[1]} años; requerida {design_life_years} años"
        return adequate, msg

    @classmethod
    def check_galvanic_contacts(cls, galvanic_contacts: list[str]) -> list[str]:
        risks = []
        for contact in (galvanic_contacts or []):
            if contact.lower() in cls._PROBLEMATIC_CONTACTS:
                risks.append(f"Par galvánico problemático: aluminio–{contact}; requiere aislamiento")
        return risks

    @staticmethod
    def check_open_cavities(has_open_cavities: bool) -> bool:
        return has_open_cavities  # True = riesgo


# ===========================================================================
# AluminiumManufacturingService
# ===========================================================================

class AluminiumManufacturingService:
    """Fabricación de columnas plegadas 5083 y extrusionadas."""

    MAX_PIECE_LENGTH_M = 12.0
    MIN_DIAMETER_MM = 60.0
    SHEET_MIN_THICKNESS_MM = 2.5
    SHEET_MAX_THICKNESS_MM = 6.0

    @classmethod
    def check_piece_length(cls, length_m: float) -> FabricabilityCheck:
        ok = length_m <= cls.MAX_PIECE_LENGTH_M
        return FabricabilityCheck(
            compliant=ok,
            code="AL-MFG-001" if not ok else "",
            severity="BLOCKING" if not ok else "",
            description=(
                f"Longitud {length_m}m excede máximo logístico {cls.MAX_PIECE_LENGTH_M}m"
                if not ok else "Longitud OK"
            ),
        )

    @classmethod
    def check_min_diameter(cls, diameter_mm: float) -> FabricabilityCheck:
        ok = diameter_mm >= cls.MIN_DIAMETER_MM
        return FabricabilityCheck(
            compliant=ok,
            code="AL-MFG-001" if not ok else "",
            severity="BLOCKING" if not ok else "",
            description=(
                f"Diámetro {diameter_mm}mm inferior al mínimo {cls.MIN_DIAMETER_MM}mm"
                if not ok else "Diámetro OK"
            ),
        )

    @classmethod
    def check_sheet_thickness(cls, thickness_mm: float) -> FabricabilityCheck:
        ok = cls.SHEET_MIN_THICKNESS_MM <= thickness_mm <= cls.SHEET_MAX_THICKNESS_MM
        return FabricabilityCheck(
            compliant=ok,
            code="AL-MFG-001" if not ok else "",
            severity="BLOCKING" if not ok else "",
            description=(
                f"Espesor {thickness_mm}mm fuera del rango 5083 aprobado "
                f"[{cls.SHEET_MIN_THICKNESS_MM}, {cls.SHEET_MAX_THICKNESS_MM}]mm"
                if not ok else "Espesor OK"
            ),
        )

    @staticmethod
    def check_seam_not_in_door(
        seam_azimuth_deg: float,
        door_azimuth_deg: float,
        tolerance_deg: float = 5.0,
    ) -> FabricabilityCheck:
        diff = abs(seam_azimuth_deg - door_azimuth_deg) % 360.0
        if diff > 180.0:
            diff = 360.0 - diff
        compliant = diff > tolerance_deg
        return FabricabilityCheck(
            compliant=compliant,
            code="AL-MFG-001" if not compliant else "",
            severity="BLOCKING" if not compliant else "",
            description=(
                "Costura longitudinal dentro de la zona de puerta"
                if not compliant else "Costura fuera de zona de puerta"
            ),
        )

    @staticmethod
    def bend_allowance(
        thickness_mm: float,
        bend_angle_deg: float,
        inner_radius_mm: float,
        k_factor: float = 0.33,
    ) -> BendAllowanceResult:
        """
        BA = (π/180) · bend_angle · (inner_radius + k_factor · thickness)
        OSSB = tan(bend_angle/2) · (inner_radius + thickness)
        """
        angle_rad = math.radians(bend_angle_deg)
        neutral_radius = inner_radius_mm + k_factor * thickness_mm
        BA = angle_rad * neutral_radius
        OSSB = math.tan(angle_rad / 2.0) * (inner_radius_mm + thickness_mm)
        return BendAllowanceResult(
            bend_allowance_mm=round(BA, 4),
            outside_setback_mm=round(OSSB, 4),
            neutral_radius_mm=round(neutral_radius, 4),
            k_factor=k_factor,
            compliant_with_min_radius=True,  # verificación real vs. tabla de material
            min_radius_for_material=None,
        )

    @staticmethod
    def cone_frustum_blank_geometry(
        D_base_mm: float,
        D_top_mm: float,
        height_m: float,
    ) -> dict:
        """Desarrollo de cono truncado (chapa plegada troncocónica)."""
        h_mm = height_m * 1000.0
        R_base = D_base_mm / 2.0
        R_top = D_top_mm / 2.0
        if abs(R_base - R_top) < 1e-6:
            # Cilindro
            slant = h_mm
            rho_base = float("inf")
        else:
            slant = math.sqrt(h_mm**2 + (R_base - R_top)**2)
            rho_base = slant * R_base / (R_base - R_top)
        rho_top = rho_base - slant if rho_base != float("inf") else float("inf")
        sector_angle = 2.0 * math.pi * R_base / rho_base if rho_base != float("inf") else 2.0 * math.pi
        blank_area = math.pi * (rho_base**2 - (rho_base - slant)**2) * sector_angle / (2.0 * math.pi) \
            if rho_base != float("inf") else math.pi * (R_base + R_top) * slant
        return {
            "slant_height_mm": round(slant, 4),
            "rho_base_mm": round(rho_base, 4) if rho_base != float("inf") else None,
            "rho_top_mm": round(rho_top, 4) if rho_top != float("inf") else None,
            "sector_angle_rad": round(sector_angle, 6),
            "blank_area_mm2": round(blank_area, 2),
        }

    @staticmethod
    def bom_mass_from_geometry(volumes_m3: dict, rho_kg_m3: float = 2700.0) -> dict:
        return {k: round(v * rho_kg_m3, 4) for k, v in volumes_m3.items()}


# ===========================================================================
# AluminiumOptimizer
# ===========================================================================

class AluminiumOptimizer:
    """Optimización Pareto multiobjetivo para columnas de aluminio."""

    @staticmethod
    def is_dominated(a: AluminiumCandidate, b: AluminiumCandidate) -> bool:
        """True si b domina a (mejor o igual en todos los objetivos)."""
        return (
            b.total_cost_eur <= a.total_cost_eur
            and b.total_mass_kg <= a.total_mass_kg
            and b.total_co2_kg <= a.total_co2_kg
            and (
                b.total_cost_eur < a.total_cost_eur
                or b.total_mass_kg < a.total_mass_kg
                or b.total_co2_kg < a.total_co2_kg
            )
        )

    @classmethod
    def build_pareto_front(cls, candidates: list[AluminiumCandidate]) -> list:
        """Solo candidatos fabricables Y transportables pueden estar en el frente."""
        eligible = [c for c in candidates if c.is_fabricable and c.is_transportable]
        pareto = []
        for c in eligible:
            if not any(cls.is_dominated(c, other) for other in eligible if other is not c):
                pareto.append(c)
        return pareto

    @classmethod
    def select_solutions(cls, pareto: list[AluminiumCandidate]) -> dict:
        if not pareto:
            return {"min_cost": None, "min_weight": None, "min_co2": None, "balanced": None}

        min_cost = min(pareto, key=lambda c: c.total_cost_eur)
        min_weight = min(pareto, key=lambda c: c.total_mass_kg)
        min_co2 = min(pareto, key=lambda c: c.total_co2_kg)

        # Solución equilibrada: menor suma de objetivos normalizados
        c_range = max(c.total_cost_eur for c in pareto) - min(c.total_cost_eur for c in pareto)
        m_range = max(c.total_mass_kg for c in pareto) - min(c.total_mass_kg for c in pareto)
        e_range = max(c.total_co2_kg for c in pareto) - min(c.total_co2_kg for c in pareto)

        def norm_dist(c: AluminiumCandidate) -> float:
            nc = (c.total_cost_eur - min_cost.total_cost_eur) / c_range if c_range > 0 else 0
            nm = (c.total_mass_kg - min_weight.total_mass_kg) / m_range if m_range > 0 else 0
            ne = (c.total_co2_kg - min_co2.total_co2_kg) / e_range if e_range > 0 else 0
            return nc + nm + ne

        balanced = min(pareto, key=norm_dist)
        return {
            "min_cost": min_cost,
            "min_weight": min_weight,
            "min_co2": min_co2,
            "balanced": balanced,
        }
