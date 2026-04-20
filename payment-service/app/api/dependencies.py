from typing import Annotated
from fastapi import Header, HTTPException, status


async def get_idempotency_key(
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")]
) -> str:
    """
    Dependency to extract and validate Idempotency-Key header
    
    Args:
        idempotency_key: Value from Idempotency-Key header
        
    Returns:
        Validated idempotency key
        
    Raises:
        HTTPException: If header is missing or empty
    """
    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Idempotency-Key header is required and must not be empty"
        )
    
    return idempotency_key.strip()
