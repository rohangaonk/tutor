"""POST /auth/signup — POST /auth/signin via Cognito User Pools."""

from __future__ import annotations

import logging

import boto3
from botocore.exceptions import ClientError, ParamValidationError
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from common.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _cognito_client():
    endpoint = settings.cognito_endpoint_url
    # cognito-local (local dev) uses "local"/"local"; real AWS uses the instance role / env creds
    if endpoint:
        kwargs: dict = {
            "region_name": settings.cognito_region,
            "endpoint_url": endpoint,
            "aws_access_key_id": "local",
            "aws_secret_access_key": "local",
        }
    else:
        kwargs = {"region_name": settings.cognito_region}
    return boto3.client("cognito-idp", **kwargs)


def _require_cognito_config() -> None:
    """Raise 503 if Cognito hasn't been configured yet."""
    if not settings.cognito_user_pool_id or not settings.cognito_client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Auth is not configured. Run `make init-cognito` and add the "
                "printed values to your .env file, then restart the API."
            ),
        )


# ── Schemas ───────────────────────────────────────────────────────────────────

class SignUpRequest(BaseModel):
    email: str
    password: str


class SignUpResponse(BaseModel):
    message: str


class SignInRequest(BaseModel):
    email: str
    password: str


class SignInResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/signup", response_model=SignUpResponse, status_code=status.HTTP_201_CREATED)
def signup(body: SignUpRequest) -> SignUpResponse:
    """Register a new user in Cognito and auto-confirm (no email verification)."""
    _require_cognito_config()
    client = _cognito_client()
    try:
        client.sign_up(
            ClientId=settings.cognito_client_id,
            Username=body.email,
            Password=body.password,
            UserAttributes=[{"Name": "email", "Value": body.email}],
        )
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code == "UsernameExistsException":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists.",
            ) from exc
        if code == "InvalidPasswordException":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=exc.response["Error"]["Message"],
            ) from exc
        logger.error("Cognito sign_up error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Registration failed.",
        ) from exc
    except ParamValidationError as exc:
        logger.error("Cognito param error (is COGNITO_CLIENT_ID set?): %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth is misconfigured. Check COGNITO_CLIENT_ID in .env.",
        ) from exc

    # Auto-confirm so users can sign in immediately (no email verification)
    try:
        client.admin_confirm_sign_up(
            UserPoolId=settings.cognito_user_pool_id,
            Username=body.email,
        )
    except ClientError as exc:
        logger.error("Cognito admin_confirm_sign_up error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not confirm registration.",
        ) from exc

    return SignUpResponse(message="Account created. You can now sign in.")


@router.post("/signin", response_model=SignInResponse)
def signin(body: SignInRequest) -> SignInResponse:
    """Authenticate and return JWT tokens."""
    _require_cognito_config()
    client = _cognito_client()
    try:
        resp = client.initiate_auth(
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": body.email, "PASSWORD": body.password},
            ClientId=settings.cognito_client_id,
        )
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code in ("NotAuthorizedException", "UserNotFoundException"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password.",
            ) from exc
        logger.error("Cognito initiate_auth error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Authentication failed.",
        ) from exc
    except ParamValidationError as exc:
        logger.error("Cognito param error (is COGNITO_CLIENT_ID set?): %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth is misconfigured. Check COGNITO_CLIENT_ID in .env.",
        ) from exc

    result = resp.get("AuthenticationResult", {})
    return SignInResponse(
        access_token=result["AccessToken"],
        refresh_token=result["RefreshToken"],
    )
