import re
from typing import List, Optional, Dict, Any
from difflib import ndiff

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from jose import jwt, JWTError

# ---------------------------
# Settings
# ---------------------------
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='../../.env', env_file_encoding='utf-8', extra='ignore')
    JWT_SECRET: str = 'change_me'
    JWT_ALG: str = 'HS256'
    PORT: int = 8103

settings = Settings()

# ---------------------------
# App
# ---------------------------
app = FastAPI(
    title='sanitize-svc',
    version='0.1.0',
    docs_url='/docs',
    openapi_url='/openapi.json'
)

@app.get('/health')
def health():
    return JSONResponse({'status': 'ok', 'service': 'sanitize-svc'})

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
# Simple Regex-based Sanitization
# ---------------------------
PATTERNS = {
    'EMAIL': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    'PHONE': r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
    'SSN': r'\b\d{3}-\d{2}-\d{4}\b',
    'CREDIT_CARD': r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',
    'DNI_ES': r'\b\d{8}[A-HJ-NP-TV-Z]\b',
    'IBAN_ES': r'\bES\d{2}[0-9A-Z]{20}\b',
    'OPENAI_KEY': r'\bsk-[A-Za-z0-9]{10,}\b',
}

class EntityHit(BaseModel):
    entity_type: str
    start: int
    end: int
    score: float
    text: str

class PreviewRequest(BaseModel):
    text: str
    language: str = "en"
    entities: Optional[List[str]] = None
    operator: str = "replace"
    mask_char: str = "*"
    mask_len: int = 6

class PreviewResponse(BaseModel):
    redacted_text: str
    entities: List[EntityHit]
    diff: Optional[List[str]] = None

class ApplyResponse(BaseModel):
    sanitized_text: str
    entities_applied: List[EntityHit]

def find_entities(text: str, allowed_entities: Optional[List[str]] = None) -> List[EntityHit]:
    """Find entities using regex patterns"""
    entities = []
    patterns = PATTERNS if not allowed_entities else {k: v for k, v in PATTERNS.items() if k in allowed_entities}
    
    for entity_type, pattern in patterns.items():
        for match in re.finditer(pattern, text, re.IGNORECASE):
            entities.append(EntityHit(
                entity_type=entity_type,
                start=match.start(),
                end=match.end(),
                score=0.95,
                text=match.group()
            ))
    
    # Sort by start position
    entities.sort(key=lambda x: x.start)
    return entities

def apply_sanitization(text: str, entities: List[EntityHit], operator: str, mask_char: str, mask_len: int) -> str:
    """Apply sanitization to text"""
    # Work backwards to avoid position shifts
    entities_reversed = sorted(entities, key=lambda x: x.start, reverse=True)
    
    result = text
    for entity in entities_reversed:
        if operator == "mask":
            replacement = mask_char * mask_len
        else:  # replace
            replacement = f"<{entity.entity_type}>"
        
        result = result[:entity.start] + replacement + result[entity.end:]
    
    return result

# ---------------------------
# Endpoints
# ---------------------------
@app.get("/recognizers", summary="Entidades soportadas")
def recognizers(_: User = Depends(require_roles("expert","moderator","admin"))):
    return {"entities": list(PATTERNS.keys())}

@app.post("/sanitize/preview", response_model=PreviewResponse)
def sanitize_preview(req: PreviewRequest, _: User = Depends(require_roles("expert","moderator","admin"))):
    entities = find_entities(req.text, req.entities)
    redacted_text = apply_sanitization(req.text, entities, req.operator, req.mask_char, req.mask_len)
    
    return PreviewResponse(
        redacted_text=redacted_text,
        entities=entities,
        diff=list(ndiff([req.text], [redacted_text]))
    )

@app.post("/sanitize/apply", response_model=ApplyResponse)
def sanitize_apply(req: PreviewRequest, _: User = Depends(require_roles("expert","moderator","admin"))):
    entities = find_entities(req.text, req.entities)
    sanitized_text = apply_sanitization(req.text, entities, req.operator, req.mask_char, req.mask_len)
    
    return ApplyResponse(
        sanitized_text=sanitized_text,
        entities_applied=entities
    )
