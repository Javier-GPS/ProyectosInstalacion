"""
Salvi Studio · Columns — Servicios Fase 8: Detalles Locales.

Motor determinista de cálculo. Mismo input + versión = mismo resultado.
"""
from __future__ import annotations
import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from app.models.db.details import (
    OpeningType, DetailRoute, ReinforcementFamily,
    DetailCheckStatus, FEAStatus,
)


# ============================================================================
# Dataclasses de resultado
# ============================================================================

@dataclass
class OpeningValidation:
    route: DetailRoute
    status: DetailCheckStatus
    blocking_step: Optional[int]
    decision_trace: List[str]
    geometric_hash: str
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class NetSectionProperties:
    A_gross_m2: float
    A_net_m2: float
    A_reduction_pct: float
    centroid_x_m: float
    centroid_y_m: float
    Iy_net_m4: float
    Iz_net_m4: float
    Iyz_net_m4: float
    J_net_m4: float
    alpha_principal_deg: float
    I1_m4: float
    I2_m4: float
    Wel_y_m3: float
    Wel_z_m3: float
    contrast_delta_pct: float
    contrast_passed: bool
    method: str = "INTEGRATION+FIBER"
    governing_rule: str = "EN 40-3-3 § sección neta"


@dataclass
class CheckResult:
    check_type: str
    status: DetailCheckStatus
    demand: float
    resistance: float
    utilization: float
    unit: str
    governing_rule: str
    error_code: Optional[str] = None
    intermediate_values: dict = field(default_factory=dict)


@dataclass
class WeldGroupCalc:
    total_length_mm: float
    centroid_x_mm: float
    centroid_y_mm: float
    Ip_polar_mm4: float
    f_res_max_n_mm: float
    capacity_n_mm: float
    utilization: float
    status: DetailCheckStatus
    governing_rule: str
    intermediate_values: dict = field(default_factory=dict)


@dataclass
class ReinfCandidate:
    family: ReinforcementFamily
    material_code: str
    thickness_mm: float
    width_mm: Optional[float]
    cost_eur: float
    mass_kg: float
    co2_kg: float
    feasible: bool = True
    pareto_dominated: Optional[bool] = None
    rejection_reason: Optional[str] = None


@dataclass
class AccessibilityResult:
    accessible: bool
    tool_clearance_ok: bool
    cable_radius_ok: bool
    all_equipment_fit: bool
    extraction_sequence: List[str] = field(default_factory=list)
    blocking_equipment: Optional[str] = None
    error_code: Optional[str] = None
    governing_rule: str = "EN 40-2 — accesibilidad y mantenimiento"


@dataclass
class FEAActivation:
    fea_required: bool
    activation_reasons: List[str]
    route: DetailRoute


@dataclass
class NormativeRouteResult:
    route: DetailRoute
    steps_passed: List[bool]
    blocking_step: Optional[int]
    decision_trace: List[str]
    input_hash: str


# ============================================================================
# OpeningService
# ============================================================================

class OpeningService:
    """Validación geométrica de huecos."""

    # Límites normativos según EN 40-2 (simplificados)
    MIN_CORNER_RADIUS_MM = 3.0
    MIN_DISTANCE_TO_JOINT_MM = 100.0
    MAX_OPENING_RATIO = 0.70   # máximo ancho_hueco / diámetro exterior

    @classmethod
    def validate_geometry(
        cls,
        D_ext_mm: float,
        t_wall_mm: float,
        width_mm: float,
        height_mm: float,
        corner_radius_mm: float,
        station_bottom_m: float,
        station_top_m: float,
        height_total_m: float,
        opening_type: OpeningType = OpeningType.RECTANGULAR_ROUNDED,
        min_corner_radius_mm: float = 3.0,
        nearby_joint_m: Optional[float] = None,
        nearby_openings: Optional[List[dict]] = None,
    ) -> OpeningValidation:
        errors = []
        warnings = []
        trace = []

        # Hash determinista
        payload = {
            "De": D_ext_mm, "t": t_wall_mm, "w": width_mm, "h": height_mm,
            "r": corner_radius_mm, "z0": station_bottom_m, "z1": station_top_m,
            "type": opening_type.value,
        }
        geo_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

        # Paso 1: dentro del fuste
        opening_top_m = station_top_m
        ok1 = (station_bottom_m >= 0.0) and (opening_top_m <= height_total_m)
        trace.append(f"Paso 1: hueco dentro del fuste [0, {height_total_m}m]: {'OK' if ok1 else 'FAIL'}")
        if not ok1:
            errors.append(f"LOC-GEO-001: hueco ({station_bottom_m:.2f}–{opening_top_m:.2f}m) fuera del fuste (0–{height_total_m:.2f}m)")

        # Paso 2: radio mínimo de esquina
        ok2 = corner_radius_mm >= min_corner_radius_mm or opening_type == OpeningType.OVAL
        trace.append(f"Paso 2: radio de esquina {corner_radius_mm}mm ≥ {min_corner_radius_mm}mm: {'OK' if ok2 else 'FAIL'}")
        if not ok2:
            errors.append(f"LOC-GEO-001: radio de esquina {corner_radius_mm}mm < mínimo {min_corner_radius_mm}mm")

        # Paso 3: ratio ancho/diámetro
        ratio = width_mm / D_ext_mm if D_ext_mm > 0 else float("inf")
        ok3 = ratio <= cls.MAX_OPENING_RATIO
        trace.append(f"Paso 3: ratio ancho/diámetro {ratio:.3f} ≤ {cls.MAX_OPENING_RATIO}: {'OK' if ok3 else 'WARN'}")
        if not ok3:
            warnings.append(f"ratio ancho/diámetro {ratio:.3f} > {cls.MAX_OPENING_RATIO} — requiere FEM o familia ensayada")

        # Paso 4: distancia a junta
        ok4 = True
        if nearby_joint_m is not None:
            dist = abs(station_bottom_m - nearby_joint_m)
            ok4 = dist >= cls.MIN_DISTANCE_TO_JOINT_MM / 1000.0
            trace.append(f"Paso 4: distancia a junta {dist*1000:.0f}mm ≥ {cls.MIN_DISTANCE_TO_JOINT_MM}mm: {'OK' if ok4 else 'FAIL'}")
            if not ok4:
                errors.append(f"LOC-GEO-003: hueco a {dist*1000:.0f}mm de la junta — mínimo {cls.MIN_DISTANCE_TO_JOINT_MM}mm")
        else:
            trace.append("Paso 4: no hay junta próxima declarada — OK")

        # Paso 5: solapamiento entre huecos
        ok5 = True
        if nearby_openings:
            for other in nearby_openings:
                if "station_bottom_m" in other and "station_top_m" in other:
                    overlap = not (opening_top_m <= other["station_bottom_m"] or station_bottom_m >= other["station_top_m"])
                    if overlap:
                        ok5 = False
                        errors.append(f"LOC-GEO-002: hueco solapa con otro ({other})")
        trace.append(f"Paso 5: solapamientos: {'NINGUNO' if ok5 else 'DETECTADO'}")

        # Clasificador de ruta
        all_ok = ok1 and ok2 and ok3 and ok4 and ok5
        has_errors = len(errors) > 0

        blocking_step = None
        for i, ok in enumerate([ok1, ok2, True, ok4, ok5]):
            if not ok:
                blocking_step = i + 1
                break

        if not ok1 or not ok2 or not ok4 or not ok5:
            route = DetailRoute.R8_E  # BLOQUEADO
        elif ratio > cls.MAX_OPENING_RATIO:
            route = DetailRoute.R8_C  # requiere FEM
        else:
            route = DetailRoute.R8_B  # analítico

        status = DetailCheckStatus.BLOCKED if route == DetailRoute.R8_E else (
            DetailCheckStatus.FEM_REQUIRED if route == DetailRoute.R8_C else DetailCheckStatus.PASS
        )

        return OpeningValidation(
            route=route,
            status=status,
            blocking_step=blocking_step,
            decision_trace=trace,
            geometric_hash=geo_hash,
            errors=errors,
            warnings=warnings,
        )

    @staticmethod
    def geometric_hash(D_ext_mm: float, width_mm: float, height_mm: float,
                       corner_radius_mm: float, orientation_deg: float) -> str:
        payload = {"De": D_ext_mm, "w": width_mm, "h": height_mm,
                   "r": corner_radius_mm, "ang": orientation_deg}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


# ============================================================================
# LocalSectionService
# ============================================================================

class LocalSectionService:
    """Propiedades de sección neta y compuesta con contraste por fibras."""

    CONTRAST_TOLERANCE_PCT = 0.5  # ≤ 0.5% diferencia entre métodos

    @staticmethod
    def annular_gross(D_ext_mm: float, D_int_mm: float) -> dict:
        """Sección bruta anular."""
        De = D_ext_mm / 1000.0
        Di = D_int_mm / 1000.0
        A = math.pi / 4.0 * (De**2 - Di**2)
        I = math.pi / 64.0 * (De**4 - Di**4)
        return {"A_m2": A, "I_m4": I, "De": De, "Di": Di}

    @staticmethod
    def rectangular_opening_area(width_mm: float, height_mm: float, corner_radius_mm: float = 0.0) -> float:
        """Área de la abertura rectangular con esquinas redondeadas."""
        w = width_mm / 1000.0
        h = height_mm / 1000.0
        r = corner_radius_mm / 1000.0
        # Área = rectángulo - 4 esquinas + 4 cuartos de círculo
        A_rect = w * h
        if r > 0:
            # Quitar cuatro cuartos de cuadrado y añadir cuatro cuartos de círculo
            A_rect -= 4.0 * r**2 + 4.0 * math.pi * r**2 / 4.0
            A_rect += math.pi * r**2  # los 4 cuartos de círculo suman un círculo completo
        return max(A_rect, 0.0)

    @classmethod
    def net_section(
        cls,
        D_ext_mm: float,
        t_wall_mm: float,
        width_mm: float,
        height_mm: float,
        corner_radius_mm: float = 0.0,
        orientation_deg: float = 0.0,
        contrast_tolerance_pct: float = 0.5,
    ) -> NetSectionProperties:
        """
        Propiedades de sección neta por sustracción geométrica.
        Dos métodos independientes: integración y fibras (discretización).
        """
        D_int_mm = D_ext_mm - 2.0 * t_wall_mm
        if D_int_mm <= 0:
            raise ValueError("LOC-GEO-001: t_wall_mm excede el radio exterior")

        gross = cls.annular_gross(D_ext_mm, D_int_mm)
        A_gross = gross["A_m2"]
        I_gross = gross["I_m4"]
        De = gross["De"]

        # Área del hueco
        A_opening = cls.rectangular_opening_area(width_mm, height_mm, corner_radius_mm)

        # Sección neta (método 1: integración simplificada)
        A_net = A_gross - A_opening

        # Desplazamiento del centroide
        # Para un hueco en el lado (θ=0), el centroide se desplaza en x
        ang = math.radians(orientation_deg)
        D_mid = (D_ext_mm - t_wall_mm) / 2.0 / 1000.0  # radio medio del muro
        # Centroide del hueco aprox. en D_mid
        x_opening = D_mid * math.cos(ang)
        y_opening = D_mid * math.sin(ang)

        cx = -A_opening * x_opening / A_net if A_net > 0 else 0.0
        cy = -A_opening * y_opening / A_net if A_net > 0 else 0.0

        # Momentos de inercia netos (Steiner)
        h_op = height_mm / 1000.0
        w_op = width_mm / 1000.0
        I_opening_y = (w_op * h_op**3) / 12.0
        I_opening_z = (h_op * w_op**3) / 12.0

        Iy_net = I_gross - I_opening_y - A_opening * y_opening**2
        Iz_net = I_gross - I_opening_z - A_opening * x_opening**2
        Iyz_net = -A_opening * x_opening * y_opening  # sección asimétrica

        # Inercia torsional (sección abierta — reducción significativa)
        # Para sección circular con hueco: J ≈ J_closed × (1 - k_open)
        # k_open ~ (w_op / (π × Dm)) donde Dm es diámetro medio
        Dm = (D_ext_mm - t_wall_mm) / 1000.0
        psi_open = w_op / (math.pi * Dm) if Dm > 0 else 0.0
        J_closed = math.pi / 32.0 * (gross["De"]**4 - gross["Di"]**4)
        # Modelo simplificado de sección abierta con hueco
        # J_net ~ J_closed × (1 - psi_open)³  (reducción cúbica conservadora)
        J_net = J_closed * max(0.0, (1.0 - psi_open))**3

        # Ejes principales
        theta = 0.5 * math.atan2(2.0 * Iyz_net, Iy_net - Iz_net) if abs(Iy_net - Iz_net) > 1e-20 else 0.0
        alpha_deg = math.degrees(theta)
        avg = (Iy_net + Iz_net) / 2.0
        diff = math.sqrt(((Iy_net - Iz_net) / 2.0)**2 + Iyz_net**2)
        I1 = avg + diff
        I2 = avg - diff

        # Módulos elásticos (fibra extrema real = De/2)
        Wel_y = Iy_net / (De / 2.0) if De > 0 else 0.0
        Wel_z = Iz_net / (De / 2.0) if De > 0 else 0.0

        # Contraste por fibras (discretización de 36 elementos)
        A_net_fiber = cls._fiber_area(D_ext_mm, D_int_mm, width_mm, height_mm, orientation_deg)
        delta_pct = abs(A_net - A_net_fiber) / A_gross * 100.0 if A_gross > 0 else 0.0
        contrast_passed = delta_pct <= contrast_tolerance_pct

        if not contrast_passed:
            raise ValueError(
                f"LOC-SEC-001: contraste de sección excede tolerancia "
                f"({delta_pct:.3f}% > {contrast_tolerance_pct}%) — BLOQUEADO"
            )

        A_reduction = (1.0 - A_net / A_gross) * 100.0

        return NetSectionProperties(
            A_gross_m2=round(A_gross, 8),
            A_net_m2=round(A_net, 8),
            A_reduction_pct=round(A_reduction, 3),
            centroid_x_m=round(cx, 8),
            centroid_y_m=round(cy, 8),
            Iy_net_m4=round(Iy_net, 14),
            Iz_net_m4=round(Iz_net, 14),
            Iyz_net_m4=round(Iyz_net, 14),
            J_net_m4=round(J_net, 14),
            alpha_principal_deg=round(alpha_deg, 4),
            I1_m4=round(I1, 14),
            I2_m4=round(I2, 14),
            Wel_y_m3=round(Wel_y, 12),
            Wel_z_m3=round(Wel_z, 12),
            contrast_delta_pct=round(delta_pct, 4),
            contrast_passed=contrast_passed,
        )

    @staticmethod
    def _fiber_area(D_ext_mm: float, D_int_mm: float, width_mm: float,
                    height_mm: float, orientation_deg: float, n_fibers: int = 36) -> float:
        """Área neta por discretización angular (método de fibras)."""
        De = D_ext_mm / 1000.0
        Di = D_int_mm / 1000.0
        w_half = width_mm / 2.0 / 1000.0
        h_half = height_mm / 2.0 / 1000.0
        ang = math.radians(orientation_deg)

        A_fiber = 0.0
        d_theta = 2.0 * math.pi / n_fibers
        D_mid = (De + Di) / 2.0 / 2.0  # radio medio en metros

        for i in range(n_fibers):
            theta = i * d_theta
            x = D_mid * math.cos(theta)
            y = D_mid * math.sin(theta)

            # Rotar al sistema local del hueco
            x_loc = x * math.cos(-ang) - y * math.sin(-ang)
            y_loc = x * math.sin(-ang) + y * math.cos(-ang)

            # Área aproximada de la fibra (sector anular)
            t_eff = (De - Di) / 2.0
            dA = t_eff * D_mid * d_theta

            # Descontar si la fibra cae dentro del hueco
            in_opening = (abs(x_loc) <= w_half) and (abs(y_loc) <= h_half)
            if not in_opening:
                A_fiber += dA

        return A_fiber


# ============================================================================
# DetailCheckService
# ============================================================================

class DetailCheckService:
    """Verificaciones locales de resistencia y estabilidad."""

    @staticmethod
    def check_net_section_stress(
        sigma_nom_mpa: float,
        fy_mpa: float,
        gamma_M0: float = 1.0,
    ) -> CheckResult:
        """Tensión nominal en sección neta ≤ fy/γM0."""
        f_yd = fy_mpa / gamma_M0
        util = abs(sigma_nom_mpa) / f_yd if f_yd > 0 else float("inf")
        ok = util <= 1.0
        return CheckResult(
            check_type="NET_SECTION_STRESS",
            status=DetailCheckStatus.PASS if ok else DetailCheckStatus.FAIL,
            demand=round(abs(sigma_nom_mpa), 4),
            resistance=round(f_yd, 4),
            utilization=round(util, 4),
            unit="MPa",
            governing_rule="EN 40-3-3 / EC3 §6.2 — sección neta",
        )

    @staticmethod
    def check_ligament_slenderness(
        b_free_mm: float,
        t_mm: float,
        fy_mpa: float,
        E_mpa: float = 210000.0,
        gamma_M1: float = 1.0,
    ) -> CheckResult:
        """
        Verificación de ligamento lateral:
        λ = b/t × √(fy/E) — clasificación de sección local.
        Límites EC3: Clase 1 λ ≤ 9ε, Clase 2 ≤ 10ε, Clase 3 ≤ 14ε, Clase 4 > 14ε
        donde ε = √(235/fy)
        """
        epsilon = math.sqrt(235.0 / fy_mpa) if fy_mpa > 0 else 1.0
        b_t_ratio = b_free_mm / t_mm if t_mm > 0 else float("inf")

        if b_t_ratio <= 9.0 * epsilon:
            section_class = 1
            ok = True
        elif b_t_ratio <= 10.0 * epsilon:
            section_class = 2
            ok = True
        elif b_t_ratio <= 14.0 * epsilon:
            section_class = 3
            ok = True
        else:
            section_class = 4
            ok = False  # requiere sección efectiva o BLOQUEADO

        util = b_t_ratio / (14.0 * epsilon) if epsilon > 0 else float("inf")
        error_code = "LOC-CHK-002" if section_class == 4 else None

        return CheckResult(
            check_type="LIGAMENT_SLENDERNESS",
            status=DetailCheckStatus.PASS if ok else DetailCheckStatus.BLOCKED,
            demand=round(b_t_ratio, 4),
            resistance=round(14.0 * epsilon, 4),
            utilization=round(util, 4),
            unit="—",
            governing_rule="EC3 §5.5 — clasificación de sección, ligamento",
            error_code=error_code,
            intermediate_values={
                "b_t_ratio": round(b_t_ratio, 3),
                "epsilon": round(epsilon, 4),
                "section_class": section_class,
                "limit_class3": round(14.0 * epsilon, 3),
            },
        )

    @staticmethod
    def check_panel_buckling(
        a_mm: float,
        b_mm: float,
        t_mm: float,
        E_mpa: float = 210000.0,
        nu: float = 0.3,
        sigma_applied_mpa: float = 0.0,
        fy_mpa: float = 355.0,
    ) -> CheckResult:
        """
        Tensión crítica de pandeo de panel (Euler-placa).
        σ_cr = kσ × π² × E × t² / (12 × (1-ν²) × b²)
        kσ = 4.0 para compresión uniaxial con extremos apoyados
        """
        k_sigma = 4.0
        b_m = b_mm / 1000.0
        t_m = t_mm / 1000.0
        sigma_cr = k_sigma * math.pi**2 * E_mpa / (12.0 * (1.0 - nu**2)) * (t_m / b_m)**2
        # Reducción por plastificación (Karman)
        rho = min(1.0, sigma_cr / fy_mpa)

        util = abs(sigma_applied_mpa) / (rho * sigma_cr) if sigma_cr > 0 else float("inf")
        ok = util <= 1.0

        return CheckResult(
            check_type="PANEL_BUCKLING",
            status=DetailCheckStatus.PASS if ok else DetailCheckStatus.FAIL,
            demand=round(abs(sigma_applied_mpa), 4),
            resistance=round(rho * sigma_cr, 4),
            utilization=round(util, 4),
            unit="MPa",
            governing_rule="EC3 §4.4 — pandeo de panel plano",
            intermediate_values={
                "sigma_cr_mpa": round(sigma_cr, 4),
                "k_sigma": k_sigma,
                "rho": round(rho, 4),
                "b_t_ratio": round(b_mm / t_mm, 2),
            },
        )

    @staticmethod
    def check_combined_interaction(
        sigma_nom_mpa: float,
        tau_mpa: float,
        fy_mpa: float,
        gamma_M0: float = 1.0,
    ) -> CheckResult:
        """
        Interacción tensión normal + cortante (Von Mises).
        (σ/fy)² + 3(τ/fy)² ≤ 1 / γM0²
        """
        f_yd = fy_mpa / gamma_M0
        vm = math.sqrt((sigma_nom_mpa / f_yd)**2 + 3.0 * (tau_mpa / f_yd)**2)
        ok = vm <= 1.0
        return CheckResult(
            check_type="COMBINED_VM",
            status=DetailCheckStatus.PASS if ok else DetailCheckStatus.FAIL,
            demand=round(vm, 4),
            resistance=1.0,
            utilization=round(vm, 4),
            unit="—",
            governing_rule="EC3 §6.2.1 — Von Mises",
            intermediate_values={"sigma_nom": sigma_nom_mpa, "tau": tau_mpa},
        )

    @staticmethod
    def check_local_deformation(
        delta_local_mm: float,
        limit_mm: float,
    ) -> CheckResult:
        """Deformación local del borde de puerta ≤ límite."""
        util = delta_local_mm / limit_mm if limit_mm > 0 else float("inf")
        ok = util <= 1.0
        return CheckResult(
            check_type="LOCAL_DEFORMATION",
            status=DetailCheckStatus.PASS if ok else DetailCheckStatus.FAIL,
            demand=round(delta_local_mm, 4),
            resistance=round(limit_mm, 4),
            utilization=round(util, 4),
            unit="mm",
            governing_rule="EN 40-3-3 — deformación local de borde",
        )

    @staticmethod
    def check_fatigue_hotspot(
        sigma_hotspot_mpa: float,
        gamma_Ff: float = 1.0,
        delta_sigma_Rsk_mpa: float = 71.0,  # FAT71 — terminación de refuerzo típica
        gamma_Mf: float = 1.15,
    ) -> CheckResult:
        """
        Verificación de fatiga por hot-spot.
        Demanda = γ_Ff × Δσ_hotspot
        Capacidad = ΔσRsk / γ_Mf
        """
        demand = gamma_Ff * sigma_hotspot_mpa
        capacity = delta_sigma_Rsk_mpa / gamma_Mf
        util = demand / capacity if capacity > 0 else float("inf")
        ok = util <= 1.0
        return CheckResult(
            check_type="FATIGUE_HOTSPOT",
            status=DetailCheckStatus.PASS if ok else DetailCheckStatus.FAIL,
            demand=round(demand, 4),
            resistance=round(capacity, 4),
            utilization=round(util, 4),
            unit="MPa",
            governing_rule="EC3 §9 / EN 40-3-3 — fatiga hot-spot",
            intermediate_values={
                "fatigue_category": f"FAT{delta_sigma_Rsk_mpa:.0f}",
                "gamma_Ff": gamma_Ff,
                "gamma_Mf": gamma_Mf,
            },
        )


# ============================================================================
# WeldService
# ============================================================================

class WeldService:
    """Distribución elástica de fuerzas en grupos de soldadura."""

    @staticmethod
    def compute_weld_group(
        segments: List[dict],  # [{x1, y1, x2, y2, throat_mm}]
        fu_mpa: float,
        Fx_kn: float = 0.0,
        Fy_kn: float = 0.0,
        M_knm: float = 0.0,
        gamma_M2: float = 1.25,
        beta_w: float = 0.8,
        haz_factor: float = 1.0,   # < 1 para aluminio en HAZ
    ) -> WeldGroupCalc:
        """
        Distribución elástica de un grupo de soldaduras plano.
        Calcula CG, Ip, f_directa, f_torsional, resultante máxima.
        """
        # Propiedades del grupo
        segs = []
        total_L = 0.0
        for s in segments:
            dx = s["x2_mm"] - s["x1_mm"]
            dy = s["y2_mm"] - s["y1_mm"]
            L = math.sqrt(dx**2 + dy**2)
            xc = (s["x1_mm"] + s["x2_mm"]) / 2.0
            yc = (s["y1_mm"] + s["y2_mm"]) / 2.0
            segs.append({"L": L, "xc": xc, "yc": yc, "throat": s.get("throat_mm", 5.0)})
            total_L += L

        if total_L <= 0:
            raise ValueError("LOC-WLD-001: longitud total de soldadura debe ser > 0")

        # Centroide del grupo
        xG = sum(s["L"] * s["xc"] for s in segs) / total_L
        yG = sum(s["L"] * s["yc"] for s in segs) / total_L

        # Momento de inercia polar respecto al CG
        Ip = sum(s["L"] * ((s["xc"] - xG)**2 + (s["yc"] - yG)**2) for s in segs)

        # Fuerzas en N (convertir kN)
        Fx = Fx_kn * 1000.0
        Fy = Fy_kn * 1000.0
        Mt = M_knm * 1e6  # kNm → Nmm

        # Fuerza directa por unidad de longitud [N/mm]
        f_dir = math.sqrt(Fx**2 + Fy**2) / total_L if total_L > 0 else 0.0

        # Fuerza por momento torsor: f = Mt × r / Ip (máximo en fibra extrema)
        r_max = max(math.sqrt((s["xc"] - xG)**2 + (s["yc"] - yG)**2) for s in segs) if segs else 0.0
        f_torsion = abs(Mt) * r_max / Ip if Ip > 0 else 0.0

        # Resultante máxima conservadora (suma vectorial)
        f_res_max = f_dir + f_torsion  # extremo conservador

        # Capacidad de diseño por unidad de longitud [N/mm]
        # F_w,Rd = fu × a / (√3 × β_w × γM2)
        throat_avg = sum(s["L"] * s["throat"] for s in segs) / total_L if total_L > 0 else 5.0
        f_w_Rd = fu_mpa * throat_avg * haz_factor / (math.sqrt(3.0) * beta_w * gamma_M2)

        util = f_res_max / f_w_Rd if f_w_Rd > 0 else float("inf")
        ok = util <= 1.0

        return WeldGroupCalc(
            total_length_mm=round(total_L, 2),
            centroid_x_mm=round(xG, 4),
            centroid_y_mm=round(yG, 4),
            Ip_polar_mm4=round(Ip, 2),
            f_res_max_n_mm=round(f_res_max, 4),
            capacity_n_mm=round(f_w_Rd, 4),
            utilization=round(util, 4),
            status=DetailCheckStatus.PASS if ok else DetailCheckStatus.FAIL,
            governing_rule="EC3 §4.5.3 / EN 40-3-3 — distribución elástica de soldaduras",
            intermediate_values={
                "f_dir_N_mm": round(f_dir, 4),
                "f_torsion_N_mm": round(f_torsion, 4),
                "throat_avg_mm": round(throat_avg, 4),
                "r_max_mm": round(r_max, 4),
                "Ip_mm4": round(Ip, 2),
                "haz_factor": haz_factor,
            },
        )

    @staticmethod
    def check_haz_reduction(
        sigma_nom_mpa: float,
        f0_mpa: float,
        haz_factor: float,
        gamma_M1: float = 1.1,
    ) -> CheckResult:
        """Resistencia reducida en HAZ de aluminio."""
        f_HAZ = haz_factor * f0_mpa / gamma_M1
        util = abs(sigma_nom_mpa) / f_HAZ if f_HAZ > 0 else float("inf")
        ok = util <= 1.0
        return CheckResult(
            check_type="HAZ_ALUMINIUM",
            status=DetailCheckStatus.PASS if ok else DetailCheckStatus.FAIL,
            demand=round(abs(sigma_nom_mpa), 4),
            resistance=round(f_HAZ, 4),
            utilization=round(util, 4),
            unit="MPa",
            governing_rule="EN 1999-1-1 §6.2 — HAZ aluminio",
            intermediate_values={"haz_factor": haz_factor, "f0_mpa": f0_mpa},
        )

    @staticmethod
    def check_pullout(
        F_applied_kn: float,
        thread_diameter_mm: float,
        embedded_length_mm: float,
        fu_bolt_mpa: float,
        fu_plate_mpa: float,
        gamma_M2: float = 1.25,
    ) -> CheckResult:
        """Arrancamiento de inserto atornillado (modelo simplificado)."""
        # Resistencia a arranque ≈ fu_plate × A_bearing / γM2
        A_bearing_mm2 = math.pi * thread_diameter_mm * embedded_length_mm
        F_Rd_kn = fu_plate_mpa * A_bearing_mm2 / (gamma_M2 * 1000.0)
        util = F_applied_kn / F_Rd_kn if F_Rd_kn > 0 else float("inf")
        ok = util <= 1.0
        return CheckResult(
            check_type="INSERT_PULLOUT",
            status=DetailCheckStatus.PASS if ok else DetailCheckStatus.FAIL,
            demand=round(F_applied_kn, 4),
            resistance=round(F_Rd_kn, 4),
            utilization=round(util, 4),
            unit="kN",
            governing_rule="EC3 §3.6 — arrancamiento de unión roscada",
            intermediate_values={"A_bearing_mm2": round(A_bearing_mm2, 2)},
        )


# ============================================================================
# SupportConfigurator
# ============================================================================

class SupportConfigurator:
    """Configuración de soportes y equipos; verificación de accesibilidad."""

    @staticmethod
    def check_equipment_fits(
        opening_width_mm: float,
        opening_height_mm: float,
        equipment_list: List[dict],  # [{length_mm, width_mm, height_mm, mass_kg, reference}]
        D_int_mm: float,
    ) -> AccessibilityResult:
        """
        Verifica que todos los equipos caben por la abertura y dentro del fuste.
        Regla: min(w, h) del equipo < opening_width_mm (y h del equipo < opening_height_mm)
        """
        all_fit = True
        blocking = None
        sequence = []

        for eq in equipment_list:
            w_eq = eq.get("width_mm", 0)
            h_eq = eq.get("height_mm", 0)
            l_eq = eq.get("length_mm", 0)
            ref = eq.get("reference", "equipo")

            can_enter = (min(w_eq, h_eq) <= opening_width_mm) and (max(w_eq, h_eq) <= opening_height_mm)
            fits_inside = max(w_eq, h_eq, l_eq) <= D_int_mm

            if not can_enter or not fits_inside:
                all_fit = False
                if blocking is None:
                    blocking = ref
            else:
                sequence.append(f"Instalar {ref}")

        accessible = all_fit
        return AccessibilityResult(
            accessible=accessible,
            tool_clearance_ok=True,   # se comprueba por separado
            cable_radius_ok=True,
            all_equipment_fit=all_fit,
            extraction_sequence=sequence,
            blocking_equipment=blocking,
            error_code="LOC-ACC-001" if not accessible else None,
        )

    @staticmethod
    def check_tool_clearance(
        available_clearance_mm: float,
        required_clearance_mm: float = 50.0,
    ) -> CheckResult:
        """Espacio libre para herramienta."""
        util = required_clearance_mm / available_clearance_mm if available_clearance_mm > 0 else float("inf")
        ok = available_clearance_mm >= required_clearance_mm
        return CheckResult(
            check_type="TOOL_CLEARANCE",
            status=DetailCheckStatus.PASS if ok else DetailCheckStatus.BLOCKED,
            demand=required_clearance_mm,
            resistance=available_clearance_mm,
            utilization=round(util, 4),
            unit="mm",
            governing_rule="EN 40-2 — acceso de herramienta",
            error_code=None if ok else "LOC-ACC-002",
        )

    @staticmethod
    def check_cable_radius(
        available_radius_mm: float,
        required_min_radius_mm: float = 25.0,
    ) -> CheckResult:
        """Radio mínimo de curvatura de cables."""
        ok = available_radius_mm >= required_min_radius_mm
        util = required_min_radius_mm / available_radius_mm if available_radius_mm > 0 else float("inf")
        return CheckResult(
            check_type="CABLE_RADIUS",
            status=DetailCheckStatus.PASS if ok else DetailCheckStatus.FAIL,
            demand=required_min_radius_mm,
            resistance=available_radius_mm,
            utilization=round(util, 4),
            unit="mm",
            governing_rule="EN 40-2 — radio mínimo de curvatura de cables",
        )

    @staticmethod
    def check_support_overload(
        load_applied_kn: float,
        capacity_kn: float,
    ) -> CheckResult:
        """Soporte interior sobrecargado."""
        util = load_applied_kn / capacity_kn if capacity_kn > 0 else float("inf")
        ok = util <= 1.0
        return CheckResult(
            check_type="SUPPORT_LOAD",
            status=DetailCheckStatus.PASS if ok else DetailCheckStatus.FAIL,
            demand=round(load_applied_kn, 4),
            resistance=round(capacity_kn, 4),
            utilization=round(util, 4),
            unit="kN",
            governing_rule="EN 40-2 — soporte interior",
        )

    @staticmethod
    def check_drainage(has_drain_opening: bool, drainage_area_mm2: float = 0.0) -> CheckResult:
        """Verifica que existe drenaje y ventilación adecuados."""
        ok = has_drain_opening and drainage_area_mm2 > 0.0
        return CheckResult(
            check_type="DRAINAGE",
            status=DetailCheckStatus.PASS if ok else DetailCheckStatus.FAIL,
            demand=0.0 if has_drain_opening else 1.0,
            resistance=1.0 if has_drain_opening else 0.0,
            utilization=0.0 if ok else float("inf"),
            unit="—",
            governing_rule="EN 40-2 — drenaje y ventilación",
            error_code=None if ok else "LOC-FAB-001",
        )

    @staticmethod
    def check_closed_cavity(has_closed_cavity: bool, material: str = "STEEL") -> CheckResult:
        """Detecta cavidad cerrada incompatible con galvanizado."""
        error = has_closed_cavity and material.upper() in ("STEEL", "ACERO")
        return CheckResult(
            check_type="CLOSED_CAVITY",
            status=DetailCheckStatus.BLOCKED if error else DetailCheckStatus.PASS,
            demand=1.0 if has_closed_cavity else 0.0,
            resistance=0.0 if error else 1.0,
            utilization=float("inf") if error else 0.0,
            unit="—",
            governing_rule="ISO 14713 — galvanizado: cavidades cerradas prohibidas",
            error_code="LOC-FAB-002" if error else None,
        )


# ============================================================================
# LocalFEAService
# ============================================================================

class LocalFEAService:
    """Contrato y validación del submodelo FEM local."""

    FEA_ACTIVATION_THRESHOLD = 0.90

    @staticmethod
    def should_activate_fea(
        multiple_openings_close: bool = False,
        outside_formula_domain: bool = False,
        high_torsion: bool = False,
        complex_open_section: bool = False,
        discontinuous_reinforcement: bool = False,
        near_joint: bool = False,
        analytic_utilization: float = 0.0,
        new_detail_no_test: bool = False,
    ) -> FEAActivation:
        """Determina si el FEM local es obligatorio."""
        reasons = []
        if multiple_openings_close:
            reasons.append("Múltiples huecos próximos")
        if outside_formula_domain:
            reasons.append("Geometría fuera de dominio de fórmulas")
        if high_torsion:
            reasons.append("Torsión elevada — sección abierta")
        if complex_open_section:
            reasons.append("Sección abierta compleja")
        if discontinuous_reinforcement:
            reasons.append("Refuerzo discontinuo")
        if near_joint:
            reasons.append("Interacción con junta o brazo")
        if analytic_utilization > LocalFEAService.FEA_ACTIVATION_THRESHOLD:
            reasons.append(f"Utilización analítica {analytic_utilization:.2f} > {LocalFEAService.FEA_ACTIVATION_THRESHOLD}")
        if new_detail_no_test:
            reasons.append("Detalle nuevo sin evidencia de ensayo")

        required = len(reasons) > 0
        route = DetailRoute.R8_C if required else DetailRoute.R8_B
        return FEAActivation(fea_required=required, activation_reasons=reasons, route=route)

    @staticmethod
    def validate_fea_model(
        convergence_ratio: float,
        equilibrium_residual_pct: float,
        max_stress_mpa: float,
        buckling_factor: float,
        analytic_ref_stress_mpa: float,
    ) -> dict:
        """
        Valida los resultados del FEM contra los criterios del contrato.
        Convergencia ≤ 3%, equilibrio ≤ 0.1%.
        """
        errors = []
        conv_ok = convergence_ratio <= 3.0
        eq_ok = equilibrium_residual_pct <= 0.1
        comparison_delta = abs(max_stress_mpa - analytic_ref_stress_mpa) / analytic_ref_stress_mpa * 100.0 if analytic_ref_stress_mpa > 0 else 0.0

        if not conv_ok:
            errors.append(f"LOC-FEA-001: convergencia {convergence_ratio:.2f}% > 3% — malla insuficiente")
        if not eq_ok:
            errors.append(f"LOC-FEA-002: equilibrio {equilibrium_residual_pct:.3f}% > 0.1%")

        status = FEAStatus.CONVERGED if (conv_ok and eq_ok) else FEAStatus.FAILED
        return {
            "model_valid": conv_ok and eq_ok,
            "convergence_ratio": round(convergence_ratio, 3),
            "equilibrium_residual_pct": round(equilibrium_residual_pct, 4),
            "max_stress_mpa": round(max_stress_mpa, 4),
            "buckling_factor": round(buckling_factor, 4),
            "comparison_delta_pct": round(comparison_delta, 3),
            "status": status,
            "errors": errors,
            "governing_rule": "Contrato FEM local — convergencia ≤3%, equilibrio ≤0.1%",
        }


# ============================================================================
# ReinforcementOptimizer
# ============================================================================

class ReinforcementOptimizer:
    """Optimización Pareto de familias de refuerzo."""

    @staticmethod
    def is_dominated(a: ReinfCandidate, b: ReinfCandidate) -> bool:
        """b domina a si es mejor o igual en todo y estrictamente mejor en algo."""
        if not a.feasible:
            return True
        if not b.feasible:
            return False
        return (
            b.cost_eur <= a.cost_eur and
            b.mass_kg <= a.mass_kg and
            b.co2_kg <= a.co2_kg and
            (b.cost_eur < a.cost_eur or b.mass_kg < a.mass_kg or b.co2_kg < a.co2_kg)
        )

    @classmethod
    def build_pareto(cls, candidates: List[ReinfCandidate]) -> List[ReinfCandidate]:
        eligible = [c for c in candidates if c.feasible]
        pareto = []
        for c in eligible:
            if not any(cls.is_dominated(c, other) for other in eligible if other is not c):
                pareto.append(c)
        return pareto

    @classmethod
    def select_solutions(cls, pareto: List[ReinfCandidate]) -> dict:
        if not pareto:
            return {"min_cost": None, "min_weight": None, "min_co2": None, "balanced": None}
        min_cost = min(pareto, key=lambda c: c.cost_eur)
        min_weight = min(pareto, key=lambda c: c.mass_kg)
        min_co2 = min(pareto, key=lambda c: c.co2_kg)
        max_c = max(c.cost_eur for c in pareto) or 1.0
        max_w = max(c.mass_kg for c in pareto) or 1.0
        max_co2 = max(c.co2_kg for c in pareto) or 1.0
        min_c_v = min(c.cost_eur for c in pareto)
        min_w_v = min(c.mass_kg for c in pareto)
        min_co2_v = min(c.co2_kg for c in pareto)
        balanced = min(
            pareto,
            key=lambda c: (
                ((c.cost_eur - min_c_v) / (max_c - min_c_v + 1e-12))**2 +
                ((c.mass_kg - min_w_v) / (max_w - min_w_v + 1e-12))**2 +
                ((c.co2_kg - min_co2_v) / (max_co2 - min_co2_v + 1e-12))**2
            )
        )
        return {"min_cost": min_cost, "min_weight": min_weight,
                "min_co2": min_co2, "balanced": balanced}


# ============================================================================
# DetailNormativeClassifier
# ============================================================================

class DetailNormativeClassifier:
    """Clasificador de ruta normativa de 7 pasos (BLOCKING si falla alguno)."""

    VERSION = "1.0"

    @staticmethod
    def classify(
        entry_complete: bool,
        has_tested_family: bool,
        within_analytic_domain: bool,
        complex_geometry: bool,
        has_evidence: bool,
        new_detail: bool,
        high_torsion: bool,
    ) -> NormativeRouteResult:
        steps = []
        trace = []

        ok1 = entry_complete
        steps.append(ok1)
        trace.append(f"Paso 1: Entrada completa: {'OK' if ok1 else 'BLOQUEADO'}")

        ok2 = True  # normativa siempre aplicable si llegamos aquí
        steps.append(ok2)
        trace.append("Paso 2: Normativa EN40/EC aplicable: OK")

        ok3 = within_analytic_domain or has_tested_family
        steps.append(ok3)
        trace.append(f"Paso 3: Dentro de dominio o familia ensayada: {'OK' if ok3 else 'BLOQUEADO'}")

        ok4 = has_evidence or not new_detail
        steps.append(ok4)
        trace.append(f"Paso 4: Evidencia disponible: {'OK' if ok4 else 'REQUIERE FEM'}")

        ok5 = not complex_geometry or not high_torsion
        steps.append(ok5)
        trace.append(f"Paso 5: Geometría no compleja o torsión baja: {'OK' if ok5 else 'REQUIERE SUBMODELO'}")

        ok6 = True
        steps.append(ok6)
        trace.append("Paso 6: Rutas de verificación definidas: OK")

        ok7 = has_evidence or has_tested_family
        steps.append(ok7)
        trace.append(f"Paso 7: Evidencias suficientes: {'OK' if ok7 else 'BLOQUEADO'}")

        payload = {
            "entry": entry_complete, "family": has_tested_family,
            "domain": within_analytic_domain, "complex": complex_geometry,
            "evidence": has_evidence, "new": new_detail, "torsion": high_torsion,
            "v": DetailNormativeClassifier.VERSION,
        }
        input_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

        blocking_step = None
        for i, ok in enumerate(steps):
            if not ok:
                blocking_step = i + 1
                break

        if not ok1 or (not ok3 and not has_tested_family) or (not ok7 and new_detail):
            route = DetailRoute.R8_E  # BLOQUEADO
        elif has_tested_family:
            route = DetailRoute.R8_A
        elif complex_geometry or high_torsion:
            route = DetailRoute.R8_C
        elif new_detail and not has_evidence:
            route = DetailRoute.R8_D
        else:
            route = DetailRoute.R8_B

        return NormativeRouteResult(
            route=route,
            steps_passed=steps,
            blocking_step=blocking_step,
            decision_trace=trace,
            input_hash=input_hash,
        )
