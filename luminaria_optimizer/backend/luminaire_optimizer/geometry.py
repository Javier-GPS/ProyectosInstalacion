"""Optional CadQuery/OCP STEP geometry loading."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


class GeometryError(ValueError):
    """Raised when the optical assembly cannot be identified."""


@dataclass(frozen=True)
class StepGeometry:
    """The STEP solids, global LED origins and optional triangle meshes."""

    path: Path
    lens: Any
    leds: tuple[Any, ...]
    emission_origins: tuple[Any, ...]
    lens_mesh: Any | None = None
    led_meshes: tuple[Any | None, ...] = ()

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
        return {
            "units": "mm",
            "coordinate_system": "global",
            "coordinate_frame": "STEP",
            "lens": lens or {"vertices": [], "faces": []},
            "leds": leds,
        }


def load_step_geometry(path: str | Path) -> StepGeometry:
    """Import a STEP assembly and identify its largest solid as the lens.

    The supplied assembly contains one large lens solid and three equal small
    LED solids. LED origins are placed on the maximum-Z face of each LED,
    which is the useful emission plane for the supplied ray set.
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
            "se necesita un ensamblaje con una lente y tres sólidos LED."
        )

    lens = max(solids, key=lambda solid: solid.Volume())
    leds = tuple(sorted((solid for solid in solids if solid is not lens), key=lambda solid: solid.Center().x))
    if len(leds) != 3:
        raise GeometryError(
            f"El STEP debe contener una lente y tres sólidos LED; "
            f"se encontraron {len(leds)} LED."
        )
    origins = []
    for led in leds:
        box = led.BoundingBox()
        origins.append(cq.Vector(led.Center().x, led.Center().y, box.zmax))
    meshes: tuple[Any, ...] = ()
    try:
        import trimesh

        tessellated = [solid.tessellate(0.01, 0.1) for solid in (lens, *leds)]
        meshes = tuple(
            trimesh.Trimesh(
                vertices=np.asarray(
                    [vertex.toTuple() for vertex in vertices], dtype=np.float64,
                ),
                faces=np.asarray(triangles, dtype=np.int64),
                process=False,
            )
            for vertices, triangles in tessellated
        )
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
    )
