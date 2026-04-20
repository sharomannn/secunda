import asyncio
import logging
from typing import Any, Dict
from faststream.rabbit import RabbitBroker, RabbitExchange, ExchangeType
from app.config import settings
from app.db import AsyncSessionLocal
from app.services import OutboxService

# Configure logging
logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

# Create broker
broker = RabbitBroker(settings.rabbitmq_url)

# Define exchange
payments_exchange = RabbitExchange("payments", type=ExchangeType.TOPIC, durable=True)


class OutboxPublisher:
    """Background task for publishing outbox events to RabbitMQ"""
    
    def __init__(self) -> None:
        self.interval = settings.outbox_publish_interval
        self.batch_size = settings.outbox_batch_size
        self.broker = broker
    
    async def publish_pending_events(self) -> int:
        """
        Publish pending outbox events to RabbitMQ
        
        Returns:
            Number of events published
        """
        async with AsyncSessionLocal() as session:
            try:
                service = OutboxService(session)
                
                # Get pending events
                events = await service.get_pending_events(limit=self.batch_size)
                
                if not events:
                    return 0
                
                published_count = 0
                
                for event in events:
                    try:
                        # Publish to RabbitMQ
                        payload: Dict[str, Any] = event.payload  # type: ignore
                        event_id: int = event.id  # type: ignore
                        event_type: str = event.event_type  # type: ignore
                        await self.broker.publish(
                            message=payload,
                            exchange=payments_exchange,
                            routing_key=event_type,
                        )
                        
                        # Mark as published
                        await service.mark_as_published(event_id)
                        published_count += 1
                        
                        logger.debug(
                            f"Published outbox event {event.id}: {event.event_type}"
                        )
                    
                    except Exception as e:
                        # Log error but continue with other events
                        logger.error(
                            f"Failed to publish outbox event {event.id}: {e}"
                        )
                        # Event remains pending, will retry in next iteration
                
                await session.commit()
                
                if published_count > 0:
                    logger.info(f"Published {published_count} outbox events")
                
                return published_count
            
            except Exception as e:
                logger.error(f"Error in outbox publisher: {e}")
                await session.rollback()
                return 0
    
    async def run(self) -> None:
        """Run the publisher loop"""
        logger.info("Starting outbox publisher...")
        await self.broker.start()
        logger.info(f"Outbox publisher started (interval={self.interval}s, batch={self.batch_size})")
        
        try:
            while True:
                try:
                    await self.publish_pending_events()
                except Exception as e:
                    logger.error(f"Error in publisher loop: {e}")
                
                # Wait before next iteration
                await asyncio.sleep(self.interval)
        
        except KeyboardInterrupt:
            logger.info("Shutting down outbox publisher...")
            await self.broker.close()
            logger.info("Outbox publisher stopped")


async def run_publisher() -> None:
    """Run the outbox publisher"""
    publisher = OutboxPublisher()
    await publisher.run()


if __name__ == "__main__":
    asyncio.run(run_publisher())
