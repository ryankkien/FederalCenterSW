from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import (
    MOCK_USERS,
    CurrentUser,
    MockLoginRequest,
    TokenResponse,
    create_token,
    get_current_user,
    user_response,
)
from app.database import create_db_schema
from app.documents import router as documents_router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    create_db_schema()
    yield


app = FastAPI(title="Federal Center SW API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents_router)


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "service": "api"}


@app.post("/api/auth/mock-login", response_model=TokenResponse)
def mock_login(payload: MockLoginRequest) -> TokenResponse:
    user = MOCK_USERS[payload.role]
    return TokenResponse(access_token=create_token(user), user=user_response(user))


@app.get("/api/auth/me")
def me(user: CurrentUser = Depends(get_current_user)):
    return user_response(user)
