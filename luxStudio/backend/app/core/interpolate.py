"""Generic linear interpolation helper shared across services and core."""

from typing import Optional


def interpolate(x: float, points: list[tuple[float, float]]) -> Optional[float]:
    """Linear interpolation through ``points``.

    Returns ``None`` for empty input, the single point's y for one-point
    input.  Out-of-range ``x`` extrapolates the first/last segment with
    the same slope (matches the legacy calculator._interpolate behaviour
    so flux factors stay numerically identical).
    """
    if not points:
        return None
    if len(points) == 1:
        return points[0][1]

    pts = sorted(points, key=lambda p: p[0])
    if x <= pts[0][0]:
        return _linear_between(x, pts[0], pts[1])
    if x >= pts[-1][0]:
        return _linear_between(x, pts[-2], pts[-1])

    for left, right in zip(pts, pts[1:]):
        if left[0] <= x <= right[0]:
            return _linear_between(x, left, right)
    return pts[-1][1]


def _linear_between(x: float, left: tuple[float, float], right: tuple[float, float]) -> float:
    x1, y1 = left
    x2, y2 = right
    if abs(x2 - x1) < 1e-9:
        return y1
    return y1 + (y2 - y1) * ((float(x) - x1) / (x2 - x1))
