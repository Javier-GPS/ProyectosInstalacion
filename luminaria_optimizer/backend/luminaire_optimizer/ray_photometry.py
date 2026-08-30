"""Convert sampled transmitted rays into EULUMDAT-compatible photometry."""
from __future__ import annotations

import math

import numpy as np

from .ldt import LampSet, LdtPhotometry
from .optical import RayTraceResult
from .ray_angles import direction_angles


def rays_to_ldt(
    result: RayTraceResult,
    *,
    c_step_deg: float = 5.0,
    gamma_step_deg: float = 1.0,
    c_offset_deg: float = 0.0,
    c_mirror: bool = False,
    gamma_flip: bool = False,
    cct_k: int = 4000,
    cri: int = 70,
) -> LdtPhotometry:
    """Estimate cd/klm from the transmitted ray directions.

    Ray weights are luminous flux values. Each angular bin is divided by its
    solid angle, then normalized to the complete input flux, matching the
    cd/klm convention used by the existing LDT engine. ``c_offset_deg`` keeps
    the ray-file azimuth convention explicit instead of silently rotating it.
    """
    if c_step_deg <= 0 or gamma_step_deg <= 0:
        raise ValueError("angular steps must be positive")
    c_count = int(round(360.0 / c_step_deg))
    gamma_count = int(round(90.0 / gamma_step_deg)) + 1
    if not math.isclose(c_count * c_step_deg, 360.0, abs_tol=1e-9):
        raise ValueError("c_step_deg must divide 360 degrees")
    if not math.isclose((gamma_count - 1) * gamma_step_deg, 90.0, abs_tol=1e-9):
        raise ValueError("gamma_step_deg must divide 90 degrees")
    if result.input_flux_lm <= 0:
        raise ValueError("ray trace input flux must be positive")

    c_angles = [index * c_step_deg for index in range(c_count)]
    gamma_angles = [index * gamma_step_deg for index in range(gamma_count)]
    matrix = np.zeros((c_count, gamma_count), dtype=np.float64)
    rays = result.transmitted_rays
    upper_flux = 0.0
    if rays.size:
        direction = rays[:, 3:6]
        azimuth, gamma = direction_angles(
            direction,
            c_mirror=c_mirror,
            c_offset_deg=c_offset_deg,
            gamma_flip=gamma_flip,
        )
        valid = (gamma >= -1e-9) & (gamma <= 90.0 + 1e-9)
        upper_flux = float(rays[~valid, 6].sum())
        c_indices = np.floor(((azimuth[valid] + c_step_deg / 2.0) % 360.0) / c_step_deg).astype(int)
        gamma_indices = np.floor((gamma[valid] + gamma_step_deg / 2.0) / gamma_step_deg).astype(int)
        gamma_indices = np.clip(gamma_indices, 0, gamma_count - 1)
        weights = rays[valid, 6]
        for c_index, gamma_index, weight in zip(c_indices, gamma_indices, weights):
            gamma_center = gamma_angles[gamma_index]
            lower = max(0.0, gamma_center - gamma_step_deg / 2.0)
            upper = min(90.0, gamma_center + gamma_step_deg / 2.0)
            solid_angle = math.radians(c_step_deg) * (
                math.cos(math.radians(lower)) - math.cos(math.radians(upper))
            )
            if solid_angle > 0:
                matrix[c_index, gamma_index] += weight * 1000.0 / result.input_flux_lm / solid_angle

    lorl = 100.0 * result.transmitted_flux_lm / result.input_flux_lm
    return LdtPhotometry(
        company="SALVI",
        name=f"SALVI HL2Z {result.led_count} LED DOT Monte Carlo",
        c_angles_deg=c_angles,
        gamma_angles_deg=gamma_angles,
        intensities_cd_per_klm=matrix.tolist(),
        lamp_sets=[LampSet(
            str(result.led_count),
            "LUXEON HL2Z 4070",
            result.input_flux_lm,
            f"{cct_k}K",
            str(cri),
            0.0,
        )],
        symmetry=0,
        conversion=1.0,
        lorl_percent=lorl,
        metadata={
            "source_report": "TM-25 ray set traced through STEP lens with CadQuery/OCP [SALVI_GROUP_C_ROTATION=0]",
            "group_c_rotation_deg": "0",
            "ray_count": str(result.traced_ray_count),
            "c_offset_deg": str(c_offset_deg),
            "c_mirror": str(c_mirror),
            "gamma_flip": str(gamma_flip),
            "gamma_gt_90_flux_lm": str(upper_flux),
        },
    )
