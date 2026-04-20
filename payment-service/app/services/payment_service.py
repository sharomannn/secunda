from typing import Optional, Any
from uuid import UUID
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Payment, PaymentStatus, Currency
from app.repositories import PaymentRepository
from app.services.outbox_service import OutboxService


class PaymentService:
    """Service for payment business logic"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.payment_repo = PaymentRepository(session)
        self.outbox_service = OutboxService(session)
    
    async def create_payment(
        self,
        amount: Decimal,
        currency: Currency,
        description: str,
        metadata: dict[str, Any],
        webhook_url: str,
        idempotency_key: str,
    ) -> Payment:
        """
        Create new payment with idempotency check
        
        Args:
            amount: Payment amount
            currency: Currency (RUB, USD, EUR)
            description: Payment description
            metadata: Additional metadata (JSON)
            webhook_url: URL for webhook notifications
            idempotency_key: Unique key for idempotency
            
        Returns:
            Created or existing payment
        """
        # Check idempotency
        # SECURITY: Race condition защищён UNIQUE constraint на idempotency_key
        # в миграции 001_create_tables.py (строки 51, 59). При параллельных
        # запросах с одинаковым ключом второй INSERT получит IntegrityError,
        # который обработается на уровне API как 409 Conflict.
        existing_payment = await self.payment_repo.get_by_idempotency_key(
            idempotency_key
        )
        if existing_payment:
            return existing_payment
        
        # Create new payment
        import uuid
        payment = Payment(
            id=uuid.uuid4(),
            amount=amount,
            currency=currency,
            description=description,
            metadata_=metadata,
            status=PaymentStatus.PENDING,
            idempotency_key=idempotency_key,
            webhook_url=webhook_url,
        )
        
        # Save payment and create outbox event in same transaction
        payment = await self.payment_repo.create(payment)
        
        await self.outbox_service.create_payment_created_event(
            payment_id=payment.id,  # type: ignore[arg-type]
            idempotency_key=idempotency_key,
        )
        
        # Commit happens in get_db() dependency
        return payment
    
    async def get_payment(self, payment_id: UUID) -> Optional[Payment]:
        """
        Get payment by ID
        
        Args:
            payment_id: Payment UUID
            
        Returns:
            Payment or None if not found
        """
        return await self.payment_repo.get_by_id(payment_id)
