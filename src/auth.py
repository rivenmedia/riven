from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader
from program.settings.manager import settings_manager

api_key_header =  APIKeyHeader(name="x-api-key")

def resolve_api_key(api_key_header: str = Security(api_key_header)):
    if api_key_header == settings_manager.settings.api_key:
        return True
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key"
        )