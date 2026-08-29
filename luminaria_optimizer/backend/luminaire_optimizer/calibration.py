"""Photometric orientation calibration against a reference LDT."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .ldt import LdtPhotometry
from .optical import RayTraceResult
from .ray_photometry import rays_to_ldt


@dataclass(frozen=True)
class OrientationCalibration:
    """Best angular convention found against a reference LDT."""

    c_offset_deg: float
    c_mirror: bool
    gamma_flip: bool
    scale_to_reference: float
    relative_rms_error: float
    evaluated_candidates: int

    def diagnostic(self) -> dict[str, object]:
        return {
            "c_offset_deg": self.c_offset_deg,
            "c_mirror": self.c_mirror,
            "gamma_flip": self.gamma_flip,
            "scale_to_reference": self.scale_to_reference,
            "relative_rms_error": self.relative_rms_error,
            "evaluated_candidates": self.evaluated_candidates,
        }


def calibrate_orientation(
    result: RayTraceResult,
    reference: LdtPhotometry,
    *,
    c_search_step_deg: float = 5.0,
    min_reference_fraction: float = 0.02,
) -> OrientationCalibration:
    """Search C rotation/mirroring and gamma direction against an LDT.

    The reference grid is used for both photometries. A least-squares scale is
    fitted for each candidate because the TM-25 source flux and the reference
    LDT operating point are different; the score therefore measures angular
    shape rather than absolute output.
    """
    reference.validate()
    if c_search_step_deg <= 0 or not np.isclose(360.0 % c_search_step_deg, 0.0):
        raise ValueError("c_search_step_deg must be a positive divisor of 360")
    if len(reference.c_angles_deg) < 2 or len(reference.gamma_angles_deg) < 2:
        raise ValueError("reference LDT has insufficient angular samples")
    c_step_deg = reference.c_angles_deg[1] - reference.c_angles_deg[0]
    gamma_step_deg = reference.gamma_angles_deg[1] - reference.gamma_angles_deg[0]
    reference_grid = np.asarray(reference.intensities_cd_per_klm, dtype=np.float64)
    c_solid_angle = np.radians(c_step_deg)
    gamma_solid_angle = np.asarray([
        np.cos(np.radians(max(0.0, gamma - gamma_step_deg / 2.0)))
        - np.cos(np.radians(min(90.0, gamma + gamma_step_deg / 2.0)))
        for gamma in reference.gamma_angles_deg
    ])
    # Compare integrated angular flux, not raw cd/klm. This avoids making the
    # tiny gamma=0 bin dominate the score because its solid angle is tiny.
    reference_grid = reference_grid * c_solid_angle * gamma_solid_angle[None, :]
    threshold = float(reference_grid.max()) * min_reference_fraction
    mask = reference_grid >= threshold
    target = reference_grid[mask]

    best: OrientationCalibration | None = None
    candidate_count = 0
    for c_mirror in (False, True):
        for gamma_flip in (False, True):
            for offset in np.arange(0.0, 360.0, c_search_step_deg):
                candidate_count += 1
                candidate = rays_to_ldt(
                    result,
                    c_step_deg=c_step_deg,
                    gamma_step_deg=gamma_step_deg,
                    c_offset_deg=float(offset),
                    c_mirror=c_mirror,
                    gamma_flip=gamma_flip,
                )
                candidate_grid = np.asarray(candidate.intensities_cd_per_klm, dtype=np.float64)
                candidate_grid = candidate_grid * c_solid_angle * gamma_solid_angle[None, :]
                values = candidate_grid[mask]
                denominator = float(np.dot(values, values))
                if denominator <= 0:
                    continue
                scale = float(np.dot(values, target) / denominator)
                target_rms = max(float(np.sqrt(np.mean(target ** 2))), 1e-12)
                error = float(np.sqrt(np.mean((scale * values - target) ** 2)) / target_rms)
                current = OrientationCalibration(
                    c_offset_deg=float(offset),
                    c_mirror=c_mirror,
                    gamma_flip=gamma_flip,
                    scale_to_reference=scale,
                    relative_rms_error=error,
                    evaluated_candidates=candidate_count,
                )
                if best is None or current.relative_rms_error < best.relative_rms_error:
                    best = current
    if best is None:
        raise ValueError("no orientation candidate produced usable photometry")
    return best
