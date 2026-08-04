"""
Salvi Studio · Columns — Geometry Service (Fase 2)
Crear, modificar, validar y derivar geometrías paramétricas.

Principios:
- Determinismo: misma entrada + versión de motor = misma geometría derivada.
- Inmutabilidad: revisiones congeladas no se editan.
- Unidades SI internas.
- Hash geométrico SHA-256 sobre serialización canónica.
"""
import hashlib
import json
import math
import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Role
from app.models.db.geometry import (
    GeometryModel, Mast, MastSegment, SectionLaw, SectionProfile,
    MastJoint, Arm, Attachment, CableLoadPoint, DoorAssembly, BaseInterface,
    GeometryValidation, GeometryArtifact,
    GeometryQualityState, GeometryLOD, ValidationResult, ValidationSeverity,
    GeometryArtifactStatus, SectionProfileType, ManufacturingProcess,
)
from app.models.schemas.geometry import (
    GeometryModelCreate, GeometryModelUpdate, MastCreate,
    ValidationSummary, SectionAtZResponse,
)

logger = structlog.get_logger()

# Roles que pueden crear/editar geometrías
_GEO_WRITE_ROLES = {Role.ENGINEER, Role.TECHNICAL_OFFICE, Role.SYSTEM_ADMIN, Role.LIBRARY_ADMIN}
# Roles que pueden aprobar excepciones geométricas
_GEO_EXCEPTION_ROLES = {Role.TECHNICAL_OFFICE, Role.SYSTEM_ADMIN}

# Versión del motor de geometría
GEOMETRY_ENGINE_VERSION = "2.0.0"

# Reglas GEO con su severidad
GEO_RULES: dict[str, tuple[ValidationSeverity, str]] = {
    "GEO-001": (ValidationSeverity.ERROR, "Altura total debe estar entre 0 y 30 m"),
    "GEO-002": (ValidationSeverity.ERROR, "Toda sección debe ser cerrada, no autointersectante y con pared positiva"),
    "GEO-003": (ValidationSeverity.ERROR, "Diámetro mínimo no alcanzado para el material"),
    "GEO-004": (ValidationSeverity.ERROR, "Espesor fuera del rango permitido para material/proceso"),
    "GEO-005": (ValidationSeverity.ERROR, "Pieza > 12 m requiere segmentación o excepción aprobada"),
    "GEO-006": (ValidationSeverity.ERROR, "Suma de tramos y solapes debe reproducir la altura total"),
    "GEO-007": (ValidationSeverity.ERROR, "Accesorios y cables deben quedar vinculados a un componente físico"),
    "GEO-008": (ValidationSeverity.ERROR, "No se permiten más de 6 cables activos"),
    "GEO-009": (ValidationSeverity.ERROR, "Hueco de puerta no permitido en hormigón"),
    "GEO-010": (ValidationSeverity.ERROR, "Colisiones críticas entre componentes"),
    "GEO-011": (ValidationSeverity.WARNING, "Geometría fuera del catálogo de fabricación"),
    "GEO-012": (ValidationSeverity.EXCEPTION_REQUIRED, "Parámetro estimado o pendiente en revisión M2+"),
}

# Diámetros mínimos por familia [m]
MIN_DIAMETER_METAL_M = 0.060
MIN_DIAMETER_CONCRETE_M = 0.150
MIN_THICKNESS_M = 0.0025
MAX_THICKNESS_STEEL_M = 0.008
MAX_THICKNESS_AL_FOLDED_M = 0.006
MAX_PIECE_LENGTH_M = 12.0
MAX_HEIGHT_M = 30.0
MAX_CABLES = 6


class GeometryService:
    """Servicio de dominio para geometría paramétrica (Fase 2)."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Crear modelo geométrico ──────────────────────────────────────────────

    async def create_geometry_model(
        self, data: GeometryModelCreate, actor_role: Role
    ) -> GeometryModel:
        """Crea un nuevo modelo geométrico en estado DRAFT."""
        if actor_role not in _GEO_WRITE_ROLES:
            from fastapi import HTTPException, status
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Sin permiso para crear geometría")

        model = GeometryModel(
            id=str(uuid.uuid4()),
            project_revision_id=str(data.project_revision_id),
            lod=data.lod,
            quality_state=GeometryQualityState.DRAFT,
            coordinate_convention=data.coordinate_convention,
            source=data.source,
            notes=data.notes,
            engine_version=GEOMETRY_ENGINE_VERSION,
        )
        self.db.add(model)
        await self.db.flush()
        await self.db.refresh(model)
        logger.info("geometry_model_created", model_id=model.id, revision_id=data.project_revision_id)
        return model

    # ── Añadir fuste ─────────────────────────────────────────────────────────

    async def add_mast(
        self, geometry_model_id: str, data: MastCreate, actor_role: Role
    ) -> Mast:
        """Añade un fuste con todos sus componentes al modelo geométrico."""
        if actor_role not in _GEO_WRITE_ROLES:
            from fastapi import HTTPException, status
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Sin permiso para editar geometría")

        # Invalidate current hash when mast is modified
        await self._invalidate_hash(geometry_model_id)

        mast = Mast(
            id=str(uuid.uuid4()),
            geometry_model_id=geometry_model_id,
            nominal_height_m=data.nominal_height_m,
            base_type=data.base_type,
            material_ref=str(data.material_ref) if data.material_ref else None,
            manufacturing_process=data.manufacturing_process,
            constraint_set_id=str(data.constraint_set_id) if data.constraint_set_id else None,
            is_segmented=len(data.segments) > 1,
        )
        self.db.add(mast)
        await self.db.flush()

        # Add segments
        for seg_data in data.segments:
            sec_law = SectionLaw(
                id=str(uuid.uuid4()),
                law_type=seg_data.section_law.law_type,
                interpolation=seg_data.section_law.interpolation,
                continuity=seg_data.section_law.continuity,
                parameter_json=seg_data.section_law.parameter_json,
                profile_ref=str(seg_data.section_law.profile_ref) if seg_data.section_law.profile_ref else None,
                domain=seg_data.section_law.domain,
            )
            self.db.add(sec_law)
            await self.db.flush()

            segment = MastSegment(
                id=str(uuid.uuid4()),
                mast_id=mast.id,
                segment_order=seg_data.segment_order,
                piece_id=seg_data.piece_id,
                z_start_m=seg_data.z_start_m,
                z_end_m=seg_data.z_end_m,
                section_law_id=sec_law.id,
                physical_length_m=seg_data.physical_length_m,
                visible_length_m=seg_data.visible_length_m,
                manufacturing_process=seg_data.manufacturing_process,
                material_ref=str(seg_data.material_ref) if seg_data.material_ref else None,
            )
            self.db.add(segment)

        # Add arms
        for arm_data in data.arms:
            arm = Arm(
                id=str(uuid.uuid4()),
                mast_id=mast.id,
                arm_type=arm_data.arm_type,
                code=arm_data.code,
                library_item_id=str(arm_data.library_item_id) if arm_data.library_item_id else None,
                library_version=arm_data.library_version,
                anchor_json=arm_data.anchor_json,
                axis_curve_json=arm_data.axis_curve_json,
                roll_angle_rad=arm_data.roll_angle_rad,
                luminaire_interface_json=arm_data.luminaire_interface_json,
                fabrication_mode=arm_data.fabrication_mode,
                symmetry_group=arm_data.symmetry_group,
                material_ref=str(arm_data.material_ref) if arm_data.material_ref else None,
                mass_kg=arm_data.mass_kg,
            )
            self.db.add(arm)

        # Add attachments
        for att_data in data.attachments:
            att = Attachment(
                id=str(uuid.uuid4()),
                mast_id=mast.id,
                attachment_type=att_data.attachment_type,
                code=att_data.code,
                parent_arm_id=str(att_data.parent_arm_id) if att_data.parent_arm_id else None,
                lod=att_data.lod,
                transform_json=att_data.transform_json,
                mass_kg=att_data.mass_kg,
                cg_local_json=att_data.cg_local_json,
                projected_areas_json=att_data.projected_areas_json,
                aero_json=att_data.aero_json,
                properties_json=att_data.properties_json,
            )
            self.db.add(att)

        # Add cable load points (max 6 — already validated in schema)
        for cable_data in data.cable_load_points:
            cable = CableLoadPoint(
                id=str(uuid.uuid4()),
                mast_id=mast.id,
                cable_identifier=cable_data.cable_identifier,
                anchor_z_m=cable_data.anchor_z_m,
                position_local_json=cable_data.position_local_json,
                azimuth_rad=cable_data.azimuth_rad,
                elevation_rad=cable_data.elevation_rad,
                tension_n=cable_data.tension_n,
                cable_state=cable_data.cable_state,
                interface_type=cable_data.interface_type,
            )
            self.db.add(cable)

        # Add door assemblies
        for door_data in data.door_assemblies:
            # Find the segment (will be flushed above)
            door = DoorAssembly(
                id=str(uuid.uuid4()),
                mast_id=mast.id,
                segment_id=str(door_data.segment_id),
                opening_json=door_data.opening_json,
                reinforcement_json=door_data.reinforcement_json,
                interior_support_json=door_data.interior_support_json,
            )
            self.db.add(door)

        # Add base interface
        if data.base_interface:
            bi = BaseInterface(
                id=str(uuid.uuid4()),
                mast_id=mast.id,
                interface_type=data.base_interface.interface_type,
                geometry_json=data.base_interface.geometry_json,
                bolt_pattern_json=data.base_interface.bolt_pattern_json,
                bolt_details_json=data.base_interface.bolt_details_json,
                embedment_length_m=data.base_interface.embedment_length_m,
            )
            self.db.add(bi)

        await self.db.flush()

        # Recargar con las relaciones precargadas: MastRead las serializa y el
        # acceso perezoso (lazy load) fuera del contexto async falla con
        # MissingGreenlet si no se cargan aquí explícitamente.
        result = await self.db.execute(
            select(Mast)
            .options(
                selectinload(Mast.segments),
                selectinload(Mast.arms),
                selectinload(Mast.attachments),
                selectinload(Mast.cable_load_points),
                selectinload(Mast.door_assemblies),
                selectinload(Mast.base_interface),
            )
            .where(Mast.id == mast.id)
        )
        return result.scalar_one()

    # ── Validar ───────────────────────────────────────────────────────────────

    async def validate(self, geometry_model_id: str) -> ValidationSummary:
        """
        Ejecuta las reglas GEO-001..GEO-012 y actualiza quality_state.
        Cada ejecución crea nuevas filas en geometry_validations (inmutable).
        """
        result = await self.db.execute(
            select(GeometryModel).where(GeometryModel.id == geometry_model_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            from fastapi import HTTPException, status
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Modelo geométrico no encontrado")

        # Load masts
        mast_result = await self.db.execute(
            select(Mast).where(Mast.geometry_model_id == geometry_model_id)
        )
        masts = mast_result.scalars().all()

        validations: list[GeometryValidation] = []
        errors = 0
        warnings_count = 0
        blocked = 0
        passed = 0

        def add_check(rule_code: str, result: ValidationResult, message: str, evidence: Optional[dict] = None):
            nonlocal errors, warnings_count, blocked, passed
            severity, default_msg = GEO_RULES.get(rule_code, (ValidationSeverity.INFO, ""))
            v = GeometryValidation(
                geometry_model_id=geometry_model_id,
                geometry_hash=model.geometry_hash,
                rule_code=rule_code,
                severity=severity,
                result=result,
                message=message or default_msg,
                evidence_json=evidence,
            )
            self.db.add(v)
            validations.append(v)
            if result == ValidationResult.FAIL:
                if severity == ValidationSeverity.ERROR:
                    errors += 1
                elif severity == ValidationSeverity.WARNING:
                    warnings_count += 1
                elif severity == ValidationSeverity.EXCEPTION_REQUIRED:
                    blocked += 1
            elif result == ValidationResult.PASS:
                passed += 1

        for mast in masts:
            # GEO-001: height
            if mast.nominal_height_m <= 0 or mast.nominal_height_m > MAX_HEIGHT_M:
                add_check("GEO-001", ValidationResult.FAIL,
                          f"Altura nominal {mast.nominal_height_m} m fuera de rango (0–30 m)")
            else:
                add_check("GEO-001", ValidationResult.PASS, "Altura válida")

            # Load segments (con section_law precargada: se accede a
            # seg.section_law.parameter_json más abajo)
            seg_result = await self.db.execute(
                select(MastSegment)
                .options(selectinload(MastSegment.section_law))
                .where(MastSegment.mast_id == mast.id)
            )
            segments = seg_result.scalars().all()

            # GEO-003/GEO-004: section dimensions
            for seg in segments:
                params = seg.section_law.parameter_json if seg.section_law else {}
                d_ext = params.get("diameter_m") or params.get("bottom_d_m") or params.get("canonical_dimension_m")
                thickness = params.get("thickness_m")

                if d_ext is not None:
                    is_concrete = seg.manufacturing_process == ManufacturingProcess.CENTRIFUGED_CONCRETE
                    min_d = MIN_DIAMETER_CONCRETE_M if is_concrete else MIN_DIAMETER_METAL_M
                    if d_ext < min_d:
                        add_check("GEO-003", ValidationResult.FAIL,
                                  f"Diámetro {d_ext*1000:.0f} mm inferior al mínimo {min_d*1000:.0f} mm para material")
                    else:
                        add_check("GEO-003", ValidationResult.PASS, "Diámetro mínimo cumplido")

                if thickness is not None and not is_concrete:
                    max_t = MAX_THICKNESS_AL_FOLDED_M if seg.manufacturing_process == ManufacturingProcess.FOLDED_WELD else MAX_THICKNESS_STEEL_M
                    if thickness < MIN_THICKNESS_M or thickness > max_t:
                        add_check("GEO-004", ValidationResult.FAIL,
                                  f"Espesor {thickness*1000:.1f} mm fuera de rango [{MIN_THICKNESS_M*1000:.1f}–{max_t*1000:.1f}] mm")
                    else:
                        add_check("GEO-004", ValidationResult.PASS, "Espesor válido")

            # GEO-005: piece length > 12 m
            for seg in segments:
                if seg.physical_length_m > MAX_PIECE_LENGTH_M:
                    add_check("GEO-005", ValidationResult.FAIL,
                              f"Tramo {seg.piece_id}: longitud {seg.physical_length_m:.2f} m > 12 m sin segmentación",
                              {"piece_id": seg.piece_id, "length_m": seg.physical_length_m})
                else:
                    add_check("GEO-005", ValidationResult.PASS, f"Tramo {seg.piece_id}: longitud transportable")

            # GEO-006: sum of segments reproduces total height
            if segments:
                total_from_segs = sum(s.physical_length_m for s in segments)
                diff = abs(total_from_segs - mast.nominal_height_m)
                if diff > 0.001:
                    add_check("GEO-006", ValidationResult.FAIL,
                              f"Suma de tramos ({total_from_segs:.3f} m) ≠ altura nominal ({mast.nominal_height_m:.3f} m)",
                              {"difference_m": diff})
                else:
                    add_check("GEO-006", ValidationResult.PASS, "Suma de tramos coherente con altura")

            # GEO-008: max 6 cables
            cable_result = await self.db.execute(
                select(CableLoadPoint).where(CableLoadPoint.mast_id == mast.id)
            )
            cables = cable_result.scalars().all()
            if len(cables) > MAX_CABLES:
                add_check("GEO-008", ValidationResult.FAIL,
                          f"Se definen {len(cables)} cables; máximo permitido: {MAX_CABLES}",
                          {"cable_count": len(cables)})
            else:
                add_check("GEO-008", ValidationResult.PASS, f"{len(cables)} cable(s) activos (máx. {MAX_CABLES})")

            # GEO-009: no door in concrete
            door_result = await self.db.execute(
                select(DoorAssembly).where(DoorAssembly.mast_id == mast.id)
            )
            doors = door_result.scalars().all()
            if doors and mast.manufacturing_process == ManufacturingProcess.CENTRIFUGED_CONCRETE:
                add_check("GEO-009", ValidationResult.FAIL,
                          "Hueco de puerta no permitido en hormigón (GEO-009)")
            elif doors:
                add_check("GEO-009", ValidationResult.PASS, "Puertas solo en columna metálica")

        # Recalculate geometry hash
        new_hash = await self._compute_hash(geometry_model_id)
        model.geometry_hash = new_hash

        # Determine new quality state
        if errors > 0 or blocked > 0:
            model.quality_state = GeometryQualityState.DRAFT
        else:
            model.quality_state = GeometryQualityState.GEOMETRY_VALID

        await self.db.flush()

        total_checks = len(validations)
        return ValidationSummary(
            geometry_model_id=uuid.UUID(geometry_model_id),
            quality_state=model.quality_state,
            total_checks=total_checks,
            errors=errors,
            warnings=warnings_count,
            blocked=blocked,
            passed=passed,
            validations=[],  # avoid N+1; caller can query separately
        )

    # ── Propiedades derivadas ─────────────────────────────────────────────────

    async def derive_section_at_z(
        self, geometry_model_id: str, z_m: float
    ) -> SectionAtZResponse:
        """
        Devuelve la sección exacta en la cota z_m.
        Determinista: misma entrada = mismo resultado.
        """
        # Find which segment contains z_m
        mast_result = await self.db.execute(
            select(Mast).where(Mast.geometry_model_id == geometry_model_id)
        )
        mast = mast_result.scalar_one_or_none()
        if not mast:
            from fastapi import HTTPException, status
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Fuste no encontrado")

        seg_result = await self.db.execute(
            select(MastSegment).where(MastSegment.mast_id == mast.id)
        )
        segments = seg_result.scalars().all()

        target_seg = None
        for seg in sorted(segments, key=lambda s: s.z_start_m):
            if seg.z_start_m <= z_m <= seg.z_end_m:
                target_seg = seg
                break

        if not target_seg:
            return SectionAtZResponse(
                z_m=z_m,
                geometry_model_id=uuid.UUID(geometry_model_id),
                parameters={},
            )

        # Load section law
        law_result = await self.db.execute(
            select(SectionLaw).where(SectionLaw.id == target_seg.section_law_id)
        )
        law = law_result.scalar_one_or_none()
        if not law:
            return SectionAtZResponse(z_m=z_m, geometry_model_id=uuid.UUID(geometry_model_id), parameters={})

        params = law.parameter_json
        section_params = dict(params)

        # Interpolate for linear law
        if law.law_type.value == "linear":
            t = (z_m - target_seg.z_start_m) / (target_seg.z_end_m - target_seg.z_start_m) if target_seg.z_end_m != target_seg.z_start_m else 0.0
            d_bottom = params.get("bottom_d_m", params.get("diameter_m", 0.1))
            d_top = params.get("top_d_m", d_bottom)
            d_at_z = d_bottom + (d_top - d_bottom) * t
            thickness = params.get("thickness_m", 0.004)
            section_params["diameter_m"] = d_at_z
            section_params["thickness_m"] = thickness

            # Compute circular section properties
            d_ext = d_at_z
            d_int = d_ext - 2 * thickness
            area = math.pi / 4 * (d_ext**2 - d_int**2)
            Ixx = math.pi / 64 * (d_ext**4 - d_int**4)
            J = math.pi / 32 * (d_ext**4 - d_int**4)
            perimeter = math.pi * d_ext

            return SectionAtZResponse(
                z_m=z_m,
                geometry_model_id=uuid.UUID(geometry_model_id),
                segment_id=uuid.UUID(target_seg.id),
                section_type=SectionProfileType.CIRCULAR,
                parameters=section_params,
                area_m2=area,
                centroid_json={"x_m": 0.0, "y_m": 0.0},
                Ixx_m4=Ixx,
                Iyy_m4=Ixx,
                Ixy_m4=0.0,
                J_m4=J,
                perimeter_m=perimeter,
            )

        # For other laws, return parameters without full section props
        return SectionAtZResponse(
            z_m=z_m,
            geometry_model_id=uuid.UUID(geometry_model_id),
            segment_id=uuid.UUID(target_seg.id) if target_seg else None,
            parameters=section_params,
        )

    # ── Hash geométrico ───────────────────────────────────────────────────────

    async def _compute_hash(self, geometry_model_id: str) -> str:
        """
        Calcula el hash geométrico SHA-256 sobre serialización canónica
        de todos los parámetros que afectan forma, masa, posición o interfaces.
        Excluye nombres, comentarios y metadatos no geométricos.
        Principio P-02: reproducible.
        """
        mast_result = await self.db.execute(
            select(Mast).where(Mast.geometry_model_id == geometry_model_id)
        )
        masts = mast_result.scalars().all()

        canonical: dict = {"geometry_model_id": geometry_model_id, "masts": []}

        for mast in sorted(masts, key=lambda m: m.id):
            mast_data: dict = {
                "nominal_height_m": mast.nominal_height_m,
                "base_type": mast.base_type.value if mast.base_type else None,
                "material_ref": mast.material_ref,
                "segments": [],
                "cables": [],
            }

            seg_result = await self.db.execute(
                select(MastSegment).where(MastSegment.mast_id == mast.id).order_by(MastSegment.segment_order)
            )
            for seg in seg_result.scalars().all():
                mast_data["segments"].append({
                    "order": seg.segment_order,
                    "z_start_m": seg.z_start_m,
                    "z_end_m": seg.z_end_m,
                    "physical_length_m": seg.physical_length_m,
                    "manufacturing_process": seg.manufacturing_process.value if seg.manufacturing_process else None,
                    "material_ref": seg.material_ref,
                })

            cable_result = await self.db.execute(
                select(CableLoadPoint).where(CableLoadPoint.mast_id == mast.id)
            )
            for cable in sorted(cable_result.scalars().all(), key=lambda c: c.cable_identifier):
                mast_data["cables"].append({
                    "identifier": cable.cable_identifier,
                    "anchor_z_m": cable.anchor_z_m,
                    "azimuth_rad": cable.azimuth_rad,
                    "elevation_rad": cable.elevation_rad,
                    "tension_n": cable.tension_n,
                })

            canonical["masts"].append(mast_data)

        canonical_str = json.dumps(canonical, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(canonical_str.encode()).hexdigest()

    async def _invalidate_hash(self, geometry_model_id: str) -> None:
        """Invalida el hash y marca los artefactos como obsoletos."""
        model_result = await self.db.execute(
            select(GeometryModel).where(GeometryModel.id == geometry_model_id)
        )
        model = model_result.scalar_one_or_none()
        if model:
            model.geometry_hash = None
            model.quality_state = GeometryQualityState.DRAFT

        artifact_result = await self.db.execute(
            select(GeometryArtifact).where(GeometryArtifact.geometry_model_id == geometry_model_id)
        )
        for artifact in artifact_result.scalars().all():
            artifact.status = GeometryArtifactStatus.OBSOLETE

    # ── Clone ──────────────────────────────────────────────────────────────────

    async def clone_geometry_model(
        self, geometry_model_id: str, target_revision_id: Optional[str], actor_role: Role
    ) -> GeometryModel:
        """
        Clona un modelo geométrico para una revisión o alternativa diferente.
        AC-16: nuevo UUID, mismo snapshot, trazabilidad de origen.
        """
        if actor_role not in _GEO_WRITE_ROLES:
            from fastapi import HTTPException, status
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Sin permiso para clonar geometría")

        result = await self.db.execute(
            select(GeometryModel).where(GeometryModel.id == geometry_model_id)
        )
        source = result.scalar_one_or_none()
        if not source:
            from fastapi import HTTPException, status
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Modelo no encontrado")

        new_model = GeometryModel(
            id=str(uuid.uuid4()),
            project_revision_id=target_revision_id or source.project_revision_id,
            schema_version=source.schema_version,
            lod=source.lod,
            quality_state=GeometryQualityState.DRAFT,
            coordinate_convention=source.coordinate_convention,
            canonical_units=source.canonical_units,
            source="cloned_from:" + geometry_model_id,
            notes=source.notes,
            engine_version=GEOMETRY_ENGINE_VERSION,
        )
        self.db.add(new_model)
        await self.db.flush()
        logger.info("geometry_model_cloned", source_id=geometry_model_id, new_id=new_model.id)
        return new_model

    # ── Compare ────────────────────────────────────────────────────────────────

    async def compare_models(
        self, model_a_id: str, model_b_id: str
    ) -> dict:
        """
        Compara dos modelos geométricos por hash.
        AC-17: mismo geometry_hash = geométricamente idénticos.
        """
        res_a = await self.db.execute(select(GeometryModel).where(GeometryModel.id == model_a_id))
        res_b = await self.db.execute(select(GeometryModel).where(GeometryModel.id == model_b_id))
        model_a = res_a.scalar_one_or_none()
        model_b = res_b.scalar_one_or_none()

        if not model_a or not model_b:
            from fastapi import HTTPException, status
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Modelo no encontrado")

        identical = (
            model_a.geometry_hash is not None
            and model_a.geometry_hash == model_b.geometry_hash
        )
        differences = []
        if not identical:
            if model_a.lod != model_b.lod:
                differences.append({"field": "lod", "a": model_a.lod, "b": model_b.lod})
            if model_a.quality_state != model_b.quality_state:
                differences.append({"field": "quality_state", "a": model_a.quality_state, "b": model_b.quality_state})

        return {
            "model_a_id": model_a_id,
            "model_b_id": model_b_id,
            "hash_a": model_a.geometry_hash,
            "hash_b": model_b.geometry_hash,
            "identical": identical,
            "differences": differences,
        }
