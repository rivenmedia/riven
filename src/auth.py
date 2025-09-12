from typing import Annotated, Optional

from fastapi import HTTPException, Query, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from program.settings.manager import settings_manager

# Module-level instances to avoid B008 linting errors
_api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)
_http_bearer = HTTPBearer(auto_error=False)
_api_key_header_security = Security(_api_key_header)
_http_bearer_security = Security(_http_bearer)


def header_auth(header: Optional[str] = _api_key_header_security):
    return header == settings_manager.settings.api_key

def bearer_auth(bearer: Optional[HTTPAuthorizationCredentials] = _http_bearer_security):
    return bearer and bearer.credentials == settings_manager.settings.api_key

# Create Security dependencies at module level
_header_security = Security(header_auth)
_bearer_security = Security(bearer_auth)

def resolve_api_key(
    header: Optional[str] = _header_security,
    bearer: Optional[HTTPAuthorizationCredentials] = _bearer_security
):
    if not (header or bearer):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )

def resolve_ws_api_key(
    api_key: Annotated[str | None, Query()] = None
):
    if not (api_key and api_key == settings_manager.settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )