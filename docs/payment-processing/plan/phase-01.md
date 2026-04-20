---
name: Инфраструктура и модели
layer: infrastructure, models
depends_on: none
plan: ./README.md
---

# Фаза 1: Инфраструктура и модели

## Цель

Создать фундамент приложения: структуру проекта, конфигурацию, модели данных и миграции БД.

## Контекст

Это первая фаза реализации. Нет зависимостей от других фаз. После завершения будут готовы:
- Структура проекта FastAPI
- Конфигурация через environment variables
- SQLAlchemy модели Payment и Outbox
- Alembic миграции для создания таблиц
- Базовая настройка БД (async session)

## Создать файлы

### `pyproject.toml`

**Назначение:** Управление зависимостями и настройка инструментов

**Содержимое:**
```toml
[tool.poetry]
name = "payment-service"
version = "0.1.0"
description = "Async payment processing microservice"
authors = ["Your Name <your.email@example.com>"]
python = "^3.11"

[tool.poetry.dependencies]
python = "^3.11"
fastapi = "^0.109.0"
uvicorn = {extras = ["standard"], version = "^0.27.0"}
pydantic = "^2.5.0"
pydantic-settings = "^2.1.0"
sqlalchemy = "^2.0.25"
asyncpg = "^0.29.0"
alembic = "^1.13.0"
faststream = {extras = ["rabbit"], version = "^0.4.0"}
httpx = "^0.26.0"

[tool.poetry.group.dev.dependencies]
pytest = "^7.4.0"
pytest-asyncio = "^0.23.0"
pytest-cov = "^4.1.0"
pytest-mock = "^3.12.0"
faker = "^22.0.0"
testcontainers = "^3.7.0"
ruff = "^0.1.0"
mypy = "^1.8.0"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.mypy]
python_version = "3.11"
strict = true
plugins = ["pydantic.mypy"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

**Детали:**
- Python 3.11+ для современных async возможностей
- FastAPI + Uvicorn для API
- SQLAlchemy 2.0 с asyncpg для async PostgreSQL
- FastStream для RabbitMQ
- Полный набор dev-зависимостей для тестирования

### `app/config.py`

**Назначение:** Централизованная конфигурация через environment variables

**Содержимое:**
```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings from environment variables"""
    
    # Database
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/payments"
    
    # RabbitMQ
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    
    # API
    api_key: str = "change-me-in-production"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    # Outbox Publisher
    outbox_publish_interval: int = 5  # seconds
    outbox_batch_size: int = 100
    
    # Logging
    log_level: str = "INFO"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )


settings = Settings()
```

**Детали:**
- Использует pydantic-settings для валидации
- Поддержка .env файла
- Значения по умолчанию для локальной разработки

### `app/db/base.py`

**Назначение:** SQLAlchemy Base для декларативных моделей

**Содержимое:**
```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models"""
    pass
```

### `app/db/session.py`

**Назначение:** Async database session factory

**Содержимое:**
```python
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.config import settings

# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=settings.log_level == "DEBUG",
    pool_size=20,
    max_overflow=10,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI endpoints to get database session
    
    Usage:
        @app.get("/")
        async def endpoint(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

**Детали:**
- Async engine с connection pooling
- Session factory для создания сессий
- Dependency для FastAPI с автоматическим commit/rollback

### `app/models/payment.py`

**Назначение:** SQLAlchemy модель для платежей

**Содержимое:**
```python
import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from sqlalchemy import Column, String, Numeric, CheckConstraint, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM as PG_ENUM
from sqlalchemy.sql import func
from app.db.base import Base


class PaymentStatus(str, Enum):
    """Payment status enum"""
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Currency(str, Enum):
    """Supported currencies"""
    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"


class Payment(Base):
    """Payment model"""
    __tablename__ = "payments"
    
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False
    )
    amount = Column(
        Numeric(precision=10, scale=2),
        nullable=False
    )
    currency = Column(
        PG_ENUM(Currency, name="currency", create_type=False),
        nullable=False
    )
    description = Column(
        String(500),
        nullable=False
    )
    metadata = Column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}"
    )
    status = Column(
        PG_ENUM(PaymentStatus, name="payment_status", create_type=False),
        nullable=False,
        default=PaymentStatus.PENDING,
        server_default="pending"
    )
    idempotency_key = Column(
        String(255),
        nullable=False,
        unique=True,
        index=True
    )
    webhook_url = Column(
        String(2048),
        nullable=False
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )
    processed_at = Column(
        DateTime(timezone=True),
        nullable=True
    )
    
    __table_args__ = (
        CheckConstraint('amount > 0', name='check_amount_positive'),
    )
    
    def __repr__(self) -> str:
        return f"<Payment(id={self.id}, status={self.status}, amount={self.amount})>"
```

**Детали реализации:**
- UUID для id (генерируется автоматически)
- Decimal для amount (точность финансовых расчётов)
- ENUM для status и currency
- JSONB для metadata
- CHECK constraint для положительной суммы
- Уникальный индекс на idempotency_key
- Timestamps с timezone

**Ссылки на дизайн:**
- Схема: `../06-models.md` (Payment)
- Бизнес-правила: `../03-decisions.md` (ADR-08, ADR-09, ADR-10)

### `app/models/outbox.py`

**Назначение:** SQLAlchemy модель для Outbox Pattern

**Содержимое:**
```python
from enum import Enum
from sqlalchemy import Column, String, BigInteger, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM as PG_ENUM
from sqlalchemy.sql import func
from app.db.base import Base


class OutboxStatus(str, Enum):
    """Outbox event status"""
    PENDING = "pending"
    PUBLISHED = "published"


class Outbox(Base):
    """Outbox event model for guaranteed message delivery"""
    __tablename__ = "outbox"
    
    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )
    aggregate_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True
    )
    event_type = Column(
        String(100),
        nullable=False
    )
    payload = Column(
        JSONB,
        nullable=False
    )
    status = Column(
        PG_ENUM(OutboxStatus, name="outbox_status", create_type=False),
        nullable=False,
        default=OutboxStatus.PENDING,
        server_default="pending"
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )
    published_at = Column(
        DateTime(timezone=True),
        nullable=True
    )
    
    def __repr__(self) -> str:
        return f"<Outbox(id={self.id}, event_type={self.event_type}, status={self.status})>"
```

**Детали реализации:**
- BigInteger для id (автоинкремент)
- UUID для aggregate_id (ссылка на Payment)
- JSONB для payload
- ENUM для status
- Индекс на aggregate_id для быстрого поиска событий платежа

**Ссылки на дизайн:**
- Схема: `../06-models.md` (Outbox)
- Паттерн: `../03-decisions.md` (ADR-01 Outbox Pattern)

### `alembic.ini`

**Назначение:** Конфигурация Alembic для миграций

**Содержимое:**
```ini
[alembic]
script_location = alembic
prepend_sys_path = .
version_path_separator = os

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

### `alembic/env.py`

**Назначение:** Alembic environment для async миграций

**Содержимое:**
```python
import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
from app.config import settings
from app.db.base import Base
from app.models import payment, outbox  # Import all models

# Alembic Config object
config = context.config

# Override sqlalchemy.url from settings
config.set_main_option("sqlalchemy.url", settings.database_url)

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode (async)."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

**Детали:**
- Поддержка async миграций
- Автоматическое использование DATABASE_URL из settings
- Импорт всех моделей для autogenerate

### `alembic/versions/001_create_tables.py`

**Назначение:** Миграция для создания таблиц payments и outbox

**Содержимое:**
```python
"""Create payments and outbox tables

Revision ID: 001
Revises: 
Create Date: 2026-04-20 10:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enums
    op.execute("CREATE TYPE payment_status AS ENUM ('pending', 'succeeded', 'failed')")
    op.execute("CREATE TYPE currency AS ENUM ('RUB', 'USD', 'EUR')")
    op.execute("CREATE TYPE outbox_status AS ENUM ('pending', 'published')")
    
    # Create payments table
    op.create_table(
        'payments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('currency', postgresql.ENUM('RUB', 'USD', 'EUR', name='currency'), nullable=False),
        sa.Column('description', sa.String(500), nullable=False),
        sa.Column('metadata', postgresql.JSONB, nullable=False, server_default='{}'),
        sa.Column('status', postgresql.ENUM('pending', 'succeeded', 'failed', name='payment_status'), nullable=False, server_default='pending'),
        sa.Column('idempotency_key', sa.String(255), nullable=False, unique=True),
        sa.Column('webhook_url', sa.String(2048), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('amount > 0', name='check_amount_positive')
    )
    
    # Create indexes for payments
    op.create_index('idx_payment_idempotency_key', 'payments', ['idempotency_key'], unique=True)
    op.create_index('idx_payment_status', 'payments', ['status'])
    op.create_index('idx_payment_created_at', 'payments', [sa.text('created_at DESC')])
    
    # Create outbox table
    op.create_table(
        'outbox',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('aggregate_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('payload', postgresql.JSONB, nullable=False),
        sa.Column('status', postgresql.ENUM('pending', 'published', name='outbox_status'), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True)
    )
    
    # Create indexes for outbox
    op.create_index('idx_outbox_status', 'outbox', ['status'], postgresql_where=sa.text("status = 'pending'"))
    op.create_index('idx_outbox_created_at', 'outbox', [sa.text('created_at DESC')])
    op.create_index('idx_outbox_aggregate_id', 'outbox', ['aggregate_id'])


def downgrade() -> None:
    op.drop_table('outbox')
    op.drop_table('payments')
    op.execute('DROP TYPE outbox_status')
    op.execute('DROP TYPE currency')
    op.execute('DROP TYPE payment_status')
```

**Детали:**
- Создание ENUM типов перед таблицами
- Все индексы из дизайна (`../06-models.md`)
- Partial index для outbox.status (только pending)
- Downgrade для отката миграции

**Ссылки на дизайн:**
- Полная схема: `../06-models.md`

### `app/__init__.py`

**Назначение:** Пустой файл для Python package

**Содержимое:** (пустой файл)

### `app/models/__init__.py`

**Назначение:** Экспорт моделей

**Содержимое:**
```python
from app.models.payment import Payment, PaymentStatus, Currency
from app.models.outbox import Outbox, OutboxStatus

__all__ = [
    "Payment",
    "PaymentStatus",
    "Currency",
    "Outbox",
    "OutboxStatus",
]
```

### `app/db/__init__.py`

**Назначение:** Экспорт database utilities

**Содержимое:**
```python
from app.db.base import Base
from app.db.session import engine, AsyncSessionLocal, get_db

__all__ = [
    "Base",
    "engine",
    "AsyncSessionLocal",
    "get_db",
]
```

### `.env.example`

**Назначение:** Пример файла с переменными окружения

**Содержимое:**
```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/payments

# RabbitMQ
RABBITMQ_URL=amqp://guest:guest@localhost:5672/

# API
API_KEY=change-me-in-production
API_HOST=0.0.0.0
API_PORT=8000

# Outbox Publisher
OUTBOX_PUBLISH_INTERVAL=5
OUTBOX_BATCH_SIZE=100

# Logging
LOG_LEVEL=INFO
```

## Команды для выполнения

```bash
# 1. Установить зависимости
poetry install

# 2. Создать .env файл
cp .env.example .env

# 3. Запустить PostgreSQL (через Docker)
docker run -d \
  --name payment-postgres \
  -e POSTGRES_USER=user \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=payments \
  -p 5432:5432 \
  postgres:16

# 4. Применить миграции
alembic upgrade head

# 5. Проверить таблицы в БД
psql postgresql://user:password@localhost:5432/payments -c "\dt"
```

## Определение готовности

- [ ] Все файлы созданы согласно списку выше
- [ ] `poetry install` выполняется без ошибок
- [ ] `alembic upgrade head` создаёт таблицы payments и outbox
- [ ] В БД созданы ENUM типы: payment_status, currency, outbox_status
- [ ] В БД созданы все индексы из дизайна
- [ ] Можно импортировать модели: `from app.models import Payment, Outbox`
- [ ] Можно создать async session: `from app.db import get_db`
- [ ] Ruff проверка проходит: `ruff check app/`
- [ ] MyPy проверка проходит: `mypy app/`

## Проверка результата

```python
# test_phase_01.py
import asyncio
from app.db import AsyncSessionLocal
from app.models import Payment, Outbox, PaymentStatus, Currency
from decimal import Decimal
import uuid

async def test_models():
    async with AsyncSessionLocal() as session:
        # Создать платёж
        payment = Payment(
            id=uuid.uuid4(),
            amount=Decimal("100.50"),
            currency=Currency.RUB,
            description="Test payment",
            metadata={"test": True},
            status=PaymentStatus.PENDING,
            idempotency_key=str(uuid.uuid4()),
            webhook_url="https://example.com/webhook"
        )
        session.add(payment)
        await session.commit()
        
        print(f"✓ Payment created: {payment.id}")
        
        # Создать outbox событие
        outbox = Outbox(
            aggregate_id=payment.id,
            event_type="payment.created",
            payload={"payment_id": str(payment.id)}
        )
        session.add(outbox)
        await session.commit()
        
        print(f"✓ Outbox event created: {outbox.id}")

if __name__ == "__main__":
    asyncio.run(test_models())
```

Запустить: `python test_phase_01.py`

Ожидаемый результат:
```
✓ Payment created: 550e8400-e29b-41d4-a716-446655440000
✓ Outbox event created: 1
```
