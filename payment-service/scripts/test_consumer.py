#!/usr/bin/env python3
"""
Test script for payment consumer

Creates a test payment and publishes event to RabbitMQ
"""
import asyncio
import uuid
from decimal import Decimal
from app.db import AsyncSessionLocal
from app.models import Payment, PaymentStatus, Currency, Outbox, OutboxStatus
from app.tasks.outbox_publisher import OutboxPublisher

async def create_test_payment():
    """Create test payment and outbox event"""
    async with AsyncSessionLocal() as session:
        # Create payment
        payment = Payment(
            id=uuid.uuid4(),
            amount=Decimal("100.50"),
            currency=Currency.RUB,
            description="Test payment for consumer",
            metadata_={"test": True},
            status=PaymentStatus.PENDING,
            idempotency_key=str(uuid.uuid4()),
            webhook_url="https://webhook.site/unique-id",  # Use webhook.site for testing
        )
        session.add(payment)
        
        # Create outbox event
        outbox = Outbox(
            aggregate_id=payment.id,
            event_type="payment.created",
            payload={
                "payment_id": str(payment.id),
                "idempotency_key": payment.idempotency_key,
                "created_at": payment.created_at.isoformat() if payment.created_at else None,
            },
            status=OutboxStatus.PENDING,
        )
        session.add(outbox)
        
        await session.commit()
        
        print(f"✓ Test payment created: {payment.id}")
        print(f"✓ Outbox event created: {outbox.id}")
        print(f"✓ Webhook URL: {payment.webhook_url}")
        print("\nNow run outbox publisher to publish the event:")
        print("  python -m app.tasks.outbox_publisher")
        print("\nThen check consumer logs to see processing:")
        print("  python -m app.consumer.payment_handler")
        
        return payment.id

async def publish_test_event():
    """Publish pending events"""
    publisher = OutboxPublisher()
    await publisher.broker.start()
    
    count = await publisher.publish_pending_events()
    print(f"✓ Published {count} events")
    
    await publisher.broker.close()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "publish":
        asyncio.run(publish_test_event())
    else:
        asyncio.run(create_test_payment())
