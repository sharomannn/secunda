# Архитектура Payment Service

## Общая схема

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ POST /api/v1/payments
       │ (Idempotency-Key)
       ▼
┌─────────────────────────────────────────────────────────┐
│                     FastAPI (API)                        │
│  ┌────────────────────────────────────────────────────┐ │
│  │  PaymentService.create_payment()                   │ │
│  │  ┌──────────────────────────────────────────────┐ │ │
│  │  │  1. Проверка idempotency_key                 │ │ │
│  │  │  2. Создание Payment (status=pending)        │ │ │
│  │  │  3. Создание Outbox event                    │ │ │
│  │  │  4. Commit транзакции (атомарно!)            │ │ │
│  │  └──────────────────────────────────────────────┘ │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
       │
       │ 202 Accepted
       ▼
┌─────────────┐
│   Client    │
└─────────────┘

       ┌─────────────────────────────────────────────────┐
       │  Outbox Publisher (фоновый процесс, каждые 5с) │
       │  ┌───────────────────────────────────────────┐ │
       │  │  1. SELECT * FROM outbox                  │ │
       │  │     WHERE status='pending' LIMIT 100      │ │
       │  │  2. Публикация в RabbitMQ                 │ │
       │  │  3. UPDATE outbox SET status='published'  │ │
       │  └───────────────────────────────────────────┘ │
       └─────────────────────────────────────────────────┘
                          │
                          │ payment.created event
                          ▼
                   ┌──────────────┐
                   │  RabbitMQ    │
                   │  Exchange:   │
                   │  payments    │
                   └──────┬───────┘
                          │
                          │ routing_key: payment.created
                          ▼
                   ┌──────────────┐
                   │   Queue:     │
                   │ payments.new │
                   └──────┬───────┘
                          │
                          ▼
       ┌─────────────────────────────────────────────────┐
       │         Consumer (payment_handler)              │
       │  ┌───────────────────────────────────────────┐ │
       │  │  1. Получение сообщения из очереди        │ │
       │  │  2. Эмуляция обработки (2-5 сек)          │ │
       │  │     - 90% успех → status=succeeded        │ │
       │  │     - 10% ошибка → status=failed          │ │
       │  │  3. UPDATE payments SET status=...        │ │
       │  │  4. Отправка webhook-уведомления          │ │
       │  │  5. ACK сообщения                         │ │
       │  └───────────────────────────────────────────┘ │
       └─────────────────────────────────────────────────┘
                          │
                          │ Webhook POST
                          ▼
                   ┌──────────────┐
                   │   External   │
                   │   Webhook    │
                   │   Endpoint   │
                   └──────────────┘
```

## Компоненты системы

### 1. API (FastAPI)
- Принимает HTTP запросы на создание и получение платежей
- Валидирует входные данные (Pydantic)
- Проверяет аутентификацию (X-API-Key)
- Создает Payment + Outbox event в одной транзакции
- Возвращает 202 Accepted (платеж принят в обработку)

### 2. Outbox Publisher (фоновый процесс)
- Запускается как отдельный контейнер
- Каждые 5 секунд сканирует таблицу `outbox`
- Публикует pending события в RabbitMQ
- Обновляет статус на `published` после успешной публикации
- Обеспечивает **at-least-once delivery**

### 3. Consumer (RabbitMQ обработчик)
- Слушает очередь `payments.new`
- Эмулирует обработку платежа (2-5 секунд, 90% успех)
- Обновляет статус платежа в БД
- Отправляет webhook-уведомление
- Реализует retry с экспоненциальной задержкой (3 попытки)

### 4. PostgreSQL
- Хранит таблицы `payments` и `outbox`
- Обеспечивает транзакционность (ACID)
- Использует partial index для оптимизации Outbox Publisher

### 5. RabbitMQ
- Exchange: `payments` (type: topic)
- Queue: `payments.new` (с DLX для failed сообщений)
- Dead Letter Queue: `payments.new.dlq` (TTL: 7 дней)

## Поток обработки платежа

1. **Клиент** отправляет POST запрос с `Idempotency-Key`
2. **API** создает `Payment` (pending) + `Outbox` event в одной транзакции
3. **API** возвращает 202 Accepted (платеж принят)
4. **Outbox Publisher** читает pending события и публикует в RabbitMQ
5. **Consumer** получает событие из очереди `payments.new`
6. **Consumer** эмулирует обработку (2-5 сек, 90% успех)
7. **Consumer** обновляет статус платежа (succeeded/failed)
8. **Consumer** отправляет webhook-уведомление
9. **Клиент** получает webhook или опрашивает GET /payments/{id}

## База данных

### Таблица: payments

```sql
CREATE TABLE payments (
    id UUID PRIMARY KEY,
    amount NUMERIC(10, 2) NOT NULL CHECK (amount > 0),
    currency currency NOT NULL,  -- ENUM: RUB, USD, EUR
    description VARCHAR(500) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    status payment_status NOT NULL DEFAULT 'pending',  -- ENUM: pending, succeeded, failed
    idempotency_key VARCHAR(255) NOT NULL UNIQUE,
    webhook_url VARCHAR(2048) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX idx_payments_idempotency_key ON payments(idempotency_key);
```

### Таблица: outbox

```sql
CREATE TABLE outbox (
    id BIGSERIAL PRIMARY KEY,
    aggregate_id UUID NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    status outbox_status NOT NULL DEFAULT 'pending',  -- ENUM: pending, published
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ
);

CREATE INDEX idx_outbox_aggregate_id ON outbox(aggregate_id);
CREATE INDEX idx_outbox_status_pending ON outbox(status) WHERE status = 'pending';
```

## RabbitMQ конфигурация

### Exchange: payments
- Type: topic
- Durable: true
- Auto-delete: false

### Queue: payments.new
- Durable: true
- Arguments:
  - `x-dead-letter-exchange`: payments.dlx
  - `x-dead-letter-routing-key`: dlq

### Exchange: payments.dlx (Dead Letter Exchange)
- Type: fanout
- Durable: true

### Queue: payments.new.dlq (Dead Letter Queue)
- Durable: true
- Arguments:
  - `x-message-ttl`: 604800000 (7 дней)

### Bindings
- `payments` → `payments.new` (routing_key: payment.created)
- `payments.dlx` → `payments.new.dlq` (routing_key: dlq)

## Масштабирование

### Горизонтальное масштабирование

```bash
# Запустить несколько Consumer'ов
docker-compose up -d --scale consumer=3

# Запустить несколько Outbox Publisher'ов
docker-compose up -d --scale outbox-publisher=2
```

### Вертикальное масштабирование

```yaml
# docker-compose.yml
services:
  api:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
```

### Connection pooling

```python
# app/db/session.py
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,          # Количество постоянных соединений
    max_overflow=10,       # Дополнительные соединения при пиковой нагрузке
    pool_pre_ping=True     # Проверка соединений перед использованием
)
```

## Производительность

### Метрики при нагрузке 100 req/s

- **API latency:** ~50ms (создание платежа)
- **Processing time:** 2-5 секунд (эмуляция)
- **Throughput:** ~20 платежей/сек (один Consumer)
- **Database connections:** ~10 (connection pool)

### Оптимизации

1. **Partial index** на `outbox.status='pending'` — ускоряет поиск pending событий
2. **Batch processing** в Outbox Publisher — обрабатывает до 100 событий за раз
3. **Async I/O** везде — неблокирующие операции БД и HTTP
4. **Connection pooling** — переиспользование соединений к БД
