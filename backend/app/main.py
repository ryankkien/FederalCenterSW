from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from app.analysis_api import router as analysis_router
from app.auth import (
    MOCK_USERS,
    CurrentUser,
    MockLoginRequest,
    TokenResponse,
    auth_mode,
    create_token,
    get_current_user,
    user_response,
)
from app.admin import router as admin_router
from app.agent import router as agent_router
from app.contracts import router as contracts_router
from app.database import create_db_schema
from app.documents import router as documents_router
from app.knowledge_api import router as knowledge_router
from app.processing_api import router as processing_router


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
app.include_router(contracts_router)
app.include_router(agent_router)
app.include_router(processing_router)
app.include_router(admin_router)
app.include_router(analysis_router)
app.include_router(knowledge_router)


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "service": "api"}


@app.post("/api/auth/mock-login", response_model=TokenResponse)
def mock_login(payload: MockLoginRequest) -> TokenResponse:
    if auth_mode() != "mock":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mock login is disabled")
    user = MOCK_USERS[payload.role]
    return TokenResponse(access_token=create_token(user), user=user_response(user))


@app.get("/api/auth/me")
def me(user: CurrentUser = Depends(get_current_user)):
    return user_response(user)
