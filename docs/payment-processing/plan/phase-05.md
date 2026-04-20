---
name: Интеграция и Docker
layer: infrastructure, deployment
depends_on: phase-03, phase-04
plan: ./README.md
---

# Фаза 5: Интеграция и Docker

## Цель

Объединить все компоненты в единую систему, настроить Docker Compose для локальной разработки и создать production-ready конфигурацию.

## Контекст

После завершения Phase 3 и Phase 4 у нас есть:
- FastAPI приложение с REST API
- RabbitMQ consumer для обработки платежей
- Outbox Publisher для публикации событий
- Все компоненты работают независимо

В этой фазе создаём:
- Docker Compose для всего стека (API, Consumer, Outbox, PostgreSQL, RabbitMQ)
- Dockerfile для приложения
- Скрипты для инициализации и управления
- Production-ready конфигурацию

## Создать файлы

### `Dockerfile`

**Назначение:** Docker образ для приложения

**Содержимое:**
```dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install poetry
RUN pip install poetry==1.7.1

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Install dependencies
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

# Copy application code
COPY . .

# Install application
RUN poetry install --no-interaction --no-ansi

# Expose port
EXPOSE 8000

# Default command (can be overridden in docker-compose)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Детали:**
- Python 3.11 slim для меньшего размера образа
- Poetry для управления зависимостями
- Установка системных зависимостей (gcc для asyncpg)
- Копирование кода и установка приложения
- Порт 8000 для API

### `docker-compose.yml`

**Назначение:** Orchestration всех сервисов

**Содержимое:**
```yaml
version: '3.8'

services:
  postgres:
    image: postgres:16
    container_name: payment-postgres
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: password
      POSTGRES_DB: payments
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U user -d payments"]
      interval: 5s
      timeout: 5s
      retries: 5

  rabbitmq:
    image: rabbitmq:3-management
    container_name: payment-rabbitmq
    environment:
      RABBITMQ_DEFAULT_USER: guest
      RABBITMQ_DEFAULT_PASS: guest
    ports:
      - "5672:5672"
      - "15672:15672"
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  api:
    build: .
    container_name: payment-api
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    environment:
      DATABASE_URL: postgresql+asyncpg://user:password@postgres:5432/payments
      RABBITMQ_URL: amqp://guest:guest@rabbitmq:5672/
      API_KEY: change-me-in-production
      API_HOST: 0.0.0.0
      API_PORT: 8000
      LOG_LEVEL: INFO
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
    volumes:
      - .:/app
    restart: unless-stopped

  consumer:
    build: .
    container_name: payment-consumer
    command: python -m app.consumer.payment_handler
    environment:
      DATABASE_URL: postgresql+asyncpg://user:password@postgres:5432/payments
      RABBITMQ_URL: amqp://guest:guest@rabbitmq:5672/
      LOG_LEVEL: INFO
    depends_on:
      postgres:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
    volumes:
      - .:/app
    restart: unless-stopped

  outbox-publisher:
    build: .
    container_name: payment-outbox-publisher
    command: python -m app.tasks.outbox_publisher
    environment:
      DATABASE_URL: postgresql+asyncpg://user:password@postgres:5432/payments
      RABBITMQ_URL: amqp://guest:guest@rabbitmq:5672/
      OUTBOX_PUBLISH_INTERVAL: 5
      OUTBOX_BATCH_SIZE: 100
      LOG_LEVEL: INFO
    depends_on:
      postgres:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
    volumes:
      - .:/app
    restart: unless-stopped

volumes:
  postgres_data:
  rabbitmq_data:
```

**Детали:**
- 5 сервисов: postgres, rabbitmq, api, consumer, outbox-publisher
- Health checks для зависимостей
- Volumes для персистентности данных
- Restart policies для production
- Shared volumes для hot reload в development

### `scripts/init.sh`

**Назначение:** Инициализация проекта

**Содержимое:**
```bash
#!/bin/bash
set -e

echo "🚀 Initializing Payment Processing Service..."
echo ""

# Check if docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

echo "1️⃣  Building Docker images..."
docker-compose build

echo ""
echo "2️⃣  Starting infrastructure (PostgreSQL, RabbitMQ)..."
docker-compose up -d postgres rabbitmq

echo ""
echo "3️⃣  Waiting for services to be healthy..."
sleep 10

# Wait for PostgreSQL
echo "   Waiting for PostgreSQL..."
until docker-compose exec -T postgres pg_isready -U user -d payments > /dev/null 2>&1; do
    sleep 1
done
echo "   ✓ PostgreSQL is ready"

# Wait for RabbitMQ
echo "   Waiting for RabbitMQ..."
until docker-compose exec -T rabbitmq rabbitmq-diagnostics ping > /dev/null 2>&1; do
    sleep 1
done
echo "   ✓ RabbitMQ is ready"

echo ""
echo "4️⃣  Running database migrations..."
docker-compose run --rm api alembic upgrade head

echo ""
echo "5️⃣  Setting up RabbitMQ queues..."
docker-compose exec -T rabbitmq bash << 'EOF'
rabbitmqadmin declare exchange name=payments type=topic durable=true
rabbitmqadmin declare queue name=payments.new durable=true arguments='{"x-dead-letter-exchange":"payments.dlx","x-dead-letter-routing-key":"dlq"}'
rabbitmqadmin declare exchange name=payments.dlx type=fanout durable=true
rabbitmqadmin declare queue name=payments.new.dlq durable=true arguments='{"x-message-ttl":604800000}'
rabbitmqadmin declare binding source=payments destination=payments.new routing_key=payment.created
rabbitmqadmin declare binding source=payments.dlx destination=payments.new.dlq routing_key=dlq
EOF

echo ""
echo "6️⃣  Starting all services..."
docker-compose up -d

echo ""
echo "✅ Initialization complete!"
echo ""
echo "📊 Services:"
echo "   API:              http://localhost:8000"
echo "   API Docs:         http://localhost:8000/docs"
echo "   Health Check:     http://localhost:8000/health"
echo "   RabbitMQ UI:      http://localhost:15672 (guest/guest)"
echo ""
echo "📝 Logs:"
echo "   All services:     docker-compose logs -f"
echo "   API only:         docker-compose logs -f api"
echo "   Consumer only:    docker-compose logs -f consumer"
echo "   Outbox only:      docker-compose logs -f outbox-publisher"
echo ""
echo "🛑 Stop services:    docker-compose down"
echo "🗑️  Clean all data:   docker-compose down -v"
```

**Детали:**
- Проверка Docker
- Build образов
- Запуск инфраструктуры
- Health checks
- Миграции БД
- Настройка RabbitMQ
- Запуск всех сервисов
- Инструкции по использованию

### `scripts/test-e2e.sh`

**Назначение:** End-to-end тест всего стека

**Содержимое:**
```bash
#!/bin/bash
set -e

echo "🧪 Running E2E test..."
echo ""

API_BASE="http://localhost:8000/api/v1"
API_KEY="change-me-in-production"

# Generate unique idempotency key
IDEMPOTENCY_KEY=$(uuidgen)

echo "1️⃣  Creating payment..."
RESPONSE=$(curl -s -X POST "$API_BASE/payments" \
  -H "X-API-Key: $API_KEY" \
  -H "Idempotency-Key: $IDEMPOTENCY_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "100.50",
    "currency": "RUB",
    "description": "E2E test payment",
    "metadata": {"test": "e2e"},
    "webhook_url": "https://webhook.site/test"
  }')

PAYMENT_ID=$(echo $RESPONSE | jq -r '.id')
STATUS=$(echo $RESPONSE | jq -r '.status')

if [ "$PAYMENT_ID" == "null" ]; then
    echo "❌ Failed to create payment"
    echo "Response: $RESPONSE"
    exit 1
fi

echo "   ✓ Payment created: $PAYMENT_ID"
echo "   ✓ Status: $STATUS"

echo ""
echo "2️⃣  Waiting for async processing (10 seconds)..."
sleep 10

echo ""
echo "3️⃣  Checking payment status..."
RESPONSE=$(curl -s "$API_BASE/payments/$PAYMENT_ID" \
  -H "X-API-Key: $API_KEY")

FINAL_STATUS=$(echo $RESPONSE | jq -r '.status')
PROCESSED_AT=$(echo $RESPONSE | jq -r '.processed_at')

echo "   ✓ Final status: $FINAL_STATUS"
echo "   ✓ Processed at: $PROCESSED_AT"

if [ "$FINAL_STATUS" == "pending" ]; then
    echo "❌ Payment still pending (processing failed or too slow)"
    exit 1
fi

if [ "$PROCESSED_AT" == "null" ]; then
    echo "❌ processed_at is null"
    exit 1
fi

echo ""
echo "4️⃣  Testing idempotency..."
RESPONSE=$(curl -s -X POST "$API_BASE/payments" \
  -H "X-API-Key: $API_KEY" \
  -H "Idempotency-Key: $IDEMPOTENCY_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "999.99",
    "currency": "USD",
    "description": "Different payment",
    "metadata": {},
    "webhook_url": "https://other.com/webhook"
  }')

SAME_PAYMENT_ID=$(echo $RESPONSE | jq -r '.id')

if [ "$SAME_PAYMENT_ID" != "$PAYMENT_ID" ]; then
    echo "❌ Idempotency failed: got different payment ID"
    exit 1
fi

echo "   ✓ Idempotency works: returned same payment"

echo ""
echo "✅ E2E test passed!"
```

**Детали:**
- Создание платежа через API
- Ожидание обработки
- Проверка финального статуса
- Тест idempotency
- Использование jq для парсинга JSON

### `scripts/logs.sh`

**Назначение:** Удобный просмотр логов

**Содержимое:**
```bash
#!/bin/bash

SERVICE=${1:-all}

case $SERVICE in
  api)
    docker-compose logs -f api
    ;;
  consumer)
    docker-compose logs -f consumer
    ;;
  outbox)
    docker-compose logs -f outbox-publisher
    ;;
  postgres)
    docker-compose logs -f postgres
    ;;
  rabbitmq)
    docker-compose logs -f rabbitmq
    ;;
  all)
    docker-compose logs -f
    ;;
  *)
    echo "Usage: $0 [api|consumer|outbox|postgres|rabbitmq|all]"
    exit 1
    ;;
esac
```

### `scripts/clean.sh`

**Назначение:** Очистка всех данных

**Содержимое:**
```bash
#!/bin/bash
set -e

echo "🗑️  Cleaning up Payment Processing Service..."
echo ""

read -p "This will remove all containers, volumes and data. Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

echo "Stopping services..."
docker-compose down -v

echo "Removing images..."
docker-compose rm -f

echo ""
echo "✅ Cleanup complete!"
echo ""
echo "To start fresh, run: ./scripts/init.sh"
```

### `README.md` (корневой)

**Назначение:** Документация проекта

**Содержимое:**
```markdown
# Payment Processing Service

Асинхронный микросервис для обработки платежей с гарантией доставки событий.

## Возможности

- ✅ REST API для создания и получения платежей
- ✅ Асинхронная обработка через RabbitMQ
- ✅ Outbox Pattern для гарантированной доставки событий
- ✅ Idempotency для защиты от дублей
- ✅ Webhook-уведомления с retry
- ✅ Dead Letter Queue для невосстановимых ошибок
- ✅ Docker Compose для локальной разработки

## Технологический стек

- **FastAPI** — REST API
- **SQLAlchemy 2.0** — ORM (async)
- **PostgreSQL** — База данных
- **RabbitMQ** — Message broker
- **FastStream** — RabbitMQ integration
- **Alembic** — Database migrations
- **Docker** — Containerization

## Быстрый старт

### Требования

- Docker и Docker Compose
- (Опционально) Python 3.11+ для локальной разработки

### Запуск

```bash
# Инициализация и запуск всех сервисов
chmod +x scripts/*.sh
./scripts/init.sh
```

Сервисы будут доступны:
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- RabbitMQ UI: http://localhost:15672 (guest/guest)

### Тестирование

```bash
# E2E тест
./scripts/test-e2e.sh

# Просмотр логов
./scripts/logs.sh all          # Все сервисы
./scripts/logs.sh api          # Только API
./scripts/logs.sh consumer     # Только Consumer
```

### Остановка

```bash
# Остановить сервисы
docker-compose down

# Остановить и удалить все данные
./scripts/clean.sh
```

## Использование API

### Создание платежа

```bash
curl -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: change-me-in-production" \
  -H "Idempotency-Key: $(uuidgen)" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "100.50",
    "currency": "RUB",
    "description": "Payment for order #12345",
    "metadata": {"order_id": "12345"},
    "webhook_url": "https://example.com/webhook"
  }'
```

### Получение платежа

```bash
curl http://localhost:8000/api/v1/payments/{payment_id} \
  -H "X-API-Key: change-me-in-production"
```

## Разработка

### Локальная разработка без Docker

```bash
# Установить зависимости
poetry install

# Запустить PostgreSQL и RabbitMQ
docker-compose up -d postgres rabbitmq

# Применить миграции
alembic upgrade head

# Запустить API
python -m app.main

# В отдельных терминалах:
python -m app.consumer.payment_handler
python -m app.tasks.outbox_publisher
```

### Тесты

```bash
# Unit тесты
pytest tests/unit/

# Integration тесты
pytest tests/integration/

# Все тесты с покрытием
pytest --cov=app --cov-report=html
```

### Линтинг

```bash
# Ruff
ruff check app/

# MyPy
mypy app/
```

## Архитектура

Подробная документация в `docs/payment-processing/`:
- `01-architecture.md` — C4 диаграммы
- `02-behavior.md` — Sequence диаграммы
- `03-decisions.md` — Архитектурные решения (ADR)
- `04-testing.md` — План тестирования
- `05-async-tasks.md` — Асинхронная обработка
- `06-models.md` — Модели данных
- `08-api-contract.md` — API контракты

## Переменные окружения

См. `.env.example` для полного списка.

Основные:
- `DATABASE_URL` — PostgreSQL connection string
- `RABBITMQ_URL` — RabbitMQ connection string
- `API_KEY` — Статический API ключ для аутентификации

## Лицензия

MIT
```

### `.dockerignore`

**Назначение:** Исключения для Docker build

**Содержимое:**
```
__pycache__
*.pyc
*.pyo
*.pyd
.Python
*.so
*.egg
*.egg-info
dist
build
.git
.gitignore
.env
.venv
venv/
docs/
tests/
*.md
.pytest_cache
.mypy_cache
.ruff_cache
htmlcov/
.coverage
```

### `.gitignore`

**Назначение:** Исключения для Git

**Содержимое:**
```
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual environments
venv/
ENV/
env/
.venv

# IDEs
.vscode/
.idea/
*.swp
*.swo
*~

# Testing
.pytest_cache/
.coverage
htmlcov/
.mypy_cache/
.ruff_cache/

# Environment
.env
.env.local

# Database
*.db
*.sqlite

# Logs
*.log
```

## Определение готовности

- [ ] Все файлы созданы согласно списку выше
- [ ] Dockerfile собирается без ошибок
- [ ] docker-compose.yml запускает все 5 сервисов
- [ ] init.sh инициализирует проект
- [ ] Миграции применяются автоматически
- [ ] RabbitMQ queues создаются автоматически
- [ ] test-e2e.sh проходит успешно
- [ ] API доступен на http://localhost:8000
- [ ] API Docs доступны на http://localhost:8000/docs
- [ ] RabbitMQ UI доступен на http://localhost:15672
- [ ] Логи доступны через logs.sh
- [ ] clean.sh удаляет все данные
- [ ] README.md содержит инструкции

## Проверка результата

### 1. Полная инициализация

```bash
# Сделать скрипты исполняемыми
chmod +x scripts/*.sh

# Запустить инициализацию
./scripts/init.sh
```

Ожидаемый вывод:
```
🚀 Initializing Payment Processing Service...

1️⃣  Building Docker images...
...
2️⃣  Starting infrastructure (PostgreSQL, RabbitMQ)...
...
3️⃣  Waiting for services to be healthy...
   ✓ PostgreSQL is ready
   ✓ RabbitMQ is ready
4️⃣  Running database migrations...
...
5️⃣  Setting up RabbitMQ queues...
...
6️⃣  Starting all services...
...
✅ Initialization complete!

📊 Services:
   API:              http://localhost:8000
   API Docs:         http://localhost:8000/docs
   ...
```

### 2. Проверить сервисы

```bash
# Проверить статус
docker-compose ps

# Должны быть запущены:
# payment-postgres
# payment-rabbitmq
# payment-api
# payment-consumer
# payment-outbox-publisher
```

### 3. Запустить E2E тест

```bash
./scripts/test-e2e.sh
```

Ожидаемый вывод:
```
🧪 Running E2E test...

1️⃣  Creating payment...
   ✓ Payment created: 550e8400-...
   ✓ Status: pending

2️⃣  Waiting for async processing (10 seconds)...

3️⃣  Checking payment status...
   ✓ Final status: succeeded
   ✓ Processed at: 2026-04-20T07:21:15.123456Z

4️⃣  Testing idempotency...
   ✓ Idempotency works: returned same payment

✅ E2E test passed!
```

### 4. Проверить логи

```bash
# Все логи
./scripts/logs.sh all

# Только consumer
./scripts/logs.sh consumer
```

### 5. Проверить UI

- API Docs: http://localhost:8000/docs
- RabbitMQ: http://localhost:15672 (guest/guest)
- Health: http://localhost:8000/health

### 6. Очистка

```bash
./scripts/clean.sh
```
