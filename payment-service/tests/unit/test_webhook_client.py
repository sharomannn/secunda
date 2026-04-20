import pytest
from unittest.mock import AsyncMock, patch
import httpx
from app.services.webhook_client import WebhookClient, WebhookClientError, WebhookDeliveryError


class TestWebhookClient:
    """Tests for WebhookClient"""
    
    @pytest.fixture
    def webhook_client(self):
        """Create WebhookClient instance"""
        return WebhookClient()
    
    @pytest.fixture
    def payment_payload(self):
        """Sample payment payload"""
        return {
            "payment_id": "550e8400-e29b-41d4-a716-446655440000",
            "status": "succeeded",
            "amount": "100.50",
            "currency": "RUB",
        }
    
    @patch('httpx.AsyncClient.post')
    async def test_send_webhook_success(self, mock_post, webhook_client, payment_payload):
        """Test successful webhook delivery"""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        await webhook_client.send_webhook(
            url="https://example.com/webhook",
            payload=payment_payload,
        )
        
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "https://example.com/webhook"
        assert call_args[1]["json"] == payment_payload
    
    @patch('httpx.AsyncClient.post')
    async def test_send_webhook_retry_on_failure(self, mock_post, webhook_client, payment_payload):
        """Test webhook retry on 5xx failure"""
        mock_response_fail = AsyncMock()
        mock_response_fail.status_code = 500
        
        mock_response_success = AsyncMock()
        mock_response_success.status_code = 200
        
        mock_post.side_effect = [mock_response_fail, mock_response_success]
        
        await webhook_client.send_webhook(
            url="https://example.com/webhook",
            payload=payment_payload,
        )
        
        assert mock_post.call_count == 2
    
    @patch('httpx.AsyncClient.post')
    async def test_send_webhook_max_retries_exceeded(self, mock_post, webhook_client, payment_payload):
        """Test webhook fails after max retries"""
        mock_response = AsyncMock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response
        
        with pytest.raises(WebhookDeliveryError):
            await webhook_client.send_webhook(
                url="https://example.com/webhook",
                payload=payment_payload,
            )
        
        assert mock_post.call_count == 3
    
    @patch('httpx.AsyncClient.post')
    async def test_send_webhook_timeout(self, mock_post, webhook_client, payment_payload):
        """Test webhook timeout handling"""
        mock_post.side_effect = httpx.TimeoutException("Timeout")
        
        with pytest.raises(WebhookDeliveryError):
            await webhook_client.send_webhook(
                url="https://example.com/webhook",
                payload=payment_payload,
            )
        
        assert mock_post.call_count == 3
    
    async def test_send_webhook_invalid_url(self, webhook_client, payment_payload):
        """Test webhook with invalid URL"""
        with pytest.raises(WebhookClientError):
            await webhook_client.send_webhook(
                url="ftp://invalid-scheme.com",
                payload=payment_payload,
            )
    
    @patch('httpx.AsyncClient.post')
    async def test_send_webhook_connection_error(self, mock_post, webhook_client, payment_payload):
        """Test webhook connection error"""
        mock_post.side_effect = httpx.ConnectError("Connection failed")
        
        with pytest.raises(WebhookDeliveryError):
            await webhook_client.send_webhook(
                url="https://example.com/webhook",
                payload=payment_payload,
            )
        
        assert mock_post.call_count == 3

