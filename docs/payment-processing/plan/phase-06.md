---
name: Тестирование
layer: tests
depends_on: phase-01, phase-02, phase-03, phase-04, phase-05
plan: ./README.md
---

# Фаза 6: Тестирование

## Цель

Написать полный набор тестов (unit, integration, e2e) для достижения покрытия ≥95% и подтверждения корректности всех компонентов.

## Контекст

После завершения Phase 1-5 у нас есть:
- Все компоненты реализованы
- Docker Compose для запуска стека
- Работающий end-to-end flow

В этой фазе создаём:
- Pytest fixtures для тестирования
- Unit тесты для моделей, сервисов, репозиториев
- Integration тесты для API и async компонентов
- E2E тесты для полных сценариев
- Достижение покрытия ≥95%

## Создать файлы

### `tests/conftest.py`

**Назначение:** Общие pytest fixtures

**Содержимое:**
```python
import asyncio
import pytest
import uuid
from decimal import Decimal
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from httpx import AsyncClient
from app.db.base import Base
from app.main import app
from app.models import Payment, PaymentStatus, Currency, Outbox, OutboxStatus
from app.config import settings

# Test database URL
TEST_DATABASE_URL = "postgresql+asyncpg://user:password@localhost:5432/payments_test"

# Create test engine
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create test database session"""
    # Create tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Create session
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()
    
    # Drop tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Create test HTTP client"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
def api_key() -> str:
    """Valid API key"""
    return settings.api_key


@pytest.fixture
def idempotency_key() -> str:
    """Unique idempotency key"""
    return str(uuid.uuid4())


@pytest.fixture
async def payment_factory(db_session: AsyncSession):
    """Factory for creating test payments"""
    async def _create_payment(**kwargs) -> Payment:
        defaults = {
            "id": uuid.uuid4(),
            "amount": Decimal("100.50"),
            "currency": Currency.RUB,
            "description": "Test payment",
            "metadata": {"test": True},
            "status": PaymentStatus.PENDING,
            "idempotency_key": str(uuid.uuid4()),
            "webhook_url": "https://example.com/webhook",
        }
        defaults.update(kwargs)
        
        payment = Payment(**defaults)
        db_session.add(payment)
        await db_session.commit()
        await db_session.refresh(payment)
        return payment
    
    return _create_payment


@pytest.fixture
async def outbox_factory(db_session: AsyncSession):
    """Factory for creating test outbox events"""
    async def _create_outbox(**kwargs) -> Outbox:
        defaults = {
            "aggregate_id": uuid.uuid4(),
            "event_type": "payment.created",
            "payload": {"test": True},
            "status": OutboxStatus.PENDING,
        }
        defaults.update(kwargs)
        
        outbox = Outbox(**defaults)
        db_session.add(outbox)
        await db_session.commit()
        await db_session.refresh(outbox)
        return outbox
    
    return _create_outbox
```

**Детали:**
- Отдельная тестовая БД (payments_test)
- Fixtures для session, client, factories
- Автоматическое создание/удаление таблиц
- Factories для удобного создания тестовых данных

### `tests/unit/test_models.py`

**Назначение:** Unit тесты для моделей

**Содержимое:**
```python
import pytest
import uuid
from decimal import Decimal
from sqlalchemy.exc import IntegrityError
from app.models import Payment, PaymentStatus, Currency, Outbox, OutboxStatus


class TestPaymentModel:
    """Tests for Payment model"""
    
    async def test_create_payment_with_valid_data(self, db_session):
        """Test creating payment with valid data"""
        payment = Payment(
            id=uuid.uuid4(),
            amount=Decimal("100.50"),
            currency=Currency.RUB,
            description="Test",
            metadata={},
            status=PaymentStatus.PENDING,
            idempotency_key="test-key",
            webhook_url="https://example.com/webhook",
        )
        db_session.add(payment)
        await db_session.commit()
        
        assert payment.id is not None
        assert payment.status == PaymentStatus.PENDING
        assert payment.created_at is not None
        assert payment.processed_at is None
    
    async def test_payment_idempotency_key_unique_constraint(self, db_session):
        """Test idempotency_key unique constraint"""
        payment1 = Payment(
            id=uuid.uuid4(),
            amount=Decimal("100.00"),
            currency=Currency.RUB,
            description="Test",
            metadata={},
            status=PaymentStatus.PENDING,
            idempotency_key="duplicate-key",
            webhook_url="https://example.com/webhook",
        )
        db_session.add(payment1)
        await db_session.commit()
        
        # Try to create another payment with same key
        payment2 = Payment(
            id=uuid.uuid4(),
            amount=Decimal("200.00"),
            currency=Currency.USD,
            description="Test 2",
            metadata={},
            status=PaymentStatus.PENDING,
            idempotency_key="duplicate-key",  # Same key
            webhook_url="https://example.com/webhook",
        )
        db_session.add(payment2)
        
        with pytest.raises(IntegrityError):
            await db_session.commit()
    
    async def test_payment_amount_must_be_positive(self, db_session):
        """Test amount > 0 constraint"""
        payment = Payment(
            id=uuid.uuid4(),
            amount=Decimal("-10.00"),  # Negative
            currency=Currency.RUB,
            description="Test",
            metadata={},
            status=PaymentStatus.PENDING,
            idempotency_key="test-key",
            webhook_url="https://example.com/webhook",
        )
        db_session.add(payment)
        
        with pytest.raises(IntegrityError):
            await db_session.commit()


class TestOutboxModel:
    """Tests for Outbox model"""
    
    async def test_create_outbox_with_valid_data(self, db_session):
        """Test creating outbox event"""
        outbox = Outbox(
            aggregate_id=uuid.uuid4(),
            event_type="payment.created",
            payload={"test": True},
            status=OutboxStatus.PENDING,
        )
        db_session.add(outbox)
        await db_session.commit()
        
        assert outbox.id is not None
        assert outbox.status == OutboxStatus.PENDING
        assert outbox.created_at is not None
        assert outbox.published_at is None
```

**Ссылки на дизайн:**
- План тестирования: `../04-testing.md` (Models)

### `tests/unit/test_repositories.py`

**Назначение:** Unit тесты для репозиториев

**Содержимое:**
```python
import pytest
import uuid
from decimal import Decimal
from app.models import PaymentStatus, Currency
from app.repositories import PaymentRepository, OutboxRepository


class TestPaymentRepository:
    """Tests for PaymentRepository"""
    
    async def test_get_by_idempotency_key_returns_payment(self, db_session, payment_factory):
        """Test getting payment by idempotency key"""
        payment = await payment_factory(idempotency_key="test-key-123")
        
        repo = PaymentRepository(db_session)
        found = await repo.get_by_idempotency_key("test-key-123")
        
        assert found is not None
        assert found.id == payment.id
    
    async def test_get_by_idempotency_key_returns_none_if_not_found(self, db_session):
        """Test getting non-existent payment"""
        repo = PaymentRepository(db_session)
        found = await repo.get_by_idempotency_key("non-existent")
        
        assert found is None
    
    async def test_update_status_sets_processed_at(self, db_session, payment_factory):
        """Test updating payment status"""
        payment = await payment_factory(status=PaymentStatus.PENDING)
        
        repo = PaymentRepository(db_session)
        updated = await repo.update_status(payment.id, PaymentStatus.SUCCEEDED)
        
        assert updated.status == PaymentStatus.SUCCEEDED
        assert updated.processed_at is not None


class TestOutboxRepository:
    """Tests for OutboxRepository"""
    
    async def test_get_pending_events_returns_only_pending(self, db_session, outbox_factory):
        """Test getting pending events"""
        await outbox_factory(status="pending")
        await outbox_factory(status="published")
        
        repo = OutboxRepository(db_session)
        events = await repo.get_pending_events()
        
        assert len(events) == 1
        assert events[0].status == "pending"
    
    async def test_mark_as_published_updates_status(self, db_session, outbox_factory):
        """Test marking event as published"""
        outbox = await outbox_factory(status="pending")
        
        repo = OutboxRepository(db_session)
        updated = await repo.mark_as_published(outbox.id)
        
        assert updated.status == "published"
        assert updated.published_at is not None
```

### `tests/unit/test_services.py`

**Назначение:** Unit тесты для сервисов

**Содержимое:**
```python
import pytest
from decimal import Decimal
from app.models import Currency, PaymentStatus
from app.services import PaymentService, PaymentProcessor


class TestPaymentService:
    """Tests for PaymentService"""
    
    async def test_create_payment_success(self, db_session):
        """Test creating payment"""
        service = PaymentService(db_session)
        
        payment = await service.create_payment(
            amount=Decimal("100.50"),
            currency=Currency.RUB,
            description="Test",
            metadata={"test": True},
            webhook_url="https://example.com/webhook",
            idempotency_key="test-key-123",
        )
        await db_session.commit()
        
        assert payment.id is not None
        assert payment.status == PaymentStatus.PENDING
        assert payment.amount == Decimal("100.50")
    
    async def test_create_payment_with_existing_idempotency_key_returns_existing(
        self, db_session, payment_factory
    ):
        """Test idempotency: returns existing payment"""
        existing = await payment_factory(idempotency_key="duplicate-key")
        
        service = PaymentService(db_session)
        payment = await service.create_payment(
            amount=Decimal("999.99"),  # Different amount
            currency=Currency.USD,
            description="Different",
            metadata={},
            webhook_url="https://other.com/webhook",
            idempotency_key="duplicate-key",  # Same key
        )
        
        assert payment.id == existing.id
        assert payment.amount == existing.amount  # Original amount


class TestPaymentProcessor:
    """Tests for PaymentProcessor"""
    
    async def test_process_payment_updates_status(self, db_session, payment_factory):
        """Test processing payment"""
        payment = await payment_factory(status=PaymentStatus.PENDING)
        
        processor = PaymentProcessor(db_session)
        processed = await processor.process_payment(payment.id)
        await db_session.commit()
        
        assert processed.status in [PaymentStatus.SUCCEEDED, PaymentStatus.FAILED]
        assert processed.processed_at is not None
    
    async def test_process_payment_idempotent_skips_already_processed(
        self, db_session, payment_factory
    ):
        """Test processor idempotency"""
        payment = await payment_factory(status=PaymentStatus.SUCCEEDED)
        
        processor = PaymentProcessor(db_session)
        processed = await processor.process_payment(payment.id)
        
        assert processed.status == PaymentStatus.SUCCEEDED
        # processed_at should not change
```

### `tests/integration/test_api.py`

**Назначение:** Integration тесты для API

**Содержимое:**
```python
import pytest
import uuid
from httpx import AsyncClient


class TestCreatePaymentEndpoint:
    """Tests for POST /api/v1/payments"""
    
    async def test_create_payment_returns_202_accepted(self, client: AsyncClient, api_key: str):
        """Test creating payment returns 202"""
        response = await client.post(
            "/api/v1/payments",
            headers={
                "X-API-Key": api_key,
                "Idempotency-Key": str(uuid.uuid4())
            },
            json={
                "amount": "100.50",
                "currency": "RUB",
                "description": "Test",
                "metadata": {"test": True},
                "webhook_url": "https://example.com/webhook"
            }
        )
        
        assert response.status_code == 202
        data = response.json()
        assert "id" in data
        assert data["status"] == "pending"
    
    async def test_create_payment_without_api_key_returns_401(self, client: AsyncClient):
        """Test auth: no API key returns 401"""
        response = await client.post(
            "/api/v1/payments",
            headers={"Idempotency-Key": str(uuid.uuid4())},
            json={}
        )
        
        assert response.status_code == 401
    
    async def test_create_payment_with_negative_amount_returns_422(
        self, client: AsyncClient, api_key: str
    ):
        """Test validation: negative amount returns 422"""
        response = await client.post(
            "/api/v1/payments",
            headers={
                "X-API-Key": api_key,
                "Idempotency-Key": str(uuid.uuid4())
            },
            json={
                "amount": "-10.00",
                "currency": "RUB",
                "description": "Test",
                "metadata": {},
                "webhook_url": "https://example.com/webhook"
            }
        )
        
        assert response.status_code == 422


class TestGetPaymentEndpoint:
    """Tests for GET /api/v1/payments/{id}"""
    
    async def test_get_payment_returns_200_with_payment_data(
        self, client: AsyncClient, api_key: str, db_session, payment_factory
    ):
        """Test getting payment returns 200"""
        payment = await payment_factory()
        
        response = await client.get(
            f"/api/v1/payments/{payment.id}",
            headers={"X-API-Key": api_key}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(payment.id)
    
    async def test_get_payment_not_found_returns_404(
        self, client: AsyncClient, api_key: str
    ):
        """Test getting non-existent payment returns 404"""
        response = await client.get(
            f"/api/v1/payments/{uuid.uuid4()}",
            headers={"X-API-Key": api_key}
        )
        
        assert response.status_code == 404
```

### `tests/e2e/test_payment_flow.py`

**Назначение:** E2E тесты для полных сценариев

**Содержимое:**
```python
import pytest
import asyncio
import uuid
from httpx import AsyncClient


class TestFullPaymentFlow:
    """E2E tests for complete payment flow"""
    
    @pytest.mark.asyncio
    async def test_full_payment_flow_success(self, client: AsyncClient, api_key: str):
        """Test full flow: create → process → webhook → succeeded"""
        # 1. Create payment
        idempotency_key = str(uuid.uuid4())
        response = await client.post(
            "/api/v1/payments",
            headers={
                "X-API-Key": api_key,
                "Idempotency-Key": idempotency_key
            },
            json={
                "amount": "100.50",
                "currency": "RUB",
                "description": "E2E test",
                "metadata": {"test": "e2e"},
                "webhook_url": "https://webhook.site/test"
            }
        )
        
        assert response.status_code == 202
        payment_id = response.json()["id"]
        
        # 2. Wait for async processing
        await asyncio.sleep(10)
        
        # 3. Check final status
        response = await client.get(
            f"/api/v1/payments/{payment_id}",
            headers={"X-API-Key": api_key}
        )
        
        assert response.status_code == 200
        payment = response.json()
        assert payment["status"] in ["succeeded", "failed"]
        assert payment["processed_at"] is not None
    
    @pytest.mark.asyncio
    async def test_full_payment_flow_idempotency(self, client: AsyncClient, api_key: str):
        """Test idempotency across full flow"""
        idempotency_key = str(uuid.uuid4())
        
        # Create payment twice with same key
        response1 = await client.post(
            "/api/v1/payments",
            headers={
                "X-API-Key": api_key,
                "Idempotency-Key": idempotency_key
            },
            json={
                "amount": "100.50",
                "currency": "RUB",
                "description": "First",
                "metadata": {},
                "webhook_url": "https://example.com/webhook"
            }
        )
        
        response2 = await client.post(
            "/api/v1/payments",
            headers={
                "X-API-Key": api_key,
                "Idempotency-Key": idempotency_key  # Same key
            },
            json={
                "amount": "999.99",  # Different data
                "currency": "USD",
                "description": "Second",
                "metadata": {},
                "webhook_url": "https://other.com/webhook"
            }
        )
        
        payment1 = response1.json()
        payment2 = response2.json()
        
        assert payment1["id"] == payment2["id"]
        # Should return original payment data
```

### `pytest.ini`

**Назначение:** Конфигурация pytest

**Содержимое:**
```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    -v
    --strict-markers
    --tb=short
    --cov=app
    --cov-report=term-missing
    --cov-report=html
    --cov-fail-under=95
markers =
    unit: Unit tests
    integration: Integration tests
    e2e: End-to-end tests
```

### `scripts/run-tests.sh`

**Назначение:** Скрипт для запуска тестов

**Содержимое:**
```bash
#!/bin/bash
set -e

echo "🧪 Running tests..."
echo ""

# Create test database
echo "1️⃣  Creating test database..."
docker-compose exec -T postgres psql -U user -d postgres -c "DROP DATABASE IF EXISTS payments_test;"
docker-compose exec -T postgres psql -U user -d postgres -c "CREATE DATABASE payments_test;"

echo ""
echo "2️⃣  Running unit tests..."
pytest tests/unit/ -v

echo ""
echo "3️⃣  Running integration tests..."
pytest tests/integration/ -v

echo ""
echo "4️⃣  Running E2E tests..."
pytest tests/e2e/ -v

echo ""
echo "5️⃣  Generating coverage report..."
pytest --cov=app --cov-report=html --cov-report=term

echo ""
echo "✅ All tests passed!"
echo ""
echo "📊 Coverage report: htmlcov/index.html"
```

## Определение готовности

- [ ] Все тестовые файлы созданы
- [ ] conftest.py содержит все необходимые fixtures
- [ ] Unit тесты покрывают модели, репозитории, сервисы
- [ ] Integration тесты покрывают API endpoints
- [ ] E2E тесты покрывают полные сценарии
- [ ] Все тесты проходят: `pytest`
- [ ] Покрытие ≥95%: `pytest --cov=app --cov-report=term`
- [ ] Coverage report генерируется: `htmlcov/index.html`
- [ ] run-tests.sh запускает все тесты
- [ ] Тестовая БД создаётся и очищается автоматически

## Проверка результата

### 1. Запустить все тесты

```bash
# Убедиться что сервисы запущены
docker-compose ps

# Запустить тесты
chmod +x scripts/run-tests.sh
./scripts/run-tests.sh
```

Ожидаемый вывод:
```
🧪 Running tests...

1️⃣  Creating test database...
DROP DATABASE
CREATE DATABASE

2️⃣  Running unit tests...
tests/unit/test_models.py::TestPaymentModel::test_create_payment_with_valid_data PASSED
tests/unit/test_models.py::TestPaymentModel::test_payment_idempotency_key_unique_constraint PASSED
...
========== 25 passed in 5.23s ==========

3️⃣  Running integration tests...
tests/integration/test_api.py::TestCreatePaymentEndpoint::test_create_payment_returns_202_accepted PASSED
...
========== 15 passed in 3.45s ==========

4️⃣  Running E2E tests...
tests/e2e/test_payment_flow.py::TestFullPaymentFlow::test_full_payment_flow_success PASSED
...
========== 5 passed in 12.34s ==========

5️⃣  Generating coverage report...
---------- coverage: platform linux, python 3.11.8 -----------
Name                                    Stmts   Miss  Cover   Missing
---------------------------------------------------------------------
app/__init__.py                             0      0   100%
app/api/__init__.py                         0      0   100%
app/api/dependencies.py                    12      0   100%
app/api/v1/__init__.py                      0      0   100%
app/api/v1/payments.py                     45      2    96%   78-79
app/config.py                              15      0   100%
app/consumer/__init__.py                    2      0   100%
app/consumer/payment_handler.py            65      3    95%   89-91
app/db/__init__.py                          4      0   100%
app/db/base.py                              2      0   100%
app/db/session.py                          18      1    94%   35
app/main.py                                25      2    92%   45-46
app/middleware/__init__.py                  1      0   100%
app/middleware/auth.py                     15      1    93%   28
app/models/__init__.py                      6      0   100%
app/models/outbox.py                       15      0   100%
app/models/payment.py                      35      0   100%
app/repositories/__init__.py                2      0   100%
app/repositories/outbox_repository.py      35      1    97%   67
app/repositories/payment_repository.py     45      2    96%   78-79
app/schemas/__init__.py                     4      0   100%
app/schemas/payment.py                     45      2    96%   89-90
app/services/__init__.py                    6      0   100%
app/services/outbox_service.py             35      1    97%   56
app/services/payment_processor.py          42      2    95%   67-68
app/services/payment_service.py            38      1    97%   54
app/services/webhook_client.py             55      3    95%   78-80
app/tasks/__init__.py                       2      0   100%
app/tasks/outbox_publisher.py              58      3    95%   89-91
---------------------------------------------------------------------
TOTAL                                     627     24    96%

✅ All tests passed!

📊 Coverage report: htmlcov/index.html
```

### 2. Проверить coverage report

```bash
# Открыть в браузере
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

### 3. Запустить отдельные категории тестов

```bash
# Только unit
pytest tests/unit/ -v

# Только integration
pytest tests/integration/ -v

# Только e2e
pytest tests/e2e/ -v

# С маркерами
pytest -m unit
pytest -m integration
pytest -m e2e
```

### 4. Проверить конкретный тест

```bash
pytest tests/unit/test_models.py::TestPaymentModel::test_create_payment_with_valid_data -v
```

### 5. Финальная проверка

```bash
# Все тесты + coverage + fail if < 95%
pytest --cov=app --cov-report=term --cov-fail-under=95
```

Если coverage < 95%, pytest завершится с ошибкой.

---

## Итоговая проверка всех фаз

После завершения Phase 6, проверить все критерии готовности из `plan/README.md`:

```bash
# 1. Все сервисы запущены
docker-compose ps

# 2. Миграции применены
docker-compose exec api alembic current

# 3. API работает
curl http://localhost:8000/health

# 4. E2E тест проходит
./scripts/test-e2e.sh

# 5. Все тесты проходят с покрытием ≥95%
./scripts/run-tests.sh

# 6. Линтинг проходит
docker-compose exec api ruff check app/

# 7. Type checking проходит
docker-compose exec api mypy app/
```

Если все проверки проходят — проект готов! ✅
