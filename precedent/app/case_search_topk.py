# precedent/app/case_search_topk.py
from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Any, Optional
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
def _parse_date(s: Optional[str]):
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
def _sentences(text: Optional[str]) -> List[str]:
    if not isinstance(text, str) or not text.strip():
        return []
    t = re.sub(r'\s+', ' ', text.strip())
    parts = SENT_SPLIT.split(t)
    return [p.strip() for p in parts if p.strip()]

def _smart_summary(row: Dict[str, Any], limit_chars: int = 700) -> Optional[str]:
    # 우선순위: 판결요지 → 판시사항 → 본문
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
    """ids.npy는 필수, meta.jsonl이 없으면 빈 메타로 대체."""
    ids = np.load(INDEX_DIR / "ids.npy")
    meta_path = INDEX_DIR / "meta.jsonl"
    metas: List[Dict[str, Any]] = []
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            for line in f:
                metas.append(json.loads(line))
        # 길이 안 맞으면 맞춰 자르거나 패딩
        if len(metas) < len(ids):
            metas += [{} for _ in range(len(ids) - len(metas))]
        elif len(metas) > len(ids):
            metas = metas[: len(ids)]
    else:
        metas = [{} for _ in range(len(ids))]
    return ids, metas

def _load_model():
    info_p = INDEX_DIR / "meta_info.json"
    model_name = MODEL_FALLBACK
    if info_p.exists():
        try:
            info = json.loads(info_p.read_text(encoding="utf-8"))
            model_name = info.get("model", model_name)
        except Exception:
            pass
    return SentenceTransformer(model_name)

# -------- 전역(모듈 단위) 싱글톤 로드 --------
try:
    faiss_index = _load_faiss_index_safe(INDEX_DIR / "faiss.index")
    ids_arr, metas = _load_meta()
    model = _load_model()

    df = pd.read_parquet(DATA_FILE)
    df["판례일련번호"] = df["판례일련번호"].astype(str)

    # 본문/행 전체 접근 맵
    body_map: Dict[str, str] = dict(zip(df["판례일련번호"], df.get("본문", pd.Series([""] * len(df)))))
    row_map: Dict[str, Dict[str, Any]] = {str(r["판례일련번호"]): r.to_dict() for _, r in df.iterrows()}

    _READY = True
except Exception as e:
    print(f"[WARN] case_search_topk 초기화 실패: {e}")
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
    court: Optional[str] = Query(None, description="쉼표구분 법원 필터 (예: 대법원,서울고등법원)"),
    from_date: Optional[str] = Query(None, description="YYYY-MM-DD 이상"),
    to_date: Optional[str] = Query(None, description="YYYY-MM-DD 이하"),
):
    if not _READY:
        return {"error": "cases index not initialized"}

    # 쿼리 임베딩
    qv = model.encode(q, convert_to_numpy=True, normalize_embeddings=True).astype(np.float32).reshape(1, -1)

    # 넉넉히 뽑은 뒤 필터 & 중복제거 & 상위 k
    rawK = max(k * 10, k)  # 여유있게
    scores, idxs = faiss_index.search(qv, rawK)
    scores, idxs = scores[0], idxs[0]

    court_set = set([c.strip() for c in court.split(",") if c.strip()]) if court else None
    from_dt = datetime.fromisoformat(from_date) if from_date else None
    to_dt   = datetime.fromisoformat(to_date) if to_date else None

    seen: set[str] = set()  # doc_id 중복 제거용
    hits: List[Dict[str, Any]] = []

    for score, ridx in zip(scores, idxs):
        if ridx == -1:
            continue

        doc_id = str(int(ids_arr[ridx]))
        if doc_id in seen:
            continue  # 같은 문서 중복 제거
        seen.add(doc_id)

        meta = metas[ridx] if 0 <= ridx < len(metas) else {}
        row = row_map.get(doc_id, {})

        # 법원 필터
        if court_set:
            court_name = (row.get("법원명") or meta.get("법원") or "").strip()
            if court_name and court_name not in court_set:
                continue

        # 날짜 필터
        raw_date = (row.get("선고일자") or meta.get("선고일자"))
        dt = _parse_date(raw_date) if raw_date else None
        if from_dt and (dt is None or dt < from_dt): 
            continue
        if to_dt   and (dt is None or dt > to_dt):   
            continue

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
            body = row.get("본문") or body_map.get(doc_id)
            if isinstance(body, str) and body.strip():
                item["본문"] = body

        hits.append(item)
        if len(hits) >= k:
            break

    return {"query": q, "count": len(hits), "items": hits}

@cases_router.get("/{doc_id}", summary="판례 한 건 상세", tags=["cases"])
def get_case(doc_id: int, with_summary: bool = True, with_body: bool = False):
    if not _READY:
        return {"error": "cases index not initialized"}

    key = str(doc_id)
    # ids_arr에서 메타 위치 찾아보기(없으면 빈 dict)
    try:
        ridx = int(np.where(ids_arr.astype(int) == int(doc_id))[0][0])
        meta = metas[ridx] if 0 <= ridx < len(metas) else {}
    except Exception:
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
        if isinstance(body, str) and body.strip():
            item["본문"] = body
    return item
