"""
Salvi Studio · Columns — Schemas Pydantic v2: Geometría Paramétrica (Fase 2)
"""
from __future__ import annotations

import uuid
from typing import Any, Optional, Set
from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.db.geometry import (
    GeometryQualityState, GeometryLOD, SectionLawType, SectionProfileType,
    JointType, ArmType, AttachmentType, CableLoadState, BaseInterfaceType,
    GeometryArtifactFormat, GeometryArtifactStatus, ValidationResult,
    ValidationSeverity, ManufacturingProcess,
)


# ── Section Profile ────────────────────────────────────────────────────────────

class SectionProfileCreate(BaseModel):
    code: str = Field(max_length=50)
    profile_type: SectionProfileType
    geometry_json: dict[str, Any]
    canonical_dimension_m: float = Field(gt=0)
    orientation_rad: float = 0.0
    library_version_id: Optional[uuid.UUID] = None


class SectionProfileRead(BaseModel):
    id: uuid.UUID
    code: str
    profile_type: SectionProfileType
    geometry_json: dict[str, Any]
    canonical_dimension_m: float
    orientation_rad: float
    schema_version: str
    properties_json: Optional[dict[str, Any]] = None

    model_config = {"from_attributes": True}


# ── Section Law ────────────────────────────────────────────────────────────────

class SectionLawCreate(BaseModel):
    law_type: SectionLawType
    interpolation: str = "linear"
    continuity: str = "C0"
    parameter_json: dict[str, Any]
    profile_ref: Optional[uuid.UUID] = None
    domain: str = "mast_segment"


class SectionLawRead(BaseModel):
    id: uuid.UUID
    law_type: SectionLawType
    interpolation: str
    continuity: str
    parameter_json: dict[str, Any]
    profile_ref: Optional[uuid.UUID] = None

    model_config = {"from_attributes": True}


# ── Manufacturing Constraint Set ───────────────────────────────────────────────

class ManufacturingConstraintSetRead(BaseModel):
    id: uuid.UUID
    code: str
    version: str
    scope: str
    rules_json: dict[str, Any]

    model_config = {"from_attributes": True}


# ── Geometry Model ─────────────────────────────────────────────────────────────

class GeometryModelCreate(BaseModel):
    project_revision_id: uuid.UUID
    lod: GeometryLOD = GeometryLOD.G1
    coordinate_convention: str = "Z_up_X_azimuth0"
    source: str = "manual"
    notes: Optional[str] = None


class GeometryModelUpdate(BaseModel):
    lod: Optional[GeometryLOD] = None
    notes: Optional[str] = None
    source: Optional[str] = None


class GeometryModelRead(BaseModel):
    id: uuid.UUID
    project_revision_id: uuid.UUID
    schema_version: str
    lod: GeometryLOD
    quality_state: GeometryQualityState
    coordinate_convention: str
    canonical_units: str
    source: str
    geometry_hash: Optional[str] = None
    engine_version: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Mast Segment ───────────────────────────────────────────────────────────────

class MastSegmentCreate(BaseModel):
    segment_order: int = Field(ge=1)
    piece_id: str = Field(max_length=20)
    z_start_m: float
    z_end_m: float
    section_law: SectionLawCreate
    physical_length_m: float = Field(gt=0)
    visible_length_m: Optional[float] = None
    transport_orientation: Optional[str] = None
    manufacturing_process: Optional[ManufacturingProcess] = None
    material_ref: Optional[uuid.UUID] = None

    @model_validator(mode="after")
    def check_z_order(self) -> "MastSegmentCreate":
        if self.z_end_m <= self.z_start_m:
            raise ValueError("z_end_m debe ser mayor que z_start_m")
        return self


class MastSegmentRead(BaseModel):
    id: uuid.UUID
    mast_id: uuid.UUID
    segment_order: int
    piece_id: str
    z_start_m: float
    z_end_m: float
    section_law_id: uuid.UUID
    physical_length_m: float
    visible_length_m: Optional[float] = None
    manufacturing_process: Optional[ManufacturingProcess] = None
    mass_kg: Optional[float] = None
    cg_z_m: Optional[float] = None

    model_config = {"from_attributes": True}


# ── Joint ──────────────────────────────────────────────────────────────────────

class JointCreate(BaseModel):
    lower_segment_id: uuid.UUID
    upper_segment_id: uuid.UUID
    joint_type: JointType
    overlap_m: Optional[float] = None
    z_joint_m: float
    geometry_json: dict[str, Any] = {}


class JointRead(BaseModel):
    id: uuid.UUID
    mast_id: uuid.UUID
    lower_segment_id: uuid.UUID
    upper_segment_id: uuid.UUID
    joint_type: JointType
    overlap_m: Optional[float] = None
    z_joint_m: float
    geometry_json: dict[str, Any]

    model_config = {"from_attributes": True}


# ── Arm ────────────────────────────────────────────────────────────────────────

class ArmCreate(BaseModel):
    arm_type: ArmType
    code: Optional[str] = None
    library_item_id: Optional[uuid.UUID] = None
    library_version: Optional[str] = None
    anchor_json: dict[str, Any]  # {z_m, azimuth_rad, offset_m, connection_diameter_m}
    axis_curve_json: dict[str, Any]
    roll_angle_rad: float = 0.0
    luminaire_interface_json: Optional[dict[str, Any]] = None
    fabrication_mode: Optional[ManufacturingProcess] = None
    symmetry_group: Optional[str] = None
    material_ref: Optional[uuid.UUID] = None
    mass_kg: Optional[float] = None


class ArmRead(BaseModel):
    id: uuid.UUID
    mast_id: uuid.UUID
    arm_type: ArmType
    code: Optional[str] = None
    anchor_json: dict[str, Any]
    axis_curve_json: dict[str, Any]
    roll_angle_rad: float
    luminaire_interface_json: Optional[dict[str, Any]] = None
    fabrication_mode: Optional[ManufacturingProcess] = None
    mass_kg: Optional[float] = None
    projected_areas_json: Optional[dict[str, Any]] = None

    model_config = {"from_attributes": True}


# ── Attachment ─────────────────────────────────────────────────────────────────

class AttachmentCreate(BaseModel):
    attachment_type: AttachmentType
    code: Optional[str] = None
    library_item_id: Optional[uuid.UUID] = None
    library_version: Optional[str] = None
    parent_arm_id: Optional[uuid.UUID] = None
    lod: GeometryLOD = GeometryLOD.G1
    transform_json: dict[str, Any] = {}
    mass_kg: Optional[float] = None
    cg_local_json: Optional[dict[str, Any]] = None
    projected_areas_json: Optional[dict[str, Any]] = None
    aero_json: Optional[dict[str, Any]] = None
    properties_json: Optional[dict[str, Any]] = None


class AttachmentRead(BaseModel):
    id: uuid.UUID
    mast_id: uuid.UUID
    parent_arm_id: Optional[uuid.UUID] = None
    attachment_type: AttachmentType
    code: Optional[str] = None
    lod: GeometryLOD
    transform_json: dict[str, Any]
    mass_kg: Optional[float] = None
    cg_local_json: Optional[dict[str, Any]] = None
    projected_areas_json: Optional[dict[str, Any]] = None

    model_config = {"from_attributes": True}


# ── Cable Load Point ───────────────────────────────────────────────────────────

class CableLoadPointCreate(BaseModel):
    cable_identifier: str = Field(max_length=20)
    anchor_z_m: float
    position_local_json: dict[str, Any] = {}
    azimuth_rad: float = Field(ge=0, lt=6.2832)  # [0, 2π)
    elevation_rad: float = 0.0
    tension_n: Optional[float] = Field(default=None, ge=0)
    cable_state: CableLoadState = CableLoadState.PENDING
    interface_type: Optional[str] = None


class CableLoadPointRead(BaseModel):
    id: uuid.UUID
    mast_id: uuid.UUID
    cable_identifier: str
    anchor_z_m: float
    azimuth_rad: float
    elevation_rad: float
    tension_n: Optional[float] = None
    cable_state: CableLoadState

    model_config = {"from_attributes": True}


# ── Door Assembly ──────────────────────────────────────────────────────────────

class DoorAssemblyCreate(BaseModel):
    segment_id: uuid.UUID
    opening_json: dict[str, Any]  # height_m, width_m, corner_radii_m, z_bottom_m, orientation_rad
    reinforcement_json: Optional[dict[str, Any]] = None
    interior_support_json: Optional[dict[str, Any]] = None


class DoorAssemblyRead(BaseModel):
    id: uuid.UUID
    mast_id: uuid.UUID
    segment_id: uuid.UUID
    opening_json: dict[str, Any]
    reinforcement_json: Optional[dict[str, Any]] = None
    interior_support_json: Optional[dict[str, Any]] = None

    model_config = {"from_attributes": True}


# ── Base Interface ─────────────────────────────────────────────────────────────

class BaseInterfaceCreate(BaseModel):
    interface_type: BaseInterfaceType
    geometry_json: dict[str, Any]
    bolt_pattern_json: Optional[dict[str, Any]] = None
    bolt_details_json: Optional[dict[str, Any]] = None
    embedment_length_m: Optional[float] = None


class BaseInterfaceRead(BaseModel):
    id: uuid.UUID
    mast_id: uuid.UUID
    interface_type: BaseInterfaceType
    geometry_json: dict[str, Any]
    bolt_pattern_json: Optional[dict[str, Any]] = None
    embedment_length_m: Optional[float] = None

    model_config = {"from_attributes": True}


# ── Mast (full) ────────────────────────────────────────────────────────────────

class MastCreate(BaseModel):
    nominal_height_m: float = Field(gt=0, le=30)
    base_type: BaseInterfaceType = BaseInterfaceType.PLATE
    material_ref: Optional[uuid.UUID] = None
    manufacturing_process: Optional[ManufacturingProcess] = None
    constraint_set_id: Optional[uuid.UUID] = None
    segments: list[MastSegmentCreate] = []
    arms: list[ArmCreate] = []
    attachments: list[AttachmentCreate] = []
    cable_load_points: list[CableLoadPointCreate] = []
    door_assemblies: list[DoorAssemblyCreate] = []
    base_interface: Optional[BaseInterfaceCreate] = None

    @field_validator("cable_load_points")
    @classmethod
    def max_six_cables(cls, v: list) -> list:
        if len(v) > 6:
            raise ValueError("Máximo 6 cables por alternativa (GEO-008)")
        return v


class MastRead(BaseModel):
    id: uuid.UUID
    geometry_model_id: uuid.UUID
    nominal_height_m: float
    base_type: BaseInterfaceType
    manufacturing_process: Optional[ManufacturingProcess] = None
    total_height_m: Optional[float] = None
    total_mass_kg: Optional[float] = None
    cg_z_m: Optional[float] = None
    is_segmented: bool
    segments: list[MastSegmentRead] = []
    arms: list[ArmRead] = []
    attachments: list[AttachmentRead] = []
    cable_load_points: list[CableLoadPointRead] = []
    door_assemblies: list[DoorAssemblyRead] = []
    base_interface: Optional[BaseInterfaceRead] = None

    model_config = {"from_attributes": True}


# ── Validation ─────────────────────────────────────────────────────────────────

class GeometryValidationRead(BaseModel):
    id: uuid.UUID
    geometry_model_id: uuid.UUID
    rule_code: str
    severity: ValidationSeverity
    result: ValidationResult
    message: Optional[str] = None
    evidence_json: Optional[dict[str, Any]] = None

    model_config = {"from_attributes": True}


class ValidationSummary(BaseModel):
    geometry_model_id: uuid.UUID
    quality_state: GeometryQualityState
    total_checks: int
    errors: int
    warnings: int
    blocked: int
    passed: int
    validations: list[GeometryValidationRead]


# ── Artifact ───────────────────────────────────────────────────────────────────

class ArtifactGenerateRequest(BaseModel):
    artifact_format: GeometryArtifactFormat
    lod: GeometryLOD = GeometryLOD.G2


class GeometryArtifactRead(BaseModel):
    id: uuid.UUID
    geometry_model_id: uuid.UUID
    geometry_hash: str
    artifact_format: GeometryArtifactFormat
    lod: GeometryLOD
    status: GeometryArtifactStatus
    storage_key: Optional[str] = None
    checksum: Optional[str] = None
    generator_version: Optional[str] = None
    job_id: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Section query ──────────────────────────────────────────────────────────────

class SectionAtZResponse(BaseModel):
    z_m: float
    geometry_model_id: uuid.UUID
    segment_id: Optional[uuid.UUID] = None
    section_type: Optional[SectionProfileType] = None
    parameters: dict[str, Any] = {}
    area_m2: Optional[float] = None
    centroid_json: Optional[dict[str, Any]] = None
    Ixx_m4: Optional[float] = None
    Iyy_m4: Optional[float] = None
    Ixy_m4: Optional[float] = None
    J_m4: Optional[float] = None
    perimeter_m: Optional[float] = None


# ── Clone & Compare ────────────────────────────────────────────────────────────

class GeometryCloneRequest(BaseModel):
    label: Optional[str] = None
    target_revision_id: Optional[uuid.UUID] = None


class GeometryCompareResponse(BaseModel):
    model_a_id: uuid.UUID
    model_b_id: uuid.UUID
    hash_a: Optional[str] = None
    hash_b: Optional[str] = None
    identical: bool
    differences: list[dict[str, Any]] = []
