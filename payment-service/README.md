# Payment Processing Service

Асинхронный микросервис для обработки платежей с гарантией доставки событий и webhook-уведомлениями.

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
cd payment-service
chmod +x scripts/*.sh
./scripts/init.sh
```

Сервисы будут доступны:
- **API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/health
- **RabbitMQ UI:** http://localhost:15672 (guest/guest)

### Тестирование

```bash
# Проверка health check
curl http://localhost:8000/health

# Просмотр логов
./scripts/logs.sh all          # Все сервисы
./scripts/logs.sh api          # Только API
./scripts/logs.sh consumer     # Только Consumer
./scripts/logs.sh outbox       # Только Outbox Publisher
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

**Примечание:** API endpoints будут реализованы в Phase 3. Сейчас доступен только `/health` endpoint.

## Разработка

### Локальная разработка без Docker

```bash
# Установка зависимостей
poetry install

# Запуск PostgreSQL и RabbitMQ через Docker
docker-compose up -d postgres rabbitmq

# Применение миграций
alembic upgrade head

# Запуск API
uvicorn app.main:app --reload

# Запуск Consumer (в отдельном терминале)
python -m app.consumer.payment_handler

# Запуск Outbox Publisher (в отдельном терминале)
python -m app.tasks.outbox_publisher
```

### Линтинг и проверка типов

```bash
# Ruff
poetry run ruff check app/

# MyPy
poetry run mypy app/
```

### Миграции базы данных

```bash
# Создать новую миграцию
alembic revision --autogenerate -m "описание изменений"

# Применить миграции
alembic upgrade head

# Откатить миграцию
alembic downgrade -1
```

## Архитектура

Проект следует 6-фазному плану реализации:

- **Phase 1** ✅ — Инфраструктура и модели (завершена)
- **Phase 2** 🔜 — Репозитории и сервисы
- **Phase 3** 🔜 — API-слой
- **Phase 4** 🔜 — Асинхронная обработка
- **Phase 5** ✅ — Интеграция и Docker (завершена)
- **Phase 6** 🔜 — Тестирование

Подробная документация в `docs/payment-processing/`.

## Структура проекта

```
payment-service/
├── app/
│   ├── main.py              # FastAPI приложение
│   ├── config.py            # Конфигурация
│   ├── db/                  # Database setup
│   ├── models/              # SQLAlchemy модели
│   ├── consumer/            # RabbitMQ consumer (заглушка)
│   └── tasks/               # Background tasks (заглушка)
├── alembic/                 # Database migrations
├── scripts/                 # Utility scripts
├── docker-compose.yml       # Docker orchestration
├── Dockerfile               # Docker image
└── pyproject.toml           # Dependencies
```

## Переменные окружения

Скопируйте `.env.example` в `.env` и настройте:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/payments

# RabbitMQ
RABBITMQ_URL=amqp://guest:guest@localhost:5672/

# API
API_KEY=change-me-in-production
API_HOST=0.0.0.0
API_PORT=8000

# Outbox Publisher
OUTBOX_PUBLISH_INTERVAL=5
OUTBOX_BATCH_SIZE=100

# Logging
LOG_LEVEL=INFO
```

## Troubleshooting

### Порты уже заняты

Если порты 5432, 5672, 8000 или 15672 уже используются, измените их в `docker-compose.yml`.

### Ошибки миграций

```bash
# Пересоздать базу данных
docker-compose down -v
./scripts/init.sh
```

### Логи контейнеров

```bash
# Все логи
docker-compose logs -f

# Конкретный сервис
docker-compose logs -f api
```

## Лицензия

MIT
