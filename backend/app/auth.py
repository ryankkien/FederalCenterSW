import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Dict, Literal

from fastapi import Header, HTTPException, status
from pydantic import BaseModel

from app.config import get_auth_secret_key

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


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str
    name: str
    role: Role


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


def require_contractor(user: CurrentUser) -> CurrentUser:
    if user.role != "contractor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Contractor access required")
    return user


def user_response(user: CurrentUser) -> UserResponse:
    return UserResponse(id=user.id, email=user.email, name=user.name, role=user.role)


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


TokenResponse.model_rebuild()
