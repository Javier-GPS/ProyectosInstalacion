"""
Salvi Studio · Columns — Schemas Pydantic para bibliotecas maestras
Fase 1, sección 11.
"""
import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field


class LibraryCreate(BaseModel):
    code: str = Field(..., max_length=64)
    name: str = Field(..., max_length=180)
    description: Optional[str] = None
    library_type: str = Field(
        ...,
        pattern="^(norms|materials|standard_geometries|processes|suppliers|costs|co2_factors|units_formats|templates|corporate_equipment)$"
    )
    owner_role: str = Field(..., max_length=64)


class LibraryRead(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: Optional[str]
    library_type: str
    owner_role: str
    created_at: datetime

    model_config = {"from_attributes": True}


class LibraryVersionCreate(BaseModel):
    version_number: str = Field(..., max_length=32, description="Ej: 1.0.0")
    description: Optional[str] = None
    change_notes: Optional[str] = None
    content: dict = Field(default_factory=dict)
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None


class LibraryVersionRead(BaseModel):
    id: uuid.UUID
    library_id: uuid.UUID
    version_number: str
    status: str
    description: Optional[str]
    change_notes: Optional[str]
    valid_from: Optional[datetime]
    valid_until: Optional[datetime]
    published_at: Optional[datetime]
    published_by_id: Optional[uuid.UUID]
    superseded_by_id: Optional[uuid.UUID]
    content_hash: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class LibraryVersionPublish(BaseModel):
    """Solicitud de publicación. P-07: tras publicar, inmutable."""
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    publish_notes: Optional[str] = Field(default=None, max_length=1000)


class LibraryVersionDeprecate(BaseModel):
    reason: str = Field(..., min_length=1, max_length=1000)


class MaterialCreate(BaseModel):
    code: str = Field(..., max_length=64)
    name: str = Field(..., max_length=180)
    material_family: str = Field(
        ...,
        pattern="^(steel|aluminum_extruded|aluminum_sheet|concrete|fasteners)$"
    )
    # Propiedades SI (P-06)
    yield_strength_pa: Optional[float] = Field(default=None, gt=0)
    ultimate_strength_pa: Optional[float] = Field(default=None, gt=0)
    youngs_modulus_pa: Optional[float] = Field(default=None, gt=0)
    poisson_ratio: Optional[float] = Field(default=None, ge=0, le=0.5)
    density_kg_m3: Optional[float] = Field(default=None, gt=0)
    thermal_expansion_1_k: Optional[float] = Field(default=None, gt=0)
    min_thickness_m: Optional[float] = Field(default=None, gt=0)
    max_thickness_m: Optional[float] = Field(default=None, gt=0)
    weldable: Optional[bool] = None
    co2_factor_kg_per_kg: Optional[float] = Field(default=None, ge=0)
    co2_source: Optional[str] = Field(default=None, max_length=255)
    extended_properties: Optional[dict] = None
    haz_properties: Optional[dict] = None
    applicable_standards: Optional[dict] = None
    compatible_finishes: Optional[dict] = None
    corrosion_class: Optional[str] = Field(default=None, max_length=16)


class MaterialRead(BaseModel):
    id: uuid.UUID
    library_version_id: uuid.UUID
    code: str
    name: str
    material_family: str
    yield_strength_pa: Optional[float]
    ultimate_strength_pa: Optional[float]
    youngs_modulus_pa: Optional[float]
    poisson_ratio: Optional[float]
    density_kg_m3: Optional[float]
    thermal_expansion_1_k: Optional[float]
    min_thickness_m: Optional[float]
    max_thickness_m: Optional[float]
    weldable: Optional[bool]
    co2_factor_kg_per_kg: Optional[float]
    co2_source: Optional[str]
    corrosion_class: Optional[str]

    model_config = {"from_attributes": True}
