"""
Salvi Studio · Columns — Fase 9: Uniones y Columnas Segmentadas
Motor de cálculo determinista (sin IA en verificaciones)
"""
from __future__ import annotations
import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.models.db.joints import JointType, JointCheckStatus, JointMaturityLevel


# ─────────────────────────────────────────────────────────────────────────────
# Utilidades
# ─────────────────────────────────────────────────────────────────────────────

def _sha256(data: dict) -> str:
    raw = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass
class CheckResult:
    status: JointCheckStatus
    utilization: float
    governing_rule: str
    intermediate_values: Dict[str, Any] = field(default_factory=dict)
    error_codes: List[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# SegmentationService — generación de planes de segmentación
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SegmentCandidate:
    index: int
    z_start: float
    z_end: float
    length: float
    envelope_length: float
    mass_kg: Optional[float] = None
    galvanizing_ok: bool = True
    transport_ok: bool = True
    weight_ok: bool = True
    error_codes: List[str] = field(default_factory=list)


@dataclass
class JointCandidate:
    z_station: float
    joint_type: JointType
    in_forbidden_zone: bool
    stiffness_model: str = "DECOUPLED_SPRINGS"
    error_codes: List[str] = field(default_factory=list)


@dataclass
class SegmentationResult:
    feasible: bool
    piece_count: int
    segments: List[SegmentCandidate]
    joints: List[JointCandidate]
    plan_hash: str
    error_codes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class SegmentationService:

    MAX_HEIGHT_M = 30.0
    DEFAULT_MAX_LENGTH_M = 12.0

    @classmethod
    def build_forbidden_zones(
        cls,
        total_height_m: float,
        door_stations: Optional[List[float]] = None,
        arm_stations: Optional[List[float]] = None,
        thickness_changes: Optional[List[float]] = None,
        min_clearance_m: float = 0.3,
    ) -> List[Tuple[float, float]]:
        """Paso 1: construir intervalos alrededor de zonas prohibidas."""
        zones: List[Tuple[float, float]] = []
        # Extremos siempre prohibidos
        zones.append((0.0, min_clearance_m))
        zones.append((total_height_m - min_clearance_m, total_height_m))

        for z in (door_stations or []):
            zones.append((z - min_clearance_m, z + min_clearance_m))
        for z in (arm_stations or []):
            zones.append((z - min_clearance_m, z + min_clearance_m))
        for z in (thickness_changes or []):
            zones.append((z - min_clearance_m, z + min_clearance_m))
        return zones

    @classmethod
    def is_in_forbidden_zone(cls, z: float, zones: List[Tuple[float, float]]) -> bool:
        return any(lo <= z <= hi for lo, hi in zones)

    @classmethod
    def generate_candidate_stations(
        cls,
        total_height_m: float,
        max_length_m: float,
        forbidden_zones: List[Tuple[float, float]],
        preferred_stations: Optional[List[float]] = None,
    ) -> List[float]:
        """Paso 2: estaciones candidatas compatibles con límite de longitud."""
        n_min = math.ceil(total_height_m / max_length_m) - 1
        stations: List[float] = []

        # Primero estaciones preferentes
        for z in (preferred_stations or []):
            if 0 < z < total_height_m:
                stations.append(z)

        # Luego distribuir uniformemente
        if n_min > 0:
            step = total_height_m / (n_min + 1)
            for i in range(1, n_min + 1):
                z_candidate = round(i * step, 3)
                # Desplazar si cae en zona prohibida (±0.5 m)
                if cls.is_in_forbidden_zone(z_candidate, forbidden_zones):
                    for delta in [0.5, -0.5, 1.0, -1.0]:
                        z_alt = z_candidate + delta
                        if 0 < z_alt < total_height_m and not cls.is_in_forbidden_zone(z_alt, forbidden_zones):
                            z_candidate = z_alt
                            break
                stations.append(round(z_candidate, 3))

        return sorted(set(stations))

    @classmethod
    def select_joint_type(
        cls,
        material_route: str,
        taper: float,
        demountable: bool,
        high_torsion: bool,
        hybrid: bool,
        concrete: bool,
        concrete_family_approved: bool = False,
    ) -> Tuple[JointType, str]:
        """Paso 3: tipo de unión compatible con material y geometría."""
        if concrete:
            if not concrete_family_approved:
                return JointType.J9_HOR, "J9-E015"
            return JointType.J9_HOR, ""
        if hybrid:
            return JointType.J9_HIB, ""
        if demountable:
            return JointType.J9_BRI, ""
        if material_route == "ALUMINIUM":
            if taper > 0:
                return JointType.J9_TEL, ""   # solo si validada para aluminio
            return JointType.J9_BRI, ""
        # Acero
        if taper > 0.003:  # cónico
            return JointType.J9_TEL, ""
        return JointType.J9_MAN, ""

    @classmethod
    def generate(
        cls,
        total_height_m: float,
        material_route: str,
        max_length_m: float = DEFAULT_MAX_LENGTH_M,
        max_mass_kg: Optional[float] = None,
        door_stations: Optional[List[float]] = None,
        arm_stations: Optional[List[float]] = None,
        thickness_changes: Optional[List[float]] = None,
        preferred_stations: Optional[List[float]] = None,
        demountable: bool = False,
        high_torsion: bool = False,
        taper: float = 0.01,
        hybrid: bool = False,
        concrete: bool = False,
        concrete_family_approved: bool = False,
        exception_approved: bool = False,
    ) -> SegmentationResult:
        """Genera plan de segmentación (pasos 1-4 del algoritmo)."""
        error_codes: List[str] = []
        warnings: List[str] = []

        if total_height_m > cls.MAX_HEIGHT_M:
            error_codes.append("J9-E001")
            return SegmentationResult(False, 0, [], [], "", error_codes)

        # Una sola pieza si cabe
        if total_height_m <= max_length_m:
            seg = SegmentCandidate(0, 0.0, total_height_m, total_height_m, total_height_m)
            return SegmentationResult(
                feasible=True, piece_count=1,
                segments=[seg], joints=[],
                plan_hash=_sha256({"h": total_height_m, "n": 1}),
            )

        # Validar excepción si supera 12 m por pieza
        if max_length_m > cls.DEFAULT_MAX_LENGTH_M and not exception_approved:
            error_codes.append("J9-E001")
            warnings.append("Longitud > 12 m requiere excepción aprobada")

        forbidden = cls.build_forbidden_zones(total_height_m, door_stations, arm_stations, thickness_changes)
        stations = cls.generate_candidate_stations(total_height_m, max_length_m, forbidden, preferred_stations)

        # Construir segmentos
        z_breaks = [0.0] + stations + [total_height_m]
        segments: List[SegmentCandidate] = []
        joints: List[JointCandidate] = []

        for i, (z0, z1) in enumerate(zip(z_breaks[:-1], z_breaks[1:])):
            length = round(z1 - z0, 4)
            envelope = round(length + 0.1, 4)  # 100mm extra para brida
            seg = SegmentCandidate(i, z0, z1, length, envelope)

            if length > max_length_m:
                seg.error_codes.append("J9-E001")
                seg.galvanizing_ok = False
            if max_mass_kg and (mass := length * 50.0) > max_mass_kg:
                seg.weight_ok = False
                seg.mass_kg = mass

            segments.append(seg)

        for z in stations:
            jtype, err = cls.select_joint_type(
                material_route, taper, demountable, high_torsion, hybrid, concrete, concrete_family_approved)
            in_forbidden = cls.is_in_forbidden_zone(z, forbidden)
            jcodes = []
            if in_forbidden:
                jcodes.append("J9-E002")
            if err:
                jcodes.append(err)
            joints.append(JointCandidate(z, jtype, in_forbidden, error_codes=jcodes))

        feasible = all(not s.error_codes for s in segments) and all(not j.in_forbidden_zone for j in joints)
        plan_hash = _sha256({"h": total_height_m, "n": len(segments), "stations": stations})

        return SegmentationResult(feasible, len(segments), segments, joints, plan_hash,
                                   error_codes, warnings)


# ─────────────────────────────────────────────────────────────────────────────
# TelescopicJointService — unión telescópica
# ─────────────────────────────────────────────────────────────────────────────

class TelescopicJointService:
    """
    Cálculo de unión telescópica por solape.
    Referencia: EN 40-3-3 + modelo mecánico validado.
    """

    @staticmethod
    def contact_pressure(
        D_ext_mm: float, t_wall_mm: float, overlap_mm: float,
        My_knm: float, Mz_knm: float, friction_coeff: float,
    ) -> Dict[str, float]:
        """Presión de contacto por par de presiones (distribución triangular)."""
        M_total = math.hypot(My_knm, Mz_knm) * 1e6  # N·mm
        D_mid = D_ext_mm - t_wall_mm
        # Fuerza de contacto en extremos del solape (par de fuerzas)
        F_contact = 2.0 * M_total / overlap_mm if overlap_mm > 0 else 0.0
        # Área de contacto (banda circunferencial)
        A_contact = math.pi * D_mid * t_wall_mm / 2.0
        p_mpa = F_contact / A_contact if A_contact > 0 else 0.0
        return {
            "contact_force_kn": F_contact / 1000.0,
            "contact_pressure_mpa": p_mpa,
        }

    @staticmethod
    def check_overlap(
        D_ext_mm: float, t_wall_mm: float, overlap_mm: float,
        My_knm: float, Mz_knm: float, N_kn: float,
        friction_coeff: float, fy_mpa: float, ovalization_mm: float = 0.0,
    ) -> CheckResult:
        """Verificación completa de unión telescópica."""
        errors: List[str] = []
        D_mid = D_ext_mm - t_wall_mm
        A = math.pi * D_mid * t_wall_mm

        # Mínimo de solape: 1.5 × D_ext
        overlap_min = 1.5 * D_ext_mm
        if overlap_mm < overlap_min:
            errors.append("J9-E007")

        # Presiones
        cp = TelescopicJointService.contact_pressure(D_ext_mm, t_wall_mm, overlap_mm, My_knm, Mz_knm, friction_coeff)
        p = cp["contact_pressure_mpa"]
        fy_wall = fy_mpa / math.sqrt(3.0)  # tensión circunferencial límite

        # Tensión axial por N
        sigma_N = abs(N_kn * 1000.0 / A) if A > 0 else 0.0

        # Tensión circunferencial por ovalización (aproximación)
        sigma_oval = 0.0 if ovalization_mm == 0 else (
            (ovalization_mm / D_mid) * fy_mpa * 0.5
        )

        sigma_total = sigma_N + sigma_oval
        util_stress = sigma_total / (fy_mpa / 1.0)

        # Deslizamiento en ELS
        V_total = math.hypot(My_knm, Mz_knm) * 1000.0 / (overlap_mm * friction_coeff) if (overlap_mm * friction_coeff) > 0 else 0.0
        sliding_sls = V_total * 0.001  # mm (simplificado)

        # Rigidez equivalente
        E = 210000.0  # MPa acero
        I = math.pi / 64.0 * ((D_ext_mm)**4 - (D_ext_mm - 2*t_wall_mm)**4)
        k_flex = 3.0 * E * I / (overlap_mm**3) if overlap_mm > 0 else 0.0

        util_sliding = sliding_sls / 10.0  # límite 10 mm ELS

        # Fretting
        fretting_risk = sliding_sls > 0.1  # > 0.1 mm → riesgo fretting

        # Estado
        if errors or util_stress > 1.0 or util_sliding > 1.0:
            status = JointCheckStatus.FAIL
        else:
            status = JointCheckStatus.PASS

        return CheckResult(
            status=status,
            utilization=max(util_stress, util_sliding),
            governing_rule="EN 40-3-3 §7.3 / Modelo Mecánico J9-TEL",
            intermediate_values={
                "contact_pressure_mpa": p,
                "sigma_total_mpa": sigma_total,
                "sliding_sls_mm": sliding_sls,
                "rigidity_kN_per_mm": k_flex / 1000.0,
                "fretting_risk": fretting_risk,
                "overlap_min_mm": overlap_min,
            },
            error_codes=errors,
        )

    @classmethod
    def check_insertion_force(
        cls, D_ext_mm: float, t_wall_mm: float, overlap_mm: float,
        friction_coeff_max: float, insertion_force_limit_kn: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Verifica que la fuerza de inserción es manejable."""
        D_mid = D_ext_mm - t_wall_mm
        A_contact = math.pi * D_mid * t_wall_mm / 2.0
        # Presión para insertar (≈ peso del tramo superior)
        # Simplificado: se usa fricción × peso estimado
        weight_kn = A_contact * 1e-6 * 7850 * 9.81 * overlap_mm * 1e-3 / 1000.0
        insertion_force = friction_coeff_max * weight_kn * 10.0  # conservador
        feasible = insertion_force_limit_kn is None or insertion_force <= insertion_force_limit_kn
        return {
            "insertion_force_kn": round(insertion_force, 2),
            "feasible": feasible,
            "error_code": "J9-E011" if not feasible else None,
        }

    @classmethod
    def check_drain(cls, drain_ok: bool, environment: str) -> Dict[str, Any]:
        """Drenaje ausente en ambiente húmedo → bloqueo."""
        humid = environment.upper() in {"C3", "C4", "C5", "CX", "MARINE"}
        if not drain_ok and humid:
            return {"blocked": True, "error_code": "J9-E012"}
        return {"blocked": False, "error_code": None}

    @classmethod
    def robust_check(
        cls, base_result: CheckResult,
        overlap_factor: float = 1.0, friction_factor: float = 1.0,
        fy_factor: float = 1.0, ovalization_factor: float = 1.0,
    ) -> Dict[str, Any]:
        """Escenario robusto con factores adversos."""
        # Un escenario peor siempre tiene mayor utilización
        robust_util = base_result.utilization
        if overlap_factor < 1.0:
            robust_util *= (1.0 / overlap_factor)
        if friction_factor < 1.0:
            robust_util *= (1.0 / friction_factor)
        if fy_factor < 1.0:
            robust_util *= (1.0 / fy_factor)
        if ovalization_factor > 1.0:
            robust_util *= ovalization_factor
        return {
            "nominal_utilization": base_result.utilization,
            "worst_utilization": min(robust_util, 9.99),
            "robust_pass": robust_util <= 1.0,
            "error_code": "J9-E010" if robust_util > 1.0 else None,
        }


# ─────────────────────────────────────────────────────────────────────────────
# FlangedJointService — unión embridada atornillada
# ─────────────────────────────────────────────────────────────────────────────

class FlangedJointService:
    """
    Distribución de esfuerzos en grupo de tornillos de brida.
    EC3-1-8 + EN 40-3-3 + modelo de prying.
    """

    @staticmethod
    def bolt_properties(bolt_class: str) -> Tuple[float, float]:
        """fyb, fub en MPa según clase."""
        table = {
            "4.6": (240.0, 400.0), "5.6": (300.0, 500.0),
            "8.8": (640.0, 800.0), "10.9": (900.0, 1000.0),
        }
        return table.get(bolt_class, (640.0, 800.0))

    @classmethod
    def distribute_bolts(
        cls,
        bolt_count: int, bolt_pcd_mm: float, bolt_class: str, bolt_diameter_mm: float,
        N_kn: float, Vy_kn: float, Vz_kn: float, My_knm: float, Mz_knm: float, T_knm: float,
        pretensioned: bool = False, target_pretension_kn: Optional[float] = None,
        friction_coeff: float = 0.3, gamma_M2: float = 1.25,
    ) -> CheckResult:
        """Distribución de esfuerzos en grupo de tornillos (posición angular)."""
        errors: List[str] = []
        fyb, fub = cls.bolt_properties(bolt_class)
        R_bolt = bolt_pcd_mm / 2.0  # mm
        A_bolt = math.pi / 4.0 * bolt_diameter_mm ** 2

        # Resistencias
        Fv_Rd_per_bolt = 0.6 * fub * A_bolt / (gamma_M2 * 1000.0)  # kN
        Ft_Rd_per_bolt = 0.9 * fub * A_bolt / (gamma_M2 * 1000.0)  # kN

        # Fuerza axial por tornillo
        N_per_bolt = N_kn / bolt_count

        # Momento resultante → tensión de tornillo más cargado
        M_res_knm = math.hypot(My_knm, Mz_knm)
        # Tornillo a máx distancia (polo de giro = centroide del grupo)
        Ip = bolt_count * R_bolt ** 2  # polar simplificado
        F_moment_kn = M_res_knm * 1e3 * R_bolt / (Ip if Ip > 0 else 1.0) * R_bolt / 1e3
        max_tension = N_per_bolt + F_moment_kn

        # Prying (amplificación por flexibilidad)
        prying_factor = 1.25  # simplificado (EC3-1-8 §6.2.4)
        max_tension_prying = max_tension * prying_factor

        # Cortante por tornillo
        V_total = math.hypot(Vy_kn, Vz_kn) + abs(T_knm) * 1e3 / R_bolt if R_bolt > 0 else 0.0
        Fv_per_bolt = V_total / bolt_count

        # Pretensión y deslizamiento
        Fs_Rd = 0.0
        sliding_ok = True
        if pretensioned and target_pretension_kn:
            Fs_Rd = friction_coeff * target_pretension_kn / 1.1  # ELS
            sliding_ok = Fv_per_bolt <= Fs_Rd
        elif not pretensioned:
            # Apoyo en agujero
            Fb_Rd = 2.5 * fub * bolt_diameter_mm * 10.0 / (gamma_M2 * 1000.0)  # simplificado
            sliding_ok = Fv_per_bolt <= Fb_Rd

        if not sliding_ok:
            errors.append("J9-E008")

        # Interacción tensión-cortante
        util_t = max_tension_prying / Ft_Rd_per_bolt if Ft_Rd_per_bolt > 0 else 0.0
        util_v = Fv_per_bolt / Fv_Rd_per_bolt if Fv_Rd_per_bolt > 0 else 0.0
        util_interact = util_t + util_v  # EC3-1-8 conservador

        # Contacto de brida
        min_tension = N_per_bolt - F_moment_kn
        if min_tension < 0:
            contact_state = "PARTIALLY_OPEN"
        else:
            contact_state = "FULLY_CLOSED"

        util = max(util_t, util_v, util_interact)
        if util > 1.0 or errors:
            status = JointCheckStatus.FAIL
        else:
            status = JointCheckStatus.PASS

        return CheckResult(
            status=status,
            utilization=util,
            governing_rule="EC3-1-8 §6.2 + EN 40-3-3 §7.4",
            intermediate_values={
                "max_bolt_tension_kn": round(max_tension_prying, 3),
                "min_bolt_tension_kn": round(min_tension, 3),
                "shear_per_bolt_kn": round(Fv_per_bolt, 3),
                "prying_factor": prying_factor,
                "contact_state": contact_state,
                "util_tension": round(util_t, 4),
                "util_shear": round(util_v, 4),
                "util_interaction": round(util_interact, 4),
                "sliding_ok": sliding_ok,
            },
            error_codes=errors,
        )

    @classmethod
    def check_wrench_access(
        cls, bolt_diameter_mm: float, wrench_size_mm: float, available_clearance_mm: float,
    ) -> Dict[str, Any]:
        """Acceso de llave de apriete."""
        required = wrench_size_mm * 1.5  # espacio de giro mínimo
        accessible = available_clearance_mm >= required
        return {
            "accessible": accessible,
            "required_clearance_mm": required,
            "error_code": "J9-E011" if not accessible else None,
        }


# ─────────────────────────────────────────────────────────────────────────────
# WeldedJointService — unión soldada entre tramos
# ─────────────────────────────────────────────────────────────────────────────

class WeldedJointService:
    """
    Soldadura preferentemente de taller.
    Obra solo con procedimiento aprobado + field_weld_approved.
    """

    @staticmethod
    def check_field_weld(field_weld: bool, field_weld_approved: bool) -> Optional[str]:
        if field_weld and not field_weld_approved:
            return "J9-E003"
        return None

    @staticmethod
    def static_check(
        D_ext_mm: float, t_wall_mm: float, N_kn: float,
        My_knm: float, Mz_knm: float, T_knm: float,
        fy_mpa: float, fu_mpa: float,
        misalignment_mm: float = 0.0, gamma_M2: float = 1.25,
    ) -> CheckResult:
        """Verificación estática de soldadura a tope penetración total."""
        D_mid = D_ext_mm - t_wall_mm
        A = math.pi * D_mid * t_wall_mm
        I = math.pi / 64.0 * ((D_ext_mm)**4 - (D_ext_mm - 2*t_wall_mm)**4)

        sigma_N = abs(N_kn * 1000.0) / A if A > 0 else 0.0
        M_res = math.hypot(My_knm, Mz_knm) * 1e6  # N·mm
        sigma_M = M_res * (D_ext_mm / 2.0) / I if I > 0 else 0.0
        tau_T = abs(T_knm * 1e6) * (D_ext_mm / 2.0) / (2.0 * I) if I > 0 else 0.0

        # Penalización por desalineación (reducción lineal 5% por mm)
        misalign_penalty = min(misalignment_mm * 0.05, 0.5)
        sigma_total = (sigma_N + sigma_M) * (1.0 + misalign_penalty)

        # Resistencia a penetración total = fy / γM0
        sigma_Rd = fy_mpa / 1.0
        util_static = sigma_total / sigma_Rd

        # Torsión
        tau_Rd = fy_mpa / (math.sqrt(3.0) * 1.0)
        util_tau = tau_T / tau_Rd

        # Von Mises
        util_vm = math.sqrt((sigma_total / sigma_Rd)**2 + 3.0 * (tau_T / tau_Rd)**2)

        util = max(util_static, util_tau, util_vm)
        ndt = "UT/RT" if util > 0.8 else "VT/PT"

        errors: List[str] = []
        if util > 1.0:
            errors.append("J9-E007")

        return CheckResult(
            status=JointCheckStatus.FAIL if errors else JointCheckStatus.PASS,
            utilization=util,
            governing_rule="EC3-1-8 §4 / EN 40-3-3 §7.5",
            intermediate_values={
                "sigma_N_mpa": round(sigma_N, 2),
                "sigma_M_mpa": round(sigma_M, 2),
                "tau_T_mpa": round(tau_T, 2),
                "sigma_total_mpa": round(sigma_total, 2),
                "misalignment_penalty_pct": round(misalign_penalty * 100, 1),
                "ndt_required": ndt,
                "util_vm": round(util_vm, 4),
            },
            error_codes=errors,
        )

    @staticmethod
    def fatigue_check(weld_category: str, delta_sigma_mpa: float, n_cycles: int) -> CheckResult:
        """Verificación de fatiga del cordón (EC3-1-9)."""
        # Capacidades FAT simplificadas
        fat_table = {
            "160": 160.0, "140": 140.0, "125": 125.0, "112": 112.0,
            "100": 100.0, "90": 90.0, "80": 80.0, "71": 71.0, "63": 63.0,
        }
        delta_sigma_C = fat_table.get(weld_category, 71.0)
        N_ref = 2e6
        # Curva S-N simplificada
        N_R = N_ref * (delta_sigma_C / delta_sigma_mpa) ** 3 if delta_sigma_mpa > 0 else float("inf")
        damage = n_cycles / N_R if N_R > 0 else 0.0
        util = min(damage, 9.99)

        errors: List[str] = []
        if damage > 1.0:
            errors.append("J9-E009")

        return CheckResult(
            status=JointCheckStatus.FAIL if errors else JointCheckStatus.PASS,
            utilization=util,
            governing_rule=f"EC3-1-9 FAT {weld_category}",
            intermediate_values={
                "delta_sigma_C": delta_sigma_C,
                "N_R": N_R,
                "damage": round(damage, 4),
            },
            error_codes=errors,
        )


# ─────────────────────────────────────────────────────────────────────────────
# SleeveJointService — manguito
# ─────────────────────────────────────────────────────────────────────────────

class SleeveJointService:

    @staticmethod
    def check_torsion_transfer(
        length_mm: float, outer_d_mm: float, inner_d_mm: float,
        T_knm: float, fy_mpa: float,
    ) -> CheckResult:
        """Transmisión de torsión por fricción/soldadura del manguito."""
        t = (outer_d_mm - inner_d_mm) / 2.0
        D_mid = (outer_d_mm + inner_d_mm) / 2.0
        # Sección anular
        J = math.pi / 32.0 * (outer_d_mm**4 - inner_d_mm**4)
        tau = abs(T_knm * 1e6) * (outer_d_mm / 2.0) / J if J > 0 else 0.0
        tau_Rd = fy_mpa / math.sqrt(3.0)
        util = tau / tau_Rd if tau_Rd > 0 else 0.0

        errors: List[str] = []
        if util > 1.0:
            errors.append("J9-E007")

        return CheckResult(
            status=JointCheckStatus.FAIL if errors else JointCheckStatus.PASS,
            utilization=util,
            governing_rule="EC3-1-1 §6.2.7 / Modelo manguito J9-MAN",
            intermediate_values={"tau_mpa": round(tau, 2), "tau_Rd_mpa": round(tau_Rd, 2)},
            error_codes=errors,
        )

    @staticmethod
    def check_exterior_water(sleeve_type: str, exterior_water_retained: bool) -> Dict[str, Any]:
        """Manguito exterior con agua retenida → bloqueo."""
        if sleeve_type == "EXTERIOR" and exterior_water_retained:
            return {"blocked": True, "error_code": "J9-E012"}
        return {"blocked": False, "error_code": None}


# ─────────────────────────────────────────────────────────────────────────────
# HybridInterfaceService — interfaces entre materiales
# ─────────────────────────────────────────────────────────────────────────────

class HybridInterfaceService:

    @staticmethod
    def check_galvanic(
        hybrid_type: str, isolator_type: Optional[str],
        galvanic_area_ratio: Optional[float] = None,
    ) -> CheckResult:
        """Verifica compatibilidad galvánica y aislamiento."""
        errors: List[str] = []
        if hybrid_type == "STEEL_ALUMINIUM":
            if not isolator_type:
                errors.append("J9-E014")
            if galvanic_area_ratio and galvanic_area_ratio > 10.0:
                errors.append("J9-E014")  # área catódica excesiva

        status = JointCheckStatus.BLOCKED if "J9-E014" in errors else JointCheckStatus.PASS
        return CheckResult(
            status=status,
            utilization=1.0 if errors else 0.0,
            governing_rule="EN 40-5 §8 / ISO 8044 (corrosión galvánica)",
            error_codes=errors,
        )

    @staticmethod
    def check_thermal(
        delta_T_k: float,
        E_steel: float = 210000.0, alpha_steel: float = 12e-6,
        E_alu: float = 70000.0, alpha_alu: float = 23e-6,
        fy_alu: float = 160.0,
    ) -> CheckResult:
        """Tensiones secundarias por diferencia de dilatación."""
        # Esfuerzo diferencial simplificado (bimetálico)
        delta_alpha = alpha_alu - alpha_steel
        # Compatible: E_s y E_a en serie
        E_eq = (E_steel * E_alu) / (E_steel + E_alu)
        sigma_thermal = E_eq * delta_alpha * delta_T_k
        util = abs(sigma_thermal) / fy_alu if fy_alu > 0 else 0.0

        errors: List[str] = []
        if util > 1.0:
            errors.append("J9-E007")

        return CheckResult(
            status=JointCheckStatus.FAIL if errors else JointCheckStatus.PASS,
            utilization=util,
            governing_rule="EC9-1-1 §5.3 (tensiones térmicas)",
            intermediate_values={
                "delta_alpha": delta_alpha,
                "sigma_thermal_mpa": round(sigma_thermal, 2),
                "E_eq_mpa": round(E_eq, 2),
            },
            error_codes=errors,
        )

    @staticmethod
    def check_concrete_bearing(
        N_kn: float, bearing_area_mm2: float, fck_mpa: float,
        family_approved: bool, grout_hardened: bool,
    ) -> CheckResult:
        """Aplastamiento local en interfaz metal-hormigón."""
        errors: List[str] = []
        if not family_approved:
            errors.append("J9-E015")
        if not grout_hardened:
            errors.append("J9-E007")  # inestabilidad temporal

        fcd = fck_mpa / 1.5
        bearing_stress = abs(N_kn * 1000.0) / bearing_area_mm2 if bearing_area_mm2 > 0 else 0.0
        # EC2 §6.7 aplastamiento
        f_cd_bearing = fcd * min(math.sqrt(1.5), 3.0)
        util = bearing_stress / f_cd_bearing if f_cd_bearing > 0 else 0.0

        if util > 1.0:
            errors.append("J9-E007")

        return CheckResult(
            status=JointCheckStatus.BLOCKED if "J9-E015" in errors else (
                JointCheckStatus.FAIL if util > 1.0 else JointCheckStatus.PASS),
            utilization=util,
            governing_rule="EC2 §6.7 (aplastamiento) + J9-HOR",
            intermediate_values={
                "bearing_stress_mpa": round(bearing_stress, 3),
                "f_cd_bearing_mpa": round(f_cd_bearing, 3),
                "family_approved": family_approved,
                "grout_hardened": grout_hardened,
            },
            error_codes=errors,
        )


# ─────────────────────────────────────────────────────────────────────────────
# JointOptimizer — optimización multiobjetivo (Pareto)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class JointParetoCandidate:
    joint_type: str
    template_ref: Optional[str]
    cost_eur: float
    mass_kg: float
    co2_kg: float
    assembly_complexity: float   # 0-10
    risk_score: float            # 0-1
    logistics_score: float       # 0-1
    durability_score: float      # 0-1
    feasible: bool = True
    discard_reason: Optional[str] = None
    utilization_max: float = 0.0


class JointOptimizer:

    @staticmethod
    def is_dominated(a: JointParetoCandidate, b: JointParetoCandidate) -> bool:
        """¿Está 'a' dominado por 'b'? (3 objetivos: coste, masa, CO₂)"""
        return (b.cost_eur <= a.cost_eur and
                b.mass_kg <= a.mass_kg and
                b.co2_kg <= a.co2_kg and
                (b.cost_eur < a.cost_eur or b.mass_kg < a.mass_kg or b.co2_kg < a.co2_kg))

    @classmethod
    def build_pareto(cls, candidates: List[JointParetoCandidate]) -> List[JointParetoCandidate]:
        """Frente de Pareto (coste / masa / CO₂), solo candidatos factibles."""
        feasible = [c for c in candidates if c.feasible]
        pareto: List[JointParetoCandidate] = []
        for a in feasible:
            if not any(cls.is_dominated(a, b) for b in feasible if b is not a):
                pareto.append(a)
        return pareto

    @classmethod
    def select_solutions(
        cls, pareto: List[JointParetoCandidate],
    ) -> Dict[str, Optional[JointParetoCandidate]]:
        """4 soluciones: min_cost, min_weight, min_co2, balanced."""
        if not pareto:
            return {"min_cost": None, "min_weight": None, "min_co2": None, "balanced": None}

        def balanced_score(c: JointParetoCandidate) -> float:
            costs = [p.cost_eur for p in pareto]
            masses = [p.mass_kg for p in pareto]
            co2s = [p.co2_kg for p in pareto]
            c_n = (c.cost_eur - min(costs)) / (max(costs) - min(costs) + 1e-9)
            w_n = (c.mass_kg - min(masses)) / (max(masses) - min(masses) + 1e-9)
            co2_n = (c.co2_kg - min(co2s)) / (max(co2s) - min(co2s) + 1e-9)
            return c_n + w_n + co2_n

        return {
            "min_cost": min(pareto, key=lambda c: c.cost_eur),
            "min_weight": min(pareto, key=lambda c: c.mass_kg),
            "min_co2": min(pareto, key=lambda c: c.co2_kg),
            "balanced": min(pareto, key=balanced_score),
        }

    @classmethod
    def rank(
        cls,
        candidates: List[JointParetoCandidate],
        weights: Optional[Dict[str, float]] = None,
    ) -> List[JointParetoCandidate]:
        """Ranking por función de puntuación normalizada."""
        w = weights or {
            "cost": 0.3, "weight": 0.15, "co2": 0.15,
            "assembly": 0.15, "risk": 0.1, "logistics": 0.1, "durability": 0.05,
        }
        feasible = [c for c in candidates if c.feasible and c.utilization_max <= 1.0]
        if not feasible:
            return []

        costs = [c.cost_eur for c in feasible]
        masses = [c.mass_kg for c in feasible]
        co2s = [c.co2_kg for c in feasible]
        compl = [c.assembly_complexity for c in feasible]

        def _norm(v: float, vals: List[float]) -> float:
            lo, hi = min(vals), max(vals)
            return (v - lo) / (hi - lo + 1e-9)

        def score(c: JointParetoCandidate) -> float:
            return (w.get("cost", 0.3) * _norm(c.cost_eur, costs) +
                    w.get("weight", 0.15) * _norm(c.mass_kg, masses) +
                    w.get("co2", 0.15) * _norm(c.co2_kg, co2s) +
                    w.get("assembly", 0.15) * _norm(c.assembly_complexity, compl) +
                    w.get("risk", 0.1) * c.risk_score +
                    w.get("logistics", 0.1) * c.logistics_score +
                    w.get("durability", 0.05) * (1.0 - c.durability_score))

        return sorted(feasible, key=score)


# ─────────────────────────────────────────────────────────────────────────────
# JointNormativeClassifier — 7 pasos bloqueantes → tipo de unión
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class NormativeClassResult:
    joint_type: JointType
    blocked: bool
    maturity: JointMaturityLevel
    input_hash: str
    error_codes: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


class JointNormativeClassifier:

    @classmethod
    def classify(
        cls,
        inside_domain: bool,
        family_tested: bool,
        material_compatible: bool,
        field_weld_requested: bool,
        concrete_family_approved: bool,
        hybrid_isolated: bool,
        exception_approved: bool,
        piece_exceeds_12m: bool = False,
        forbidden_zone: bool = False,
        high_torsion: bool = False,
        demountable: bool = False,
        is_hybrid: bool = False,
        is_concrete: bool = False,
        is_telescopic: bool = True,
    ) -> NormativeClassResult:
        errors: List[str] = []
        notes: List[str] = []

        # Paso 1: longitud > 12m sin excepción
        if piece_exceeds_12m and not exception_approved:
            errors.append("J9-E001")

        # Paso 2: zona prohibida
        if forbidden_zone:
            errors.append("J9-E002")

        # Paso 3: incompatibilidad material
        if not material_compatible:
            errors.append("J9-E003")

        # Paso 4: soldadura de obra
        if field_weld_requested:
            errors.append("J9-E003")

        # Paso 5: hormigón sin familia
        if is_concrete and not concrete_family_approved:
            errors.append("J9-E015")

        # Paso 6: híbrido sin aislamiento
        if is_hybrid and not hybrid_isolated:
            errors.append("J9-E014")

        # Paso 7: fuera de dominio normativo
        if not inside_domain:
            errors.append("J9-E004")
            notes.append("Requiere FEM/ensayo")

        blocked = len(errors) > 0

        # Selección de tipo
        if is_concrete:
            jtype = JointType.J9_HOR
        elif is_hybrid:
            jtype = JointType.J9_HIB
        elif demountable:
            jtype = JointType.J9_BRI
        elif is_telescopic:
            jtype = JointType.J9_TEL
        else:
            jtype = JointType.J9_MAN

        # Madurez
        if family_tested and inside_domain:
            maturity = JointMaturityLevel.V3_TEST
        elif inside_domain:
            maturity = JointMaturityLevel.V1_ANALYTICAL
        else:
            maturity = JointMaturityLevel.V0_DEVELOPMENT

        input_hash = _sha256({
            "domain": inside_domain, "tested": family_tested, "compat": material_compatible,
            "field": field_weld_requested, "conc": is_concrete, "hyb": is_hybrid,
        })

        return NormativeClassResult(jtype, blocked, maturity, input_hash, errors, notes)


# ─────────────────────────────────────────────────────────────────────────────
# AssemblyService — secuencia y validación de montaje
# ─────────────────────────────────────────────────────────────────────────────

class AssemblyService:

    @staticmethod
    def validate_assembly(
        joint_type: str,
        interior_access: bool = True,
        personnel_count: int = 2,
        insertion_force_kn: Optional[float] = None,
        force_limit_kn: Optional[float] = None,
        torque_nm: Optional[float] = None,
    ) -> Dict[str, Any]:
        errors: List[str] = []
        hold_points: List[str] = []
        tools: List[str] = []
        insertion_force_ok = None

        if joint_type in ("J9_BRI", "flanged"):
            if not interior_access:
                errors.append("J9-E011")  # brida interior sin acceso
            tools = ["llave dinamométrica", "calibrador de par", "plantilla de alineación"]
            hold_points = ["verificar par de apriete", "control dimensional brida"]
            if torque_nm:
                hold_points.append(f"par objetivo: {torque_nm:.0f} N·m")

        elif joint_type in ("J9_TEL", "telescopic"):
            tools = ["eslingas", "tensiómetro", "calibre longitud de solape"]
            hold_points = ["medir solape tras inserción", "control de alineación angular"]
            if insertion_force_kn is not None and force_limit_kn is not None:
                insertion_force_ok = insertion_force_kn <= force_limit_kn
                if not insertion_force_ok:
                    errors.append("J9-E011")

        elif joint_type in ("J9_SOL", "welded"):
            tools = ["equipo soldadura", "galgas END", "control dimensional"]
            hold_points = ["inspección visual VT", "END por criticidad", "control distorsión"]

        return {
            "feasible": len(errors) == 0,
            "hold_points": hold_points,
            "tools_required": tools,
            "insertion_force_ok": insertion_force_ok,
            "access_ok": interior_access or joint_type in ("J9_TEL", "J9_SOL"),
            "error_codes": errors,
        }
