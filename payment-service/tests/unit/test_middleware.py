from unittest.mock import AsyncMock, MagicMock
from fastapi import Request
from starlette.responses import JSONResponse
from app.middleware.auth import APIKeyMiddleware
from app.config import settings


class TestAPIKeyMiddleware:
    """Tests for APIKeyMiddleware"""
    
    async def test_valid_api_key_passes(self):
        """Test valid API key allows request"""
        middleware = APIKeyMiddleware(app=MagicMock())
        
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/payments"
        request.headers.get.return_value = settings.api_key
        
        call_next = AsyncMock(return_value=JSONResponse(content={"status": "ok"}))
        
        response = await middleware.dispatch(request, call_next)
        
        assert response.status_code == 200
        call_next.assert_called_once_with(request)
    
    async def test_invalid_api_key_returns_401(self):
        """Test invalid API key returns 401"""
        middleware = APIKeyMiddleware(app=MagicMock())
        
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/payments"
        request.headers.get.return_value = "invalid-key"
        
        call_next = AsyncMock()
        
        response = await middleware.dispatch(request, call_next)
        
        assert response.status_code == 401
        assert response.body == b'{"detail":"Invalid API key"}'
        call_next.assert_not_called()
    
    async def test_missing_api_key_returns_401(self):
        """Test missing API key returns 401"""
        middleware = APIKeyMiddleware(app=MagicMock())
        
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/payments"
        request.headers.get.return_value = None
        
        call_next = AsyncMock()
        
        response = await middleware.dispatch(request, call_next)
        
        assert response.status_code == 401
        assert response.body == b'{"detail":"X-API-Key header is required"}'
        call_next.assert_not_called()
    
    async def test_public_endpoints_skip_auth(self):
        """Test public endpoints skip authentication"""
        middleware = APIKeyMiddleware(app=MagicMock())
        
        public_paths = ["/docs", "/redoc", "/openapi.json", "/health", "/"]
        
        for path in public_paths:
            request = MagicMock(spec=Request)
            request.url.path = path
            
            call_next = AsyncMock(return_value=JSONResponse(content={"status": "ok"}))
            
            response = await middleware.dispatch(request, call_next)
            
            assert response.status_code == 200
            call_next.assert_called_once_with(request)
            call_next.reset_mock()
