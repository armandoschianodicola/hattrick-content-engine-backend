import secrets

from fastapi import Depends
from fastapi.security import APIKeyHeader

from hattrick_backend.core.config import Settings, get_settings
from hattrick_backend.core.exceptions import AppError

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_admin(
    key: str | None = Depends(api_key_header), settings: Settings = Depends(get_settings)
) -> str:
    if not key or not secrets.compare_digest(
        key.encode("utf-8"), settings.api_key.get_secret_value().encode("utf-8")
    ):
        raise AppError("unauthorized", "A valid X-API-Key is required", 401)
    # Single shared credential: no claim of individual user attribution.
    return "api-key-admin"
