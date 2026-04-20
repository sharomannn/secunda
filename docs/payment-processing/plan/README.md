---
date: 2026-04-20
feature: payment-processing
design: ../README.md
status: approved
---

# План реализации: Payment Processing Microservice

## Обзор

Реализация микросервиса обработки платежей с использованием FastAPI, SQLAlchemy 2.0, RabbitMQ и PostgreSQL. План разбит на 6 фаз, каждая из которых представляет собой атомарную задачу с чёткими критериями готовности.

## Стратегия фаз

**Выбранная стратегия:** Снизу вверх (Bottom-Up)

**Обоснование:**
- Начинаем с инфраструктуры и моделей данных (фундамент)
- Затем бизнес-логика и сервисы
- API-слой строится поверх готовых сервисов
- Асинхронная обработка интегрируется в конце
- Каждая фаза тестируема независимо

**Порядок:**
```
Инфраструктура → Модели → Сервисы → API → Consumer → Интеграция
```

---

## Карта файлов

### Структура проекта

```
payment-service/
├── app/
│   ├── __init__.py
│   ├── main.py                      # FastAPI приложение
│   ├── config.py                    # Конфигурация (env vars)
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py                  # SQLAlchemy Base
│   │   └── session.py               # Async session factory
│   ├── models/
│   │   ├── __init__.py
│   │   ├── payment.py               # Payment модель
│   │   └── outbox.py                # Outbox модель
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── payment.py               # Pydantic schemas
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── payment_repository.py
│   │   └── outbox_repository.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── payment_service.py
│   │   ├── outbox_service.py
│   │   ├── payment_processor.py
│   │   └── webhook_client.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── dependencies.py          # API dependencies
│   │   └── v1/
│   │       ├── __init__.py
│   │       └── payments.py          # Payment endpoints
│   ├── middleware/
│   │   ├── __init__.py
│   │   └── auth.py                  # API Key middleware
│   ├── consumer/
│   │   ├── __init__.py
│   │   └── payment_handler.py       # RabbitMQ consumer
│   └── tasks/
│       ├── __init__.py
│       └── outbox_publisher.py      # Background outbox publisher
├── alembic/
│   ├── env.py
│   └── versions/
│       └── 001_create_tables.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py                  # Pytest fixtures
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── alembic.ini
└── README.md
```

---

## Фазы реализации

| Фаза | Название | Файл | Зависимости | Статус |
|------|----------|------|-------------|:------:|
| 1 | Инфраструктура и модели | `phase-01.md` | - | [ ] |
| 2 | Репозитории и сервисы | `phase-02.md` | phase-01 | [ ] |
| 3 | API-слой | `phase-03.md` | phase-02 | [ ] |
| 4 | Асинхронная обработка | `phase-04.md` | phase-02 | [ ] |
| 5 | Интеграция и Docker | `phase-05.md` | phase-03, phase-04 | [ ] |
| 6 | Тестирование | `phase-06.md` | phase-01..05 | [ ] |

---

## Зависимости (pyproject.toml)

```toml
[tool.poetry]
name = "payment-service"
version = "0.1.0"
description = "Async payment processing microservice"
python = "^3.11"

[tool.poetry.dependencies]
python = "^3.11"
fastapi = "^0.109.0"
uvicorn = {extras = ["standard"], version = "^0.27.0"}
pydantic = "^2.5.0"
pydantic-settings = "^2.1.0"
sqlalchemy = "^2.0.25"
asyncpg = "^0.29.0"
alembic = "^1.13.0"
faststream = {extras = ["rabbit"], version = "^0.4.0"}
httpx = "^0.26.0"

[tool.poetry.group.dev.dependencies]
pytest = "^7.4.0"
pytest-asyncio = "^0.23.0"
pytest-cov = "^4.1.0"
pytest-mock = "^3.12.0"
faker = "^22.0.0"
testcontainers = "^3.7.0"
ruff = "^0.1.0"
mypy = "^1.8.0"
```

---

## Критерии готовности проекта

### Функциональные требования

- [ ] POST /api/v1/payments создаёт платёж и возвращает 202 Accepted
- [ ] GET /api/v1/payments/{id} возвращает детальную информацию
- [ ] Idempotency-Key защищает от дублей
- [ ] X-API-Key аутентифицирует все запросы
- [ ] События публикуются в payments.new через outbox
- [ ] Consumer обрабатывает платежи (2-5 сек, 90% успех)
- [ ] Webhook отправляется на указанный URL
- [ ] Retry работает (3 попытки, exponential backoff)
- [ ] DLQ получает невосстановимые сообщения

### Технические требования

- [ ] Все миграции применены
- [ ] Все тесты проходят (coverage ≥95%)
- [ ] Docker Compose поднимает весь стек
- [ ] API документация доступна (/docs)
- [ ] Логирование настроено (structured logs)
- [ ] Health check эндпоинт работает

### Качество кода

- [ ] Ruff проверки проходят (linting)
- [ ] MyPy проверки проходят (type checking)
- [ ] Нет TODO/FIXME в коде
- [ ] README содержит инструкции по запуску

---

## Переменные окружения

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/payments

# RabbitMQ
RABBITMQ_URL=amqp://guest:guest@localhost:5672/

# API
API_KEY=your-secret-api-key-here
API_HOST=0.0.0.0
API_PORT=8000

# Outbox Publisher
OUTBOX_PUBLISH_INTERVAL=5
OUTBOX_BATCH_SIZE=100

# Logging
LOG_LEVEL=INFO
```

---

## Команды для разработки

### Запуск инфраструктуры

```bash
# Поднять PostgreSQL и RabbitMQ
docker-compose up -d postgres rabbitmq

# Применить миграции
alembic upgrade head
```

### Запуск приложения

```bash
# API
uvicorn app.main:app --reload

# Consumer
python -m app.consumer.payment_handler

# Outbox Publisher
python -m app.tasks.outbox_publisher
```

### Тестирование

```bash
# Все тесты
pytest

# С покрытием
pytest --cov=app --cov-report=html

# Только unit тесты
pytest tests/unit/

# Линтинг
ruff check app/

# Type checking
mypy app/
```

### Docker

```bash
# Собрать образ
docker build -t payment-service:latest .

# Запустить весь стек
docker-compose up

# Остановить
docker-compose down
```

---

## Порядок выполнения

1. **Phase 1:** Создать инфраструктуру, модели, миграции
2. **Phase 2:** Реализовать репозитории и бизнес-сервисы
3. **Phase 3:** Создать API-эндпоинты с аутентификацией
4. **Phase 4:** Реализовать consumer, webhook, outbox publisher
5. **Phase 5:** Настроить Docker Compose, интеграцию компонентов
6. **Phase 6:** Написать все тесты, достичь 95% покрытия

Каждая фаза должна быть завершена и проверена перед переходом к следующей.

---

## Оценка времени

| Фаза | Сложность | Оценка времени |
|------|-----------|----------------|
| Phase 1 | Средняя | 4-6 часов |
| Phase 2 | Средняя | 4-6 часов |
| Phase 3 | Низкая | 3-4 часа |
| Phase 4 | Высокая | 6-8 часов |
| Phase 5 | Низкая | 2-3 часа |
| Phase 6 | Высокая | 8-10 часов |
| **Итого** | | **27-37 часов** |

**Примечание:** Оценка для опытного разработчика, знакомого со стеком.

---

## Риски и митигация

| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| Проблемы с async SQLAlchemy | Средняя | Использовать проверенные паттерны, тестировать на ранних этапах |
| Сложности с FastStream | Средняя | Изучить документацию, начать с простых примеров |
| Проблемы с testcontainers | Низкая | Использовать docker-compose для локальных тестов |
| Недостаточное покрытие тестами | Средняя | Писать тесты параллельно с кодом, не откладывать на конец |

---

## Следующие шаги

1. Прочитать все файлы фаз (phase-01.md .. phase-06.md)
2. Настроить окружение разработки
3. Начать с Phase 1
4. После каждой фазы проверять критерии готовности
5. Коммитить изменения после завершения фазы
