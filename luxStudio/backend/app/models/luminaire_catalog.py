"""Catalog tables for LED / PCB / driver and the 4-tuple -> LED binding.

These back the hard power cap that the configurator applies on every
``Tramo``:
- A 4-tuple ``(gama, difusor, lente, led_type)`` is resolved through
  ``LuminaireLED`` to exactly one ``LED`` (the highest-cap one if the
  4-tuple has several build options in the source xlsx).
- The selected ``LED.pmax_ajustada`` becomes the upper bound for the
  user-selectable power; the slider clamps to it and the backend
  rejects any calculation request that exceeds it.

PCB and driver tables are kept for diagnostic / reporting purposes and
are intentionally **not** used to compute the power cap.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class LED(Base):
    """A single LED catalog entry from ``Param_ Configura``.

    ``pmax_lum`` is the LED's theoretical maximum, ``pmax_ajustada`` is
    the conservative ceiling (typically 88 % of the theoretical
    maximum) that the configurator enforces.
    """

    __tablename__ = "leds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    led_ref: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    led_desc_corta: Mapped[str | None] = mapped_column(String(255), nullable=True)
    led_tipo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pmax_lum: Mapped[float | None] = mapped_column(Float, nullable=True)
    i_max_led: Mapped[float | None] = mapped_column(Float, nullable=True)
    pmax_ajustada: Mapped[float | None] = mapped_column(Float, nullable=True)
    # LUXEON 5050 model fields (see docs/modelo_completo_flujo_led_luxeon5050_todas_referencias_v2_con_rs.md).
    # ``family`` ties the row to one of the 9 catalog families (HE_PLUS_6V, …);
    # the V2 model uses it to look up the I-V curve, Rs, Rth and the Vf temperature
    # coefficient.  ``part_number`` is the Lumileds partNumber, kept for traceability
    # though not used for the flux lookup.
    family: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    flux_ref_lm: Mapped[float | None] = mapped_column(Float, nullable=True)
    cct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cri: Mapped[int | None] = mapped_column(Integer, nullable=True)
    part_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    same_drive_flux_lm: Mapped[float | None] = mapped_column(Float, nullable=True)
    technology: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    luminaire_bindings: Mapped[list["LuminaireLED"]] = relationship(
        "LuminaireLED", back_populates="led", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<LED {self.led_ref} pmax_ajustada={self.pmax_ajustada}>"


class PCB(Base):
    """A single PCB catalog entry. Stored for diagnostics only."""

    __tablename__ = "pcbs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pcb_ref: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    pcb_no_drivers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pcb_v_nominal: Mapped[float | None] = mapped_column(Float, nullable=True)
    pcb_no_led: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pcb_no_circuitos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pcb_imax_led: Mapped[float | None] = mapped_column(Float, nullable=True)
    pcb_descripcion: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    luminaire_bindings: Mapped[list["LuminaireLED"]] = relationship(
        "LuminaireLED", back_populates="pcb", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<PCB {self.pcb_ref}>"


class Driver(Base):
    """A single driver catalog entry. Stored for diagnostics only."""

    __tablename__ = "drivers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dr_ref: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    dr_pot_max_driver: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return f"<Driver {self.dr_ref}>"


class LuminaireLED(Base):
    """Binding between a 4-tuple ``(gama, difusor, lente, led_type)`` and a single LED.

    Uniqueness is enforced on the 4-tuple (``uq_luminaire_leds_4tuple``).
    If a 4-tuple resolves to several ``LED_REF``s in the source xlsx,
    the seed keeps the LED with the highest ``pmax_ajustada`` because
    that value indicates the maximum supported build, and emits a
    warning so the operator can audit the choice.
    """

    __tablename__ = "luminaire_leds"
    __table_args__ = (
        UniqueConstraint(
            "gama_id", "difusor_id", "lente_id", "led_type_id",
            name="uq_luminaire_leds_4tuple",
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
    led_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("leds.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    n_pcbs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    n_leds_per_pcb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pcb_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("pcbs.id", ondelete="SET NULL"), nullable=True)

    gama: Mapped["Gama"] = relationship("Gama")
    difusor: Mapped["Difusor"] = relationship("Difusor")
    lente: Mapped["Lente"] = relationship("Lente")
    led_type: Mapped["LedType | None"] = relationship("LedType")
    led: Mapped["LED"] = relationship("LED", back_populates="luminaire_bindings")
    pcb: Mapped["PCB | None"] = relationship("PCB", back_populates="luminaire_bindings")

    def __repr__(self) -> str:
        return (
            f"<LuminaireLED gama_id={self.gama_id} difusor_id={self.difusor_id} "
            f"lente_id={self.lente_id} led_type_id={self.led_type_id} led_id={self.led_id}>"
        )


class GamaPCB(Base):
    """Available PCB options for a gama (from motor_configurador Excel)."""

    __tablename__ = "gama_pcbs"
    __table_args__ = (
        UniqueConstraint("gama_id", "pcb_id", name="uq_gama_pcbs"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gama_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("gamas.id", ondelete="CASCADE"), nullable=False
    )
    pcb_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pcbs.id", ondelete="CASCADE"), nullable=False
    )

    gama: Mapped["Gama"] = relationship("Gama")
    pcb: Mapped["PCB"] = relationship("PCB")

    def __repr__(self) -> str:
        return f"<GamaPCB gama_id={self.gama_id} pcb_id={self.pcb_id}>"


class TSCoefficient(Base):
    """Solder-pad thermal coefficient (°C/W) per ``(gama, difusor)``.

    Used to estimate ``Tsp = T_amb + coef_led_c_per_w × P_luminaire``
    (see ``docs/TablaTS.xlsx``).  Only rows that have a coefficient
    are queryable; missing rows raise an error in the flux endpoint
    so the operator is forced to populate them before running a
    calculation.
    """

    __tablename__ = "ts_coefficients"
    __table_args__ = (
        UniqueConstraint("gama_id", "difusor_id", name="uq_ts_coefficients_pair"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gama_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("gamas.id", ondelete="CASCADE"), nullable=False
    )
    difusor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("difusores.id", ondelete="CASCADE"), nullable=False
    )
    coef_led_c_per_w: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    gama: Mapped["Gama"] = relationship("Gama")
    difusor: Mapped["Difusor"] = relationship("Difusor")

    def __repr__(self) -> str:
        return (
            f"<TSCoefficient gama_id={self.gama_id} difusor_id={self.difusor_id} "
            f"coef={self.coef_led_c_per_w}>"
        )
