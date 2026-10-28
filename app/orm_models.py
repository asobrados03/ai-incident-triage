from datetime import datetime

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IncidentORM(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(5000), nullable=False)
    steps_to_reproduce: Mapped[str | None] = mapped_column(String(5000))
    expected_behavior: Mapped[str | None] = mapped_column(String(2000))
    actual_behavior: Mapped[str | None] = mapped_column(String(2000))
    environment: Mapped[str | None] = mapped_column(String(1000))
    components: Mapped[list[str] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
