from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Outbox, OutboxStatus


class OutboxRepository:
    """Repository for Outbox model"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(self, outbox: Outbox) -> Outbox:
        """
        Create new outbox event
        
        Args:
            outbox: Outbox instance
            
        Returns:
            Created outbox event
        """
        self.session.add(outbox)
        await self.session.flush()
        await self.session.refresh(outbox)
        return outbox
    
    async def get_pending_events(self, limit: int = 100) -> List[Outbox]:
        """
        Get pending outbox events for publishing
        
        Args:
            limit: Maximum number of events to fetch
            
        Returns:
            List of pending outbox events
        """
        result = await self.session.execute(
            select(Outbox)
            .where(Outbox.status == OutboxStatus.PENDING)
            .order_by(Outbox.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def mark_as_published(self, outbox_id: int) -> Outbox:
        """
        Mark outbox event as published
        
        Args:
            outbox_id: Outbox event ID
            
        Returns:
            Updated outbox event
            
        Raises:
            ValueError: If outbox event not found
        """
        result = await self.session.execute(
            select(Outbox).where(Outbox.id == outbox_id)
        )
        outbox = result.scalar_one_or_none()
        
        if not outbox:
            raise ValueError(f"Outbox event {outbox_id} not found")
        
        from datetime import datetime, timezone
        outbox.status = OutboxStatus.PUBLISHED  # type: ignore[assignment]
        outbox.published_at = datetime.now(timezone.utc)  # type: ignore[assignment]
        
        await self.session.flush()
        await self.session.refresh(outbox)
        return outbox
