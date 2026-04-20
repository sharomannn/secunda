from enum import Enum
from typing import Any
from sqlalchemy import Column, String, BigInteger, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM as PG_ENUM
from sqlalchemy.sql import func
from app.db.base import Base


class OutboxStatus(str, Enum):
    """Статус события Outbox"""
    PENDING = "pending"
    PUBLISHED = "published"


class Outbox(Base):
    """Модель события Outbox для гарантированной доставки сообщений"""
    __tablename__ = "outbox"
    
    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )
    aggregate_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True
    )
    event_type = Column(
        String(100),
        nullable=False
    )
    payload = Column(
        JSONB,
        nullable=False
    )
    status: Column[Any] = Column(
        PG_ENUM(OutboxStatus, name="outbox_status", create_type=False),
        nullable=False,
        default=OutboxStatus.PENDING,
        server_default="pending"
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )
    published_at = Column(
        DateTime(timezone=True),
        nullable=True
    )
    
    def __repr__(self) -> str:
        return f"<Outbox(id={self.id}, event_type={self.event_type}, status={self.status})>"
