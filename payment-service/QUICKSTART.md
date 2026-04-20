# 🚀 Быстрый старт Payment Service

## Запуск проекта (самый простой способ)

### 1. Запустить все сервисы

```bash
cd payment-service
./scripts/init.sh
```

Этот скрипт:
- Создаст `.env` файл из `.env.example`
- Запустит PostgreSQL, RabbitMQ, API, Consumer, Outbox Publisher
- Применит миграции базы данных
- Настроит RabbitMQ (exchanges, queues)

**Время запуска:** ~30-60 секунд

### 2. Проверить что всё работает

```bash
# Health check
curl http://localhost:8000/health

# Должен вернуть:
# {"status":"healthy"}
```

### 3. Открыть документацию API

Откройте в браузере: **http://localhost:8000/docs**

Здесь вы увидите все доступные endpoints с интерактивной документацией.

---

## Тестирование API

### Создать платёж

```bash
curl -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: change-me-in-production" \
  -H "Idempotency-Key: $(uuidgen)" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "100.50",
    "currency": "RUB",
    "description": "Тестовый платёж",
    "metadata": {"order_id": "12345"},
    "webhook_url": "https://webhook.site/unique-id"
  }'
```

**Ответ (202 Accepted):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "amount": "100.50",
  "currency": "RUB",
  "status": "pending",
  "created_at": "2026-04-20T09:33:00Z"
}
```

### Получить информацию о платеже

```bash
# Замените {payment_id} на ID из предыдущего ответа
curl http://localhost:8000/api/v1/payments/{payment_id} \
  -H "X-API-Key: change-me-in-production"
```

**Ответ (200 OK):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "amount": "100.50",
  "currency": "RUB",
  "status": "succeeded",
  "description": "Тестовый платёж",
  "metadata": {"order_id": "12345"},
  "webhook_url": "https://webhook.site/unique-id",
  "created_at": "2026-04-20T09:33:00Z",
  "processed_at": "2026-04-20T09:33:05Z"
}
```

---

## Просмотр логов

```bash
# Все сервисы
./scripts/logs.sh all

# Только API
./scripts/logs.sh api

# Только Consumer (обработка платежей)
./scripts/logs.sh consumer

# Только Outbox Publisher (публикация событий)
./scripts/logs.sh outbox
```

---

## Мониторинг RabbitMQ

Откройте в браузере: **http://localhost:15672**

- **Логин:** guest
- **Пароль:** guest

Здесь вы увидите:
- Очереди: `payments.new`, `payments.dlq`
- Exchanges: `payments`
- Сообщения в реальном времени

---

## E2E тест (полный сценарий)

```bash
./scripts/test-e2e.sh
```

Этот скрипт:
1. Создаст платёж через API
2. Дождётся обработки Consumer'ом
3. Проверит что статус изменился на `succeeded`
4. Проверит что webhook был отправлен

---

## Остановка проекта

```bash
# Остановить все сервисы (данные сохранятся)
docker-compose down

# Остановить и удалить все данные (БД, RabbitMQ)
./scripts/clean.sh
```

---

## Доступные сервисы

| Сервис | URL | Описание |
|--------|-----|----------|
| API | http://localhost:8000 | REST API |
| API Docs | http://localhost:8000/docs | Swagger UI |
| Health Check | http://localhost:8000/health | Проверка работоспособности |
| RabbitMQ UI | http://localhost:15672 | Управление очередями |
| PostgreSQL | localhost:5432 | База данных |

---

## Структура проекта

```
payment-service/
├── app/
│   ├── api/v1/payments.py      # REST API endpoints
│   ├── models/                 # SQLAlchemy модели (Payment, Outbox)
│   ├── services/               # Бизнес-логика
│   ├── repositories/           # Работа с БД
│   ├── consumer/               # RabbitMQ consumer (обработка платежей)
│   ├── tasks/                  # Outbox publisher (публикация событий)
│   └── middleware/             # API Key аутентификация
├── tests/                      # 35 тестов (67% покрытие)
├── alembic/                    # Миграции БД
├── scripts/                    # Утилиты для запуска
└── docker-compose.yml          # Оркестрация сервисов
```

---

## Архитектура (кратко)

1. **API** принимает POST /api/v1/payments
2. **Payment Service** создаёт Payment + Outbox event в одной транзакции
3. **Outbox Publisher** читает pending события и публикует в RabbitMQ
4. **Consumer** получает событие, обрабатывает платёж (2-5 сек)
5. **Webhook Client** отправляет уведомление на webhook_url

**Гарантии:**
- Idempotency (защита от дублей)
- At-least-once delivery (Outbox Pattern)
- Retry с exponential backoff
- Dead Letter Queue для невосстановимых ошибок

---

## Troubleshooting

### Порты заняты

Если порты 5432, 5672, 8000, 15672 уже используются:

```bash
# Найти процесс
sudo lsof -i :8000

# Или изменить порты в docker-compose.yml
```

### Ошибки миграций

```bash
# Пересоздать БД
docker-compose down -v
./scripts/init.sh
```

### Логи не показываются

```bash
# Проверить статус контейнеров
docker-compose ps

# Посмотреть логи конкретного сервиса
docker-compose logs -f api
```

---

## Следующие шаги

1. ✅ Запустить проект: `./scripts/init.sh`
2. ✅ Проверить health: `curl http://localhost:8000/health`
3. ✅ Открыть docs: http://localhost:8000/docs
4. ✅ Создать тестовый платёж (см. выше)
5. ✅ Посмотреть логи: `./scripts/logs.sh all`
6. ✅ Открыть RabbitMQ UI: http://localhost:15672
7. ✅ Запустить E2E тест: `./scripts/test-e2e.sh`

---

## Полная документация

- **Архитектура:** `docs/payment-processing/01-architecture.md`
- **Поведение:** `docs/payment-processing/02-behavior.md`
- **API контракт:** `docs/payment-processing/08-api-contract.md`
- **План реализации:** `docs/payment-processing/plan/README.md`
