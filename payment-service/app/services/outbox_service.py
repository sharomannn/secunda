from typing import List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Outbox, OutboxStatus
from app.repositories import OutboxRepository


class OutboxService:
    """Service for Outbox Pattern"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.outbox_repo = OutboxRepository(session)
    
    async def create_payment_created_event(
        self,
        payment_id: UUID,
        idempotency_key: str,
    ) -> Outbox:
        """
        Create outbox event for payment.created
        
        Args:
            payment_id: Payment UUID
            idempotency_key: Idempotency key from request
            
        Returns:
            Created outbox event
        """
        from datetime import datetime, timezone
        
        outbox = Outbox(
            aggregate_id=payment_id,
            event_type="payment.created",
            payload={
                "payment_id": str(payment_id),
                "idempotency_key": idempotency_key,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            status=OutboxStatus.PENDING,
        )
        
        return await self.outbox_repo.create(outbox)
    
    async def get_pending_events(self, limit: int = 100) -> List[Outbox]:
        """
        Get pending events for publishing
        
        Args:
            limit: Maximum number of events
            
        Returns:
            List of pending outbox events
        """
        return await self.outbox_repo.get_pending_events(limit)
    
    async def mark_as_published(self, outbox_id: int) -> Outbox:
        """
        Mark event as published
        
        Args:
            outbox_id: Outbox event ID
            
        Returns:
            Updated outbox event
        """
        return await self.outbox_repo.mark_as_published(outbox_id)
