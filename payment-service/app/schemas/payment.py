from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, HttpUrl, field_validator
from app.models import PaymentStatus, Currency


class PaymentCreateRequest(BaseModel):
    """Request schema for creating payment"""
    
    amount: Decimal = Field(
        ...,
        gt=0,
        decimal_places=2,
        description="Payment amount (must be positive, max 2 decimal places)"
    )
    currency: Currency = Field(
        ...,
        description="Currency code (RUB, USD, EUR)"
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Payment description"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (JSON object)"
    )
    webhook_url: HttpUrl = Field(
        ...,
        description="URL for webhook notifications"
    )
    
    @field_validator('amount')
    @classmethod
    def validate_amount_precision(cls, v: Decimal) -> Decimal:
        """Ensure amount has max 2 decimal places"""
        exponent = v.as_tuple().exponent
        if isinstance(exponent, int) and exponent < -2:
            raise ValueError("Amount must have at most 2 decimal places")
        return v
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "amount": "100.50",
                    "currency": "RUB",
                    "description": "Payment for order #12345",
                    "metadata": {"order_id": "12345"},
                    "webhook_url": "https://example.com/webhook"
                }
            ]
        }
    }


class PaymentCreateResponse(BaseModel):
    """Response schema for payment creation (202 Accepted)"""
    
    id: UUID = Field(..., description="Payment unique identifier")
    status: PaymentStatus = Field(..., description="Payment status (always 'pending' on creation)")
    created_at: datetime = Field(..., description="Payment creation timestamp (UTC)")
    
    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "examples": [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "status": "pending",
                    "created_at": "2026-04-20T10:00:00.123456Z"
                }
            ]
        }
    }


class PaymentDetailResponse(BaseModel):
    """Response schema for payment details"""
    
    id: UUID
    amount: Decimal
    currency: Currency
    description: str
    metadata: Dict[str, Any] = Field(..., validation_alias="metadata_", serialization_alias="metadata")
    status: PaymentStatus
    idempotency_key: str
    webhook_url: str
    created_at: datetime
    processed_at: Optional[datetime] = None
    
    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
        "json_schema_extra": {
            "examples": [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "amount": "100.50",
                    "currency": "RUB",
                    "description": "Payment for order #12345",
                    "metadata": {"order_id": "12345"},
                    "status": "succeeded",
                    "idempotency_key": "client-key-123",
                    "webhook_url": "https://example.com/webhook",
                    "created_at": "2026-04-20T10:00:00.123456Z",
                    "processed_at": "2026-04-20T10:00:03.456789Z"
                }
            ]
        }
    }


class ErrorResponse(BaseModel):
    """Standard error response"""
    
    detail: str = Field(..., description="Error message")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {"detail": "Payment not found"},
                {"detail": "Invalid API key"}
            ]
        }
    }
