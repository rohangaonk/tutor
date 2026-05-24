"""FastAPI dependencies for authentication."""

from __future__ import annotations

import logging
import urllib.request
import uuid
from json import loads

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from common.config import settings
from common.db import get_db
from common.models import User

logger = logging.getLogger(__name__)

bearer = HTTPBearer()

# Module-level JWKS cache — refreshed on first request after startup
_jwks_cache: dict | None = None


def _jwks_url() -> str:
    base = settings.cognito_endpoint_url or f"https://cognito-idp.{settings.cognito_region}.amazonaws.com"
    return f"{base}/{settings.cognito_user_pool_id}/.well-known/jwks.json"


def _get_jwks() -> dict:
    global _jwks_cache
    if _jwks_cache is None:
        url = _jwks_url()
        logger.debug("Fetching JWKS from %s", url)
        with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310
            _jwks_cache = loads(resp.read())
    return _jwks_cache


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> uuid.UUID:
    """Verify a Cognito JWT and return the caller's user UUID.

    Auto-provisions a User row on first login so callers never need to
    pre-register in the DB separately from Cognito.
    """
    token = credentials.credentials
    try:
        jwks = _get_jwks()
        claims = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
    except JWTError as exc:
        logger.warning("JWT verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    sub = claims.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing sub claim",
        )

    try:
        user_id = uuid.UUID(sub)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed sub claim",
        ) from exc

    # Auto-provision user row on first login
    user = db.get(User, user_id)
    if not user:
        email = claims.get("username") or claims.get("cognito:username") or str(user_id)
        db.add(User(id=user_id, email=email))
        db.commit()

    return user_id
