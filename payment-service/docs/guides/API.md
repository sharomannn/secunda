# API Reference

## Базовая информация

**Base URL:** `http://localhost:8000/api/v1`

**Аутентификация:** Все endpoints требуют заголовок `X-API-Key`

**Content-Type:** `application/json`

## Endpoints

### 1. Health Check

Проверка работоспособности сервиса.

```http
GET /health
```

**Headers:** Не требуются

**Response (200 OK):**
```json
{
  "status": "healthy"
}
```

---

### 2. Создание платежа

Создает новый платеж и ставит его в очередь на обработку.

```http
POST /api/v1/payments
```

**Headers:**
- `X-API-Key` (required) — API ключ для аутентификации
- `Idempotency-Key` (required) — Уникальный UUID для защиты от дублей
- `Content-Type: application/json`

**Request Body:**
```json
{
  "amount": "100.50",
  "currency": "RUB",
  "description": "Оплата заказа #12345",
  "metadata": {
    "order_id": "12345",
    "user_id": "67890"
  },
  "webhook_url": "https://example.com/webhook"
}
```

**Request Body Schema:**

| Поле | Тип | Обязательное | Описание |
|------|-----|--------------|----------|
| `amount` | string (decimal) | Да | Сумма платежа (> 0, до 2 знаков после запятой) |
| `currency` | string (enum) | Да | Валюта: `RUB`, `USD`, `EUR` |
| `description` | string | Да | Описание платежа (до 500 символов) |
| `metadata` | object (JSON) | Да | Произвольные метаданные |
| `webhook_url` | string (URL) | Да | URL для webhook-уведомления (до 2048 символов) |

**Response (202 Accepted):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "amount": "100.50",
  "currency": "RUB",
  "status": "pending",
  "description": "Оплата заказа #12345",
  "metadata": {
    "order_id": "12345",
    "user_id": "67890"
  },
  "webhook_url": "https://example.com/webhook",
  "created_at": "2026-04-20T15:00:00Z",
  "processed_at": null
}
```

**Response Schema:**

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | string (UUID) | Уникальный идентификатор платежа |
| `amount` | string (decimal) | Сумма платежа |
| `currency` | string | Валюта платежа |
| `status` | string (enum) | Статус: `pending`, `succeeded`, `failed` |
| `description` | string | Описание платежа |
| `metadata` | object | Метаданные |
| `webhook_url` | string | URL для webhook |
| `created_at` | string (ISO 8601) | Дата и время создания |
| `processed_at` | string (ISO 8601) или null | Дата и время обработки |

**Errors:**

| Код | Описание | Пример |
|-----|----------|--------|
| 401 | Missing API Key | `{"detail": "Missing API Key"}` |
| 422 | Missing Idempotency-Key | `{"detail": "Missing Idempotency-Key header"}` |
| 422 | Validation Error | `{"detail": [{"loc": ["body", "amount"], "msg": "amount must be greater than 0"}]}` |

**Примеры:**

```bash
# Успешный запрос
curl -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: change-me-in-production" \
  -H "Idempotency-Key: 550e8400-e29b-41d4-a716-446655440001" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "100.50",
    "currency": "RUB",
    "description": "Тестовый платёж",
    "metadata": {"order_id": "12345"},
    "webhook_url": "https://webhook.site/unique-id"
  }'

# Идемпотентный запрос (тот же Idempotency-Key)
curl -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: change-me-in-production" \
  -H "Idempotency-Key: 550e8400-e29b-41d4-a716-446655440001" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "999.99",
    "currency": "USD",
    "description": "Другой платёж",
    "metadata": {},
    "webhook_url": "https://other.com/webhook"
  }'
# Вернет тот же платеж с amount=100.50
```

---

### 3. Получение информации о платеже

Возвращает детальную информацию о платеже по ID.

```http
GET /api/v1/payments/{payment_id}
```

**Path Parameters:**
- `payment_id` (required) — UUID платежа

**Headers:**
- `X-API-Key` (required) — API ключ для аутентификации

**Response (200 OK):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "amount": "100.50",
  "currency": "RUB",
  "status": "succeeded",
  "description": "Оплата заказа #12345",
  "metadata": {
    "order_id": "12345",
    "user_id": "67890"
  },
  "webhook_url": "https://example.com/webhook",
  "created_at": "2026-04-20T15:00:00Z",
  "processed_at": "2026-04-20T15:00:03Z"
}
```

**Errors:**

| Код | Описание | Пример |
|-----|----------|--------|
| 401 | Missing API Key | `{"detail": "Missing API Key"}` |
| 404 | Payment Not Found | `{"detail": "Payment not found"}` |
| 422 | Invalid UUID | `{"detail": [{"loc": ["path", "payment_id"], "msg": "value is not a valid uuid"}]}` |

**Примеры:**

```bash
# Успешный запрос
curl http://localhost:8000/api/v1/payments/550e8400-e29b-41d4-a716-446655440000 \
  -H "X-API-Key: change-me-in-production"

# Несуществующий платеж
curl http://localhost:8000/api/v1/payments/00000000-0000-0000-0000-000000000000 \
  -H "X-API-Key: change-me-in-production"
# Response: 404 Not Found
```

---

## Webhook-уведомления

После обработки платежа сервис отправляет POST запрос на указанный `webhook_url`.

### Формат webhook-запроса

```http
POST {webhook_url}
Content-Type: application/json
```

**Body:**
```json
{
  "payment_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "succeeded",
  "amount": "100.50",
  "currency": "RUB",
  "processed_at": "2026-04-20T15:00:03Z"
}
```

### Retry механизм

Если webhook URL недоступен, сервис повторит попытку:

| Попытка | Задержка | Общее время |
|---------|----------|-------------|
| 1       | 0s       | 0s          |
| 2       | 1s       | 1s          |
| 3       | 2s       | 3s          |

После 3 неудачных попыток сообщение отправляется в Dead Letter Queue.

### Требования к webhook endpoint

- **Timeout:** Должен отвечать в течение 10 секунд
- **Status code:** Должен вернуть 200 OK для успешной обработки
- **Idempotency:** Должен корректно обрабатывать дубликаты (at-least-once delivery)

### Тестирование webhooks

Используйте https://webhook.site/ для тестирования:

1. Откройте https://webhook.site/
2. Скопируйте уникальный URL (например, `https://webhook.site/abc-123`)
3. Используйте этот URL в поле `webhook_url` при создании платежа
4. После обработки платежа на webhook.site появится HTTP запрос

---

## Статусы платежа

| Статус | Описание |
|--------|----------|
| `pending` | Платеж создан и ожидает обработки |
| `succeeded` | Платеж успешно обработан (90% вероятность) |
| `failed` | Платеж отклонен (10% вероятность) |

**Переходы статусов:**
```
pending → succeeded (90%)
pending → failed (10%)
```

Статусы `succeeded` и `failed` являются финальными и не меняются.

---

## Валюты

Поддерживаемые валюты:

| Код | Название |
|-----|----------|
| `RUB` | Российский рубль |
| `USD` | Доллар США |
| `EUR` | Евро |

---

## Идемпотентность

### Как работает

1. Клиент генерирует уникальный `Idempotency-Key` (UUID)
2. Отправляет запрос с этим ключом
3. Сервер проверяет, существует ли платеж с таким ключом
4. Если существует — возвращает существующий платеж
5. Если не существует — создает новый

### Пример

```bash
# Первый запрос — создает платеж
curl -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: change-me-in-production" \
  -H "Idempotency-Key: my-unique-key-123" \
  -H "Content-Type: application/json" \
  -d '{"amount": "100.50", "currency": "RUB", ...}'
# Response: {"id": "aaa-bbb-ccc", "amount": "100.50"}

# Второй запрос с тем же ключом — возвращает существующий
curl -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: change-me-in-production" \
  -H "Idempotency-Key: my-unique-key-123" \
  -H "Content-Type: application/json" \
  -d '{"amount": "999.99", "currency": "USD", ...}'  # Другие данные
# Response: {"id": "aaa-bbb-ccc", "amount": "100.50"}  # Тот же платеж!
```

### Рекомендации

- Используйте UUID v4 для генерации ключей
- Храните ключи на стороне клиента для повторных попыток
- Не используйте один ключ для разных платежей

---

## Rate Limiting

**Текущая реализация:** Не ограничено

**Рекомендации для production:**
- 100 запросов/минуту на API ключ
- 1000 запросов/час на API ключ
- Burst: до 10 запросов/секунду

---

## Коды ошибок

### 401 Unauthorized

**Причина:** Отсутствует или неверный API ключ

**Пример:**
```json
{
  "detail": "Missing API Key"
}
```

**Решение:** Добавьте заголовок `X-API-Key: change-me-in-production`

### 404 Not Found

**Причина:** Платеж с указанным ID не найден

**Пример:**
```json
{
  "detail": "Payment not found"
}
```

**Решение:** Проверьте правильность `payment_id`

### 422 Unprocessable Entity

**Причина:** Ошибка валидации входных данных

**Пример:**
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

**Решение:** Исправьте данные согласно сообщению об ошибке

### 500 Internal Server Error

**Причина:** Внутренняя ошибка сервера

**Пример:**
```json
{
  "detail": "Internal server error"
}
```

**Решение:** Проверьте логи сервера или повторите запрос позже

---

## Примеры использования

### Python (requests)

```python
import requests
import uuid

API_BASE = "http://localhost:8000/api/v1"
API_KEY = "change-me-in-production"

# Создание платежа
response = requests.post(
    f"{API_BASE}/payments",
    headers={
        "X-API-Key": API_KEY,
        "Idempotency-Key": str(uuid.uuid4()),
        "Content-Type": "application/json"
    },
    json={
        "amount": "100.50",
        "currency": "RUB",
        "description": "Тестовый платёж",
        "metadata": {"order_id": "12345"},
        "webhook_url": "https://webhook.site/unique-id"
    }
)

payment = response.json()
print(f"Payment created: {payment['id']}")

# Получение информации о платеже
response = requests.get(
    f"{API_BASE}/payments/{payment['id']}",
    headers={"X-API-Key": API_KEY}
)

payment = response.json()
print(f"Payment status: {payment['status']}")
```

### JavaScript (fetch)

```javascript
const API_BASE = "http://localhost:8000/api/v1";
const API_KEY = "change-me-in-production";

// Создание платежа
const response = await fetch(`${API_BASE}/payments`, {
  method: "POST",
  headers: {
    "X-API-Key": API_KEY,
    "Idempotency-Key": crypto.randomUUID(),
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    amount: "100.50",
    currency: "RUB",
    description: "Тестовый платёж",
    metadata: { order_id: "12345" },
    webhook_url: "https://webhook.site/unique-id"
  })
});

const payment = await response.json();
console.log(`Payment created: ${payment.id}`);

// Получение информации о платеже
const response2 = await fetch(`${API_BASE}/payments/${payment.id}`, {
  headers: { "X-API-Key": API_KEY }
});

const payment2 = await response2.json();
console.log(`Payment status: ${payment2.status}`);
```

### cURL

```bash
# Создание платежа
PAYMENT_ID=$(curl -s -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: change-me-in-production" \
  -H "Idempotency-Key: $(uuidgen)" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "100.50",
    "currency": "RUB",
    "description": "Тестовый платёж",
    "metadata": {"order_id": "12345"},
    "webhook_url": "https://webhook.site/unique-id"
  }' | jq -r '.id')

echo "Payment created: $PAYMENT_ID"

# Ожидание обработки
sleep 5

# Получение информации о платеже
curl -s http://localhost:8000/api/v1/payments/$PAYMENT_ID \
  -H "X-API-Key: change-me-in-production" | jq
```
