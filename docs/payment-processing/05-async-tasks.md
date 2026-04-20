---
date: 2026-04-20
feature: payment-processing
---

# Асинхронные задачи: Payment Processing Microservice

## Обзор

Асинхронная обработка реализована через RabbitMQ с использованием FastStream. Включает:
- Consumer для обработки платежей
- Webhook-клиент с retry-логикой
- Outbox Publisher для гарантированной доставки событий
- Dead Letter Queue для невосстановимых ошибок

---

## Очереди RabbitMQ

### payments.new

**Назначение:** Основная очередь для новых платежей

**Конфигурация:**
```python
exchange = "payments"
exchange_type = "topic"
routing_key = "payment.created"
queue_name = "payments.new"
prefetch_count = 10  # Количество сообщений для одновременной обработки
```

**Параметры:**
- **Durable:** true (очередь переживает перезапуск RabbitMQ)
- **Auto-delete:** false
- **Message TTL:** нет (сообщения хранятся до обработки)
- **Max retries:** 3
- **Dead Letter Exchange:** payments.dlx

**Формат сообщения:**
```json
{
  "payment_id": "550e8400-e29b-41d4-a716-446655440000",
  "idempotency_key": "client-generated-key-123",
  "created_at": "2026-04-20T10:00:00Z"
}
```

### payments.new.dlq

**Назначение:** Dead Letter Queue для невосстановимых сообщений

**Конфигурация:**
```python
exchange = "payments.dlx"
exchange_type = "fanout"
queue_name = "payments.new.dlq"
```

**Параметры:**
- **Durable:** true
- **Auto-delete:** false
- **Message TTL:** 7 дней (автоматическая очистка старых сообщений)

**Формат сообщения:**
```json
{
  "payment_id": "550e8400-e29b-41d4-a716-446655440000",
  "idempotency_key": "client-generated-key-123",
  "error": "Webhook delivery failed after 3 attempts",
  "attempts": 3,
  "last_error_at": "2026-04-20T10:05:00Z",
  "original_message": {...}
}
```

---

## Payment Consumer

### Назначение

Обрабатывает платежи из очереди `payments.new`:
1. Получает сообщение с payment_id
2. Эмулирует обработку платежа (2-5 секунд)
3. Обновляет статус в БД (succeeded/failed)
4. Отправляет webhook-уведомление
5. ACK/NACK сообщение

### Файл

`app/consumer/payment_handler.py`

### Реализация

```python
from faststream.rabbit import RabbitBroker, RabbitQueue
from app.services.payment_processor import PaymentProcessor
from app.services.webhook_client import WebhookClient

broker = RabbitBroker()

@broker.subscriber(
    queue=RabbitQueue(
        name="payments.new",
        durable=True,
        routing_key="payment.created"
    ),
    retry=3,  # Количество повторных попыток
)
async def handle_payment(message: dict):
    """
    Обрабатывает платёж из очереди
    
    Args:
        message: {"payment_id": str, "idempotency_key": str}
    
    Raises:
        Exception: При ошибке обработки (для retry/DLQ)
    """
    payment_id = message["payment_id"]
    
    # Обработка платежа
    processor = PaymentProcessor()
    payment = await processor.process_payment(payment_id)
    
    # Отправка webhook
    webhook_client = WebhookClient()
    await webhook_client.send_webhook(
        url=payment.webhook_url,
        payload={
            "payment_id": str(payment.id),
            "status": payment.status.value,
            "processed_at": payment.processed_at.isoformat()
        }
    )
```

### Обработка ошибок

| Ошибка | Действие | Retry | DLQ |
|--------|----------|-------|-----|
| Платёж не найден | Логирование, ACK | ❌ | ❌ |
| Платёж уже обработан | ACK (идемпотентность) | ❌ | ❌ |
| Ошибка БД (временная) | NACK, requeue | ✅ (3x) | ✅ после 3 попыток |
| Webhook timeout | NACK, requeue | ✅ (3x) | ✅ после 3 попыток |
| Webhook 4xx (клиентская ошибка) | Логирование, ACK | ❌ | ❌ |
| Webhook 5xx (серверная ошибка) | NACK, requeue | ✅ (3x) | ✅ после 3 попыток |

### Идемпотентность

Consumer проверяет статус платежа перед обработкой:
```python
if payment.status in [PaymentStatus.SUCCEEDED, PaymentStatus.FAILED]:
    # Платёж уже обработан, пропускаем
    return
```

Это защищает от повторной обработки при:
- Дублировании сообщений в RabbitMQ
- Ручной повторной отправке из DLQ
- Сбоях между обработкой и ACK

---

## Payment Processor

### Назначение

Эмулирует обработку платежа через платёжный шлюз.

### Файл

`app/services/payment_processor.py`

### Логика обработки

```python
import asyncio
import random
from app.models.payment import Payment, PaymentStatus
from app.repositories.payment_repository import PaymentRepository

class PaymentProcessor:
    def __init__(self):
        self.repo = PaymentRepository()
    
    async def process_payment(self, payment_id: str) -> Payment:
        """
        Эмулирует обработку платежа
        
        - Время обработки: 2-5 секунд
        - Вероятность успеха: 90%
        - Вероятность ошибки: 10%
        """
        payment = await self.repo.get_by_id(payment_id)
        
        # Проверка идемпотентности
        if payment.status != PaymentStatus.PENDING:
            return payment
        
        # Эмуляция обработки
        processing_time = random.uniform(2.0, 5.0)
        await asyncio.sleep(processing_time)
        
        # Определение результата (90% успех, 10% ошибка)
        success = random.random() < 0.9
        
        # Обновление статуса
        new_status = PaymentStatus.SUCCEEDED if success else PaymentStatus.FAILED
        payment = await self.repo.update_status(
            payment_id=payment_id,
            status=new_status
        )
        
        return payment
```

### Метрики (рекомендуется)

- `payment_processing_duration_seconds` — гистограмма времени обработки
- `payment_processing_total` — счётчик обработанных платежей (labels: status)
- `payment_processing_errors_total` — счётчик ошибок

---

## Webhook Client

### Назначение

Отправляет HTTP-уведомления на webhook_url клиента с retry-логикой.

### Файл

`app/services/webhook_client.py`

### Реализация

```python
import httpx
import asyncio
from typing import Dict, Any

class WebhookClient:
    def __init__(self):
        self.timeout = 5.0  # Таймаут HTTP-запроса
        self.max_retries = 3
        self.backoff_delays = [1, 2, 4]  # Экспоненциальная задержка
    
    async def send_webhook(self, url: str, payload: Dict[str, Any]) -> None:
        """
        Отправляет webhook с retry-логикой
        
        Args:
            url: Webhook URL клиента
            payload: Данные для отправки
        
        Raises:
            WebhookDeliveryError: После исчерпания всех попыток
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(self.max_retries):
                try:
                    response = await client.post(
                        url,
                        json=payload,
                        headers={"Content-Type": "application/json"}
                    )
                    
                    # Успех: 2xx статус
                    if 200 <= response.status_code < 300:
                        return
                    
                    # Клиентская ошибка 4xx: не retry
                    if 400 <= response.status_code < 500:
                        raise WebhookClientError(
                            f"Client error {response.status_code}: {response.text}"
                        )
                    
                    # Серверная ошибка 5xx: retry
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.backoff_delays[attempt])
                        continue
                    
                except (httpx.TimeoutException, httpx.ConnectError) as e:
                    # Сетевые ошибки: retry
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.backoff_delays[attempt])
                        continue
                    raise WebhookDeliveryError(
                        f"Failed after {self.max_retries} attempts: {str(e)}"
                    )
            
            raise WebhookDeliveryError(
                f"Failed after {self.max_retries} attempts"
            )
```

### Формат webhook payload

```json
{
  "payment_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "succeeded",
  "processed_at": "2026-04-20T10:00:05.123Z"
}
```

### Retry-логика

| Попытка | Задержка | Действие |
|---------|----------|----------|
| 1 | 0s | Немедленная отправка |
| 2 | 1s | Retry после 1 секунды |
| 3 | 2s | Retry после 2 секунд (итого 3s от попытки 2) |
| Итого | ~7s | 3 попытки за ~7 секунд |

### Обработка ответов

| Статус | Действие | Retry |
|--------|----------|-------|
| 2xx | Успех, завершение | ❌ |
| 4xx | Клиентская ошибка, логирование, ACK | ❌ |
| 5xx | Серверная ошибка, retry | ✅ |
| Timeout | Сетевая ошибка, retry | ✅ |
| Connection Error | Сетевая ошибка, retry | ✅ |

---

## Outbox Publisher

### Назначение

Фоновый процесс, публикующий неопубликованные события из таблицы `outbox` в RabbitMQ.

### Файл

`app/tasks/outbox_publisher.py`

### Реализация

```python
import asyncio
from app.services.outbox_service import OutboxService

class OutboxPublisher:
    def __init__(self):
        self.service = OutboxService()
        self.interval = 5  # Интервал проверки (секунды)
        self.batch_size = 100  # Количество событий за раз
    
    async def run(self):
        """
        Бесконечный цикл публикации событий
        """
        while True:
            try:
                await self.service.publish_pending_events(
                    limit=self.batch_size
                )
            except Exception as e:
                # Логирование ошибки, продолжение работы
                print(f"Outbox publisher error: {e}")
            
            await asyncio.sleep(self.interval)
```

### Запуск

Outbox Publisher запускается как отдельный процесс или background task:

**Вариант 1: Отдельный процесс**
```bash
python -m app.tasks.outbox_publisher
```

**Вариант 2: FastAPI background task**
```python
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(outbox_publisher.run())
```

### Логика публикации

1. Выбрать до 100 событий со статусом `pending`
2. Для каждого события:
   - Опубликовать в RabbitMQ
   - При успехе: обновить статус на `published`
   - При ошибке: оставить `pending`, повторить в следующей итерации
3. Ожидание 5 секунд
4. Повторить

### Обработка ошибок

| Ошибка | Действие |
|--------|----------|
| RabbitMQ недоступен | Логирование, события остаются pending, retry через 5s |
| Ошибка БД | Логирование, retry через 5s |
| Невалидный payload | Логирование, пропуск события (требует ручного анализа) |

---

## Мониторинг и алерты

### Метрики (рекомендуется)

**Consumer:**
- `consumer_messages_processed_total` — счётчик обработанных сообщений
- `consumer_processing_duration_seconds` — время обработки сообщения
- `consumer_errors_total` — счётчик ошибок (labels: error_type)

**Webhook:**
- `webhook_delivery_attempts_total` — счётчик попыток отправки
- `webhook_delivery_success_total` — счётчик успешных отправок
- `webhook_delivery_failures_total` — счётчик неудач

**Outbox:**
- `outbox_pending_events` — количество неопубликованных событий
- `outbox_publish_duration_seconds` — время публикации батча
- `outbox_publish_errors_total` — счётчик ошибок публикации

**DLQ:**
- `dlq_messages_total` — количество сообщений в DLQ

### Алерты

| Условие | Критичность | Действие |
|---------|-------------|----------|
| DLQ > 10 сообщений | Warning | Проверить причины ошибок |
| DLQ > 100 сообщений | Critical | Немедленное расследование |
| Outbox pending > 1000 | Warning | Проверить доступность RabbitMQ |
| Consumer lag > 5 минут | Critical | Масштабировать consumer |
| Webhook success rate < 80% | Warning | Проверить доступность клиентских эндпоинтов |

---

## Масштабирование

### Горизонтальное масштабирование Consumer

Запустить несколько инстансов consumer:
```bash
# Инстанс 1
python -m app.consumer.payment_handler

# Инстанс 2
python -m app.consumer.payment_handler

# Инстанс 3
python -m app.consumer.payment_handler
```

RabbitMQ автоматически распределяет сообщения между consumer (competing consumers pattern).

**Рекомендации:**
- Количество consumer ≤ количество сообщений в очереди
- Мониторить CPU и memory каждого инстанса
- Использовать `prefetch_count` для контроля нагрузки

### Вертикальное масштабирование

- Увеличить `prefetch_count` для обработки большего количества сообщений параллельно
- Оптимизировать запросы к БД (индексы, connection pooling)
- Использовать async I/O для webhook-отправки

---

## Очистка данных

### Outbox события

Рекомендуется периодически удалять старые опубликованные события:

```sql
DELETE FROM outbox
WHERE status = 'published'
  AND published_at < NOW() - INTERVAL '7 days';
```

Запускать через cron или scheduled task (например, раз в день).

### DLQ сообщения

RabbitMQ автоматически удаляет сообщения из DLQ через 7 дней (настроено через TTL).

Для ручного анализа:
```bash
# Просмотр сообщений в DLQ
rabbitmqadmin get queue=payments.new.dlq count=10

# Повторная отправка в основную очередь
rabbitmqadmin publish routing_key=payment.created payload='...'
```
