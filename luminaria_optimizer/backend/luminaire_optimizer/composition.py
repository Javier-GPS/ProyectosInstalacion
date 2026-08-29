"""Azimuthal composition of repeated group photometries."""
from __future__ import annotations

from .hl2x import LuminaireOperatingPoint
from .ldt import LdtPhotometry, LampSet

# Default equal azimuth sectors mirrored about the transverse road plane C=90°.
DEFAULT_GROUP_ANGLES_DEG = (11.25, 33.75, 56.25, 78.75, 101.25, 123.75, 146.25, 168.75)
# The supplied group LDT is referenced 90° counter-clockwise from the road
# convention used by the complete luminaire. In the plan-view display, positive
# C therefore moves clockwise.
GROUP_C_ROTATION_DEG = 90.0


def group_c_rotation_deg(group_ldt: LdtPhotometry) -> float:
    """Return the source-specific C rotation, preserving the legacy default."""
    raw = group_ldt.metadata.get("group_c_rotation_deg")
    if raw is None:
        return GROUP_C_ROTATION_DEG
    try:
        return float(raw)
    except ValueError:
        return GROUP_C_ROTATION_DEG


def scale_ldt_runtime(ldt: LdtPhotometry, flux_lm: float, power_w: float) -> LdtPhotometry:
    """Return the same normalized LDT with runtime flux and power metadata."""
    flux_factor = flux_lm / ldt.flux_lm if ldt.flux_lm > 0 else 0.0
    power_factor = power_w / ldt.power_w if ldt.power_w > 0 else 0.0
    fallback_power = power_w / len(ldt.lamp_sets) if ldt.lamp_sets else 0.0
    lamp_sets = [
        LampSet(
            item.number_of_lamps, item.lamp_type, item.flux_lm * flux_factor,
            item.color, item.cri, item.wattage_w * power_factor if ldt.power_w > 0 else fallback_power,
        )
        for item in ldt.lamp_sets
    ]
    return LdtPhotometry(
        company=ldt.company,
        name=f"{ldt.name} · runtime",
        c_angles_deg=list(ldt.c_angles_deg),
        gamma_angles_deg=list(ldt.gamma_angles_deg),
        intensities_cd_per_klm=[list(row) for row in ldt.intensities_cd_per_klm],
        lamp_sets=lamp_sets,
        symmetry=ldt.symmetry,
        conversion=ldt.conversion,
        lorl_percent=ldt.lorl_percent,
        dimensions_mm=ldt.dimensions_mm,
        metadata={**ldt.metadata, "runtime_scaled": "true"},
    )
def compose_luminaire(group_ldt: LdtPhotometry, operating_point: LuminaireOperatingPoint, *, angles_deg: tuple[float, ...] | None = None, c_step_deg: float = 1.0, gamma_step_deg: float = 1.0, cct_k: int | None = None, cri: int | None = None, symmetric: bool = False) -> LdtPhotometry:
    if angles_deg is None:
        angles_deg = tuple((index + 0.5) * 180.0 / len(operating_point.groups) for index in range(len(operating_point.groups)))
    if len(angles_deg) != len(operating_point.groups):
        raise ValueError("group angle count does not match operating point")
    c_count = int(round(360.0 / c_step_deg))
    g_count = int(round(90.0 / gamma_step_deg)) + 1
    c_angles = [index * c_step_deg for index in range(c_count)]
    gamma_angles = [index * gamma_step_deg for index in range(g_count)]
    total_flux = operating_point.total_flux_lm
    c_rotation = group_c_rotation_deg(group_ldt)
    matrix: list[list[float]] = []
    def total_at(c: float, gamma: float) -> float:
        if not 0.0 <= c % 360.0 <= 180.0:
            return 0.0
        return sum(
            group_ldt.intensity_cd_per_klm(c - angle - c_rotation, gamma) * point.group_flux_lm / 1000.0
            for angle, point in zip(angles_deg, operating_point.groups)
        )

    for c in c_angles:
        row = []
        for gamma in gamma_angles:
            absolute_cd = total_at(c, gamma)
            if symmetric:
                absolute_cd = 0.5 * (absolute_cd + total_at((180.0 - c) % 360.0, gamma))
            row.append(1000.0 * absolute_cd / total_flux if total_flux > 0 else 0.0)
        matrix.append(row)
    lamp = LampSet(str(len(operating_point.groups) * 3), "LUXEON HL2X 3535", total_flux, f"{cct_k or ''}K", str(cri or ''), operating_point.total_driver_power_w)
    group_count = len(operating_point.groups)
    return LdtPhotometry(
        company="SALVI",
        name=f"SALVI HL2X {group_count}-group calculated",
        c_angles_deg=c_angles,
        gamma_angles_deg=gamma_angles,
        intensities_cd_per_klm=matrix,
        lamp_sets=[lamp],
        symmetry=0,
        conversion=1.0,
        lorl_percent=group_ldt.lorl_percent,
        dimensions_mm=group_ldt.dimensions_mm,
        metadata={
            "source_report": f"Calculated sum of {group_count} azimuthal group LDTs",
            "source_date": "",
            "group_angles_deg": ",".join(map(str, angles_deg)),
            "directional_c0_c180": "true",
            "group_c_rotation_deg": str(c_rotation),
        },
    )
