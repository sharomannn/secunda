---
date: 2026-04-20
feature: payment-processing
type: microservice
stack: FastAPI, SQLAlchemy 2.0, RabbitMQ, PostgreSQL
status: design
---

# Payment Processing Microservice

## Обзор

Асинхронный микросервис для обработки платежей с гарантией доставки событий и webhook-уведомлениями.

## Бизнес-цель

Принимать запросы на оплату, обрабатывать их через эмулированный платежный шлюз и уведомлять клиента о результате через webhook с гарантией доставки.

## Ключевые требования

### Функциональные
- Создание платежа с идемпотентностью (Idempotency-Key)
- Получение информации о платеже
- Асинхронная обработка через RabbitMQ
- Webhook-уведомления с retry-логикой
- Гарантия доставки событий (Outbox pattern)
- Dead Letter Queue для невосстановимых сообщений

### Нефункциональные
- Защита API статическим ключом (X-API-Key)
- 90% успешных платежей, 10% ошибок (эмуляция)
- Время обработки: 2-5 секунд
- 3 попытки retry с экспоненциальной задержкой
- Поддержка валют: RUB, USD, EUR

## Критерии приёмки

- [ ] POST /api/v1/payments возвращает 202 Accepted
- [ ] GET /api/v1/payments/{payment_id} возвращает детальную информацию
- [ ] Idempotency-Key защищает от дублей
- [ ] События публикуются в payments.new через outbox
- [ ] Consumer обрабатывает платёж и обновляет статус
- [ ] Webhook отправляется на указанный URL
- [ ] Retry работает при ошибках webhook
- [ ] DLQ получает сообщения после 3 неудач
- [ ] Docker Compose поднимает весь стек
- [ ] Все эндпоинты защищены X-API-Key

## Структура документации

### Обязательные документы
- `01-architecture.md` — C4-архитектура (L1→L2→L3)
- `02-behavior.md` — Sequence диаграммы use cases
- `03-decisions.md` — Архитектурные решения (ADR)
- `04-testing.md` — План тестирования

### Условные документы
- `05-async-tasks.md` — Consumer, webhook, retry-логика
- `06-models.md` — Модели Payment и Outbox
- `08-api-contract.md` — REST API контракты

### План реализации
- `plan/` — Создаётся после утверждения архитектуры

## Технологический стек

| Компонент | Технология | Версия |
|-----------|------------|--------|
| Framework | FastAPI | latest |
| ORM | SQLAlchemy | 2.0 (async) |
| Validation | Pydantic | v2 |
| Database | PostgreSQL | latest |
| Message Broker | RabbitMQ | latest |
| Messaging | FastStream | latest |
| Migrations | Alembic | latest |
| Containerization | Docker Compose | latest |

## Сущности

### Payment
- ID (UUID)
- Сумма (Decimal)
- Валюта (RUB/USD/EUR)
- Описание
- Метаданные (JSON)
- Статус (pending/succeeded/failed)
- Idempotency Key
- Webhook URL
- Даты создания и обработки

### Outbox
- ID
- Aggregate ID (Payment ID)
- Event Type
- Payload (JSON)
- Статус (pending/published)
- Даты создания и публикации

## API Endpoints

| Метод | URL | Описание |
|-------|-----|----------|
| POST | /api/v1/payments | Создание платежа |
| GET | /api/v1/payments/{payment_id} | Получение информации о платеже |

## Асинхронная обработка

### Очереди
- `payments.new` — новые платежи для обработки
- `payments.new.dlq` — Dead Letter Queue

### Consumer
1. Получает сообщение из payments.new
2. Эмулирует обработку (2-5 сек, 90% успех)
3. Обновляет статус платежа
4. Отправляет webhook
5. Retry при ошибках (3 попытки)
6. Отправка в DLQ после исчерпания попыток

## Паттерны

- **Outbox Pattern** — гарантированная публикация событий
- **Idempotency** — защита от дублей через Idempotency-Key
- **Retry with Exponential Backoff** — повторные попытки webhook
- **Dead Letter Queue** — обработка невосстановимых ошибок

## Связанные документы

- Исходное ТЗ: `/home/roman/projects/hh/Тестовое python -2.pdf`
- План задач: `/home/roman/projects/hh/task.md`
