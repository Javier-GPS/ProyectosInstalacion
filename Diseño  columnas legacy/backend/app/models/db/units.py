"""
Salvi Studio · Columns — Servicio de unidades y magnitudes
Fase 1, sección 10.

P-06: Almacenamiento interno en SI. La presentación usa unidades configurables.
Regla: toda magnitud en API incluye value, unit y opcionalmente sourcePrecision.
"""
from enum import Enum
from dataclasses import dataclass
from typing import Optional


class PhysicalDimension(str, Enum):
    """Dimensiones físicas con sus unidades SI internas."""
    LENGTH = "length"               # m
    AREA = "area"                   # m²
    VOLUME = "volume"               # m³
    MASS = "mass"                   # kg
    FORCE = "force"                 # N
    MOMENT = "moment"               # N·m
    STRESS = "stress"               # Pa
    PRESSURE = "pressure"           # Pa
    DENSITY = "density"             # kg/m³
    VELOCITY = "velocity"           # m/s
    ANGLE = "angle"                 # rad
    TEMPERATURE = "temperature"     # K
    ENERGY = "energy"               # J
    DIMENSIONLESS = "dimensionless"
    COST = "cost"                   # moneda base
    CO2 = "co2"                     # kgCO2e


# Unidad SI interna por dimensión
SI_UNIT: dict[PhysicalDimension, str] = {
    PhysicalDimension.LENGTH: "m",
    PhysicalDimension.AREA: "m²",
    PhysicalDimension.VOLUME: "m³",
    PhysicalDimension.MASS: "kg",
    PhysicalDimension.FORCE: "N",
    PhysicalDimension.MOMENT: "N·m",
    PhysicalDimension.STRESS: "Pa",
    PhysicalDimension.PRESSURE: "Pa",
    PhysicalDimension.DENSITY: "kg/m³",
    PhysicalDimension.VELOCITY: "m/s",
    PhysicalDimension.ANGLE: "rad",
    PhysicalDimension.TEMPERATURE: "K",
    PhysicalDimension.ENERGY: "J",
    PhysicalDimension.DIMENSIONLESS: "-",
    PhysicalDimension.COST: "EUR",
    PhysicalDimension.CO2: "kgCO2e",
}

# Factores de conversión → SI (multiplicar por factor para obtener SI)
CONVERSION_FACTORS: dict[str, float] = {
    # Longitud
    "mm": 1e-3, "cm": 1e-2, "m": 1.0,
    # Área
    "mm²": 1e-6, "cm²": 1e-4, "m²": 1.0,
    # Masa
    "g": 1e-3, "kg": 1.0, "t": 1e3,
    # Fuerza
    "N": 1.0, "kN": 1e3, "MN": 1e6,
    # Momento
    "N·m": 1.0, "kN·m": 1e3,
    # Tensión / Presión
    "Pa": 1.0, "kPa": 1e3, "MPa": 1e6, "N/mm²": 1e6, "GPa": 1e9, "bar": 1e5,
    # Velocidad
    "m/s": 1.0, "km/h": 1/3.6,
    # Ángulo
    "rad": 1.0, "°": 3.141592653589793 / 180.0,
    # Temperatura (offset gestionado aparte)
    "K": 1.0,
    # Energía
    "J": 1.0, "Wh": 3600.0, "kWh": 3.6e6,
    # CO2
    "kgCO2e": 1.0, "tCO2e": 1e3,
}


@dataclass
class Quantity:
    """
    Magnitud física con valor, unidad y metadatos de trazabilidad.
    Sección 10, Fase 1 — toda magnitud en API incluye value, unit.
    Las comparaciones de cumplimiento usan value_si (no redondeado).
    """
    value_si: float                           # Valor en unidad SI interna
    dimension: PhysicalDimension
    source_unit: str                          # Unidad en que fue introducido
    source_value: Optional[float] = None     # Valor original antes de conversión
    source_precision: Optional[int] = None   # Decimales significativos originales
    origin: Optional[str] = None             # "user_input", "calculated", "imported", etc.

    @property
    def si_unit(self) -> str:
        return SI_UNIT[self.dimension]

    def to_unit(self, target_unit: str) -> float:
        """Convierte el valor SI a la unidad solicitada para presentación."""
        if target_unit == "°C" and self.dimension == PhysicalDimension.TEMPERATURE:
            return self.value_si - 273.15
        factor = CONVERSION_FACTORS.get(target_unit)
        if factor is None:
            raise ValueError(f"Unidad desconocida: {target_unit}")
        return self.value_si / factor

    @classmethod
    def from_user_input(
        cls,
        value: float,
        unit: str,
        dimension: PhysicalDimension,
        precision: Optional[int] = None,
    ) -> "Quantity":
        """Crea una Quantity a partir de la entrada del usuario (no SI)."""
        if unit == "°C" and dimension == PhysicalDimension.TEMPERATURE:
            value_si = value + 273.15
        else:
            factor = CONVERSION_FACTORS.get(unit)
            if factor is None:
                raise ValueError(f"Unidad desconocida para conversión: {unit}")
            value_si = value * factor
        return cls(
            value_si=value_si,
            dimension=dimension,
            source_unit=unit,
            source_value=value,
            source_precision=precision,
            origin="user_input",
        )
