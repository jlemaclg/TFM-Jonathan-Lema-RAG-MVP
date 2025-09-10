# 🤖 Agentic RAG MVP

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.0-green.svg)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue.svg)](https://www.docker.com/)

> **Sistema de Recuperación Aumentada Generativa (RAG) Empresarial** con arquitectura de microservicios, guardrails de privacidad PII, y orquestación inteligente.

## 📋 Tabla de Contenidos

- [🎯 Características](#-características)
- [🏗️ Arquitectura](#️-arquitectura)
- [🚀 Inicio Rápido](#-inicio-rápido)
- [📦 Servicios](#-servicios)
- [🔧 Instalación](#-instalación)
- [📖 Uso](#-uso)
- [🧪 Testing](#-testing)
- [🤝 Contribución](#-contribución)

## 🎯 Características

### 🔒 **Seguridad y Privacidad**
- **Guardrails PII**: Detección y sanitización automática de datos personales usando Microsoft Presidio
- **Autenticación JWT**: Sistema de roles jerárquicos (admin, moderator, user)
- **Encriptación**: Comunicación segura entre servicios

### 🏗️ **Arquitectura Empresarial**
- **Microservicios desacoplados**: 6 servicios independientes con responsabilidades claras
- **API Gateway**: Traefik como punto de entrada único
- **Orquestación**: Agent-svc + MCP-server para coordinación inteligente
- **Escalabilidad**: Diseño preparado para Kubernetes/Docker Swarm

### 📊 **Tecnologías Avanzadas**
- **Vector Search**: ChromaDB para búsqueda semántica eficiente
- **Embeddings**: Modelos E5 multilingüe para representaciones vectoriales
- **LLM Integration**: OpenAI GPT-4o-mini con fallback local
- **Storage**: MinIO S3-compatible + PostgreSQL para persistencia

### 🔍 **Funcionalidades RAG**
- **Retrieval Augmentation**: Búsqueda híbrida (semántica + BM25)
- **Context Window Management**: Optimización automática del contexto
- **Citation Tracking**: Referencias precisas a fuentes originales
- **Feedback Loop**: Sistema de evaluación y mejora continua

## 🏗️ Arquitectura

```mermaid
graph TB
    subgraph "API Gateway"
        T[Traefik]
    end

    subgraph "Microservicios"
        A[auth-svc :8101<br/>JWT Auth]
        F[files-svc :8102<br/>MinIO Storage]
        S[sanitize-svc :8103<br/>PII Detection]
        I[indexer-svc :8104<br/>Document Indexing]
        R[rag-svc :8105<br/>Query Processing]
        FB[feedback-svc :8106<br/>Evaluation]
    end

    subgraph "Inteligencia"
        AG[agent-svc<br/>Orchestration]
        MCP[mcp-server<br/>Model Context Protocol]
    end

    subgraph "Infraestructura"
        PG[(PostgreSQL)]
        M[(MinIO)]
        CH[(ChromaDB)]
        RD[(Redis)]
    end

    T --> A
    T --> F
    T --> S
    T --> I
    T --> R
    T --> FB

    A --> PG
    F --> M
    I --> CH
    R --> CH
    FB --> PG

    AG --> R
    MCP --> AG
```

### 🔄 **Flujo de Trabajo**

1. **📤 Upload**: Documentos subidos via files-svc → MinIO
2. **🧹 Sanitize**: Detección PII con Presidio → Texto limpio
3. **📚 Index**: Chunking + embeddings E5 → ChromaDB
4. **🔍 Query**: Retrieval semántico + LLM → Respuesta contextual
5. **📊 Feedback**: Evaluación de calidad → Mejora continua

## 🚀 Inicio Rápido

### Prerrequisitos

- **Python 3.11+**
- **Docker & Docker Compose**
- **Git**
- **4GB RAM mínimo** (recomendado 8GB+)

### Instalación Automática

```bash
# Clonar repositorio
git clone https://github.com/tu-usuario/agentic-rag-mvp.git
cd agentic-rag-mvp

# Configurar entorno
cp .env.example .env
# Editar .env con tus claves API

# Levantar infraestructura
docker-compose up -d

# Instalar dependencias y levantar servicios
./scripts/setup-all-services.sh
```

### Verificación

```bash
# Verificar servicios
curl http://localhost:8101/health  # auth-svc
curl http://localhost:8102/health  # files-svc
curl http://localhost:8103/health  # sanitize-svc
curl http://localhost:8104/health  # indexer-svc
curl http://localhost:8105/health  # rag-svc
curl http://localhost:8106/health  # feedback-svc
```

## 📦 Servicios

| Puerto | Servicio | Descripción | Tecnologías |
|--------|----------|-------------|-------------|
| **8101** | `auth-svc` | Autenticación JWT con roles | FastAPI, Jose, PostgreSQL |
| **8102** | `files-svc` | Gestión de archivos | FastAPI, MinIO, Boto3 |
| **8103** | `sanitize-svc` | Detección PII | FastAPI, Microsoft Presidio, SpaCy |
| **8104** | `indexer-svc` | Indexación de documentos | FastAPI, ChromaDB, SentenceTransformers |
| **8105** | `rag-svc` | Consultas RAG | FastAPI, OpenAI, ChromaDB |
| **8106** | `feedback-svc` | Recolección de feedback | FastAPI, PostgreSQL, SQLAlchemy |

## 🔧 Instalación Detallada

### 1. Clonar y Configurar

```bash
git clone https://github.com/tu-usuario/agentic-rag-mvp.git
cd agentic-rag-mvp

# Configurar variables de entorno
cp .env.example .env
nano .env  # Configurar OPENAI_API_KEY, DB credentials, etc.
```

### 2. Infraestructura Docker

```bash
# Levantar servicios base
docker-compose up -d postgres minio chroma redis

# Verificar que estén corriendo
docker ps
```

### 3. Servicios Python

```bash
# Instalar dependencias para cada servicio
cd services/auth-svc && pip install -r requirements.txt
cd ../files-svc && pip install -r requirements.txt
cd ../sanitize-svc && pip install -r requirements.txt
cd ../indexer-svc && pip install -r requirements.txt
cd ../rag-svc && pip install -r requirements.txt
cd ../feedback-svc && pip install -r requirements.txt

# Levantar servicios (en terminales separadas)
uvicorn services.auth-svc.app.main:app --reload --port 8101
uvicorn services.files-svc.app.main:app --reload --port 8102
# ... continuar con los demás
```

### 4. Verificación Completa

```bash
# Script de verificación
./scripts/health-check.sh
```

## 📖 Uso

### Autenticación

```bash
# Obtener token JWT
curl -X POST "http://localhost:8101/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'
```

### Subir Documento

```bash
# Subir archivo con autenticación
curl -X POST "http://localhost:8102/files/upload" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -F "file=@document.pdf"
```

### Consultar RAG

```bash
# Realizar consulta
curl -X POST "http://localhost:8105/rag/query" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "¿Cómo funciona el sistema RAG?",
    "top_k": 4,
    "sanitize_in": true,
    "sanitize_out": true
  }'
```

### Respuesta de Ejemplo

```json
{
  "answer": "El sistema RAG funciona mediante recuperación de información relevante...",
  "citations": [
    {
      "rank": 1,
      "id": "doc1__0",
      "score": 0.87,
      "source": "manual-rag.pdf",
      "chunk_index": 0,
      "preview": "El sistema RAG combina técnicas de recuperación..."
    }
  ],
  "question_sanitized": "¿Cómo funciona el sistema RAG?",
  "latency_ms": 1250
}
```

## 🧪 Testing

### Tests Unitarios

```bash
# Ejecutar tests para todos los servicios
pytest services/*/tests/

# Tests específicos
pytest services/auth-svc/tests/test_auth.py -v
pytest services/rag-svc/tests/test_rag.py -v
```

### Tests de Integración

```bash
# Tests end-to-end
./scripts/test-integration.sh

# Tests de carga
./scripts/load-test.sh
```

### Evaluación RAG

```bash
# Usando RAGAS para evaluación automática
python -m ragas.evaluate \
  --dataset test_dataset.json \
  --metrics answer_relevancy context_relevancy faithfulness
```

## 🤝 Contribución

¡Las contribuciones son bienvenidas! Por favor, lee nuestras [guías de contribución](CONTRIBUTING.md).

### Desarrollo Local

1. **Fork** el proyecto
2. **Crea** una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. **Commit** tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. **Push** a la rama (`git push origin feature/AmazingFeature`)
5. **Abre** un Pull Request

### Estándares de Código

- **Python**: PEP 8 con Black para formateo
- **Commits**: Conventional Commits
- **Tests**: Cobertura mínima del 80%
- **Documentación**: Docstrings completos

---

## � **Trabajo Fin de Máster - UNIR**

Este proyecto ha sido desarrollado como parte del **Trabajo Fin de Máster (TFM)** en el **Máster Universitario en Inteligencia Artificial** de la **Universidad Internacional de La Rioja (UNIR)**.

**Autor**: Jonathan Lema  
**Fecha**: Septiembre 2025  
**Programa**: Máster en Inteligencia Artificial - UNIR

<div align="center">
  <img src="docs/architecture-diagram.png" alt="Arquitectura del Sistema" width="600"/>
</div>
