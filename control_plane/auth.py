from fastapi import Security, HTTPException, Depends
from fastapi.security.api_key import APIKeyHeader
from control_plane.db import get_api_key_owner
from typing import Optional

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def get_current_user(api_key: str = Security(api_key_header)) -> str:
    """Validates X-API-Key header and returns the owner's address/ID."""
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    owner = get_api_key_owner(api_key)
    if not owner:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return owner
