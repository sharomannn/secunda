from typing import Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Payment, PaymentStatus


class PaymentRepository:
    """Repository for Payment model"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(self, payment: Payment) -> Payment:
        """
        Create new payment
        
        Args:
            payment: Payment instance
            
        Returns:
            Created payment
        """
        self.session.add(payment)
        await self.session.flush()
        await self.session.refresh(payment)
        return payment
    
    async def get_by_id(self, payment_id: UUID) -> Optional[Payment]:
        """
        Get payment by ID
        
        Args:
            payment_id: Payment UUID
            
        Returns:
            Payment or None if not found
        """
        result = await self.session.execute(
            select(Payment).where(Payment.id == payment_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_idempotency_key(self, idempotency_key: str) -> Optional[Payment]:
        """
        Get payment by idempotency key
        
        Args:
            idempotency_key: Unique idempotency key
            
        Returns:
            Payment or None if not found
        """
        result = await self.session.execute(
            select(Payment).where(Payment.idempotency_key == idempotency_key)
        )
        return result.scalar_one_or_none()
    
    async def update_status(
        self,
        payment_id: UUID,
        status: PaymentStatus,
    ) -> Payment:
        """
        Update payment status and set processed_at
        
        Args:
            payment_id: Payment UUID
            status: New status
            
        Returns:
            Updated payment
            
        Raises:
            ValueError: If payment not found
        """
        payment = await self.get_by_id(payment_id)
        if not payment:
            raise ValueError(f"Payment {payment_id} not found")
        
        old_status = payment.status
        payment.status = status  # type: ignore[assignment]
        
        # Set processed_at only if transitioning from pending
        if old_status == PaymentStatus.PENDING:
            from datetime import datetime, timezone
            payment.processed_at = datetime.now(timezone.utc)  # type: ignore[assignment]
        
        await self.session.flush()
        await self.session.refresh(payment)
        return payment
