# Task P2-02 — Auth Service (JWT Bearer → account_id)

**Type**: `feature`

**Summary**: Implement a JWT-based auth service that decodes a Bearer token and returns the `account_id`. Wire it into the FastAPI router as a dependency and into the MCP server as a token validator. Replace the `"dev"` placeholder from P2-01.

**Depends on**: P2-01

---

## Context

**Background**: The system needs to know *who* is calling in order to scope data. JWTs are chosen because they are stateless (no DB lookup), easy to generate for each tenant, and supported natively by both HTTP Bearer and MCP env var patterns. This task also establishes the `get_current_account_id` FastAPI dependency that all auth-protected routes will use.

**Affected components**:
- [x] Backend API (new auth dependency)
- [x] New service module: `app/services/auth.py`
- [x] Config (new JWT env vars)
- [x] Routers (replace dev placeholder)

---

## Requirements

**Functional**:
- `app/services/auth.py` provides:
  - `decode_token(token: str) -> str` — verifies JWT signature, extracts `sub` as `account_id`, raises `AuthError` on invalid/expired token
  - `get_current_account_id(request: Request) -> str` — FastAPI dependency; extracts Bearer token from `Authorization` header, falls back to `MCP_AUTH_TOKEN` env var (for stdio MCP), calls `decode_token`
- Invalid or missing token → `401 Unauthorized` with standard error envelope
- Expired token → `401 Unauthorized` with `code: "token_expired"`
- Routers `documents.py` and `query.py` replace `account_id="dev"` with `Depends(get_current_account_id)`

**Non-functional**:
- `JWT_SECRET` and `JWT_ALGORITHM` come from `config.settings` — never hardcoded
- The auth service must be importable without side effects (no network calls at import time)
- If `JWT_SECRET` is not set, the app starts but auth will fail on every request (log a warning at startup)

---

## Implementation Guidelines

**New package to add** (via `uv add`):
- `PyJWT` — JWT encode/decode

**Files to create**:
- `app/services/auth.py`

**Files to modify**:
- `app/config.py` — add `JWT_SECRET: str = ""` and `JWT_ALGORITHM: str = "HS256"`
- `app/routers/documents.py` — replace `account_id="dev"` with `account_id: str = Depends(get_current_account_id)`
- `app/routers/query.py` — same

**Auth service implementation sketch**:

```python
# app/services/auth.py
import os
import jwt
from fastapi import Request, HTTPException
from app.config import settings

class AuthError(Exception):
    pass

def decode_token(token: str) -> str:
    """Decode JWT and return account_id (sub claim). Raises AuthError on failure."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        account_id: str | None = payload.get("sub")
        if not account_id:
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
        raise HTTPException(401, detail={"error": {"code": "unauthorized", "message": "Missing auth token", "field": None}})

    try:
        return decode_token(token)
    except AuthError as e:
        code = "token_expired" if "token_expired" in str(e) else "invalid_token"
        raise HTTPException(401, detail={"error": {"code": code, "message": str(e), "field": None}})
```

**Token generation helper** (for dev/testing, not exposed as an endpoint):

```python
# scripts/generate_token.py
"""
Usage: uv run python scripts/generate_token.py <account_id>
Generates a JWT for local dev and testing.
"""
import sys, jwt, datetime
from app.config import settings

account_id = sys.argv[1]
payload = {"sub": account_id, "iat": datetime.datetime.utcnow()}
token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
print(token)
```

---

## API Changes

All existing endpoints now require `Authorization: Bearer <jwt>` or `MCP_AUTH_TOKEN` env var.

**New error responses**:

`401` — missing token:
```json
{"error": {"code": "unauthorized", "message": "Missing auth token", "field": null}}
```

`401` — expired token:
```json
{"error": {"code": "token_expired", "message": "...", "field": null}}
```

`401` — invalid token:
```json
{"error": {"code": "invalid_token", "message": "...", "field": null}}
```

---

## Test Requirements

Create `tests/test_auth.py`:

- `test_valid_token_returns_account_id` — encode a JWT with known secret, call `decode_token`, assert correct account_id returned
- `test_expired_token_raises_auth_error` — encode expired JWT, assert `AuthError` raised with `token_expired`
- `test_invalid_token_raises_auth_error` — pass garbage string, assert `AuthError`
- `test_missing_token_returns_401` — call `GET /health` or `POST /documents` with no auth header, assert 401
- `test_bearer_token_accepted` — call endpoint with valid `Authorization: Bearer <token>`, assert request proceeds
- `test_env_token_accepted` — monkeypatch `MCP_AUTH_TOKEN` env var, call endpoint without header, assert request proceeds

**Testing notes**:
- Use a short-lived `JWT_SECRET` fixture in conftest — override `settings.jwt_secret` for tests
- The health endpoint `GET /health` should remain unauthenticated (health checks must not require auth)

---

## Acceptance Criteria

- [ ] `decode_token` correctly extracts `account_id` from a valid JWT
- [ ] Expired/invalid tokens raise `AuthError` with appropriate code
- [ ] `POST /documents` with no token → 401
- [ ] `POST /documents` with valid token → proceeds (with correct `account_id` stored on document)
- [ ] `GET /health` still returns 200 with no token (health check excluded from auth)
- [ ] `MCP_AUTH_TOKEN` env var is accepted as fallback (for stdio MCP use)
- [ ] `make test` passes
- [ ] `make lint && make typecheck` passes

---

## Validation Steps

```bash
# Generate a test token
JWT_SECRET=test-secret uv run python scripts/generate_token.py acct_001

# Test auth on document upload
TOKEN=$(JWT_SECRET=test-secret uv run python scripts/generate_token.py acct_001)
curl -X POST http://localhost:8000/documents \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@test.txt"

# Test rejected request (no token)
curl -X POST http://localhost:8000/documents -F "file=@test.txt"
# Expected: 401

# Confirm account_id stored
docker compose exec postgres psql -U rag -d rag \
  -c "SELECT id, account_id, filename FROM documents;"

make test
make lint
make typecheck
```

---

## Risks

- `PyJWT` vs `python-jose`: prefer `PyJWT` — simpler, fewer dependencies, actively maintained
- If `JWT_SECRET` is empty/unset, `jwt.decode` will raise — handle this gracefully with a clear startup warning, not a crash
- The `MCP_AUTH_TOKEN` env var fallback must only be used when no `Authorization` header is present — do not silently prefer env over header
- `GET /health` must remain open (no auth) — add it to an explicit allow-list or skip the dependency on that route