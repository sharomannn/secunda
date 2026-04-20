from typing import Callable, Awaitable
from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse
from app.config import settings


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Middleware to validate X-API-Key header"""
    
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Skip auth for docs endpoints
        if request.url.path in ["/docs", "/redoc", "/openapi.json", "/health", "/"]:
            return await call_next(request)
        
        # Check X-API-Key header
        api_key = request.headers.get("X-API-Key")
        
        if not api_key:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "X-API-Key header is required"}
            )
        
        if api_key != settings.api_key:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid API key"}
            )
        
        # Continue to endpoint
        response = await call_next(request)
        return response
