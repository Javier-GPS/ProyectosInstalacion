from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class Gama(Base):
    """Catálogo de gamas (modelos) de fotometría.

    Cada ``Fotometria`` existente en la base de datos referencia exactamente
    una gama. Los valores se siembran desde ``BBDD_Fotometrias.xlsx`` o
    desde los nombres de archivo de los LDT legacy.
    """

    __tablename__ = "gamas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    fotometrias: Mapped[list["Fotometria"]] = relationship("Fotometria", back_populates="gama")

    def __repr__(self) -> str:
        return f"<Gama {self.name}>"


class Difusor(Base):
    """Catálogo de difusores."""

    __tablename__ = "difusores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    eficiencia: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    fotometrias: Mapped[list["Fotometria"]] = relationship("Fotometria", back_populates="difusor")

    def __repr__(self) -> str:
        return f"<Difusor {self.name}>"


class Lente(Base):
    """Catálogo de lentes / familias ópticas (F151, F2M2, ...)."""

    __tablename__ = "lentes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    eficiencia: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    fotometrias: Mapped[list["Fotometria"]] = relationship("Fotometria", back_populates="lente")

    def __repr__(self) -> str:
        return f"<Lente {self.name}>"


class LedType(Base):
    """Catálogo de tipos de LED."""

    __tablename__ = "led_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    fotometrias: Mapped[list["Fotometria"]] = relationship("Fotometria", back_populates="led_type")

    def __repr__(self) -> str:
        return f"<LedType {self.name}>"


class ValidCombination(Base):
    """Combinación (gama, difusor, lente, led_type) que sabemos que es válida.

    Se siembra a partir de las filas de ``BBDD_Fotometrias.xlsx``. Cualquier
    ``Fotometria`` (futuro) debe pertenecer a una fila de esta tabla — el
    catálogo no admite combinaciones arbitrarias.
    """

    __tablename__ = "valid_combinations"
    __table_args__ = (
        UniqueConstraint(
            "gama_id", "difusor_id", "lente_id", "led_type_id",
            name="uq_valid_combinations",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gama_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("gamas.id", ondelete="CASCADE"), nullable=False
    )
    difusor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("difusores.id", ondelete="CASCADE"), nullable=False
    )
    lente_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lentes.id", ondelete="CASCADE"), nullable=False
    )
    led_type_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("led_types.id", ondelete="CASCADE"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    gama: Mapped["Gama"] = relationship("Gama")
    difusor: Mapped["Difusor"] = relationship("Difusor")
    lente: Mapped["Lente"] = relationship("Lente")
    led_type: Mapped["LedType | None"] = relationship("LedType")

    def __repr__(self) -> str:
        return (
            f"<ValidCombination gama={self.gama_id} difusor={self.difusor_id} "
            f"lente={self.lente_id} led_type={self.led_type_id}>"
        )


# Re-export para evitar import circular con Fotometria.
from .luminaire import Fotometria  # noqa: E402
