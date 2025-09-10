import time
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from jose import jwt, JWTError

import requests

# ---------------------------
# Settings
# ---------------------------
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='../../.env', env_file_encoding='utf-8', extra='ignore')
    # Auth
    JWT_SECRET: str = 'change_me'
    JWT_ALG: str = 'HS256'
    # Service
    SERVICE_NAME: str = 'rag-svc'
    PORT: int = 8105
    # Chroma
    CHROMA_HOST: str = 'localhost'
    CHROMA_PORT: int = 8000
    CHROMA_COLLECTION: str = 'rag_docs'
    # OpenAI
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_CHAT_MODEL: str = 'gpt-4o-mini'
    OPENAI_EMBED_MODEL: str = 'text-embedding-3-small'
    # sanitize
    SANITIZE_BASE: str = 'http://localhost:8103'

settings = Settings()

# ---------------------------
# App
# ---------------------------
app = FastAPI(
    title=settings.SERVICE_NAME,
    version='0.1.0',
    docs_url='/docs',
    openapi_url='/openapi.json'
)

@app.get('/health')
def health():
    return JSONResponse({'status': 'ok', 'service': settings.SERVICE_NAME})

# ---------------------------
# Auth (JWT + roles)
# ---------------------------
class User(BaseModel):
    email: str
    roles: List[str] = []

def get_current_user(authorization: Optional[str] = Header(None)) -> User:
    if not authorization or not authorization.lower().startswith('bearer '):
        raise HTTPException(status_code=401, detail='Missing bearer token')
    token = authorization.split(' ', 1)[1]
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
        email = payload.get('sub')
        roles = payload.get('roles', [])
        if not email:
            raise HTTPException(status_code=401, detail='Invalid token (sub)')
        return User(email=email, roles=roles)
    except JWTError:
        raise HTTPException(status_code=401, detail='Invalid token')

def require_roles(*required: str):
    def checker(user: User = Depends(get_current_user)) -> User:
        if not any(r in user.roles for r in required):
            raise HTTPException(status_code=403, detail='Insufficient role')
        return user
    return checker

# ---------------------------
# Simple Mock RAG (without OpenAI/Chroma for now)
# ---------------------------
def sanitize(text: str, token: str) -> str:
    try:
        url = f'{settings.SANITIZE_BASE}/sanitize/apply'
        req = {"text": text, "language": "en", "operator": "replace"}
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        r = requests.post(url, json=req, headers=headers, timeout=30)
        if r.status_code >= 300:
            return text
        return r.json().get("sanitized_text", text)
    except:
        return text

# ---------------------------
# Models
# ---------------------------
class QueryRequest(BaseModel):
    question: str = Field(..., description="Pregunta del usuario")
    top_k: int = Field(4, ge=1, le=10)
    sanitize_in: bool = Field(True, description="Pre-sanitizar pregunta")
    sanitize_out: bool = Field(True, description="Post-sanitizar respuesta")

class Citation(BaseModel):
    rank: int
    id: str
    score: Optional[float] = None
    source: Optional[str] = None
    filename: Optional[str] = None
    chunk_index: Optional[int] = None
    preview: Optional[str] = None

class QueryResponse(BaseModel):
    answer: str
    citations: List[Citation]
    question_sanitized: Optional[str] = None
    latency_ms: int

# ---------------------------
# Endpoint principal (MOCK)
# ---------------------------
@app.post('/rag/query', response_model=QueryResponse, summary='Consultar RAG con citas (MOCK)')
def rag_query(req: QueryRequest, user: User = Depends(require_roles('user','expert','moderator','admin')), authorization: Optional[str] = Header(None)):
    t0 = time.time()

    # 1) Pre-sanitize pregunta
    q = req.question
    token = authorization.split(' ', 1)[1] if authorization and authorization.lower().startswith('bearer ') else None
    if req.sanitize_in and token:
        q = sanitize(q, token)

    # 2) Mock response (sin Chroma/OpenAI)
    mock_answer = f"Esta es una respuesta mock para la pregunta: '{q}'. El sistema RAG no está completamente configurado aún (falta OpenAI API key o Chroma). Pero la autenticación y sanitización están funcionando."
    
    # 3) Mock citations
    citations = [
        Citation(
            rank=1,
            id="mock-doc-1",
            score=0.95,
            source="mock://document1.pdf",
            filename="document1.pdf",
            chunk_index=0,
            preview="Este es un fragmento mock de un documento..."
        )
    ]

    # 4) Post-sanitize respuesta
    if req.sanitize_out and token:
        mock_answer = sanitize(mock_answer, token)

    dt = int((time.time() - t0) * 1000)
    return QueryResponse(
        answer=mock_answer, 
        citations=citations, 
        question_sanitized=q if req.sanitize_in else None, 
        latency_ms=dt
    )
