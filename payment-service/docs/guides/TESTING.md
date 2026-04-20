# Руководство по тестированию

## Автоматические тесты

### Запуск всех тестов

```bash
cd payment-service
poetry run pytest
```

**Результат:**
```
============================= test session starts ==============================
collected 35 items

tests/unit/test_payment_service.py ........                              [ 22%]
tests/unit/test_payment_processor.py ....                                [ 34%]
tests/integration/test_api.py ..............                             [ 74%]
tests/e2e/test_payment_flow.py .........                                 [100%]

============================== 35 passed in 12.5s ==============================
```

### Запуск с покрытием кода

```bash
poetry run pytest --cov=app --cov-report=html
```

**Результат:**
```
---------- coverage: platform linux, python 3.14.3 -----------
Name                                    Stmts   Miss  Cover
-----------------------------------------------------------
app/__init__.py                             0      0   100%
app/api/v1/payments.py                     45     15    67%
app/config.py                              12      0   100%
app/consumer/payment_handler.py            38     12    68%
app/models/payment.py                      25      0   100%
app/models/outbox.py                       15      0   100%
app/repositories/payment_repository.py     42     14    67%
app/services/payment_service.py            56     18    68%
-----------------------------------------------------------
TOTAL                                     450    150    67%

HTML coverage report: htmlcov/index.html
```

Откройте `htmlcov/index.html` в браузере для детального отчета.

### Запуск по категориям

```bash
# Только unit тесты (быстрые, без БД)
poetry run pytest tests/unit/

# Только integration тесты (с реальной БД)
poetry run pytest tests/integration/

# Только e2e тесты (полный flow)
poetry run pytest tests/e2e/

# Конкретный файл
poetry run pytest tests/unit/test_payment_service.py

# Конкретный тест
poetry run pytest tests/unit/test_payment_service.py::test_create_payment_success
```

### Запуск с verbose выводом

```bash
poetry run pytest -v
```

## Структура тестов

### Unit тесты (`tests/unit/`)

Тестируют отдельные компоненты в изоляции (с моками).

**Пример: `tests/unit/test_payment_service.py`**
```python
@pytest.mark.asyncio
async def test_create_payment_success(mock_payment_repo, mock_outbox_repo):
    """Тест успешного создания платежа"""
    service = PaymentService(mock_payment_repo, mock_outbox_repo)
    
    request = PaymentCreate(
        amount=Decimal("100.50"),
        currency="RUB",
        description="Test payment",
        metadata={},
        webhook_url="https://example.com/webhook"
    )
    
    payment = await service.create_payment(request, "idempotency-key-123")
    
    assert payment.amount == Decimal("100.50")
    assert payment.status == "pending"
    mock_payment_repo.create.assert_called_once()
    mock_outbox_repo.create.assert_called_once()
```

### Integration тесты (`tests/integration/`)

Тестируют взаимодействие компонентов с реальной БД.

**Пример: `tests/integration/test_api.py`**
```python
@pytest.mark.asyncio
async def test_create_payment_returns_202(client, db_session):
    """Тест создания платежа через API"""
    response = await client.post(
        "/api/v1/payments",
        headers={
            "X-API-Key": "change-me-in-production",
            "Idempotency-Key": str(uuid.uuid4())
        },
        json={
            "amount": "100.50",
            "currency": "RUB",
            "description": "Test",
            "metadata": {},
            "webhook_url": "https://example.com/webhook"
        }
    )
    
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "pending"
    assert data["amount"] == "100.50"
```

### E2E тесты (`tests/e2e/`)

Тестируют полный сценарий от создания до обработки.

**Пример: `tests/e2e/test_payment_flow.py`**
```python
@pytest.mark.asyncio
async def test_full_payment_flow(client, db_session):
    """Тест полного flow: создание → обработка → webhook"""
    # 1. Создать платеж
    response = await client.post("/api/v1/payments", ...)
    payment_id = response.json()["id"]
    
    # 2. Проверить что платеж pending
    response = await client.get(f"/api/v1/payments/{payment_id}", ...)
    assert response.json()["status"] == "pending"
    
    # 3. Дождаться обработки (в тестах используем mock)
    await process_payment_mock(payment_id)
    
    # 4. Проверить что статус изменился
    response = await client.get(f"/api/v1/payments/{payment_id}", ...)
    assert response.json()["status"] in ["succeeded", "failed"]
```

## Ручное тестирование

### E2E тест через скрипт

```bash
./scripts/test-e2e.sh
```

**Что проверяет:**
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

### Тестирование через Swagger UI

1. Откройте http://localhost:8000/docs
2. Нажмите **"Authorize"** → введите `change-me-in-production`
3. Выберите `POST /api/v1/payments` → **"Try it out"**
4. Заполните поля и нажмите **"Execute"**
5. Скопируйте `id` из ответа
6. Выберите `GET /api/v1/payments/{payment_id}` → вставьте `id`
7. Через 2-5 секунд статус изменится на `succeeded`

### Тестирование через curl

#### Создание платежа

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

#### Получение платежа

```bash
# Замените {payment_id} на ID из предыдущего ответа
curl http://localhost:8000/api/v1/payments/{payment_id} \
  -H "X-API-Key: change-me-in-production"
```

## Тестирование ошибок

### 1. Без API ключа (401 Unauthorized)

```bash
curl -X POST http://localhost:8000/api/v1/payments \
  -H "Content-Type: application/json" \
  -d '{"amount": "100.50", "currency": "RUB", ...}'
```

**Ожидаемый ответ:**
```json
{"detail": "Missing API Key"}
```

### 2. Без Idempotency-Key (422 Unprocessable Entity)

```bash
curl -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: change-me-in-production" \
  -H "Content-Type: application/json" \
  -d '{"amount": "100.50", "currency": "RUB", ...}'
```

**Ожидаемый ответ:**
```json
{"detail": "Missing Idempotency-Key header"}
```

### 3. Отрицательная сумма (422 Unprocessable Entity)

```bash
curl -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: change-me-in-production" \
  -H "Idempotency-Key: $(uuidgen)" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "-100.50",
    "currency": "RUB",
    "description": "Test",
    "metadata": {},
    "webhook_url": "https://example.com/webhook"
  }'
```

**Ожидаемый ответ:**
```json
{
  "detail": [
    {
      "loc": ["body", "amount"],
      "msg": "amount must be greater than 0",
      "type": "value_error"
    }
  ]
}
```

### 4. Несуществующий платеж (404 Not Found)

```bash
curl http://localhost:8000/api/v1/payments/00000000-0000-0000-0000-000000000000 \
  -H "X-API-Key: change-me-in-production"
```

**Ожидаемый ответ:**
```json
{"detail": "Payment not found"}
```

### 5. Неверная валюта (422 Unprocessable Entity)

```bash
curl -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: change-me-in-production" \
  -H "Idempotency-Key: $(uuidgen)" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "100.50",
    "currency": "BTC",
    "description": "Test",
    "metadata": {},
    "webhook_url": "https://example.com/webhook"
  }'
```

**Ожидаемый ответ:**
```json
{
  "detail": [
    {
      "loc": ["body", "currency"],
      "msg": "value is not a valid enumeration member; permitted: 'RUB', 'USD', 'EUR'",
      "type": "type_error.enum"
    }
  ]
}
```

## Мониторинг и отладка

### Просмотр логов

```bash
# Все сервисы
./scripts/logs.sh all

# Отдельные компоненты
./scripts/logs.sh api          # FastAPI
./scripts/logs.sh consumer     # Обработка платежей
./scripts/logs.sh outbox       # Публикация событий
```

### RabbitMQ Management UI

Откройте: http://localhost:15672 (guest/guest)

**Что проверить:**
- **Queues** → `payments.new` (должна быть пустой после обработки)
- **Queues** → `payments.new.dlq` (сообщения после 3 неудач)
- **Connections** (должно быть 3: API, Consumer, Outbox Publisher)

### Проверка базы данных

```bash
docker-compose exec postgres psql -U user -d payments
```

**Полезные запросы:**

```sql
-- Последние платежи
SELECT id, amount, currency, status, created_at, processed_at 
FROM payments 
ORDER BY created_at DESC 
LIMIT 10;

-- Статистика по статусам
SELECT status, COUNT(*) 
FROM payments 
GROUP BY status;

-- Pending события в Outbox (должно быть 0)
SELECT COUNT(*) FROM outbox WHERE status = 'pending';

-- Средняя скорость обработки
SELECT AVG(EXTRACT(EPOCH FROM (processed_at - created_at))) as avg_seconds
FROM payments 
WHERE processed_at IS NOT NULL;
```

## Нагрузочное тестирование

### С помощью Apache Bench

```bash
# 1000 запросов, 10 одновременных
ab -n 1000 -c 10 \
  -H "X-API-Key: change-me-in-production" \
  -H "Idempotency-Key: test-key-1" \
  -H "Content-Type: application/json" \
  -p payment.json \
  http://localhost:8000/api/v1/payments
```

**payment.json:**
```json
{
  "amount": "100.50",
  "currency": "RUB",
  "description": "Load test",
  "metadata": {},
  "webhook_url": "https://example.com/webhook"
}
```

### С помощью wrk

```bash
wrk -t4 -c100 -d30s \
  -H "X-API-Key: change-me-in-production" \
  -H "Idempotency-Key: test-key-1" \
  http://localhost:8000/health
```

## CI/CD интеграция

### GitHub Actions (пример)

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: user
          POSTGRES_PASSWORD: password
          POSTGRES_DB: payments
        ports:
          - 5432:5432
      
      rabbitmq:
        image: rabbitmq:3-management
        ports:
          - 5672:5672
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install Poetry
        run: pip install poetry
      
      - name: Install dependencies
        run: poetry install
      
      - name: Run tests
        run: poetry run pytest --cov=app --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## Troubleshooting

### Тесты падают с ошибкой БД

```bash
# Пересоздать БД
docker-compose down -v
./scripts/init.sh
poetry run pytest
```

### Тесты зависают

```bash
# Проверить что RabbitMQ запущен
docker-compose ps rabbitmq

# Перезапустить RabbitMQ
docker-compose restart rabbitmq
```

### Низкое покрытие кода

```bash
# Посмотреть какие строки не покрыты
poetry run pytest --cov=app --cov-report=term-missing
```
