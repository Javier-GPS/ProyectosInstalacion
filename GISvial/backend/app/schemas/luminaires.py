"""Luminaire schemas."""
from typing import Optional
from pydantic import BaseModel


class GisBulkLuminaire(BaseModel):
    project_id: Optional[int] = None
    zone_id: str
    road_type: Optional[str] = None
    lighting_class: Optional[str] = None
    street_name: Optional[str] = None
    lat: float
    lon: float
    watts: Optional[float] = None
    spacing: Optional[float] = None
    tilt: Optional[float] = None
    height_m: Optional[float] = None
    arm_len: Optional[float] = None
    distribution: Optional[str] = None


class GisPlantillaRow(BaseModel):
    name: str = ""
    description: str = ""
    road_width: float = 7.0
    sidewalk_left: float = 0.0
    sidewalk_right: float = 0.0
    lanes: int = 2
    median_width: float = 0.0
    arrangement: str = "Unilateral"
    height: float = 9.0
    spacing: float = 30.0
    arm_length: float = 1.0
    pole_offset: float = 1.0
    pole_side: str = "right"
    tilt: float = 5.0
    manufacturer: str = "Salvi"
    gama: str = "Clap M"
    difusor: str = "Vidrio ultrawhite transp plano"
    lente: str = "F151"
    led_type: str = "Luxeon HOP 5050"
    power: Optional[float] = None
    cct: int = 3000
    cri: int = 70
    lighting_class: str = "M4"
    mf: float = 0.80
    pavement: str = "R3"


class GisPlantillaRequest(BaseModel):
    zone_id: str
    rows: list[GisPlantillaRow]


class GisImportInventoryBody(BaseModel):
    temp_id: str
    mapping: dict
    zone_name: str = "Nueva zona"
    project_id: Optional[int] = None
    color: str = "#4caf82"
