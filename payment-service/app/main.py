from typing import Any, Dict
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.openapi.utils import get_openapi
from app.config import settings
from app.middleware import APIKeyMiddleware
from app.api.v1 import payments

# Create FastAPI app
app = FastAPI(
    title="Payment Processing Service",
    description="Async payment processing microservice with guaranteed delivery",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add middleware
app.add_middleware(APIKeyMiddleware)

# Include routers
app.include_router(payments.router, prefix="/api/v1")


def custom_openapi() -> Dict[str, Any]:
    """
    Кастомная OpenAPI схема с поддержкой X-API-Key в Swagger UI
    
    Добавляет security scheme для APIKeyHeader, чтобы в Swagger UI
    появилась кнопка "Authorize" для ввода API ключа.
    """
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    
    # Добавить security scheme для X-API-Key
    openapi_schema["components"]["securitySchemes"] = {
        "APIKeyHeader": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "Static API key for authentication. Use value from API_KEY env variable."
        }
    }
    
    # Применить security ко всем операциям кроме /health
    for path_name, path_item in openapi_schema["paths"].items():
        # Пропустить /health (не требует auth согласно middleware)
        if path_name == "/health":
            continue
            
        for operation in path_item.values():
            if isinstance(operation, dict) and "operationId" in operation:
                operation["security"] = [{"APIKeyHeader": []}]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema


# Переопределить метод openapi
app.openapi = custom_openapi  # type: ignore[method-assign]


@app.get("/health", tags=["health"])
async def health_check() -> JSONResponse:
    """Health check endpoint"""
    return JSONResponse(
        content={
            "status": "healthy",
            "service": "payment-processing"
        }
    )


@app.get("/", include_in_schema=False)
async def root() -> JSONResponse:
    """Root endpoint redirect to docs"""
    return JSONResponse(
        content={
            "message": "Payment Processing Service",
            "docs": "/docs",
            "health": "/health"
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
