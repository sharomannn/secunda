# 🚀 Быстрый старт Payment Service

> **Для проверяющего:** Эта инструкция позволит запустить и протестировать проект за 5 минут.

## Запуск проекта (1 команда)

```bash
cd payment-service
./scripts/init.sh
```

**Что происходит:**
- ✅ Сборка Docker образов
- ✅ Запуск PostgreSQL, RabbitMQ, API, Consumer, Outbox Publisher
- ✅ Применение миграций БД
- ✅ Настройка RabbitMQ (exchanges, queues, DLQ)

**Время запуска:** ~30-60 секунд

## Проверка работоспособности

### 1. Health Check

```bash
curl http://localhost:8000/health
```

**Ожидаемый ответ:**
```json
{"status":"healthy"}
```

### 2. Доступные сервисы

| Сервис | URL | Логин/Пароль |
|--------|-----|--------------|
| **API Docs (Swagger)** | http://localhost:8000/docs | API Key: `change-me-in-production` |
| **RabbitMQ Management** | http://localhost:15672 | guest/guest |
| **API** | http://localhost:8000 | - |

### 3. Открыть Swagger UI

Откройте в браузере: **http://localhost:8000/docs**

Здесь вы увидите все endpoints с интерактивной документацией.

## Тестирование через Swagger UI (рекомендуется)

### Шаг 1: Авторизация

1. Откройте http://localhost:8000/docs
2. Нажмите кнопку **"Authorize"** (замок в правом верхнем углу)
3. Введите API ключ: `change-me-in-production`
4. Нажмите **"Authorize"** → **"Close"**

### Шаг 2: Создание платежа

1. Найдите endpoint `POST /api/v1/payments`
2. Нажмите **"Try it out"**
3. Заполните поля:

**Idempotency-Key:** (сгенерируйте UUID на https://www.uuidgenerator.net/ или используйте любой уникальный ключ)
```
550e8400-e29b-41d4-a716-446655440001
```

**Request body:**
```json
{
  "amount": "100.50",
  "currency": "RUB",
  "description": "Тестовый платёж для проверки",
  "metadata": {
    "order_id": "12345",
    "test": true
  },
  "webhook_url": "https://webhook.site/unique-id"
}
```

> **Совет:** Используйте https://webhook.site/ для тестирования webhooks — он покажет все входящие HTTP запросы в реальном времени.

4. Нажмите **"Execute"**

**Ожидаемый ответ (202 Accepted):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "amount": "100.50",
  "currency": "RUB",
  "status": "pending",
  "description": "Тестовый платёж для проверки",
  "metadata": {
    "order_id": "12345",
    "test": true
  },
  "webhook_url": "https://webhook.site/unique-id",
  "created_at": "2026-04-20T15:00:00Z",
  "processed_at": null
}
```

**Скопируйте `id` из ответа!**

### Шаг 3: Проверка статуса платежа

1. Найдите endpoint `GET /api/v1/payments/{payment_id}`
2. Нажмите **"Try it out"**
3. Вставьте скопированный `id` в поле `payment_id`
4. Нажмите **"Execute"**

**Первый запрос (сразу после создания):**
```json
{
  "status": "pending",
  "processed_at": null
}
```

**Подождите 2-5 секунд и повторите запрос:**
```json
{
  "status": "succeeded",  // или "failed" (10% вероятность)
  "processed_at": "2026-04-20T15:00:03Z"
}
```

### Шаг 4: Проверка идемпотентности

1. Вернитесь к `POST /api/v1/payments`
2. Используйте **тот же самый** `Idempotency-Key`
3. Измените данные в body (например, amount: "999.99")
4. Нажмите **"Execute"**

**Результат:** Вернется тот же самый платеж с оригинальными данными (amount: "100.50"), а не новый.

## Тестирование через curl

### Создание платежа

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
    "webhook_url": "https://webhook.site/your-unique-id"
  }'
```

**Сохраните `id` из ответа.**

### Получение информации о платеже

```bash
# Замените {payment_id} на ID из предыдущего ответа
curl http://localhost:8000/api/v1/payments/{payment_id} \
  -H "X-API-Key: change-me-in-production"
```

## Автоматический E2E тест

Запустите полный сценарий тестирования:

```bash
./scripts/test-e2e.sh
```

**Что проверяет скрипт:**
1. ✅ Создание платежа через API
2. ✅ Асинхронная обработка (ожидание 10 секунд)
3. ✅ Изменение статуса на `succeeded`
4. ✅ Идемпотентность (повторный запрос с тем же ключом)

**Ожидаемый вывод:**
```
🧪 Running E2E test...

1️⃣  Creating payment...
   ✓ Payment created: 550e8400-e29b-41d4-a716-446655440000
   ✓ Status: pending

2️⃣  Waiting for async processing (10 seconds)...

3️⃣  Checking payment status...
   ✓ Final status: succeeded
   ✓ Processed at: 2026-04-20T15:00:03Z

4️⃣  Testing idempotency...
   ✓ Idempotency works: returned same payment

✅ E2E test passed!
```

## Мониторинг и отладка

### Просмотр логов

```bash
# Все сервисы в реальном времени
./scripts/logs.sh all

# Отдельные компоненты
./scripts/logs.sh api          # FastAPI (создание платежей)
./scripts/logs.sh consumer     # Обработка платежей
./scripts/logs.sh outbox       # Публикация событий в RabbitMQ
```

**Что искать в логах:**

**API:**
```
INFO: Payment created: 550e8400-e29b-41d4-a716-446655440000
INFO: Outbox event created: payment.created
```

**Outbox Publisher:**
```
INFO: Publishing 1 pending events
INFO: Event published: payment.created
```

**Consumer:**
```
INFO: Processing payment: 550e8400-e29b-41d4-a716-446655440000
INFO: Payment processing took 3.2s
INFO: Payment status updated: succeeded
INFO: Webhook sent successfully
```

### RabbitMQ Management UI

Откройте: **http://localhost:15672**
- Логин: `guest`
- Пароль: `guest`

**Что проверить:**

1. **Queues** (вкладка Queues):
   - `payments.new` — основная очередь (должна быть пустой после обработки)
   - `payments.new.dlq` — Dead Letter Queue (сообщения после 3 неудач)

2. **Exchanges** (вкладка Exchanges):
   - `payments` — основной exchange (type: topic)
   - `payments.dlx` — Dead Letter Exchange (type: fanout)

3. **Connections** (вкладка Connections):
   - Должно быть 3 подключения: API, Consumer, Outbox Publisher

### Проверка базы данных

```bash
# Подключиться к PostgreSQL
docker-compose exec postgres psql -U user -d payments

# Посмотреть последние платежи
SELECT id, amount, currency, status, created_at, processed_at 
FROM payments 
ORDER BY created_at DESC 
LIMIT 5;

# Посмотреть события Outbox
SELECT id, event_type, status, created_at, published_at 
FROM outbox 
ORDER BY created_at DESC 
LIMIT 5;

# Проверить pending события (должно быть 0)
SELECT COUNT(*) FROM outbox WHERE status = 'pending';

# Выйти
\q
```

## Проверка требований тестового задания

### ✅ Функционал API

- [x] **POST /api/v1/payments** — создание платежа (202 Accepted)
- [x] **GET /api/v1/payments/{id}** — получение информации о платеже
- [x] **Idempotency-Key** — обязательный заголовок для защиты от дублей
- [x] **X-API-Key** — статический API ключ для аутентификации

### ✅ Сущности

- [x] **Payment** — id, amount, currency, description, metadata, status, idempotency_key, webhook_url, created_at, processed_at
- [x] **Статусы:** pending, succeeded, failed
- [x] **Валюты:** RUB, USD, EUR
- [x] **Metadata:** JSON поле для дополнительной информации

### ✅ Брокер сообщений

- [x] **RabbitMQ** — публикация событий в очередь `payments.new`
- [x] **Consumer** — один обработчик, делающий всё:
  - Получает сообщение из очереди
  - Эмулирует обработку (2-5 сек, 90% успех, 10% ошибка)
  - Обновляет статус в БД
  - Отправляет webhook-уведомление
  - Реализует retry при ошибках

### ✅ Гарантии доставки

- [x] **Outbox Pattern** — транзакционная публикация событий
- [x] **Idempotency** — защита от дублей через уникальный ключ
- [x] **Dead Letter Queue** — для сообщений после 3 неудачных попыток
- [x] **Retry** — 3 попытки с экспоненциальной задержкой (1s, 2s, 4s)

### ✅ Технологический стек

- [x] **FastAPI** + **Pydantic v2**
- [x] **SQLAlchemy 2.0** (асинхронный режим)
- [x] **PostgreSQL** — таблицы payments и outbox
- [x] **RabbitMQ** + **FastStream**
- [x] **Alembic** — миграции
- [x] **Docker** + **docker-compose**

### ✅ Документация

- [x] **README.md** — полная документация (1300+ строк)
- [x] **QUICKSTART.md** — быстрый старт для проверяющего
- [x] **Swagger UI** — интерактивная документация API
- [x] **Примеры** — curl команды и сценарии тестирования

### ✅ Тестирование

- [x] **35 тестов** (unit, integration, e2e)
- [x] **67% покрытие кода**
- [x] **E2E скрипт** — автоматическая проверка полного flow

## Остановка проекта

```bash
# Остановить все сервисы (данные сохранятся)
docker-compose down

# Остановить и удалить все данные (БД, RabbitMQ)
./scripts/clean.sh

# Перезапустить
./scripts/init.sh
```

## Troubleshooting

### Порты заняты

Если порты 5432, 5672, 8000, 15672 уже используются:

```bash
# Найти процесс
sudo lsof -i :8000

# Или изменить порты в docker-compose.yml
```

### Сервисы не запускаются

```bash
# Проверить статус
docker-compose ps

# Посмотреть логи
docker-compose logs

# Пересоздать всё
docker-compose down -v
./scripts/init.sh
```

### Consumer не обрабатывает платежи

```bash
# Проверить логи Consumer
./scripts/logs.sh consumer

# Проверить RabbitMQ UI
# http://localhost:15672 → Queues → payments.new

# Перезапустить Consumer
docker-compose restart consumer outbox-publisher
```

## Дополнительная информация

**Полная документация:** См. `README.md` (1300+ строк)

**Архитектура:** Подробные диаграммы и описание компонентов в `README.md` → раздел "Архитектура"

**Технические решения:** Детальное объяснение Outbox Pattern, Idempotency, Retry, DLQ в `README.md` → раздел "Технические решения"

**Разработка:** Инструкции по локальной разработке, миграциям, линтингу в `README.md` → раздел "Разработка"

---

## Контрольный чеклист для проверяющего

- [ ] Запустил проект через `./scripts/init.sh`
- [ ] Проверил health check: `curl http://localhost:8000/health`
- [ ] Открыл Swagger UI: http://localhost:8000/docs
- [ ] Создал платёж через Swagger (статус `pending`)
- [ ] Проверил платёж через GET (статус изменился на `succeeded`)
- [ ] Проверил идемпотентность (повторный запрос с тем же ключом)
- [ ] Запустил E2E тест: `./scripts/test-e2e.sh`
- [ ] Открыл RabbitMQ UI: http://localhost:15672
- [ ] Посмотрел логи: `./scripts/logs.sh all`
- [ ] Проверил БД: `docker-compose exec postgres psql -U user -d payments`

**Время на полную проверку:** ~10 минут

---

**Вопросы?** См. полную документацию в `README.md` или раздел "Troubleshooting".
