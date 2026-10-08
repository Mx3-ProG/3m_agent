import hmac

from fastapi import Header, HTTPException, status

from backend.app.core.config import get_settings


async def require_api_token(x_3m_token: str | None = Header(default=None)) -> None:
    expected = get_settings().api_token
    if not x_3m_token or not hmac.compare_digest(x_3m_token, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Jeton API invalide")
