"""Zone and road-planning schemas."""
from typing import Annotated, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


class GisCreateZoneBody(BaseModel):
    id: Optional[str] = None
    name: str = "Zona"
    type: str = ""
    color: Optional[str] = None
    priority: int = 2
    center_lat: Optional[float] = None
    center_lon: Optional[float] = None
    zoom: int = 12
    bbox: str = ""
    description: str = ""
    est: dict = {}
    corridors: list = []
    bounds_polygon: list | dict = []
    source: str = "manual"
    project_id: Optional[int] = None
    osm_relation: Optional[int] = None
    center: list = []


LightingClass = Literal[
    "M1", "M2", "M3", "M4", "M5", "M6",
    "C0", "C1", "C2", "C3", "C4", "C5",
    "P1", "P2", "P3", "P4", "P5", "P6", "P7",
]
Distribution = Literal[
    "unilateral_r", "unilateral_l", "bilateral_pareado",
    "bilateral_tresbolillo", "centrada_mediana", "mediana_compartida",
]
ShortText = Annotated[str, StringConstraints(min_length=1, max_length=256, pattern=r".*\S.*", strict=True)]
FiniteNumber = Annotated[float, Field(allow_inf_nan=False, strict=True)]
NonNegativeNumber = Annotated[float, Field(allow_inf_nan=False, strict=True, ge=0)]
PercentageNumber = Annotated[float, Field(allow_inf_nan=False, strict=True, ge=0, le=100)]


class GisLuxParamsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    poleH: Optional[NonNegativeNumber] = None
    armLen: Optional[NonNegativeNumber] = None
    setback: Optional[NonNegativeNumber] = None
    tilt: Optional[FiniteNumber] = None
    sidewalkL: Optional[NonNegativeNumber] = None
    sidewalkR: Optional[NonNegativeNumber] = None
    medianW: Optional[NonNegativeNumber] = None
    maintFactor: Optional[NonNegativeNumber] = None
    brand: Optional[ShortText] = None
    range: Optional[ShortText] = None
    diffuser: Optional[ShortText] = None
    optic: Optional[ShortText] = None
    ledType: Optional[ShortText] = None
    power: Optional[NonNegativeNumber] = None
    colorTemp: Optional[NonNegativeNumber] = None
    cri: Optional[PercentageNumber] = None


class GisPlanningPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lighting_class: Optional[LightingClass] = None
    spacing: Optional[NonNegativeNumber] = None
    distribution: Optional[Distribution] = None
    luxParams: Optional[GisLuxParamsPatch] = None


class GisPlanningPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_defaults: dict[str, GisPlanningPatch] = Field(default_factory=dict)
    target_overrides: dict[str, GisPlanningPatch] = Field(default_factory=dict)


class GisPlanningDraftPut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["update", "recreate"] = "update"
    confirm: bool = False
    schema_version: Literal[1] = 1
    base_inventory_hash: str = Field(pattern=r"^(sha256:[0-9a-f]{64}|md5:[0-9a-f]{32})$")
    payload: GisPlanningPayload

    @model_validator(mode="after")
    def validate_recreate(self):
        if self.mode == "recreate" and (
            not self.confirm or self.payload.group_defaults or self.payload.target_overrides
        ):
            raise ValueError("recreate requires confirmation and an empty payload")
        return self


class GisRoadScopeAnchor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_ref: ShortText
    segment_index: int = Field(strict=True, ge=0)
    segment_t: float = Field(strict=True, allow_inf_nan=False, ge=0, le=1)


class GisRoadScopePut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    base_inventory_hash: str = Field(pattern=r"^(sha256:[0-9a-f]{64}|md5:[0-9a-f]{32})$")
    boundary: dict
    allowed_group_refs: list[ShortText] = Field(min_length=1, max_length=50)
    a: GisRoadScopeAnchor
    b: GisRoadScopeAnchor

    @model_validator(mode="after")
    def validate_groups(self):
        if len(set(self.allowed_group_refs)) != len(self.allowed_group_refs):
            raise ValueError("allowed_group_refs must be unique")
        return self


class GisRoutePreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_inventory_hash: str = Field(pattern=r"^(sha256:[0-9a-f]{64}|md5:[0-9a-f]{32})$")
    a: GisRoadScopeAnchor
    b: GisRoadScopeAnchor
    allowed_group_refs: Optional[list[ShortText]] = None


# GisImportInventoryBody lives in schemas/luminaires.py (shared)
