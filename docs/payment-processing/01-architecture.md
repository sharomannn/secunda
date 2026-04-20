---
date: 2026-04-20
feature: payment-processing
---

# Архитектура: Payment Processing Microservice

## L1 — Системный контекст

Микросервис обработки платежей взаимодействует с внешними клиентами через REST API и отправляет webhook-уведомления о результатах обработки.

```mermaid
C4Context
    title Системный контекст: Payment Processing

    Person(client, "Клиент", "Внешняя система, инициирующая платежи")
    System(payment_service, "Payment Service", "Микросервис обработки платежей")
    System_Ext(webhook_receiver, "Webhook Receiver", "Система клиента для получения уведомлений")
    
    Rel(client, payment_service, "Создаёт платежи, получает статус", "REST API, X-API-Key")
    Rel(payment_service, webhook_receiver, "Отправляет уведомления о результате", "HTTP POST")
    
    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

**Актёры:**
- **Клиент** — внешняя система, создающая платежи через API
- **Webhook Receiver** — система клиента, принимающая уведомления о результатах

**Границы системы:**
- Вход: REST API с аутентификацией по X-API-Key
- Выход: HTTP webhook на URL, указанный клиентом

## L2 — Контейнеры

Микросервис состоит из API-приложения, consumer-воркера, базы данных и брокера сообщений.

```mermaid
C4Container
    title Контейнеры: Payment Service

    Person(client, "Клиент")
    System_Ext(webhook_receiver, "Webhook Receiver")

    Container_Boundary(payment_service, "Payment Service") {
        Container(api, "FastAPI Application", "FastAPI, Pydantic", "Принимает запросы, валидирует, записывает в БД и Outbox")
        Container(consumer, "Payment Consumer", "FastStream", "Обрабатывает платежи, обновляет статус, отправляет webhook")
        ContainerDb(db, "PostgreSQL", "База данных", "Хранит платежи и outbox-события")
        ContainerQueue(mq, "RabbitMQ", "Message Broker", "Очереди payments.new и DLQ")
    }

    Rel(client, api, "POST /api/v1/payments, GET /api/v1/payments/{id}", "HTTPS + X-API-Key")
    Rel(api, db, "Записывает Payment и Outbox", "SQLAlchemy async")
    Rel(api, mq, "Публикует события из Outbox", "AMQP")
    Rel(consumer, mq, "Подписан на payments.new", "AMQP")
    Rel(consumer, db, "Обновляет статус платежа", "SQLAlchemy async")
    Rel(consumer, webhook_receiver, "POST webhook_url", "HTTP")
    Rel(consumer, mq, "Отправляет в DLQ при исчерпании retry", "AMQP")

    UpdateLayoutConfig($c4ShapeInRow="2", $c4BoundaryInRow="1")
```

**Компоненты:**
- **FastAPI Application** — REST API, валидация, запись в БД
- **Payment Consumer** — асинхронная обработка, webhook-отправка
- **PostgreSQL** — хранение платежей и outbox-событий
- **RabbitMQ** — брокер сообщений с DLQ

**Потоки данных:**
1. API → DB: запись Payment + Outbox (транзакция)
2. API → MQ: публикация события из Outbox
3. Consumer ← MQ: получение события
4. Consumer → DB: обновление статуса
5. Consumer → Webhook: уведомление клиента

## L3 — Компоненты

Детализация внутренней структуры FastAPI Application и Payment Consumer.

### FastAPI Application

```mermaid
C4Component
    title Компоненты: FastAPI Application

    Container_Boundary(api, "FastAPI Application") {
        Component(router, "Payment Router", "FastAPI Router", "Маршрутизация /api/v1/payments")
        Component(auth, "API Key Middleware", "Middleware", "Проверка X-API-Key")
        Component(schema, "Pydantic Schemas", "Pydantic v2", "Валидация запросов/ответов")
        Component(service, "Payment Service", "Business Logic", "Создание платежа, idempotency check")
        Component(outbox_svc, "Outbox Service", "Business Logic", "Запись и публикация событий")
        Component(repo, "Payment Repository", "SQLAlchemy", "ORM-операции с Payment")
        Component(outbox_repo, "Outbox Repository", "SQLAlchemy", "ORM-операции с Outbox")
    }

    ContainerDb(db, "PostgreSQL")
    ContainerQueue(mq, "RabbitMQ")

    Rel(router, auth, "Проверяет аутентификацию")
    Rel(router, schema, "Валидирует данные")
    Rel(router, service, "Вызывает бизнес-логику")
    Rel(service, repo, "Создаёт/читает Payment")
    Rel(service, outbox_svc, "Записывает событие в Outbox")
    Rel(outbox_svc, outbox_repo, "Сохраняет Outbox-запись")
    Rel(repo, db, "ORM queries")
    Rel(outbox_repo, db, "ORM queries")
    Rel(outbox_svc, mq, "Публикует событие")

    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

**Слои:**
- **Presentation** — Router, Middleware, Schemas
- **Business Logic** — Payment Service, Outbox Service
- **Data Access** — Repositories (Payment, Outbox)

**Ключевые компоненты:**
- **API Key Middleware** — проверяет X-API-Key для всех запросов
- **Payment Service** — проверяет idempotency key, создаёт платёж
- **Outbox Service** — реализует Outbox pattern (запись + публикация)

### Payment Consumer

```mermaid
C4Component
    title Компоненты: Payment Consumer

    Container_Boundary(consumer, "Payment Consumer") {
        Component(handler, "Payment Handler", "FastStream Handler", "Обрабатывает сообщения из payments.new")
        Component(processor, "Payment Processor", "Business Logic", "Эмулирует обработку платежа (2-5 сек)")
        Component(webhook, "Webhook Client", "HTTP Client", "Отправляет webhook с retry")
        Component(repo, "Payment Repository", "SQLAlchemy", "Обновляет статус платежа")
    }

    ContainerQueue(mq, "RabbitMQ")
    ContainerDb(db, "PostgreSQL")
    System_Ext(webhook_receiver, "Webhook Receiver")

    Rel(handler, mq, "Подписан на payments.new")
    Rel(handler, processor, "Передаёт payment_id")
    Rel(processor, repo, "Обновляет статус")
    Rel(processor, webhook, "Отправляет уведомление")
    Rel(webhook, webhook_receiver, "POST webhook_url")
    Rel(repo, db, "ORM queries")
    Rel(handler, mq, "Отправляет в DLQ при ошибке")

    UpdateLayoutConfig($c4ShapeInRow="2", $c4BoundaryInRow="1")
```

**Ключевые компоненты:**
- **Payment Handler** — FastStream subscriber на очередь payments.new
- **Payment Processor** — эмулирует обработку (90% успех, 10% fail)
- **Webhook Client** — отправка с retry (3 попытки, exponential backoff)

**Обработка ошибок:**
- Retry на уровне RabbitMQ (3 попытки)
- Dead Letter Queue для невосстановимых сообщений
- Exponential backoff для webhook (1s, 2s, 4s)

## Архитектурные слои

| Слой | Назначение | Компоненты |
|------|------------|------------|
| **Presentation** | HTTP API, валидация | Router, Middleware, Schemas |
| **Business Logic** | Бизнес-правила, оркестрация | Services (Payment, Outbox, Processor) |
| **Data Access** | Работа с БД | Repositories (SQLAlchemy) |
| **Infrastructure** | Внешние системы | RabbitMQ, HTTP Client |

## Паттерны проектирования

### Outbox Pattern
- Запись события в таблицу `outbox` в той же транзакции, что и `payment`
- Отдельный процесс публикует события из `outbox` в RabbitMQ
- Гарантирует at-least-once delivery

### Repository Pattern
- Инкапсуляция ORM-операций
- Упрощение тестирования (mock repositories)

### Idempotency
- Проверка `idempotency_key` перед созданием платежа
- Возврат существующего платежа при повторном запросе

### Retry with Exponential Backoff
- 3 попытки отправки webhook
- Задержки: 1s, 2s, 4s
- Dead Letter Queue после исчерпания попыток

## Масштабирование

**Горизонтальное:**
- API: несколько инстансов за load balancer
- Consumer: несколько воркеров на одной очереди (competing consumers)

**Вертикальное:**
- PostgreSQL: индексы на `idempotency_key`, `status`, `created_at`
- RabbitMQ: prefetch_count для контроля нагрузки

## Безопасность

- **Аутентификация:** статический X-API-Key (переменная окружения)
- **Валидация:** Pydantic schemas для всех входных данных
- **Secrets:** все чувствительные данные в environment variables
- **HTTPS:** для production (в ТЗ не указано, но рекомендуется)

## Мониторинг и наблюдаемость

**Логирование:**
- Структурированные логи (JSON)
- Уровни: INFO для бизнес-событий, ERROR для ошибок
- Correlation ID для трейсинга запросов

**Метрики (рекомендуется):**
- Количество созданных платежей
- Распределение статусов (succeeded/failed)
- Время обработки платежа
- Количество retry webhook
- Размер DLQ

**Health checks:**
- `/health` — проверка доступности API
- Проверка подключения к PostgreSQL и RabbitMQ
