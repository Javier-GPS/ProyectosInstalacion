"""
Salvi Studio · Columns — API v1: Servicio de unidades
P-06: almacenamiento interno SI; conversión para presentación.
Sección 10, Fase 1.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.models.db.units import (
    Quantity, PhysicalDimension, SI_UNIT, CONVERSION_FACTORS
)

router = APIRouter(prefix="/units", tags=["units"])


class ConvertRequest(BaseModel):
    value: float
    from_unit: str
    to_unit: str
    dimension: PhysicalDimension


class ConvertResponse(BaseModel):
    value_in: float
    unit_in: str
    value_out: float
    unit_out: str
    value_si: float
    unit_si: str
    dimension: str


class UnitInfo(BaseModel):
    dimension: str
    si_unit: str
    available_units: list[str]


@router.post("/convert", response_model=ConvertResponse)
def convert_units(data: ConvertRequest):
    """
    Convierte entre unidades. Internamente convierte a SI y luego a la unidad destino.
    Comparaciones de cumplimiento SIEMPRE con value_si (no redondeado).
    """
    try:
        qty = Quantity.from_user_input(data.value, data.from_unit, data.dimension)
        value_out = qty.to_unit(data.to_unit)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))

    return ConvertResponse(
        value_in=data.value,
        unit_in=data.from_unit,
        value_out=value_out,
        unit_out=data.to_unit,
        value_si=qty.value_si,
        unit_si=qty.si_unit,
        dimension=data.dimension.value,
    )


@router.get("", response_model=list[UnitInfo])
def list_units():
    """Lista todas las dimensiones físicas con sus unidades disponibles."""
    # Agrupar unidades disponibles por dimensión
    # (heurístico: buscar unidades de conversión que correspondan a cada dimensión)
    dimension_units: dict[str, list[str]] = {d.value: [] for d in PhysicalDimension}

    # Mapeo aproximado de unidades conocidas a dimensiones
    unit_dimension_map = {
        "mm": "length", "cm": "length", "m": "length",
        "mm²": "area", "cm²": "area", "m²": "area",
        "m³": "volume",
        "g": "mass", "kg": "mass", "t": "mass",
        "N": "force", "kN": "force", "MN": "force",
        "N·m": "moment", "kN·m": "moment",
        "Pa": "stress", "kPa": "stress", "MPa": "stress", "N/mm²": "stress", "GPa": "stress",
        "bar": "pressure",
        "m/s": "velocity", "km/h": "velocity",
        "rad": "angle", "°": "angle",
        "K": "temperature", "°C": "temperature",
        "J": "energy", "Wh": "energy", "kWh": "energy",
        "kgCO2e": "co2", "tCO2e": "co2",
    }

    for unit, dim in unit_dimension_map.items():
        if dim in dimension_units:
            dimension_units[dim].append(unit)

    return [
        UnitInfo(
            dimension=dim,
            si_unit=SI_UNIT.get(PhysicalDimension(dim), "?"),
            available_units=units,
        )
        for dim, units in dimension_units.items()
        if units
    ]


@router.get("/{dimension}", response_model=UnitInfo)
def get_dimension_units(dimension: PhysicalDimension):
    """Información de unidades para una dimensión física específica."""
    return UnitInfo(
        dimension=dimension.value,
        si_unit=SI_UNIT[dimension],
        available_units=[
            u for u, f in CONVERSION_FACTORS.items()
            if u != "°C"  # caso especial con offset
        ],
    )
