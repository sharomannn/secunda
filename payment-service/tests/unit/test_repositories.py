from app.models import PaymentStatus, OutboxStatus
from app.repositories import PaymentRepository, OutboxRepository


class TestPaymentRepository:
    """Tests for PaymentRepository"""
    
    async def test_get_by_idempotency_key_returns_payment(self, db_session, payment_factory):
        """Test getting payment by idempotency key"""
        payment = await payment_factory(idempotency_key="test-key-123")
        
        repo = PaymentRepository(db_session)
        found = await repo.get_by_idempotency_key("test-key-123")
        
        assert found is not None
        assert found.id == payment.id
    
    async def test_get_by_idempotency_key_returns_none_if_not_found(self, db_session):
        """Test getting non-existent payment"""
        repo = PaymentRepository(db_session)
        found = await repo.get_by_idempotency_key("non-existent")
        
        assert found is None
    
    async def test_update_status_sets_processed_at(self, db_session, payment_factory):
        """Test updating payment status"""
        payment = await payment_factory(status=PaymentStatus.PENDING)
        
        repo = PaymentRepository(db_session)
        updated = await repo.update_status(payment.id, PaymentStatus.SUCCEEDED)
        
        assert updated.status == PaymentStatus.SUCCEEDED
        assert updated.processed_at is not None


class TestOutboxRepository:
    """Tests for OutboxRepository"""
    
    async def test_get_pending_events_returns_only_pending(self, db_session, outbox_factory):
        """Test getting pending events"""
        await outbox_factory(status=OutboxStatus.PENDING)
        await outbox_factory(status=OutboxStatus.PUBLISHED)
        
        repo = OutboxRepository(db_session)
        events = await repo.get_pending_events()
        
        assert len(events) == 1
        assert events[0].status == OutboxStatus.PENDING
    
    async def test_mark_as_published_updates_status(self, db_session, outbox_factory):
        """Test marking event as published"""
        outbox = await outbox_factory(status=OutboxStatus.PENDING)
        
        repo = OutboxRepository(db_session)
        updated = await repo.mark_as_published(outbox.id)
        
        assert updated.status == OutboxStatus.PUBLISHED
        assert updated.published_at is not None
