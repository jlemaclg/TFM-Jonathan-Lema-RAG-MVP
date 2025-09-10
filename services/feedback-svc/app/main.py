import csv
import io
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any, Literal

from fastapi import FastAPI, HTTPException, Depends, Header, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from jose import jwt, JWTError
import psycopg2
import psycopg2.extras

# ---------------------------
# Settings
# ---------------------------
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='../../.env', env_file_encoding='utf-8', extra='ignore')
    # JWT
    JWT_SECRET: str = 'change_me'
    JWT_ALG: str = 'HS256'
    # Service
    SERVICE_NAME: str = 'feedback-svc'
    PORT: int = 8106
    # Postgres
    POSTGRES_USER: str = 'rag'
    POSTGRES_PASSWORD: str = 'ragpass'
    POSTGRES_DB: str = 'ragdb'
    POSTGRES_HOST: str = 'localhost'
    POSTGRES_PORT: int = 5432

settings = Settings()

def pg_conn():
    return psycopg2.connect(
        dbname=settings.POSTGRES_DB,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT
    )

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
# DB bootstrap
# ---------------------------
DDL = '''
CREATE TABLE IF NOT EXISTS feedback (
  id UUID PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  user_email TEXT NOT NULL,
  verdict TEXT NOT NULL CHECK (verdict IN ('good','bad','mixed')),
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  question_sanitized TEXT NULL,
  answer_sanitized TEXT NULL,
  citations JSONB NULL,
  tags TEXT[] NULL,
  notes TEXT NULL,
  correction TEXT NULL,
  meta JSONB NULL
);
CREATE INDEX IF NOT EXISTS idx_feedback_created_at ON feedback (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_feedback_verdict ON feedback (verdict);
'''

@app.on_event('startup')
def on_startup():
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(DDL)
        conn.commit()

# ---------------------------
# Models
# ---------------------------
Verdict = Literal['good','bad','mixed']

class Citation(BaseModel):
    rank: int
    id: Optional[str] = None
    score: Optional[float] = None
    source: Optional[str] = None
    filename: Optional[str] = None
    chunk_index: Optional[int] = None
    preview: Optional[str] = None

class SubmitRequest(BaseModel):
    verdict: Verdict
    question: str
    answer: str
    question_sanitized: Optional[str] = None
    answer_sanitized: Optional[str] = None
    citations: Optional[List[Citation]] = None
    tags: Optional[List[str]] = Field(default=None, description='p.ej. ["hallucination","outdated","pii","good_citation"]')
    notes: Optional[str] = None
    correction: Optional[str] = Field(default=None, description='Texto corregido por el experto (para re-indexar)')
    meta: Optional[Dict[str, Any]] = Field(default=None, description='Libre: latencia, modelo, top_k, etc.')

class SubmitResponse(BaseModel):
    id: str
    created_at: datetime

class ListItem(BaseModel):
    id: str
    created_at: datetime
    user_email: str
    verdict: Verdict
    tags: Optional[List[str]] = None
    notes: Optional[str] = None

class Stats(BaseModel):
    total: int
    good: int
    bad: int
    mixed: int
    last_24h: int

# ---------------------------
# Endpoints
# ---------------------------
@app.post('/feedback/submit', response_model=SubmitResponse, summary='Registrar feedback')
def submit_feedback(req: SubmitRequest, user: User = Depends(require_roles('user','expert','moderator','admin'))):
    fid = str(uuid.uuid4())
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                '''INSERT INTO feedback
                   (id, user_email, verdict, question, answer, question_sanitized, answer_sanitized, citations, tags, notes, correction, meta)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (
                    fid,
                    user.email,
                    req.verdict,
                    req.question,
                    req.answer,
                    req.question_sanitized,
                    req.answer_sanitized,
                    psycopg2.extras.Json([c.model_dump() for c in (req.citations or [])]),
                    req.tags,
                    req.notes,
                    req.correction,
                    psycopg2.extras.Json(req.meta or {})
                )
            )
        conn.commit()
    return SubmitResponse(id=fid, created_at=datetime.now(timezone.utc))

@app.get('/feedback/stats', response_model=Stats, summary='Estadísticas de feedback')
def feedback_stats(_: User = Depends(require_roles('expert','moderator','admin'))):
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT count(*) FROM feedback'); total = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM feedback WHERE verdict='good'"); good = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM feedback WHERE verdict='bad'"); bad = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM feedback WHERE verdict='mixed'"); mixed = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM feedback WHERE created_at >= now() - interval '24 hours'"); last24 = cur.fetchone()[0]
    return Stats(total=total, good=good, bad=bad, mixed=mixed, last_24h=last24)

@app.get('/feedback/list', response_model=List[ListItem], summary='Listar feedback (paginado)')
def feedback_list(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    verdict: Optional[Verdict] = None,
    _: User = Depends(require_roles('expert','moderator','admin'))
):
    sql = 'SELECT id, created_at, user_email, verdict, tags, notes FROM feedback'
    params = []
    if verdict:
        sql += ' WHERE verdict=%s'
        params.append(verdict)
    sql += ' ORDER BY created_at DESC LIMIT %s OFFSET %s'
    params += [limit, offset]
    rows: List[ListItem] = []
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            for r in cur.fetchall():
                rows.append(ListItem(
                    id=str(r[0]), created_at=r[1], user_email=r[2], verdict=r[3],
                    tags=r[4], notes=r[5]
                ))
    return rows

@app.get('/feedback/export', summary='Exportar feedback (csv|json)')
def feedback_export(
    fmt: str = Query('csv', pattern='^(csv|json)$'),
    _: User = Depends(require_roles('expert','moderator','admin'))
):
    with pg_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute('SELECT * FROM feedback ORDER BY created_at DESC')
            rows = cur.fetchall()

    if fmt == 'json':
        return rows

    # csv
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()) if rows else [
        'id','created_at','user_email','verdict','question','answer','question_sanitized','answer_sanitized','citations','tags','notes','correction','meta'
    ])
    writer.writeheader()
    for row in rows:
        # psycopg2 retorna dicts con tipos ya serializables; convierto listas/json explícitamente
        row = dict(row)
        if isinstance(row.get('citations'), (dict, list)):
            row['citations'] = str(row['citations'])
        if isinstance(row.get('meta'), (dict, list)):
            row['meta'] = str(row['meta'])
        if isinstance(row.get('tags'), list):
            row['tags'] = ','.join(row['tags'])
        writer.writerow(row)

    data = output.getvalue()
    headers = {'Content-Disposition': 'attachment; filename=feedback_export.csv'}
    return StreamingResponse(iter([data]), media_type='text/csv', headers=headers)

@app.delete('/feedback/{fid}', summary='Borrar feedback por ID (mod/admin)')
def feedback_delete(fid: str, _: User = Depends(require_roles('moderator','admin'))):
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM feedback WHERE id=%s', (fid,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail='Not found')
        conn.commit()
    return {'deleted': fid}
