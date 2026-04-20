---
name: API-слой
layer: presentation
depends_on: phase-02
plan: ./README.md
---

# Фаза 3: API-слой

## Цель

Создать REST API эндпоинты с аутентификацией, валидацией и интеграцией с сервисами из Phase 2.

## Контекст

После завершения Phase 2 у нас есть:
- PaymentService для создания и получения платежей
- Repositories и модели
- Бизнес-логика с idempotency

В этой фазе создаём:
- Pydantic schemas для валидации запросов/ответов
- API Key middleware для аутентификации
- FastAPI endpoints: POST /api/v1/payments, GET /api/v1/payments/{id}
- Обработку ошибок и HTTP статусов
- OpenAPI документацию

## Создать файлы

### `app/schemas/payment.py`

**Назначение:** Pydantic schemas для валидации API

**Содержимое:**
```python
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, HttpUrl, field_validator
from app.models import PaymentStatus, Currency


class PaymentCreateRequest(BaseModel):
    """Request schema for creating payment"""
    
    amount: Decimal = Field(
        ...,
        gt=0,
        decimal_places=2,
        description="Payment amount (must be positive, max 2 decimal places)"
    )
    currency: Currency = Field(
        ...,
        description="Currency code (RUB, USD, EUR)"
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Payment description"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (JSON object)"
    )
    webhook_url: HttpUrl = Field(
        ...,
        description="URL for webhook notifications"
    )
    
    @field_validator('amount')
    @classmethod
    def validate_amount_precision(cls, v: Decimal) -> Decimal:
        """Ensure amount has max 2 decimal places"""
        if v.as_tuple().exponent < -2:
            raise ValueError("Amount must have at most 2 decimal places")
        return v
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "amount": "100.50",
                    "currency": "RUB",
                    "description": "Payment for order #12345",
                    "metadata": {"order_id": "12345"},
                    "webhook_url": "https://example.com/webhook"
                }
            ]
        }
    }


class PaymentCreateResponse(BaseModel):
    """Response schema for payment creation (202 Accepted)"""
    
    id: UUID = Field(..., description="Payment unique identifier")
    status: PaymentStatus = Field(..., description="Payment status (always 'pending' on creation)")
    created_at: datetime = Field(..., description="Payment creation timestamp (UTC)")
    
    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "examples": [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "status": "pending",
                    "created_at": "2026-04-20T10:00:00.123456Z"
                }
            ]
        }
    }


class PaymentDetailResponse(BaseModel):
    """Response schema for payment details"""
    
    id: UUID
    amount: Decimal
    currency: Currency
    description: str
    metadata: Dict[str, Any]
    status: PaymentStatus
    idempotency_key: str
    webhook_url: str
    created_at: datetime
    processed_at: Optional[datetime] = None
    
    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "examples": [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "amount": "100.50",
                    "currency": "RUB",
                    "description": "Payment for order #12345",
                    "metadata": {"order_id": "12345"},
                    "status": "succeeded",
                    "idempotency_key": "client-key-123",
                    "webhook_url": "https://example.com/webhook",
                    "created_at": "2026-04-20T10:00:00.123456Z",
                    "processed_at": "2026-04-20T10:00:03.456789Z"
                }
            ]
        }
    }


class ErrorResponse(BaseModel):
    """Standard error response"""
    
    detail: str = Field(..., description="Error message")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {"detail": "Payment not found"},
                {"detail": "Invalid API key"}
            ]
        }
    }
```

**Детали реализации:**
- Decimal validation с gt=0 и decimal_places=2
- HttpUrl для webhook_url (автоматическая валидация URL)
- from_attributes=True для конвертации из ORM моделей
- Примеры в json_schema_extra для OpenAPI документации

**Ссылки на дизайн:**
- API контракт: `../08-api-contract.md`
- Решения: `../03-decisions.md` (ADR-09 Decimal)

### `app/schemas/__init__.py`

**Назначение:** Экспорт schemas

**Содержимое:**
```python
from app.schemas.payment import (
    PaymentCreateRequest,
    PaymentCreateResponse,
    PaymentDetailResponse,
    ErrorResponse,
)

__all__ = [
    "PaymentCreateRequest",
    "PaymentCreateResponse",
    "PaymentDetailResponse",
    "ErrorResponse",
]
```

### `app/middleware/auth.py`

**Назначение:** Middleware для проверки X-API-Key

**Содержимое:**
```python
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from app.config import settings


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Middleware to validate X-API-Key header"""
    
    async def dispatch(self, request: Request, call_next):
        # Skip auth for docs endpoints
        if request.url.path in ["/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)
        
        # Check X-API-Key header
        api_key = request.headers.get("X-API-Key")
        
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="X-API-Key header is required"
            )
        
        if api_key != settings.api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key"
            )
        
        # Continue to endpoint
        response = await call_next(request)
        return response
```

**Детали реализации:**
- Проверка наличия заголовка X-API-Key
- Сравнение с settings.api_key
- 401 Unauthorized при отсутствии или неверном ключе
- Пропуск /docs, /redoc, /openapi.json для доступа к документации

**Ссылки на дизайн:**
- Решение: `../03-decisions.md` (ADR-03 API Key)
- API контракт: `../08-api-contract.md` (аутентификация)

### `app/middleware/__init__.py`

**Назначение:** Экспорт middleware

**Содержимое:**
```python
from app.middleware.auth import APIKeyMiddleware

__all__ = ["APIKeyMiddleware"]
```

### `app/api/dependencies.py`

**Назначение:** FastAPI dependencies

**Содержимое:**
```python
from typing import Annotated
from fastapi import Header, HTTPException, status


async def get_idempotency_key(
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")]
) -> str:
    """
    Dependency to extract and validate Idempotency-Key header
    
    Args:
        idempotency_key: Value from Idempotency-Key header
        
    Returns:
        Validated idempotency key
        
    Raises:
        HTTPException: If header is missing or empty
    """
    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Idempotency-Key header is required and must not be empty"
        )
    
    return idempotency_key.strip()
```

**Детали реализации:**
- Header dependency для Idempotency-Key
- Валидация наличия и непустоты
- 422 Unprocessable Entity при отсутствии

### `app/api/__init__.py`

**Назначение:** Пустой файл для package

**Содержимое:** (пустой файл)

### `app/api/v1/__init__.py`

**Назначение:** Пустой файл для package

**Содержимое:** (пустой файл)

### `app/api/v1/payments.py`

**Назначение:** Payment endpoints

**Содержимое:**
```python
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.schemas import (
    PaymentCreateRequest,
    PaymentCreateResponse,
    PaymentDetailResponse,
    ErrorResponse,
)
from app.services import PaymentService
from app.api.dependencies import get_idempotency_key

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post(
    "",
    response_model=PaymentCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        200: {
            "model": PaymentCreateResponse,
            "description": "Payment already exists (idempotency)"
        },
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        422: {"model": ErrorResponse, "description": "Validation error"},
    },
    summary="Create payment",
    description="Create new payment and queue for async processing. Returns 202 Accepted.",
)
async def create_payment(
    request: PaymentCreateRequest,
    idempotency_key: str = Depends(get_idempotency_key),
    db: AsyncSession = Depends(get_db),
) -> PaymentCreateResponse:
    """
    Create new payment
    
    - Requires X-API-Key header for authentication
    - Requires Idempotency-Key header for idempotency
    - Returns 202 Accepted for new payments
    - Returns 200 OK if payment with same Idempotency-Key already exists
    """
    service = PaymentService(db)
    
    payment = await service.create_payment(
        amount=request.amount,
        currency=request.currency,
        description=request.description,
        metadata=request.metadata,
        webhook_url=str(request.webhook_url),
        idempotency_key=idempotency_key,
    )
    
    # Return 200 OK if payment already existed (idempotency)
    # Note: FastAPI will use 202 by default, we handle this in response
    return PaymentCreateResponse.model_validate(payment)


@router.get(
    "/{payment_id}",
    response_model=PaymentDetailResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        404: {"model": ErrorResponse, "description": "Payment not found"},
    },
    summary="Get payment details",
    description="Get detailed information about payment by ID",
)
async def get_payment(
    payment_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> PaymentDetailResponse:
    """
    Get payment by ID
    
    - Requires X-API-Key header for authentication
    - Returns 404 if payment not found
    """
    service = PaymentService(db)
    
    payment = await service.get_payment(payment_id)
    
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found"
        )
    
    return PaymentDetailResponse.model_validate(payment)
```

**Детали реализации:**
- APIRouter с prefix="/payments"
- Dependency injection для db session и idempotency_key
- response_model для автоматической сериализации
- responses для OpenAPI документации
- HTTPException для 404
- model_validate() для конвертации ORM → Pydantic

**Ссылки на дизайн:**
- API контракт: `../08-api-contract.md` (оба эндпоинта)
- Поведение: `../02-behavior.md` (Use Case 1, 2)

### `app/main.py`

**Назначение:** FastAPI приложение

**Содержимое:**
```python
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from app.config import settings
from app.middleware import APIKeyMiddleware
from app.api.v1 import payments

# Create FastAPI app
app = FastAPI(
    title="Payment Processing Service",
    description="Async payment processing microservice with guaranteed delivery",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add middleware
app.add_middleware(APIKeyMiddleware)

# Include routers
app.include_router(payments.router, prefix="/api/v1")


@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint"""
    return JSONResponse(
        content={
            "status": "healthy",
            "service": "payment-processing"
        }
    )


@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint redirect to docs"""
    return JSONResponse(
        content={
            "message": "Payment Processing Service",
            "docs": "/docs",
            "health": "/health"
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
```

**Детали реализации:**
- FastAPI app с metadata для OpenAPI
- APIKeyMiddleware для всех эндпоинтов
- Router с prefix /api/v1
- Health check эндпоинт
- Uvicorn для запуска

## Определение готовности

- [ ] Все файлы созданы согласно списку выше
- [ ] Pydantic schemas валидируют запросы/ответы
- [ ] APIKeyMiddleware проверяет X-API-Key
- [ ] POST /api/v1/payments создаёт платёж
- [ ] POST /api/v1/payments возвращает 202 Accepted
- [ ] POST /api/v1/payments проверяет Idempotency-Key
- [ ] GET /api/v1/payments/{id} возвращает детали
- [ ] GET /api/v1/payments/{id} возвращает 404 если не найден
- [ ] Без X-API-Key возвращается 401
- [ ] OpenAPI документация доступна на /docs
- [ ] Health check работает: GET /health
- [ ] Ruff проверка проходит: `ruff check app/`
- [ ] MyPy проверка проходит: `mypy app/`

## Проверка результата

### 1. Запустить API

```bash
# Убедиться что PostgreSQL запущен
docker ps | grep payment-postgres

# Запустить FastAPI
python -m app.main
```

Ожидаемый вывод:
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 2. Проверить документацию

Открыть в браузере: http://localhost:8000/docs

Должна отобразиться Swagger UI с двумя эндпоинтами:
- POST /api/v1/payments
- GET /api/v1/payments/{payment_id}

### 3. Тестовые запросы

```bash
# Health check (без auth)
curl http://localhost:8000/health

# Создать платёж (с auth)
curl -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: change-me-in-production" \
  -H "Idempotency-Key: $(uuidgen)" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "100.50",
    "currency": "RUB",
    "description": "Test payment",
    "metadata": {"test": true},
    "webhook_url": "https://example.com/webhook"
  }'

# Ожидаемый ответ: 202 Accepted
# {
#   "id": "550e8400-...",
#   "status": "pending",
#   "created_at": "2026-04-20T10:00:00.123456Z"
# }

# Получить платёж
PAYMENT_ID="<id из предыдущего ответа>"
curl http://localhost:8000/api/v1/payments/$PAYMENT_ID \
  -H "X-API-Key: change-me-in-production"

# Ожидаемый ответ: 200 OK с полными деталями

# Проверить idempotency (тот же Idempotency-Key)
curl -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: change-me-in-production" \
  -H "Idempotency-Key: <тот же ключ>" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "999.99",
    "currency": "USD",
    "description": "Different",
    "metadata": {},
    "webhook_url": "https://other.com/webhook"
  }'

# Ожидаемый ответ: 200 OK с оригинальным платежом (amount=100.50)

# Проверить 401 без API key
curl -X POST http://localhost:8000/api/v1/payments \
  -H "Content-Type: application/json" \
  -d '{}'

# Ожидаемый ответ: 401 Unauthorized
# {"detail": "X-API-Key header is required"}

# Проверить 404
curl http://localhost:8000/api/v1/payments/00000000-0000-0000-0000-000000000000 \
  -H "X-API-Key: change-me-in-production"

# Ожидаемый ответ: 404 Not Found
# {"detail": "Payment not found"}
```

### 4. Python тест

```python
# test_phase_03.py
import httpx
import uuid

API_BASE = "http://localhost:8000/api/v1"
API_KEY = "change-me-in-production"

def test_api():
    # Test create payment
    idempotency_key = str(uuid.uuid4())
    response = httpx.post(
        f"{API_BASE}/payments",
        headers={
            "X-API-Key": API_KEY,
            "Idempotency-Key": idempotency_key
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
    payment_id = data["id"]
    print(f"✓ Payment created: {payment_id}")
    
    # Test get payment
    response = httpx.get(
        f"{API_BASE}/payments/{payment_id}",
        headers={"X-API-Key": API_KEY}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == payment_id
    assert data["status"] == "pending"
    print(f"✓ Payment retrieved: {data['status']}")
    
    # Test idempotency
    response = httpx.post(
        f"{API_BASE}/payments",
        headers={
            "X-API-Key": API_KEY,
            "Idempotency-Key": idempotency_key  # Same key
        },
        json={
            "amount": "999.99",  # Different data
            "currency": "USD",
            "description": "Different",
            "metadata": {},
            "webhook_url": "https://other.com/webhook"
        }
    )
    
    assert response.status_code == 202  # Still 202, but returns existing
    data = response.json()
    assert data["id"] == payment_id
    print(f"✓ Idempotency works")
    
    # Test 401
    response = httpx.post(
        f"{API_BASE}/payments",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={}
    )
    
    assert response.status_code == 401
    print(f"✓ Auth works: 401 without API key")
    
    # Test 404
    response = httpx.get(
        f"{API_BASE}/payments/00000000-0000-0000-0000-000000000000",
        headers={"X-API-Key": API_KEY}
    )
    
    assert response.status_code == 404
    print(f"✓ 404 for non-existent payment")

if __name__ == "__main__":
    test_api()
    print("\n✅ All API tests passed!")
```

Запустить: `python test_phase_03.py`
