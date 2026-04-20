---
date: 2026-04-20
feature: payment-processing
---

# Поведение: Payment Processing Microservice

## Use Case 1: Создание платежа (успешный сценарий)

**Актор:** Внешний клиент
**Предусловие:** Клиент имеет валидный X-API-Key
**Цель:** Создать новый платёж и получить подтверждение приёма

### Happy path

```mermaid
sequenceDiagram
    participant Client
    participant API as FastAPI Router
    participant Auth as API Key Middleware
    participant Schema as Pydantic Schema
    participant Service as Payment Service
    participant Repo as Payment Repository
    participant OutboxSvc as Outbox Service
    participant DB as PostgreSQL
    participant MQ as RabbitMQ

    Client->>API: POST /api/v1/payments<br/>Headers: X-API-Key, Idempotency-Key<br/>Body: {amount, currency, description, metadata, webhook_url}
    API->>Auth: Проверить X-API-Key
    Auth-->>API: ✓ Авторизован
    API->>Schema: Валидировать запрос
    Schema-->>API: ✓ Данные валидны
    API->>Service: create_payment(data, idempotency_key)
    Service->>Repo: check_idempotency_key(idempotency_key)
    Repo->>DB: SELECT * FROM payments WHERE idempotency_key = ?
    DB-->>Repo: NULL (ключ не найден)
    Repo-->>Service: Платёж не существует
    
    Service->>Repo: create(payment_data)
    Service->>OutboxSvc: create_event(payment_id, "payment.created")
    
    Note over Service,OutboxSvc: Транзакция BEGIN
    Repo->>DB: INSERT INTO payments (...)
    OutboxSvc->>DB: INSERT INTO outbox (aggregate_id, event_type, payload)
    DB-->>Service: ✓ Транзакция COMMIT
    Note over Service,OutboxSvc: Транзакция END
    
    OutboxSvc->>MQ: Publish to payments.new<br/>{payment_id, idempotency_key}
    MQ-->>OutboxSvc: ✓ Acknowledged
    OutboxSvc->>DB: UPDATE outbox SET status='published'
    
    Service-->>API: Payment(id, status='pending', created_at)
    API-->>Client: 202 Accepted<br/>{id, status, created_at}
```

### Ошибки и edge cases

#### 1.1 Невалидный X-API-Key

```mermaid
sequenceDiagram
    participant Client
    participant API as FastAPI Router
    participant Auth as API Key Middleware

    Client->>API: POST /api/v1/payments<br/>Headers: X-API-Key=invalid
    API->>Auth: Проверить X-API-Key
    Auth-->>API: ✗ Неверный ключ
    API-->>Client: 401 Unauthorized<br/>{"detail": "Invalid API key"}
```

#### 1.2 Невалидные данные запроса

```mermaid
sequenceDiagram
    participant Client
    participant API as FastAPI Router
    participant Auth as API Key Middleware
    participant Schema as Pydantic Schema

    Client->>API: POST /api/v1/payments<br/>Body: {amount: -100, currency: "INVALID"}
    API->>Auth: Проверить X-API-Key
    Auth-->>API: ✓ Авторизован
    API->>Schema: Валидировать запрос
    Schema-->>API: ✗ ValidationError
    API-->>Client: 422 Unprocessable Entity<br/>{"detail": [{"loc": ["amount"], "msg": "must be positive"}]}
```

#### 1.3 Повторный запрос с тем же Idempotency-Key

```mermaid
sequenceDiagram
    participant Client
    participant API as FastAPI Router
    participant Service as Payment Service
    participant Repo as Payment Repository
    participant DB as PostgreSQL

    Client->>API: POST /api/v1/payments<br/>Headers: Idempotency-Key=abc123
    API->>Service: create_payment(data, "abc123")
    Service->>Repo: check_idempotency_key("abc123")
    Repo->>DB: SELECT * FROM payments WHERE idempotency_key = 'abc123'
    DB-->>Repo: Payment(id=1, status='pending')
    Repo-->>Service: Платёж уже существует
    Service-->>API: Existing Payment(id=1, status='pending')
    API-->>Client: 200 OK<br/>{id: 1, status: 'pending', created_at}
    
    Note over Client,API: Возвращается существующий платёж,<br/>новый не создаётся
```

#### 1.4 Ошибка публикации в RabbitMQ

```mermaid
sequenceDiagram
    participant Service as Payment Service
    participant Repo as Payment Repository
    participant OutboxSvc as Outbox Service
    participant DB as PostgreSQL
    participant MQ as RabbitMQ

    Service->>Repo: create(payment_data)
    Service->>OutboxSvc: create_event(payment_id, "payment.created")
    
    Repo->>DB: INSERT INTO payments
    OutboxSvc->>DB: INSERT INTO outbox
    DB-->>Service: ✓ COMMIT
    
    OutboxSvc->>MQ: Publish to payments.new
    MQ-->>OutboxSvc: ✗ Connection Error
    
    Note over OutboxSvc: Событие остаётся в outbox<br/>со статусом 'pending'
    Note over OutboxSvc: Фоновый процесс повторит<br/>публикацию позже
    
    Service-->>Service: Платёж создан, событие в очереди на публикацию
```

---

## Use Case 2: Получение информации о платеже

**Актор:** Внешний клиент
**Предусловие:** Клиент имеет валидный X-API-Key и payment_id
**Цель:** Получить актуальный статус платежа

### Happy path

```mermaid
sequenceDiagram
    participant Client
    participant API as FastAPI Router
    participant Auth as API Key Middleware
    participant Service as Payment Service
    participant Repo as Payment Repository
    participant DB as PostgreSQL

    Client->>API: GET /api/v1/payments/{payment_id}<br/>Headers: X-API-Key
    API->>Auth: Проверить X-API-Key
    Auth-->>API: ✓ Авторизован
    API->>Service: get_payment(payment_id)
    Service->>Repo: get_by_id(payment_id)
    Repo->>DB: SELECT * FROM payments WHERE id = ?
    DB-->>Repo: Payment(id, amount, currency, status, ...)
    Repo-->>Service: Payment
    Service-->>API: Payment
    API-->>Client: 200 OK<br/>{id, amount, currency, status, description, metadata, webhook_url, created_at, processed_at}
```

### Ошибки и edge cases

#### 2.1 Платёж не найден

```mermaid
sequenceDiagram
    participant Client
    participant API as FastAPI Router
    participant Service as Payment Service
    participant Repo as Payment Repository
    participant DB as PostgreSQL

    Client->>API: GET /api/v1/payments/non-existent-id
    API->>Service: get_payment("non-existent-id")
    Service->>Repo: get_by_id("non-existent-id")
    Repo->>DB: SELECT * FROM payments WHERE id = ?
    DB-->>Repo: NULL
    Repo-->>Service: None
    Service-->>API: PaymentNotFound
    API-->>Client: 404 Not Found<br/>{"detail": "Payment not found"}
```

---

## Use Case 3: Обработка платежа (Consumer)

**Актор:** Payment Consumer
**Предусловие:** Событие опубликовано в очередь payments.new
**Цель:** Обработать платёж, обновить статус, отправить webhook

### Happy path

```mermaid
sequenceDiagram
    participant MQ as RabbitMQ
    participant Handler as Payment Handler
    participant Processor as Payment Processor
    participant Repo as Payment Repository
    participant DB as PostgreSQL
    participant Webhook as Webhook Client
    participant Client as Client Webhook URL

    MQ->>Handler: Consume message from payments.new<br/>{payment_id, idempotency_key}
    Handler->>Processor: process_payment(payment_id)
    
    Processor->>Repo: get_by_id(payment_id)
    Repo->>DB: SELECT * FROM payments WHERE id = ?
    DB-->>Repo: Payment(id, status='pending', webhook_url)
    Repo-->>Processor: Payment
    
    Note over Processor: Эмуляция обработки<br/>sleep(random(2, 5))<br/>90% success, 10% fail
    
    alt Успешная обработка (90%)
        Processor->>Repo: update_status(payment_id, 'succeeded')
        Repo->>DB: UPDATE payments SET status='succeeded', processed_at=NOW()
        DB-->>Repo: ✓
        
        Processor->>Webhook: send_webhook(webhook_url, {payment_id, status: 'succeeded'})
        Webhook->>Client: POST webhook_url<br/>Body: {payment_id, status: 'succeeded', processed_at}
        Client-->>Webhook: 200 OK
        Webhook-->>Processor: ✓ Webhook доставлен
    else Неудачная обработка (10%)
        Processor->>Repo: update_status(payment_id, 'failed')
        Repo->>DB: UPDATE payments SET status='failed', processed_at=NOW()
        DB-->>Repo: ✓
        
        Processor->>Webhook: send_webhook(webhook_url, {payment_id, status: 'failed'})
        Webhook->>Client: POST webhook_url<br/>Body: {payment_id, status: 'failed', processed_at}
        Client-->>Webhook: 200 OK
        Webhook-->>Processor: ✓ Webhook доставлен
    end
    
    Processor-->>Handler: ✓ Обработка завершена
    Handler->>MQ: ACK message
```

### Ошибки и edge cases

#### 3.1 Ошибка отправки webhook (с retry)

```mermaid
sequenceDiagram
    participant Processor as Payment Processor
    participant Webhook as Webhook Client
    participant Client as Client Webhook URL

    Processor->>Webhook: send_webhook(webhook_url, payload)
    
    Note over Webhook: Попытка 1
    Webhook->>Client: POST webhook_url
    Client-->>Webhook: ✗ 500 Internal Server Error
    
    Note over Webhook: Ожидание 1 секунда
    Note over Webhook: Попытка 2
    Webhook->>Client: POST webhook_url
    Client-->>Webhook: ✗ Timeout
    
    Note over Webhook: Ожидание 2 секунды
    Note over Webhook: Попытка 3
    Webhook->>Client: POST webhook_url
    Client-->>Webhook: 200 OK
    
    Webhook-->>Processor: ✓ Webhook доставлен после 3 попыток
```

#### 3.2 Исчерпание retry и отправка в DLQ

```mermaid
sequenceDiagram
    participant MQ as RabbitMQ
    participant Handler as Payment Handler
    participant Processor as Payment Processor
    participant Webhook as Webhook Client
    participant Client as Client Webhook URL
    participant DLQ as Dead Letter Queue

    MQ->>Handler: Consume message (попытка 1)
    Handler->>Processor: process_payment(payment_id)
    Processor->>Webhook: send_webhook(webhook_url, payload)
    
    loop 3 попытки webhook
        Webhook->>Client: POST webhook_url
        Client-->>Webhook: ✗ Error
    end
    
    Webhook-->>Processor: ✗ Все попытки исчерпаны
    Processor-->>Handler: ✗ Ошибка обработки
    Handler->>MQ: NACK message (requeue)
    
    Note over MQ: RabbitMQ повторяет доставку
    
    MQ->>Handler: Consume message (попытка 2)
    Handler->>Processor: process_payment(payment_id)
    Processor-->>Handler: ✗ Ошибка
    Handler->>MQ: NACK message (requeue)
    
    MQ->>Handler: Consume message (попытка 3)
    Handler->>Processor: process_payment(payment_id)
    Processor-->>Handler: ✗ Ошибка
    Handler->>MQ: NACK message (no requeue)
    
    MQ->>DLQ: Отправить в payments.new.dlq
    
    Note over DLQ: Сообщение сохранено для<br/>ручного анализа
```

#### 3.3 Платёж уже обработан (идемпотентность consumer)

```mermaid
sequenceDiagram
    participant MQ as RabbitMQ
    participant Handler as Payment Handler
    participant Processor as Payment Processor
    participant Repo as Payment Repository
    participant DB as PostgreSQL

    MQ->>Handler: Consume message<br/>{payment_id}
    Handler->>Processor: process_payment(payment_id)
    Processor->>Repo: get_by_id(payment_id)
    Repo->>DB: SELECT * FROM payments WHERE id = ?
    DB-->>Repo: Payment(id, status='succeeded')
    Repo-->>Processor: Payment
    
    Note over Processor: Статус уже 'succeeded' или 'failed'<br/>Обработка не требуется
    
    Processor-->>Handler: ✓ Уже обработан (skip)
    Handler->>MQ: ACK message
    
    Note over Handler,MQ: Сообщение удалено из очереди<br/>без повторной обработки
```

---

## Use Case 4: Публикация событий из Outbox (фоновый процесс)

**Актор:** Outbox Publisher (фоновая задача)
**Предусловие:** Есть неопубликованные события в таблице outbox
**Цель:** Гарантировать публикацию всех событий в RabbitMQ

### Happy path

```mermaid
sequenceDiagram
    participant Scheduler as Background Scheduler
    participant OutboxSvc as Outbox Service
    participant DB as PostgreSQL
    participant MQ as RabbitMQ

    loop Каждые N секунд
        Scheduler->>OutboxSvc: publish_pending_events()
        OutboxSvc->>DB: SELECT * FROM outbox WHERE status='pending' LIMIT 100
        DB-->>OutboxSvc: List[OutboxEvent]
        
        loop Для каждого события
            OutboxSvc->>MQ: Publish event to payments.new
            alt Успешная публикация
                MQ-->>OutboxSvc: ✓ Acknowledged
                OutboxSvc->>DB: UPDATE outbox SET status='published', published_at=NOW()
            else Ошибка публикации
                MQ-->>OutboxSvc: ✗ Error
                Note over OutboxSvc: Событие остаётся 'pending'<br/>Будет повторено в следующей итерации
            end
        end
    end
```

### Ошибки и edge cases

#### 4.1 RabbitMQ недоступен

```mermaid
sequenceDiagram
    participant Scheduler as Background Scheduler
    participant OutboxSvc as Outbox Service
    participant DB as PostgreSQL
    participant MQ as RabbitMQ

    Scheduler->>OutboxSvc: publish_pending_events()
    OutboxSvc->>DB: SELECT * FROM outbox WHERE status='pending'
    DB-->>OutboxSvc: List[OutboxEvent]
    
    OutboxSvc->>MQ: Publish event
    MQ-->>OutboxSvc: ✗ Connection refused
    
    Note over OutboxSvc: Логирование ошибки<br/>Событие остаётся 'pending'
    
    OutboxSvc-->>Scheduler: ✗ Частичная публикация
    
    Note over Scheduler: Следующая попытка через N секунд
```
