import asyncio
import random
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Payment, PaymentStatus
from app.repositories import PaymentRepository


class PaymentProcessor:
    """Service for payment processing emulation"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.payment_repo = PaymentRepository(session)
    
    async def process_payment(self, payment_id: UUID) -> Payment:
        """
        Process payment with emulation
        
        - Processing time: 2-5 seconds
        - Success rate: 90%
        - Failure rate: 10%
        
        Args:
            payment_id: Payment UUID
            
        Returns:
            Processed payment
            
        Raises:
            ValueError: If payment not found or already processed
        """
        payment = await self.payment_repo.get_by_id(payment_id)
        
        if not payment:
            raise ValueError(f"Payment {payment_id} not found")
        
        # Check idempotency: skip if already processed
        if payment.status != PaymentStatus.PENDING:
            return payment
        
        # Emulate processing time (2-5 seconds)
        processing_time = random.uniform(2.0, 5.0)
        await asyncio.sleep(processing_time)
        
        # Determine result (90% success, 10% failure)
        success = random.random() < 0.9
        new_status = PaymentStatus.SUCCEEDED if success else PaymentStatus.FAILED
        
        # Update payment status
        payment = await self.payment_repo.update_status(
            payment_id=payment_id,
            status=new_status,
        )
        
        return payment
