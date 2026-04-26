import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Sequence

from fastapi import Header, HTTPException, status
from pydantic import BaseModel

from app.config import (
    get_auth_mode,
    get_auth_secret_key,
    get_entra_audience,
    get_entra_contractor_group_ids,
    get_entra_issuer,
    get_entra_jwks_json,
    get_entra_jwks_url,
    get_entra_official_group_ids,
)

Role = Literal["contractor", "official"]


class MockLoginRequest(BaseModel):
    role: Role


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserResponse"


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: Role
    group_ids: List[str] = []


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str
    name: str
    role: Role
    group_ids: Sequence[str] = field(default_factory=tuple)


MOCK_USERS: Dict[Role, CurrentUser] = {
    "contractor": CurrentUser(
        id="contractor-demo",
        email="contractor@example.com",
        name="Contractor Demo",
        role="contractor",
    ),
    "official": CurrentUser(
        id="official-demo",
        email="official@example.gov",
        name="Government Official Demo",
        role="official",
    ),
}


def create_token(user: CurrentUser) -> str:
    payload = {
        "sub": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "exp": int(time.time()) + 60 * 60 * 8,
    }
    encoded_payload = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _signature(encoded_payload)
    return f"{encoded_payload}.{signature}"


def get_current_user(authorization: str = Header(default="")) -> CurrentUser:
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    token = authorization[len(prefix) :]
    if get_auth_mode() == "entra":
        return _get_entra_user(token)
    if get_auth_mode() != "mock":
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid AUTH_MODE")

    return _get_mock_user(token)


def _get_mock_user(token: str) -> CurrentUser:
    try:
        encoded_payload, signature = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    if not hmac.compare_digest(_signature(encoded_payload), signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    try:
        payload = json.loads(_b64decode(encoded_payload))
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    if int(payload.get("exp", 0)) < int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Expired token")

    role = payload.get("role")
    if role not in MOCK_USERS:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid role")

    return CurrentUser(
        id=str(payload["sub"]),
        email=str(payload["email"]),
        name=str(payload["name"]),
        role=role,
    )


def _get_entra_user(token: str) -> CurrentUser:
    issuer = get_entra_issuer()
    audience = get_entra_audience()
    if not issuer or not audience:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Entra authentication is not fully configured",
        )

    try:
        import jwt
        from jwt import PyJWKClient
    except ImportError as exc:  # pragma: no cover - dependency wiring guard.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PyJWT is required for Entra authentication",
        ) from exc

    try:
        jwks_json = get_entra_jwks_json()
        if jwks_json:
            jwks = json.loads(jwks_json)
            signing_key = _signing_key_from_jwks(jwt, jwks, token)
        else:
            jwks_url = get_entra_jwks_url()
            if not jwks_url:
                raise ValueError("ENTRA_JWKS_URL is not configured")
            signing_key = PyJWKClient(jwks_url).get_signing_key_from_jwt(token).key
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=audience,
            issuer=issuer,
            options={"require": ["exp", "iss", "aud"]},
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    groups = _string_list(payload.get("groups"))
    roles = {value.lower() for value in _string_list(payload.get("roles"))}
    official_groups = get_entra_official_group_ids()
    contractor_groups = get_entra_contractor_group_ids()
    if "official" in roles or official_groups.intersection(groups):
        role: Role = "official"
    elif "contractor" in roles or contractor_groups.intersection(groups):
        role = "contractor"
    else:
        role = "contractor"

    subject = str(payload.get("oid") or payload.get("sub") or "")
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    return CurrentUser(
        id=subject,
        email=str(payload.get("preferred_username") or payload.get("email") or ""),
        name=str(payload.get("name") or payload.get("preferred_username") or subject),
        role=role,
        group_ids=tuple(groups),
    )


def require_contractor(user: CurrentUser) -> CurrentUser:
    if user.role != "contractor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Contractor access required")
    return user


def user_response(user: CurrentUser) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        group_ids=list(user.group_ids),
    )


def auth_mode() -> str:
    return get_auth_mode()


def _signature(encoded_payload: str) -> str:
    digest = hmac.new(
        get_auth_secret_key().encode("utf-8"),
        encoded_payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _b64encode(digest)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> str:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding).decode("utf-8")


def _string_list(value: object) -> List[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _signing_key_from_jwks(jwt_module, jwks: dict, token: str):
    header = jwt_module.get_unverified_header(token)
    kid = header.get("kid")
    for key_data in jwks.get("keys", []):
        if key_data.get("kid") == kid:
            return jwt_module.algorithms.RSAAlgorithm.from_jwk(json.dumps(key_data))
    raise ValueError("Signing key not found")


TokenResponse.model_rebuild()
