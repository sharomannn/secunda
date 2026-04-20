from fastapi import FastAPI
from fastapi.responses import JSONResponse
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
