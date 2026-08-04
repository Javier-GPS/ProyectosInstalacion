"""
Salvi Studio · Columns — Tipos base reutilizables para modelos SQLAlchemy
"""
import uuid
from typing import Annotated
from sqlalchemy import String, Text
from sqlalchemy.orm import mapped_column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

# UUID como clave primaria estándar
UUIDPk = Annotated[
    uuid.UUID,
    mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
]

# Código humano legible (ej: "COL-2026-0042")
CodeStr = Annotated[str, mapped_column(String(64), nullable=False)]

# Texto corto (nombres, etiquetas)
ShortStr = Annotated[str, mapped_column(String(180), nullable=False)]

# Texto largo (descripciones, notas)
LongText = Annotated[str, mapped_column(Text, nullable=True)]
