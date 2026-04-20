import uuid
from enum import Enum
from typing import Any
from sqlalchemy import Column, String, Numeric, CheckConstraint, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM as PG_ENUM
from sqlalchemy.sql import func
from app.db.base import Base


class PaymentStatus(str, Enum):
    """Статус платежа"""
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Currency(str, Enum):
    """Поддерживаемые валюты"""
    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"


class Payment(Base):
    """Модель платежа"""
    __tablename__ = "payments"
    
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False
    )
    amount = Column(
        Numeric(precision=10, scale=2),
        nullable=False
    )
    currency: Column[Any] = Column(
        PG_ENUM(Currency, name="currency", create_type=False),
        nullable=False
    )
    description = Column(
        String(500),
        nullable=False
    )
    metadata_: Column[Any] = Column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}"
    )
    status: Column[Any] = Column(
        PG_ENUM(PaymentStatus, name="payment_status", create_type=False),
        nullable=False,
        default=PaymentStatus.PENDING,
        server_default="pending"
    )
    idempotency_key = Column(
        String(255),
        nullable=False,
        unique=True,
        index=True
    )
    webhook_url = Column(
        String(2048),
        nullable=False
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )
    processed_at = Column(
        DateTime(timezone=True),
        nullable=True
    )
    
    __table_args__ = (
        CheckConstraint('amount > 0', name='check_amount_positive'),
    )
    
    def __repr__(self) -> str:
        return f"<Payment(id={self.id}, status={self.status}, amount={self.amount})>"
