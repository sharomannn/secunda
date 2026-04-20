---
name: Репозитории и сервисы
layer: data-access, business-logic
depends_on: phase-01
plan: ./README.md
---

# Фаза 2: Репозитории и сервисы

## Цель

Реализовать слой доступа к данным (repositories) и бизнес-логику (services) для работы с платежами и outbox событиями.

## Контекст

После завершения Phase 1 у нас есть:
- SQLAlchemy модели Payment и Outbox
- Async database session
- Миграции применены

В этой фазе создаём:
- Repositories для инкапсуляции ORM-операций
- Services для бизнес-логики (создание платежа, outbox, обработка, webhook)
- Все компоненты готовы для использования в API и Consumer

## Создать файлы

### `app/repositories/payment_repository.py`

**Назначение:** Репозиторий для работы с Payment

**Содержимое:**
```python
from typing import Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Payment, PaymentStatus


class PaymentRepository:
    """Repository for Payment model"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(self, payment: Payment) -> Payment:
        """
        Create new payment
        
        Args:
            payment: Payment instance
            
        Returns:
            Created payment
        """
        self.session.add(payment)
        await self.session.flush()
        await self.session.refresh(payment)
        return payment
    
    async def get_by_id(self, payment_id: UUID) -> Optional[Payment]:
        """
        Get payment by ID
        
        Args:
            payment_id: Payment UUID
            
        Returns:
            Payment or None if not found
        """
        result = await self.session.execute(
            select(Payment).where(Payment.id == payment_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_idempotency_key(self, idempotency_key: str) -> Optional[Payment]:
        """
        Get payment by idempotency key
        
        Args:
            idempotency_key: Unique idempotency key
            
        Returns:
            Payment or None if not found
        """
        result = await self.session.execute(
            select(Payment).where(Payment.idempotency_key == idempotency_key)
        )
        return result.scalar_one_or_none()
    
    async def update_status(
        self,
        payment_id: UUID,
        status: PaymentStatus,
    ) -> Payment:
        """
        Update payment status and set processed_at
        
        Args:
            payment_id: Payment UUID
            status: New status
            
        Returns:
            Updated payment
            
        Raises:
            ValueError: If payment not found
        """
        payment = await self.get_by_id(payment_id)
        if not payment:
            raise ValueError(f"Payment {payment_id} not found")
        
        payment.status = status
        
        # Set processed_at only if transitioning from pending
        if payment.status == PaymentStatus.PENDING:
            from datetime import datetime, timezone
            payment.processed_at = datetime.now(timezone.utc)
        
        await self.session.flush()
        await self.session.refresh(payment)
        return payment
```

**Детали реализации:**
- Инкапсуляция всех ORM-операций
- Async методы для всех операций
- flush() + refresh() для получения актуальных данных
- Явная обработка отсутствия записей (Optional)

**Ссылки на дизайн:**
- Архитектура: `../01-architecture.md` (Repository Pattern)
- Модель: `../06-models.md` (Payment)

### `app/repositories/outbox_repository.py`

**Назначение:** Репозиторий для работы с Outbox

**Содержимое:**
```python
from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Outbox, OutboxStatus


class OutboxRepository:
    """Repository for Outbox model"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(self, outbox: Outbox) -> Outbox:
        """
        Create new outbox event
        
        Args:
            outbox: Outbox instance
            
        Returns:
            Created outbox event
        """
        self.session.add(outbox)
        await self.session.flush()
        await self.session.refresh(outbox)
        return outbox
    
    async def get_pending_events(self, limit: int = 100) -> List[Outbox]:
        """
        Get pending outbox events for publishing
        
        Args:
            limit: Maximum number of events to fetch
            
        Returns:
            List of pending outbox events
        """
        result = await self.session.execute(
            select(Outbox)
            .where(Outbox.status == OutboxStatus.PENDING)
            .order_by(Outbox.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def mark_as_published(self, outbox_id: int) -> Outbox:
        """
        Mark outbox event as published
        
        Args:
            outbox_id: Outbox event ID
            
        Returns:
            Updated outbox event
            
        Raises:
            ValueError: If outbox event not found
        """
        result = await self.session.execute(
            select(Outbox).where(Outbox.id == outbox_id)
        )
        outbox = result.scalar_one_or_none()
        
        if not outbox:
            raise ValueError(f"Outbox event {outbox_id} not found")
        
        from datetime import datetime, timezone
        outbox.status = OutboxStatus.PUBLISHED
        outbox.published_at = datetime.now(timezone.utc)
        
        await self.session.flush()
        await self.session.refresh(outbox)
        return outbox
```

**Детали реализации:**
- get_pending_events() для Outbox Publisher
- Сортировка по created_at (FIFO)
- Limit для batch processing
- mark_as_published() устанавливает timestamp

**Ссылки на дизайн:**
- Паттерн: `../03-decisions.md` (ADR-01 Outbox Pattern)
- Модель: `../06-models.md` (Outbox)

### `app/repositories/__init__.py`

**Назначение:** Экспорт репозиториев

**Содержимое:**
```python
from app.repositories.payment_repository import PaymentRepository
from app.repositories.outbox_repository import OutboxRepository

__all__ = [
    "PaymentRepository",
    "OutboxRepository",
]
```

### `app/services/payment_service.py`

**Назначение:** Бизнес-логика для работы с платежами

**Содержимое:**
```python
from typing import Optional
from uuid import UUID
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Payment, PaymentStatus, Currency
from app.repositories import PaymentRepository, OutboxRepository
from app.services.outbox_service import OutboxService


class PaymentService:
    """Service for payment business logic"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.payment_repo = PaymentRepository(session)
        self.outbox_service = OutboxService(session)
    
    async def create_payment(
        self,
        amount: Decimal,
        currency: Currency,
        description: str,
        metadata: dict,
        webhook_url: str,
        idempotency_key: str,
    ) -> Payment:
        """
        Create new payment with idempotency check
        
        Args:
            amount: Payment amount
            currency: Currency (RUB, USD, EUR)
            description: Payment description
            metadata: Additional metadata (JSON)
            webhook_url: URL for webhook notifications
            idempotency_key: Unique key for idempotency
            
        Returns:
            Created or existing payment
        """
        # Check idempotency
        existing_payment = await self.payment_repo.get_by_idempotency_key(
            idempotency_key
        )
        if existing_payment:
            return existing_payment
        
        # Create new payment
        import uuid
        payment = Payment(
            id=uuid.uuid4(),
            amount=amount,
            currency=currency,
            description=description,
            metadata=metadata,
            status=PaymentStatus.PENDING,
            idempotency_key=idempotency_key,
            webhook_url=webhook_url,
        )
        
        # Save payment and create outbox event in same transaction
        payment = await self.payment_repo.create(payment)
        
        await self.outbox_service.create_payment_created_event(
            payment_id=payment.id,
            idempotency_key=idempotency_key,
        )
        
        # Commit happens in get_db() dependency
        return payment
    
    async def get_payment(self, payment_id: UUID) -> Optional[Payment]:
        """
        Get payment by ID
        
        Args:
            payment_id: Payment UUID
            
        Returns:
            Payment or None if not found
        """
        return await self.payment_repo.get_by_id(payment_id)
```

**Детали реализации:**
- Проверка idempotency_key перед созданием
- Создание Payment и Outbox в одной транзакции
- Возврат существующего платежа при дубликате ключа
- Делегирование ORM-операций в репозитории

**Ссылки на дизайн:**
- Логика: `../02-behavior.md` (Use Case 1)
- Решение: `../03-decisions.md` (ADR-02 Idempotency)

### `app/services/outbox_service.py`

**Назначение:** Сервис для работы с Outbox Pattern

**Содержимое:**
```python
from typing import List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Outbox, OutboxStatus
from app.repositories import OutboxRepository


class OutboxService:
    """Service for Outbox Pattern"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.outbox_repo = OutboxRepository(session)
    
    async def create_payment_created_event(
        self,
        payment_id: UUID,
        idempotency_key: str,
    ) -> Outbox:
        """
        Create outbox event for payment.created
        
        Args:
            payment_id: Payment UUID
            idempotency_key: Idempotency key from request
            
        Returns:
            Created outbox event
        """
        from datetime import datetime, timezone
        
        outbox = Outbox(
            aggregate_id=payment_id,
            event_type="payment.created",
            payload={
                "payment_id": str(payment_id),
                "idempotency_key": idempotency_key,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            status=OutboxStatus.PENDING,
        )
        
        return await self.outbox_repo.create(outbox)
    
    async def get_pending_events(self, limit: int = 100) -> List[Outbox]:
        """
        Get pending events for publishing
        
        Args:
            limit: Maximum number of events
            
        Returns:
            List of pending outbox events
        """
        return await self.outbox_repo.get_pending_events(limit)
    
    async def mark_as_published(self, outbox_id: int) -> Outbox:
        """
        Mark event as published
        
        Args:
            outbox_id: Outbox event ID
            
        Returns:
            Updated outbox event
        """
        return await self.outbox_repo.mark_as_published(outbox_id)
```

**Детали реализации:**
- create_payment_created_event() формирует payload
- Payload содержит payment_id, idempotency_key, created_at
- get_pending_events() для Outbox Publisher
- mark_as_published() для обновления статуса после публикации

**Ссылки на дизайн:**
- Паттерн: `../03-decisions.md` (ADR-01)
- Async tasks: `../05-async-tasks.md` (Outbox Publisher)

### `app/services/payment_processor.py`

**Назначение:** Эмуляция обработки платежа

**Содержимое:**
```python
import asyncio
import random
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Payment, PaymentStatus
from app.repositories import PaymentRepository


class PaymentProcessor:
    """Service for payment processing emulation"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.payment_repo = PaymentRepository(session)
    
    async def process_payment(self, payment_id: UUID) -> Payment:
        """
        Process payment with emulation
        
        - Processing time: 2-5 seconds
        - Success rate: 90%
        - Failure rate: 10%
        
        Args:
            payment_id: Payment UUID
            
        Returns:
            Processed payment
            
        Raises:
            ValueError: If payment not found or already processed
        """
        payment = await self.payment_repo.get_by_id(payment_id)
        
        if not payment:
            raise ValueError(f"Payment {payment_id} not found")
        
        # Check idempotency: skip if already processed
        if payment.status != PaymentStatus.PENDING:
            return payment
        
        # Emulate processing time (2-5 seconds)
        processing_time = random.uniform(2.0, 5.0)
        await asyncio.sleep(processing_time)
        
        # Determine result (90% success, 10% failure)
        success = random.random() < 0.9
        new_status = PaymentStatus.SUCCEEDED if success else PaymentStatus.FAILED
        
        # Update payment status
        payment = await self.payment_repo.update_status(
            payment_id=payment_id,
            status=new_status,
        )
        
        return payment
```

**Детали реализации:**
- random.uniform(2.0, 5.0) для времени обработки
- random.random() < 0.9 для 90% успеха
- Идемпотентность: пропуск уже обработанных
- update_status() устанавливает processed_at

**Ссылки на дизайн:**
- Требования: `../README.md` (эмуляция 2-5 сек, 90% успех)
- Логика: `../02-behavior.md` (Use Case 3)
- Async tasks: `../05-async-tasks.md` (Payment Processor)

### `app/services/webhook_client.py`

**Назначение:** HTTP-клиент для отправки webhook с retry

**Содержимое:**
```python
import asyncio
from typing import Dict, Any
import httpx


class WebhookDeliveryError(Exception):
    """Raised when webhook delivery fails after all retries"""
    pass


class WebhookClientError(Exception):
    """Raised when webhook returns 4xx error (no retry)"""
    pass


class WebhookClient:
    """HTTP client for webhook delivery with retry logic"""
    
    def __init__(self):
        self.timeout = 5.0  # HTTP request timeout
        self.max_retries = 3
        self.backoff_delays = [1, 2, 4]  # Exponential backoff
    
    async def send_webhook(self, url: str, payload: Dict[str, Any]) -> None:
        """
        Send webhook with retry logic
        
        - 3 attempts with exponential backoff (1s, 2s, 4s)
        - Retry on 5xx, timeout, connection errors
        - No retry on 4xx (client errors)
        
        Args:
            url: Webhook URL
            payload: JSON payload to send
            
        Raises:
            WebhookClientError: On 4xx errors (no retry)
            WebhookDeliveryError: After exhausting all retries
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(self.max_retries):
                try:
                    response = await client.post(
                        url,
                        json=payload,
                        headers={"Content-Type": "application/json"}
                    )
                    
                    # Success: 2xx status
                    if 200 <= response.status_code < 300:
                        return
                    
                    # Client error 4xx: no retry
                    if 400 <= response.status_code < 500:
                        raise WebhookClientError(
                            f"Client error {response.status_code}: {response.text}"
                        )
                    
                    # Server error 5xx: retry
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.backoff_delays[attempt])
                        continue
                    
                except (httpx.TimeoutException, httpx.ConnectError) as e:
                    # Network errors: retry
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.backoff_delays[attempt])
                        continue
                    
                    raise WebhookDeliveryError(
                        f"Failed after {self.max_retries} attempts: {str(e)}"
                    )
            
            raise WebhookDeliveryError(
                f"Failed after {self.max_retries} attempts"
            )
```

**Детали реализации:**
- httpx.AsyncClient для async HTTP
- Timeout 5 секунд
- Exponential backoff: 1s, 2s, 4s
- Различная обработка 4xx (no retry) и 5xx (retry)
- Retry на timeout и connection errors

**Ссылки на дизайн:**
- Решение: `../03-decisions.md` (ADR-04 Retry)
- Async tasks: `../05-async-tasks.md` (Webhook Client)
- Поведение: `../02-behavior.md` (Use Case 3, ошибки webhook)

### `app/services/__init__.py`

**Назначение:** Экспорт сервисов

**Содержимое:**
```python
from app.services.payment_service import PaymentService
from app.services.outbox_service import OutboxService
from app.services.payment_processor import PaymentProcessor
from app.services.webhook_client import (
    WebhookClient,
    WebhookDeliveryError,
    WebhookClientError,
)

__all__ = [
    "PaymentService",
    "OutboxService",
    "PaymentProcessor",
    "WebhookClient",
    "WebhookDeliveryError",
    "WebhookClientError",
]
```

## Определение готовности

- [ ] Все файлы созданы согласно списку выше
- [ ] PaymentRepository реализует: create, get_by_id, get_by_idempotency_key, update_status
- [ ] OutboxRepository реализует: create, get_pending_events, mark_as_published
- [ ] PaymentService проверяет idempotency перед созданием
- [ ] PaymentService создаёт Payment и Outbox в одной транзакции
- [ ] PaymentProcessor эмулирует обработку 2-5 сек, 90% успех
- [ ] WebhookClient реализует retry с exponential backoff
- [ ] WebhookClient различает 4xx (no retry) и 5xx (retry)
- [ ] Можно импортировать: `from app.services import PaymentService`
- [ ] Ruff проверка проходит: `ruff check app/`
- [ ] MyPy проверка проходит: `mypy app/`

## Проверка результата

```python
# test_phase_02.py
import asyncio
from decimal import Decimal
from app.db import AsyncSessionLocal
from app.models import Currency
from app.services import PaymentService, PaymentProcessor
import uuid

async def test_services():
    async with AsyncSessionLocal() as session:
        # Test PaymentService
        service = PaymentService(session)
        
        idempotency_key = str(uuid.uuid4())
        payment = await service.create_payment(
            amount=Decimal("100.50"),
            currency=Currency.RUB,
            description="Test payment",
            metadata={"test": True},
            webhook_url="https://example.com/webhook",
            idempotency_key=idempotency_key,
        )
        await session.commit()
        
        print(f"✓ Payment created: {payment.id}, status={payment.status}")
        
        # Test idempotency
        same_payment = await service.create_payment(
            amount=Decimal("200.00"),  # Different amount
            currency=Currency.USD,
            description="Different",
            metadata={},
            webhook_url="https://other.com/webhook",
            idempotency_key=idempotency_key,  # Same key
        )
        
        assert same_payment.id == payment.id
        assert same_payment.amount == Decimal("100.50")  # Original amount
        print(f"✓ Idempotency works: returned existing payment")
        
        # Test PaymentProcessor
        processor = PaymentProcessor(session)
        processed = await processor.process_payment(payment.id)
        await session.commit()
        
        print(f"✓ Payment processed: status={processed.status}, processed_at={processed.processed_at}")
        
        # Test idempotency of processor
        processed_again = await processor.process_payment(payment.id)
        assert processed_again.status == processed.status
        print(f"✓ Processor idempotency works: skipped already processed")

if __name__ == "__main__":
    asyncio.run(test_services())
```

Запустить: `python test_phase_02.py`

Ожидаемый результат:
```
✓ Payment created: 550e8400-..., status=PaymentStatus.PENDING
✓ Idempotency works: returned existing payment
✓ Payment processed: status=PaymentStatus.SUCCEEDED, processed_at=2026-04-20 10:00:05
✓ Processor idempotency works: skipped already processed
```
