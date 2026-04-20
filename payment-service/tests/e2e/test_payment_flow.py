import pytest
import uuid
from httpx import AsyncClient


class TestFullPaymentFlow:
    """E2E tests for complete payment flow"""
    
    @pytest.mark.asyncio
    async def test_full_payment_flow_success(self, client: AsyncClient, api_key: str):
        """Test full flow: create → verify created"""
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
        
        # 2. Verify payment was created
        response = await client.get(
            f"/api/v1/payments/{payment_id}",
            headers={"X-API-Key": api_key}
        )
        
        assert response.status_code == 200
        payment = response.json()
        assert payment["status"] == "pending"
        assert payment["amount"] == "100.50"
        assert payment["metadata"] == {"test": "e2e"}
    
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
