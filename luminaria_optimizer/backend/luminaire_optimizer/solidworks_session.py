"""Small serialized SolidWorks automation session for local CAD previews."""
from __future__ import annotations

import pathlib
import shutil
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

import numpy as np

from .geometry import EmissionFrame, GeometryBox, GeometryError, GeometryVector, MeshSolid, StepGeometry


class SolidWorksError(RuntimeError):
    """Raised when SolidWorks cannot open or rebuild a CAD document."""


@dataclass(frozen=True)
class _NativePartMesh:
    name: str
    mesh: Any
    surface_ids: tuple[int, ...]
    surface_labels: tuple[str, ...]
    surface_centers: tuple[np.ndarray, ...]
    surface_normals: tuple[np.ndarray, ...]
    surface_areas: tuple[float, ...]


@dataclass
class SolidWorksSession:
    source_path: pathlib.Path
    working_path: pathlib.Path
    sw: Any
    model: Any
    document_type: int
    owns_application: bool

    @classmethod
    def open(cls, source_path: str | pathlib.Path, document_root: str | pathlib.Path | None = None, *, visible: bool = False) -> "SolidWorksSession":
        try:
            import pythoncom
            import win32com.client as win32
        except ImportError as exc:
            raise SolidWorksError(
                "La edición CAD requiere pywin32 en Windows."
            ) from exc

        source = pathlib.Path(source_path).resolve()
        if not source.is_file():
            raise SolidWorksError(f"No existe el documento CAD: {source}")
        extension = source.suffix.lower()
        document_type = {".sldprt": 1, ".sldasm": 2}.get(extension)
        if document_type is None:
            raise SolidWorksError("SolidWorks solo admite documentos SLDPRT o SLDASM.")
        temp_dir = pathlib.Path(tempfile.mkdtemp(prefix="salvi-sw-"))
        working_root = temp_dir / "document"
        if extension == ".sldasm":
            source_root = pathlib.Path(document_root or source.parent).resolve()
            try:
                relative_source = source.relative_to(source_root)
            except ValueError as exc:
                raise SolidWorksError("El ensamblaje CAD está fuera de su carpeta de referencias.") from exc
            shutil.copytree(source_root, working_root)
            working = working_root / relative_source
        else:
            working_root.mkdir()
            working = working_root / f"{source.stem}-{uuid.uuid4().hex[:8]}{source.suffix}"
            working.write_bytes(source.read_bytes())
        pythoncom.CoInitialize()
        owns_application = True
        try:
            try:
                sw = win32.DispatchEx("SldWorks.Application.34")
            except Exception as dispatch_error:
                try:
                    sw = win32.GetActiveObject("SldWorks.Application")
                    owns_application = False
                except Exception:
                    raise dispatch_error
            sw.Visible = visible
            errors = win32.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            warnings = win32.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            model = sw.OpenDoc6(str(working), document_type, 0, "", errors, warnings)
            if model is None:
                raise SolidWorksError(
                    f"SolidWorks no pudo abrir {source.name} "
                    f"(error {errors.value}, advertencia {warnings.value})."
                )
            return cls(source, working, sw, model, document_type, owns_application)
        except Exception:
            pythoncom.CoUninitialize()
            raise

    def parameters(self) -> list[dict[str, object]]:
        result: list[dict[str, object]] = []
        feature = self.model.FirstFeature
        seen: set[str] = set()
        while feature is not None:
            feature_name = str(feature.Name)
            feature_type = str(feature.GetTypeName)
            for prefix in ("D", "R", "A"):
                for index in range(1, 33):
                    name = f"{prefix}{index}@{feature_name}"
                    if name in seen:
                        continue
                    try:
                        parameter = self.model.Parameter(name)
                        value = float(parameter.SystemValue)
                        dimension_type = int(parameter.GetType)
                    except Exception:
                        continue
                    seen.add(name)
                    is_angle = dimension_type == 1
                    result.append({
                        "name": name,
                        "feature": feature_name,
                        "feature_type": feature_type,
                        "value": value,
                        "display_value": value * 180.0 / 3.141592653589793 if is_angle else value * 1000.0,
                        "unit": "deg" if is_angle else "mm",
                        "dimension_type": dimension_type,
                    })
            feature = feature.GetNextFeature
        return result

    def features(self) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        feature = self.model.FirstFeature
        while feature is not None:
            result.append({
                "name": str(feature.Name),
                "type": str(feature.GetTypeName),
                "type2": str(feature.GetTypeName2),
            })
            feature = feature.GetNextFeature
        return result

    def update(self, values: dict[str, float]) -> list[dict[str, object]]:
        for name, value in values.items():
            try:
                parameter = self.model.Parameter(str(name))
                parameter.SystemValue = float(value)
            except Exception as exc:
                raise SolidWorksError(f"No se pudo modificar {name}: {exc}") from exc
        if not bool(self.model.EditRebuild3):
            raise SolidWorksError("SolidWorks no pudo reconstruir todas las operaciones.")
        try:
            self.model.GraphicsRedraw2()
        except Exception:
            # Rebuild success is still usable when the display refresh is unavailable.
            pass
        return self.parameters()

    def export_step(self, target_path: str | pathlib.Path) -> pathlib.Path:
        import pythoncom
        import win32com.client as win32

        target = pathlib.Path(target_path).resolve()
        errors = win32.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        warnings = win32.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        null_dispatch = win32.VARIANT(pythoncom.VT_DISPATCH, None)
        exported = self.model.Extension.SaveAs(
            str(target), 0, 1, null_dispatch, errors, warnings,
        )
        if not exported:
            raise SolidWorksError(
                f"No se pudo exportar la geometría "
                f"(error {errors.value}, advertencia {warnings.value})."
            )
        return target

    def export_native_copy(self, target_path: str | pathlib.Path) -> pathlib.Path:
        """Save the current native document after any parameter updates."""
        import pythoncom
        import win32com.client as win32

        target = pathlib.Path(target_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        errors = win32.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        warnings = win32.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        null_dispatch = win32.VARIANT(pythoncom.VT_DISPATCH, None)
        exported = self.model.Extension.SaveAs(
            str(target), 0, 1, null_dispatch, errors, warnings,
        )
        if not exported:
            raise SolidWorksError(
                f"No se pudo guardar la copia nativa "
                f"(error {errors.value}, advertencia {warnings.value})."
            )
        return target

    def native_geometry(self, reference_assembly: str | pathlib.Path | None = None) -> StepGeometry:
        """Build the tracer mesh from SolidWorks' in-memory face tessellation.

        Embree still needs triangles, but this avoids writing and reimporting an
        intermediate STEP file after each parameter update.
        """
        parts = self._native_parts(self.model)
        if self.document_type == 1:
            if reference_assembly is None:
                raise SolidWorksError("Una pieza óptica necesita un ensamblaje de referencia para situar los LED.")
            reference = pathlib.Path(reference_assembly).resolve()
            if not reference.is_file():
                raise SolidWorksError(f"No existe el ensamblaje de referencia: {reference}")
            parts = self._native_part_with_reference_leds(parts, reference)
        return self._geometry_from_parts(parts)

    def _native_part_with_reference_leds(self, lens_parts: list[_NativePartMesh], reference: pathlib.Path) -> list[_NativePartMesh]:
        if len(lens_parts) != 1:
            raise SolidWorksError("La pieza óptica debe contener un único cuerpo sólido.")
        import pythoncom
        import win32com.client as win32

        errors = win32.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        warnings = win32.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        model = self.sw.OpenDoc6(str(reference), 2, 1, "", errors, warnings)
        if model is None:
            raise SolidWorksError(
                f"SolidWorks no pudo abrir el ensamblaje de referencia "
                f"(error {errors.value}, advertencia {warnings.value})."
            )
        try:
            reference_parts = self._native_parts(model)
        finally:
            self.sw.CloseDoc(model.GetTitle)
        if len(reference_parts) < 2:
            raise SolidWorksError("El ensamblaje de referencia no contiene lente y LED.")
        reference_lens = max(reference_parts, key=lambda item: abs(float(item.mesh.volume)))
        # This is the same orientation previously applied while composing a
        # user SLDPRT with the fixed three-LED assembly, now done in memory.
        lens = self._transform_native_part(
            lens_parts[0],
            np.array([[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]]),
        )
        return [lens, *(item for item in reference_parts if item is not reference_lens)]

    @staticmethod
    def _transform_native_part(part: _NativePartMesh, rotation: np.ndarray) -> _NativePartMesh:
        import trimesh

        vertices = np.asarray(part.mesh.vertices, dtype=np.float64) @ rotation.T
        mesh = trimesh.Trimesh(vertices=vertices, faces=np.asarray(part.mesh.faces), process=False)
        mesh.triangle_surface_ids = np.asarray(part.surface_ids, dtype=np.int64)
        centers = tuple(center @ rotation.T for center in part.surface_centers)
        normals = tuple(normal @ rotation.T for normal in part.surface_normals)
        return _NativePartMesh(
            part.name, mesh, part.surface_ids, part.surface_labels,
            centers, normals, part.surface_areas,
        )

    def _native_parts(self, model: Any) -> list[_NativePartMesh]:
        components = []
        if int(model.GetType) == 2:
            for component in model.GetComponents(True):
                components.extend(self._leaf_components(component))
        else:
            components.append((model.GetTitle, model, None))
        parts: list[_NativePartMesh] = []
        for name, part_model, transform in components:
            if int(part_model.GetType) != 1:
                continue
            parts.extend(self._native_bodies(name, part_model, transform))
        if not parts:
            raise SolidWorksError("No se encontraron cuerpos sólidos teselables en el documento CAD.")
        return parts

    def _leaf_components(self, component: Any) -> list[tuple[str, Any, Any]]:
        children = component.GetChildren
        if children:
            result = []
            for child in children:
                result.extend(self._leaf_components(child))
            return result
        model = component.GetModelDoc2
        return [(str(component.Name2), model, component.Transform2)] if model is not None else []

    @staticmethod
    def _dispatch_array(object_: Any, name: str, arg_types: tuple[tuple[int, int], ...] = (), *args: Any) -> tuple[Any, ...]:
        import pythoncom

        ole = object_._oleobj_
        result = ole.InvokeTypes(
            ole.GetIDsOfNames(name), 0, pythoncom.DISPATCH_METHOD,
            (pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, 0), arg_types, *args,
        )
        return tuple(result or ())

    def _native_bodies(self, component_name: str, part_model: Any, transform: Any) -> list[_NativePartMesh]:
        import pythoncom
        import trimesh
        import win32com.client as win32

        bodies = self._dispatch_array(
            part_model, "GetBodies2",
            ((pythoncom.VT_I4, 0), (pythoncom.VT_BOOL, 0)), 0, True,
        )
        matrix = self._transform_matrix(transform)
        result = []
        for body_index, raw_body in enumerate(bodies):
            body = win32.Dispatch(raw_body)
            raw_faces = self._dispatch_array(body, "GetFaces")
            vertices: list[list[float]] = []
            faces: list[list[int]] = []
            surface_ids: list[int] = []
            centers: list[np.ndarray] = []
            normals: list[np.ndarray] = []
            areas: list[float] = []
            for face_index, raw_face in enumerate(raw_faces):
                face = win32.Dispatch(raw_face)
                values = face._oleobj_.InvokeTypes(
                    face._oleobj_.GetIDsOfNames("GetTessTriangles"), 0,
                    pythoncom.DISPATCH_METHOD, (pythoncom.VT_ARRAY | pythoncom.VT_R8, 0),
                    ((pythoncom.VT_BOOL, 0),), True,
                )
                points = np.asarray(values or (), dtype=np.float64).reshape((-1, 3))
                if not len(points):
                    continue
                world = self._apply_transform(points, matrix) * 1000.0
                triangles = world.reshape((-1, 3, 3))
                cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
                triangle_areas = np.linalg.norm(cross, axis=1) * .5
                area = float(triangle_areas.sum())
                if area <= 1e-12:
                    continue
                normal = (cross * triangle_areas[:, None]).sum(axis=0)
                normal /= max(float(np.linalg.norm(normal)), 1e-12)
                center = np.average(triangles.mean(axis=1), axis=0, weights=triangle_areas)
                offset = len(vertices)
                vertices.extend(world.tolist())
                faces.extend((offset + index, offset + index + 1, offset + index + 2) for index in range(0, len(world), 3))
                surface_ids.extend([face_index] * len(triangles))
                centers.append(center)
                normals.append(normal)
                areas.append(area)
            if not faces:
                continue
            mesh = trimesh.Trimesh(
                vertices=np.asarray(vertices, dtype=np.float64),
                faces=np.asarray(faces, dtype=np.int64), process=False,
            )
            mesh.triangle_surface_ids = np.asarray(surface_ids, dtype=np.int64)
            result.append(_NativePartMesh(
                f"{component_name} / cuerpo {body_index + 1}", mesh,
                tuple(surface_ids), tuple(f"Face {index + 1} - SolidWorks native" for index in range(len(raw_faces))),
                tuple(centers), tuple(normals), tuple(areas),
            ))
        return result

    @staticmethod
    def _transform_matrix(transform: Any) -> np.ndarray:
        if transform is None:
            return np.eye(4, dtype=np.float64)
        data = np.asarray(transform.ArrayData, dtype=np.float64)
        if len(data) < 13:
            raise SolidWorksError("La transformación de un componente CAD es inválida.")
        matrix = np.eye(4, dtype=np.float64)
        matrix[:3, :3] = np.array([
            [data[0], data[3], data[6]],
            [data[1], data[4], data[7]],
            [data[2], data[5], data[8]],
        ]) * data[12]
        matrix[:3, 3] = data[9:12]
        return matrix

    @staticmethod
    def _apply_transform(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
        return points @ matrix[:3, :3].T + matrix[:3, 3]

    @staticmethod
    def _geometry_from_parts(parts: list[_NativePartMesh]) -> StepGeometry:
        lens_part = max(parts, key=lambda item: abs(float(item.mesh.volume)))
        led_parts = sorted((item for item in parts if item is not lens_part), key=lambda item: float(item.mesh.centroid[0]))
        if not led_parts:
            raise SolidWorksError("Se necesita una lente y al menos un sólido LED para trazar rayos.")
        lens_center = np.asarray(lens_part.mesh.centroid, dtype=np.float64)
        frames = []
        for led in led_parts:
            to_lens = lens_center - np.asarray(led.mesh.centroid, dtype=np.float64)
            to_lens /= max(float(np.linalg.norm(to_lens)), 1e-12)
            candidates = [
                (area, float(normal @ to_lens), index)
                for index, (area, normal) in enumerate(zip(led.surface_areas, led.surface_normals))
            ]
            if not candidates:
                raise SolidWorksError(f"No se pudo identificar una cara emisora en {led.name}.")
            _, alignment, face_index = max(candidates, key=lambda item: (item[1] > 1e-6, item[0], item[1]))
            normal = np.asarray(led.surface_normals[face_index], dtype=np.float64)
            if alignment < 0:
                normal = -normal
            reference = np.array([1.0, 0.0, 0.0]) if abs(float(normal[0])) <= .9 else np.array([0.0, 1.0, 0.0])
            axis_x = reference - normal * float(reference @ normal)
            axis_x /= max(float(np.linalg.norm(axis_x)), 1e-12)
            axis_y = np.cross(normal, axis_x)
            axis_y /= max(float(np.linalg.norm(axis_y)), 1e-12)
            center = np.asarray(led.surface_centers[face_index], dtype=np.float64)
            frames.append(EmissionFrame(
                GeometryVector(*center), GeometryVector(*axis_x), GeometryVector(*axis_y), GeometryVector(*normal), face_index,
            ))
        bounds = np.asarray(lens_part.mesh.bounds, dtype=np.float64)
        solid = MeshSolid(
            abs(float(lens_part.mesh.volume)),
            GeometryBox(bounds[0, 0], bounds[1, 0], bounds[0, 1], bounds[1, 1], bounds[0, 2], bounds[1, 2]),
            len(lens_part.surface_labels),
        )
        return StepGeometry(
            pathlib.Path("SolidWorks native geometry"), solid, tuple(MeshSolid(
                abs(float(led.mesh.volume)),
                GeometryBox(led.mesh.bounds[0, 0], led.mesh.bounds[1, 0], led.mesh.bounds[0, 1], led.mesh.bounds[1, 1], led.mesh.bounds[0, 2], led.mesh.bounds[1, 2]),
                len(led.surface_labels),
            ) for led in led_parts),
            tuple(frame.origin for frame in frames), lens_part.mesh, tuple(led.mesh for led in led_parts),
            lens_part.surface_ids, lens_part.surface_labels, tuple(frames), "SolidWorks native",
        )

    def close(self) -> None:
        try:
            title = self.model.GetTitle
            self.sw.CloseDoc(title)
            if self.owns_application:
                self.sw.ExitApp()
        finally:
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except ImportError:
                pass
            shutil.rmtree(self.working_path.parent.parent, ignore_errors=True)


class SolidWorksSessionManager:
    """Keep all COM calls on one thread, as required by SolidWorks automation."""

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="solidworks")
        self._sessions: dict[str, SolidWorksSession] = {}

    def _submit(self, callback, *args):
        return self._executor.submit(callback, *args).result()

    def open(self, source_path: str | pathlib.Path, document_root: str | pathlib.Path | None = None, *, visible: bool = False) -> str:
        def operation():
            session = SolidWorksSession.open(source_path, document_root, visible=visible)
            session_id = uuid.uuid4().hex
            self._sessions[session_id] = session
            return session_id

        return self._submit(operation)

    def describe(self, session_id: str) -> dict[str, object]:
        def operation():
            session = self._sessions[session_id]
            return {
                "title": str(session.model.GetTitle),
                "source_filename": session.source_path.name,
                "document_type": "assembly" if session.document_type == 2 else "part",
                "features": session.features(),
                "parameters": session.parameters(),
            }

        return self._submit(operation)

    def update(self, session_id: str, values: dict[str, float]) -> dict[str, object]:
        def operation():
            session = self._sessions[session_id]
            return {"parameters": session.update(values)}

        return self._submit(operation)

    def export_step(self, session_id: str, target_path: str | pathlib.Path) -> pathlib.Path:
        def operation():
            return self._sessions[session_id].export_step(target_path)

        return self._submit(operation)

    def export_native_copy(self, session_id: str, target_path: str | pathlib.Path) -> pathlib.Path:
        def operation():
            return self._sessions[session_id].export_native_copy(target_path)

        return self._submit(operation)

    def native_geometry(self, session_id: str, reference_assembly: str | pathlib.Path | None = None) -> StepGeometry:
        def operation():
            return self._sessions[session_id].native_geometry(reference_assembly)

        return self._submit(operation)

    def close(self, session_id: str) -> None:
        def operation():
            session = self._sessions.pop(session_id, None)
            if session is not None:
                session.close()

        self._submit(operation)

    def shutdown(self) -> None:
        def operation():
            for session in self._sessions.values():
                session.close()
            self._sessions.clear()

        self._submit(operation)
        self._executor.shutdown(wait=True)
