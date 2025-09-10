# 🤝 Guía de Contribución - Agentic RAG MVP

¡Gracias por tu interés en contribuir al **Agentic RAG MVP**! Este documento describe las mejores prácticas y procesos para contribuir al proyecto.

## 📋 Tabla de Contenidos

- [🚀 Inicio Rápido](#-inicio-rápido)
- [💻 Configuración de Desarrollo](#-configuración-de-desarrollo)
- [🔄 Flujo de Trabajo](#-flujo-de-trabajo)
- [📝 Estándares de Código](#-estándares-de-código)
- [🧪 Testing](#-testing)
- [📚 Documentación](#-documentación)
- [🔍 Pull Requests](#-pull-requests)
- [🐛 Reporte de Bugs](#-reporte-de-bugs)
- [💡 Solicitud de Features](#-solicitud-de-features)

## 🚀 Inicio Rápido

### Prerrequisitos

- **Python 3.11+**
- **Docker & Docker Compose**
- **Git**
- **VS Code** (recomendado) con extensiones:
  - Python
  - Pylance
  - Docker
  - GitLens

### Configuración Inicial

```bash
# 1. Fork y clona el repositorio
git clone https://github.com/tu-usuario/agentic-rag-mvp.git
cd agentic-rag-mvp

# 2. Crea rama de desarrollo
git checkout -b development

# 3. Configura entorno virtual
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# o
.venv\Scripts\activate     # Windows

# 4. Instala dependencias de desarrollo
pip install -r requirements-dev.txt

# 5. Configura variables de entorno
cp .env.example .env
# Edita .env con tus configuraciones

# 6. Levanta infraestructura
docker-compose up -d

# 7. Ejecuta tests iniciales
pytest --version
```

## 💻 Configuración de Desarrollo

### Estructura del Proyecto

```
agentic-rag-mvp/
├── services/                 # Microservicios
│   ├── auth-svc/            # Autenticación JWT
│   ├── files-svc/           # Gestión de archivos
│   ├── sanitize-svc/        # Detección PII
│   ├── indexer-svc/         # Indexación de documentos
│   ├── rag-svc/            # Consultas RAG
│   └── feedback-svc/       # Recolección de feedback
├── infra/                   # Configuración de infraestructura
├── scripts/                 # Scripts de automatización
├── docs/                    # Documentación
└── tests/                   # Tests globales
```

### Dependencias de Desarrollo

Instala las herramientas necesarias:

```bash
# Herramientas de calidad de código
pip install black isort flake8 mypy pre-commit

# Testing
pip install pytest pytest-cov pytest-asyncio

# Documentación
pip install mkdocs mkdocs-material

# Pre-commit hooks
pre-commit install
```

## 🔄 Flujo de Trabajo

### 1. Elige una Issue

- Revisa las [issues abiertas](https://github.com/tu-usuario/agentic-rag-mvp/issues)
- Elige una issue etiquetada como `good first issue` o `help wanted`
- Asigna la issue a ti mismo

### 2. Crea una Rama

```bash
# Crea rama descriptiva
git checkout -b feature/add-user-authentication
# o
git checkout -b fix/sanitize-svc-crash
# o
git checkout -b docs/update-api-docs
```

### 3. Desarrolla

- Sigue los estándares de código
- Escribe tests para tu código
- Actualiza documentación si es necesario
- Haz commits frecuentes con mensajes descriptivos

### 4. Prueba tus Cambios

```bash
# Ejecuta tests locales
pytest services/nombre-servicio/tests/

# Verifica linting
black --check .
isort --check-only .
flake8 .

# Tests de integración
docker-compose -f docker-compose.test.yml up --abort-on-container-exit
```

### 5. Crea Pull Request

- Push tu rama: `git push origin feature/tu-feature`
- Crea PR desde GitHub
- Espera revisión de maintainers

## 📝 Estándares de Código

### Python

- **Formateo**: [Black](https://black.readthedocs.io/) (línea de 88 caracteres)
- **Imports**: [isort](https://pycqa.github.io/isort/) (orden alfabético)
- **Linting**: [flake8](https://flake8.pycqa.org/)
- **Type hints**: Obligatorios en funciones públicas
- **Docstrings**: Google style para funciones públicas

```python
# ✅ Correcto
def authenticate_user(
    username: str,
    password: str,
    db: Session = Depends(get_db)
) -> User:
    """Authenticate a user with username and password.

    Args:
        username: The user's username
        password: The user's password
        db: Database session

    Returns:
        The authenticated user object

    Raises:
        HTTPException: If authentication fails
    """
    # Implementation here
    pass

# ❌ Incorrecto
def authenticate_user(username,password,db=Depends(get_db)):
    # No type hints, no docstring, bad formatting
    pass
```

### Commits

Usamos [Conventional Commits](https://conventionalcommits.org/):

```bash
# ✅ Correcto
git commit -m "feat: add JWT token refresh endpoint"
git commit -m "fix: resolve PII detection false positives"
git commit -m "docs: update API documentation for rag-svc"
git commit -m "test: add integration tests for file upload"

# ❌ Incorrecto
git commit -m "fixed bug"
git commit -m "updated code"
git commit -m "changes"
```

### Nombres de Rama

```bash
# Features
feature/add-user-preferences
feature/implement-rag-evaluation

# Fixes
fix/sanitize-svc-memory-leak
fix/auth-token-expiration

# Documentation
docs/update-contributing-guide
docs/add-api-examples

# Testing
test/add-e2e-tests
test/fix-flaky-tests
```

## 🧪 Testing

### Tipos de Tests

1. **Unit Tests**: Prueban funciones individuales
2. **Integration Tests**: Prueban interacción entre servicios
3. **End-to-End Tests**: Prueban flujos completos
4. **Performance Tests**: Prueban rendimiento bajo carga

### Estructura de Tests

```python
# tests/test_auth_svc/
# ├── __init__.py
# ├── test_auth.py
# ├── test_models.py
# ├── test_routes.py
# ├── conftest.py
# └── fixtures/
#     ├── users.json
#     └── tokens.json
```

### Ejecutar Tests

```bash
# Todos los tests
pytest

# Tests específicos
pytest services/auth-svc/tests/test_auth.py

# Con cobertura
pytest --cov=services/auth-svc --cov-report=html

# Tests de integración
pytest -m integration

# Tests lentos
pytest -m slow
```

### Escribir Tests

```python
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

@pytest.mark.asyncio
async def test_user_registration(
    client: AsyncClient,
    db_session: AsyncSession
):
    """Test user registration endpoint."""
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "password": "securepassword123"
    }

    response = await client.post("/auth/register", json=user_data)

    assert response.status_code == 201
    data = response.json()
    assert data["username"] == user_data["username"]
    assert "password" not in data  # Password should not be returned
```

## 📚 Documentación

### API Documentation

- Usa docstrings en todas las funciones públicas
- Documenta parámetros, returns, y excepciones
- Incluye ejemplos de uso cuando sea relevante

### README Updates

- Actualiza el README principal si agregas nuevas funcionalidades
- Incluye ejemplos de uso para nuevas features
- Actualiza diagramas de arquitectura si cambian

### Code Comments

```python
# ✅ Bueno
# Calculate similarity score between query and document chunks
# using cosine similarity of their embeddings
similarity_score = cosine_similarity(query_embedding, doc_embedding)

# ❌ Malo
# Calculate similarity
score = cos_sim(q_emb, d_emb)
```

## 🔍 Pull Requests

### Template de PR

Usa esta plantilla para tus Pull Requests:

```markdown
## Descripción
Breve descripción de los cambios realizados.

## Tipo de Cambio
- [ ] 🐛 Bug fix
- [ ] ✨ New feature
- [ ] 💥 Breaking change
- [ ] 📚 Documentation
- [ ] 🎨 Style
- [ ] ♻️ Refactor
- [ ] ⚡ Performance
- [ ] ✅ Test

## Checklist
- [ ] Tests agregados/actualizados
- [ ] Documentación actualizada
- [ ] Linting aprobado
- [ ] Commits siguen conventional commits
- [ ] Revisión de seguridad completada

## Issues Relacionadas
Closes #123, #124

## Testing
- [ ] Tests unitarios pasan
- [ ] Tests de integración pasan
- [ ] Tests E2E pasan (si aplica)
```

### Proceso de Revisión

1. **Automated Checks**: CI/CD ejecuta tests y linting
2. **Peer Review**: Al menos 1 maintainer revisa el código
3. **Security Review**: Para cambios críticos
4. **Merge**: Squash merge con mensaje descriptivo

## 🐛 Reporte de Bugs

### Template de Bug Report

```markdown
**Descripción del Bug**
Descripción clara y concisa del bug.

**Pasos para Reproducir**
1. Ir a '...'
2. Hacer click en '....'
3. Ver error

**Comportamiento Esperado**
Qué debería suceder.

**Comportamiento Actual**
Qué sucede en realidad.

**Screenshots**
Si aplica, agrega screenshots.

**Entorno**
- OS: [e.g. Windows 11]
- Python: [e.g. 3.11.5]
- Docker: [e.g. 24.0.5]
- Browser: [e.g. Chrome 120]

**Contexto Adicional**
Cualquier información adicional relevante.
```

## 💡 Solicitud de Features

### Template de Feature Request

```markdown
**¿Es tu solicitud de feature relacionada con un problema? Por favor describe.**
Descripción clara del problema.

**Describe la solución que te gustaría**
Descripción de la feature que propones.

**Describe alternativas que has considerado**
Alternativas que has evaluado.

**Contexto adicional**
Cualquier información adicional.
```

## 🎯 Mejores Prácticas

### General

- ✅ **Haz commits pequeños y frecuentes**
- ✅ **Escribe tests antes del código (TDD)**
- ✅ **Mantén la simplicidad (KISS)**
- ✅ **No repitas código (DRY)**
- ✅ **Documenta decisiones de diseño importantes**

### Seguridad

- 🔒 **Nunca commits credenciales**
- 🔒 **Usa variables de entorno para secrets**
- 🔒 **Valida todas las entradas de usuario**
- 🔒 **Implementa rate limiting**
- 🔒 **Mantén dependencias actualizadas**

### Performance

- ⚡ **Optimiza queries de base de datos**
- ⚡ **Usa async/await para operaciones I/O**
- ⚡ **Implementa caching cuando sea necesario**
- ⚡ **Monitorea uso de memoria y CPU**

## 📞 Comunicación

- **Discusiones**: Usa [GitHub Discussions](https://github.com/tu-usuario/agentic-rag-mvp/discussions) para preguntas generales
- **Issues**: Para bugs y features específicas
- **Slack/Teams**: Para comunicación en tiempo real (si aplica)

## 🙏 Reconocimiento

¡Gracias por contribuir al Agentic RAG MVP! Tu tiempo y esfuerzo ayudan a mejorar el proyecto para toda la comunidad.

---

**Recuerda**: Este proyecto sigue el [Código de Conducta](CODE_OF_CONDUCT.md). Por favor, mantén un ambiente respetuoso y colaborativo.
