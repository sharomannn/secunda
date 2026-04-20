import uuid
from httpx import AsyncClient


class TestCreatePaymentEndpoint:
    """Tests for POST /api/v1/payments"""
    
    async def test_create_payment_returns_202_accepted(self, client: AsyncClient, api_key: str):
        """Test creating payment returns 202"""
        response = await client.post(
            "/api/v1/payments",
            headers={
                "X-API-Key": api_key,
                "Idempotency-Key": str(uuid.uuid4())
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
        assert "id" in data
        assert data["status"] == "pending"
    
    async def test_create_payment_without_api_key_returns_401(self, client: AsyncClient):
        """Test auth: no API key returns 401"""
        response = await client.post(
            "/api/v1/payments",
            headers={"Idempotency-Key": str(uuid.uuid4())},
            json={}
        )
        
        assert response.status_code == 401
    
    async def test_create_payment_with_negative_amount_returns_422(
        self, client: AsyncClient, api_key: str
    ):
        """Test validation: negative amount returns 422"""
        response = await client.post(
            "/api/v1/payments",
            headers={
                "X-API-Key": api_key,
                "Idempotency-Key": str(uuid.uuid4())
            },
            json={
                "amount": "-10.00",
                "currency": "RUB",
                "description": "Test",
                "metadata": {},
                "webhook_url": "https://example.com/webhook"
            }
        )
        
        assert response.status_code == 422


class TestGetPaymentEndpoint:
    """Tests for GET /api/v1/payments/{id}"""
    
    async def test_get_payment_returns_200_with_payment_data(
        self, client: AsyncClient, api_key: str, db_session, payment_factory
    ):
        """Test getting payment returns 200"""
        payment = await payment_factory()
        
        response = await client.get(
            f"/api/v1/payments/{payment.id}",
            headers={"X-API-Key": api_key}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(payment.id)
    
    async def test_get_payment_not_found_returns_404(
        self, client: AsyncClient, api_key: str
    ):
        """Test getting non-existent payment returns 404"""
        response = await client.get(
            f"/api/v1/payments/{uuid.uuid4()}",
            headers={"X-API-Key": api_key}
        )
        
        assert response.status_code == 404
