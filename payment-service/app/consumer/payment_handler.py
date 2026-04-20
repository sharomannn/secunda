import asyncio
import logging
from typing import Dict, Any
from uuid import UUID
from faststream.rabbit import RabbitBroker, RabbitQueue, RabbitExchange, ExchangeType
from faststream.rabbit.annotations import RabbitMessage
from faststream.middlewares.acknowledgement.config import AckPolicy
from app.config import settings
from app.db import AsyncSessionLocal
from app.services import PaymentProcessor, WebhookClient, WebhookDeliveryError

# Configure logging
logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

# Create broker
broker = RabbitBroker(settings.rabbitmq_url)

# Define exchange and queues
payments_exchange = RabbitExchange("payments", type=ExchangeType.TOPIC, durable=True)

payments_queue = RabbitQueue(
    "payments.new",
    durable=True,
    routing_key="payment.created",
)

dlq_queue = RabbitQueue(
    "payments.new.dlq",
    durable=True,
)


@broker.subscriber(
    queue=payments_queue,
    exchange=payments_exchange,
    ack_policy=AckPolicy.NACK_ON_ERROR,  # NACK on error (DLQ configured in RabbitMQ with retry)
)
async def handle_payment(
    message: Dict[str, Any],
    raw_message: RabbitMessage,
) -> None:
    """
    Handle payment processing from RabbitMQ queue
    
    Message format:
    {
        "payment_id": "uuid",
        "idempotency_key": "string",
        "created_at": "iso8601"
    }
    
    Flow:
    1. Get payment from DB
    2. Check if already processed (idempotency)
    3. Process payment (2-5 sec, 90% success)
    4. Send webhook notification
    5. ACK message
    
    On error:
    - NACK and requeue (up to 3 times)
    - After 3 failures, send to DLQ
    """
    payment_id_str = message.get("payment_id")
    
    if not payment_id_str:
        logger.error(f"Invalid message: missing payment_id: {message}")
        # ACK invalid messages (don't retry)
        return
    
    try:
        payment_id = UUID(payment_id_str)
    except ValueError:
        logger.error(f"Invalid payment_id format: {payment_id_str}")
        # ACK invalid messages (don't retry)
        return
    
    logger.info(f"Processing payment {payment_id}")
    
    async with AsyncSessionLocal() as session:
        try:
            # Process payment
            processor = PaymentProcessor(session)
            payment = await processor.process_payment(payment_id)
            await session.commit()
            
            logger.info(
                f"Payment {payment_id} processed: status={payment.status}"
            )
            
            # Send webhook
            webhook_client = WebhookClient()
            webhook_url: str = payment.webhook_url  # type: ignore
            await webhook_client.send_webhook(
                url=webhook_url,
                payload={
                    "payment_id": str(payment.id),
                    "status": payment.status.value,
                    "processed_at": payment.processed_at.isoformat() if payment.processed_at else None,
                }
            )
            
            logger.info(f"Webhook sent for payment {payment_id}")
            
            # Success: message will be ACKed automatically
            
        except WebhookDeliveryError as e:
            # Webhook failed after all retries
            logger.error(f"Webhook delivery failed for payment {payment_id}: {e}")
            await session.rollback()
            # Raise to trigger NACK and retry
            raise
        
        except Exception as e:
            # Other errors (DB, processing, etc.)
            logger.error(f"Error processing payment {payment_id}: {e}")
            await session.rollback()
            # Raise to trigger NACK and retry
            raise


async def run_consumer() -> None:
    """Run the consumer"""
    logger.info("Starting payment consumer...")
    await broker.start()
    logger.info("Payment consumer started")
    
    try:
        # Keep running
        await asyncio.Future()
    except KeyboardInterrupt:
        logger.info("Shutting down payment consumer...")
        await broker.close()
        logger.info("Payment consumer stopped")


if __name__ == "__main__":
    asyncio.run(run_consumer())
