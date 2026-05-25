import secrets
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from backend.core.config import settings

# --- Rate Limiting ---
# Initialize slowapi Limiter using client IP address
limiter = Limiter(key_func=get_remote_address, default_limits=[settings.RATE_LIMIT_DEFAULT])

# --- API Key Authentication ---
# The API key is optional in the codebase. If API_KEY is set in the environment,
# we enforce it via the X-API-Key header to secure endpoints.
# If not set, it allows public usage (for local deployments or UI demos).
# No hardcoded keys are stored here.
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key_header: str = Security(api_key_header)):
    """
    Dependency to verify API Key.
    Follows OWASP best practices:
    - Uses constant-time comparison to prevent timing attacks.
    - Keys are managed via environment variables (not hardcoded).
    """
    if not settings.API_KEY:
        # If no API key is configured on the server, we assume public access is allowed
        return None
        
    if not api_key_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key is missing",
        )
        
    # Constant-time comparison to protect against timing attacks
    if not secrets.compare_digest(api_key_header, settings.API_KEY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API Key",
        )
        
    return api_key_header
