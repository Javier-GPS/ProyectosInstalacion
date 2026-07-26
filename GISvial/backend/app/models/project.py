"""Project model (lightweight, same projects table as LuxStudio)."""

from datetime import datetime, timezone
from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    project_name: Mapped[str] = mapped_column(String(255), nullable=False)
    client: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    designer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    study_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    calculation_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    standard: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    last_opened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    t_amb_c: Mapped[float] = mapped_column(Float, nullable=False, default=25.0)
    margen_lavg: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    i_op_ma: Mapped[float | None] = mapped_column(Float, nullable=True)
    lm_w_min: Mapped[float | None] = mapped_column(Float, nullable=True)
