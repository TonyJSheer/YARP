import logging
import os

import jwt
from fastapi import HTTPException, Request

from app.config import settings

logger = logging.getLogger(__name__)

if not settings.jwt_secret:
    logger.warning("JWT_SECRET is not set — all authenticated requests will fail")


class AuthError(Exception):
    pass


def decode_token(token: str) -> str:
    """Decode JWT and return account_id (sub claim). Raises AuthError on failure."""
    try:
        payload: dict[str, object] = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        account_id = payload.get("sub")
        if not account_id or not isinstance(account_id, str):
            raise AuthError("Token missing 'sub' claim")
        return account_id
    except jwt.ExpiredSignatureError:
        raise AuthError("token_expired")
    except jwt.InvalidTokenError as e:
        raise AuthError(f"invalid_token: {e}")


def get_current_account_id(request: Request) -> str:
    """FastAPI dependency. Extracts + validates Bearer token."""
    token: str | None = None

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
    elif env_token := os.getenv("MCP_AUTH_TOKEN"):
        token = env_token

    if not token:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "unauthorized",
                    "message": "Missing auth token",
                    "field": None,
                }
            },
        )

    try:
        return decode_token(token)
    except AuthError as e:
        code = "token_expired" if "token_expired" in str(e) else "invalid_token"
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": code, "message": str(e), "field": None}},
        )
