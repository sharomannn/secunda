import pytest
import uuid
from decimal import Decimal
from sqlalchemy.exc import IntegrityError
from app.models import Payment, PaymentStatus, Currency, Outbox, OutboxStatus


class TestPaymentModel:
    """Tests for Payment model"""
    
    async def test_create_payment_with_valid_data(self, db_session):
        """Test creating payment with valid data"""
        payment = Payment(
            id=uuid.uuid4(),
            amount=Decimal("100.50"),
            currency=Currency.RUB,
            description="Test",
            metadata_={},
            status=PaymentStatus.PENDING,
            idempotency_key="test-key",
            webhook_url="https://example.com/webhook",
        )
        db_session.add(payment)
        await db_session.commit()
        
        assert payment.id is not None
        assert payment.status == PaymentStatus.PENDING
        assert payment.created_at is not None
        assert payment.processed_at is None
    
    async def test_payment_idempotency_key_unique_constraint(self, db_session):
        """Test idempotency_key unique constraint"""
        payment1 = Payment(
            id=uuid.uuid4(),
            amount=Decimal("100.00"),
            currency=Currency.RUB,
            description="Test",
            metadata_={},
            status=PaymentStatus.PENDING,
            idempotency_key="duplicate-key",
            webhook_url="https://example.com/webhook",
        )
        db_session.add(payment1)
        await db_session.commit()
        
        # Try to create another payment with same key
        payment2 = Payment(
            id=uuid.uuid4(),
            amount=Decimal("200.00"),
            currency=Currency.USD,
            description="Test 2",
            metadata_={},
            status=PaymentStatus.PENDING,
            idempotency_key="duplicate-key",  # Same key
            webhook_url="https://example.com/webhook",
        )
        db_session.add(payment2)
        
        with pytest.raises(IntegrityError):
            await db_session.commit()
    
    async def test_payment_amount_must_be_positive(self, db_session):
        """Test amount > 0 constraint"""
        payment = Payment(
            id=uuid.uuid4(),
            amount=Decimal("-10.00"),  # Negative
            currency=Currency.RUB,
            description="Test",
            metadata_={},
            status=PaymentStatus.PENDING,
            idempotency_key="test-key",
            webhook_url="https://example.com/webhook",
        )
        db_session.add(payment)
        
        with pytest.raises(IntegrityError):
            await db_session.commit()


class TestOutboxModel:
    """Tests for Outbox model"""
    
    async def test_create_outbox_with_valid_data(self, db_session):
        """Test creating outbox event"""
        outbox = Outbox(
            aggregate_id=uuid.uuid4(),
            event_type="payment.created",
            payload={"test": True},
            status=OutboxStatus.PENDING,
        )
        db_session.add(outbox)
        await db_session.commit()
        
        assert outbox.id is not None
        assert outbox.status == OutboxStatus.PENDING
        assert outbox.created_at is not None
        assert outbox.published_at is None
