"""Optional CadQuery/OCP STEP geometry loading."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


class GeometryError(ValueError):
    """Raised when the optical assembly cannot be identified."""


@dataclass(frozen=True)
class GeometryVector:
    """Small coordinate carrier shared by STEP and native CAD geometry."""

    x: float
    y: float
    z: float

    def toTuple(self) -> tuple[float, float, float]:
        return self.x, self.y, self.z


@dataclass(frozen=True)
class GeometryBox:
    xmin: float
    xmax: float
    ymin: float
    ymax: float
    zmin: float
    zmax: float


@dataclass(frozen=True)
class MeshSolid:
    """Minimal solid metadata used when the mesh comes from SolidWorks COM."""

    volume_mm3: float
    bounds_mm: GeometryBox
    face_count: int

    def BoundingBox(self) -> GeometryBox:
        return self.bounds_mm

    def Volume(self) -> float:
        return self.volume_mm3

    def Faces(self) -> tuple[None, ...]:
        return (None,) * self.face_count


@dataclass(frozen=True)
class EmissionFrame:
    origin: Any
    axis_x: Any
    axis_y: Any
    normal: Any
    face_index: int


@dataclass(frozen=True)
class StepGeometry:
    """The STEP solids, global LED origins and optional triangle meshes."""

    path: Path
    lens: Any
    leds: tuple[Any, ...]
    emission_origins: tuple[Any, ...]
    lens_mesh: Any | None = None
    led_meshes: tuple[Any | None, ...] = ()
    lens_surface_ids: tuple[int, ...] = ()
    lens_surface_labels: tuple[str, ...] = ()
    emission_frames: tuple[EmissionFrame, ...] = ()
    coordinate_frame: str = "STEP"

    @property
    def solid_count(self) -> int:
        return len(self.leds) + 1

    def diagnostic(self) -> dict[str, object]:
        lens_box = self.lens.BoundingBox()
        return {
            "path": str(self.path),
            "solid_count": self.solid_count,
            "led_count": len(self.leds),
            "lens_volume": self.lens.Volume(),
            "lens_faces": len(self.lens.Faces()),
            "lens_triangles": len(self.lens_mesh.faces) if self.lens_mesh is not None else None,
            "led_triangles": [
                len(self.led_meshes[index].faces)
                if index < len(self.led_meshes) and self.led_meshes[index] is not None
                else None
                for index in range(len(self.leds))
            ],
            "lens_bbox_mm": {
                "xmin": lens_box.xmin,
                "xmax": lens_box.xmax,
                "ymin": lens_box.ymin,
                "ymax": lens_box.ymax,
                "zmin": lens_box.zmin,
                "zmax": lens_box.zmax,
            },
            "led_origins_mm": [origin.toTuple() for origin in self.emission_origins],
            "led_emission_normals": [frame.normal.toTuple() for frame in self.emission_frames],
            "led_emission_faces": [frame.face_index for frame in self.emission_frames],
        }

    @staticmethod
    def _mesh_payload(mesh: Any | None) -> dict[str, list[list[float | int]]] | None:
        if mesh is None:
            return None
        vertices = np.asarray(mesh.vertices, dtype=np.float64).tolist()
        faces = np.asarray(mesh.faces, dtype=np.int64).tolist()
        return {"vertices": vertices, "faces": faces}

    def mesh_payload(self) -> dict[str, object]:
        """Serialize the lens and LED meshes without changing their STEP frame."""
        leds = []
        for index in range(len(self.leds)):
            mesh = self.led_meshes[index] if index < len(self.led_meshes) else None
            payload = self._mesh_payload(mesh)
            leds.append({
                "led_index": index,
                "vertices": payload["vertices"] if payload is not None else [],
                "faces": payload["faces"] if payload is not None else [],
            })
        lens = self._mesh_payload(self.lens_mesh)
        if lens is None:
            lens = {"vertices": [], "faces": []}
        lens["surface_ids"] = list(self.lens_surface_ids)
        lens["surface_labels"] = list(self.lens_surface_labels)
        return {
            "units": "mm",
            "coordinate_system": "global",
            "coordinate_frame": self.coordinate_frame,
            "lens": lens,
            "leds": leds,
        }


def load_step_geometry(path: str | Path) -> StepGeometry:
    """Import a STEP assembly and identify its largest solid as the lens.

    The supplied assembly contains one large lens solid and one or more LED
    solids. The LED emission face is selected from the face oriented toward
    the lens, and the ray file is mapped to that face's local frame.
    """
    try:
        import cadquery as cq
    except ImportError as exc:
        raise GeometryError(
            "STEP support requires CadQuery/OCP; install the geometry extra"
        ) from exc

    step_path = Path(path)
    if not step_path.is_file():
        raise GeometryError(f"STEP file does not exist: {step_path}")
    try:
        imported = cq.importers.importStep(str(step_path))
        solids = tuple(imported.solids().vals())
    except Exception as exc:
        raise GeometryError(f"cannot import STEP file: {step_path}") from exc
    if len(solids) < 2:
        raise GeometryError(
            f"El STEP seleccionado contiene {len(solids)} sólido(s); "
            "se necesita un ensamblaje con una lente y al menos un sólido LED."
        )

    lens = max(solids, key=lambda solid: solid.Volume())
    leds = tuple(sorted((solid for solid in solids if solid is not lens), key=lambda solid: solid.Center().x))
    if not leds:
        raise GeometryError(
            f"El STEP debe contener una lente y al menos un sólido LED; "
            f"se encontraron {len(leds)} LED."
        )
    origins = []
    emission_frames = []
    lens_center = lens.Center()
    for led in leds:
        frame = _find_emission_frame(cq, led, lens_center)
        emission_frames.append(frame)
        origins.append(frame.origin)
    meshes: tuple[Any, ...] = ()
    try:
        import trimesh

        def point_tuple(vertex: Any) -> tuple[float, float, float]:
            return tuple(float(value) for value in vertex.toTuple()) if hasattr(vertex, "toTuple") else tuple(float(value) for value in vertex)

        lens_vertices: list[tuple[float, float, float]] = []
        lens_faces: list[tuple[int, int, int]] = []
        lens_surface_ids: list[int] = []
        lens_surface_labels: list[str] = []
        for surface_index, face in enumerate(lens.Faces()):
            vertices, triangles = face.tessellate(0.01, 0.1)
            offset = len(lens_vertices)
            lens_vertices.extend(vertex.toTuple() for vertex in vertices)
            lens_faces.extend(
                tuple(int(vertex_index) + offset for vertex_index in triangle)
                for triangle in triangles
            )
            lens_surface_ids.extend([surface_index] * len(triangles))
            geom_type = str(face.geomType())
            lens_surface_labels.append(f"Face {surface_index + 1} - {geom_type}")
        tessellated = [
            (lens_vertices, lens_faces),
            *(solid.tessellate(0.01, 0.1) for solid in leds),
        ]
        meshes = tuple(
            trimesh.Trimesh(
                vertices=np.asarray(
                    [point_tuple(vertex) for vertex in vertices], dtype=np.float64,
                ),
                faces=np.asarray(triangles, dtype=np.int64),
                process=False,
            )
            for vertices, triangles in tessellated
        )
        meshes[0].triangle_surface_ids = np.asarray(lens_surface_ids, dtype=np.int64)
        # Construct the Embree intersector now, not on the first ray batch.
        _ = meshes[0].ray
    except ImportError:
        pass
    return StepGeometry(
        step_path,
        lens,
        leds,
        tuple(origins),
        meshes[0] if meshes else None,
        tuple(meshes[1:]) if meshes else (),
        tuple(lens_surface_ids) if meshes else (),
        tuple(lens_surface_labels) if meshes else (),
        tuple(emission_frames),
    )


def _find_emission_frame(cq: Any, led: Any, lens_center: Any) -> EmissionFrame:
    """Choose the LED face facing the lens and build its local ray frame."""
    led_center = led.Center()
    to_lens = np.asarray((lens_center - led_center).toTuple(), dtype=np.float64)
    to_lens /= max(float(np.linalg.norm(to_lens)), 1e-12)
    candidates = []
    fallback_candidates = []
    for face_index, face in enumerate(led.Faces()):
        try:
            normal = np.asarray(face.normalAt().toTuple(), dtype=np.float64)
        except Exception:
            continue
        norm = float(np.linalg.norm(normal))
        if norm <= 1e-12:
            continue
        normal /= norm
        alignment = float(normal @ to_lens)
        area = float(face.Area())
        candidate = (area, alignment, face_index, face, normal)
        fallback_candidates.append((area, abs(alignment), face_index, face, normal))
        if alignment > 1e-6:
            candidates.append(candidate)
    if not candidates:
        candidates = fallback_candidates
    if not candidates:
        raise GeometryError("No se pudo identificar una cara emisora en un LED.")
    _, _, face_index, face, normal = max(candidates, key=lambda item: (item[0], item[1]))
    if normal @ to_lens < 0.0:
        normal = -normal
    # Keep the projected world X axis as photometric C0 whenever possible.
    # This makes the generated LDT compatible with the road convention while
    # allowing the native CAD assembly to use any mounting orientation.
    reference = np.array([1.0, 0.0, 0.0])
    if abs(float(normal[0])) > 0.9:
        reference = np.array([0.0, 1.0, 0.0])
    axis_x = reference - normal * float(reference @ normal)
    axis_x /= max(float(np.linalg.norm(axis_x)), 1e-12)
    axis_y = np.cross(normal, axis_x)
    axis_y /= max(float(np.linalg.norm(axis_y)), 1e-12)
    center = np.asarray(face.Center().toTuple(), dtype=np.float64)
    return EmissionFrame(
        cq.Vector(*center), cq.Vector(*axis_x), cq.Vector(*axis_y), cq.Vector(*normal), face_index,
    )
