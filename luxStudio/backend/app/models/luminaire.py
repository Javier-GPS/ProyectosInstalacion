from datetime import datetime, timezone
from sqlalchemy import ForeignKey, String, Float, Integer, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class Manufacturer(Base):
    __tablename__ = "manufacturers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    fotometrias: Mapped[list["Fotometria"]] = relationship(
        "Fotometria", back_populates="manufacturer", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Manufacturer {self.name}>"


class Fotometria(Base):
    """Catálogo de fotometrías.

    Tabla ``fotometrias`` con columnas normalizadas del catálogo y
    referencias a las dimensiones ``gama``, ``difusor``, ``lente``,
    ``led_type``.
    """

    __tablename__ = "fotometrias"
    __table_args__ = (
        UniqueConstraint("fotometria", name="uq_fotometrias_fotometria"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    manufacturer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("manufacturers.id"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    optic_family: Mapped[str] = mapped_column(String(50), nullable=False)
    gama_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("gamas.id", ondelete="RESTRICT"), nullable=True
    )
    difusor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("difusores.id", ondelete="RESTRICT"), nullable=True
    )
    lente_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("lentes.id", ondelete="RESTRICT"), nullable=True
    )
    led_type_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("led_types.id", ondelete="RESTRICT"), nullable=True
    )
    fotometria: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    power: Mapped[float] = mapped_column(Float, nullable=False)
    cct: Mapped[int] = mapped_column(Integer, nullable=False)
    cri: Mapped[int] = mapped_column(Integer, nullable=False, default=70)
    flux: Mapped[float] = mapped_column(Float, nullable=False)
    efficiency: Mapped[float] = mapped_column(Float, nullable=False)
    LORL: Mapped[float] = mapped_column(Float, nullable=False)
    isym: Mapped[int] = mapped_column(Integer, nullable=False)
    photometric_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mf_origen: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0,
        doc="Maintenance factor baked into the LDT candela values. "
            "Salvi LDTs are exported at LOR=1.0 (no MF applied), so the "
            "default is 1.0 and the user-supplied config.mf is applied "
            "verbatim. Set explicitly only for LDTs that already have a "
            "depreciation factor baked into the cd values.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    manufacturer: Mapped["Manufacturer"] = relationship(
        "Manufacturer", back_populates="fotometrias"
    )
    gama: Mapped["Gama | None"] = relationship("Gama", back_populates="fotometrias")
    difusor: Mapped["Difusor | None"] = relationship("Difusor", back_populates="fotometrias")
    lente: Mapped["Lente | None"] = relationship("Lente", back_populates="fotometrias")
    led_type: Mapped["LedType | None"] = relationship("LedType", back_populates="fotometrias")

    def __repr__(self) -> str:
        return f"<Fotometria {self.name} ({self.manufacturer.name} {self.type})>"
