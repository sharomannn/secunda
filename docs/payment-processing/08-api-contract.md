---
date: 2026-04-20
feature: payment-processing
---

# API-контракт: Payment Processing Microservice

## Обзор

REST API для управления платежами. Все эндпоинты защищены статическим API ключом.

**Base URL:** `/api/v1`

**Аутентификация:** Все запросы требуют заголовок `X-API-Key`

---

## Общие заголовки

### Запрос

| Заголовок | Обязательный | Описание |
|-----------|:------------:|----------|
| X-API-Key | ✅ | Статический API ключ для аутентификации |
| Content-Type | ✅ | `application/json` для POST запросов |
| Idempotency-Key | ✅ (POST) | Уникальный ключ для идемпотентности (UUID рекомендуется) |

### Ответ

| Заголовок | Описание |
|-----------|----------|
| Content-Type | `application/json` |
| X-Request-ID | Уникальный ID запроса для трейсинга |

---

## Эндпоинты

### 1. Создание платежа

**Метод:** POST  
**URL:** `/api/v1/payments`  
**Permissions:** Требуется X-API-Key  
**Идемпотентность:** Да (через Idempotency-Key)

#### Описание

Создаёт новый платёж и ставит его в очередь на асинхронную обработку. Возвращает 202 Accepted, так как обработка происходит асинхронно.

#### Заголовки запроса

```http
X-API-Key: your-api-key-here
Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
Content-Type: application/json
```

#### Тело запроса

```json
{
  "amount": "100.50",
  "currency": "RUB",
  "description": "Payment for order #12345",
  "metadata": {
    "order_id": "12345",
    "customer_id": "67890",
    "source": "web"
  },
  "webhook_url": "https://example.com/webhooks/payments"
}
```

#### Параметры запроса

| Поле | Тип | Обязательное | Ограничения | Описание |
|------|-----|:------------:|-------------|----------|
| amount | string (decimal) | ✅ | > 0, max 2 decimal places | Сумма платежа |
| currency | string (enum) | ✅ | RUB, USD, EUR | Валюта платежа |
| description | string | ✅ | 1-500 символов | Описание платежа |
| metadata | object | ❌ | Валидный JSON | Дополнительные данные (по умолчанию {}) |
| webhook_url | string (url) | ✅ | Валидный HTTP(S) URL, max 2048 символов | URL для webhook-уведомлений |

#### Ответ 202 Accepted

Платёж успешно создан и поставлен в очередь на обработку.

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "created_at": "2026-04-20T10:00:00.123456Z"
}
```

| Поле | Тип | Описание |
|------|-----|----------|
| id | string (uuid) | Уникальный идентификатор платежа |
| status | string (enum) | Статус платежа (всегда "pending" при создании) |
| created_at | string (datetime) | Дата и время создания (ISO 8601, UTC) |

#### Ответ 200 OK (идемпотентность)

Платёж с таким Idempotency-Key уже существует. Возвращается существующий платёж.

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "created_at": "2026-04-20T10:00:00.123456Z"
}
```

**Примечание:** Статус может быть "pending", "succeeded" или "failed" в зависимости от текущего состояния платежа.

#### Ошибки

##### 401 Unauthorized

Отсутствует или неверный X-API-Key.

```json
{
  "detail": "Invalid API key"
}
```

##### 422 Unprocessable Entity

Невалидные данные запроса.

```json
{
  "detail": [
    {
      "loc": ["body", "amount"],
      "msg": "ensure this value is greater than 0",
      "type": "value_error.number.not_gt"
    },
    {
      "loc": ["body", "currency"],
      "msg": "value is not a valid enumeration member; permitted: 'RUB', 'USD', 'EUR'",
      "type": "type_error.enum"
    }
  ]
}
```

**Возможные ошибки валидации:**

| Поле | Ошибка | Сообщение |
|------|--------|-----------|
| amount | Отрицательное или ноль | "ensure this value is greater than 0" |
| amount | Больше 2 знаков после запятой | "ensure that there are no more than 2 decimal places" |
| currency | Невалидная валюта | "value is not a valid enumeration member" |
| description | Пустая строка | "ensure this value has at least 1 characters" |
| description | Слишком длинная | "ensure this value has at most 500 characters" |
| webhook_url | Невалидный URL | "invalid or missing URL scheme" |
| metadata | Невалидный JSON | "value is not a valid dict" |
| Idempotency-Key | Отсутствует | "Idempotency-Key header is required" |

##### 500 Internal Server Error

Внутренняя ошибка сервера.

```json
{
  "detail": "Internal server error"
}
```

#### Примеры запросов

**cURL:**
```bash
curl -X POST https://api.example.com/api/v1/payments \
  -H "X-API-Key: your-api-key" \
  -H "Idempotency-Key: $(uuidgen)" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "100.50",
    "currency": "RUB",
    "description": "Test payment",
    "metadata": {"order_id": "12345"},
    "webhook_url": "https://example.com/webhook"
  }'
```

**Python (httpx):**
```python
import httpx
import uuid

response = httpx.post(
    "https://api.example.com/api/v1/payments",
    headers={
        "X-API-Key": "your-api-key",
        "Idempotency-Key": str(uuid.uuid4())
    },
    json={
        "amount": "100.50",
        "currency": "RUB",
        "description": "Test payment",
        "metadata": {"order_id": "12345"},
        "webhook_url": "https://example.com/webhook"
    }
)
print(response.status_code, response.json())
```

---

### 2. Получение информации о платеже

**Метод:** GET  
**URL:** `/api/v1/payments/{payment_id}`  
**Permissions:** Требуется X-API-Key

#### Описание

Возвращает детальную информацию о платеже по его ID.

#### Параметры пути

| Параметр | Тип | Описание |
|----------|-----|----------|
| payment_id | string (uuid) | Уникальный идентификатор платежа |

#### Заголовки запроса

```http
X-API-Key: your-api-key-here
```

#### Ответ 200 OK

Платёж найден.

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "amount": "100.50",
  "currency": "RUB",
  "description": "Payment for order #12345",
  "metadata": {
    "order_id": "12345",
    "customer_id": "67890",
    "source": "web"
  },
  "status": "succeeded",
  "idempotency_key": "550e8400-e29b-41d4-a716-446655440001",
  "webhook_url": "https://example.com/webhooks/payments",
  "created_at": "2026-04-20T10:00:00.123456Z",
  "processed_at": "2026-04-20T10:00:03.456789Z"
}
```

#### Параметры ответа

| Поле | Тип | Nullable | Описание |
|------|-----|:--------:|----------|
| id | string (uuid) | ❌ | Уникальный идентификатор платежа |
| amount | string (decimal) | ❌ | Сумма платежа |
| currency | string (enum) | ❌ | Валюта (RUB, USD, EUR) |
| description | string | ❌ | Описание платежа |
| metadata | object | ❌ | Дополнительные данные (JSON) |
| status | string (enum) | ❌ | Статус: pending, succeeded, failed |
| idempotency_key | string | ❌ | Ключ идемпотентности |
| webhook_url | string (url) | ❌ | URL для webhook-уведомлений |
| created_at | string (datetime) | ❌ | Дата создания (ISO 8601, UTC) |
| processed_at | string (datetime) | ✅ | Дата обработки (ISO 8601, UTC), null для pending |

#### Статусы платежа

| Статус | Описание |
|--------|----------|
| pending | Платёж создан, ожидает обработки |
| succeeded | Платёж успешно обработан |
| failed | Обработка платежа завершилась ошибкой |

#### Ошибки

##### 401 Unauthorized

Отсутствует или неверный X-API-Key.

```json
{
  "detail": "Invalid API key"
}
```

##### 404 Not Found

Платёж с указанным ID не найден.

```json
{
  "detail": "Payment not found"
}
```

##### 422 Unprocessable Entity

Невалидный формат payment_id (не UUID).

```json
{
  "detail": [
    {
      "loc": ["path", "payment_id"],
      "msg": "value is not a valid uuid",
      "type": "type_error.uuid"
    }
  ]
}
```

##### 500 Internal Server Error

Внутренняя ошибка сервера.

```json
{
  "detail": "Internal server error"
}
```

#### Примеры запросов

**cURL:**
```bash
curl -X GET https://api.example.com/api/v1/payments/550e8400-e29b-41d4-a716-446655440000 \
  -H "X-API-Key: your-api-key"
```

**Python (httpx):**
```python
import httpx

payment_id = "550e8400-e29b-41d4-a716-446655440000"
response = httpx.get(
    f"https://api.example.com/api/v1/payments/{payment_id}",
    headers={"X-API-Key": "your-api-key"}
)
print(response.status_code, response.json())
```

---

## Webhook-уведомления

### Описание

После обработки платежа сервис отправляет HTTP POST запрос на `webhook_url`, указанный при создании платежа.

### Формат webhook

**Метод:** POST  
**URL:** `webhook_url` из запроса создания платежа  
**Content-Type:** `application/json`

### Тело запроса

```json
{
  "payment_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "succeeded",
  "processed_at": "2026-04-20T10:00:03.456789Z"
}
```

| Поле | Тип | Описание |
|------|-----|----------|
| payment_id | string (uuid) | ID обработанного платежа |
| status | string (enum) | Результат обработки: succeeded или failed |
| processed_at | string (datetime) | Дата и время обработки (ISO 8601, UTC) |

### Ожидаемый ответ

Сервис ожидает HTTP статус **2xx** (200-299) для подтверждения получения webhook.

**Успешный ответ:**
```http
HTTP/1.1 200 OK
Content-Type: application/json

{"received": true}
```

### Retry-логика

Если webhook-эндпоинт возвращает ошибку или недоступен, сервис повторяет отправку:

| Попытка | Задержка | Условие retry |
|---------|----------|---------------|
| 1 | 0s | Немедленно |
| 2 | 1s | 5xx, timeout, connection error |
| 3 | 2s (от попытки 2) | 5xx, timeout, connection error |

**Общее время retry:** ~7 секунд

**Не retry при:**
- 2xx статус (успех)
- 4xx статус (клиентская ошибка, проблема на стороне получателя)

**После исчерпания попыток:**
- Сообщение отправляется в Dead Letter Queue
- Требуется ручной анализ и повторная отправка

### Безопасность webhook

**Рекомендации для получателя:**
1. Проверять подпись запроса (если реализовано)
2. Валидировать payment_id (запросить детали через GET /api/v1/payments/{id})
3. Обрабатывать идемпотентно (один payment_id может прийти несколько раз)
4. Возвращать 2xx быстро (< 5 секунд), обработку делать асинхронно

---

## Коды ошибок

### HTTP статусы

| Статус | Название | Когда возвращается |
|--------|----------|-------------------|
| 200 | OK | GET запрос успешен, или идемпотентный POST вернул существующий ресурс |
| 202 | Accepted | POST запрос принят, обработка асинхронная |
| 401 | Unauthorized | Отсутствует или неверный X-API-Key |
| 404 | Not Found | Ресурс не найден |
| 422 | Unprocessable Entity | Невалидные данные запроса |
| 500 | Internal Server Error | Внутренняя ошибка сервера |

### Формат ошибок

Все ошибки возвращаются в формате:

```json
{
  "detail": "Error message"
}
```

Или для ошибок валидации (422):

```json
{
  "detail": [
    {
      "loc": ["body", "field_name"],
      "msg": "Error message",
      "type": "error_type"
    }
  ]
}
```

---

## Rate Limiting

**Текущая версия:** Не реализовано

**Рекомендации для production:**
- 100 запросов в минуту на API ключ
- Заголовки ответа: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`
- HTTP 429 Too Many Requests при превышении лимита

---

## Версионирование API

**Текущая версия:** v1

**URL:** `/api/v1/...`

**Политика версионирования:**
- Мажорная версия в URL (`/api/v1`, `/api/v2`)
- Обратная совместимость в рамках одной мажорной версии
- Deprecation warnings за 6 месяцев до удаления

---

## OpenAPI спецификация

Полная OpenAPI (Swagger) спецификация доступна по адресу:

**URL:** `/docs` (Swagger UI)  
**URL:** `/redoc` (ReDoc)  
**URL:** `/openapi.json` (JSON спецификация)

---

## Примеры интеграции

### Полный flow создания и отслеживания платежа

```python
import httpx
import uuid
import time

API_BASE = "https://api.example.com/api/v1"
API_KEY = "your-api-key"

# 1. Создать платёж
payment_response = httpx.post(
    f"{API_BASE}/payments",
    headers={
        "X-API-Key": API_KEY,
        "Idempotency-Key": str(uuid.uuid4())
    },
    json={
        "amount": "100.50",
        "currency": "RUB",
        "description": "Test payment",
        "metadata": {"order_id": "12345"},
        "webhook_url": "https://example.com/webhook"
    }
)

payment_id = payment_response.json()["id"]
print(f"Payment created: {payment_id}")

# 2. Опционально: Polling статуса (если webhook недоступен)
while True:
    status_response = httpx.get(
        f"{API_BASE}/payments/{payment_id}",
        headers={"X-API-Key": API_KEY}
    )
    payment = status_response.json()
    
    if payment["status"] != "pending":
        print(f"Payment {payment['status']}: {payment}")
        break
    
    time.sleep(2)  # Проверять каждые 2 секунды
```

### Обработка webhook на стороне клиента

```python
from fastapi import FastAPI, Request

app = FastAPI()

@app.post("/webhook")
async def handle_payment_webhook(request: Request):
    payload = await request.json()
    
    payment_id = payload["payment_id"]
    status = payload["status"]
    processed_at = payload["processed_at"]
    
    # Валидация: запросить детали платежа через API
    # (защита от поддельных webhook)
    
    # Обработка результата (асинхронно)
    if status == "succeeded":
        # Выполнить заказ, отправить товар и т.д.
        pass
    elif status == "failed":
        # Уведомить клиента об ошибке
        pass
    
    return {"received": True}
```
