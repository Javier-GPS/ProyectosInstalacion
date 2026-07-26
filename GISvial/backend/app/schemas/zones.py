"""Zone schemas."""
from typing import Optional
from pydantic import BaseModel


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
    bounds_polygon: list = []
    source: str = "manual"
    project_id: Optional[int] = None
    osm_relation: Optional[int] = None
    center: list = []


class GisImportInventoryBody(BaseModel):
    temp_id: str
    mapping: dict
    zone_name: str = "Nueva zona"
    project_id: Optional[int] = None
    color: str = "#4caf82"
