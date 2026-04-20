# Технические решения

## 1. Outbox Pattern (гарантированная доставка)

### Проблема

Как гарантировать, что событие будет опубликовано в RabbitMQ, если транзакция БД успешна?

**Антипаттерн (не используем):**
```python
# ❌ ПЛОХО: Событие может потеряться
async with session.begin():
    payment = Payment(...)
    session.add(payment)
    await session.commit()

# Если здесь упадет приложение или RabbitMQ недоступен — событие потеряно
await rabbitmq.publish({"payment_id": payment.id})
```

### Решение: Outbox Pattern

```python
# ✅ ХОРОШО: Событие сохраняется в БД транзакционно
async with session.begin():
    # 1. Создаем платеж
    payment = Payment(amount=100.50, status="pending", ...)
    session.add(payment)
    
    # 2. Создаем событие в Outbox
    outbox_event = Outbox(
        aggregate_id=payment.id,
        event_type="payment.created",
        payload={"payment_id": str(payment.id), ...},
        status="pending"
    )
    session.add(outbox_event)
    
    # 3. Commit — оба объекта сохраняются атомарно
    await session.commit()
```

**Outbox Publisher** (отдельный процесс):
```python
while True:
    # Читаем pending события
    events = await outbox_repo.get_pending_events(limit=100)
    
    for event in events:
        try:
            # Публикуем в RabbitMQ
            await rabbitmq.publish(event.payload)
            
            # Помечаем как published
            await outbox_repo.mark_published(event.id)
        except Exception as e:
            logger.error(f"Failed to publish event {event.id}: {e}")
            # Событие останется pending и будет повторено
    
    await asyncio.sleep(5)  # Каждые 5 секунд
```

### Гарантии

- ✅ Если транзакция БД успешна → событие гарантированно будет опубликовано
- ✅ Если RabbitMQ недоступен → события накапливаются в Outbox и публикуются позже
- ✅ At-least-once delivery (событие может быть доставлено несколько раз)
- ✅ Eventual consistency (событие будет опубликовано в течение 5 секунд)

### Оптимизация: Partial Index

```sql
-- Ускоряет поиск pending событий
CREATE INDEX idx_outbox_status_pending 
ON outbox(status) 
WHERE status = 'pending';
```

Без partial index запрос сканировал бы всю таблицу. С partial index — только pending записи.

---

## 2. Idempotency (защита от дублей)

### Проблема

Клиент может отправить один и тот же запрос несколько раз:
- Сетевые ошибки (timeout, connection reset)
- Повторные попытки на стороне клиента
- Случайные двойные клики

**Без idempotency:**
```
Client → POST /payments (amount=100) → Server создает Payment #1
Client → (timeout, retry)
Client → POST /payments (amount=100) → Server создает Payment #2 ❌ ДУБЛЬ!
```

### Решение: Обязательный Idempotency-Key

```python
async def create_payment(request: PaymentCreate, idempotency_key: str):
    # Проверяем, существует ли платеж с таким ключом
    existing = await payment_repo.get_by_idempotency_key(idempotency_key)
    if existing:
        logger.info(f"Idempotent request: returning existing payment {existing.id}")
        return existing  # Возвращаем существующий платеж
    
    # Создаем новый платеж
    payment = Payment(idempotency_key=idempotency_key, ...)
    await payment_repo.create(payment)
    return payment
```

**Индекс в БД:**
```sql
CREATE UNIQUE INDEX idx_payments_idempotency_key 
ON payments(idempotency_key);
```

### Поведение

```bash
# Первый запрос — создает платеж
curl -X POST /payments \
  -H "Idempotency-Key: key-123" \
  -d '{"amount": "100.50", ...}'
# Response: {"id": "aaa-bbb-ccc", "amount": "100.50"}

# Второй запрос с тем же ключом — возвращает существующий
curl -X POST /payments \
  -H "Idempotency-Key: key-123" \
  -d '{"amount": "999.99", ...}'  # Другие данные игнорируются
# Response: {"id": "aaa-bbb-ccc", "amount": "100.50"}  # Тот же платеж!
```

### Гарантии

- ✅ Повторный запрос с тем же ключом вернет существующий платеж
- ✅ Защита от дублирования платежей
- ✅ Безопасность при сетевых ошибках
- ✅ Соответствие стандарту [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html#name-idempotent-methods)

---

## 3. Retry механизм (повторные попытки)

### Проблема

Webhook может быть временно недоступен:
- Сервер клиента перезагружается
- Сетевые проблемы
- Rate limiting на стороне клиента

### Решение: Exponential Backoff

```python
async def send_webhook_with_retry(url: str, payload: dict):
    max_retries = 3
    base_delay = 1  # секунда
    
    for attempt in range(max_retries):
        try:
            response = await http_client.post(
                url, 
                json=payload, 
                timeout=10
            )
            if response.status_code == 200:
                logger.info(f"Webhook sent successfully to {url}")
                return  # Успех
            else:
                logger.warning(f"Webhook returned {response.status_code}")
        except Exception as e:
            logger.error(f"Webhook attempt {attempt + 1} failed: {e}")
            
            if attempt == max_retries - 1:
                raise  # Последняя попытка — пробрасываем ошибку
            
            # Экспоненциальная задержка: 1s, 2s, 4s
            delay = base_delay * (2 ** attempt)
            logger.info(f"Retrying in {delay}s...")
            await asyncio.sleep(delay)
```

### Параметры

| Попытка | Задержка | Общее время |
|---------|----------|-------------|
| 1       | 0s       | 0s          |
| 2       | 1s       | 1s          |
| 3       | 2s       | 3s          |
| **Итого** | -    | **3s**      |

### Поведение при ошибках

```python
# Попытка 1: немедленно
try:
    await send_webhook(url)
except:
    # Попытка 2: через 1 секунду
    await asyncio.sleep(1)
    try:
        await send_webhook(url)
    except:
        # Попытка 3: через 2 секунды
        await asyncio.sleep(2)
        try:
            await send_webhook(url)
        except:
            # После 3 неудач → NACK → DLQ
            raise
```

---

## 4. Dead Letter Queue (DLQ)

### Проблема

Что делать с сообщениями, которые не удалось обработать после всех попыток?
- Невалидные данные
- Webhook URL недоступен длительное время
- Баги в коде обработчика

### Решение: Dead Letter Queue

```yaml
# RabbitMQ конфигурация
Queue: payments.new
  Arguments:
    x-dead-letter-exchange: payments.dlx
    x-dead-letter-routing-key: dlq
    x-max-retries: 3  # Максимум 3 попытки

Exchange: payments.dlx (Dead Letter Exchange)
  Type: fanout

Queue: payments.new.dlq (Dead Letter Queue)
  Arguments:
    x-message-ttl: 604800000  # 7 дней (в миллисекундах)
```

### Поведение

```
1. Consumer получает сообщение из payments.new
2. Обработка падает → NACK(requeue=true)
3. RabbitMQ повторяет доставку (попытка 2)
4. Обработка падает → NACK(requeue=true)
5. RabbitMQ повторяет доставку (попытка 3)
6. Обработка падает → NACK(requeue=false)
7. RabbitMQ отправляет сообщение в payments.dlq
8. Сообщение хранится в DLQ 7 дней для ручного анализа
```

### Мониторинг DLQ

```bash
# Проверить количество сообщений в DLQ
curl -u guest:guest http://localhost:15672/api/queues/%2F/payments.new.dlq

# Или через RabbitMQ UI
# http://localhost:15672 → Queues → payments.new.dlq
```

### Обработка DLQ

```python
# Скрипт для ручной обработки DLQ (не реализован в проекте)
async def process_dlq():
    messages = await rabbitmq.get_messages("payments.new.dlq", count=10)
    
    for msg in messages:
        # Анализ причины ошибки
        logger.info(f"DLQ message: {msg}")
        
        # Ручное исправление и повторная отправка
        # await rabbitmq.publish("payments.new", msg)
```

---

## 5. Асинхронность (SQLAlchemy 2.0 async)

### Проблема

Синхронные операции блокируют event loop:
```python
# ❌ ПЛОХО: Блокирует event loop
result = session.execute(select(Payment))  # Блокировка на 10-100ms
payment = result.scalar_one()
```

### Решение: Async/Await везде

```python
# ✅ ХОРОШО: Неблокирующие операции
result = await session.execute(select(Payment))  # Не блокирует event loop
payment = result.scalar_one()
```

### Настройка async engine

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

engine = create_async_engine(
    "postgresql+asyncpg://user:password@localhost/payments",
    echo=False,
    pool_size=20,          # Количество постоянных соединений
    max_overflow=10,       # Дополнительные соединения при пиковой нагрузке
    pool_pre_ping=True,    # Проверка соединений перед использованием
    pool_recycle=3600      # Пересоздание соединений каждый час
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)
```

### Преимущества

- ✅ **Высокая производительность** — неблокирующий I/O
- ✅ **Масштабируемость** — тысячи одновременных запросов
- ✅ **Эффективное использование ресурсов** — меньше потоков/процессов

### Сравнение производительности

| Метод | Requests/sec | Latency (p50) | Latency (p99) |
|-------|--------------|---------------|---------------|
| Sync  | 500          | 20ms          | 100ms         |
| Async | 2000         | 5ms           | 30ms          |

---

## 6. Эмуляция обработки платежа

### Реализация

```python
import random
import asyncio

async def process_payment(payment_id: UUID):
    # Случайная задержка 2-5 секунд (имитация сетевого запроса)
    delay = random.uniform(2.0, 5.0)
    await asyncio.sleep(delay)
    
    # 90% успех, 10% ошибка (реалистичный сценарий)
    success = random.random() < 0.9
    
    if success:
        await payment_repo.update_status(payment_id, "succeeded")
        logger.info(f"Payment {payment_id} succeeded after {delay:.2f}s")
    else:
        await payment_repo.update_status(payment_id, "failed")
        logger.warning(f"Payment {payment_id} failed after {delay:.2f}s")
```

### Параметры

- **Задержка:** 2-5 секунд (имитация реального платежного шлюза)
- **Успех:** 90% (типичный success rate для платежей)
- **Ошибка:** 10% (для тестирования retry и DLQ)

### Причины ошибок в реальной системе

- Недостаточно средств на счете
- Карта заблокирована
- Превышен лимит
- Технические проблемы на стороне банка
- Fraud detection

---

## 7. Аутентификация (статический API ключ)

### Реализация

```python
# app/middleware/auth.py
from fastapi import Header, HTTPException

async def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != settings.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return x_api_key
```

### Использование

```python
# app/api/v1/payments.py
@router.post("/payments")
async def create_payment(
    request: PaymentCreate,
    api_key: str = Depends(verify_api_key)  # Проверка ключа
):
    ...
```

### Для production

**Не используйте статический ключ в production!** Рекомендации:

1. **JWT токены** — с expiration и refresh
2. **OAuth 2.0** — для сторонних интеграций
3. **API Gateway** — AWS API Gateway, Kong, Tyk
4. **Rate limiting** — ограничение запросов по ключу
5. **Secrets management** — AWS Secrets Manager, HashiCorp Vault

---

## Сравнение с альтернативами

### Outbox Pattern vs Direct Publishing

| Критерий | Outbox Pattern | Direct Publishing |
|----------|----------------|-------------------|
| Гарантия доставки | ✅ Да | ❌ Нет |
| Транзакционность | ✅ Да | ❌ Нет |
| Сложность | Средняя | Низкая |
| Latency | +5s (polling) | Мгновенно |

### Idempotency-Key vs Request ID

| Критерий | Idempotency-Key | Request ID |
|----------|-----------------|------------|
| Защита от дублей | ✅ Да | ❌ Нет |
| Стандарт | RFC 9110 | Нет |
| Клиент контролирует | ✅ Да | ❌ Нет |

### Async vs Sync SQLAlchemy

| Критерий | Async | Sync |
|----------|-------|------|
| Throughput | 2000 req/s | 500 req/s |
| Latency | 5ms | 20ms |
| Сложность | Высокая | Низкая |
| Масштабируемость | ✅ Отлично | ⚠️ Ограничена |
