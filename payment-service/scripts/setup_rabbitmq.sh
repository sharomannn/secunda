#!/bin/bash
set -e

echo "Setting up RabbitMQ for payment service..."

# Wait for RabbitMQ to be ready
echo "Waiting for RabbitMQ..."
sleep 5

# Create exchange
rabbitmqadmin declare exchange \
  name=payments \
  type=topic \
  durable=true

echo "✓ Exchange 'payments' created"

# Create main queue
rabbitmqadmin declare queue \
  name=payments.new \
  durable=true \
  arguments='{"x-dead-letter-exchange":"payments.dlx","x-dead-letter-routing-key":"dlq"}'

echo "✓ Queue 'payments.new' created with DLQ config"

# Create DLX (Dead Letter Exchange)
rabbitmqadmin declare exchange \
  name=payments.dlx \
  type=fanout \
  durable=true

echo "✓ DLX 'payments.dlx' created"

# Create DLQ
rabbitmqadmin declare queue \
  name=payments.new.dlq \
  durable=true \
  arguments='{"x-message-ttl":604800000}'  # 7 days TTL

echo "✓ DLQ 'payments.new.dlq' created with 7 days TTL"

# Bind main queue to exchange
rabbitmqadmin declare binding \
  source=payments \
  destination=payments.new \
  routing_key=payment.created

echo "✓ Binding 'payments.new' to 'payments' exchange"

# Bind DLQ to DLX
rabbitmqadmin declare binding \
  source=payments.dlx \
  destination=payments.new.dlq \
  routing_key=dlq

echo "✓ Binding 'payments.new.dlq' to 'payments.dlx'"

echo ""
echo "✅ RabbitMQ setup complete!"
echo ""
echo "Queues:"
echo "  - payments.new (main queue)"
echo "  - payments.new.dlq (dead letter queue, 7 days TTL)"
echo ""
echo "Exchanges:"
echo "  - payments (topic)"
echo "  - payments.dlx (fanout, for DLQ)"
