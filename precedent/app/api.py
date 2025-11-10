# precedent/app/main.py
from __future__ import annotations
from pathlib import Path
from fastapi import FastAPI, APIRouter, Query

from .laws_search_topk import LawRetriever
from .gpt import gpt_router
from .case_search_topk import cases_router
try:
    from .gpt_risk import router as gpt_risk_router
except Exception:
    gpt_risk_router = None

APP_ROOT = Path(__file__).resolve().parents[1]
app = FastAPI(
    title="precedent API",
    openapi_tags=[{"name": "AI", "description": "AI 기반 판례/법령/리스크 분석 API 모음"}],
)

@app.get("/health")
def health():
    return {"ok": True}

DEFAULT_CORPUS = APP_ROOT / "index" / "laws_preprocessed.json"
try:
    law_retriever = LawRetriever(meta_path=None, corpus_path=DEFAULT_CORPUS)
except Exception as e:
    print(f"[WARN] 법령 검색 인덱스 로드 실패: {e}")
    law_retriever = None

laws_router = APIRouter(prefix="/laws")

@laws_router.get("/search", summary="법령 검색 (TF-IDF + BM25 + 키워드/문구 부스트)")
def laws_search(
    q: str = Query(..., description="검색 질의어 (예: 보증금 반환 지체)"),
    k: int = Query(5, ge=1, le=50, description="반환 개수"),
    min_score: float = Query(0.05, ge=0.0, le=1.0, description="최소 점수 비율(0~1)"),
):
    if not law_retriever:
        return {"error": "LawRetriever not initialized"}
    results = law_retriever.pretty(q, top_k=k, min_score=min_score)
    return {"query": q, "count": len(results), "items": results}

def retag_router(router: APIRouter, tag: str = "AI") -> None:
    for r in router.routes:
        if hasattr(r, "tags"):
            r.tags = [tag]

retag_router(laws_router)
retag_router(gpt_router)
retag_router(cases_router)
if gpt_risk_router:
    retag_router(gpt_risk_router)

ai_router = APIRouter(prefix="/ai", tags=["AI"])

ai_router.include_router(laws_router)
ai_router.include_router(gpt_router)
ai_router.include_router(cases_router)
if gpt_risk_router:
    ai_router.include_router(gpt_risk_router)

app.include_router(ai_router)
