import asyncio
import base64
import concurrent.futures
import html
import math
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright
from ..salvi_lighting import build_luminaires

from .ldt_loader import get_photometry
from ..schemas.models import CalculationConfig, CalculationResult
from .geometry import effective_overhang, luminaire_mounting_height
from .i18n import normalize_language, translator
from .report_grids import calculation_config_dict, calculation_grids

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))


def _fmt(value, digits=2, fallback="-"):
    if value is None:
        return fallback
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return fallback


def _safe(value):
    return html.escape(str(value))


def _nice_scale(max_value):
    target = max(400, max_value * 1.08)
    max_r = int(math.ceil(target / 100) * 100)
    # Keep the printed scale stable and readable for roadway luminaire reports.
    return max_r, [100, 200, 300, 400]


def _interp_plane(photometry, c_index):
    c_angles = photometry["C"]
    g_angles = photometry["G"]
    grid = photometry["I"]
    if not c_angles or not g_angles or not grid:
        return [(g, 0.0) for g in range(0, 181, 5)]
    conv = float(photometry.get("conv", 1.0))
    mf_factor = float(photometry.get("mf_factor", 1.0) or 1.0)
    target = c_index % 360
    indexed_angles = [(float(c) % 360, idx) for idx, c in enumerate(c_angles)]
    exact = next((idx for c, idx in indexed_angles if abs(c - target) < 1e-6), None)
    if exact is not None:
        return [(float(g), float(grid[exact][i]) * conv * mf_factor) for i, g in enumerate(g_angles)]

    ordered = sorted(indexed_angles)
    wrapped = ordered + [(ordered[0][0] + 360, ordered[0][1])]
    target_wrapped = target if target >= ordered[0][0] else target + 360
    lower = wrapped[0]
    upper = wrapped[-1]
    for left, right in zip(wrapped, wrapped[1:]):
        if left[0] <= target_wrapped <= right[0]:
            lower, upper = left, right
            break

    span = max(upper[0] - lower[0], 1e-9)
    t = (target_wrapped - lower[0]) / span
    return [
        (float(g), (float(grid[lower[1]][i]) * (1 - t) + float(grid[upper[1]][i]) * t) * conv * mf_factor)
        for i, g in enumerate(g_angles)
    ]


def _closed_plane(plane_a, plane_b):
    forward = [(gamma, value) for gamma, value in plane_a if 0 <= gamma <= 180]
    backward = [(360 - gamma, value) for gamma, value in reversed(plane_b) if 0 < gamma < 180]
    return forward + backward


def renderPolarPhotometrySvg(photometry, t=None, mf_factor: float = 1.0):
    """Render a technical polar photometry SVG with gamma 0 at the bottom.

    ``mf_factor`` is the effective maintenance factor already applied to the
    candela values used in the calculation. It is folded into the curve so
    the report shows exactly the photometry that was used to compute the
    results (rather than the raw LDT).
    """
    t = t or translator("en")
    lum_name = _safe(photometry.get("luminaire_name", "Luminaire"))
    photometry = {**photometry, "mf_factor": mf_factor}
    c0 = _interp_plane(photometry, 0)
    c90 = _interp_plane(photometry, 90)
    c180 = _interp_plane(photometry, 180)
    c270 = _interp_plane(photometry, 270)
    red_curve = _closed_plane(c0, c180)
    blue_curve = _closed_plane(c90, c270)
    max_value = max([v for _, v in red_curve + blue_curve] or [400])
    max_r, radial_ticks = _nice_scale(max_value)

    width, height = 620, 500
    cx, cy, radius = 300, 260, 178

    def xy(angle_deg, value):
        a = math.radians(angle_deg)
        r = radius * max(0.0, min(value / max_r, 1.0))
        # LDT gamma convention: 0 is straight down. In this polar diagram,
        # 0 is drawn at the bottom, 90 at the right and 180 at the top.
        return cx + math.sin(a) * r, cy + math.cos(a) * r

    def path_for(curve):
        if not curve:
            return ""
        pts = [xy(a, v) for a, v in curve]
        d = f"M {pts[0][0]:.1f} {pts[0][1]:.1f}"
        for x, y in pts[1:]:
            d += f" L {x:.1f} {y:.1f}"
        return d + " Z"

    grid = []
    for tick in radial_ticks:
        r = radius * tick / max_r
        grid.append(f'<circle cx="{cx}" cy="{cy}" r="{r:.1f}" fill="none" stroke="#d8dee8" stroke-width="1"/>')
        label_angle = math.radians(78)
        lx = cx + math.sin(label_angle) * r
        ly = cy + math.cos(label_angle) * r
        grid.append(
            f'<rect x="{lx + 5:.1f}" y="{ly - 9:.1f}" width="34" height="15" rx="2" fill="white" opacity="0.94"/>'
            f'<text x="{lx + 9:.1f}" y="{ly + 2:.1f}" font-size="11" fill="#475569">{tick}</text>'
        )
    for angle in range(0, 360, 15):
        x1, y1 = xy(angle, 0)
        x2, y2 = xy(angle, max_r)
        stroke = "#cbd5e1" if angle % 45 == 0 else "#e7ebf1"
        width_line = "1.1" if angle % 45 == 0 else "0.7"
        grid.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{stroke}" stroke-width="{width_line}"/>')

    labels = []
    for angle in range(0, 360, 45):
        lx, ly = xy(angle, max_r * (1.22 if angle == 0 else 1.16))
        labels.append(
            f'<text x="{lx:.1f}" y="{ly + 4:.1f}" text-anchor="middle" font-size="13" font-weight="700" fill="#111827">{angle}&#176;</text>'
        )

    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="{_safe(t('svg.polar_aria'))}">
  <rect x="0" y="0" width="{width}" height="{height}" fill="white"/>
  <text x="28" y="30" font-size="15" font-weight="800" fill="#0f172a">I (cd/klm) - {lum_name}</text>
  <text x="28" y="50" font-size="10.5" fill="#64748b">{_safe(t('svg.photometric_distribution'))}</text>
  <text x="28" y="68" font-size="10.5" fill="#64748b">{_safe(t('svg.radial_scale'))}: {', '.join(str(tick) for tick in radial_ticks[:4])} cd/klm</text>
  <g>{''.join(grid)}</g>
  <path d="{path_for(red_curve)}" fill="none" stroke="#ef4444" stroke-width="2.4" stroke-linejoin="round"/>
  <path d="{path_for(blue_curve)}" fill="none" stroke="#2563eb" stroke-width="2.4" stroke-linejoin="round"/>
  <circle cx="{cx}" cy="{cy}" r="3" fill="#111827"/>
  <g>{''.join(labels)}</g>
  <g transform="translate(430 36)">
    <rect x="0" y="0" width="150" height="54" rx="6" fill="white" stroke="#dbe3ef"/>
    <line x1="14" y1="18" x2="48" y2="18" stroke="#ef4444" stroke-width="2.8"/>
    <text x="58" y="22" font-size="12" font-weight="700" fill="#334155">C0-180</text>
    <line x1="14" y1="38" x2="48" y2="38" stroke="#2563eb" stroke-width="2.8"/>
    <text x="58" y="42" font-size="12" font-weight="700" fill="#334155">C90-270</text>
  </g>
</svg>
"""


def renderRoadPlanSvg(config: CalculationConfig, t=None):
    """Render a proportional top view of the road, lanes, sidewalks and luminaires."""
    t = t or translator(getattr(config, "language", "en"))
    total_w = config.road_width + config.sidewalk_left + config.sidewalk_right
    width, height = 900, 360
    margin_x, road_x = 50, 50
    usable_w = width - 2 * margin_x
    scale_x = usable_w / max(config.spacing, 1)
    scale_y = 190 / max(total_w, 1)
    top = 48
    section_h = total_w * scale_y
    road_y = top + config.sidewalk_left * scale_y
    road_h = config.road_width * scale_y
    right_sidewalk_y = road_y + road_h
    y_center = road_y + road_h / 2

    # --- BACKGROUND ---
    bg  = f'<rect width="{width}" height="{height}" fill="#f8fafc"/>'
    bg += f'<rect x="0" y="0" width="{width}" height="{top + section_h + 12}" fill="#f1f5f9"/>'

    # --- TITLE ---
    title = (
        f'<text x="20" y="22" font-size="15" font-weight="800" fill="#0f172a">{_safe(t("svg.plan_title"))}</text>'
        f'<text x="20" y="36" font-size="9" fill="#64748b">{_safe(t("svg.plan_subtitle"))}</text>'
    )

    # --- OBSERVER ---
    observer_icon = (
        f'<g transform="translate({road_x + 10:.1f} {y_center:.1f})">'
        f'  <circle r="7" fill="#e2e8f0" stroke="#94a3b8" stroke-width="1"/>'
        f'  <circle r="3" fill="#475569"/>'
        f'  <text x="12" y="3" font-size="7" fill="#64748b">O</text>'
        f'</g>'
    )

    # --- SIDEWALKS ---
    s_top = ''
    if config.sidewalk_left > 0:
        swh = config.sidewalk_left * scale_y
        s_top  = f'<rect x="{road_x}" y="{top:.1f}" width="{usable_w}" height="{swh:.1f}" fill="#e2e8f0"/>'
        if config.sidewalk_left > 0.8:
            for sl in range(1, int(config.sidewalk_left) + 1):
                ly = top + sl * scale_y
                s_top += f'<line x1="{road_x}" y1="{ly:.1f}" x2="{road_x + usable_w}" y2="{ly:.1f}" stroke="#cbd5e1" stroke-width="0.5" stroke-dasharray="3 3"/>'
        s_top += f'<text x="{road_x + 8:.1f}" y="{top + swh / 2 + 3:.1f}" font-size="8.5" font-weight="700" fill="#64748b">Acera</text>'

    s_bot = ''
    if config.sidewalk_right > 0:
        swh = config.sidewalk_right * scale_y
        s_bot  = f'<rect x="{road_x}" y="{right_sidewalk_y:.1f}" width="{usable_w}" height="{swh:.1f}" fill="#e2e8f0"/>'
        s_bot += f'<text x="{road_x + 8:.1f}" y="{right_sidewalk_y + swh / 2 + 3:.1f}" font-size="8.5" font-weight="700" fill="#64748b">Acera</text>'

    # --- ROAD SURFACE ---
    road_surf = f'<rect x="{road_x}" y="{road_y:.1f}" width="{usable_w}" height="{road_h:.1f}" fill="#475569"/>'
    # Asphalt texture dots
    for _ in range(80):
        import random
        dx = random.uniform(0, usable_w)
        dy = random.uniform(0, road_h)
        road_surf += f'<circle cx="{road_x + dx:.1f}" cy="{road_y + dy:.1f}" r="0.6" fill="#334155" opacity="0.3"/>'

    # --- EDGE LINES (solid white) ---
    edge_top = f'<line x1="{road_x}" y1="{road_y + 2:.1f}" x2="{road_x + usable_w}" y2="{road_y + 2:.1f}" stroke="white" stroke-width="2.5" stroke-linecap="round"/>'
    edge_bot = f'<line x1="{road_x}" y1="{road_y + road_h - 2:.1f}" x2="{road_x + usable_w}" y2="{road_y + road_h - 2:.1f}" stroke="white" stroke-width="2.5" stroke-linecap="round"/>'

    # --- LANE LINES (dashed) ---
    lane_lines = []
    for i in range(1, config.lanes):
        y = road_y + road_h * i / config.lanes
        lane_lines.append(f'<line x1="{road_x}" y1="{y:.1f}" x2="{road_x + usable_w}" y2="{y:.1f}" stroke="white" stroke-width="1.8" stroke-dasharray="14 10" stroke-linecap="round"/>')

    # --- CENTER LINE (if even lanes, double yellow) ---
    if config.lanes % 2 == 0:
        cx = road_y + road_h * (config.lanes / 2) / config.lanes
        lane_lines.append(f'<line x1="{road_x}" y1="{cx:.1f}" x2="{road_x + usable_w}" y2="{cx:.1f}" stroke="#fbbf24" stroke-width="2" stroke-dasharray="12 8"/>')

    # --- TRAFFIC ARROWS with direction labels ---
    arrows = []
    for i in range(config.lanes):
        ly = road_y + road_h * (i + 0.5) / config.lanes
        direction = -1 if i % 2 == 0 else 1
        ax = road_x + usable_w * (0.30 if direction == 1 else 0.70)
        arrows.append(_traffic_arrow(ax, ly, 50 * direction))
        label = "→" if direction == 1 else "←"
        arrows.append(f'<text x="{ax + (28 if direction == 1 else -28):.1f}" y="{ly + 3:.1f}" font-size="11" font-weight="800" fill="white" text-anchor="middle">{label}</text>')

    # --- LUMINAIRES (improved) ---
    luminaires = _plan_luminaires(config, road_x, road_y, usable_w, road_h, scale_x, scale_y)

    # --- DIMENSION LINE ---
    dim_y = top + section_h + 16
    dims = []
    dims.append(
        f'<line x1="{road_x}" y1="{dim_y:.1f}" x2="{road_x + usable_w}" y2="{dim_y:.1f}" stroke="#334155" stroke-width="1"/>'
        f'<polygon points="{road_x:.1f},{dim_y:.1f} {road_x + 6:.1f},{dim_y - 3.5:.1f} {road_x + 6:.1f},{dim_y + 3.5:.1f}" fill="#334155"/>'
        f'<polygon points="{road_x + usable_w:.1f},{dim_y:.1f} {road_x + usable_w - 6:.1f},{dim_y - 3.5:.1f} {road_x + usable_w - 6:.1f},{dim_y + 3.5:.1f}" fill="#334155"/>'
    )
    # Tick marks
    dims.append(f'<line x1="{road_x}" y1="{dim_y - 4:.1f}" x2="{road_x}" y2="{dim_y + 4:.1f}" stroke="#334155" stroke-width="1"/>')
    dims.append(f'<line x1="{road_x + usable_w}" y1="{dim_y - 4:.1f}" x2="{road_x + usable_w}" y2="{dim_y + 4:.1f}" stroke="#334155" stroke-width="1"/>')
    # Labels
    dims.append(f'<text x="{road_x:.1f}" y="{dim_y + 18:.1f}" text-anchor="middle" font-size="10" font-weight="800" fill="#1e293b">0.00</text>')
    dims.append(f'<text x="{road_x + usable_w:.1f}" y="{dim_y + 18:.1f}" text-anchor="middle" font-size="10" font-weight="800" fill="#1e293b">{config.spacing:.2f} m</text>')
    midx = road_x + usable_w / 2
    dims.append(
        f'<rect x="{midx - 70:.1f}" y="{dim_y - 12:.1f}" width="140" height="16" rx="3" fill="white" opacity="0.92"/>'
        f'<text x="{midx:.1f}" y="{dim_y:.1f}" text-anchor="middle" font-size="9" font-weight="700" fill="#334155">{_safe(t("svg.calculation_spacing", value=f"{config.spacing:.1f}"))}</text>'
    )

    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">
  {bg}
  {title}
  {s_top}
  {road_surf}
  {s_bot}
  {edge_top}
  {edge_bot}
  {''.join(lane_lines)}
  {observer_icon}
  {''.join(arrows)}
  {''.join(luminaires)}
  {''.join(dims)}
</svg>
"""


def _plan_luminaires(config, road_x, road_y, usable_w, road_h, scale_x, scale_y):
    y_pole_left = road_y - config.pole_offset * scale_y
    y_pole_right = road_y + road_h + config.pole_offset * scale_y
    overhang = max(float(config.arm_length), 0) * scale_y
    xs = [road_x, road_x + usable_w]
    items = []

    def lum(x, y, side=1):
        head_y = y + side * overhang
        # Pole shadow
        items.append(f'<circle cx="{x + 1.5:.1f}" cy="{y + 1.5:.1f}" r="5.5" fill="#000" opacity="0.12"/>')
        # Pole cross
        items.append(f'<line x1="{x - 7:.1f}" y1="{y:.1f}" x2="{x + 7:.1f}" y2="{y:.1f}" stroke="#334155" stroke-width="3" stroke-linecap="round"/>')
        items.append(f'<line x1="{x:.1f}" y1="{y - 7:.1f}" x2="{x:.1f}" y2="{y + 7:.1f}" stroke="#334155" stroke-width="3" stroke-linecap="round"/>')
        # Pole dot
        items.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#1e293b"/>')
        items.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2" fill="#475569"/>')
        # Arm to head
        items.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x:.1f}" y2="{head_y:.1f}" stroke="#334155" stroke-width="2.5" stroke-linecap="round"/>')
        # Head - modern rectangle with glow
        items.append(f'<rect x="{x - 14:.1f}" y="{head_y - 6:.1f}" width="28" height="12" rx="3" fill="#1e293b"/>')
        items.append(f'<rect x="{x - 11:.1f}" y="{head_y - 3:.1f}" width="22" height="6" rx="1.5" fill="#38bdf8" opacity="0.85"/>')
        items.append(f'<line x1="{x - 14:.1f}" y1="{head_y:.1f}" x2="{x + 14:.1f}" y2="{head_y:.1f}" stroke="#60a5fa" stroke-width="0.5" opacity="0.4"/>')

    if config.arrangement in ("Bilateral", "Bilateral Alternada"):
        for x in xs:
            if config.pole_side == "right":
                lum(x, y_pole_right, -1)
                lum(x, y_pole_left, 1)
            else:
                lum(x, y_pole_left, 1)
                lum(x, y_pole_right, -1)
    elif config.arrangement == "Central Doble":
        for x in xs:
            lum(x, road_y + road_h / 2, -1)
            lum(x, road_y + road_h / 2, 1)
    elif config.arrangement == "En Isleta":
        for x in xs:
            lum(x, road_y + road_h / 2, 1)
    else:
        for x in xs:
            if config.pole_side == "right":
                lum(x, y_pole_right, -1)
            else:
                lum(x, y_pole_left, 1)
    return items


def _traffic_arrow(x, y, length):
    x2 = x + length
    head = 9 if length > 0 else -9
    return (
        f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x2:.1f}" y2="{y:.1f}" stroke="#f8fafc" stroke-width="2.2"/>'
        f'<polygon points="{x2:.1f},{y:.1f} {x2 - head:.1f},{y - 6:.1f} {x2 - head:.1f},{y + 6:.1f}" fill="#f8fafc"/>'
    )


def _dimension(x1, y1, x2, y2, label, vertical=False):
    if vertical:
        mid_y = (y1 + y2) / 2
        return (
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x1:.1f}" y2="{y2:.1f}" stroke="#334155" stroke-width="1"/>'
            f'<line x1="{x1 - 5:.1f}" y1="{y1:.1f}" x2="{x1 + 5:.1f}" y2="{y1:.1f}" stroke="#334155" stroke-width="1"/>'
            f'<line x1="{x1 - 5:.1f}" y1="{y2:.1f}" x2="{x1 + 5:.1f}" y2="{y2:.1f}" stroke="#334155" stroke-width="1"/>'
            f'<text x="{x1 - 8:.1f}" y="{mid_y:.1f}" transform="rotate(-90 {x1 - 8:.1f} {mid_y:.1f})" text-anchor="middle" font-size="11" font-weight="700" fill="#334155">{_safe(label)}</text>'
        )
    mid_x = (x1 + x2) / 2
    return (
        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#334155" stroke-width="1"/>'
        f'<polygon points="{x1:.1f},{y1:.1f} {x1 + 7:.1f},{y1 - 4:.1f} {x1 + 7:.1f},{y1 + 4:.1f}" fill="#334155"/>'
        f'<polygon points="{x2:.1f},{y2:.1f} {x2 - 7:.1f},{y2 - 4:.1f} {x2 - 7:.1f},{y2 + 4:.1f}" fill="#334155"/>'
        f'<text x="{mid_x:.1f}" y="{y1 + 17:.1f}" text-anchor="middle" font-size="11" font-weight="700" fill="#334155">{_safe(label)}</text>'
    )


def renderRoadSectionSvg(config: CalculationConfig, t=None):
    """Render a technical transverse section with dimensions, arm, tilt and road proportions."""
    t = t or translator(getattr(config, "language", "en"))
    total_w = config.road_width + config.sidewalk_left + config.sidewalk_right
    scale_x = 600 / max(total_w, 1)
    left = 150
    ground_y = 218
    road_left = left + config.sidewalk_left * scale_x
    road_w = config.road_width * scale_x
    side_sign = -1 if config.pole_side == "right" else 1
    road_edge_x = road_left + road_w if config.pole_side == "right" else road_left
    pole_y_offset = config.pole_offset * scale_x
    pole_x = road_edge_x - side_sign * pole_y_offset
    pole_top = 76
    pole_h_px = ground_y - pole_top
    arm_px = side_sign * max(float(config.arm_length), 0) * scale_x
    head_x = pole_x + arm_px
    head_y = pole_top
    tilt_rad = math.radians(config.tilt)
    head_len, head_h = 46, 12
    head_angle = -config.tilt if side_sign == 1 else 180 + config.tilt
    total_right = left + total_w * scale_x

    def dim_h(x1, x2, y, label, label_y=None, box_w=104):
        label_y = y - 5 if label_y is None else label_y
        mid = (x1 + x2) / 2
        return (
            f'<line x1="{x1:.1f}" y1="{y:.1f}" x2="{x2:.1f}" y2="{y:.1f}" stroke="#334155" stroke-width="1"/>'
            f'<polygon points="{x1:.1f},{y:.1f} {x1 + 6:.1f},{y - 3.5:.1f} {x1 + 6:.1f},{y + 3.5:.1f}" fill="#334155"/>'
            f'<polygon points="{x2:.1f},{y:.1f} {x2 - 6:.1f},{y - 3.5:.1f} {x2 - 6:.1f},{y + 3.5:.1f}" fill="#334155"/>'
            f'<rect x="{mid - box_w / 2:.1f}" y="{label_y - 10:.1f}" width="{box_w}" height="14" rx="3" fill="#ffffff" opacity="0.9"/>'
            f'<text x="{mid:.1f}" y="{label_y:.1f}" text-anchor="middle" font-size="8.8" font-weight="800" fill="#0f172a">{_safe(label)}</text>'
        )

    def label_box(x, y, label, color="#0f172a", fill="#ffffff", anchor="middle"):
        w = max(54, len(label) * 5.1)
        left_x = x - w / 2 if anchor == "middle" else x
        text_x = x if anchor == "middle" else x + 6
        return (
            f'<rect x="{left_x:.1f}" y="{y - 11:.1f}" width="{w:.1f}" height="15" rx="3" fill="{fill}" opacity="0.94"/>'
            f'<text x="{text_x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-size="8.8" font-weight="800" fill="{color}">{_safe(label)}</text>'
        )

    def dim_v(x, y1, y2, label):
        mid = (y1 + y2) / 2
        return (
            f'<line x1="{x:.1f}" y1="{y1:.1f}" x2="{x:.1f}" y2="{y2:.1f}" stroke="#334155" stroke-width="1"/>'
            f'<line x1="{x - 5:.1f}" y1="{y1:.1f}" x2="{x + 5:.1f}" y2="{y1:.1f}" stroke="#334155" stroke-width="1"/>'
            f'<line x1="{x - 5:.1f}" y1="{y2:.1f}" x2="{x + 5:.1f}" y2="{y2:.1f}" stroke="#334155" stroke-width="1"/>'
            f'<rect x="{x - 57:.1f}" y="{mid - 7:.1f}" width="96" height="14" rx="3" fill="#ffffff" opacity="0.9" transform="rotate(-90 {x - 9:.1f} {mid:.1f})"/>'
            f'<text x="{x - 9:.1f}" y="{mid + 3:.1f}" transform="rotate(-90 {x - 9:.1f} {mid:.1f})" text-anchor="middle" font-size="8.8" font-weight="800" fill="#0f172a">{_safe(label)}</text>'
        )

    # lane marks (drawn on curb front face)
    lanes = []
    curb_bottom = ground_y + 16
    for i in range(1, config.lanes):
        x = road_left + road_w * i / config.lanes
        lanes.append(f'<line x1="{x:.1f}" y1="{ground_y + 10:.1f}" x2="{x:.1f}" y2="{curb_bottom:.1f}" stroke="white" stroke-width="1.4" stroke-dasharray="5 4"/>')

    component_y = curb_bottom + 18
    dims = [
        dim_h(road_left, road_left + road_w, component_y, f"Calzada {config.road_width:.1f} m", component_y - 5),
        dim_h(left, total_right, curb_bottom + 36, f"Ancho total {total_w:.1f} m"),
        dim_v(pole_x - 50, pole_top, ground_y, f"Poste {config.height:.1f} m"),
    ]
    if config.sidewalk_left > 0:
        dims.append(dim_h(left, road_left, component_y, f"Acera {config.sidewalk_left:.1f} m", component_y - 5, 78))
    if config.sidewalk_right > 0:
        dims.append(dim_h(road_left + road_w, total_right, component_y, f"Acera {config.sidewalk_right:.1f} m", component_y - 5, 78))
    if config.arm_length > 0:
        dims.append(dim_h(pole_x, head_x, pole_top - 18, f"Brazo {config.arm_length:.1f} m", pole_top - 22))
    if config.pole_offset > 0:
        dims.append(dim_h(pole_x, road_edge_x, ground_y - 12, f"Retranqueo {config.pole_offset:.2f} m", ground_y - 16, 104))
    else:
        dims.append(label_box(pole_x + side_sign * 58, ground_y - 15, "Retranqueo 0.00 m", "#334155", "#ffffff"))
    tilt_label_x = (pole_x + head_x) / 2
    tilt_label_y = max(pole_top + 22, head_y + 24)
    dims.append(label_box(tilt_label_x, tilt_label_y, f"Inclinacion {config.tilt:.0f}°", "#ea580c", "#fff7ed"))

    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 290">
  <defs>
    <linearGradient id="sky1" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#f8fafc"/>
      <stop offset="100%" stop-color="#e2e8f0"/>
    </linearGradient>
    <linearGradient id="poleG" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#334155"/>
      <stop offset="30%" stop-color="#475569"/>
      <stop offset="70%" stop-color="#475569"/>
      <stop offset="100%" stop-color="#334155"/>
    </linearGradient>
    <linearGradient id="roadTop" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#5c6a7a"/>
      <stop offset="100%" stop-color="#475569"/>
    </linearGradient>
    <filter id="sd" x="-50%" y="-50%" width="200%" height="200%">
      <feDropShadow dx="1.5" dy="1.5" stdDeviation="1" flood-opacity="0.12"/>
    </filter>
  </defs>

  <rect width="900" height="290" fill="url(#sky1)"/>
  <text x="24" y="26" font-size="15" font-weight="800" fill="#0f172a">{_safe(t('svg.section_title'))}</text>
  <text x="24" y="40" font-size="9" fill="#64748b">{_safe(t('svg.section_subtitle'))}</text>

  <!-- road thickness / curb -->
  <rect x="{left:.1f}" y="{ground_y:.1f}" width="{config.sidewalk_left * scale_x:.1f}" height="16" fill="#9ca3af"/>
  <rect x="{road_left:.1f}" y="{ground_y:.1f}" width="{road_w:.1f}" height="16" fill="#4b5563"/>
  <rect x="{road_left + road_w:.1f}" y="{ground_y:.1f}" width="{config.sidewalk_right * scale_x:.1f}" height="16" fill="#9ca3af"/>

  <!-- road surface -->
  <rect x="{road_left:.1f}" y="{ground_y - 8:.1f}" width="{road_w:.1f}" height="8" fill="url(#roadTop)"/>

  <!-- sidewalk surfaces -->
  <rect x="{left:.1f}" y="{ground_y - 4:.1f}" width="{config.sidewalk_left * scale_x:.1f}" height="4" fill="#cbd5e1"/>
  <rect x="{road_left + road_w:.1f}" y="{ground_y - 4:.1f}" width="{config.sidewalk_right * scale_x:.1f}" height="4" fill="#cbd5e1"/>

  <!-- curb top edge -->
  <line x1="{left:.1f}" y1="{ground_y:.1f}" x2="{left + total_w * scale_x:.1f}" y2="{ground_y:.1f}" stroke="#94a3b8" stroke-width="1"/>
  <line x1="{left:.1f}" y1="{curb_bottom:.1f}" x2="{left + total_w * scale_x:.1f}" y2="{curb_bottom:.1f}" stroke="#64748b" stroke-width="1"/>

  {''.join(lanes)}

  <!-- pole -->
  <rect x="{pole_x - 3:.1f}" y="{pole_top:.1f}" width="6" height="{pole_h_px:.1f}" fill="url(#poleG)" rx="2"/>

  <!-- pole base -->
  <rect x="{pole_x - 12:.1f}" y="{ground_y - 4:.1f}" width="24" height="6" rx="1.5" fill="#334155"/>
  <rect x="{pole_x - 10:.1f}" y="{ground_y + 2:.1f}" width="20" height="4" rx="1" fill="#1e293b" opacity="0.5"/>

  <!-- arm -->
  <line x1="{pole_x:.1f}" y1="{pole_top:.1f}" x2="{head_x:.1f}" y2="{head_y:.1f}" stroke="#1e293b" stroke-width="4" stroke-linecap="round"/>

  <!-- luminaire head -->
  <g transform="translate({head_x:.1f} {head_y:.1f}) rotate({head_angle:.1f})">
    <rect x="{-head_len / 2:.1f}" y="{-head_h / 2:.1f}" width="{head_len}" height="{head_h}" rx="4" fill="#1e293b"/>
    <rect x="{-head_len / 2 + 3:.1f}" y="{-head_h / 2 + 2:.1f}" width="{head_len - 6}" height="{head_h - 4}" rx="2" fill="none" stroke="#38bdf8" stroke-width="0.4" opacity="0.5"/>
  </g>
  <text x="{head_x + side_sign * 34:.1f}" y="{head_y + 4:.1f}" text-anchor="{'start' if side_sign == 1 else 'end'}" font-size="8.5" font-weight="700" fill="#334155">Luminaria</text>

  <!-- tilt arc -->
  <line x1="{pole_x:.1f}" y1="{pole_top:.1f}" x2="{pole_x + side_sign * 50:.1f}" y2="{pole_top:.1f}" stroke="#94a3b8" stroke-width="0.6" stroke-dasharray="3 3"/>
  <path d="M {pole_x + side_sign * 28:.1f} {pole_top:.1f} A 28 28 0 0 {1 if config.tilt >= 0 else 0} {pole_x + side_sign * 28 * math.cos(tilt_rad):.1f} {pole_top - 28 * math.sin(tilt_rad):.1f}" fill="none" stroke="#ea580c" stroke-width="1.3" stroke-linecap="round"/>

  {''.join(dims)}
</svg>
"""


def _visible_luminaires(config: CalculationConfig, photometry, flux_scale):
    cfg = calculation_config_dict(config)
    luminaires = build_luminaires(cfg, photometry, flux_scale=flux_scale)
    margin = max(config.spacing * 0.02, 0.5)
    return [
        lum for lum in luminaires
        if -margin <= lum.x0 <= config.spacing + margin
    ]


def _visible_pole_positions(config: CalculationConfig):
    spacing = float(config.spacing)
    margin = max(spacing * 0.02, 0.5)
    pole_side = str(config.pole_side or "left").lower()
    left, right, centre = 0.0, float(config.road_width), float(config.road_width) / 2.0

    if config.arrangement == "Bilateral":
        poles = [(0.0, left), (0.0, right)]
    elif config.arrangement == "Bilateral Alternada":
        first = right if pole_side == "right" else left
        second = left if first == right else right
        poles = [(0.0, first), (spacing / 2.0, second)]
    elif config.arrangement in ("Central Doble", "En Isleta"):
        poles = [(0.0, centre)]
    else:
        poles = [(0.0, right if pole_side == "right" else left)]

    return [
        (k * spacing + x_offset, y)
        for k in range(-5, 6)
        for x_offset, y in poles
        if -margin <= k * spacing + x_offset <= spacing + margin
    ]


def _isoline_luminaire_markers(config, photometry, flux_scale, sx, sy, y_min, y_max):
    markers = []
    for pole_x, pole_y in _visible_pole_positions(config):
        if y_min <= pole_y <= y_max:
            x, y = sx(pole_x), sy(pole_y)
            markers.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6.4" fill="#111827" stroke="white" stroke-width="1.8"/>')
            markers.append(f'<path d="M {x - 12:.1f} {y:.1f} L {x + 12:.1f} {y:.1f} M {x:.1f} {y - 12:.1f} L {x:.1f} {y + 12:.1f}" stroke="#111827" stroke-width="1.4"/>')
            markers.append(f'<text x="{x + 9:.1f}" y="{y - 9:.1f}" font-size="9" font-weight="800" fill="#111827">L</text>')
    return markers


def _isoline_observer_marker(calculationGrid, sx, sy, plot_x, plot_y, plot_h, t):
    if calculationGrid.get("zone") != "observer" or not calculationGrid.get("observer"):
        return []
    _, obs_y = calculationGrid["observer"]
    y = max(plot_y + 8, min(plot_y + plot_h - 8, sy(float(obs_y))))
    x = plot_x - 42
    label = _safe(t("svg.worst_observer"))
    return [
        f'<line x1="{x + 9:.1f}" y1="{y:.1f}" x2="{plot_x - 6:.1f}" y2="{y:.1f}" stroke="#dc2626" stroke-width="2.4"/>',
        f'<polygon points="{plot_x - 6:.1f},{y:.1f} {plot_x - 17:.1f},{y - 6:.1f} {plot_x - 17:.1f},{y + 6:.1f}" fill="#dc2626"/>',
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="8" fill="#fee2e2" stroke="#dc2626" stroke-width="2"/>',
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="#dc2626"/>',
        f'<rect x="{x - 34:.1f}" y="{y + 12:.1f}" width="74" height="17" rx="3" fill="white" opacity="0.94" stroke="#fecaca"/>',
        f'<text x="{x + 3:.1f}" y="{y + 24:.1f}" text-anchor="middle" font-size="8.5" font-weight="800" fill="#991b1b">{label}</text>',
    ]


def _field_contours(x_coords, y_coords, values, level):
    """Marching-squares contour segments for a rectilinear grid."""
    segments = []

    def crossing(p1, p2, v1, v2):
        if abs(v2 - v1) < 1e-12:
            t = 0.5
        else:
            t = (level - v1) / (v2 - v1)
        t = max(0.0, min(1.0, t))
        return p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t

    for ix in range(len(x_coords) - 1):
        for iy in range(len(y_coords) - 1):
            p = [
                (x_coords[ix], y_coords[iy]),
                (x_coords[ix + 1], y_coords[iy]),
                (x_coords[ix + 1], y_coords[iy + 1]),
                (x_coords[ix], y_coords[iy + 1]),
            ]
            v = [
                values[ix][iy],
                values[ix + 1][iy],
                values[ix + 1][iy + 1],
                values[ix][iy + 1],
            ]
            pts = []
            for a, b in ((0, 1), (1, 2), (2, 3), (3, 0)):
                va, vb = v[a], v[b]
                if (va < level <= vb) or (vb < level <= va):
                    pts.append(crossing(p[a], p[b], va, vb))
            if len(pts) == 2:
                segments.append((pts[0], pts[1]))
            elif len(pts) == 4:
                segments.append((pts[0], pts[1]))
                segments.append((pts[2], pts[3]))
    return segments


def _dense_isoline_field(calculationGrid, config: CalculationConfig, photometry, flux_scale, include_sidewalks):
    cfg = calculation_config_dict(config)
    luminaires = build_luminaires(cfg, photometry, flux_scale=flux_scale)
    nx, ny = 74, 46
    x_min, x_max = 0.0, config.spacing
    y_min = -config.sidewalk_left if include_sidewalks else 0.0
    y_max = config.road_width + (config.sidewalk_right if include_sidewalks else 0.0)
    if y_max <= y_min:
        y_min, y_max = 0.0, max(config.road_width, 1.0)
    xs = [x_min + (x_max - x_min) * i / (nx - 1) for i in range(nx)]
    ys = [y_min + (y_max - y_min) * j / (ny - 1) for j in range(ny)]
    if calculationGrid.get("unit") == "lux":
        values = [[sum(lum.E_at(x, y) for lum in luminaires) for y in ys] for x in xs]
    else:
        observer_xy = calculationGrid.get("observer") or (-60.0, config.road_width / max(config.lanes, 1) / 2.0)
        pavement = calculationGrid.get("pavement", config.pavement)
        values = [[sum(lum.L_at(x, y, observer_xy, road=pavement) for lum in luminaires) for y in ys] for x in xs]
    flat = [v for col in values for v in col]
    return xs, ys, values, min(flat), max(flat)


def renderIsoLinesSvg(calculationGrid, config: CalculationConfig, photometry=None, flux_scale=1.0, t=None):
    """Render technical isolines from the calculated photometric field around each luminaire."""
    t = t or translator(getattr(config, "language", "en"))
    xs = calculationGrid.get("xs", [])
    ys = calculationGrid.get("ys", [])
    values = calculationGrid.get("values", [])
    unit = calculationGrid.get("unit", "lux")
    title = _safe(calculationGrid.get("title", "Isolines"))
    if not xs or not ys or not values:
        return ""

    include_sidewalks = calculationGrid.get("unit") == "lux"
    if photometry is not None:
        field_xs, field_ys, field_values, vmin, vmax = _dense_isoline_field(
            calculationGrid, config, photometry, flux_scale, include_sidewalks
        )
    else:
        field_xs, field_ys, field_values = xs, ys, values
        flat = [float(v) for row in values for v in row]
        vmin, vmax = min(flat), max(flat)
    if vmax <= vmin:
        levels = [vmax]
    else:
        levels = [vmin + (vmax - vmin) * p for p in (0.10, 0.30, 0.50, 0.70, 0.90)]
    width, height = 900, 350
    plot_x, plot_y, plot_w, plot_h = 86, 78, 720, 215
    y_min, y_max = min(field_ys), max(field_ys)
    road_y = plot_y + (0 - y_min) / max(y_max - y_min, 1) * plot_h
    road_h = config.road_width / max(y_max - y_min, 1) * plot_h

    x_min, x_max = min(field_xs), max(field_xs)

    def sx(x):
        return plot_x + (x - x_min) / max(x_max - x_min, 1) * plot_w

    def sy(y):
        return plot_y + (y - y_min) / max(y_max - y_min, 1) * plot_h

    grid_pts = []
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            value = values[i][j]
            color = "#1e40af" if value >= (vmin + vmax) / 2 else "#64748b"
            grid_pts.append(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="2.2" fill="{color}" opacity="0.72"/>')

    contours = []
    colors = ["#22c55e", "#3b82f6", "#f59e0b", "#f97316", "#ef4444"]
    for idx, level in enumerate(levels):
        segments = _field_contours(field_xs, field_ys, field_values, level)
        for (x1, y1), (x2, y2) in segments:
            contours.append(
                f'<line x1="{sx(x1):.1f}" y1="{sy(y1):.1f}" x2="{sx(x2):.1f}" y2="{sy(y2):.1f}" '
                f'stroke="{colors[idx]}" stroke-width="1.7" stroke-linecap="round" opacity="0.9"/>'
            )
        label_x = plot_x + plot_w - 116
        label_y = plot_y + 20 + idx * 22
        contours.append(
            f'<rect x="{label_x - 7:.1f}" y="{label_y - 14:.1f}" width="108" height="19" rx="3" fill="white" opacity="0.9" stroke="#dbe3ef"/>'
            f'<line x1="{label_x:.1f}" y1="{label_y - 4:.1f}" x2="{label_x + 20:.1f}" y2="{label_y - 4:.1f}" stroke="{colors[idx]}" stroke-width="2.4"/>'
            f'<text x="{label_x + 26:.1f}" y="{label_y:.1f}" font-size="10" font-weight="800" fill="{colors[idx]}">{_fmt(level, 2)} {unit}</text>'
        )

    lanes = []
    for lane in range(1, config.lanes):
        y = road_y + road_h * lane / config.lanes
        lanes.append(f'<line x1="{plot_x}" y1="{y:.1f}" x2="{plot_x + plot_w}" y2="{y:.1f}" stroke="white" stroke-width="2" stroke-dasharray="14 10"/>')

    lum_markers = _isoline_luminaire_markers(config, photometry, flux_scale, sx, sy, y_min, y_max)
    observer_marker = _isoline_observer_marker(calculationGrid, sx, sy, plot_x, plot_y, plot_h, t)

    uniformity = (vmin / calculationGrid.get("avg", vmax)) if calculationGrid.get("avg", 0) else 0
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">
  <rect width="{width}" height="{height}" fill="white"/>
  <text x="28" y="34" font-size="17" font-weight="800" fill="#0f172a">{title}</text>
  <text x="28" y="53" font-size="11" fill="#64748b">{_safe(t('svg.contours_subtitle'))}</text>
  <rect x="{plot_x}" y="{plot_y}" width="{plot_w}" height="{plot_h}" fill="#e8edf3" stroke="#cbd5e1"/>
  <rect x="{plot_x}" y="{road_y:.1f}" width="{plot_w}" height="{road_h:.1f}" fill="#59616c"/>
  {''.join(lanes)}
  {''.join(contours)}
  {''.join(grid_pts)}
  {''.join(lum_markers)}
  {''.join(observer_marker)}
  <line x1="{plot_x}" y1="{plot_y + plot_h + 24}" x2="{plot_x + plot_w}" y2="{plot_y + plot_h + 24}" stroke="#334155"/>
  <text x="{plot_x + plot_w / 2}" y="{plot_y + plot_h + 42}" text-anchor="middle" font-size="11" font-weight="700" fill="#334155">{_safe(t('svg.x_coordinate', value=f'{config.spacing:.1f}'))}</text>
  <g transform="translate(820 94)">
    <rect x="0" y="0" width="60" height="150" rx="6" fill="#f8fafc" stroke="#dbe3ef"/>
    <text x="30" y="22" text-anchor="middle" font-size="10" fill="#64748b">{_safe(t('svg.scale'))}</text>
    <text x="30" y="48" text-anchor="middle" font-size="12" font-weight="800" fill="#0f172a">{_safe(t('svg.avg'))}</text>
    <text x="30" y="64" text-anchor="middle" font-size="11" fill="#334155">{_fmt(calculationGrid.get("avg"), 2)}</text>
    <text x="30" y="91" text-anchor="middle" font-size="12" font-weight="800" fill="#0f172a">{_safe(t('svg.min'))}</text>
    <text x="30" y="107" text-anchor="middle" font-size="11" fill="#334155">{_fmt(vmin, 2)}</text>
    <text x="30" y="133" text-anchor="middle" font-size="12" font-weight="800" fill="#0f172a">Min/Avg</text>
    <text x="30" y="147" text-anchor="middle" font-size="10" fill="#334155">{_fmt(uniformity, 2)}</text>
  </g>
</svg>
"""


def renderResultsTable(result: CalculationResult, t=None):
    t = t or translator(result.config.language)
    rows = []
    for criterion in result.criteria:
        status_class = "ok" if criterion.passed else "fail"
        rows.append(
            f"<tr><td class=\"criterion-name\">{_safe(criterion.name)}</td>"
            f"<td class=\"criterion-value\">{_fmt(criterion.value, 2)}</td>"
            f"<td class=\"criterion-req {status_class}\">req {_fmt(criterion.required, 2)}</td>"
            f"<td class=\"criterion-status {status_class}\">{'&#10003;' if criterion.passed else '&#9888;'}</td></tr>"
        )
    return "<table class=\"criteria-compact\"><tbody>" + "".join(rows) + "</tbody></table>"


def _point_table(grid, t=None, max_rows=10, max_cols=12):
    t = t or translator("en")
    if not grid:
        return ""
    xs = grid.get("xs", [])[:max_cols]
    ys = grid.get("ys", [])[:max_rows]
    values = grid.get("values", [])
    unit = grid.get("unit", "")
    header = "".join(f"<th>x={_fmt(x, 1)}</th>" for x in xs)
    rows = []
    for j, y in enumerate(ys):
        cells = []
        for i, _ in enumerate(xs):
            try:
                cells.append(f"<td>{_fmt(values[i][j], 2)}</td>")
            except Exception:
                cells.append("<td>-</td>")
        rows.append(f"<tr><th>y={_fmt(y, 1)}</th>{''.join(cells)}</tr>")
    return (
        f"<div class=\"table-note\">{_safe(t('report.point_values_note', unit=unit))}</div>"
        f"<table class=\"point-table\"><tr><th>y / x</th>{header}</tr>{''.join(rows)}</table>"
    )


def _render_html(result: CalculationResult, project: dict | None = None) -> str:
    cfg = result.config
    language = normalize_language(cfg.language)
    t = translator(language)
    ldt_info = result.luminaire
    photometry = get_photometry(ldt_info.id)
    flux_scale = 1.0
    if photometry is not None and getattr(photometry, "flux", 0):
        flux_scale = ldt_info.flux / photometry.flux
    polar_data = {**photometry.d, "luminaire_name": ldt_info.luminaire_name} if photometry else {"luminaire_name": ldt_info.luminaire_name, "C": [], "G": [], "I": []}
    grids = calculation_grids(result, ldt_info.id)
    primary_grid = grids.get("luminance") or grids.get("illuminance")
    illuminance_grid = grids.get("illuminance")
    luminance_grid = grids.get("luminance")
    sidewalk_left_grid = grids.get("sidewalk_left")
    sidewalk_right_grid = grids.get("sidewalk_right")

    template = env.get_template("report.html")
    mf_origen = float(ldt_info.mf_origen or 1.0)
    mf_efectivo = float(cfg.mf) / mf_origen if mf_origen > 0 else float(cfg.mf)
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    tr = {
        key: t(key)
        for key in [
            "report.project_summary",
            "report.luminaire",
            "report.lighting_class",
            "report.arrangement",
            "report.road_height",
            "report.maintenance_factor",
            "report.pavement_cct_cri",
            "report.planning_parameter",
            "report.value",
            "report.total_width",
            "report.roadway_width",
            "report.sidewalks",
            "report.spacing",
            "report.pole_side_offset_arm_tilt",
            "report.right_sidewalk",
            "report.left_sidewalk",
            "report.footer_technical",
            "report.photometry",
            "report.property",
            "report.manufacturer",
            "report.model",
            "report.optic_family",
            "report.power",
            "report.luminous_flux",
            "report.efficiency",
            "report.technical_note_polar",
            "report.street_geometry",
            "report.road_planning_data",
            "report.public_road_profile",
            "report.sidewalk_area_2",
            "report.sidewalk_area_1",
            "report.width",
            "report.roadway",
            "report.traffic_lanes",
            "report.pavement",
            "report.arrangement_geometry",
            "report.luminaire_pole",
            "report.pole_height",
            "report.pole_offset",
            "report.pole_side",
            "report.effective_overhang",
            "report.arm_tilt",
            "report.arm_length",
            "report.mounting_height",
            "report.planning_relation",
            "report.spacing_between_masts",
            "report.road_total_width",
            "report.optic_cct_cri",
            "report.overall_result",
            "report.pole_luminaire_h",
            "report.arm_tilt_short",
            "report.optic_status",
            "report.footer_plan",
            "report.performance",
            "report.photometric_results",
            "report.all_checked_pass",
            "report.criteria_fail",
            "report.isolines",
            "report.isolines_title",
            "report.no_grid",
            "report.isoline_note",
            "report.isoline_footer",
            "report.point_table",
            "report.point_note",
            "report.point_footer",
        ]
    }
    tr.update({
        "report.subtitle": t("report.subtitle", standard="CIE 140 / EN 13201"),
        "report.generated": t("report.generated", date=now),
        "report.compliant_text": t("report.compliant_text", class_name=cfg.lighting_class),
        "report.non_compliant_text": t("report.non_compliant_text", class_name=cfg.lighting_class),
        "luminaire_footer": t("report.luminaire_footer", name=ldt_info.luminaire_name),
        "criteria_table_footer": t("report.criteria_table", standard="CIE 140 / EN 13201"),
        **{f"page_{page}": t("report.page", page=page) for page in range(1, 7)},
    })

    criteria_map = {}
    for c in result.criteria:
        short_key = c.name.split(" (")[0]
        criteria_map[short_key] = "ok" if c.passed else "fail"

    return template.render(
        language=language,
        project=project,
        tr=tr,
        title=f"{t('report.title')} - {ldt_info.luminaire_name}",
        date=now,
        standard="CIE 140 / EN 13201",
        compliant=result.compliant,
        compliant_label=t("status.pass") if result.compliant else t("status.fail"),
        compliant_color="#10b981" if result.compliant else "#d97706",
        luminaire=ldt_info,
        cfg=cfg,
        criteria_map=criteria_map,
        mf_efectivo=mf_efectivo,
        total_width=cfg.road_width + cfg.sidewalk_left + cfg.sidewalk_right,
        arm_horizontal=cfg.arm_length,
        effective_arm_overhang=effective_overhang(cfg),
        luminaire_mounting_height=luminaire_mounting_height(cfg),
        road_plan_svg=renderRoadPlanSvg(cfg, t),
        road_section_svg=renderRoadSectionSvg(cfg, t),
        mini_section_svg=renderRoadSectionSvg(cfg, t),
        polar_svg=renderPolarPhotometrySvg(polar_data, t, mf_factor=mf_efectivo),
        iso_luminance_svg=renderIsoLinesSvg(luminance_grid, cfg, photometry, flux_scale, t) if luminance_grid else "",
        iso_illuminance_svg=renderIsoLinesSvg(illuminance_grid, cfg, photometry, flux_scale, t) if illuminance_grid else "",
        results_table=renderResultsTable(result, t),
        point_table=_point_table(primary_grid, t),
        sidewalk_left_point_table=_point_table(sidewalk_left_grid, t) if sidewalk_left_grid else "",
        sidewalk_right_point_table=_point_table(sidewalk_right_grid, t) if sidewalk_right_grid else "",
        logo_base64=_load_logo_b64(),
        Lavg=_fmt(result.Lavg, 2),
        Uo=_fmt(result.Uo, 2),
        Ul=_fmt(result.Ul, 2),
        TI=_fmt(result.TI, 2),
        SR=_fmt(result.SR, 2),
        EIR=_fmt(result.EIR, 2),
        Eavg=_fmt(result.Eavg or (illuminance_grid or {}).get("avg"), 2),
        Emin=_fmt(result.Emin or (illuminance_grid or {}).get("min"), 2),
        Emax=_fmt((illuminance_grid or {}).get("max"), 2),
    )


def _generate_pdf_sync(html_doc: str) -> bytes:
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 794, "height": 1123})
        try:
            page.set_content(html_doc, wait_until="networkidle")
            return page.pdf(
                format="A4",
                print_background=True,
                margin={"top": "0mm", "bottom": "0mm", "left": "0mm", "right": "0mm"},
            )
        finally:
            page.close()
            browser.close()


async def generate_pdf(result: CalculationResult, project: dict | None = None) -> bytes:
    html_doc = _render_html(result, project)
    loop = asyncio.get_running_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        return await loop.run_in_executor(pool, _generate_pdf_sync, html_doc)


def _load_logo_b64() -> str:
    logo_path = STATIC_DIR / "logo-salvi.jpeg"
    if not logo_path.exists():
        return ""
    return base64.b64encode(logo_path.read_bytes()).decode()

