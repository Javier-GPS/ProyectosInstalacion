"""Angular conventions shared by ray photometry and visual ray previews."""
from __future__ import annotations

import numpy as np


def direction_angles(
    direction: np.ndarray,
    *,
    c_mirror: bool = False,
    c_offset_deg: float = 0.0,
    gamma_flip: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """Return C/gamma angles using the ray photometry convention.

    C is ``atan2(y, x)``, followed by the optional mirror and offset. Gamma is
    ``acos(z)``. The function accepts one direction or an array of directions.
    """
    direction = np.asarray(direction, dtype=np.float64)
    azimuth = np.degrees(np.arctan2(direction[..., 1], direction[..., 0]))
    if c_mirror:
        azimuth = -azimuth
    azimuth = (azimuth + c_offset_deg) % 360.0
    gamma = np.degrees(np.arccos(np.clip(direction[..., 2], -1.0, 1.0)))
    if gamma_flip:
        gamma = 180.0 - gamma
    return azimuth, gamma
