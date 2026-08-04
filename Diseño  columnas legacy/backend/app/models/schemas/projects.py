"""
Salvi Studio · Columns — Schemas Pydantic para proyectos
Toda magnitud incluye value + unit (P-06, sección 10 Fase 1).
"""
import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.security import MaturityLevel, ProjectStatus


# ── Proyecto ────────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str = Field(..., max_length=180)
    country: str = Field(..., min_length=2, max_length=2, description="ISO 3166-1 alpha-2")
    language: str = Field(default="es", pattern="^(es|en|fr|ca|it|pt)$")
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    timezone: str = Field(default="Europe/Madrid")
    confidentiality: str = Field(default="internal", pattern="^(internal|restricted|client)$")
    description: Optional[str] = None
    customer_id: Optional[uuid.UUID] = None
    opportunity_ref: Optional[str] = Field(default=None, max_length=120)
    region: Optional[str] = Field(default=None, max_length=80)
    cloned_from_id: Optional[uuid.UUID] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=180)
    description: Optional[str] = None
    customer_id: Optional[uuid.UUID] = None
    opportunity_ref: Optional[str] = Field(default=None, max_length=120)
    confidentiality: Optional[str] = Field(default=None, pattern="^(internal|restricted|client)$")
    region: Optional[str] = Field(default=None, max_length=80)


class ProjectRead(BaseModel):
    id: uuid.UUID
    project_code: str
    name: str
    country: str
    language: str
    currency: str
    timezone: str
    confidentiality: str
    status: ProjectStatus
    maturity: MaturityLevel
    owner_user_id: uuid.UUID
    customer_id: Optional[uuid.UUID]
    opportunity_ref: Optional[str]
    description: Optional[str]
    region: Optional[str]
    cloned_from_id: Optional[uuid.UUID]
    created_at: datetime
    updated_at: datetime
    archived_at: Optional[datetime]

    model_config = {"from_attributes": True}


class ProjectStatusTransition(BaseModel):
    """Solicitud de cambio de estado con razón obligatoria."""
    target_status: ProjectStatus
    reason: str = Field(..., min_length=1, max_length=1000)


class ProjectMaturityTransition(BaseModel):
    """Solicitud de cambio de nivel de madurez."""
    target_maturity: MaturityLevel
    reason: str = Field(..., min_length=1, max_length=1000)
    validation_comment: Optional[str] = None  # Obligatorio para M3


# ── Escenario ───────────────────────────────────────────────────────────────

class ScenarioCreate(BaseModel):
    name: str = Field(..., max_length=180)
    description: Optional[str] = None
    site_id: Optional[uuid.UUID] = None
    is_base: bool = False
    cloned_from_id: Optional[uuid.UUID] = None


class ScenarioRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: Optional[str]
    status: str
    is_base: bool
    site_id: Optional[uuid.UUID]
    cloned_from_id: Optional[uuid.UUID]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Revisión ─────────────────────────────────────────────────────────────────

class RevisionCreate(BaseModel):
    revision_code: str = Field(..., max_length=16, description="Ej: R00, D1, C00")
    revision_type: str = Field(
        default="draft",
        pattern="^(draft|technical|client|production|as_built)$"
    )
    description: Optional[str] = None
    change_summary: Optional[str] = None


class RevisionRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    revision_code: str
    revision_type: str
    maturity: MaturityLevel
    description: Optional[str]
    change_summary: Optional[str]
    is_frozen: bool
    frozen_at: Optional[datetime]
    frozen_by_id: Optional[uuid.UUID]
    validated_at: Optional[datetime]
    validated_by_id: Optional[uuid.UUID]
    input_hash: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class RevisionFreezeRequest(BaseModel):
    """
    Congelar una revisión — P-01.
    Una vez congelada, ninguna modificación es posible: cambios crean nueva revisión.
    """
    change_summary: str = Field(..., min_length=1, max_length=2000)
    maturity: MaturityLevel


class RevisionValidateRequest(BaseModel):
    """Validación OT — transición a M3."""
    validation_comment: str = Field(..., min_length=1, max_length=2000)
    accept: bool = True  # False = rechazar con observaciones


# ── Respuestas paginadas ─────────────────────────────────────────────────────

class PaginatedProjects(BaseModel):
    items: List[ProjectRead]
    total: int
    page: int
    page_size: int
    pages: int


class PaginatedRevisions(BaseModel):
    items: List[RevisionRead]
    total: int
    page: int
    page_size: int
    pages: int
