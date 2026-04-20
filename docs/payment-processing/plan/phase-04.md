---
name: Асинхронная обработка
layer: consumer, background-tasks
depends_on: phase-02
plan: ./README.md
---

# Фаза 4: Асинхронная обработка

## Цель

Реализовать RabbitMQ consumer для обработки платежей, webhook-уведомления и Outbox Publisher для гарантированной доставки событий.

## Контекст

После завершения Phase 2 у нас есть:
- PaymentProcessor для обработки платежей
- WebhookClient для отправки webhook
- OutboxService для работы с outbox событиями

В этой фазе создаём:
- RabbitMQ consumer (FastStream) для обработки платежей
- Outbox Publisher для публикации событий из БД в RabbitMQ
- Настройку очередей, DLQ, retry-логики
- Интеграцию всех компонентов асинхронной обработки

## Создать файлы

### `app/consumer/payment_handler.py`

**Назначение:** RabbitMQ consumer для обработки платежей

**Содержимое:**
```python
import asyncio
import logging
from typing import Dict, Any
from uuid import UUID
from faststream.rabbit import RabbitBroker, RabbitQueue, RabbitExchange
from faststream.rabbit.annotations import RabbitMessage
from app.config import settings
from app.db import AsyncSessionLocal
from app.services import PaymentProcessor, WebhookClient, WebhookDeliveryError

# Configure logging
logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

# Create broker
broker = RabbitBroker(settings.rabbitmq_url)

# Define exchange and queues
payments_exchange = RabbitExchange("payments", type="topic", durable=True)

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
    retry=3,  # Retry 3 times before sending to DLQ
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
            await webhook_client.send_webhook(
                url=payment.webhook_url,
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


async def run_consumer():
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
```

**Детали реализации:**
- FastStream RabbitBroker для async RabbitMQ
- Retry=3 для автоматических повторных попыток
- Идемпотентность через PaymentProcessor
- WebhookClient с собственной retry-логикой
- Логирование всех операций
- NACK при ошибках для retry
- ACK при успехе (автоматически)

**Ссылки на дизайн:**
- Async tasks: `../05-async-tasks.md` (Payment Consumer)
- Поведение: `../02-behavior.md` (Use Case 3)
- Решение: `../03-decisions.md` (ADR-05 DLQ)

### `app/consumer/__init__.py`

**Назначение:** Экспорт consumer

**Содержимое:**
```python
from app.consumer.payment_handler import broker, run_consumer

__all__ = ["broker", "run_consumer"]
```

### `app/tasks/outbox_publisher.py`

**Назначение:** Background task для публикации outbox событий

**Содержимое:**
```python
import asyncio
import logging
from faststream.rabbit import RabbitBroker, RabbitExchange
from app.config import settings
from app.db import AsyncSessionLocal
from app.services import OutboxService

# Configure logging
logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

# Create broker
broker = RabbitBroker(settings.rabbitmq_url)

# Define exchange
payments_exchange = RabbitExchange("payments", type="topic", durable=True)


class OutboxPublisher:
    """Background task for publishing outbox events to RabbitMQ"""
    
    def __init__(self):
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
                        await self.broker.publish(
                            message=event.payload,
                            exchange=payments_exchange,
                            routing_key=event.event_type.replace(".", "_"),  # payment.created -> payment_created
                        )
                        
                        # Mark as published
                        await service.mark_as_published(event.id)
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
    
    async def run(self):
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


async def run_publisher():
    """Run the outbox publisher"""
    publisher = OutboxPublisher()
    await publisher.run()


if __name__ == "__main__":
    asyncio.run(run_publisher())
```

**Детали реализации:**
- Бесконечный цикл с интервалом из settings
- Batch processing (100 событий за раз)
- Публикация в RabbitMQ через FastStream
- mark_as_published() после успешной публикации
- Обработка ошибок: событие остаётся pending
- Логирование всех операций

**Ссылки на дизайн:**
- Async tasks: `../05-async-tasks.md` (Outbox Publisher)
- Паттерн: `../03-decisions.md` (ADR-01 Outbox Pattern)
- Поведение: `../02-behavior.md` (Use Case 4)

### `app/tasks/__init__.py`

**Назначение:** Экспорт tasks

**Содержимое:**
```python
from app.tasks.outbox_publisher import OutboxPublisher, run_publisher

__all__ = ["OutboxPublisher", "run_publisher"]
```

### `scripts/setup_rabbitmq.sh`

**Назначение:** Скрипт для настройки RabbitMQ (exchange, queues, DLQ)

**Содержимое:**
```bash
#!/bin/bash
set -e

echo "Setting up RabbitMQ for payment service..."

# Wait for RabbitMQ to be ready
echo "Waiting for RabbitMQ..."
sleep 5

# Create exchange
rabbitmqadmin declare exchange \
  name=payments \
  type=topic \
  durable=true

echo "✓ Exchange 'payments' created"

# Create main queue
rabbitmqadmin declare queue \
  name=payments.new \
  durable=true \
  arguments='{"x-dead-letter-exchange":"payments.dlx","x-dead-letter-routing-key":"dlq"}'

echo "✓ Queue 'payments.new' created with DLQ config"

# Create DLX (Dead Letter Exchange)
rabbitmqadmin declare exchange \
  name=payments.dlx \
  type=fanout \
  durable=true

echo "✓ DLX 'payments.dlx' created"

# Create DLQ
rabbitmqadmin declare queue \
  name=payments.new.dlq \
  durable=true \
  arguments='{"x-message-ttl":604800000}'  # 7 days TTL

echo "✓ DLQ 'payments.new.dlq' created with 7 days TTL"

# Bind main queue to exchange
rabbitmqadmin declare binding \
  source=payments \
  destination=payments.new \
  routing_key=payment.created

echo "✓ Binding 'payments.new' to 'payments' exchange"

# Bind DLQ to DLX
rabbitmqadmin declare binding \
  source=payments.dlx \
  destination=payments.new.dlq \
  routing_key=dlq

echo "✓ Binding 'payments.new.dlq' to 'payments.dlx'"

echo ""
echo "✅ RabbitMQ setup complete!"
echo ""
echo "Queues:"
echo "  - payments.new (main queue)"
echo "  - payments.new.dlq (dead letter queue, 7 days TTL)"
echo ""
echo "Exchanges:"
echo "  - payments (topic)"
echo "  - payments.dlx (fanout, for DLQ)"
```

**Детали:**
- Создание exchange "payments" (topic)
- Создание queue "payments.new" с DLQ config
- Создание DLX и DLQ
- Bindings для routing
- TTL 7 дней для DLQ

**Ссылки на дизайн:**
- Async tasks: `../05-async-tasks.md` (Очереди RabbitMQ)
- Решение: `../03-decisions.md` (ADR-05 DLQ)

### `scripts/test_consumer.py`

**Назначение:** Скрипт для тестирования consumer

**Содержимое:**
```python
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
            metadata={"test": True},
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
        print(f"\nNow run outbox publisher to publish the event:")
        print(f"  python -m app.tasks.outbox_publisher")
        print(f"\nThen check consumer logs to see processing:")
        print(f"  python -m app.consumer.payment_handler")
        
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
```

**Детали:**
- Создание тестового платежа
- Создание outbox события
- Использование webhook.site для тестирования webhook
- Инструкции по запуску

## Определение готовности

- [ ] Все файлы созданы согласно списку выше
- [ ] RabbitMQ consumer подписан на payments.new
- [ ] Consumer обрабатывает платежи через PaymentProcessor
- [ ] Consumer отправляет webhook через WebhookClient
- [ ] Consumer реализует retry (3 попытки)
- [ ] Outbox Publisher публикует pending события
- [ ] Outbox Publisher обновляет статус на published
- [ ] DLQ настроена для невосстановимых сообщений
- [ ] Логирование работает для всех операций
- [ ] Скрипт setup_rabbitmq.sh создаёт очереди
- [ ] Можно запустить: `python -m app.consumer.payment_handler`
- [ ] Можно запустить: `python -m app.tasks.outbox_publisher`

## Проверка результата

### 1. Запустить RabbitMQ

```bash
docker run -d \
  --name payment-rabbitmq \
  -p 5672:5672 \
  -p 15672:15672 \
  -e RABBITMQ_DEFAULT_USER=guest \
  -e RABBITMQ_DEFAULT_PASS=guest \
  rabbitmq:3-management

# Подождать запуска
sleep 10

# Установить rabbitmqadmin (если нужно)
docker exec payment-rabbitmq rabbitmq-plugins enable rabbitmq_management

# Настроить очереди
chmod +x scripts/setup_rabbitmq.sh
docker exec payment-rabbitmq bash -c "$(cat scripts/setup_rabbitmq.sh)"
```

### 2. Проверить RabbitMQ Management UI

Открыть: http://localhost:15672
- Login: guest / guest
- Проверить наличие:
  - Exchange: payments
  - Queue: payments.new
  - Queue: payments.new.dlq

### 3. Создать тестовый платёж

```bash
# Создать платёж и outbox событие
python scripts/test_consumer.py
```

Ожидаемый вывод:
```
✓ Test payment created: 550e8400-e29b-41d4-a716-446655440000
✓ Outbox event created: 1
✓ Webhook URL: https://webhook.site/unique-id
```

### 4. Запустить Outbox Publisher

```bash
# В отдельном терминале
python -m app.tasks.outbox_publisher
```

Ожидаемый вывод:
```
INFO:app.tasks.outbox_publisher:Starting outbox publisher...
INFO:app.tasks.outbox_publisher:Outbox publisher started (interval=5s, batch=100)
INFO:app.tasks.outbox_publisher:Published 1 outbox events
```

### 5. Запустить Consumer

```bash
# В отдельном терминале
python -m app.consumer.payment_handler
```

Ожидаемый вывод:
```
INFO:app.consumer.payment_handler:Starting payment consumer...
INFO:app.consumer.payment_handler:Payment consumer started
INFO:app.consumer.payment_handler:Processing payment 550e8400-...
INFO:app.consumer.payment_handler:Payment 550e8400-... processed: status=PaymentStatus.SUCCEEDED
INFO:app.consumer.payment_handler:Webhook sent for payment 550e8400-...
```

### 6. Проверить результат

```bash
# Проверить статус платежа в БД
psql postgresql://user:password@localhost:5432/payments -c \
  "SELECT id, status, processed_at FROM payments ORDER BY created_at DESC LIMIT 1;"
```

Ожидаемый результат:
```
                  id                  |  status   |         processed_at
--------------------------------------+-----------+---------------------------
 550e8400-e29b-41d4-a716-446655440000 | succeeded | 2026-04-20 10:00:05.123456
```

### 7. Проверить webhook

Открыть webhook.site URL из вывода test_consumer.py

Должен быть запрос:
```json
{
  "payment_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "succeeded",
  "processed_at": "2026-04-20T10:00:05.123456Z"
}
```

### 8. Тест полного flow

```python
# test_phase_04.py
import asyncio
import httpx
import uuid
from decimal import Decimal

API_BASE = "http://localhost:8000/api/v1"
API_KEY = "change-me-in-production"

async def test_full_flow():
    # 1. Create payment via API
    idempotency_key = str(uuid.uuid4())
    response = httpx.post(
        f"{API_BASE}/payments",
        headers={
            "X-API-Key": API_KEY,
            "Idempotency-Key": idempotency_key
        },
        json={
            "amount": "100.50",
            "currency": "RUB",
            "description": "Full flow test",
            "metadata": {"test": "phase-04"},
            "webhook_url": "https://webhook.site/your-unique-id"
        }
    )
    
    assert response.status_code == 202
    payment_id = response.json()["id"]
    print(f"✓ Payment created: {payment_id}")
    
    # 2. Wait for processing (consumer should pick it up)
    print("⏳ Waiting for async processing (10 seconds)...")
    await asyncio.sleep(10)
    
    # 3. Check payment status
    response = httpx.get(
        f"{API_BASE}/payments/{payment_id}",
        headers={"X-API-Key": API_KEY}
    )
    
    assert response.status_code == 200
    payment = response.json()
    
    print(f"✓ Payment status: {payment['status']}")
    print(f"✓ Processed at: {payment['processed_at']}")
    
    assert payment["status"] in ["succeeded", "failed"]
    assert payment["processed_at"] is not None
    
    print("\n✅ Full async flow works!")

if __name__ == "__main__":
    asyncio.run(test_full_flow())
```

Запустить (убедиться что API, Consumer и Outbox Publisher запущены):
```bash
python test_phase_04.py
```

Ожидаемый результат:
```
✓ Payment created: 550e8400-...
⏳ Waiting for async processing (10 seconds)...
✓ Payment status: succeeded
✓ Processed at: 2026-04-20T10:00:05.123456Z

✅ Full async flow works!
```
