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
    enforce_c_symmetry: bool = False,
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
    gamma_count = int(round(180.0 / gamma_step_deg)) + 1
    if not math.isclose(c_count * c_step_deg, 360.0, abs_tol=1e-9):
        raise ValueError("c_step_deg must divide 360 degrees")
    if not math.isclose((gamma_count - 1) * gamma_step_deg, 180.0, abs_tol=1e-9):
        raise ValueError("gamma_step_deg must divide 180 degrees")
    if result.input_flux_lm <= 0:
        raise ValueError("ray trace input flux must be positive")

    c_angles = [index * c_step_deg for index in range(c_count)]
    gamma_angles = [index * gamma_step_deg for index in range(gamma_count)]
    flux_bins = np.zeros((c_count, gamma_count), dtype=np.float64)
    solid_angles = np.zeros(gamma_count, dtype=np.float64)
    for gamma_index, gamma_center in enumerate(gamma_angles):
        lower = max(0.0, gamma_center - gamma_step_deg / 2.0)
        upper = min(180.0, gamma_center + gamma_step_deg / 2.0)
        solid_angles[gamma_index] = math.radians(c_step_deg) * (
            math.cos(math.radians(lower)) - math.cos(math.radians(upper))
        )
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
        valid = (gamma >= -1e-9) & (gamma <= 180.0 + 1e-9)
        upper_flux = float(rays[gamma > 90.0 + 1e-9, 6].sum())
        c_indices = np.floor(((azimuth[valid] + c_step_deg / 2.0) % 360.0) / c_step_deg).astype(int)
        gamma_indices = np.floor((gamma[valid] + gamma_step_deg / 2.0) / gamma_step_deg).astype(int)
        gamma_indices = np.clip(gamma_indices, 0, gamma_count - 1)
        weights = rays[valid, 6]
        # A ray sample must not produce isolated one-degree spikes. Spread its
        # flux over immediate angular neighbours, then divide by each bin's
        # solid angle. The normalized kernel preserves total transmitted flux.
        c_kernel = ((-1, 1.0), (0, 2.0), (1, 1.0))
        gamma_kernel = ((-2, 1.0), (-1, 4.0), (0, 6.0), (1, 4.0), (2, 1.0))
        for c_index, gamma_index, weight in zip(c_indices, gamma_indices, weights):
            neighbours = [
                ((c_index + c_offset) % c_count, gamma_index + gamma_offset, c_weight * gamma_weight)
                for c_offset, c_weight in c_kernel
                for gamma_offset, gamma_weight in gamma_kernel
                if 0 <= gamma_index + gamma_offset < gamma_count
            ]
            kernel_total = sum(item[2] for item in neighbours)
            for neighbour_c, neighbour_gamma, kernel_weight in neighbours:
                flux_bins[neighbour_c, neighbour_gamma] += weight * kernel_weight / kernel_total

    matrix = np.divide(
        flux_bins * 1000.0 / result.input_flux_lm,
        solid_angles[None, :],
        out=np.zeros_like(flux_bins),
        where=solid_angles[None, :] > 0,
    )
    if enforce_c_symmetry:
        matrix = _mirror_average_c_planes(c_angles, matrix)

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
            "angular_reconstruction": "flux-preserving triangular kernel: C +/- 5 deg, gamma +/- 2 deg",
            "c_symmetrized": str(enforce_c_symmetry).lower(),
        },
    )


def _mirror_average_c_planes(c_angles: list[float], matrix: np.ndarray) -> np.ndarray:
    """Average C planes mirrored about C90 without changing total flux."""
    result = matrix.copy()
    used: set[int] = set()
    for index, angle in enumerate(c_angles):
        if index in used:
            continue
        mirror = (180.0 - angle) % 360.0
        mirror_index = min(
            range(len(c_angles)),
            key=lambda item: abs(((c_angles[item] - mirror + 180.0) % 360.0) - 180.0),
        )
        used.update((index, mirror_index))
        if mirror_index != index:
            average = 0.5 * (matrix[index] + matrix[mirror_index])
            result[index] = average
            result[mirror_index] = average
    return result
