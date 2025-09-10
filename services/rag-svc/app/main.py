import time
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from jose import jwt, JWTError

import chromadb
from openai import OpenAI
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
# Clients
# ---------------------------
if not settings.OPENAI_API_KEY:
    raise RuntimeError('OPENAI_API_KEY no configurada en .env (raíz).')
oa = OpenAI(api_key=settings.OPENAI_API_KEY)

chroma = chromadb.HttpClient(host=settings.CHROMA_HOST, port=settings.CHROMA_PORT)
collection = chroma.get_or_create_collection(name=settings.CHROMA_COLLECTION, metadata={'hnsw:space': 'cosine'})

# ---------------------------
# Helpers
# ---------------------------
def embed(texts: List[str]) -> List[List[float]]:
    resp = oa.embeddings.create(model=settings.OPENAI_EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]

def sanitize(text: str, token: str) -> str:
    url = f'{settings.SANITIZE_BASE}/sanitize/apply'
    req = {"text": text, "language": "en", "operator": "replace"}
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = requests.post(url, json=req, headers=headers, timeout=30)
    if r.status_code >= 300:
        # Falla suave: mejor responder que romper (guardrail out lo intentaremos igual)
        return text
    return r.json().get("sanitized_text", text)

def build_context(docs: List[str], metas: List[Dict[str, Any]], max_chars: int = 8000) -> str:
    """Concatena trozos como '[[n]] <source> (chunk i): trozo...' para usar en el prompt."""
    ctx_parts = []
    total = 0
    for i, (d, m) in enumerate(zip(docs, metas), start=1):
        source = m.get('source') or m.get('filename') or 'unknown'
        chunk_idx = m.get('chunk_index', '?')
        header = f'[[{i}]] {source} (chunk {chunk_idx})\n'
        piece = header + d.strip()
        if total + len(piece) > max_chars:
            break
        ctx_parts.append(piece)
        total += len(piece)
    return '\n\n---\n\n'.join(ctx_parts)

def call_llm(question: str, context: str) -> str:
    system = (
        "Eres un asistente especializado en RAG. "
        "Responde SOLO con información del CONTEXTO proporcionado. "
        "Si no hay suficiente evidencia, di claramente: "
        "'No hay suficiente contexto para responder con precisión.'. "
        "Incluye referencias entre corchetes como [1], [2] si las utilizas."
    )
    user = f"PREGUNTA:\n{question}\n\nCONTEXTO:\n{context}"
    resp = oa.chat.completions.create(
        model=settings.OPENAI_CHAT_MODEL,
        messages=[{"role":"system","content":system},{"role":"user","content":user}],
        temperature=0.2,
    )
    return resp.choices[0].message.content.strip()

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
# Endpoint principal
# ---------------------------
@app.post('/rag/query', response_model=QueryResponse, summary='Consultar RAG con citas')
def rag_query(req: QueryRequest, user: User = Depends(require_roles('user','expert','moderator','admin')), authorization: Optional[str] = Header(None)):
    t0 = time.time()

    # 1) Pre-sanitize pregunta
    q = req.question
    token = authorization.split(' ', 1)[1] if authorization and authorization.lower().startswith('bearer ') else None
    if req.sanitize_in and token:
        q = sanitize(q, token)

    # 2) Retrieve en Chroma
    q_vec = embed([q])[0]
    res = collection.query(query_embeddings=[q_vec], n_results=req.top_k, include=['documents','metadatas','distances','ids'])
    docs = (res.get('documents') or [[]])[0]
    metas = (res.get('metadatas') or [[]])[0]
    dists = (res.get('distances') or [[]])[0]
    ids   = (res.get('ids') or [[]])[0]

    # 3) Preparar contexto y citas
    context = build_context(docs, metas, max_chars=8000)
    citations: List[Citation] = []
    for i, (cid, m, d, doc) in enumerate(zip(ids, metas, dists, docs), start=1):
        citations.append(Citation(
            rank=i,
            id=cid,
            score=float(d) if d is not None else None,
            source=m.get('source'),
            filename=m.get('filename'),
            chunk_index=m.get('chunk_index'),
            preview=(doc[:200] + '...') if doc else None
        ))

    # 4) LLM
    answer = call_llm(q, context)

    # 5) Post-sanitize respuesta
    if req.sanitize_out and token:
        answer = sanitize(answer, token)

    dt = int((time.time() - t0) * 1000)
    return QueryResponse(answer=answer, citations=citations, question_sanitized=q if req.sanitize_in else None, latency_ms=dt)
