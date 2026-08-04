"""
Fase 11 · Cimentaciones y Geotecnia — Pydantic v2 schemas
"""
from __future__ import annotations

import math
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.db.foundation import (
    DrainageCondition,
    EmbedmentFill,
    EvidenceType,
    FoundationCandidateStatus,
    FoundationCheckMode,
    FoundationFamily,
    FoundationMaturityLevel,
    GeotechnicalLevel,
    SoilClass,
    StiffnessModel,
    WaterScenario,
)


# ---------------------------------------------------------------------------
# Soil layer
# ---------------------------------------------------------------------------

class SoilLayerRequest(BaseModel):
    layer_index: int = Field(..., ge=0)
    depth_top_m: float = Field(..., ge=0.0)
    depth_bottom_m: float = Field(..., gt=0.0)
    soil_class: SoilClass
    description: Optional[str] = None
    gamma_kn_m3: Optional[float] = Field(None, ge=10.0, le=25.0)
    gamma_sat_kn_m3: Optional[float] = Field(None, ge=10.0, le=25.0)
    phi_deg: Optional[float] = Field(None, ge=0.0, le=55.0)
    c_kpa: Optional[float] = Field(None, ge=0.0, le=500.0)
    cu_kpa: Optional[float] = Field(None, ge=0.0, le=1000.0)
    E_mpa: Optional[float] = Field(None, ge=0.1, le=1000.0)
    nu: Optional[float] = Field(None, ge=0.0, le=0.5)
    ks_kn_m3: Optional[float] = Field(None, ge=1.0, le=200_000.0)
    drainage_condition: DrainageCondition = DrainageCondition.DRAINED
    source: Optional[str] = None
    is_conservative_estimate: bool = True
    extra_data: Optional[dict[str, Any]] = None

    @model_validator(mode="after")
    def depth_order(self) -> "SoilLayerRequest":
        if self.depth_bottom_m <= self.depth_top_m:
            raise ValueError("F11-E005: depth_bottom_m debe ser mayor que depth_top_m")
        return self

    @model_validator(mode="after")
    def undrained_params(self) -> "SoilLayerRequest":
        if self.drainage_condition == DrainageCondition.UNDRAINED and self.cu_kpa is None:
            raise ValueError("F11-E005: condición UNDRAINED requiere cu_kpa")
        return self


class SoilLayerResponse(BaseModel):
    id: UUID
    layer_index: int
    depth_top_m: float
    depth_bottom_m: float
    soil_class: SoilClass
    gamma_kn_m3: Optional[float]
    phi_deg: Optional[float]
    c_kpa: Optional[float]
    cu_kpa: Optional[float]
    E_mpa: Optional[float]
    ks_kn_m3: Optional[float]
    drainage_condition: DrainageCondition
    is_conservative_estimate: bool

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Geotechnical site
# ---------------------------------------------------------------------------

class GeotechnicalSiteRequest(BaseModel):
    project_id: UUID
    geo_level: GeotechnicalLevel = GeotechnicalLevel.G0
    # Location
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)
    country_code: Optional[str] = Field(None, max_length=4)
    municipality: Optional[str] = Field(None, max_length=128)
    altitude_m: Optional[float] = Field(None, ge=-500.0, le=9000.0)
    # Site conditions
    frost_depth_m: Optional[float] = Field(None, ge=0.0, le=3.0)
    seismic_zone: Optional[str] = Field(None, max_length=32)
    environmental_class: Optional[str] = Field(None, max_length=32)
    # Water
    water_scenario: WaterScenario = WaterScenario.UNKNOWN
    water_table_depth_m: Optional[float] = Field(None, ge=0.0, le=100.0)
    water_table_seasonal_high_m: Optional[float] = Field(None, ge=0.0, le=100.0)
    # Intake flags
    surface_type: Optional[str] = None
    slope_near_m: Optional[float] = Field(None, ge=0.0, le=1000.0)
    buried_services: Optional[bool] = None
    proximity_slope: Optional[bool] = None
    # Data
    data_source: Optional[list[str]] = None
    soil_layers: Optional[list[SoilLayerRequest]] = None

    @model_validator(mode="after")
    def location_for_g3(self) -> "GeotechnicalSiteRequest":
        if self.geo_level in (GeotechnicalLevel.G3, GeotechnicalLevel.G4):
            if self.latitude is None or self.longitude is None:
                raise ValueError("F11-E001: nivel G3/G4 requiere coordenadas GPS")
        return self

    @model_validator(mode="after")
    def g1_requires_surface_type(self) -> "GeotechnicalSiteRequest":
        if self.geo_level != GeotechnicalLevel.G0 and self.surface_type is None:
            raise ValueError("F11-E001: niveles G1+ requieren surface_type")
        return self


class GeotechnicalSiteResponse(BaseModel):
    id: UUID
    project_id: UUID
    geo_level: GeotechnicalLevel
    latitude: Optional[float]
    longitude: Optional[float]
    water_scenario: WaterScenario
    water_table_depth_m: Optional[float]
    blockers: Optional[list[str]]
    warnings: Optional[list[str]]
    confirmed_fields: Optional[list[str]]
    calc_hash: Optional[str]
    soil_layers: list[SoilLayerResponse] = []

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Foundation candidate
# ---------------------------------------------------------------------------

class FoundationCandidateRequest(BaseModel):
    site_id: UUID
    family: FoundationFamily
    width_m: Optional[float] = Field(None, ge=0.2, le=10.0)
    length_m: Optional[float] = Field(None, ge=0.2, le=10.0)
    depth_m: Optional[float] = Field(None, ge=0.1, le=5.0)
    diameter_m: Optional[float] = Field(None, ge=0.2, le=5.0)
    pedestal_width_m: Optional[float] = Field(None, ge=0.05, le=2.0)
    pedestal_height_m: Optional[float] = Field(None, ge=0.0, le=2.0)
    fck_mpa: float = Field(default=25.0, ge=12.0, le=90.0)
    # Design actions
    N_kn: Optional[float] = None
    My_knm: Optional[float] = None
    Mz_knm: Optional[float] = None
    Vy_kn: Optional[float] = None
    Vz_kn: Optional[float] = None
    T_knm: Optional[float] = None
    governing_combination: Optional[str] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def circular_needs_diameter(self) -> "FoundationCandidateRequest":
        if self.family in (FoundationFamily.F11_D, FoundationFamily.F11_E):
            if self.diameter_m is None:
                raise ValueError("F11-E005: familias F11-D/E requieren diameter_m")
        return self

    @model_validator(mode="after")
    def rectangular_needs_both_dims(self) -> "FoundationCandidateRequest":
        if self.family in (FoundationFamily.F11_A, FoundationFamily.F11_B,
                           FoundationFamily.F11_C, FoundationFamily.F11_G):
            if self.width_m is None:
                raise ValueError("F11-E005: familia requiere width_m")
            if self.depth_m is None:
                raise ValueError("F11-E005: familia requiere depth_m")
        return self

    @model_validator(mode="after")
    def pile_route_blocked(self) -> "FoundationCandidateRequest":
        # F11-H requires mandatory geotechnical study (G3+), validated elsewhere
        return self


class FoundationCandidateResponse(BaseModel):
    id: UUID
    family: FoundationFamily
    status: FoundationCandidateStatus
    maturity_level: FoundationMaturityLevel
    width_m: Optional[float]
    length_m: Optional[float]
    depth_m: Optional[float]
    diameter_m: Optional[float]
    fck_mpa: float
    util_bearing: Optional[float]
    util_overturning: Optional[float]
    util_sliding: Optional[float]
    util_uplift: Optional[float]
    util_governing: Optional[float]
    governing_mode: Optional[str]
    total_cost_eur: Optional[float]
    total_co2_kg: Optional[float]
    is_recommended: bool
    label: Optional[str]
    calc_hash: Optional[str]

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Foundation check
# ---------------------------------------------------------------------------

class FoundationCheckResponse(BaseModel):
    id: UUID
    combination_id: str
    check_mode: FoundationCheckMode
    demand: Optional[float]
    resistance: Optional[float]
    utilization: Optional[float]
    governing: bool
    norm_clause: Optional[str]
    factors: Optional[dict[str, Any]]
    error_codes: Optional[list[str]]

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Stiffness
# ---------------------------------------------------------------------------

class FoundationStiffnessRequest(BaseModel):
    stiffness_model: StiffnessModel = StiffnessModel.ELASTIC_LINEAR
    override_kz: Optional[float] = Field(None, ge=0.0)
    override_kx: Optional[float] = Field(None, ge=0.0)
    override_ky: Optional[float] = Field(None, ge=0.0)
    override_kthx: Optional[float] = Field(None, ge=0.0)
    override_kthy: Optional[float] = Field(None, ge=0.0)
    override_kthz: Optional[float] = Field(None, ge=0.0)


class FoundationStiffnessResponse(BaseModel):
    id: UUID
    stiffness_model: StiffnessModel
    kz_kn_m: Optional[float]
    kx_kn_m: Optional[float]
    ky_kn_m: Optional[float]
    kthx_knm_rad: Optional[float]
    kthy_knm_rad: Optional[float]
    kthz_knm_rad: Optional[float]
    matrix_6x6: Optional[list[list[float]]]
    converged: Optional[bool]
    iterations: Optional[int]

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Embedded pole
# ---------------------------------------------------------------------------

class EmbeddedPoleRequest(BaseModel):
    pole_diameter_mm: float = Field(..., ge=50.0, le=1000.0)
    block_diameter_m: Optional[float] = Field(None, ge=0.2, le=5.0)
    embedment_length_m: float = Field(..., ge=0.3, le=5.0)
    fill_type: EmbedmentFill = EmbedmentFill.CONCRETE
    has_bottom_drain: bool = False
    corrosion_protection: Optional[str] = None

    @field_validator("embedment_length_m")
    @classmethod
    def min_embedment_ratio(cls, v: float, info: Any) -> float:
        # Will be cross-checked with pole diameter in service
        return v


class EmbeddedPoleResponse(BaseModel):
    id: UUID
    pole_diameter_mm: float
    embedment_length_m: float
    fill_type: EmbedmentFill
    passive_pressure_kpa: Optional[float]
    reaction_top_kn: Optional[float]
    reaction_bottom_kn: Optional[float]
    moment_at_surface_knm: Optional[float]
    util_lateral: Optional[float]
    util_toe: Optional[float]

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Optimization
# ---------------------------------------------------------------------------

class OptimizationWeights(BaseModel):
    w_cost: float = Field(default=0.4, ge=0.0, le=1.0)
    w_co2: float = Field(default=0.3, ge=0.0, le=1.0)
    w_excavation: float = Field(default=0.2, ge=0.0, le=1.0)
    w_risk: float = Field(default=0.1, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def weights_sum(self) -> "OptimizationWeights":
        total = self.w_cost + self.w_co2 + self.w_excavation + self.w_risk
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"F11-E010: pesos deben sumar 1.0, suman {total:.4f}")
        return self


class OptimizationRequest(BaseModel):
    weights: OptimizationWeights = OptimizationWeights()
    max_candidates: int = Field(default=5, ge=1, le=20)


class OptimizationResult(BaseModel):
    candidate_id: UUID
    family: FoundationFamily
    label: str
    total_cost_eur: Optional[float]
    total_co2_kg: Optional[float]
    excavation_volume_m3: Optional[float]
    util_governing: Optional[float]
    score: float


class OptimizationResponse(BaseModel):
    results: list[OptimizationResult]
    pareto_count: int
    dominated_count: int


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

class FoundationEvidenceRequest(BaseModel):
    evidence_type: EvidenceType
    description: str = Field(..., min_length=5)
    reference: Optional[str] = None
    file_ref: Optional[str] = None
    approved_by: Optional[str] = None
    geo_level_at_approval: Optional[GeotechnicalLevel] = None


# ---------------------------------------------------------------------------
# Release
# ---------------------------------------------------------------------------

class ReleaseRequest(BaseModel):
    candidate_id: UUID
    approver: str = Field(..., min_length=2)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def approver_not_empty(self) -> "ReleaseRequest":
        if not self.approver.strip():
            raise ValueError("F11-E011: approver no puede estar vacío")
        return self


class ReleaseResponse(BaseModel):
    candidate_id: UUID
    status: FoundationCandidateStatus
    maturity_level: FoundationMaturityLevel
    blockers: list[str]
    warnings: list[str]
    approved: bool


# ---------------------------------------------------------------------------
# Generate candidates request
# ---------------------------------------------------------------------------

class GenerateCandidatesRequest(BaseModel):
    site_id: UUID
    families: Optional[list[FoundationFamily]] = None  # None = all applicable
    N_kn: float = Field(..., description="Axial force from column base, negative=compression")
    My_knm: float = Field(default=0.0)
    Mz_knm: float = Field(default=0.0)
    Vy_kn: float = Field(default=0.0)
    Vz_kn: float = Field(default=0.0)
    T_knm: float = Field(default=0.0)
    governing_combination: Optional[str] = None
    max_width_m: float = Field(default=2.0, ge=0.3, le=8.0)
    max_depth_m: float = Field(default=2.0, ge=0.3, le=5.0)
    fck_mpa: float = Field(default=25.0, ge=12.0, le=90.0)


class GlobalModelIterateRequest(BaseModel):
    candidate_id: UUID
    phase4_stiffness_kthx: Optional[float] = None
    phase4_stiffness_kthy: Optional[float] = None
    phase4_stiffness_kz: Optional[float] = None
    tolerance: float = Field(default=0.05, ge=0.001, le=0.5)
    max_iterations: int = Field(default=10, ge=1, le=50)
