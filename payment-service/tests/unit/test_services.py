from decimal import Decimal
from app.models import Currency, PaymentStatus
from app.services import PaymentService, PaymentProcessor


class TestPaymentService:
    """Tests for PaymentService"""
    
    async def test_create_payment_success(self, db_session):
        """Test creating payment"""
        service = PaymentService(db_session)
        
        payment = await service.create_payment(
            amount=Decimal("100.50"),
            currency=Currency.RUB,
            description="Test",
            metadata={"test": True},
            webhook_url="https://example.com/webhook",
            idempotency_key="test-key-123",
        )
        await db_session.commit()
        
        assert payment.id is not None
        assert payment.status == PaymentStatus.PENDING
        assert payment.amount == Decimal("100.50")
    
    async def test_create_payment_with_existing_idempotency_key_returns_existing(
        self, db_session, payment_factory
    ):
        """Test idempotency: returns existing payment"""
        existing = await payment_factory(idempotency_key="duplicate-key")
        
        service = PaymentService(db_session)
        payment = await service.create_payment(
            amount=Decimal("999.99"),  # Different amount
            currency=Currency.USD,
            description="Different",
            metadata={},
            webhook_url="https://other.com/webhook",
            idempotency_key="duplicate-key",  # Same key
        )
        
        assert payment.id == existing.id
        assert payment.amount == existing.amount  # Original amount


class TestPaymentProcessor:
    """Tests for PaymentProcessor"""
    
    async def test_process_payment_updates_status(self, db_session, payment_factory):
        """Test processing payment"""
        payment = await payment_factory(status=PaymentStatus.PENDING)
        
        processor = PaymentProcessor(db_session)
        processed = await processor.process_payment(payment.id)
        await db_session.commit()
        
        assert processed.status in [PaymentStatus.SUCCEEDED, PaymentStatus.FAILED]
        assert processed.processed_at is not None
    
    async def test_process_payment_idempotent_skips_already_processed(
        self, db_session, payment_factory
    ):
        """Test processor idempotency"""
        payment = await payment_factory(status=PaymentStatus.SUCCEEDED)
        
        processor = PaymentProcessor(db_session)
        processed = await processor.process_payment(payment.id)
        
        assert processed.status == PaymentStatus.SUCCEEDED
        # processed_at should not change
