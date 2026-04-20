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
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create test HTTP client with DB dependency override"""
    from app.db import get_db
    
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    
    app.dependency_overrides.clear()


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
            "metadata_": {"test": True},
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
