from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pathlib import Path
import sys
from typing import List, Dict, Any

# Inserta el src de rag-starter en sys.path (ruta relativa desde el repo)
RAG_SRC = Path(__file__).resolve().parents[3] / "RAG" / "RAG" / "rag-starter" / "src"
if str(RAG_SRC) not in sys.path:
    sys.path.insert(0, str(RAG_SRC))

# Debug: verificar si el path existe y imprimir para troubleshooting
print(f"RAG_SRC path: {RAG_SRC}")
print(f"Path exists: {RAG_SRC.exists()}")

try:
    from retrieve import dense_retrieve
    from llm import generate_answer
except Exception as e:
    # Import error explícito para troubleshooting
    raise RuntimeError(f"No se pudo importar rag-starter modules: {e}")

app = FastAPI(title="rag-starter-svc", version="0.1.0")


class QueryRequest(BaseModel):
    question: str
    top_k: int = 8
    top: int = 5


class Citation(BaseModel):
    rank: int
    text: str
    meta: Dict[str, Any]
    score: float | None = None


class QueryResponse(BaseModel):
    answer: str
    citations: List[Citation]


@app.get("/health")
def health():
    return {"status": "ok", "service": "rag-starter-svc"}


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    # 1) retrieve
    cands = dense_retrieve(req.question, k=req.top_k)
    ctx = cands[: req.top]
    if not ctx:
        raise HTTPException(status_code=404, detail="No hay contexto recuperado. ¿Indexaste documentos?")

    # 2) generate answer
    answer = generate_answer(req.question, ctx)

    # 3) formatear citas
    citations = []
    for i, c in enumerate(ctx, start=1):
        citations.append(Citation(rank=i, text=c.get("text",""), meta=c.get("meta",{}), score=c.get("score")))

    return QueryResponse(answer=answer, citations=citations)
