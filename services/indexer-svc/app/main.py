import os
import io
import uuid
import pathlib
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from jose import jwt, JWTError

# Optional imports with error handling
try:
    import chromadb
except ImportError:
    chromadb = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from minio import Minio
    from minio.error import S3Error
except ImportError:
    Minio = None
    S3Error = None

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    import docx
except ImportError:
    docx = None

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
    PORT: int = 8104
    SERVICE_NAME: str = 'indexer-svc'
    # Chroma
    CHROMA_HOST: str = 'localhost'
    CHROMA_PORT: int = 8000
    CHROMA_COLLECTION: str = 'rag_docs'
    # OpenAI
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_EMBED_MODEL: str = 'text-embedding-3-small'
    # MinIO
    MINIO_ENDPOINT: str = 'localhost:9000'
    MINIO_ROOT_USER: str = 'admin'
    MINIO_ROOT_PASSWORD: str = 'adminadmin'
    MINIO_BUCKET: str = 'rag-docs'
    MINIO_SECURE: bool = False
    # Sanitize
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
# Basic Models and Endpoints
# ---------------------------
class StatsResponse(BaseModel):
    collection: str
    count: int
    status: str

@app.get('/stats', response_model=StatsResponse, summary='Estadísticas de la colección')
def stats(_: User = Depends(require_roles('user','expert','moderator','admin'))):
    return StatsResponse(
        collection=settings.CHROMA_COLLECTION, 
        count=0, 
        status="Service available - dependencies not fully installed"
    )
