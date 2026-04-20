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
