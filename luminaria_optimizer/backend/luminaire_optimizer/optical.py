"""Small-block geometric ray tracer for the supplied LED/lens assembly."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from .ray_angles import direction_angles

if TYPE_CHECKING:
    from .geometry import StepGeometry
    from .rayset import Tm25RaySet


MAX_PREVIEW_RAY_COUNT = 20_000


@dataclass(frozen=True)
class RayTraceResult:
    """Flux accounting and transmitted rays from one sampled trace."""

    source_ray_count: int
    led_count: int
    traced_ray_count: int
    input_flux_lm: float
    missed_ray_count: int
    missed_flux_lm: float
    intercepted_ray_count: int
    intercepted_flux_lm: float
    transmitted_ray_count: int
    transmitted_flux_lm: float
    total_internal_reflection_count: int
    untransmitted_flux_lm: float
    transmitted_rays: np.ndarray
    preview_rays_detail: tuple[dict[str, object], ...] = ()

    def diagnostic(self) -> dict[str, object]:
        return {
            "source_ray_count": self.source_ray_count,
            "led_count": self.led_count,
            "traced_ray_count": self.traced_ray_count,
            "input_flux_lm": self.input_flux_lm,
            "missed_ray_count": self.missed_ray_count,
            "missed_flux_lm": self.missed_flux_lm,
            "intercepted_ray_count": self.intercepted_ray_count,
            "intercepted_flux_lm": self.intercepted_flux_lm,
            "transmitted_ray_count": self.transmitted_ray_count,
            "transmitted_flux_lm": self.transmitted_flux_lm,
            "total_internal_reflection_count": self.total_internal_reflection_count,
            "untransmitted_flux_lm": self.untransmitted_flux_lm,
            "transmission_pct": (
                100.0 * self.transmitted_flux_lm / self.input_flux_lm
                if self.input_flux_lm else 0.0
            ),
            "preview_ray_count": len(self.preview_rays_detail),
            "preview_status_counts": {
                status: sum(
                    1 for ray in self.preview_rays_detail
                    if ray["status"] == status
                )
                for status in sorted({
                    str(ray["status"]) for ray in self.preview_rays_detail
                })
            },
        }


def _unit(vector: np.ndarray) -> np.ndarray:
    length = float(np.linalg.norm(vector))
    if length <= 1e-12:
        raise ValueError("zero-length ray vector")
    return vector / length


class _PreviewCollector:
    """Keep a bounded, status-diverse visual sample during the full trace."""

    def __init__(self, limit: int, *, c_mirror: bool, c_offset_deg: float) -> None:
        self.limit = limit
        self.c_mirror = c_mirror
        self.c_offset_deg = c_offset_deg
        self._buckets: dict[str, list[tuple[int, dict[str, object]]]] = {}
        self._sequence = 0

    @staticmethod
    def _vector(value: np.ndarray | None) -> list[float] | None:
        if value is None:
            return None
        return [float(component) for component in value]

    def _add_one(
        self,
        *,
        led_index: int,
        status: str,
        origin: np.ndarray,
        entry: np.ndarray | None,
        exit_point: np.ndarray | None,
        final_direction: np.ndarray | None,
        input_power: float,
        output_power: float,
        tir_count: int,
        reflection_points: list[np.ndarray],
        entry_surface_index: int | None = None,
        exit_surface_index: int | None = None,
    ) -> None:
        if self.limit <= 0:
            return
        bucket = self._buckets.setdefault(status, [])
        if len(bucket) >= self.limit:
            return
        direction = self._vector(final_direction)
        if final_direction is None:
            c_deg = None
            gamma_deg = None
        else:
            c_value, gamma_value = direction_angles(
                np.asarray(final_direction, dtype=np.float64),
                c_mirror=self.c_mirror,
                c_offset_deg=self.c_offset_deg,
            )
            c_deg = float(c_value)
            gamma_deg = float(gamma_value)
        record = {
            "led_index": int(led_index),
            "status": status,
            "origin_xyz": self._vector(origin),
            "entry_xyz": self._vector(entry),
            "exit_xyz": self._vector(exit_point),
            "direction_xyz": direction,
            # Keep source power available for every status. Transmitted power
            # after Fresnel losses is exposed separately for transmitted rays.
            "power_lm": float(input_power),
            "transmitted_power_lm": float(output_power),
            "c_deg": c_deg,
            "gamma_deg": gamma_deg,
            "tir": bool(tir_count),
            "tir_count": int(tir_count),
            "reflection_points_xyz": [
                self._vector(point) for point in reflection_points
            ],
            "entry_surface_index": entry_surface_index,
            "exit_surface_index": exit_surface_index,
        }
        bucket.append((self._sequence, record))
        self._sequence += 1

    def add_batch(
        self,
        *,
        led_indices: np.ndarray,
        statuses: np.ndarray,
        origins: np.ndarray,
        entry_points: np.ndarray,
        entry_hit: np.ndarray,
        exit_points: np.ndarray,
        final_directions: np.ndarray,
        input_power: np.ndarray,
        output_power: np.ndarray,
        tir_counts: np.ndarray,
        reflection_points: dict[int, list[np.ndarray]],
        entry_surface_indices: np.ndarray,
        exit_surface_indices: np.ndarray,
    ) -> None:
        if self.limit <= 0:
            return
        statuses = np.asarray(statuses, dtype=object)
        for status_value in sorted({str(value) for value in statuses}):
            bucket = self._buckets.setdefault(status_value, [])
            if len(bucket) >= self.limit:
                continue
            indices = np.flatnonzero(statuses == status_value)
            remaining = self.limit - len(bucket)
            if len(indices) > remaining:
                indices = indices[np.linspace(0, len(indices) - 1, remaining, dtype=int)]
            for index in indices:
                self._add_one(
                    led_index=int(led_indices[index]),
                    status=status_value,
                    origin=origins[index],
                    entry=entry_points[index] if entry_hit[index] else None,
                    exit_point=exit_points[index] if status_value == "transmitted" else None,
                    final_direction=final_directions[index],
                    input_power=float(input_power[index]),
                    output_power=float(output_power[index]),
                    tir_count=int(tir_counts[index]),
                    reflection_points=reflection_points.get(int(index), []),
                    entry_surface_index=(
                        int(entry_surface_indices[index])
                        if entry_hit[index] and entry_surface_indices[index] >= 0 else None
                    ),
                    exit_surface_index=(
                        int(exit_surface_indices[index])
                        if status_value == "transmitted" and exit_surface_indices[index] >= 0 else None
                    ),
                )

    def add_one(
        self,
        *,
        led_index: int,
        status: str,
        origin: np.ndarray,
        entry: np.ndarray | None,
        exit_point: np.ndarray | None,
        final_direction: np.ndarray | None,
        input_power: float,
        output_power: float,
        tir_count: int,
    ) -> None:
        self._add_one(
            led_index=led_index,
            status=status,
            origin=origin,
            entry=entry,
            exit_point=exit_point,
            final_direction=final_direction,
            input_power=input_power,
            output_power=output_power,
            tir_count=tir_count,
            reflection_points=[],
        )

    def records(self) -> tuple[dict[str, object], ...]:
        buckets = [
            (status, bucket)
            for status, bucket in self._buckets.items()
            if bucket
        ]
        if not buckets or self.limit <= 0:
            return ()

        allocations = {status: min(len(bucket), self.limit // len(buckets)) for status, bucket in buckets}
        remaining = self.limit - sum(allocations.values())
        while remaining:
            changed = False
            for status, bucket in buckets:
                if allocations[status] < len(bucket):
                    allocations[status] += 1
                    remaining -= 1
                    changed = True
                    if not remaining:
                        break
            if not changed:
                break

        selected: list[tuple[int, dict[str, object]]] = []
        for status, bucket in buckets:
            count = allocations[status]
            if count <= 0:
                continue
            indices = np.linspace(0, len(bucket) - 1, count, dtype=int)
            selected.extend(bucket[index] for index in indices)
        selected.sort(key=lambda item: item[0])
        return tuple(record for _, record in selected)


def _refract(
    direction: np.ndarray,
    normal: np.ndarray,
    n_from: float,
    n_to: float,
) -> tuple[np.ndarray, float] | None:
    """Return refracted direction and unpolarized power transmission."""
    direction = _unit(direction)
    normal = _unit(normal)
    if float(np.dot(direction, normal)) > 0.0:
        normal = -normal
    cos_i = max(0.0, min(1.0, -float(np.dot(direction, normal))))
    eta = n_from / n_to
    sin_t2 = eta * eta * max(0.0, 1.0 - cos_i * cos_i)
    if sin_t2 >= 1.0:
        return None
    cos_t = math.sqrt(max(0.0, 1.0 - sin_t2))
    transmitted = eta * direction + (eta * cos_i - cos_t) * normal
    transmitted = _unit(transmitted)
    rs = ((n_from * cos_i - n_to * cos_t) / (n_from * cos_i + n_to * cos_t)) ** 2
    rp = ((n_from * cos_t - n_to * cos_i) / (n_from * cos_t + n_to * cos_i)) ** 2
    return transmitted, max(0.0, 1.0 - 0.5 * (rs + rp))


def _reflect(direction: np.ndarray, normal: np.ndarray) -> np.ndarray:
    """Return the specular reflection direction at a surface."""
    direction = _unit(direction)
    normal = _unit(normal)
    return _unit(direction - 2.0 * float(np.dot(direction, normal)) * normal)


def _intersections(shape: Any, origin: np.ndarray, direction: np.ndarray) -> list[tuple[float, np.ndarray, np.ndarray]]:
    """Return forward intersections as distance, point and surface normal."""
    from OCP.BRepIntCurveSurface import BRepIntCurveSurface_Inter
    from OCP.gce import gce_MakeLin
    from OCP.gp import gp_Dir, gp_Pnt
    import cadquery as cq

    direction = _unit(direction)
    intersector = BRepIntCurveSurface_Inter()
    line = gce_MakeLin(
        gp_Pnt(*origin.tolist()),
        gp_Dir(*direction.tolist()),
    ).Value()
    intersector.Init(shape.wrapped, line, 1e-7)
    hits: list[tuple[float, np.ndarray, np.ndarray]] = []
    while intersector.More():
        point = intersector.Pnt()
        location = np.array([point.X(), point.Y(), point.Z()], dtype=np.float64)
        distance = float(np.dot(location - origin, direction))
        if distance > 1e-6:
            face = cq.Face(intersector.Face())
            normal = np.asarray(face.normalAt(cq.Vector(*location)).toTuple(), dtype=np.float64)
            hits.append((distance, location, _unit(normal)))
        intersector.Next()
    hits.sort(key=lambda hit: hit[0])
    unique: list[tuple[float, np.ndarray, np.ndarray]] = []
    for hit in hits:
        if not unique or hit[0] - unique[-1][0] > 1e-6:
            unique.append(hit)
    return unique


def _trace_single_lens_ray(
    shape: Any,
    origin: np.ndarray,
    direction: np.ndarray,
    lens_index: float,
    max_bounces: int,
) -> tuple[str, np.ndarray | None, np.ndarray | None, np.ndarray | None, float, int]:
    """Trace one ray and return its visual path and optical result."""
    direction = _unit(direction)
    hits = _intersections(shape, origin, direction)
    if not hits:
        return "missed", None, None, direction, 0.0, 0

    entry = _refract(direction, hits[0][2], 1.0, lens_index)
    if entry is None:
        return "untransmitted", hits[0][1], None, direction, 0.0, 1
    entry_point = hits[0][1]
    current_point = hits[0][1]
    current_direction, transmission = entry
    tir_count = 0

    for _ in range(max_bounces):
        probe = current_point + current_direction * 1e-4
        next_hits = _intersections(shape, probe, current_direction)
        if not next_hits:
            return "untransmitted", entry_point, None, current_direction, 0.0, tir_count
        hit = next_hits[0]
        exit_result = _refract(current_direction, hit[2], lens_index, 1.0)
        if exit_result is not None:
            exit_direction, exit_transmission = exit_result
            return "transmitted", entry_point, hit[1], exit_direction, transmission * exit_transmission, tir_count
        current_point = hit[1]
        current_direction = _reflect(current_direction, hit[2])
        tir_count += 1

    return "untransmitted", entry_point, None, current_direction, 0.0, tir_count


def _mesh_hits(mesh: Any, origins: np.ndarray, directions: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Find the nearest forward triangle hit for every ray in a batch."""
    count = len(origins)
    distance = np.full(count, np.inf, dtype=np.float64)
    points = np.zeros((count, 3), dtype=np.float64)
    normals = np.zeros((count, 3), dtype=np.float64)
    triangles = np.full(count, -1, dtype=np.int64)
    locations, ray_indices, triangle_indices = mesh.ray.intersects_location(
        origins, directions, multiple_hits=True,
    )
    if len(locations) == 0:
        return distance, points, normals, np.zeros(count, dtype=bool), triangles
    ray_indices = np.asarray(ray_indices, dtype=np.int64)
    triangle_indices = np.asarray(triangle_indices, dtype=np.int64)
    locations = np.asarray(locations, dtype=np.float64)
    distances = np.einsum(
        "ij,ij->i", locations - origins[ray_indices], directions[ray_indices],
    )
    valid = distances > 1e-4
    if not np.any(valid):
        return distance, points, normals, np.zeros(count, dtype=bool), triangles
    ray_indices = ray_indices[valid]
    triangle_indices = triangle_indices[valid]
    locations = locations[valid]
    distances = distances[valid]
    order = np.lexsort((distances, ray_indices))
    selected = np.zeros(count, dtype=bool)
    for index in order:
        ray_index = ray_indices[index]
        if selected[ray_index]:
            continue
        selected[ray_index] = True
        distance[ray_index] = distances[index]
        points[ray_index] = locations[index]
        normals[ray_index] = mesh.face_normals[triangle_indices[index]]
        triangles[ray_index] = triangle_indices[index]
    return distance, points, normals, selected, triangles


def _refract_batch(
    directions: np.ndarray,
    normals: np.ndarray,
    n_from: float,
    n_to: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Vectorized Snell/Fresnel calculation for a ray batch."""
    normals = normals / np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
    flip = np.einsum("ij,ij->i", directions, normals) > 0
    normals = np.where(flip[:, None], -normals, normals)
    cos_i = np.clip(-np.einsum("ij,ij->i", directions, normals), 0.0, 1.0)
    eta = n_from / n_to
    sin_t2 = eta * eta * np.maximum(0.0, 1.0 - cos_i * cos_i)
    valid = sin_t2 < 1.0
    cos_t = np.sqrt(np.maximum(0.0, 1.0 - sin_t2))
    transmitted = eta * directions + (eta * cos_i - cos_t)[:, None] * normals
    transmitted /= np.maximum(np.linalg.norm(transmitted, axis=1, keepdims=True), 1e-12)
    rs = ((n_from * cos_i - n_to * cos_t) / np.maximum(n_from * cos_i + n_to * cos_t, 1e-12)) ** 2
    rp = ((n_from * cos_t - n_to * cos_i) / np.maximum(n_from * cos_t + n_to * cos_i, 1e-12)) ** 2
    transmission = np.maximum(0.0, 1.0 - 0.5 * (rs + rp))
    return transmitted, transmission, valid


def _trace_mesh_batch(
    mesh: Any,
    origins: np.ndarray,
    directions: np.ndarray,
    source_flux: np.ndarray,
    lens_index: float,
    max_bounces: int,
) -> dict[str, Any]:
    """Trace a batch through the tessellated lens with vectorized bounces."""
    _, entry_points, entry_normals, hit, entry_triangles = _mesh_hits(mesh, origins, directions)
    surface_ids = getattr(mesh, "triangle_surface_ids", None)
    entry_surfaces = np.full(len(origins), -1, dtype=np.int64)
    if surface_ids is not None:
        surface_ids = np.asarray(surface_ids, dtype=np.int64)
        entry_surfaces[hit] = surface_ids[entry_triangles[hit]]
    intercepted_flux = float(source_flux[hit].sum())
    missed_flux = float(source_flux[~hit].sum())
    statuses = np.full(len(origins), "missed", dtype=object)
    statuses[hit] = "untransmitted"
    final_directions = directions.copy()
    output_power = np.zeros(len(origins), dtype=np.float64)
    exit_points = np.zeros_like(entry_points)
    exit_surfaces = np.full(len(origins), -1, dtype=np.int64)
    tir_counts = np.zeros(len(origins), dtype=np.int64)
    reflection_points: dict[int, list[np.ndarray]] = {}
    current_points = entry_points.copy()
    current_directions, entry_transmission, entry_valid = _refract_batch(
        directions, entry_normals, 1.0, lens_index,
    )
    active = hit & entry_valid
    tir_counts[hit & ~entry_valid] = 1
    final_directions[active] = current_directions[active]
    transmitted_rows: list[np.ndarray] = []
    for _ in range(max_bounces):
        active_indices = np.flatnonzero(active)
        if len(active_indices) == 0:
            break
        probe = current_points[active_indices] + current_directions[active_indices] * 1e-4
        _, next_points, next_normals, next_hit, next_triangles = _mesh_hits(
            mesh, probe, current_directions[active_indices],
        )
        active[active_indices[~next_hit]] = False
        active_hit_indices = active_indices[next_hit]
        if len(active_hit_indices) == 0:
            active[active_indices] = False
            continue
        exit_directions, exit_transmission, can_exit = _refract_batch(
            current_directions[active_hit_indices],
            next_normals[next_hit],
            lens_index,
            1.0,
        )
        exiting_indices = active_hit_indices[can_exit]
        if len(exiting_indices):
            optical_transmission = entry_transmission[exiting_indices] * exit_transmission[can_exit]
            power = source_flux[exiting_indices] * optical_transmission
            statuses[exiting_indices] = "transmitted"
            exit_points[exiting_indices] = next_points[next_hit][can_exit]
            if surface_ids is not None:
                exit_surfaces[exiting_indices] = surface_ids[next_triangles[next_hit][can_exit]]
            final_directions[exiting_indices] = exit_directions[can_exit]
            output_power[exiting_indices] = power
            transmitted_rows.append(np.column_stack((
                next_points[next_hit][can_exit],
                exit_directions[can_exit],
                power,
            )))
            active[exiting_indices] = False
        reflecting_indices = active_hit_indices[~can_exit]
        if len(reflecting_indices):
            reflection_normals = next_normals[next_hit][~can_exit]
            reflected = current_directions[reflecting_indices] - 2.0 * np.einsum(
                "ij,ij->i", current_directions[reflecting_indices], reflection_normals,
            )[:, None] * reflection_normals
            reflected /= np.maximum(np.linalg.norm(reflected, axis=1, keepdims=True), 1e-12)
            current_points[reflecting_indices] = next_points[next_hit][~can_exit]
            current_directions[reflecting_indices] = reflected
            final_directions[reflecting_indices] = reflected
            tir_counts[reflecting_indices] += 1
            for ray_index, point in zip(
                reflecting_indices, next_points[next_hit][~can_exit], strict=True,
            ):
                reflection_points.setdefault(int(ray_index), []).append(point.copy())
    if transmitted_rows:
        transmitted = np.vstack(transmitted_rows)
    else:
        transmitted = np.empty((0, 7), dtype=np.float64)
    return {
        "missed_count": int((~hit).sum()),
        "missed_flux": missed_flux,
        "intercepted_count": int(hit.sum()),
        "intercepted_flux": intercepted_flux,
        "transmitted_count": len(transmitted),
        "transmitted_flux": float(transmitted[:, 6].sum()),
        "tir_count": int(tir_counts.sum()),
        "transmitted": transmitted,
        "statuses": statuses,
        "entry_points": entry_points,
        "entry_hit": hit,
        "entry_surface_indices": entry_surfaces,
        "exit_points": exit_points,
        "exit_surface_indices": exit_surfaces,
        "final_directions": final_directions,
        "output_power": output_power,
        "tir_counts": tir_counts,
        "reflection_points": reflection_points,
    }


def trace_tm25(
    ray_set: "Tm25RaySet",
    geometry: "StepGeometry",
    *,
    sample_count: int = 10_000,
    chunk_size: int = 1_000,
    seed: int = 7,
    lens_index: float = 1.49,
    max_bounces: int = 16,
    preview_ray_count: int = 0,
    c_mirror: bool = False,
    c_offset_deg: float = 0.0,
) -> RayTraceResult:
    """Trace a reproducible sample of the ray set through all three LEDs.

    The input ray file is a single-LED source. Its rays are translated to each
    LED emission origin, and flux is scaled from the sample back to the full
    ray count. The accelerated path tessellates the lens once, then accounts
    for refraction, Fresnel transmission and internal specular reflections in
    vectorized batches.

    ``preview_ray_count`` only bounds the visual event records collected while
    this same trace runs. It does not reduce ``sample_count`` or the
    photometric ``transmitted_rays`` result.
    """
    if sample_count <= 0 or sample_count > ray_set.ray_count:
        raise ValueError("sample_count must be between 1 and the source ray count")
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if lens_index <= 1.0:
        raise ValueError("lens_index must be greater than air index")
    if max_bounces <= 0:
        raise ValueError("max_bounces must be positive")
    if preview_ray_count < 0 or preview_ray_count > MAX_PREVIEW_RAY_COUNT:
        raise ValueError(
            f"preview_ray_count must be between 0 and {MAX_PREVIEW_RAY_COUNT}"
        )

    sample = ray_set.sample(sample_count, seed=seed)
    flux_column = ray_set.flux_column
    sample_scale = ray_set.ray_count / sample_count
    flux_scale = sample_scale
    traced_count = 0
    missed_count = 0
    intercepted_count = 0
    transmitted_count = 0
    tir_count = 0
    input_flux = 0.0
    missed_flux = 0.0
    intercepted_flux = 0.0
    transmitted_flux = 0.0
    transmitted_rows: list[np.ndarray] = []
    mesh = getattr(geometry, "lens_mesh", None)
    preview_collector = _PreviewCollector(
        preview_ray_count,
        c_mirror=c_mirror,
        c_offset_deg=c_offset_deg,
    )

    for start in range(0, sample_count, chunk_size):
        chunk = sample[start:min(start + chunk_size, sample_count)]
        if mesh is not None:
            local_origins = chunk[:, :3].astype(np.float64)
            local_directions = chunk[:, 3:6].astype(np.float64)
            local_directions /= np.maximum(np.linalg.norm(local_directions, axis=1, keepdims=True), 1e-12)
            local_flux = chunk[:, flux_column].astype(np.float64) * flux_scale
            origins = np.concatenate([
                local_origins + np.asarray(origin.toTuple(), dtype=np.float64)
                for origin in geometry.emission_origins
            ])
            directions = np.tile(local_directions, (len(geometry.emission_origins), 1))
            source_flux = np.tile(local_flux, len(geometry.emission_origins))
            batch = _trace_mesh_batch(mesh, origins, directions, source_flux, lens_index, max_bounces)
            if preview_ray_count:
                led_indices = np.repeat(
                    np.arange(len(geometry.emission_origins), dtype=np.int64),
                    len(chunk),
                )
                preview_collector.add_batch(
                    led_indices=led_indices,
                    statuses=batch["statuses"],
                    origins=origins,
                    entry_points=batch["entry_points"],
                    entry_hit=batch["entry_hit"],
                    exit_points=batch["exit_points"],
                    final_directions=batch["final_directions"],
                    input_power=source_flux,
                    output_power=batch["output_power"],
                    tir_counts=batch["tir_counts"],
                    reflection_points=batch["reflection_points"],
                    entry_surface_indices=batch["entry_surface_indices"],
                    exit_surface_indices=batch["exit_surface_indices"],
                )
            traced_count += len(origins)
            missed_count += batch["missed_count"]
            missed_flux += batch["missed_flux"]
            intercepted_count += batch["intercepted_count"]
            intercepted_flux += batch["intercepted_flux"]
            transmitted_count += batch["transmitted_count"]
            transmitted_flux += batch["transmitted_flux"]
            tir_count += batch["tir_count"]
            transmitted_rows.append(batch["transmitted"])
            input_flux += float(source_flux.sum())
            continue
        for ray in chunk:
            local_origin = ray[:3].astype(np.float64)
            local_direction = _unit(ray[3:6].astype(np.float64))
            source_flux = float(ray[flux_column]) * flux_scale
            for led_index, emission_origin in enumerate(geometry.emission_origins):
                origin = local_origin + np.asarray(emission_origin.toTuple(), dtype=np.float64)
                traced_count += 1
                input_flux += source_flux
                status, entry_point, exit_point, final_direction, optical_transmission, ray_tir_count = _trace_single_lens_ray(
                    geometry.lens,
                    origin,
                    local_direction,
                    lens_index,
                    max_bounces,
                )
                output_power = (
                    source_flux * optical_transmission
                    if status == "transmitted" else 0.0
                )
                preview_collector.add_one(
                    led_index=led_index,
                    status=status,
                    origin=origin,
                    entry=entry_point,
                    exit_point=exit_point,
                    final_direction=final_direction,
                    input_power=source_flux,
                    output_power=output_power,
                    tir_count=ray_tir_count,
                )
                tir_count += ray_tir_count
                if status == "missed":
                    missed_count += 1
                    missed_flux += source_flux
                    continue
                intercepted_count += 1
                intercepted_flux += source_flux
                if status != "transmitted" or exit_point is None or final_direction is None:
                    continue
                power = output_power
                transmitted_count += 1
                transmitted_flux += power
                transmitted_rows.append([
                    exit_point[0], exit_point[1], exit_point[2],
                    final_direction[0], final_direction[1], final_direction[2], power,
                ])

    transmitted_array = np.vstack(transmitted_rows) if transmitted_rows else np.empty((0, 7), dtype=np.float64)
    return RayTraceResult(
        source_ray_count=ray_set.ray_count,
        led_count=len(geometry.emission_origins),
        traced_ray_count=traced_count,
        input_flux_lm=input_flux,
        missed_ray_count=missed_count,
        missed_flux_lm=missed_flux,
        intercepted_ray_count=intercepted_count,
        intercepted_flux_lm=intercepted_flux,
        transmitted_ray_count=transmitted_count,
        transmitted_flux_lm=transmitted_flux,
        total_internal_reflection_count=tir_count,
        untransmitted_flux_lm=input_flux - transmitted_flux,
        transmitted_rays=transmitted_array,
        preview_rays_detail=preview_collector.records(),
    )
