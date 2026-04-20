#!/bin/bash
set -e

echo "🚀 Инициализация Payment Processing Service..."
echo ""

# Проверка что Docker запущен
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker не запущен. Пожалуйста, запустите Docker сначала."
    exit 1
fi

echo "1️⃣  Сборка Docker образов..."
docker-compose build

echo ""
echo "2️⃣  Запуск инфраструктуры (PostgreSQL, RabbitMQ)..."
docker-compose up -d postgres rabbitmq

echo ""
echo "3️⃣  Ожидание готовности сервисов..."
sleep 10

# Ожидание PostgreSQL
echo "   Ожидание PostgreSQL..."
until docker-compose exec -T postgres pg_isready -U user -d payments > /dev/null 2>&1; do
    sleep 1
done
echo "   ✓ PostgreSQL готов"

# Ожидание RabbitMQ
echo "   Ожидание RabbitMQ..."
until docker-compose exec -T rabbitmq rabbitmq-diagnostics ping > /dev/null 2>&1; do
    sleep 1
done
echo "   ✓ RabbitMQ готов"

echo ""
echo "4️⃣  Применение миграций базы данных..."
docker-compose run --rm api alembic upgrade head

echo ""
echo "5️⃣  Настройка RabbitMQ очередей..."
docker-compose exec -T rabbitmq bash << 'EOF'
rabbitmqadmin declare exchange name=payments type=topic durable=true
rabbitmqadmin declare queue name=payments.new durable=true arguments='{"x-dead-letter-exchange":"payments.dlx","x-dead-letter-routing-key":"dlq"}'
rabbitmqadmin declare exchange name=payments.dlx type=fanout durable=true
rabbitmqadmin declare queue name=payments.new.dlq durable=true arguments='{"x-message-ttl":604800000}'
rabbitmqadmin declare binding source=payments destination=payments.new routing_key=payment.created
rabbitmqadmin declare binding source=payments.dlx destination=payments.new.dlq routing_key=dlq
EOF

echo ""
echo "6️⃣  Запуск всех сервисов..."
docker-compose up -d

echo ""
echo "✅ Инициализация завершена!"
echo ""
echo "📊 Сервисы:"
echo "   API:              http://localhost:8000"
echo "   API Docs:         http://localhost:8000/docs"
echo "   Health Check:     http://localhost:8000/health"
echo "   RabbitMQ UI:      http://localhost:15672 (guest/guest)"
echo ""
echo "📝 Логи:"
echo "   Все сервисы:      docker-compose logs -f"
echo "   API:              docker-compose logs -f api"
echo "   Consumer:         docker-compose logs -f consumer"
echo "   Outbox:           docker-compose logs -f outbox-publisher"
echo ""
echo "🛑 Остановка:        docker-compose down"
echo "🗑️  Очистка данных:   ./scripts/clean.sh"
