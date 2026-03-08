import uuid
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Mapped, mapped_column

from app.base import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    filename: Mapped[str]
    content_type: Mapped[str]
    sha256: Mapped[str]
    status: Mapped[str] = mapped_column(default="uploaded")
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
