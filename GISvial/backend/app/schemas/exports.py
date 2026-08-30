"""Export schemas (DXF, plantilla)."""
from typing import Any
from pydantic import BaseModel


class GisDxfRoad(BaseModel):
    name: str | None = None
    type: str = "road"
    estWidth: float | None = None
    geom: list[dict[str, float]] = []  # [{lon, lat}, ...]


class GisDxfObject(BaseModel):
    type: str = "farola"
    lng: float
    lat: float
    width: float = 1.0
    length: float = 1.0
    rotation: float = 0.0
    label: str | None = None


class GisDxfExportRequest(BaseModel):
    zone_id: str
    roads: list[GisDxfRoad] = []
    objects: list[GisDxfObject] = []
    boundary: list[Any] = []
