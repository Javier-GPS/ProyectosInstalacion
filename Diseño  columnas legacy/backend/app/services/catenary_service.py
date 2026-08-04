"""
Salvi Studio · Columns — Fase 16: Servicio de Catenarias y Alumbrado Suspendido.

Implementación analítica pura (sin dependencias de red ni de base de datos).
Todos los tipos de retorno son dataclasses para evitar dependencia de Pydantic.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field as dc_field
from typing import Any, Dict, List, Optional, Tuple


# ══════════════════════════════════════════════════════════════════════════════
# Tipos de retorno (dataclasses, sin Pydantic)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class SpanResult:
    """Resultado de un tramo de cable bajo una hipótesis de carga."""
    span_id: str
    tension_h_kn: float
    tension_max_kn: float
    sag_m: float
    cable_length_m: float
    clearance_min_m: float
    utilization_strength: float
    utilization_clearance: float
    checks_passed: bool
    error_codes: List[str] = dc_field(default_factory=list)
    detail: Dict[str, Any] = dc_field(default_factory=dict)


@dataclass
class AnchorReaction:
    """Resultante vectorial sobre un anclaje (punto de apoyo de cable)."""
    anchor_id: str
    fx_kn: float
    fy_kn: float
    fz_kn: float
    mx_knm: float
    my_knm: float
    mz_knm: float
    cables_count: int
    error_codes: List[str] = dc_field(default_factory=list)


@dataclass
class ConvergenceInfo:
    """Informe de convergencia del solver Newton-Raphson."""
    converged: bool
    iterations: int
    residual_final: float
    displacement_final: float
    error_code: Optional[str] = None
    detail: str = ""
    h_converged: float = 0.0   # tensión horizontal al converger [kN]


@dataclass
class ValidationIssue:
    code: str
    severity: str      # BLOQUEANTE, GRAVE, ADVERTENCIA, INFO
    message: str
    entity: Optional[str] = None


@dataclass
class ValidationReport:
    issues: List[ValidationIssue] = dc_field(default_factory=list)
    passed: bool = False

    @property
    def blocking(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "BLOQUEANTE"]

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity in ("BLOQUEANTE", "GRAVE")]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "ADVERTENCIA"]


@dataclass
class TensioningPlanResult:
    """Plan de tensado calculado."""
    method: str
    target_value: float
    target_unit: str
    cut_length_m: Optional[float]
    tensor_stroke_mm: Optional[float]
    sequence: List[Dict[str, Any]]
    t_install_c: float
    accepted: bool
    warnings: List[str] = dc_field(default_factory=list)


@dataclass
class ParetoSolution:
    """Solución Pareto para optimización de sistema de cables."""
    solution_id: str
    label: str
    cost_eur: float
    mass_kg: float
    co2_kg: float
    robustness_score: float
    dominated: bool = False
    configuration: Dict[str, Any] = dc_field(default_factory=dict)


@dataclass
class OptimizationReport:
    alternatives: List[ParetoSolution] = dc_field(default_factory=list)
    recommended_id: Optional[str] = None

    @property
    def pareto_front(self) -> List[ParetoSolution]:
        return [s for s in self.alternatives if not s.dominated]


@dataclass
class AsBuiltCalibration:
    """Resultado de calibración as-built."""
    span_id: str
    sag_design_m: float
    sag_measured_m: Optional[float]
    tension_design_kn: float
    tension_measured_kn: Optional[float]
    deviation_pct: float
    accepted: bool
    t_reference_correction: float   # corrección térmica a T_ref
    uncertainty_m: float
    comments: str = ""


# ══════════════════════════════════════════════════════════════════════════════
# Constantes del dominio
# ══════════════════════════════════════════════════════════════════════════════

MAX_CABLES_PER_COLUMN = 6
MIN_SPAN_LENGTH_M = 0.5
MAX_SPAN_LENGTH_M = 200.0
MAX_SPANS_PER_CABLE = 20
MAX_POINT_LOADS_PER_SPAN = 100

# Criterios de convergencia
TOL_RESIDUAL = 1e-6
TOL_DISPLACEMENT = 1e-7
TOL_REACTION = 1e-5
MAX_ITER_DEFAULT = 200

# Tipologías de cable
VALID_TYPOLOGIES = {"C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"}

# Tipologías que admiten cable en flojo (flopping)
FLOPPY_CABLE_TYPOLOGIES = {"C8"}  # cable estabilizador puede ir a flojo

# Códigos de error
ERROR_CODES = {
    "CAB-GEO-001": ("BLOQUEANTE", "Topología inválida o apoyo coincidente"),
    "CAB-MAT-001": ("BLOQUEANTE", "Material o terminal sin propiedades homologadas"),
    "CAB-SOL-001": ("BLOQUEANTE", "No convergencia del solver Newton-Raphson"),
    "CAB-SOL-002": ("GRAVE",      "Cable flojo fuera del método validado"),
    "CAB-CPL-001": ("BLOQUEANTE", "No convergencia del acoplamiento cable-estructura"),
    "CAB-NOR-001": ("GRAVE",      "Caso fuera del dominio normativo"),
    "CAB-CLR-001": ("BLOQUEANTE", "Altura libre insuficiente"),
    "CAB-STR-001": ("BLOQUEANTE", "Capacidad de cable o terminal excedida"),
    "CAB-TEN-001": ("GRAVE",      "Carrera de tensor insuficiente"),
    "CAB-DYN-001": ("GRAVE",      "Riesgo dinámico: requiere análisis de especialista"),
}

# Gálibo mínimo por tipo de vía (EN 40 / normativa local)
MIN_CLEARANCE_M = {
    "PEDESTRIAN":   5.0,
    "ROAD":         5.5,
    "MOTORWAY":     6.0,
    "RAIL":         6.7,
    "DEFAULT":      5.5,
}

# Propiedades por defecto de materiales de cable comunes
CABLE_MATERIAL_DEFAULTS = {
    "GALVANIZED_STEEL": {
        "e_mpa": 170_000.0,
        "alpha_k": 11.5e-6,
        "density_kg_m3": 7850.0,
    },
    "STAINLESS_STEEL": {
        "e_mpa": 190_000.0,
        "alpha_k": 16.0e-6,
        "density_kg_m3": 7900.0,
    },
    "HDPE_SHEATHED": {
        "e_mpa": 165_000.0,
        "alpha_k": 12.0e-6,
        "density_kg_m3": 7900.0,
    },
    "ALUMINUM_ALLOY": {
        "e_mpa": 69_000.0,
        "alpha_k": 23.0e-6,
        "density_kg_m3": 2700.0,
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# CatenaryPhysics — ecuaciones físicas puras
# ══════════════════════════════════════════════════════════════════════════════

class CatenaryPhysics:
    """
    Ecuaciones físicas de la catenaria (aproximación parabólica y correcciones).

    La aproximación parabólica es válida cuando f/L < 0.1 (cables de alumbrado
    público típicos). Para f/L ≥ 0.1 se aplica la solución catenaria exacta.
    """

    # ── Aproximación parabólica ───────────────────────────────────────────

    @staticmethod
    def horizontal_tension(w: float, L: float, f: float) -> float:
        """
        H ≈ w·L² / (8·f)
        Tensión horizontal [kN] desde carga repartida w [N/m], vano L [m], flecha f [m].
        """
        if f <= 0:
            raise ValueError("La flecha debe ser positiva.")
        return w * L ** 2 / (8.0 * f) / 1000.0  # N → kN

    @staticmethod
    def sag_from_tension(w: float, L: float, H_kn: float) -> float:
        """
        f = w·L² / (8·H)
        Flecha [m] desde carga repartida w [N/m], vano L [m], tensión horizontal H [kN].
        """
        H = H_kn * 1000.0
        if H <= 0:
            raise ValueError("La tensión horizontal debe ser positiva.")
        return w * L ** 2 / (8.0 * H)

    @staticmethod
    def support_tension(H_kn: float, w: float, L: float) -> float:
        """
        T_sup ≈ √(H² + (w·L/2)²)
        Tensión máxima en el apoyo [kN].
        """
        H = H_kn * 1000.0
        V = w * L / 2.0
        return math.sqrt(H ** 2 + V ** 2) / 1000.0

    @staticmethod
    def cable_length_parabolic(L: float, f: float) -> float:
        """
        S ≈ L · [1 + 8f²/(3L²)]
        Longitud de cable [m] por la aproximación parabólica.
        """
        return L * (1.0 + 8.0 * f ** 2 / (3.0 * L ** 2))

    @staticmethod
    def cable_length_catenary(H_kn: float, w: float, L: float) -> float:
        """
        Longitud exacta de la catenaria: S = (H/w) · [sinh(w·L/(2H))·2]
        """
        H = H_kn * 1000.0
        a = H / w  # parámetro de la catenaria [m]
        return 2.0 * a * math.sinh(L / (2.0 * a))

    @staticmethod
    def sag_catenary_exact(H_kn: float, w: float, L: float) -> float:
        """
        Flecha exacta de la catenaria: f = (H/w)·[cosh(wL/(2H)) - 1]
        """
        H = H_kn * 1000.0
        a = H / w
        return a * (math.cosh(L / (2.0 * a)) - 1.0)

    @staticmethod
    def thermal_length(L_ref: float, alpha: float, T: float, T_ref: float) -> float:
        """
        L_free(T) = L_ref · [1 + α·(T − T_ref)]
        Longitud libre del cable a temperatura T [m].
        """
        return L_ref * (1.0 + alpha * (T - T_ref))

    @staticmethod
    def thermal_tension_correction(
        H_kn: float,
        EA: float,
        L_ref: float,
        alpha: float,
        delta_T: float,
        L_span: float,
    ) -> float:
        """
        Corrección de tensión horizontal por cambio térmico ΔT [K].
        Basado en ecuación de compatibilidad: ε_mec + ε_ter = 0 para longitud fija.
        ΔH ≈ −EA·α·ΔT  (válido para Δf/f pequeño)
        """
        delta_H = -EA * alpha * delta_T / 1000.0  # N → kN
        return max(0.0, H_kn + delta_H)

    @staticmethod
    def clearance_at_midspan(z_a: float, z_b: float, f: float) -> float:
        """
        Cota mínima del cable = [(z_a + z_b)/2 - f] para vano nivelado.
        Para apoyos a diferente cota la flecha mínima está desplazada.
        """
        z_avg = (z_a + z_b) / 2.0
        return z_avg - f

    @staticmethod
    def is_parabolic_valid(f: float, L: float) -> bool:
        """La aproximación parabólica es válida cuando f/L < 0.1."""
        return (f / L) < 0.1

    @staticmethod
    def sag_slope_factor(L: float, f: float) -> float:
        """
        Factor de corrección de flecha por pendiente: aplica al vano inclinado.
        Para sección horizontal equivalente: L_eq = L / cos(θ).
        """
        return 1.0  # placeholder; se calcula iterativamente con height_diff

    @staticmethod
    def point_load_sag(F_n: float, a: float, b: float, H_kn: float) -> float:
        """
        Flecha adicional bajo una carga puntual F [N] a distancia a [m] del apoyo A,
        siendo b = L - a la distancia al apoyo B.
        δ_F = F·a·b / (H·L)   [m]
        """
        L = a + b
        H = H_kn * 1000.0
        if H <= 0 or L <= 0:
            return 0.0
        return F_n * a * b / (H * L)


# ══════════════════════════════════════════════════════════════════════════════
# TopologyValidator — validación geométrica y topológica
# ══════════════════════════════════════════════════════════════════════════════

class TopologyValidator:
    """
    Verifica la coherencia geométrica y topológica del sistema de cables.
    Principio P-03 (fallo seguro): cualquier error bloqueante impide el análisis.
    """

    # Umbral de apoyos coincidentes [m]
    COINCIDENT_THRESHOLD_M = 0.05

    def validate_system(
        self,
        typology: str,
        anchors: List[Dict[str, Any]],
        spans: List[Dict[str, Any]],
        cables_per_column: Dict[str, int],
    ) -> ValidationReport:
        report = ValidationReport()
        issues = report.issues

        # Verificar tipología
        if typology not in VALID_TYPOLOGIES:
            issues.append(ValidationIssue(
                code="CAB-NOR-001",
                severity="GRAVE",
                message=f"Tipología '{typology}' no reconocida. Valores válidos: {sorted(VALID_TYPOLOGIES)}",
            ))

        # Verificar apoyos coincidentes
        for i, a in enumerate(anchors):
            for j, b in enumerate(anchors):
                if j <= i:
                    continue
                dist = math.sqrt(
                    (a["x_m"] - b["x_m"]) ** 2
                    + (a["y_m"] - b["y_m"]) ** 2
                    + (a["z_m"] - b["z_m"]) ** 2
                )
                if dist < self.COINCIDENT_THRESHOLD_M:
                    issues.append(ValidationIssue(
                        code="CAB-GEO-001",
                        severity="BLOQUEANTE",
                        message=f"Apoyos {a.get('id', i)} y {b.get('id', j)} coincidentes "
                                f"(d={dist:.4f} m < {self.COINCIDENT_THRESHOLD_M} m).",
                        entity=str(a.get("id", i)),
                    ))

        # Verificar longitudes de vano
        for span in spans:
            L = span.get("length_m", 0)
            if L < MIN_SPAN_LENGTH_M or L > MAX_SPAN_LENGTH_M:
                issues.append(ValidationIssue(
                    code="CAB-GEO-001",
                    severity="BLOQUEANTE",
                    message=f"Longitud de vano {L:.2f} m fuera del dominio "
                            f"[{MIN_SPAN_LENGTH_M}, {MAX_SPAN_LENGTH_M}] m.",
                    entity=str(span.get("id", "")),
                ))

        # Verificar cables por columna
        for col_id, n_cables in cables_per_column.items():
            if n_cables > MAX_CABLES_PER_COLUMN:
                issues.append(ValidationIssue(
                    code="CAB-GEO-001",
                    severity="BLOQUEANTE",
                    message=f"Columna {col_id} tiene {n_cables} cables; el máximo es {MAX_CABLES_PER_COLUMN}.",
                    entity=col_id,
                ))

        # Verificar cargas puntuales por vano
        for span in spans:
            n_pl = len(span.get("point_loads", []))
            if n_pl > MAX_POINT_LOADS_PER_SPAN:
                issues.append(ValidationIssue(
                    code="CAB-NOR-001",
                    severity="ADVERTENCIA",
                    message=f"Vano {span.get('id', '')} tiene {n_pl} cargas puntuales "
                            f"(máx. recomendado: {MAX_POINT_LOADS_PER_SPAN}).",
                ))

        report.passed = len(report.blocking) == 0
        return report

    def validate_anchor_positions(
        self,
        anchors: List[Dict[str, Any]],
        min_height_m: float = 3.0,
    ) -> List[ValidationIssue]:
        """Verifica que los anclajes estén a altura útil."""
        issues: List[ValidationIssue] = []
        for a in anchors:
            if a.get("z_m", 0) < min_height_m:
                issues.append(ValidationIssue(
                    code="CAB-CLR-001",
                    severity="ADVERTENCIA",
                    message=f"Anclaje {a.get('id', '')} a cota {a.get('z_m', 0):.2f} m, "
                            f"inferior a {min_height_m:.1f} m.",
                    entity=str(a.get("id", "")),
                ))
        return issues

    def detect_orphan_anchors(
        self,
        anchor_ids: List[str],
        span_anchor_ids: List[str],
    ) -> List[str]:
        """Devuelve lista de anclajes sin ningún vano conectado."""
        used = set(span_anchor_ids)
        return [aid for aid in anchor_ids if aid not in used]

    def validate_span_continuity(
        self,
        spans: List[Dict[str, Any]],
    ) -> List[ValidationIssue]:
        """Verifica que los vanos de cada cable sean continuos (endpoint chain)."""
        issues: List[ValidationIssue] = []
        # Agrupa por line_id
        from collections import defaultdict
        by_line: Dict[str, List[Dict]] = defaultdict(list)
        for s in spans:
            by_line[s.get("line_id", "?")].append(s)

        for line_id, line_spans in by_line.items():
            sorted_spans = sorted(line_spans, key=lambda s: s.get("span_index", 0))
            for i in range(len(sorted_spans) - 1):
                curr = sorted_spans[i]
                nxt = sorted_spans[i + 1]
                if curr.get("anchor_b_id") != nxt.get("anchor_a_id"):
                    issues.append(ValidationIssue(
                        code="CAB-GEO-001",
                        severity="BLOQUEANTE",
                        message=f"Cable {line_id}: discontinuidad entre vano {i} y {i+1}. "
                                f"Anchor B del vano {i} ≠ Anchor A del vano {i+1}.",
                        entity=line_id,
                    ))
        return issues


# ══════════════════════════════════════════════════════════════════════════════
# CableVectorAggregator — suma vectorial de cables en columna
# ══════════════════════════════════════════════════════════════════════════════

class CableVectorAggregator:
    """
    Suma vectorial de hasta MAX_CABLES_PER_COLUMN cables incidentes sobre un anclaje.
    La resultante se añade a la columna en el punto de fijación.
    M = Σ(r_i × F_i) donde r_i es el vector de brazo al centro de sección.
    """

    def aggregate(
        self,
        anchor_x: float,
        anchor_y: float,
        anchor_z: float,
        cable_forces: List[Dict[str, Any]],  # [{fx, fy, fz, attach_x, attach_y, attach_z}]
    ) -> AnchorReaction:
        """
        cable_forces: lista de dicts con las componentes de la reacción de cada cable [kN]
        y el punto de aplicación {attach_x, attach_y, attach_z} [m].
        Devuelve la resultante vectorial y el momento respecto al anclaje.
        """
        if len(cable_forces) > MAX_CABLES_PER_COLUMN:
            raise ValueError(
                f"Se superó el límite de {MAX_CABLES_PER_COLUMN} cables por columna."
            )

        fx_tot = fy_tot = fz_tot = 0.0
        mx_tot = my_tot = mz_tot = 0.0

        for cf in cable_forces:
            fx = cf.get("fx_kn", 0.0)
            fy = cf.get("fy_kn", 0.0)
            fz = cf.get("fz_kn", 0.0)
            ax = cf.get("attach_x", anchor_x)
            ay = cf.get("attach_y", anchor_y)
            az = cf.get("attach_z", anchor_z)

            # Vector de brazo
            rx = ax - anchor_x
            ry = ay - anchor_y
            rz = az - anchor_z

            fx_tot += fx
            fy_tot += fy
            fz_tot += fz

            # Momento = r × F
            mx_tot += ry * fz - rz * fy
            my_tot += rz * fx - rx * fz
            mz_tot += rx * fy - ry * fx

        return AnchorReaction(
            anchor_id="",  # caller asigna
            fx_kn=fx_tot,
            fy_kn=fy_tot,
            fz_kn=fz_tot,
            mx_knm=mx_tot,
            my_knm=my_tot,
            mz_knm=mz_tot,
            cables_count=len(cable_forces),
        )

    def reaction_resultant(self, reaction: AnchorReaction) -> float:
        """Módulo de la fuerza resultante [kN]."""
        return math.sqrt(
            reaction.fx_kn ** 2 + reaction.fy_kn ** 2 + reaction.fz_kn ** 2
        )

    def moment_resultant(self, reaction: AnchorReaction) -> float:
        """Módulo del momento resultante [kN·m]."""
        return math.sqrt(
            reaction.mx_knm ** 2 + reaction.my_knm ** 2 + reaction.mz_knm ** 2
        )

    def check_cables_limit(self, cables_count: int) -> Optional[ValidationIssue]:
        """Devuelve issue BLOQUEANTE si se supera el límite de cables por columna."""
        if cables_count > MAX_CABLES_PER_COLUMN:
            return ValidationIssue(
                code="CAB-GEO-001",
                severity="BLOQUEANTE",
                message=f"Número de cables por columna ({cables_count}) supera el límite ({MAX_CABLES_PER_COLUMN}).",
            )
        return None


# ══════════════════════════════════════════════════════════════════════════════
# ThermalCalculator — estados térmicos y correcciones
# ══════════════════════════════════════════════════════════════════════════════

class ThermalCalculator:
    """Cálculo de estados térmicos y correcciones de longitud/tensión."""

    def __init__(self, t_ref: float = 15.0):
        self.t_ref = t_ref

    def free_length(self, L_ref: float, alpha: float, T: float) -> float:
        """Longitud libre del cable a temperatura T [°C]."""
        return CatenaryPhysics.thermal_length(L_ref, alpha, T, self.t_ref)

    def tension_at_temperature(
        self,
        H_install_kn: float,
        EA: float,       # [kN]
        L_span: float,
        alpha: float,
        T: float,
    ) -> float:
        """
        Tensión horizontal estimada a temperatura T, partiendo de H instalada.
        Linealización válida para |ΔT| < 40 K.
        """
        delta_T = T - self.t_ref
        return CatenaryPhysics.thermal_tension_correction(
            H_install_kn, EA * 1000.0, L_span, alpha, delta_T, L_span
        )

    def governing_temperature(
        self,
        t_min: float,
        t_max: float,
        t_install: float,
    ) -> Dict[str, float]:
        """
        Devuelve las temperaturas de cálculo relevantes:
        - max_sag: T_max (mayor flecha)
        - min_clearance: T_max (mayor flecha → menor gálibo)
        - max_tension: T_min (menor flecha → mayor tensión)
        - install: T_install (estado referencia)
        """
        return {
            "max_sag":       t_max,
            "min_clearance": t_max,
            "max_tension":   t_min,
            "install":       t_install,
        }

    def delta_length_thermal(
        self, L_ref: float, alpha: float, T_from: float, T_to: float
    ) -> float:
        """Variación de longitud térmica entre dos temperaturas [m]."""
        return L_ref * alpha * (T_to - T_from)


# ══════════════════════════════════════════════════════════════════════════════
# ConvergenceChecker — control de residuos Newton-Raphson
# ══════════════════════════════════════════════════════════════════════════════

class ConvergenceChecker:
    """Evaluación de criterios de convergencia del solver iterativo."""

    def __init__(
        self,
        tol_residual: float = TOL_RESIDUAL,
        tol_displacement: float = TOL_DISPLACEMENT,
        tol_reaction: float = TOL_REACTION,
    ):
        self.tol_residual = tol_residual
        self.tol_displacement = tol_displacement
        self.tol_reaction = tol_reaction

    def check(
        self,
        residual: float,
        displacement: float,
        reaction_imbalance: float,
    ) -> Tuple[bool, str]:
        """
        Verifica los tres criterios de convergencia.
        Devuelve (converged, reason).
        """
        if residual > self.tol_residual:
            return False, f"Residuo {residual:.2e} > {self.tol_residual:.2e}"
        if displacement > self.tol_displacement:
            return False, f"Incremento despl. {displacement:.2e} > {self.tol_displacement:.2e}"
        if reaction_imbalance > self.tol_reaction:
            return False, f"Desequilibrio reacciones {reaction_imbalance:.2e} > {self.tol_reaction:.2e}"
        return True, "OK"

    def residual_normalized(self, r_abs: float, f_ref: float) -> float:
        """Residuo normalizado respecto a la fuerza de referencia."""
        if f_ref == 0:
            return float("inf")
        return abs(r_abs) / f_ref

    def displacement_normalized(self, u_abs: float, L_char: float) -> float:
        """Incremento de desplazamiento normalizado respecto a longitud característica."""
        if L_char == 0:
            return float("inf")
        return abs(u_abs) / L_char

    def simulate_newton_raphson(
        self,
        w: float,       # carga repartida [N/m]
        L: float,       # vano [m]
        EA: float,      # rigidez axial [kN]
        L0: float,      # longitud sin carga [m]
        H0_kn: float,   # estimación inicial [kN]
        max_iter: int = MAX_ITER_DEFAULT,
    ) -> ConvergenceInfo:
        """
        Solver Newton-Raphson simplificado para el equilibrio cable parabólico.
        Ecuación: f_int(H) - f_ext(H) = 0
        donde f_int = elongación mecánica = (S - L0) / L0 · EA
              f_ext = S(H) de la geometría catenaria.

        Este método implementa la lógica de convergencia que los ACs verifican.
        """
        H = max(H0_kn, 0.01)
        physics = CatenaryPhysics()

        f_ref = w * L / 2.0 / 1000.0  # fuerza de referencia [kN]
        if f_ref == 0:
            f_ref = 1.0

        prev_H = H
        for it in range(1, max_iter + 1):
            # Flecha y longitud de cable para H actual
            f_sag = physics.sag_from_tension(w, L, H)
            S = physics.cable_length_parabolic(L, f_sag)

            # Residuo: equilibrio entre elongación mecánica y geométrica
            r = (S - L0) / L0 * EA - (H - H0_kn)
            r_norm = abs(r) / f_ref

            # Jacobiano numérico (diferencia finita)
            dH = H * 1e-6 + 1e-9
            f_sag2 = physics.sag_from_tension(w, L, H + dH)
            S2 = physics.cable_length_parabolic(L, f_sag2)
            r2 = (S2 - L0) / L0 * EA - (H + dH - H0_kn)
            dR_dH = (r2 - r) / dH if dH != 0 else 1.0

            # Actualización Newton
            if abs(dR_dH) < 1e-12:
                break
            delta_H = -r / dR_dH
            H = max(H + delta_H, 1e-3)

            u_norm = abs(H - prev_H) / L
            reaction_imb = abs(r) / (w * L / 2.0 / 1000.0 + 1e-9)

            if r_norm <= self.tol_residual and u_norm <= self.tol_displacement:
                return ConvergenceInfo(
                    converged=True,
                    iterations=it,
                    residual_final=r_norm,
                    displacement_final=u_norm,
                    h_converged=H,
                )
            prev_H = H

        # No convergió
        return ConvergenceInfo(
            converged=False,
            iterations=max_iter,
            residual_final=abs(r) / f_ref if f_ref > 0 else float("inf"),
            displacement_final=abs(H - prev_H) / L if L > 0 else float("inf"),
            error_code="CAB-SOL-001",
            detail=f"No convergió en {max_iter} iteraciones.",
            h_converged=H,
        )


# ══════════════════════════════════════════════════════════════════════════════
# SpanSolver — cálculo de un tramo individual
# ══════════════════════════════════════════════════════════════════════════════

class SpanSolver:
    """Calcula tensión, flecha, longitud y verificaciones para un tramo."""

    def __init__(self):
        self.physics = CatenaryPhysics()
        self.checker = ConvergenceChecker()

    def solve(
        self,
        span_id: str,
        length_m: float,
        height_diff_m: float,
        w_n_m: float,          # carga repartida total [N/m]
        point_loads: List[Dict[str, Any]],
        EA_kn: float,          # rigidez axial del cable [kN]
        L0_m: float,           # longitud libre sin carga [m]
        z_a: float,            # cota anclaje A [m]
        z_b: float,            # cota anclaje B [m]
        mbl_kn: float,         # carga de rotura mínima [kN]
        clearance_req_m: float = MIN_CLEARANCE_M["DEFAULT"],
        typology: str = "C1",
        tol_residual: float = TOL_RESIDUAL,
        max_iter: int = MAX_ITER_DEFAULT,
    ) -> SpanResult:
        """
        Resuelve el tramo mediante aproximación parabólica + Newton-Raphson.
        """
        L = length_m
        error_codes: List[str] = []

        # Estimación inicial de flecha (5% del vano)
        f_init = 0.05 * L
        H0 = self.physics.horizontal_tension(w_n_m, L, f_init)

        # Iteración Newton-Raphson
        conv = self.checker.simulate_newton_raphson(
            w=w_n_m, L=L, EA=EA_kn, L0=L0_m, H0_kn=H0, max_iter=max_iter
        )
        if not conv.converged:
            error_codes.append("CAB-SOL-001")

        # Usar H del solver NR (converged o no); cota mínima 1 N/m para evitar división por cero
        H_kn = max(conv.h_converged if conv.h_converged > 0 else H0, 0.001)

        f_sag = self.physics.sag_from_tension(w_n_m, L, H_kn)
        T_kn = self.physics.support_tension(H_kn, w_n_m, L)
        S_m = self.physics.cable_length_parabolic(L, f_sag)

        # Gálibo mínimo
        z_avg = (z_a + z_b) / 2.0
        clearance_min = z_avg - f_sag

        # Suma de flechas adicionales por cargas puntuales
        extra_sag = 0.0
        for pl in point_loads:
            pos = pl.get("pos_m", L / 2)
            F = pl.get("force_n", 0.0)
            a = min(pos, L)
            b = L - a
            extra_sag += self.physics.point_load_sag(F, a, b, H_kn)

        f_total = f_sag + extra_sag
        clearance_min -= extra_sag

        # Verificación de gálibo
        if clearance_min < clearance_req_m:
            error_codes.append("CAB-CLR-001")

        # Verificación de resistencia (factor de seguridad ≥ 2.5 sobre MBL)
        fs_design = mbl_kn / 2.5  # MBL_design = MBL / γ_MBL
        util_strength = T_kn / fs_design if fs_design > 0 else float("inf")
        if util_strength > 1.0:
            error_codes.append("CAB-STR-001")

        # Cable flojo
        if H_kn < 0.01:
            if typology not in FLOPPY_CABLE_TYPOLOGIES:
                error_codes.append("CAB-SOL-002")

        util_clearance = (
            (clearance_req_m - clearance_min) / clearance_req_m
            if clearance_req_m > 0 else 0.0
        )

        return SpanResult(
            span_id=span_id,
            tension_h_kn=H_kn,
            tension_max_kn=T_kn,
            sag_m=f_total,
            cable_length_m=S_m,
            clearance_min_m=clearance_min,
            utilization_strength=util_strength,
            utilization_clearance=util_clearance,
            checks_passed=len(error_codes) == 0,
            error_codes=error_codes,
            detail={
                "conv_iterations": conv.iterations,
                "conv_residual": conv.residual_final,
                "conv_converged": conv.converged,
                "f_parabolic_m": f_sag,
                "f_point_loads_m": extra_sag,
            },
        )


# ══════════════════════════════════════════════════════════════════════════════
# CouplingIterator — acoplamiento iterativo cable-columna
# ══════════════════════════════════════════════════════════════════════════════

class CouplingIterator:
    """
    Acoplamiento iterativo entre el modelo de catenaria y el modelo de columna.
    Estrategia PARTITIONED: intercambio de reacciones/desplazamientos entre submodelos.
    """

    def __init__(self, tol_coupling: float = 1e-5, max_iter: int = 50):
        self.tol_coupling = tol_coupling
        self.max_iter = max_iter

    def iterate(
        self,
        initial_displacements: Dict[str, float],  # {anchor_id: delta_z [m]}
        cable_stiffnesses: Dict[str, float],       # {anchor_id: K_cable [kN/m]}
        column_stiffnesses: Dict[str, float],      # {anchor_id: K_column [kN/m]}
    ) -> Tuple[Dict[str, float], ConvergenceInfo]:
        """
        Itera hasta que los desplazamientos de los anclajes converjan.
        Modelo simplificado: Κ_cable · δ = F_external para cada anclaje.
        """
        disp = dict(initial_displacements)
        max_delta = float("inf")

        for it in range(1, self.max_iter + 1):
            disp_old = dict(disp)   # valores al inicio de esta iteración
            max_delta = 0.0
            for aid in disp:
                K_c = cable_stiffnesses.get(aid, 1.0)
                K_col = column_stiffnesses.get(aid, 1.0)
                K_total = K_c + K_col
                # Corrección de compatibilidad: δ_new = K_cable / K_total · δ_old
                disp[aid] = K_c / K_total * disp_old[aid]
                max_delta = max(max_delta, abs(disp[aid] - disp_old[aid]))

            if max_delta <= self.tol_coupling:
                return disp, ConvergenceInfo(
                    converged=True,
                    iterations=it,
                    residual_final=max_delta,
                    displacement_final=max_delta,
                )

        return disp, ConvergenceInfo(
            converged=False,
            iterations=self.max_iter,
            residual_final=max_delta,
            displacement_final=max_delta,
            error_code="CAB-CPL-001",
            detail=f"No convergió en {self.max_iter} iteraciones de acoplamiento.",
        )


# ══════════════════════════════════════════════════════════════════════════════
# TensioningPlanService — cálculo del plan de tensado
# ══════════════════════════════════════════════════════════════════════════════

class TensioningPlanService:
    """Genera y verifica el plan de tensado según el método seleccionado."""

    def __init__(self):
        self.physics = CatenaryPhysics()

    def compute_cut_length(
        self,
        span_length_m: float,
        target_h_kn: float,
        w_n_m: float,
        EA_kn: float,
        t_install_c: float,
        alpha: float,
        t_ref: float = 15.0,
    ) -> float:
        """
        Calcula la longitud de corte del cable para conseguir la tensión objetivo.
        L_cut = S_target · [1 - ΔT_thermal_correction]
        """
        f_target = self.physics.sag_from_tension(w_n_m, span_length_m, target_h_kn)
        S_target = self.physics.cable_length_parabolic(span_length_m, f_target)
        # Corrección térmica
        delta_L_thermal = S_target * alpha * (t_install_c - t_ref)
        L_cut = S_target - delta_L_thermal
        return L_cut

    def check_tensor_stroke(
        self,
        L_cut_m: float,
        S_required_m: float,
        tensor_stroke_mm: float,
    ) -> Tuple[bool, float]:
        """
        Verifica que la carrera del tensor sea suficiente.
        ΔL = S_required - L_cut  debe ser ≤ tensor_stroke.
        """
        delta_L_mm = (S_required_m - L_cut_m) * 1000.0
        ok = delta_L_mm <= tensor_stroke_mm
        return ok, delta_L_mm

    def plan(
        self,
        method: str,
        target_value: float,
        target_unit: str,
        span_length_m: float,
        w_n_m: float,
        EA_kn: float,
        mbl_kn: float,
        t_install_c: float,
        alpha: float,
        tensor_stroke_mm: Optional[float],
        t_ref: float = 15.0,
        tolerance_pct: float = 2.0,
    ) -> TensioningPlanResult:
        warnings: List[str] = []
        cut_length_m = None
        stroke_ok = True

        if method == "FORCE":
            H_kn = target_value  # fuerza objetivo [kN]
            cut_length_m = self.compute_cut_length(
                span_length_m, H_kn, w_n_m, EA_kn, t_install_c, alpha, t_ref
            )
        elif method == "SAG":
            f_target = target_value  # flecha objetivo [m]
            H_kn = self.physics.horizontal_tension(w_n_m, span_length_m, f_target)
            cut_length_m = self.compute_cut_length(
                span_length_m, H_kn, w_n_m, EA_kn, t_install_c, alpha, t_ref
            )
        elif method == "CUT_LENGTH":
            cut_length_m = target_value  # longitud de corte [m]
            H_kn = None
        else:
            H_kn = None

        # Verificar carrera de tensor
        if tensor_stroke_mm and cut_length_m:
            f_sag = self.physics.sag_from_tension(w_n_m, span_length_m, H_kn or 1.0)
            S_req = self.physics.cable_length_parabolic(span_length_m, f_sag)
            stroke_ok, delta_mm = self.check_tensor_stroke(cut_length_m, S_req, tensor_stroke_mm)
            if not stroke_ok:
                warnings.append(
                    f"CAB-TEN-001: Carrera tensor insuficiente ({delta_mm:.1f} mm > {tensor_stroke_mm:.1f} mm)."
                )

        # Verificar utilización respecto a MBL
        if H_kn and mbl_kn > 0:
            T_max = self.physics.support_tension(H_kn, w_n_m, span_length_m)
            util = T_max / (mbl_kn / 2.5)
            if util > 0.9:
                warnings.append(f"Utilización de resistencia del cable alta ({util:.1%}).")

        sequence = [
            {"step": 1, "action": "Montar cable y fijar extremo A"},
            {"step": 2, "action": f"Cortar a {cut_length_m:.3f} m" if cut_length_m else "Preparar tensor"},
            {"step": 3, "action": f"Tensar con método {method} hasta {target_value:.2f} {target_unit}"},
            {"step": 4, "action": f"Verificar flecha/tensión con tolerancia ±{tolerance_pct:.1f}%"},
            {"step": 5, "action": "Fijar extremo B y registrar as-built"},
        ]

        return TensioningPlanResult(
            method=method,
            target_value=target_value,
            target_unit=target_unit,
            cut_length_m=cut_length_m,
            tensor_stroke_mm=tensor_stroke_mm,
            sequence=sequence,
            t_install_c=t_install_c,
            accepted=len(warnings) == 0,
            warnings=warnings,
        )


# ══════════════════════════════════════════════════════════════════════════════
# OptimizationEngine — Pareto multiobjetivo para el sistema de cables
# ══════════════════════════════════════════════════════════════════════════════

class OptimizationEngine:
    """
    Genera alternativas Pareto-óptimas para el sistema de cables.
    Objetivos: coste/peso/CO2/robustez.
    """

    def dominates(self, a: ParetoSolution, b: ParetoSolution) -> bool:
        """a domina b si es mejor o igual en todos los objetivos y estrictamente mejor en alguno."""
        a_vals = [a.cost_eur, a.mass_kg, a.co2_kg, -a.robustness_score]
        b_vals = [b.cost_eur, b.mass_kg, b.co2_kg, -b.robustness_score]
        at_least_one_better = False
        for av, bv in zip(a_vals, b_vals):
            if av > bv:
                return False
            if av < bv:
                at_least_one_better = True
        return at_least_one_better

    def compute_pareto(self, solutions: List[ParetoSolution]) -> List[ParetoSolution]:
        """Marca las soluciones dominadas y devuelve la lista actualizada."""
        for i, s in enumerate(solutions):
            for j, t in enumerate(solutions):
                if i == j:
                    continue
                if self.dominates(t, s):
                    s.dominated = True
                    break
        return solutions

    def generate_alternatives(
        self,
        base_h_kn: float,
        base_cost: float,
        n: int = 5,
    ) -> OptimizationReport:
        """
        Genera n alternativas variando la tensión de instalación.
        Caso simplificado para demostración; en producción llama al SpanSolver.
        """
        solutions: List[ParetoSolution] = []
        for i in range(n):
            factor = 0.7 + 0.15 * i  # 0.70, 0.85, 1.00, 1.15, 1.30
            H = base_h_kn * factor
            sol = ParetoSolution(
                solution_id=f"ALT-{i+1:02d}",
                label=f"H={H:.1f} kN",
                cost_eur=base_cost * (0.95 + 0.05 * i),
                mass_kg=50.0 * factor,
                co2_kg=30.0 * factor,
                robustness_score=1.0 / factor,
                configuration={"H_kn": H, "factor": factor},
            )
            solutions.append(sol)

        solutions = self.compute_pareto(solutions)
        pareto = [s for s in solutions if not s.dominated]
        recommended = pareto[0].solution_id if pareto else None

        return OptimizationReport(alternatives=solutions, recommended_id=recommended)


# ══════════════════════════════════════════════════════════════════════════════
# AsBuiltCalibrationService — calibración as-built
# ══════════════════════════════════════════════════════════════════════════════

class AsBuiltCalibrationService:
    """Compara las mediciones reales con los valores de diseño y calibra el modelo."""

    def __init__(self, acceptance_threshold_pct: float = 5.0):
        self.threshold = acceptance_threshold_pct
        self.physics = CatenaryPhysics()

    def calibrate(
        self,
        span_id: str,
        sag_design_m: float,
        tension_design_kn: float,
        sag_measured_m: Optional[float],
        tension_measured_kn: Optional[float],
        t_measure_c: float,
        t_ref_c: float,
        alpha: float,
        L_span: float,
        w_n_m: float,
        uncertainty_m: float = 0.02,
    ) -> AsBuiltCalibration:
        """
        Corrige la medición de flecha a temperatura de referencia y calcula desviación.
        """
        # Corrección térmica: ajustar sag medido a T_ref
        if sag_measured_m is not None:
            H_meas = self.physics.horizontal_tension(w_n_m, L_span, sag_measured_m)
            H_corr = self.physics.thermal_tension_correction(
                H_meas,
                EA=1000.0,  # placeholder; en prod se usa EA real
                L_ref=L_span,
                alpha=alpha,
                delta_T=t_ref_c - t_measure_c,
                L_span=L_span,
            )
            sag_corrected = self.physics.sag_from_tension(w_n_m, L_span, H_corr)
            t_ref_correction = sag_corrected - sag_measured_m
            deviation_pct = abs(sag_corrected - sag_design_m) / sag_design_m * 100.0
        else:
            sag_corrected = sag_design_m
            t_ref_correction = 0.0
            deviation_pct = 0.0

        accepted = deviation_pct <= self.threshold

        return AsBuiltCalibration(
            span_id=span_id,
            sag_design_m=sag_design_m,
            sag_measured_m=sag_measured_m,
            tension_design_kn=tension_design_kn,
            tension_measured_kn=tension_measured_kn,
            deviation_pct=deviation_pct,
            accepted=accepted,
            t_reference_correction=t_ref_correction,
            uncertainty_m=uncertainty_m,
            comments="" if accepted else f"Desviación {deviation_pct:.2f}% supera el {self.threshold:.1f}%.",
        )


# ══════════════════════════════════════════════════════════════════════════════
# LuminaireAssigner — asignación de luminarias a vanos
# ══════════════════════════════════════════════════════════════════════════════

class LuminaireAssigner:
    """
    Asigna luminarias a vanos según reglas de prioridad:
    1. Posición real (as-built / DXF importado)
    2. Regla geométrica (a/3 o L/2 según tipología)
    3. Estimación de diseño
    """

    def assign_midspan(self, length_m: float) -> float:
        """Asigna la luminaria al centro del vano."""
        return length_m / 2.0

    def assign_third_point(self, length_m: float) -> float:
        """Asigna la luminaria al tercio del vano (suspensión asimétrica)."""
        return length_m / 3.0

    def assign_from_dxf(
        self,
        dxf_position_m: float,
        span_length_m: float,
    ) -> Tuple[float, str]:
        """
        Valida la posición de DXF y la asigna si está dentro del vano.
        Devuelve (posición, data_quality).
        """
        if 0.0 <= dxf_position_m <= span_length_m:
            return dxf_position_m, "IMPORTED"
        else:
            # Fuerza al centro si está fuera del vano
            return span_length_m / 2.0, "ESTIMATED"

    def effective_distributed_load(
        self,
        w_cable_n_m: float,
        suspended_items: List[Dict[str, Any]],
        span_length_m: float,
    ) -> float:
        """
        Carga distribuida efectiva incluyendo las cargas puntuales de luminarias
        como carga uniforme equivalente para el cálculo parabólico.
        """
        total_point = sum(item.get("mass_kg", 0.0) * 9.81 for item in suspended_items)
        equivalent_w = total_point / span_length_m if span_length_m > 0 else 0.0
        return w_cable_n_m + equivalent_w


# ══════════════════════════════════════════════════════════════════════════════
# InputHasher — hash de entradas para trazabilidad
# ══════════════════════════════════════════════════════════════════════════════

class InputHasher:
    """Genera hashes SHA-256 de las entradas del sistema para trazabilidad."""

    @staticmethod
    def hash_system(system_data: Dict[str, Any]) -> str:
        payload = json.dumps(system_data, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def hash_span(
        length_m: float,
        height_diff_m: float,
        w_n_m: float,
        point_loads: List[Dict],
        EA_kn: float,
        L0_m: float,
    ) -> str:
        payload = json.dumps({
            "L": length_m, "dz": height_diff_m,
            "w": w_n_m, "pl": point_loads,
            "EA": EA_kn, "L0": L0_m,
        }, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


# ══════════════════════════════════════════════════════════════════════════════
# CableMaterialLibrary — propiedades por defecto de materiales
# ══════════════════════════════════════════════════════════════════════════════

class CableMaterialLibrary:
    """Biblioteca de propiedades de materiales de cable."""

    _MATERIALS = CABLE_MATERIAL_DEFAULTS

    def get_defaults(self, material_type: str) -> Optional[Dict[str, Any]]:
        return self._MATERIALS.get(material_type.upper())

    def list_materials(self) -> List[str]:
        return list(self._MATERIALS.keys())

    def ea_from_diameter(self, material_type: str, diameter_mm: float) -> float:
        """
        Rigidez axial EA [kN] estimada desde diámetro.
        A = π/4 · d²; EA = E · A.
        """
        mat = self.get_defaults(material_type)
        if not mat:
            return 0.0
        e_mpa = mat["e_mpa"]
        area_mm2 = math.pi / 4.0 * diameter_mm ** 2
        return e_mpa * area_mm2 / 1000.0  # N → kN

    def mass_from_diameter(self, material_type: str, diameter_mm: float) -> float:
        """Masa lineal estimada [kg/m] desde diámetro y densidad."""
        mat = self.get_defaults(material_type)
        if not mat:
            return 0.0
        area_m2 = math.pi / 4.0 * (diameter_mm / 1000.0) ** 2
        return mat["density_kg_m3"] * area_m2


# ══════════════════════════════════════════════════════════════════════════════
# CatenaryOrchestrator — coordinador del flujo completo de análisis
# ══════════════════════════════════════════════════════════════════════════════

class CatenaryOrchestrator:
    """
    Coordinador de análisis: valida, resuelve cada vano en cada estado de carga,
    agrega reacciones vectoriales y verifica convergencia de acoplamiento.
    """

    def __init__(self):
        self.validator = TopologyValidator()
        self.solver = SpanSolver()
        self.aggregator = CableVectorAggregator()
        self.coupling = CouplingIterator()
        self.physics = CatenaryPhysics()

    def analyze_span(
        self,
        span: Dict[str, Any],
        state: Dict[str, Any],
        cable_props: Dict[str, Any],
        z_a: float,
        z_b: float,
        typology: str = "C1",
    ) -> SpanResult:
        """Analiza un vano bajo un estado de carga."""
        # Carga total = cable + luminarias + viento + hielo
        g_cable = cable_props.get("mass_kg_m", 0.0) * 9.81  # peso propio cable [N/m]
        g_items = sum(
            it.get("mass_kg", 0.0) * 9.81 / span.get("length_m", 1.0)
            for it in span.get("point_loads", [])
        )
        # Carga de viento sobre el cable: q_w = 0.5·ρ·V²·d·Cd (simplificado)
        V = state.get("wind_speed_ms", 0.0)
        d = cable_props.get("diameter_mm", 10.0) / 1000.0
        Cd = 1.2
        rho = 1.25
        q_wind = 0.5 * rho * V ** 2 * d * Cd
        w_ice = state.get("ice_load_n_m", 0.0)

        w_total = g_cable + g_items + w_ice
        # Peso total (vertical) + viento (horizontal) → módulo
        w_eff = math.sqrt(w_total ** 2 + q_wind ** 2) if q_wind > 0 else w_total

        EA_kn = cable_props.get("e_mpa", 170_000.0) * (
            cable_props.get("area_mm2", math.pi / 4.0 * cable_props.get("diameter_mm", 10.0) ** 2)
        ) / 1000.0

        L0 = span.get("length_m", 1.0) * 0.99  # longitud libre de referencia

        return self.solver.solve(
            span_id=str(span.get("id", "")),
            length_m=span.get("length_m", 1.0),
            height_diff_m=span.get("height_diff_m", 0.0),
            w_n_m=max(w_eff, 0.1),
            point_loads=span.get("point_loads", []),
            EA_kn=EA_kn,
            L0_m=L0,
            z_a=z_a,
            z_b=z_b,
            mbl_kn=cable_props.get("mbl_kn", 100.0),
            clearance_req_m=MIN_CLEARANCE_M["DEFAULT"],
            typology=typology,
        )

    def aggregate_anchor(
        self,
        anchor: Dict[str, Any],
        cable_results: List[Dict[str, Any]],
    ) -> AnchorReaction:
        """Suma vectorial de reacciones de cables en un anclaje."""
        forces = [
            {
                "fx_kn": r.get("rx_kn", 0.0),
                "fy_kn": r.get("ry_kn", 0.0),
                "fz_kn": r.get("rz_kn", 0.0),
                "attach_x": anchor.get("x_m", 0.0),
                "attach_y": anchor.get("y_m", 0.0),
                "attach_z": anchor.get("z_m", 0.0),
            }
            for r in cable_results
        ]
        reaction = self.aggregator.aggregate(
            anchor_x=anchor.get("x_m", 0.0),
            anchor_y=anchor.get("y_m", 0.0),
            anchor_z=anchor.get("z_m", 0.0),
            cable_forces=forces,
        )
        reaction.anchor_id = str(anchor.get("id", ""))
        return reaction
