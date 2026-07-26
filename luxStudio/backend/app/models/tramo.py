from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class Tramo(Base):
    __tablename__ = "tramos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_section_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("tramos.id", ondelete="CASCADE"), nullable=True)
    base_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    variant_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_calculated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    project: Mapped["Project"] = relationship("Project")
    parent: Mapped["Tramo | None"] = relationship("Tramo", remote_side=[id])
    documents: Mapped[list["TramoDocument"]] = relationship(
        "TramoDocument", back_populates="tramo", cascade="all, delete-orphan"
    )


class TramoDocument(Base):
    __tablename__ = "tramo_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tramo_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tramos.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    document_type: Mapped[str] = mapped_column(String(20), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    tramo: Mapped[Tramo] = relationship("Tramo", back_populates="documents")
