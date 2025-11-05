# precedent/app/case_search_topk.py
from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Any
import json
import re
from datetime import datetime

import numpy as np
import pandas as pd
import faiss
from fastapi import APIRouter, Query
from sentence_transformers import SentenceTransformer

# -------- 경로/모델 기본값 --------
APP_ROOT = Path(__file__).resolve().parents[1]
INDEX_DIR = APP_ROOT / "index"
DATA_FILE = APP_ROOT / "data" / "cases_clean.parquet"
MODEL_FALLBACK = "jhgan/ko-sroberta-multitask"

# -------- 유틸 --------
def _parse_date(s: str):
    if not isinstance(s, str):
        return None
    s = s.strip()
    for fmt in ("%Y.%m.%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    return None

SENT_SPLIT = re.compile(r'(?<=[\.!?])(?=[\s\"\')\]])')
def _sentences(text: str):
    if not isinstance(text, str) or not text.strip():
        return []
    t = re.sub(r'\s+', ' ', text.strip())
    parts = SENT_SPLIT.split(t)
    return [p.strip() for p in parts if p.strip()]

def _smart_summary(row: Dict[str, Any], limit_chars: int = 700):
    for col, take in (("판결요지", 3), ("판시사항", 3), ("본문", 2)):
        txt = row.get(col)
        if isinstance(txt, str) and txt.strip():
            sents = _sentences(txt)
            cand = " ".join(sents[:take]) if sents else txt.strip()
            return cand if len(cand) <= limit_chars else cand[:limit_chars] + "…"
    return None

def _load_faiss_index_safe(path: Path):
    with open(path, "rb") as f:
        data = f.read()
    arr = np.frombuffer(data, dtype=np.uint8)
    return faiss.deserialize_index(arr)

def _load_meta():
    metas = []
    with open(INDEX_DIR / "meta.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            metas.append(json.loads(line))
    ids = np.load(INDEX_DIR / "ids.npy")
    return ids, metas

def _load_model():
    info_p = INDEX_DIR / "meta_info.json"
    model_name = MODEL_FALLBACK
    if info_p.exists():
        info = json.loads(info_p.read_text(encoding="utf-8"))
        model_name = info.get("model", model_name)
    return SentenceTransformer(model_name)

# -------- 전역(모듈 단위) 싱글톤 로드 --------
try:
    faiss_index = _load_faiss_index_safe(INDEX_DIR / "faiss.index")
    ids_arr, metas = _load_meta()
    model = _load_model()

    df = pd.read_parquet(DATA_FILE)
    df["판례일련번호"] = df["판례일련번호"].astype(str)
    body_map = dict(zip(df["판례일련번호"], df["본문"]))
    row_map  = { str(r["판례일련번호"]) : r.to_dict() for _, r in df.iterrows() }

    _READY = True
except Exception as e:
    print(f"[WARN] case_search_topk 초기화 실패: {e}")
    # 안전하게 더미 값
    faiss_index = None
    ids_arr, metas, model = None, [], None
    body_map, row_map = {}, {}
    _READY = False

# -------- 라우터 --------
cases_router = APIRouter(prefix="/cases", tags=["cases"])

@cases_router.get("/search", summary="판례 벡터 검색 (FAISS)", tags=["cases"])
def search_topk(
    q: str = Query(..., description="검색 질의문"),
    k: int = Query(5, ge=1, le=50, description="반환 개수"),
    with_summary: bool = Query(True, description="본문요약 포함 여부"),
    with_body: bool = Query(False, description="전체 본문 포함 여부"),
    court: str | None = Query(None, description="쉼표구분 법원 필터 (예: 대법원,서울고등법원)"),
    from_date: str | None = Query(None, description="YYYY-MM-DD 이상"),
    to_date: str | None = Query(None, description="YYYY-MM-DD 이하"),
):
    if not _READY:
        return {"error": "cases index not initialized"}

    qv = model.encode(q, convert_to_numpy=True, normalize_embeddings=True).astype(np.float32).reshape(1, -1)
    scores, idxs = faiss_index.search(qv, k * 5)  # 넉넉히 뽑고 필터 후 k개로 줄임
    scores, idxs = scores[0], idxs[0]

    court_set = set([c.strip() for c in court.split(",") if c.strip()]) if court else None
    from_dt = datetime.fromisoformat(from_date) if from_date else None
    to_dt   = datetime.fromisoformat(to_date) if to_date else None

    hits = []
    for score, ridx in zip(scores, idxs):
        if ridx == -1:
            continue
        doc_id = str(int(ids_arr[ridx]))
        meta = metas[ridx]
        row = row_map.get(doc_id, {})

        if court_set:
            court_name = (row.get("법원명") or meta.get("법원") or "").strip()
            if court_name not in court_set:
                continue

        raw_date = (row.get("선고일자") or meta.get("선고일자"))
        dt = _parse_date(raw_date) if raw_date else None
        if from_dt and (dt is None or dt < from_dt): continue
        if to_dt   and (dt is None or dt > to_dt):   continue

        item = {
            "doc_id": int(doc_id),
            "score": float(score),
            "사건명": row.get("사건명") or meta.get("제목"),
            "법원명": row.get("법원명") or meta.get("법원"),
            "선고일자": row.get("선고일자") or meta.get("선고일자"),
            "사건번호": row.get("사건번호") or meta.get("사건번호"),
        }
        if with_summary:
            item["본문요약"] = _smart_summary(row, 700) or meta.get("본문요약", "")
        if with_body:
            body = body_map.get(doc_id)
            if body:
                item["본문"] = body

        hits.append(item)
        if len(hits) >= k:
            break

    return {
        "query": q,
        "count": len(hits),
        "items": hits
    }

@cases_router.get("/{doc_id}", summary="판례 한 건 상세", tags=["cases"])
def get_case(doc_id: int, with_summary: bool = True, with_body: bool = False):
    if not _READY:
        return {"error": "cases index not initialized"}

    key = str(doc_id)
    try:
        ridx = list(map(int, ids_arr)).index(doc_id)
        meta = metas[ridx]
    except ValueError:
        meta = {}

    row = row_map.get(key, {})
    item = {
        "doc_id": doc_id,
        "사건명": row.get("사건명") or meta.get("제목"),
        "법원명": row.get("법원명") or meta.get("법원"),
        "선고일자": row.get("선고일자") or meta.get("선고일자"),
        "사건번호": row.get("사건번호") or meta.get("사건번호"),
    }
    if with_summary:
        item["본문요약"] = _smart_summary(row, 700) or meta.get("본문요약", "")
    if with_body:
        body = row.get("본문") or body_map.get(key)
        if body:
            item["본문"] = body

    return item
