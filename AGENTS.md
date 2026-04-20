# AGENTS.md

## Project Overview

Payment processing microservice built with **FastAPI + SQLAlchemy 2.0 async + RabbitMQ + PostgreSQL**. Implementation follows a **6-phase plan** in `docs/payment-processing/plan/`.

**Current status:** Phase 1 complete (infrastructure and models). Phases 2-6 pending.

## Repository Structure

```
payment-service/          # FastAPI microservice (only service in repo)
├── app/
│   ├── models/          # SQLAlchemy 2.0 async models (Payment, Outbox)
│   ├── db/              # Async session factory, Base
│   ├── config.py        # pydantic-settings for env vars
│   └── [future: repositories/, services/, api/, consumer/, tasks/]
├── alembic/             # Database migrations
│   └── versions/001_create_tables.py
├── pyproject.toml       # Poetry deps, ruff/mypy config
└── .env.example         # Required env vars template

docs/payment-processing/  # Complete design docs (read before coding)
├── README.md            # Business requirements, acceptance criteria
├── 01-architecture.md   # C4 diagrams, component structure
├── 02-behavior.md       # Sequence diagrams for all use cases
├── 03-decisions.md      # ADRs (Outbox pattern, idempotency, etc.)
├── 06-models.md         # Full DB schema, indexes, constraints
├── 08-api-contract.md   # REST API spec, webhook format
└── plan/
    ├── README.md        # 6-phase implementation plan, file map
    └── phase-01..06.md  # Detailed specs per phase
```

## Critical Commands

**Working directory:** Always `cd payment-service/` first.

```bash
# Setup (first time)
poetry config virtualenvs.in-project true  # Create .venv in project dir
poetry install

# Linting and type checking (run before commit)
poetry run ruff check app/
poetry run mypy app/

# Database migrations
alembic upgrade head              # Apply migrations
alembic revision --autogenerate   # Generate new migration

# Tests (when implemented in Phase 6)
poetry run pytest                 # All tests
poetry run pytest tests/unit/     # Unit only
poetry run pytest --cov=app       # With coverage
```

## Architecture Constraints (from ADRs)

**Must follow these patterns:**

1. **Outbox Pattern** (ADR-01): Payment + Outbox event written in same transaction. Never publish to RabbitMQ directly from API.

2. **Idempotency** (ADR-02): All POST endpoints require `Idempotency-Key` header. Check DB before creating resources.

3. **SQLAlchemy 2.0 async** (ADR-06):
   - Use `AsyncSession`, `async_sessionmaker`, `create_async_engine`
   - All ORM operations must use `await`
   - Models use `DeclarativeBase`

4. **Data types** (ADR-08, ADR-09, ADR-10):
   - Payment IDs: `UUID` (postgresql.UUID(as_uuid=True))
   - Money amounts: `Numeric(10, 2)` → Python `Decimal`
   - Enums: PostgreSQL ENUM types (payment_status, currency, outbox_status)

5. **Layer separation**:
   - Models: SQLAlchemy only, no business logic
   - Repositories: ORM operations only
   - Services: Business logic, orchestration
   - API: FastAPI routers, validation via Pydantic

6. **Code language**: All comments, docstrings, and inline documentation must be in Russian. Code identifiers (variables, functions, classes) remain in English.

## Phase Implementation Workflow

**Read phase spec completely before coding.** Each `phase-NN.md` contains:
- Full file contents to create/modify
- Business rules to implement
- Verification criteria
- Links to relevant design docs

**Phase dependencies:**
- Phase 1 ✅ (infrastructure, models)
- Phase 2 → depends on Phase 1 (repositories, services)
- Phase 3 → depends on Phase 2 (API layer)
- Phase 4 → depends on Phase 2 (async consumer, webhook)
- Phase 5 → depends on Phase 3+4 (Docker, integration)
- Phase 6 → depends on all (tests)

**Verification order per phase:**
1. `ruff check app/` (must pass)
2. `mypy app/` (must pass)
3. Run phase-specific checks from `phase-NN.md`

## Environment Setup

Copy `.env.example` to `.env` and adjust:
- `DATABASE_URL`: PostgreSQL connection (asyncpg driver required)
- `RABBITMQ_URL`: RabbitMQ connection
- `API_KEY`: Static key for X-API-Key auth

**PostgreSQL must be running** before applying migrations or running app.

## Common Pitfalls

1. **Virtual environment**: Poetry creates `.venv/` in project directory (configured via `virtualenvs.in-project = true`). System uses Python 3.14.3, project requires `^3.11` (compatible).

2. **SQLAlchemy reserved words**: `metadata` field in Payment model is aliased as `metadata_` to avoid conflicts. Use `mapped_column(name="metadata")`.

3. **ENUM creation**: Create PostgreSQL ENUM types in migration with `op.execute("CREATE TYPE ...")` before creating tables. In models, use `create_type=False` parameter.

4. **Partial indexes**: Outbox table has `WHERE status='pending'` partial index. Use `postgresql_where=sa.text("status = 'pending'")` in migration.

5. **Async context**: Always use `async with AsyncSessionLocal() as session:` for DB operations. FastAPI dependency `get_db()` handles this automatically.

6. **Poetry package mode**: `pyproject.toml` has `package-mode = false` because this is an application, not a library.

## Design Docs Priority

When implementing a feature, read in this order:
1. `plan/phase-NN.md` for the current phase (has exact file contents)
2. `06-models.md` for DB schema details
3. `02-behavior.md` for sequence diagrams (happy + error paths)
4. `08-api-contract.md` for API contracts
5. `03-decisions.md` for architectural constraints

All docs are in Russian. Design is complete and approved (`status: approved` in plan).

## Testing Strategy (Phase 6)

- Unit tests: Mock repositories, test services in isolation
- Integration tests: Real DB (testcontainers), test repositories + services
- E2E tests: Full stack with Docker Compose

**No tests exist yet.** Phase 6 will add full test suite with ≥95% coverage target.

## Git Commit Standards

**All commits must be in Russian and follow Conventional Commits format:**

```
<тип>(<область>): краткое описание

Детали изменений (опционально)
```

**Типы коммитов:**
- `feat` — новая функциональность
- `fix` — исправление бага
- `refactor` — рефакторинг без изменения поведения
- `docs` — изменения в документации
- `test` — добавление/обновление тестов
- `chore` — инфраструктура, конфиг, зависимости

**Примеры:**
- `feat(payment-service): добавить модели Payment и Outbox`
- `fix(api): исправить валидацию idempotency_key`
- `refactor(services): упростить логику PaymentService`
- `test(repositories): добавить тесты для PaymentRepository`

**Правила:**
- Краткое описание: до 72 символов
- Без точки в конце
- Используйте повелительное наклонение ("добавить", не "добавил")
- Область в скобках: payment-service, api, models, services, tests
