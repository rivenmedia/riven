from typing import Optional

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from program.settings.manager import settings_manager


def header_auth(header = Security(APIKeyHeader(name="x-api-key", auto_error=False))):
    return header == settings_manager.settings.api_key

def bearer_auth(bearer: HTTPAuthorizationCredentials = Security(HTTPBearer(auto_error=False))):
    return bearer and bearer.credentials == settings_manager.settings.api_key

def resolve_api_key(
    header: Optional[str] = Security(header_auth),
    bearer: Optional[HTTPAuthorizationCredentials] = Security(bearer_auth)
):
    if not (header or bearer):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )