"""Search a simple TIR profile against the measured LED ray file."""
from __future__ import annotations

import math
from pathlib import Path

import cadquery as cq
import numpy as np
import trimesh

from .geometry import StepGeometry, load_step_geometry
from .optical import trace_tm25
from .rayset import parse_tm25


TARGET_TILT_DEG = 7.5
TARGET_DIRECTION = np.array(
    [0.0, math.cos(math.radians(TARGET_TILT_DEG)), math.sin(math.radians(TARGET_TILT_DEG))],
    dtype=np.float64,
)


def build_profile_lens(top_z: np.ndarray, ys: np.ndarray, *, width: float = 14.0) -> cq.Shape:
    boundary = [(float(ys[0]), 0.05), (float(ys[-1]), 0.05)]
    boundary.append((float(ys[-1]), float(top_z[-1])))
    boundary.extend((float(y), float(z)) for y, z in zip(ys[-2::-1], top_z[-2::-1]))
    return cq.Workplane("YZ").polyline(boundary).close().extrude(width).translate((-width / 2, 0, 0)).val()


def make_geometry(base: StepGeometry, lens: cq.Shape, name: str) -> StepGeometry:
    vertices, triangles = lens.tessellate(0.03, 0.08)
    mesh = trimesh.Trimesh(
        vertices=np.asarray([vertex.toTuple() for vertex in vertices], dtype=np.float64),
        faces=np.asarray(triangles, dtype=np.int64),
        process=False,
    )
    _ = mesh.ray
    return StepGeometry(
        Path(name),
        lens,
        base.leds,
        base.emission_origins,
        lens_mesh=mesh,
        led_meshes=base.led_meshes,
        emission_frames=base.emission_frames,
    )


def evaluate(base: StepGeometry, ray_set, top_z: np.ndarray, ys: np.ndarray) -> tuple[float, dict[str, float]]:
    lens = build_profile_lens(top_z, ys)
    if not lens.isValid():
        return float("inf"), {}
    geometry = make_geometry(base, lens, "freeform-search")
    trace = trace_tm25(ray_set, geometry, sample_count=1_000, chunk_size=1_000, lens_index=1.49)
    if not trace.transmitted_rays.size:
        return float("inf"), {}
    rays = trace.transmitted_rays
    directions = rays[:, 3:6]
    directions /= np.maximum(np.linalg.norm(directions, axis=1, keepdims=True), 1e-12)
    weights = rays[:, 6]
    deviations = np.degrees(np.arccos(np.clip(directions @ TARGET_DIRECTION, -1.0, 1.0)))
    transmission_pct = trace.transmitted_flux_lm / trace.input_flux_lm * 100.0
    rms_deg = math.sqrt(float(np.sum(weights * deviations**2) / np.sum(weights)))
    p95_deg = float(np.quantile(deviations, 0.95))
    metrics = {
        "transmission_pct": transmission_pct,
        "rms_deg": rms_deg,
        "p95_deg": p95_deg,
        "mean_deg": float(np.average(deviations, weights=weights)),
    }
    score = rms_deg + 0.25 * p95_deg + 2.0 * max(0.0, 85.0 - transmission_pct)
    return score, metrics


def main() -> None:
    base = load_step_geometry("ensamblaje lente dot led.STEP")
    ray_set = parse_tm25("LUXEON HL2Z_5000000Rays_IESTM25.tm25ray")
    a = 3.0
    ys = np.linspace(-a, 12.0, 13)
    top = 0.1 + np.sqrt(4.0 * a * (ys + a))
    score, metrics = evaluate(base, ray_set, top, ys)
    print("initial", score, metrics)
    step = 2.0
    for _ in range(3):
        improved = True
        while improved:
            improved = False
            for index in range(1, len(top) - 1):
                for delta in (-step, step):
                    candidate = top.copy()
                    candidate[index] += delta
                    if candidate[index] <= 0.15:
                        continue
                    candidate_score, candidate_metrics = evaluate(base, ray_set, candidate, ys)
                    if candidate_score < score:
                        top, score, metrics = candidate, candidate_score, candidate_metrics
                        improved = True
                        print("candidate", score, metrics, "index", index, "delta", delta)
        step *= 0.5
    lens = build_profile_lens(top, ys)
    output = "ensamblaje lente dot led_freeform_optimized_v2.STEP"
    cq.exporters.export(cq.Compound.makeCompound([lens, *base.leds]), output)
    print("best", output, score, metrics)
    ray_set.close()


if __name__ == "__main__":
    main()
