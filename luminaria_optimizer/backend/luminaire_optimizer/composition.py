"""Azimuthal composition of the eight common group photometries."""
from __future__ import annotations

from .hl2x import LuminaireOperatingPoint
from .ldt import LdtPhotometry, LampSet

# Eight equal azimuth sectors mirrored about the transverse road plane C=90°.
DEFAULT_GROUP_ANGLES_DEG = (11.25, 33.75, 56.25, 78.75, 101.25, 123.75, 146.25, 168.75)


def compose_luminaire(group_ldt: LdtPhotometry, operating_point: LuminaireOperatingPoint, *, angles_deg: tuple[float, ...] = DEFAULT_GROUP_ANGLES_DEG, c_step_deg: float = 1.0, gamma_step_deg: float = 1.0, cct_k: int | None = None, cri: int | None = None, symmetric: bool = False) -> LdtPhotometry:
    if len(angles_deg) != len(operating_point.groups):
        raise ValueError("group angle count does not match operating point")
    c_count = int(round(360.0 / c_step_deg))
    g_count = int(round(90.0 / gamma_step_deg)) + 1
    c_angles = [index * c_step_deg for index in range(c_count)]
    gamma_angles = [index * gamma_step_deg for index in range(g_count)]
    total_flux = operating_point.total_flux_lm
    matrix: list[list[float]] = []
    def total_at(c: float, gamma: float) -> float:
        if not 0.0 <= c % 360.0 <= 180.0:
            return 0.0
        return sum(
            group_ldt.intensity_cd_per_klm(c - angle, gamma) * point.group_flux_lm / 1000.0
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
    return LdtPhotometry(
        company="SALVI",
        name="SALVI HL2X 8-group calculated",
        c_angles_deg=c_angles,
        gamma_angles_deg=gamma_angles,
        intensities_cd_per_klm=matrix,
        lamp_sets=[lamp],
        symmetry=0,
        conversion=1.0,
        lorl_percent=group_ldt.lorl_percent,
        dimensions_mm=group_ldt.dimensions_mm,
        metadata={"source_report": "Calculated sum of eight azimuthal group LDTs", "source_date": "", "group_angles_deg": ",".join(map(str, angles_deg))},
    )
