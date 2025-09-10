param(
    [switch]$Install,   # pip install -r requirements.txt inside the venv when passed
    [switch]$Start      # start the uvicorn server when passed
)

# 0) Ir a la raíz del proyecto
Set-Location "C:\Users\jflema\OneDrive - Indra\Jonathan escritorio\Master Unir\TFM Jonathan Lema"

# 1) Crear .env local a partir del ejemplo (si aún no lo hiciste)
if (-Not (Test-Path ".\.env")) { Copy-Item ".env.example" ".env" }

# 2) Ajusta valores mínimos del .env (reemplaza el secret si quieres)
function Write-WithRetries {
    param(
        [string]$Path,
        [string]$Content,
        [int]$Retries = 5
    )
    $tmp = [System.IO.Path]::GetTempFileName()
    try {
        Set-Content -Path $tmp -Value $Content -Encoding UTF8 -Force
        for ($i = 0; $i -lt $Retries; $i++) {
            try {
                Move-Item -Path $tmp -Destination $Path -Force -ErrorAction Stop
                return
            } catch {
                Start-Sleep -Milliseconds 200
            }
        }
        Throw "No se pudo escribir $Path después de $Retries intentos."
    } finally {
        if (Test-Path $tmp) { Remove-Item $tmp -ErrorAction SilentlyContinue }
    }
}

# Ajustar .env mínimo
$envContent = (Get-Content .env -Raw) `
  -replace 'JWT_SECRET=.*', 'JWT_SECRET=super_secret_dev_key_please_change' `
  -replace 'JWT_EXP_MIN=.*', 'JWT_EXP_MIN=30'
Write-WithRetries -Path ".\.env" -Content $envContent

# 3) Actualizar requirements del servicio auth-svc (añadimos JWT y settings)
Write-WithRetries -Path "services/auth-svc/requirements.txt" -Content @"
fastapi==0.115.0
uvicorn[standard]==0.30.0
python-multipart==0.0.9
pydantic==2.8.2
pydantic-settings==2.4.0
python-jose==3.3.0
passlib[bcrypt]==1.7.4
python-dotenv==1.0.1
"@

# 4) Definir el puerto del servicio auth-svc (opcional, por claridad)
@"
SERVICE_NAME=auth-svc
PORT=8101
"@ | Out-String | ForEach-Object { $_ } | % { } # noop to keep formatting
Write-WithRetries -Path "services/auth-svc/.env.example" -Content @"
SERVICE_NAME=auth-svc
PORT=8101
"@
if (-Not (Test-Path "services/auth-svc/.env")) { Copy-Item "services/auth-svc/.env.example" "services/auth-svc/.env" }

# 5) Crear/Actualizar el código de auth-svc (main.py)
@"
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------
# Config
# ---------------------------
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../../.env", env_file_encoding="utf-8", extra="ignore")
    JWT_SECRET: str = "change_me"
    JWT_ALG: str = "HS256"
    JWT_EXP_MIN: int = 30
    PORT: int = 8101  # fallback

settings = Settings()

# ---------------------------
# App
# ---------------------------
app = FastAPI(
    title="auth-svc",
    version="0.1.0",
    docs_url="/docs",
    openapi_url="/openapi.json"
)

@app.get("/health")
def health():
    return JSONResponse({"status": "ok", "service": "auth-svc"})

# ---------------------------
# Seguridad / Usuarios demo
# ---------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

# Usuarios de ejemplo (in-memory). En producción -> DB.
_fake_users_db = {
    "admin@example.com": {
        "email": "admin@example.com",
        "hashed_password": pwd_context.hash("admin123"),
        "roles": ["admin", "moderator", "expert", "user"]
    },
    "expert@example.com": {
        "email": "expert@example.com",
        "hashed_password": pwd_context.hash("expert123"),
        "roles": ["expert", "user"]
    },
    "user@example.com": {
        "email": "user@example.com",
        "hashed_password": pwd_context.hash("user123"),
        "roles": ["user"]
    }
}

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class User(BaseModel):
    email: str
    roles: List[str]

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def authenticate_user(email: str, password: str) -> Optional[User]:
    user = _fake_users_db.get(email)
    if not user: 
        return None
    if not verify_password(password, user["hashed_password"]):
        return None
    return User(email=user["email"], roles=user["roles"])

def create_access_token(data: dict, expires_minutes: int) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALG)
    return token

async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
        email: str = payload.get("sub")
        roles: List[str] = payload.get("roles", [])
        if email is None:
            raise credentials_exception
        return User(email=email, roles=roles)
    except JWTError:
        raise credentials_exception

def require_roles(*required: str):
    async def checker(user: User = Depends(get_current_user)):
        if not any(role in user.roles for role in required):
            raise HTTPException(status_code=403, detail="Insufficient role")
        return user
    return checker

# ---------------------------
# Endpoints
# ---------------------------
@app.post("/login", response_model=Token, summary="Obtener token JWT (demo)")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    token = create_access_token(
        {"sub": user.email, "roles": user.roles},
        expires_minutes=int(settings.JWT_EXP_MIN)
    )
    return Token(access_token=token)

@app.get("/me", response_model=User, summary="Usuario actual (requiere JWT)")
async def me(user: User = Depends(get_current_user)):
    return user

@app.get("/admin/ping", summary="Solo ADMIN")
async def admin_ping(_: User = Depends(require_roles("admin"))):
    return {"ok": True, "scope": "admin"}
"@ | Out-String | ForEach-Object { $_ } | % { } # keep here-doc formatting
Write-WithRetries -Path "services/auth-svc/app/main.py" -Content @"
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------
# Config
# ---------------------------
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../../.env", env_file_encoding="utf-8", extra="ignore")
    JWT_SECRET: str = "change_me"
    JWT_ALG: str = "HS256"
    JWT_EXP_MIN: int = 30
    PORT: int = 8101  # fallback

settings = Settings()

# ---------------------------
# App
# ---------------------------
app = FastAPI(
    title="auth-svc",
    version="0.1.0",
    docs_url="/docs",
    openapi_url="/openapi.json"
)

@app.get("/health")
def health():
    return JSONResponse({"status": "ok", "service": "auth-svc"})

# ---------------------------
# Seguridad / Usuarios demo
# ---------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

# Usuarios de ejemplo (in-memory). En producción -> DB.
_fake_users_db = {
    "admin@example.com": {
        "email": "admin@example.com",
        "hashed_password": pwd_context.hash("admin123"),
        "roles": ["admin", "moderator", "expert", "user"]
    },
    "expert@example.com": {
        "email": "expert@example.com",
        "hashed_password": pwd_context.hash("expert123"),
        "roles": ["expert", "user"]
    },
    "user@example.com": {
        "email": "user@example.com",
        "hashed_password": pwd_context.hash("user123"),
        "roles": ["user"]
    }
}

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class User(BaseModel):
    email: str
    roles: List[str]

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def authenticate_user(email: str, password: str) -> Optional[User]:
    user = _fake_users_db.get(email)
    if not user: 
        return None
    if not verify_password(password, user["hashed_password"]):
        return None
    return User(email=user["email"], roles=user["roles"])

def create_access_token(data: dict, expires_minutes: int) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALG)
    return token

async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
        email: str = payload.get("sub")
        roles: List[str] = payload.get("roles", [])
        if email is None:
            raise credentials_exception
        return User(email=email, roles=roles)
    except JWTError:
        raise credentials_exception

def require_roles(*required: str):
    async def checker(user: User = Depends(get_current_user)):
        if not any(role in user.roles for role in required):
            raise HTTPException(status_code=403, detail="Insufficient role")
        return user
    return checker

# ---------------------------
# Endpoints
# ---------------------------
@app.post("/login", response_model=Token, summary="Obtener token JWT (demo)")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    token = create_access_token(
        {"sub": user.email, "roles": user.roles},
        expires_minutes=int(settings.JWT_EXP_MIN)
    )
    return Token(access_token=token)

@app.get("/me", response_model=User, summary="Usuario actual (requiere JWT)")
async def me(user: User = Depends(get_current_user)):
    return user

@app.get("/admin/ping", summary="Solo ADMIN")
async def admin_ping(_: User = Depends(require_roles("admin"))):
    return {"ok": True, "scope": "admin"}
"@

# 6) Crear entorno virtual dedicado al servicio (no se activa automáticamente)
Set-Location "services/auth-svc"
if (-Not (Test-Path ".venv-auth")) { python -m venv .venv-auth }

Write-Host "Entorno virtual: services/auth-svc/.venv-auth"
Write-Host "Para activar manualmente: .\.venv-auth\Scripts\Activate.ps1"

if ($Install) {
    Write-Host "Instalando dependencias dentro del venv..."
    $venvPython = Join-Path -Path (Get-Location) -ChildPath ".venv-auth\Scripts\python.exe"
    if (-Not (Test-Path $venvPython)) { Throw "No se encontró python en .venv-auth. Asegúrate de que el venv se creó correctamente." }
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r requirements.txt
}

if ($Start) {
    Write-Host "Iniciando uvicorn (desde el venv)..."
    $venvPython = Join-Path -Path (Get-Location) -ChildPath ".venv-auth\Scripts\python.exe"
    if (-Not (Test-Path $venvPython)) { Throw "No se encontró python en .venv-auth. Crea el venv y/o ejecuta con -Install para instalar paquetes." }
    & $venvPython -m uvicorn app.main:app --reload --port 8101
}
