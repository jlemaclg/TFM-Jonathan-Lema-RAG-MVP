import re
from typing import List, Optional, Dict
from difflib import ndiff

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from jose import jwt, JWTError

# Presidio / spaCy
from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import SpacyNlpEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import AnonymizerConfig

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='../../.env', env_file_encoding='utf-8', extra='ignore')
    JWT_SECRET: str = 'change_me'
    JWT_ALG: str = 'HS256'
    PORT: int = 8103
settings = Settings()

app = FastAPI(title='sanitize-svc', version='0.1.0', docs_url='/docs', openapi_url='/openapi.json')

@app.get('/health')
def health():
    return JSONResponse({'status': 'ok', 'service': 'sanitize-svc'})

# --------- Auth ----------
class User(BaseModel):
    email: str
    roles: List[str] = []

def get_current_user(authorization: Optional[str] = Header(None)) -> User:
    if not authorization or not authorization.lower().startswith('bearer '):
        raise HTTPException(status_code=401, detail='Missing bearer token')
    token = authorization.split(' ', 1)[1]
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
        email = payload.get('sub'); roles = payload.get('roles', [])
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

# --------- Lazy init Presidio/spaCy ----------
_analyzer: AnalyzerEngine | None = None
_anonymizer: AnonymizerEngine | None = None

def ensure_ready():
    global _analyzer, _anonymizer
    if _analyzer and _anonymizer:
        return
    # Carga spaCy y Presidio aquí (una sola vez)
    nlp_engine = SpacyNlpEngine(models={"en": "en_core_web_sm"})
    analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
    anonymizer = AnonymizerEngine()

    # Reglas custom ES/secretos
    dni = PatternRecognizer(supported_entity="ES_DNI", patterns=[Pattern(name="dni_es", regex=r"\b\d{8}[A-HJ-NP-TV-Z]\b", score=0.65)])
    iban = PatternRecognizer(supported_entity="ES_IBAN", patterns=[Pattern(name="iban_es", regex=r"\bES\d{2}[0-9A-Z]{20}\b", score=0.7)])
    oai = PatternRecognizer(supported_entity="OPENAI_KEY", patterns=[Pattern(name="openai_key", regex=r"\bsk-[A-Za-z0-9]{10,}\b", score=0.9)])
    cc  = PatternRecognizer(supported_entity="GENERIC_CREDIT_CARD", patterns=[Pattern(name="cc_fallback", regex=r"\b(?:\d[ -]*?){13,19}\b", score=0.4)])

    analyzer.registry.add_recognizer(dni)
    analyzer.registry.add_recognizer(iban)
    analyzer.registry.add_recognizer(oai)
    analyzer.registry.add_recognizer(cc)

    _analyzer = analyzer
    _anonymizer = anonymizer

def _supported_entities():
    ensure_ready()
    base = set(_analyzer.get_supported_entities("en")) | {"ES_DNI","ES_IBAN","OPENAI_KEY","GENERIC_CREDIT_CARD"}
    return sorted(base)

# --------- Modelos ----------
class PreviewRequest(BaseModel):
    text: str
    language: str = "en"
    entities: Optional[List[str]] = None
    operator: str = "replace"
    mask_char: str = "*"
    mask_len: int = 6

class EntityHit(BaseModel):
    entity_type: str; start: int; end: int; score: float; text: str

class PreviewResponse(BaseModel):
    redacted_text: str
    entities: List[EntityHit]
    diff: Optional[List[str]] = None

class ApplyRequest(PreviewRequest): pass

class ApplyResponse(BaseModel):
    sanitized_text: str
    entities_applied: List[EntityHit]

# --------- Utils ----------
def _ops(operator: str, mask_char: str, mask_len: int) -> Dict[str, AnonymizerConfig]:
    ensure_ready()
    ops: Dict[str, AnonymizerConfig] = {}
    for ent in _supported_entities():
        if operator == "mask":
            ops[ent] = AnonymizerConfig("mask", {"masking_char": mask_char, "chars_to_mask": mask_len, "from_end": True})
        else:
            ops[ent] = AnonymizerConfig("replace", {"new_value": f"<{ent}>"})
    return ops

def _filter(results: List[RecognizerResult], allowed: Optional[List[str]]):
    if not allowed: return results
    allowed = set(allowed); return [r for r in results if r.entity_type in allowed]

def _to_hits(text: str, results: List[RecognizerResult]) -> List[EntityHit]:
    return [EntityHit(entity_type=r.entity_type, start=r.start, end=r.end, score=float(r.score), text=text[r.start:r.end]) for r in results]

def _diff(original: str, redacted: str) -> List[str]:
    return list(ndiff([original], [redacted]))

# --------- Endpoints ----------
@app.get("/recognizers", summary="Entidades soportadas")
def recognizers(_: User = Depends(require_roles("expert","moderator","admin"))):
    return {"entities": _supported_entities()}

@app.post("/sanitize/preview", response_model=PreviewResponse)
def sanitize_preview(req: PreviewRequest, _: User = Depends(require_roles("expert","moderator","admin"))):
    ensure_ready()
    results = _analyzer.analyze(text=req.text, language=req.language)
    results = _filter(results, req.entities)
    red = _anonymizer.anonymize(text=req.text, analyzer_results=results, operators=_ops(req.operator, req.mask_char, req.mask_len)).text
    return PreviewResponse(redacted_text=red, entities=_to_hits(req.text, results), diff=_diff(req.text, red))

@app.post("/sanitize/apply", response_model=ApplyResponse)
def sanitize_apply(req: ApplyRequest, _: User = Depends(require_roles("expert","moderator","admin"))):
    ensure_ready()
    results = _analyzer.analyze(text=req.text, language=req.language)
    results = _filter(results, req.entities)
    out = _anonymizer.anonymize(text=req.text, analyzer_results=results, operators=_ops(req.operator, req.mask_char, req.mask_len))
    return ApplyResponse(sanitized_text=out.text, entities_applied=_to_hits(req.text, results))

@app.on_event('startup')
def _startup():
    # Opcional: calienta en background; si falla, endpoints harán ensure_ready() igual
    try:
        ensure_ready()
    except Exception:
        pass
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
# Presidio (Analyzer + Anonymizer)
# ---------------------------
# Simple analyzer without spaCy for now
analyzer = AnalyzerEngine(supported_languages=["en"])
anonymizer = AnonymizerEngine()

# --- Reglas personalizadas (España/secretos) ---
# DNI/NIF: 8 dígitos + letra (simplificado)
dni_pattern = Pattern(name="dni_es", regex=r"\b\d{8}[A-HJ-NP-TV-Z]\b", score=0.65)
dni_recognizer = PatternRecognizer(supported_entity="ES_DNI", patterns=[dni_pattern])

# IBAN España: ES + 2 dígitos + 20 alfanum (simplificado)
iban_es_pattern = Pattern(name="iban_es", regex=r"\bES\d{2}[0-9A-Z]{20}\b", score=0.7)
iban_es_recognizer = PatternRecognizer(supported_entity="ES_IBAN", patterns=[iban_es_pattern])

# OpenAI key (sk- prefijo común)
openai_key_pattern = Pattern(name="openai_key", regex=r"\bsk-[A-Za-z0-9]{10,}\b", score=0.9)
openai_key_recognizer = PatternRecognizer(supported_entity="OPENAI_KEY", patterns=[openai_key_pattern])

# Tarjeta Visa/Mastercard (fallback simple si el built-in no dispara)
cc_pattern = Pattern(name="cc_fallback", regex=r"\b(?:\d[ -]*?){13,19}\b", score=0.4)
cc_recognizer = PatternRecognizer(supported_entity="GENERIC_CREDIT_CARD", patterns=[cc_pattern])

# Registrar custom recognizers
analyzer.registry.add_recognizer(dni_recognizer)
analyzer.registry.add_recognizer(iban_es_recognizer)
analyzer.registry.add_recognizer(openai_key_recognizer)
analyzer.registry.add_recognizer(cc_recognizer)

# ---------------------------
# Modelos de request/response
# ---------------------------
class PreviewRequest(BaseModel):
    text: str
    language: str = "en"
    # filtrar entidades por tipo (opcional). Si vacío => todas.
    entities: Optional[List[str]] = None
    # operador por defecto: replace con <ENTITY_TYPE>
    operator: str = "replace"
    mask_char: str = "*"  # si operator == "mask"
    mask_len: int = 6     # si operator == "mask"

class EntityHit(BaseModel):
    entity_type: str
    start: int
    end: int
    score: float
    text: str

class PreviewResponse(BaseModel):
    redacted_text: str
    entities: List[EntityHit]
    diff: Optional[List[str]] = None

class ApplyRequest(PreviewRequest):
    pass

class ApplyResponse(BaseModel):
    sanitized_text: str
    entities_applied: List[EntityHit]

# ---------------------------
# Utilidades
# ---------------------------
def build_operator_map(operator: str, mask_char: str, mask_len: int) -> Dict[str, AnonymizerConfig]:
    """
    Crea un mapa de operadores por defecto: todas las entidades detectadas
    se reemplazan por <ENTITY_TYPE> o se enmascaran.
    """
    # Lista base de entidades conocidas por Presidio + custom
    base_entities = set(analyzer.get_supported_entities("en")) | {"ES_DNI","ES_IBAN","OPENAI_KEY","GENERIC_CREDIT_CARD"}
    ops: Dict[str, AnonymizerConfig] = {}
    for ent in base_entities:
        if operator == "mask":
            ops[ent] = AnonymizerConfig("mask", {"masking_char": mask_char, "chars_to_mask": mask_len, "from_end": True})
        else:
            # replace
            ops[ent] = AnonymizerConfig("replace", {"new_value": f"<{ent}>"})
    return ops

def filter_entities(entities: List[RecognizerResult], allowed: Optional[List[str]]) -> List[RecognizerResult]:
    if not allowed:
        return entities
    allowed_set = set(allowed)
    return [e for e in entities if e.entity_type in allowed_set]

def to_hits(text: str, results: List[RecognizerResult]) -> List[EntityHit]:
    out: List[EntityHit] = []
    for r in results:
        snippet = text[r.start:r.end]
        out.append(EntityHit(entity_type=r.entity_type, start=r.start, end=r.end, score=float(r.score), text=snippet))
    return out

def compute_diff(original: str, redacted: str) -> List[str]:
    # diff legible (línea a línea)
    return list(ndiff([original], [redacted]))

# ---------------------------
# Endpoints
# ---------------------------
@app.get("/recognizers", summary="Entidades soportadas")
def recognizers(_: User = Depends(require_roles("expert","moderator","admin"))):
    base = sorted(set(analyzer.get_supported_entities("en")) | {"ES_DNI","ES_IBAN","OPENAI_KEY","GENERIC_CREDIT_CARD"})
    return {"entities": base}

@app.post("/sanitize/preview", response_model=PreviewResponse)
def sanitize_preview(req: PreviewRequest, _: User = Depends(require_roles("expert","moderator","admin"))):
    results = analyzer.analyze(text=req.text, language=req.language)
    results = filter_entities(results, req.entities)
    ops = build_operator_map(req.operator, req.mask_char, req.mask_len)
    redacted = anonymizer.anonymize(text=req.text, analyzer_results=results, operators=ops).text
    return PreviewResponse(
        redacted_text=redacted,
        entities=to_hits(req.text, results),
        diff=compute_diff(req.text, redacted)
    )

@app.post("/sanitize/apply", response_model=ApplyResponse)
def sanitize_apply(req: ApplyRequest, _: User = Depends(require_roles("expert","moderator","admin"))):
    results = analyzer.analyze(text=req.text, language=req.language)
    results = filter_entities(results, req.entities)
    ops = build_operator_map(req.operator, req.mask_char, req.mask_len)
    out = anonymizer.anonymize(text=req.text, analyzer_results=results, operators=ops)
    return ApplyResponse(
        sanitized_text=out.text,
        entities_applied=to_hits(req.text, results)
    )
