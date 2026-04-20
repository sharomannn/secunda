---
date: 2026-04-20
feature: payment-processing
---

# Тестирование: Payment Processing Microservice

## Стратегия тестирования

### Уровни тестирования

| Уровень | Инструмент | Покрытие | Цель |
|---------|------------|----------|------|
| Unit | pytest | Модели, сервисы, репозитории | Изолированная логика |
| Integration | pytest + testcontainers | API + БД + RabbitMQ | Взаимодействие компонентов |
| E2E | pytest | Полный flow: API → Consumer → Webhook | Сквозные сценарии |

### Инструменты

- **pytest** — фреймворк тестирования
- **pytest-asyncio** — поддержка async тестов
- **httpx** — HTTP-клиент для тестирования FastAPI
- **testcontainers** — PostgreSQL и RabbitMQ в Docker для интеграционных тестов
- **faker** — генерация тестовых данных
- **pytest-mock** — моки для внешних зависимостей

---

## Фикстуры

### Базовые фикстуры

```python
# conftest.py

@pytest.fixture
async def db_session():
    """Async database session для тестов"""
    
@pytest.fixture
async def client():
    """FastAPI TestClient"""
    
@pytest.fixture
def api_key():
    """Валидный API ключ"""
    return "test-api-key-12345"
    
@pytest.fixture
def idempotency_key():
    """Уникальный idempotency key"""
    return str(uuid.uuid4())
```

### Фикстуры для моделей

```python
@pytest.fixture
async def payment_factory(db_session):
    """Фабрика для создания Payment"""
    
@pytest.fixture
async def outbox_factory(db_session):
    """Фабрика для создания Outbox событий"""
```

### Фикстуры для внешних систем

```python
@pytest.fixture
def mock_rabbitmq():
    """Mock RabbitMQ publisher"""
    
@pytest.fixture
def mock_webhook_server():
    """Mock HTTP сервер для webhook"""
```

---

## Unit тесты

### Models (app/models/payment.py)

| Тест | Что проверяет |
|------|---------------|
| `test_payment_creation_with_valid_data` | Создание Payment с валидными данными |
| `test_payment_status_enum_values` | Допустимые значения PaymentStatus |
| `test_payment_currency_enum_values` | Допустимые значения Currency (RUB, USD, EUR) |
| `test_payment_amount_must_be_positive` | Сумма должна быть > 0 |
| `test_payment_idempotency_key_unique_constraint` | Уникальность idempotency_key |
| `test_payment_default_status_is_pending` | Статус по умолчанию = pending |
| `test_payment_created_at_auto_set` | created_at устанавливается автоматически |
| `test_payment_processed_at_nullable` | processed_at может быть NULL |

### Models (app/models/outbox.py)

| Тест | Что проверяет |
|------|---------------|
| `test_outbox_creation_with_valid_data` | Создание Outbox с валидными данными |
| `test_outbox_default_status_is_pending` | Статус по умолчанию = pending |
| `test_outbox_payload_is_json` | payload хранится как JSON |
| `test_outbox_published_at_nullable` | published_at может быть NULL |

### Services (app/services/payment_service.py)

| Тест | Что проверяет |
|------|---------------|
| `test_create_payment_success` | Успешное создание платежа |
| `test_create_payment_with_existing_idempotency_key_returns_existing` | Возврат существующего платежа при дубликате ключа |
| `test_create_payment_creates_outbox_event` | Создание Outbox события в той же транзакции |
| `test_get_payment_by_id_success` | Получение платежа по ID |
| `test_get_payment_by_id_not_found_raises_exception` | Исключение при отсутствии платежа |
| `test_create_payment_validates_amount_positive` | Валидация положительной суммы |
| `test_create_payment_validates_currency` | Валидация допустимой валюты |

### Services (app/services/outbox_service.py)

| Тест | Что проверяет |
|------|---------------|
| `test_create_event_success` | Создание события в outbox |
| `test_publish_pending_events_publishes_to_rabbitmq` | Публикация pending событий в RabbitMQ |
| `test_publish_pending_events_updates_status_to_published` | Обновление статуса после публикации |
| `test_publish_pending_events_handles_rabbitmq_error` | Обработка ошибки RabbitMQ (событие остаётся pending) |
| `test_publish_pending_events_batch_limit` | Ограничение batch размера (100 событий) |

### Services (app/services/payment_processor.py)

| Тест | Что проверяет |
|------|---------------|
| `test_process_payment_success_updates_status_to_succeeded` | Успешная обработка → статус succeeded |
| `test_process_payment_failure_updates_status_to_failed` | Неудачная обработка → статус failed |
| `test_process_payment_emulation_takes_2_to_5_seconds` | Время обработки в диапазоне 2-5 сек |
| `test_process_payment_success_rate_approximately_90_percent` | ~90% успешных обработок (статистический тест) |
| `test_process_payment_sets_processed_at_timestamp` | Установка processed_at после обработки |
| `test_process_payment_idempotent_skips_already_processed` | Пропуск уже обработанных платежей |

### Services (app/services/webhook_client.py)

| Тест | Что проверяет |
|------|---------------|
| `test_send_webhook_success` | Успешная отправка webhook |
| `test_send_webhook_retry_on_failure` | Retry при ошибке (3 попытки) |
| `test_send_webhook_exponential_backoff` | Задержки 1s, 2s, 4s между попытками |
| `test_send_webhook_raises_after_3_failures` | Исключение после исчерпания попыток |
| `test_send_webhook_payload_format` | Формат payload: {payment_id, status, processed_at} |
| `test_send_webhook_timeout_configuration` | Таймаут HTTP-запроса (5 секунд) |

### Middleware (app/middleware/auth.py)

| Тест | Что проверяет |
|------|---------------|
| `test_api_key_middleware_valid_key_passes` | Валидный ключ пропускается |
| `test_api_key_middleware_invalid_key_returns_401` | Невалидный ключ → 401 |
| `test_api_key_middleware_missing_key_returns_401` | Отсутствие ключа → 401 |
| `test_api_key_middleware_case_sensitive` | Ключ чувствителен к регистру |

---

## Integration тесты

### API Endpoints (tests/integration/test_api.py)

| Тест | Что проверяет |
|------|---------------|
| `test_create_payment_returns_202_accepted` | POST /api/v1/payments → 202 Accepted |
| `test_create_payment_saves_to_database` | Платёж сохраняется в БД |
| `test_create_payment_creates_outbox_event` | Outbox событие создаётся |
| `test_create_payment_idempotency_returns_existing` | Повторный запрос возвращает существующий платёж |
| `test_create_payment_without_api_key_returns_401` | Без X-API-Key → 401 |
| `test_create_payment_without_idempotency_key_returns_422` | Без Idempotency-Key → 422 |
| `test_create_payment_with_negative_amount_returns_422` | Отрицательная сумма → 422 |
| `test_create_payment_with_invalid_currency_returns_422` | Невалидная валюта → 422 |
| `test_get_payment_returns_200_with_payment_data` | GET /api/v1/payments/{id} → 200 OK |
| `test_get_payment_not_found_returns_404` | Несуществующий ID → 404 |
| `test_get_payment_without_api_key_returns_401` | Без X-API-Key → 401 |

### Consumer (tests/integration/test_consumer.py)

| Тест | Что проверяет |
|------|---------------|
| `test_consumer_processes_message_from_queue` | Consumer получает сообщение из payments.new |
| `test_consumer_updates_payment_status_to_succeeded` | Статус обновляется на succeeded |
| `test_consumer_updates_payment_status_to_failed` | Статус обновляется на failed (10% случаев) |
| `test_consumer_sends_webhook_after_processing` | Webhook отправляется после обработки |
| `test_consumer_acks_message_after_success` | ACK после успешной обработки |
| `test_consumer_nacks_message_on_failure` | NACK при ошибке |
| `test_consumer_skips_already_processed_payment` | Пропуск уже обработанных платежей |

### Outbox Publisher (tests/integration/test_outbox_publisher.py)

| Тест | Что проверяет |
|------|---------------|
| `test_outbox_publisher_publishes_pending_events` | Публикация pending событий |
| `test_outbox_publisher_updates_status_to_published` | Обновление статуса после публикации |
| `test_outbox_publisher_handles_rabbitmq_unavailable` | Обработка недоступности RabbitMQ |
| `test_outbox_publisher_batch_processing` | Обработка батчами по 100 событий |

### Webhook Retry (tests/integration/test_webhook_retry.py)

| Тест | Что проверяет |
|------|---------------|
| `test_webhook_retry_succeeds_on_second_attempt` | Успех на 2-й попытке |
| `test_webhook_retry_succeeds_on_third_attempt` | Успех на 3-й попытке |
| `test_webhook_retry_fails_after_3_attempts` | Ошибка после 3 попыток |
| `test_webhook_retry_exponential_backoff_timing` | Проверка задержек 1s, 2s, 4s |

### Dead Letter Queue (tests/integration/test_dlq.py)

| Тест | Что проверяет |
|------|---------------|
| `test_message_sent_to_dlq_after_3_failures` | Сообщение в DLQ после 3 неудач |
| `test_dlq_message_contains_original_payload` | DLQ содержит оригинальный payload |
| `test_dlq_message_contains_error_metadata` | DLQ содержит метаданные ошибки |

---

## E2E тесты

### Full Payment Flow (tests/e2e/test_payment_flow.py)

| Тест | Что проверяет |
|------|---------------|
| `test_full_payment_flow_success` | Полный flow: создание → обработка → webhook → succeeded |
| `test_full_payment_flow_failure` | Полный flow с failed статусом |
| `test_full_payment_flow_idempotency` | Повторный запрос не создаёт дубликат |
| `test_full_payment_flow_webhook_retry` | Webhook retry при временной недоступности |
| `test_full_payment_flow_dlq_on_permanent_failure` | Отправка в DLQ при постоянной ошибке |

### Concurrent Requests (tests/e2e/test_concurrency.py)

| Тест | Что проверяет |
|------|---------------|
| `test_concurrent_payment_creation_with_different_keys` | Параллельное создание разных платежей |
| `test_concurrent_payment_creation_with_same_key` | Параллельные запросы с одним idempotency_key |
| `test_concurrent_consumer_processing` | Несколько consumer обрабатывают разные платежи |

---

## Итоговое покрытие

| Модуль | Unit | Integration | E2E | Целевое покрытие |
|--------|------|-------------|-----|------------------|
| Models | ✅ | ✅ | ✅ | 100% |
| Services | ✅ | ✅ | ✅ | 95% |
| API Endpoints | ✅ | ✅ | ✅ | 100% |
| Consumer | ✅ | ✅ | ✅ | 95% |
| Middleware | ✅ | ✅ | - | 100% |
| Outbox Publisher | ✅ | ✅ | ✅ | 95% |
| Webhook Client | ✅ | ✅ | ✅ | 95% |

**Общее целевое покрытие:** 95%+

---

## Запуск тестов

### Все тесты
```bash
pytest
```

### По уровням
```bash
pytest tests/unit/          # Unit тесты
pytest tests/integration/   # Integration тесты
pytest tests/e2e/           # E2E тесты
```

### С покрытием
```bash
pytest --cov=app --cov-report=html
```

### Параллельный запуск
```bash
pytest -n auto  # pytest-xdist
```

---

## Тестовые данные

### Валидный запрос создания платежа
```json
{
  "amount": "100.50",
  "currency": "RUB",
  "description": "Test payment",
  "metadata": {"order_id": "12345"},
  "webhook_url": "https://example.com/webhook"
}
```

### Невалидные запросы (для негативных тестов)
```json
// Отрицательная сумма
{"amount": "-10.00", "currency": "RUB", ...}

// Невалидная валюта
{"amount": "100.00", "currency": "BTC", ...}

// Отсутствует обязательное поле
{"amount": "100.00"}
```

---

## CI/CD Integration

### GitHub Actions / GitLab CI
```yaml
test:
  script:
    - docker-compose up -d postgres rabbitmq
    - pytest --cov=app --cov-report=xml
    - coverage report --fail-under=95
```

### Pre-commit hooks
```yaml
- repo: local
  hooks:
    - id: pytest
      name: Run tests
      entry: pytest tests/unit/
      language: system
      pass_filenames: false
```

---

## Метрики качества

- **Покрытие кода:** ≥95%
- **Время выполнения unit тестов:** <10 секунд
- **Время выполнения integration тестов:** <60 секунд
- **Время выполнения E2E тестов:** <120 секунд
- **Flaky tests:** 0 (все тесты детерминированы)
