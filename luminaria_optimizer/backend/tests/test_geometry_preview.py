from types import SimpleNamespace

import numpy as np
import trimesh

from luminaire_optimizer.geometry import StepGeometry
from luminaire_optimizer.optical import trace_tm25
from luminaire_optimizer.ray_angles import direction_angles


class _Origin:
    def __init__(self, x: float, y: float, z: float):
        self._value = (x, y, z)

    def toTuple(self):
        return self._value


class _RaySet:
    ray_count = 3
    flux_column = 6

    def __init__(self):
        self.rays = np.array([
            [0.0, 0.0, -2.0, 0.0, 0.0, 1.0, 1.0],
            [5.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0],
            [-0.5, 0.0, -2.0, 0.7, 0.0, 0.714, 1.0],
        ])

    def sample(self, count: int, *, seed: int):
        assert count == self.ray_count
        return self.rays.copy()


def test_step_geometry_serializes_global_meshes_as_json_lists():
    lens_mesh = SimpleNamespace(
        vertices=np.array([[10.0, 20.0, 30.0]]),
        faces=np.array([[0, 0, 0]]),
    )
    led_mesh = SimpleNamespace(
        vertices=np.array([[40.0, 50.0, 60.0]]),
        faces=np.array([[0, 0, 0]]),
    )
    geometry = StepGeometry(
        path=SimpleNamespace(),
        lens=object(),
        leds=(object(), object(), object()),
        emission_origins=(),
        lens_mesh=lens_mesh,
        led_meshes=(led_mesh, led_mesh, led_mesh),
        lens_surface_ids=(4,),
        lens_surface_labels=("Face 5 - CYLINDER",),
    )

    payload = geometry.mesh_payload()

    assert payload["units"] == "mm"
    assert payload["coordinate_system"] == "global"
    assert payload["lens"] == {
        "vertices": [[10.0, 20.0, 30.0]],
        "faces": [[0, 0, 0]],
        "surface_ids": [4],
        "surface_labels": ["Face 5 - CYLINDER"],
    }
    assert len(payload["leds"]) == 3
    assert payload["leds"][2]["led_index"] == 2
    assert payload["leds"][2]["vertices"] == [[40.0, 50.0, 60.0]]


def test_visual_trace_is_bounded_and_keeps_distinct_statuses():
    lens_mesh = trimesh.creation.box(extents=(2.0, 2.0, 2.0))
    lens_mesh.triangle_surface_ids = np.arange(len(lens_mesh.faces), dtype=np.int64) + 100
    geometry = SimpleNamespace(
        lens=object(),
        lens_mesh=lens_mesh,
        emission_origins=(_Origin(0.0, 0.0, 0.0),) * 3,
    )

    result = trace_tm25(
        _RaySet(),
        geometry,
        sample_count=3,
        chunk_size=3,
        max_bounces=1,
        preview_ray_count=6,
        c_mirror=True,
        c_offset_deg=15.0,
    )

    details = result.preview_rays_detail
    assert len(details) <= 6
    assert {detail["status"] for detail in details} == {
        "transmitted", "missed", "untransmitted",
    }
    assert all(detail["led_index"] in (0, 1, 2) for detail in details)
    assert all(len(detail["origin_xyz"]) == 3 for detail in details)
    assert all(detail["c_deg"] is not None for detail in details)
    assert all(detail["gamma_deg"] is not None for detail in details)
    assert all("entry_surface_index" in detail for detail in details)
    assert all("exit_surface_index" in detail for detail in details)
    assert all(isinstance(detail["reflection_points_xyz"], list) for detail in details)
    assert all(isinstance(detail["reflection_surface_indices"], list) for detail in details)
    assert all(
        all(len(point) == 3 for point in detail["reflection_points_xyz"])
        for detail in details
    )
    assert all(
        len(detail["reflection_surface_indices"]) == len(detail["reflection_points_xyz"])
        and all(isinstance(surface_index, int) for surface_index in detail["reflection_surface_indices"])
        for detail in details
    )
    tir_details = [detail for detail in details if detail["tir_count"]]
    assert tir_details
    assert all(
        all(100 <= surface_index < 100 + len(lens_mesh.faces)
            for surface_index in detail["reflection_surface_indices"])
        for detail in tir_details
    )
    assert result.traced_ray_count == 9
    assert result.transmitted_rays.shape[1] == 7


def test_preview_angles_use_the_same_mirror_and_offset_order_as_photometry():
    c_deg, gamma_deg = direction_angles(
        np.array([0.0, 1.0, 0.0]), c_mirror=True, c_offset_deg=15.0,
    )

    assert float(c_deg) == 285.0
    assert float(gamma_deg) == 90.0


def test_non_accelerated_preview_keeps_empty_reflection_surface_indices(monkeypatch):
    def fake_trace_single_lens_ray(*args, **kwargs):
        return (
            "untransmitted",
            np.zeros(3),
            None,
            np.array([0.0, 0.0, 1.0]),
            0.0,
            0,
        )

    monkeypatch.setattr(
        "luminaire_optimizer.optical._trace_single_lens_ray",
        fake_trace_single_lens_ray,
    )
    geometry = SimpleNamespace(
        lens=object(),
        emission_origins=(_Origin(0.0, 0.0, 0.0),),
    )

    result = trace_tm25(
        _RaySet(),
        geometry,
        sample_count=3,
        chunk_size=3,
        preview_ray_count=3,
    )

    assert result.preview_rays_detail
    assert all(detail["reflection_points_xyz"] == [] for detail in result.preview_rays_detail)
    assert all(detail["reflection_surface_indices"] == [] for detail in result.preview_rays_detail)
