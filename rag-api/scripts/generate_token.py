"""
Dev token generator.

Usage:
    uv run python scripts/generate_token.py <account_id>

Generates a JWT for local dev and testing. Requires JWT_SECRET env var.
"""

import datetime
import sys

import jwt

from app.config import settings

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: uv run python scripts/generate_token.py <account_id>", file=sys.stderr)
        sys.exit(1)

    account_id = sys.argv[1]
    payload = {
        "sub": account_id,
        "iat": datetime.datetime.now(datetime.UTC),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    print(token)
