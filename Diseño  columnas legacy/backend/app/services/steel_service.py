"""
Services · Fase 5 — Acero: Diseño, Verificación y Fabricación
Salvi Studio · Columns

Principio de seguridad: ninguna fórmula, coeficiente o curva normativa generada
libremente por IA. Toda regla procede de fuente identificada o aproximación
conservadora aprobada por Oficina Técnica.
"""
import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ===========================================================================
# NormativeClassifier — árbol de decisión de 7 pasos bloqueantes
# ===========================================================================

class RouteDecision(str, Enum):
    EN40 = "EN40"
    EN40_EXTENDED = "EN40_EXTENDED"
    SPECIAL = "SPECIAL"


@dataclass
class StepResult:
    step: int
    condition: str
    status: str          # PASS / BLOCKED / WARNING
    detail: Optional[str] = None


@dataclass
class NormativeClassificationResult:
    route: RouteDecision
    route_version: str
    steps: list[StepResult]
    active_rules: list[str]
    discarded_rules: list[str]
    exclusions: list[str]
    warnings: list[str]
    max_declaration_allowed: Optional[str]
    input_hash: str
    all_steps_pass: bool


class NormativeClassifier:
    """
    Clasificador normativo determinista de 7 pasos.

    Paso 1: Material = acero y producto dentro de EN 40-5
    Paso 2: Altura nominal ≤ 20 m
    Paso 3: Sin cables de catenaria ni acciones excluidas
    Paso 4: Sección y detalle dentro del dominio de EN 40-3-3
    Paso 5: Puerta y refuerzo dentro de método aprobado
    Paso 6: Combinaciones y anexos nacionales disponibles
    Paso 7: Todas las reglas tienen edición y tests vigentes
    """

    ROUTE_VERSION = "1.0"

    @staticmethod
    def classify(
        height_nominal_m: float,
        has_catenary_cables: bool,
        has_excluded_actions: bool,
        section_in_en40_domain: bool,
        door_in_approved_method: bool,
        combinations_available: bool,
        all_rules_have_editions: bool,
    ) -> NormativeClassificationResult:
        steps: list[StepResult] = []
        active_rules: list[str] = []
        discarded_rules: list[str] = []
        exclusions: list[str] = []
        warnings: list[str] = []

        # Paso 1: siempre PASS en este módulo (ya se validó que es acero)
        steps.append(StepResult(
            step=1,
            condition="Material = acero y producto dentro de EN 40-5",
            status="PASS",
            detail="Módulo de acero activo",
        ))
        active_rules.append("EN 40-5: requisitos de producto de acero")

        # Paso 2: altura ≤ 20 m
        if height_nominal_m <= 20.0:
            steps.append(StepResult(
                step=2,
                condition=f"Altura nominal {height_nominal_m} m ≤ 20 m",
                status="PASS",
                detail="Candidato a ruta EN 40",
            ))
        else:
            steps.append(StepResult(
                step=2,
                condition=f"Altura nominal {height_nominal_m} m > 20 m",
                status="WARNING",
                detail="Activar ruta ampliada EN 40 + Eurocódigos",
            ))
            warnings.append(f"Altura {height_nominal_m} m > 20 m: ruta ampliada requerida")

        # Paso 3: sin cables ni acciones excluidas
        if not has_catenary_cables and not has_excluded_actions:
            steps.append(StepResult(
                step=3,
                condition="Sin cables de catenaria ni acciones excluidas",
                status="PASS",
                detail="Mantener candidato EN 40",
            ))
        else:
            reasons = []
            if has_catenary_cables:
                reasons.append("cables de catenaria")
                exclusions.append("cables de catenaria → estructura especial")
            if has_excluded_actions:
                reasons.append("acciones excluidas")
                exclusions.append("acciones excluidas del ámbito EN 40")
            steps.append(StepResult(
                step=3,
                condition="Cables de catenaria u otras acciones excluidas presentes",
                status="WARNING",
                detail=f"Estructura especial: {', '.join(reasons)}",
            ))

        # Paso 4: sección y detalle dentro de EN 40-3-3
        if section_in_en40_domain:
            steps.append(StepResult(
                step=4,
                condition="Sección y detalle dentro del dominio de EN 40-3-3",
                status="PASS",
                detail="Usar método EN 40-3-3",
            ))
            active_rules.append("EN 40-3-3: verificación de secciones")
        else:
            steps.append(StepResult(
                step=4,
                condition="Sección o detalle fuera del dominio de EN 40-3-3",
                status="WARNING",
                detail="Usar EN 1993 o método validado específico",
            ))
            discarded_rules.append("EN 40-3-3: fuera de dominio para este detalle")
            active_rules.append("EN 1993: ruta de diseño ampliada")

        # Paso 5: puerta y refuerzo dentro de método aprobado
        if door_in_approved_method:
            steps.append(StepResult(
                step=5,
                condition="Puerta y refuerzo dentro de método aprobado",
                status="PASS",
                detail="Aplicar método aprobado",
            ))
        else:
            steps.append(StepResult(
                step=5,
                condition="Puerta o refuerzo fuera del dominio de método aprobado",
                status="BLOCKED",
                detail="STEEL-DOOR-001: exigir submodelo FEM o ensayo",
            ))
            exclusions.append("STEEL-DOOR-001: puerta fuera de método aprobado")

        # Paso 6: combinaciones y anexos nacionales disponibles
        if combinations_available:
            steps.append(StepResult(
                step=6,
                condition="Combinaciones y anexos nacionales disponibles",
                status="PASS",
                detail="Ejecutar verificaciones",
            ))
        else:
            steps.append(StepResult(
                step=6,
                condition="Combinaciones o anexos nacionales no disponibles",
                status="BLOCKED",
                detail="Bloquear cálculo final hasta completar datos",
            ))

        # Paso 7: todas las reglas tienen edición y tests vigentes
        if all_rules_have_editions:
            steps.append(StepResult(
                step=7,
                condition="Todas las reglas tienen edición y tests vigentes",
                status="PASS",
                detail="Permitir informe",
            ))
        else:
            steps.append(StepResult(
                step=7,
                condition="Alguna regla sin edición o tests vigentes",
                status="BLOCKED",
                detail="Resultado no liberable hasta resolver",
            ))

        # Determinar ruta final
        blocked = any(s.status == "BLOCKED" for s in steps)
        has_extended = (
            height_nominal_m > 20.0
            or has_catenary_cables
            or has_excluded_actions
            or not section_in_en40_domain
        )

        if blocked:
            route = RouteDecision.SPECIAL
            max_declaration = None
        elif has_extended:
            route = RouteDecision.EN40_EXTENDED
            max_declaration = "Diseño ampliado EN 40 + EN 1993; no declarar EN 40 como única base"
        else:
            route = RouteDecision.EN40
            max_declaration = "Verificación EN 40 por cálculo"

        all_pass = not blocked

        # Hash determinista de los inputs
        input_data = {
            "height_nominal_m": height_nominal_m,
            "has_catenary_cables": has_catenary_cables,
            "has_excluded_actions": has_excluded_actions,
            "section_in_en40_domain": section_in_en40_domain,
            "door_in_approved_method": door_in_approved_method,
            "combinations_available": combinations_available,
            "all_rules_have_editions": all_rules_have_editions,
            "route_version": NormativeClassifier.ROUTE_VERSION,
        }
        input_hash = hashlib.sha256(
            json.dumps(input_data, sort_keys=True).encode()
        ).hexdigest()

        return NormativeClassificationResult(
            route=route,
            route_version=NormativeClassifier.ROUTE_VERSION,
            steps=steps,
            active_rules=active_rules,
            discarded_rules=discarded_rules,
            exclusions=exclusions,
            warnings=warnings,
            max_declaration_allowed=max_declaration,
            input_hash=input_hash,
            all_steps_pass=all_pass,
        )


# ===========================================================================
# SteelMaterialService — política de espesores y selección de propiedades
# ===========================================================================

@dataclass
class ThicknessPolicy:
    t_nom_mm: float
    delta_t_tol_mm: float
    delta_t_corr_mm: float
    t_min_mm: float        # t_nom - delta_t_tol
    t_eff_mm: float        # t_min - delta_t_corr (aprobado)
    t_mass_mm: float       # t_nom o valor contractual
    double_deduction_check: bool  # False = ERROR


class SteelMaterialService:
    """Selección de propiedades de acero y política de espesores."""

    @staticmethod
    def compute_thickness_policy(
        t_nom_mm: float,
        delta_t_tol_mm: float,
        delta_t_corr_mm: float = 0.0,
        corrosion_already_applied: bool = False,
    ) -> ThicknessPolicy:
        """
        Calcula la política de espesores mostrando simultáneamente
        t_nom, t_min, t_eff y t_mass.

        Regla: nunca aplicar la misma reducción dos veces.
        """
        if t_nom_mm <= 0:
            raise ValueError("t_nom_mm debe ser positivo")
        if delta_t_tol_mm < 0:
            raise ValueError("delta_t_tol_mm debe ser >= 0")
        if delta_t_corr_mm < 0:
            raise ValueError("delta_t_corr_mm debe ser >= 0")

        t_min = t_nom_mm - delta_t_tol_mm
        if t_min <= 0:
            raise ValueError("t_min (t_nom - delta_t_tol) no puede ser <= 0")

        # Doble deducción: corrosión ya fue descontada previamente
        double_deduction = corrosion_already_applied and delta_t_corr_mm > 0
        t_eff = t_min - delta_t_corr_mm if not double_deduction else t_min

        return ThicknessPolicy(
            t_nom_mm=t_nom_mm,
            delta_t_tol_mm=delta_t_tol_mm,
            delta_t_corr_mm=delta_t_corr_mm,
            t_min_mm=round(t_min, 4),
            t_eff_mm=round(t_eff, 4),
            t_mass_mm=t_nom_mm,
            double_deduction_check=not double_deduction,
        )

    @staticmethod
    def select_fy_by_thickness(
        thickness_mm: float,
        property_records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Selecciona fy y fu del registro que cubre el espesor dado.
        Registra la transición si el espesor cruza un intervalo normativo.
        Raises ValueError si no hay registro aplicable.
        """
        applicable = [
            r for r in property_records
            if r["thickness_min_mm"] < thickness_mm <= r["thickness_max_mm"]
        ]
        if not applicable:
            raise ValueError(
                f"STEEL-MAT-001: no hay propiedades de acero para t={thickness_mm} mm. "
                "Revisar biblioteca de materiales."
            )
        # Si hay varios (distintas normas), el llamador debe filtrar previamente
        return applicable[0]

    @staticmethod
    def canonical_key(
        norm: str,
        grade: str,
        subgrade: str,
        product_form: str,
        condition: str,
        t_min_mm: float,
        t_max_mm: float,
        temp_c: Optional[float],
    ) -> str:
        """Clave canónica determinista para un material de acero."""
        parts = [norm, grade, subgrade, product_form, condition,
                 f"{t_min_mm:.2f}", f"{t_max_mm:.2f}",
                 f"{temp_c:.1f}" if temp_c is not None else "NA"]
        return "|".join(parts)


# ===========================================================================
# SteelSectionEngine — flujo canónico de 10 pasos
# ===========================================================================

@dataclass
class SectionForces:
    """Esfuerzos concurrentes en una estación y combinación."""
    N_kn: float = 0.0     # axil (+ tensión)
    Vy_kn: float = 0.0
    Vz_kn: float = 0.0
    T_knm: float = 0.0
    My_knm: float = 0.0
    Mz_knm: float = 0.0


@dataclass
class CircularHollowProperties:
    """Propiedades de sección hueca circular."""
    D_ext_mm: float
    t_mm: float
    A_m2: float
    Iy_m4: float          # = Iz para circulares
    J_m4: float           # = 2 * Iy para sección circular cerrada
    Ay_m2: float          # área eficaz a cortante
    Az_m2: float
    Wel_y_m3: float       # módulo resistente elástico
    mass_per_m_kg: float  # masa lineal


@dataclass
class PolygonalHollowProperties:
    """Propiedades de sección hueca poligonal regular."""
    n_faces: int
    inscribed_d_mm: float
    t_mm: float
    A_m2: float
    Iy_m4: float
    Iz_m4: float
    J_m4: float
    Ay_m2: float
    Az_m2: float
    Wel_y_m3: float
    mass_per_m_kg: float


@dataclass
class CheckResult:
    check_type: str
    status: str           # PASS / FAIL / BLOCKED / WARNING
    utilization: float
    margin: float
    resistance: float     # Rd en la unidad del esfuerzo dominante
    solicitation: float   # Ed
    norm: str
    norm_clause: Optional[str]
    intermediate_values: dict[str, Any]
    domain_ok: bool = True
    domain_notes: Optional[str] = None
    error_code: Optional[str] = None


class SteelSectionEngine:
    """
    Motor determinista de verificación de secciones de acero.
    Implementa el flujo canónico de 10 pasos.

    Las resistencias de diseño utilizan coeficientes parciales de la norma;
    aquí se usan γM0=1.00, γM1=1.00 (EN 40-3-3 §6) como valores de referencia.
    El llamador debe pasar los coeficientes parciales correctos según la ruta.
    """

    @staticmethod
    def circular_hollow_properties(
        D_ext_mm: float,
        t_mm: float,
        rho_kg_m3: float = 7850.0,
    ) -> CircularHollowProperties:
        """
        Propiedades geométricas de una sección hueca circular.
        D_ext: diámetro exterior en mm; t: espesor de pared en mm.
        """
        if t_mm <= 0 or D_ext_mm <= 0:
            raise ValueError("D_ext_mm y t_mm deben ser positivos")
        if 2 * t_mm >= D_ext_mm:
            raise ValueError("El espesor (2t) debe ser menor que el diámetro exterior")

        D = D_ext_mm / 1000      # m
        d = (D_ext_mm - 2 * t_mm) / 1000  # diámetro interior, m
        t = t_mm / 1000

        A = math.pi / 4 * (D**2 - d**2)
        I = math.pi / 64 * (D**4 - d**4)
        J = 2 * I                 # sección circular cerrada: J = 2·I
        # Área eficaz a cortante para tubo circular: A_v = 2·A/π (Timoshenko)
        Av = 2 * A / math.pi
        Wel = I / (D / 2)
        mass = rho_kg_m3 * A

        return CircularHollowProperties(
            D_ext_mm=D_ext_mm,
            t_mm=t_mm,
            A_m2=A,
            Iy_m4=I,
            J_m4=J,
            Ay_m2=Av,
            Az_m2=Av,
            Wel_y_m3=Wel,
            mass_per_m_kg=mass,
        )

    @staticmethod
    def regular_polygon_hollow_properties(
        n_faces: int,
        inscribed_d_mm: float,
        t_mm: float,
        rho_kg_m3: float = 7850.0,
    ) -> PolygonalHollowProperties:
        """
        Propiedades geométricas de una sección hueca poligonal regular.
        n_faces: número de caras; inscribed_d_mm: diámetro inscrito exterior (mm);
        t_mm: espesor de pared (mm).
        """
        if n_faces < 3:
            raise ValueError("n_faces debe ser >= 3")
        if t_mm <= 0 or inscribed_d_mm <= 0:
            raise ValueError("inscribed_d_mm y t_mm deben ser positivos")

        # Apotema exterior e interior
        a_ext = inscribed_d_mm / 2 / 1000           # m
        a_int = (inscribed_d_mm / 2 - t_mm) / 1000  # m (aprox para secciones delgadas)

        # Longitud de cara
        s_ext = 2 * a_ext * math.tan(math.pi / n_faces)
        s_int = 2 * a_int * math.tan(math.pi / n_faces)

        # Área (fórmula polígono regular)
        A_ext = n_faces * a_ext * s_ext / 2
        A_int = n_faces * a_int * s_int / 2
        A = A_ext - A_int

        # Inercia respecto al centroide (fórmula polígono regular)
        # I = (n·s³·a) / 24 para polígono sólido (simplificación de referencia)
        Iy_ext = n_faces * s_ext * a_ext * (a_ext**2 + s_ext**2 / 12) / 6
        Iy_int = n_faces * s_int * a_int * (a_int**2 + s_int**2 / 12) / 6
        Iy = Iy_ext - Iy_int
        Iz = Iy  # sección regular: Iy = Iz

        # Constante torsional (aproximación de Saint-Venant para sección delgada cerrada)
        # J = 4·Ao²·t / L_perimeter (fórmula de Bredt)
        L_ext = n_faces * s_ext
        Ao = A_ext                # área encerrada por la línea media (aprox)
        t_m = t_mm / 1000
        J = 4 * Ao**2 * t_m / L_ext if L_ext > 0 else 0.0

        # Área eficaz a cortante (aproximación: A / 2 para polígono)
        Av = A / 2

        Wel_y = Iy / a_ext if a_ext > 0 else 0.0
        mass = rho_kg_m3 * A

        return PolygonalHollowProperties(
            n_faces=n_faces,
            inscribed_d_mm=inscribed_d_mm,
            t_mm=t_mm,
            A_m2=A,
            Iy_m4=Iy,
            Iz_m4=Iz,
            J_m4=J,
            Ay_m2=Av,
            Az_m2=Av,
            Wel_y_m3=Wel_y,
            mass_per_m_kg=mass,
        )

    @staticmethod
    def check_axial(
        N_kn: float,
        A_m2: float,
        fy_mpa: float,
        gamma_M0: float = 1.0,
        norm: str = "EN40-3-3",
        norm_clause: str = "§6.2.2",
    ) -> CheckResult:
        """
        Comprobación de axil (tracción o compresión).
        N_Rd = A · fy / γM0
        """
        N_rd_kn = A_m2 * fy_mpa * 1000 / gamma_M0 / 1000  # kN
        utilization = abs(N_kn) / N_rd_kn if N_rd_kn > 0 else float("inf")
        margin = 1.0 - utilization
        status = "PASS" if utilization <= 1.0 else "FAIL"

        return CheckResult(
            check_type="TENSION" if N_kn >= 0 else "COMPRESSION",
            status=status,
            utilization=round(utilization, 6),
            margin=round(margin, 6),
            resistance=round(N_rd_kn, 4),
            solicitation=round(abs(N_kn), 4),
            norm=norm,
            norm_clause=norm_clause,
            intermediate_values={
                "A_m2": A_m2,
                "fy_mpa": fy_mpa,
                "gamma_M0": gamma_M0,
                "N_kn": N_kn,
                "N_rd_kn": N_rd_kn,
            },
        )

    @staticmethod
    def check_bending_uniaxial(
        M_knm: float,
        Wel_m3: float,
        fy_mpa: float,
        gamma_M0: float = 1.0,
        norm: str = "EN40-3-3",
        norm_clause: str = "§6.2.4",
    ) -> CheckResult:
        """
        Comprobación de flexión uniaxial.
        Mc,Rd = Wel · fy / γM0  (sección clase 3; usar Wpl para clase 1/2)
        """
        M_rd_knm = Wel_m3 * fy_mpa * 1e6 / gamma_M0 / 1e3  # kNm
        utilization = abs(M_knm) / M_rd_knm if M_rd_knm > 0 else float("inf")
        margin = 1.0 - utilization
        status = "PASS" if utilization <= 1.0 else "FAIL"

        return CheckResult(
            check_type="BENDING",
            status=status,
            utilization=round(utilization, 6),
            margin=round(margin, 6),
            resistance=round(M_rd_knm, 6),
            solicitation=round(abs(M_knm), 6),
            norm=norm,
            norm_clause=norm_clause,
            intermediate_values={
                "Wel_m3": Wel_m3,
                "fy_mpa": fy_mpa,
                "gamma_M0": gamma_M0,
                "M_knm": M_knm,
                "M_rd_knm": M_rd_knm,
            },
        )

    @staticmethod
    def check_biaxial_bending_interaction(
        My_knm: float,
        Mz_knm: float,
        My_rd_knm: float,
        Mz_rd_knm: float,
        alpha: float = 2.0,
        beta: float = 2.0,
        norm: str = "EN40-3-3",
        norm_clause: str = "§6.2.9",
    ) -> CheckResult:
        """
        Interacción de flexión biaxial: (My/My,Rd)^α + (Mz/Mz,Rd)^β ≤ 1.
        Para secciones circulares α = β = 2.
        """
        ratio = (abs(My_knm) / My_rd_knm) ** alpha + (abs(Mz_knm) / Mz_rd_knm) ** beta
        utilization = ratio
        margin = 1.0 - utilization
        status = "PASS" if utilization <= 1.0 else "FAIL"

        return CheckResult(
            check_type="INTERACTION",
            status=status,
            utilization=round(utilization, 6),
            margin=round(margin, 6),
            resistance=1.0,
            solicitation=round(ratio, 6),
            norm=norm,
            norm_clause=norm_clause,
            intermediate_values={
                "My_knm": My_knm,
                "Mz_knm": Mz_knm,
                "My_rd_knm": My_rd_knm,
                "Mz_rd_knm": Mz_rd_knm,
                "alpha": alpha,
                "beta": beta,
                "interaction_ratio": round(ratio, 6),
            },
        )

    @staticmethod
    def check_shear(
        V_kn: float,
        Av_m2: float,
        fy_mpa: float,
        gamma_M0: float = 1.0,
        norm: str = "EN40-3-3",
        norm_clause: str = "§6.2.5",
    ) -> CheckResult:
        """
        Comprobación de cortante.
        Vpl,Rd = Av · fy / (√3 · γM0)
        """
        Vpl_rd_kn = Av_m2 * fy_mpa * 1000 / (math.sqrt(3) * gamma_M0) / 1000
        utilization = abs(V_kn) / Vpl_rd_kn if Vpl_rd_kn > 0 else float("inf")
        margin = 1.0 - utilization
        status = "PASS" if utilization <= 1.0 else "FAIL"

        return CheckResult(
            check_type="SHEAR",
            status=status,
            utilization=round(utilization, 6),
            margin=round(margin, 6),
            resistance=round(Vpl_rd_kn, 4),
            solicitation=round(abs(V_kn), 4),
            norm=norm,
            norm_clause=norm_clause,
            intermediate_values={
                "Av_m2": Av_m2,
                "fy_mpa": fy_mpa,
                "gamma_M0": gamma_M0,
                "V_kn": V_kn,
                "Vpl_rd_kn": Vpl_rd_kn,
            },
        )

    @staticmethod
    def check_circular_wall_slenderness(
        D_ext_mm: float,
        t_eff_mm: float,
        E_mpa: float = 210000.0,
        fy_mpa: float = 235.0,
        norm: str = "EN40-3-3",
        norm_clause: str = "§5.3",
    ) -> CheckResult:
        """
        Esbeltez de pared para sección circular tubular.
        D/t es el parámetro principal de clasificación.
        Clase 1: D/t ≤ 50·(235/fy); Clase 2: ≤70·(235/fy); Clase 3: ≤90·(235/fy).
        Para D/t > 90·(235/fy) → Clase 4, requiere análisis de pandeo local.
        """
        if t_eff_mm <= 0:
            raise ValueError("t_eff_mm debe ser positivo")

        dt = D_ext_mm / t_eff_mm
        epsilon_sq = 235.0 / fy_mpa
        lim1 = 50 * epsilon_sq
        lim2 = 70 * epsilon_sq
        lim3 = 90 * epsilon_sq

        if dt <= lim1:
            section_class = 1
        elif dt <= lim2:
            section_class = 2
        elif dt <= lim3:
            section_class = 3
        else:
            section_class = 4

        # Utilización = D/t frente al límite de clase 3 (conservador)
        utilization = dt / lim3
        status = "PASS" if section_class <= 3 else "WARNING"
        domain_notes = "Clase 4: requiere propiedades efectivas (STEEL-SEC-001)" if section_class == 4 else None

        return CheckResult(
            check_type="LOCAL_BUCKLING",
            status=status,
            utilization=round(utilization, 6),
            margin=round(1.0 - utilization, 6),
            resistance=lim3,
            solicitation=round(dt, 4),
            norm=norm,
            norm_clause=norm_clause,
            intermediate_values={
                "D_ext_mm": D_ext_mm,
                "t_eff_mm": t_eff_mm,
                "D_over_t": round(dt, 4),
                "epsilon_sq": round(epsilon_sq, 4),
                "class_limit_1": round(lim1, 2),
                "class_limit_2": round(lim2, 2),
                "class_limit_3": round(lim3, 2),
                "section_class": section_class,
            },
            domain_notes=domain_notes,
        )

    @staticmethod
    def compute_run_hash(
        geometry_hash: str,
        material_hash: str,
        rules_hash: str,
        stress_hash: str,
        engine_version: str = "1.0",
    ) -> str:
        """Hash determinista de una ejecución completa."""
        data = {
            "geometry": geometry_hash,
            "material": material_hash,
            "rules": rules_hash,
            "stress": stress_hash,
            "engine": engine_version,
        }
        return hashlib.sha256(
            json.dumps(data, sort_keys=True).encode()
        ).hexdigest()


# ===========================================================================
# WeldEngine — motor de cálculo de soldaduras
# ===========================================================================

@dataclass
class WeldForces:
    """Resultantes concurrentes en el centroide del grupo de soldadura."""
    Fx_kn: float = 0.0
    Fy_kn: float = 0.0
    Fz_kn: float = 0.0
    Mx_knm: float = 0.0
    My_knm: float = 0.0
    Mz_knm: float = 0.0


class WeldEngine:
    """
    Motor de cálculo de grupos de soldadura.
    Verifica resistencia estática y fatiga.

    Método de referencia: tensión equivalente σ_eq para soldaduras a filete.
    σ_eq = √(σ_⊥² + 3·τ_⊥² + 3·τ_∥²) ≤ fu_w / (β_w · γM2)
    """

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
        norm: str = "EN1993-1-8",
        norm_clause: str = "§4.5.3",
    ) -> CheckResult:
        """
        Comprobación estática simplificada de soldadura a filete.
        Tensión equivalente distribuida sobre el área de garganta.
        """
        if effective_throat_mm <= 0 or effective_length_mm <= 0:
            raise ValueError("Garganta y longitud deben ser positivas")

        a_m = effective_throat_mm / 1000
        l_m = effective_length_mm / 1000
        A_weld = a_m * l_m    # área de garganta en m²

        # Tensiones medias (Pa) = Fuerza(N) / Área(m²)
        Fx_N = Fx_kn * 1000
        Fy_N = Fy_kn * 1000
        Fz_N = Fz_kn * 1000

        sigma_perp = Fz_N / A_weld      # perpendicular al plano de garganta
        tau_perp = Fy_N / A_weld        # cortante en el plano, perpendicular al eje
        tau_par = Fx_N / A_weld         # cortante paralelo al eje de la soldadura

        sigma_eq_pa = math.sqrt(sigma_perp**2 + 3 * tau_perp**2 + 3 * tau_par**2)
        sigma_eq_mpa = sigma_eq_pa / 1e6

        sigma_rd_mpa = fu_w_mpa / (beta_w * gamma_M2)
        utilization = sigma_eq_mpa / sigma_rd_mpa if sigma_rd_mpa > 0 else float("inf")
        margin = 1.0 - utilization
        status = "PASS" if utilization <= 1.0 else "FAIL"

        return CheckResult(
            check_type="WELD_STATIC",
            status=status,
            utilization=round(utilization, 6),
            margin=round(margin, 6),
            resistance=round(sigma_rd_mpa, 4),
            solicitation=round(sigma_eq_mpa, 4),
            norm=norm,
            norm_clause=norm_clause,
            intermediate_values={
                "effective_throat_mm": effective_throat_mm,
                "effective_length_mm": effective_length_mm,
                "A_weld_m2": A_weld,
                "sigma_perp_mpa": round(sigma_perp / 1e6, 4),
                "tau_perp_mpa": round(tau_perp / 1e6, 4),
                "tau_par_mpa": round(tau_par / 1e6, 4),
                "sigma_eq_mpa": round(sigma_eq_mpa, 4),
                "sigma_rd_mpa": round(sigma_rd_mpa, 4),
                "fu_w_mpa": fu_w_mpa,
                "beta_w": beta_w,
                "gamma_M2": gamma_M2,
            },
        )

    @staticmethod
    def seam_in_door_check(seam_azimuth_deg: float, door_azimuth_deg: float, tolerance_deg: float = 5.0) -> bool:
        """
        Regla GEO: costura longitudinal NO puede coincidir con el hueco de puerta.
        Devuelve True (conforme) si la costura está fuera del hueco.
        """
        diff = abs(seam_azimuth_deg - door_azimuth_deg) % 360
        diff = min(diff, 360 - diff)
        return diff > tolerance_deg


# ===========================================================================
# FatigueEngine — ciclos y daño acumulado
# ===========================================================================

class FatigueEngine:
    """
    Motor de verificación de fatiga.
    Soporta método simplificado EN 40 y daño acumulado (Palmgren-Miner).

    Principio: Los ciclos de distintas fuentes conservan su origen para
    evitar doble conteo.
    """

    @staticmethod
    def miner_damage(
        cycle_blocks: list[dict[str, float]],
    ) -> dict[str, float]:
        """
        Cálculo de daño acumulado de Palmgren-Miner.
        cycle_blocks: lista de {delta_sigma_mpa, n_cycles, N_ref, source}
        donde N_ref es el número de ciclos a rotura para Δσ en la curva S-N.

        D = Σ(n_i / N_i) ≤ 1.0
        """
        total_damage = 0.0
        sources: dict[str, float] = {}
        for block in cycle_blocks:
            delta_s = block["delta_sigma_mpa"]
            n = block["n_cycles"]
            N_ref = block.get("N_ref", 0)
            source = block.get("source", "unknown")
            if N_ref <= 0:
                continue
            d_i = n / N_ref
            total_damage += d_i
            sources[source] = sources.get(source, 0.0) + d_i

        return {
            "total_damage": round(total_damage, 8),
            "sources": {k: round(v, 8) for k, v in sources.items()},
            "utilization": round(total_damage, 6),
            "status": "PASS" if total_damage <= 1.0 else "FAIL",
        }

    @staticmethod
    def simplified_en40_fatigue_check(
        delta_sigma_mpa: float,
        fatigue_category_mpa: float,
        gamma_Ff: float = 1.0,
        gamma_Mf: float = 1.15,
    ) -> CheckResult:
        """
        Comprobación simplificada EN 40: rango de tensión frente a categoría.
        gamma_Ff · ΔσE ≤ ΔσC / gamma_Mf
        """
        demand = gamma_Ff * delta_sigma_mpa
        capacity = fatigue_category_mpa / gamma_Mf
        utilization = demand / capacity if capacity > 0 else float("inf")
        margin = 1.0 - utilization
        status = "PASS" if utilization <= 1.0 else "FAIL"

        return CheckResult(
            check_type="FATIGUE",
            status=status,
            utilization=round(utilization, 6),
            margin=round(margin, 6),
            resistance=round(capacity, 4),
            solicitation=round(demand, 4),
            norm="EN40-3-3",
            norm_clause="§9",
            intermediate_values={
                "delta_sigma_mpa": delta_sigma_mpa,
                "fatigue_category_mpa": fatigue_category_mpa,
                "gamma_Ff": gamma_Ff,
                "gamma_Mf": gamma_Mf,
                "demand_mpa": round(demand, 4),
                "capacity_mpa": round(capacity, 4),
            },
        )

    @staticmethod
    def check_duplicate_source(cycle_blocks: list[dict[str, Any]]) -> bool:
        """
        Detecta doble conteo: misma fuente aparece más de una vez.
        Retorna True si hay duplicado (ERROR).
        """
        sources = [b.get("source") for b in cycle_blocks]
        return len(sources) != len(set(sources))


# ===========================================================================
# DurabilityService — selección de sistema de protección
# ===========================================================================

class DurabilityService:
    """
    Motor de selección de sistema de protección anticorrosiva.
    Verifica reglas automáticas de galvanizado.
    """

    # Rangos de vida útil orientativos (años) por sistema y categoría
    # Fuente: EN ISO 12944 — valores de referencia; el proyectista confirma
    _LIFE_RANGES: dict[str, dict[str, tuple[int, int]]] = {
        "HOT_DIP_GALVANIZING": {
            "C1": (75, 100), "C2": (35, 75), "C3": (15, 35),
            "C4": (7, 15), "C5": (4, 7), "CX": (2, 4),
        },
        "PAINT": {
            "C1": (25, 40), "C2": (15, 25), "C3": (10, 15),
            "C4": (7, 10), "C5": (3, 7), "CX": (1, 3),
        },
        "DUPLEX": {
            "C1": (80, 120), "C2": (50, 80), "C3": (25, 50),
            "C4": (15, 25), "C5": (8, 15), "CX": (4, 8),
        },
    }

    @staticmethod
    def check_life_adequacy(
        protection_system: str,
        corrosivity_category: str,
        design_life_years: int,
    ) -> tuple[bool, str]:
        """
        Comprueba si el sistema cubre la vida útil de diseño.
        Retorna (compatible, mensaje).
        """
        ranges = DurabilityService._LIFE_RANGES.get(protection_system, {})
        cat_range = ranges.get(corrosivity_category)
        if cat_range is None:
            return False, f"STEEL-COR-001: no hay datos de vida útil para {protection_system} en {corrosivity_category}"
        min_life, max_life = cat_range
        if design_life_years <= max_life:
            compatible = True
            msg = f"Sistema {protection_system} cubre vida útil {design_life_years} a en categoría {corrosivity_category} (rango {min_life}–{max_life} a)"
        else:
            compatible = False
            msg = f"STEEL-COR-001: {protection_system} no cubre {design_life_years} a en {corrosivity_category} (máx {max_life} a)"
        return compatible, msg

    @staticmethod
    def check_galvanizing_geometry(
        closed_volumes: list[dict[str, Any]],
    ) -> tuple[bool, list[str]]:
        """
        Verifica que no existan cavidades cerradas sin venteo/drenaje.
        closed_volumes: lista de {id, has_vent, has_drain, volume_cm3}
        Retorna (all_ok, lista_errores).
        """
        errors = []
        for vol in closed_volumes:
            if not vol.get("has_vent") or not vol.get("has_drain"):
                errors.append(
                    f"STEEL-COR-001: cavidad {vol.get('id', '?')} sin venteo/drenaje — riesgo en galvanizado"
                )
        return len(errors) == 0, errors


# ===========================================================================
# ManufacturingService — reglas de fabricabilidad bloqueantes
# ===========================================================================

@dataclass
class FabricabilityCheck:
    rule: str
    compliant: bool
    blocking: bool
    detail: Optional[str] = None
    error_code: Optional[str] = None


class ManufacturingService:
    """
    Servicio de fabricabilidad: aplica reglas bloqueantes de Salvi.
    """

    MAX_PIECE_LENGTH_M = 12.0
    MIN_DIAMETER_MM = 60.0
    STANDARD_TAPERS = (11.0, 13.0)  # ‰

    @staticmethod
    def check_piece_length(length_m: float) -> FabricabilityCheck:
        ok = length_m <= ManufacturingService.MAX_PIECE_LENGTH_M
        return FabricabilityCheck(
            rule="LONGITUD_MAXIMA_PIEZA",
            compliant=ok,
            blocking=True,
            detail=f"Longitud {length_m:.2f} m {'≤' if ok else '>'} {ManufacturingService.MAX_PIECE_LENGTH_M} m",
            error_code=None if ok else "STEEL-MFG-001",
        )

    @staticmethod
    def check_min_diameter(diameter_mm: float) -> FabricabilityCheck:
        ok = diameter_mm >= ManufacturingService.MIN_DIAMETER_MM
        return FabricabilityCheck(
            rule="DIAMETRO_MINIMO",
            compliant=ok,
            blocking=True,
            detail=f"Diámetro {diameter_mm:.1f} mm {'≥' if ok else '<'} {ManufacturingService.MIN_DIAMETER_MM} mm",
            error_code=None if ok else "STEEL-MFG-001",
        )

    @staticmethod
    def check_seam_not_in_door(seam_azimuth_deg: float, door_azimuth_deg: float, tolerance_deg: float = 5.0) -> FabricabilityCheck:
        diff = abs(seam_azimuth_deg - door_azimuth_deg) % 360
        diff = min(diff, 360 - diff)
        ok = diff > tolerance_deg
        return FabricabilityCheck(
            rule="COSTURA_NO_EN_PUERTA",
            compliant=ok,
            blocking=True,
            detail=f"Ángulo entre costura y puerta: {diff:.1f}° {'>' if ok else '≤'} {tolerance_deg}° (regla: costura dentro del hueco de puerta PROHIBIDA)",
            error_code=None if ok else "STEEL-MFG-001",
        )

    @staticmethod
    def cone_frustum_blank_geometry(
        D_base_mm: float,
        D_top_mm: float,
        height_m: float,
    ) -> dict[str, float]:
        """
        Desarrollo de tronco de cono: geometría exacta del sector anular.
        Devuelve: radio_base, radio_top, sector_angle_deg, arc_length_base_mm,
        slant_height_mm, blank_area_m2.
        """
        if D_base_mm <= D_top_mm:
            raise ValueError("D_base_mm debe ser mayor que D_top_mm para tronco de cono")
        if height_m <= 0:
            raise ValueError("height_m debe ser positivo")

        R_base = D_base_mm / 2
        R_top = D_top_mm / 2
        h_mm = height_m * 1000

        # Generatriz del tronco de cono
        slant = math.sqrt(h_mm**2 + (R_base - R_top)**2)
        # Radio de sector en el desarrollo
        rho_base = slant * R_base / (R_base - R_top) if R_base != R_top else float("inf")
        rho_top = slant * R_top / (R_base - R_top) if R_base != R_top else 0.0
        # Ángulo del sector: longitud del arco = 2π·R_base → ángulo = 2π·R_base / rho_base
        sector_angle_rad = 2 * math.pi * R_base / rho_base if rho_base > 0 else 2 * math.pi
        sector_angle_deg = math.degrees(sector_angle_rad)
        arc_length_base_mm = sector_angle_rad * rho_base
        blank_area_m2 = math.pi * (rho_base**2 - rho_top**2) * sector_angle_rad / (2 * math.pi) / 1e6

        return {
            "slant_height_mm": round(slant, 4),
            "rho_base_mm": round(rho_base, 4),
            "rho_top_mm": round(rho_top, 4),
            "sector_angle_deg": round(sector_angle_deg, 4),
            "arc_length_base_mm": round(arc_length_base_mm, 4),
            "blank_area_m2": round(blank_area_m2, 6),
        }

    @staticmethod
    def bom_mass_from_geometry(
        volumes_m3: dict[str, float],
        rho_kg_m3: float = 7850.0,
    ) -> dict[str, float]:
        """
        Calcula masa por grupo de BOM a partir de volúmenes.
        """
        result = {}
        for group, vol in volumes_m3.items():
            result[group] = round(vol * rho_kg_m3, 3)
        result["total_kg"] = round(sum(result.values()), 3)
        return result


# ===========================================================================
# SteelOptimizer — generación de candidatos y frente de Pareto
# ===========================================================================

@dataclass
class DesignVariable:
    steel_grade: str
    subgrade: str
    thickness_mm: float
    D_base_mm: float
    D_top_mm: float
    n_faces: Optional[int] = None
    taper_per_mille: Optional[float] = None


@dataclass
class DesignCandidate:
    variables: DesignVariable
    total_mass_kg: float
    total_industrial_cost: float
    co2_total_kg: float
    max_utilization: float
    fabricable: bool
    transportable: bool
    pareto_dominated: bool = False


class SteelOptimizer:
    """
    Optimizador discreto + continuo para acero.

    Fase 1: genera candidatos discretos fabricables desde bibliotecas.
    Fase 2: ajuste fino de variables continuas.
    Fase 3: califica candidatos con F4+F5 completos.
    Fase 4: construye frente de Pareto.

    Nunca optimiza una geometría que no pueda convertirse en BOM y proceso.
    """

    @staticmethod
    def is_dominated(a: DesignCandidate, b: DesignCandidate) -> bool:
        """
        True si 'a' está dominado por 'b' (b es mejor o igual en todos los objetivos).
        Objetivos a minimizar: total_industrial_cost, total_mass_kg, co2_total_kg.
        """
        return (
            b.total_industrial_cost <= a.total_industrial_cost
            and b.total_mass_kg <= a.total_mass_kg
            and b.co2_total_kg <= a.co2_total_kg
            and (
                b.total_industrial_cost < a.total_industrial_cost
                or b.total_mass_kg < a.total_mass_kg
                or b.co2_total_kg < a.co2_total_kg
            )
        )

    @staticmethod
    def build_pareto_front(candidates: list[DesignCandidate]) -> list[DesignCandidate]:
        """
        Construye el frente de Pareto eliminando candidatos dominados.
        Solo candidatos fabricables y transportables pueden estar en el frente.
        """
        eligible = [c for c in candidates if c.fabricable and c.transportable]
        pareto: list[DesignCandidate] = []
        for c in eligible:
            dominated = any(SteelOptimizer.is_dominated(c, b) for b in eligible if b is not c)
            if not dominated:
                pareto.append(c)
            else:
                c.pareto_dominated = True
        return pareto

    @staticmethod
    def select_solutions(
        pareto: list[DesignCandidate],
    ) -> dict[str, Optional[DesignCandidate]]:
        """
        Identifica la solución de menor coste, menor peso, menor CO₂
        y la equilibrada (menor distancia normalizada al origen del frente).
        """
        if not pareto:
            return {"min_cost": None, "min_weight": None, "min_co2": None, "balanced": None}

        min_cost = min(pareto, key=lambda c: c.total_industrial_cost)
        min_weight = min(pareto, key=lambda c: c.total_mass_kg)
        min_co2 = min(pareto, key=lambda c: c.co2_total_kg)

        # Solución equilibrada: menor suma normalizada de los tres objetivos
        max_cost = max(c.total_industrial_cost for c in pareto)
        max_weight = max(c.total_mass_kg for c in pareto)
        max_co2 = max(c.co2_total_kg for c in pareto)

        def normalized_distance(c: DesignCandidate) -> float:
            nc = c.total_industrial_cost / max_cost if max_cost > 0 else 0
            nw = c.total_mass_kg / max_weight if max_weight > 0 else 0
            nco2 = c.co2_total_kg / max_co2 if max_co2 > 0 else 0
            return nc + nw + nco2

        balanced = min(pareto, key=normalized_distance)

        return {
            "min_cost": min_cost,
            "min_weight": min_weight,
            "min_co2": min_co2,
            "balanced": balanced,
        }
