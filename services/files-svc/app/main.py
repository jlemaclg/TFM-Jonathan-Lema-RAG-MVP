import re
from io import BytesIO
from datetime import timedelta
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, status, Query, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from jose import jwt, JWTError
from minio import Minio
from minio.error import S3Error

SAFE_NAME_RE = re.compile(r'[^a-zA-Z0-9._/-]+')

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='../../.env', env_file_encoding='utf-8', extra='ignore')
    JWT_SECRET: str = 'change_me'
    JWT_ALG: str = 'HS256'
    MINIO_ROOT_USER: str = 'admin'
    MINIO_ROOT_PASSWORD: str = 'adminadmin'
    MINIO_BUCKET: str = 'rag-docs'
    MINIO_ENDPOINT: str = 'localhost:9000'  # Cliente local
    MINIO_SECURE: bool = False
    PORT: int = 8102

settings = Settings()

app = FastAPI(title='files-svc', version='0.1.0', docs_url='/docs', openapi_url='/openapi.json')

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

_minio = Minio(
    endpoint=settings.MINIO_ENDPOINT,
    access_key=settings.MINIO_ROOT_USER,
    secret_key=settings.MINIO_ROOT_PASSWORD,
    secure=settings.MINIO_SECURE
)

def ensure_bucket():
    found = _minio.bucket_exists(settings.MINIO_BUCKET)
    if not found:
        _minio.make_bucket(settings.MINIO_BUCKET)

@app.on_event('startup')
def on_startup():
    ensure_bucket()

@app.get('/health')
def health():
    return JSONResponse({'status':'ok', 'service':'files-svc'})

class FileItem(BaseModel):
    object_name: str
    size: int
    last_modified: Optional[str] = None
    presigned_url: Optional[str] = None

def sanitize_object_name(name: str) -> str:
    name = name.replace('..','.')
    name = SAFE_NAME_RE.sub('_', name).strip('_')
    if not name:
        raise HTTPException(status_code=400, detail='Invalid filename')
    return name

@app.post('/files/upload', response_model=FileItem, summary='Subir archivo (roles: admin|moderator|expert)')
async def upload_file(
    f: UploadFile = File(...),
    _: User = Depends(require_roles('admin','moderator','expert'))
):
    if f.content_type and not any(f.content_type.startswith(x) for x in ['text/','application/','image/','audio/','video/','application/pdf']):
        raise HTTPException(status_code=415, detail=f'Content-Type no permitido: {f.content_type}')
    object_name = sanitize_object_name(f.filename or 'file')
    try:
        content = await f.read()
        bio = BytesIO(content)  # <-- lector válido
        _minio.put_object(
            bucket_name=settings.MINIO_BUCKET,
            object_name=object_name,
            data=bio,
            length=len(content),
            content_type=f.content_type or 'application/octet-stream'
        )
        url = _minio.presigned_get_object(settings.MINIO_BUCKET, object_name, expires=timedelta(minutes=30))
        st = _minio.stat_object(settings.MINIO_BUCKET, object_name)
        return FileItem(object_name=object_name, size=st.size, last_modified=st.last_modified.isoformat(), presigned_url=url)
    except S3Error as e:
        raise HTTPException(status_code=500, detail=f'Upload error: {str(e)}')

@app.get('/files', response_model=List[FileItem], summary='Listar archivos (roles: user|expert|moderator|admin)')
def list_files(
    presign: bool = Query(True, description='Incluir URL presignada'),
    _: User = Depends(require_roles('user','expert','moderator','admin'))
):
    try:
        items: List[FileItem] = []
        for obj in _minio.list_objects(settings.MINIO_BUCKET, recursive=True):
            url = _minio.presigned_get_object(settings.MINIO_BUCKET, obj.object_name, expires=timedelta(minutes=30)) if presign else None
            last = obj.last_modified.isoformat() if obj.last_modified else None
            items.append(FileItem(object_name=obj.object_name, size=obj.size or 0, last_modified=last, presigned_url=url))
        return items
    except S3Error as e:
        raise HTTPException(status_code=500, detail=f'List error: {str(e)}')

@app.get('/files/{object_name}/url', summary='Obtener URL presignada (roles: user|expert|moderator|admin)')
def presign_url(
    object_name: str,
    _: User = Depends(require_roles('user','expert','moderator','admin'))
):
    object_name = sanitize_object_name(object_name)
    try:
        _minio.stat_object(settings.MINIO_BUCKET, object_name)
        url = _minio.presigned_get_object(settings.MINIO_BUCKET, object_name, expires=timedelta(minutes=30))
        return {'object_name': object_name, 'url': url}
    except S3Error as e:
        if e.code == 'NoSuchKey':
            raise HTTPException(status_code=404, detail='Object not found')
        raise HTTPException(status_code=500, detail=f'Presign error: {str(e)}')

@app.delete('/files/{object_name}', summary='Borrar archivo (roles: admin|moderator)')
def delete_file(
    object_name: str,
    _: User = Depends(require_roles('admin','moderator'))
):
    object_name = sanitize_object_name(object_name)
    try:
        _minio.remove_object(settings.MINIO_BUCKET, object_name)
        return {'deleted': object_name}
    except S3Error as e:
        if e.code == 'NoSuchKey':
            raise HTTPException(status_code=404, detail='Object not found')
        raise HTTPException(status_code=500, detail=f'Delete error: {str(e)}')
