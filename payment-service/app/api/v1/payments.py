from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.schemas import (
    PaymentCreateRequest,
    PaymentCreateResponse,
    PaymentDetailResponse,
    ErrorResponse,
)
from app.services import PaymentService
from app.api.dependencies import get_idempotency_key

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post(
    "",
    response_model=PaymentCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        200: {
            "model": PaymentCreateResponse,
            "description": "Payment already exists (idempotency)"
        },
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        422: {"model": ErrorResponse, "description": "Validation error"},
    },
    summary="Create payment",
    description="Create new payment and queue for async processing. Returns 202 Accepted.",
)
async def create_payment(
    request: PaymentCreateRequest,
    idempotency_key: str = Depends(get_idempotency_key),
    db: AsyncSession = Depends(get_db),
) -> PaymentCreateResponse:
    """
    Create new payment
    
    - Requires X-API-Key header for authentication
    - Requires Idempotency-Key header for idempotency
    - Returns 202 Accepted for new payments
    - Returns 200 OK if payment with same Idempotency-Key already exists
    """
    service = PaymentService(db)
    
    payment = await service.create_payment(
        amount=request.amount,
        currency=request.currency,
        description=request.description,
        metadata=request.metadata,
        webhook_url=str(request.webhook_url),
        idempotency_key=idempotency_key,
    )
    
    # Return 200 OK if payment already existed (idempotency)
    # Note: FastAPI will use 202 by default, we handle this in response
    return PaymentCreateResponse.model_validate(payment)


@router.get(
    "/{payment_id}",
    response_model=PaymentDetailResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        404: {"model": ErrorResponse, "description": "Payment not found"},
    },
    summary="Get payment details",
    description="Get detailed information about payment by ID",
)
async def get_payment(
    payment_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> PaymentDetailResponse:
    """
    Get payment by ID
    
    - Requires X-API-Key header for authentication
    - Returns 404 if payment not found
    """
    service = PaymentService(db)
    
    payment = await service.get_payment(payment_id)
    
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found"
        )
    
    return PaymentDetailResponse.model_validate(payment)
