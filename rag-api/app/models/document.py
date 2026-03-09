import uuid
from datetime import datetime

from sqlalchemy import Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.base import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    filename: Mapped[str]
    content_type: Mapped[str]
    sha256: Mapped[str]
    storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(default="uploaded")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
