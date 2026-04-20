import uuid
from app.services.outbox_service import OutboxService
from app.models import OutboxStatus
from app.repositories import OutboxRepository


class TestOutboxService:
    """Tests for OutboxService"""
    
    async def test_create_payment_created_event(self, db_session):
        """Test creating payment.created outbox event"""
        service = OutboxService(db_session)
        payment_id = uuid.uuid4()
        idempotency_key = "test-key-123"
        
        outbox = await service.create_payment_created_event(
            payment_id=payment_id,
            idempotency_key=idempotency_key,
        )
        await db_session.commit()
        
        assert outbox.id is not None
        assert outbox.aggregate_id == payment_id
        assert outbox.event_type == "payment.created"
        assert outbox.status == OutboxStatus.PENDING
        assert outbox.payload["idempotency_key"] == idempotency_key
    
    async def test_get_pending_events(self, db_session, outbox_factory):
        """Test getting pending outbox events"""
        await outbox_factory(status=OutboxStatus.PENDING)
        await outbox_factory(status=OutboxStatus.PENDING)
        await outbox_factory(status=OutboxStatus.PUBLISHED)
        
        repo = OutboxRepository(db_session)
        events = await repo.get_pending_events(limit=10)
        
        assert len(events) == 2
        assert all(e.status == OutboxStatus.PENDING for e in events)
    
    async def test_mark_as_published(self, db_session, outbox_factory):
        """Test marking outbox event as published"""
        outbox = await outbox_factory(status=OutboxStatus.PENDING)
        
        repo = OutboxRepository(db_session)
        updated = await repo.mark_as_published(outbox.id)
        await db_session.commit()
        
        assert updated.status == OutboxStatus.PUBLISHED
        assert updated.published_at is not None
    
    async def test_get_pending_events_respects_limit(self, db_session, outbox_factory):
        """Test pending events limit parameter"""
        for _ in range(5):
            await outbox_factory(status=OutboxStatus.PENDING)
        
        repo = OutboxRepository(db_session)
        events = await repo.get_pending_events(limit=3)
        
        assert len(events) == 3
    
    async def test_create_multiple_events_for_same_payment(self, db_session):
        """Test creating multiple events for same payment"""
        service = OutboxService(db_session)
        payment_id = uuid.uuid4()
        
        outbox1 = await service.create_payment_created_event(
            payment_id=payment_id,
            idempotency_key="key-1",
        )
        outbox2 = await service.create_payment_created_event(
            payment_id=payment_id,
            idempotency_key="key-2",
        )
        await db_session.commit()
        
        assert outbox1.aggregate_id == payment_id
        assert outbox2.aggregate_id == payment_id
        assert outbox1.id != outbox2.id
