#!/bin/bash
set -e

echo "🧪 Running E2E test..."
echo ""

API_BASE="http://localhost:8000/api/v1"
API_KEY="change-me-in-production"

# Generate unique idempotency key
IDEMPOTENCY_KEY=$(uuidgen)

echo "1️⃣  Creating payment..."
RESPONSE=$(curl -s -X POST "$API_BASE/payments" \
  -H "X-API-Key: $API_KEY" \
  -H "Idempotency-Key: $IDEMPOTENCY_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "100.50",
    "currency": "RUB",
    "description": "E2E test payment",
    "metadata": {"test": "e2e"},
    "webhook_url": "https://webhook.site/test"
  }')

PAYMENT_ID=$(echo $RESPONSE | jq -r '.id')
STATUS=$(echo $RESPONSE | jq -r '.status')

if [ "$PAYMENT_ID" == "null" ]; then
    echo "❌ Failed to create payment"
    echo "Response: $RESPONSE"
    exit 1
fi

echo "   ✓ Payment created: $PAYMENT_ID"
echo "   ✓ Status: $STATUS"

echo ""
echo "2️⃣  Waiting for async processing (10 seconds)..."
sleep 10

echo ""
echo "3️⃣  Checking payment status..."
RESPONSE=$(curl -s "$API_BASE/payments/$PAYMENT_ID" \
  -H "X-API-Key: $API_KEY")

FINAL_STATUS=$(echo $RESPONSE | jq -r '.status')
PROCESSED_AT=$(echo $RESPONSE | jq -r '.processed_at')

echo "   ✓ Final status: $FINAL_STATUS"
echo "   ✓ Processed at: $PROCESSED_AT"

if [ "$FINAL_STATUS" == "pending" ]; then
    echo "❌ Payment still pending (processing failed or too slow)"
    exit 1
fi

if [ "$PROCESSED_AT" == "null" ]; then
    echo "❌ processed_at is null"
    exit 1
fi

echo ""
echo "4️⃣  Testing idempotency..."
RESPONSE=$(curl -s -X POST "$API_BASE/payments" \
  -H "X-API-Key: $API_KEY" \
  -H "Idempotency-Key: $IDEMPOTENCY_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "999.99",
    "currency": "USD",
    "description": "Different payment",
    "metadata": {},
    "webhook_url": "https://other.com/webhook"
  }')

SAME_PAYMENT_ID=$(echo $RESPONSE | jq -r '.id')

if [ "$SAME_PAYMENT_ID" != "$PAYMENT_ID" ]; then
    echo "❌ Idempotency failed: got different payment ID"
    exit 1
fi

echo "   ✓ Idempotency works: returned same payment"

echo ""
echo "✅ E2E test passed!"
