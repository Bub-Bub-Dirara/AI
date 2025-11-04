# src/search_topk.py
import json
import re
from pathlib import Path
from typing import List, Optional, Dict

import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
import faiss
from datetime import datetime

# ----- 경로/모델 기본값 -----
INDEX_DIR_DEFAULT = "index"
DATA_PATH_DEFAULT = "data/cases_clean.parquet"
MODEL_NAME_FALLBACK = "jhgan/ko-sroberta-multitask"


# =========================
# 유틸: 날짜/문장 처리
# =========================
def _parse_date(s: str) -> Optional[datetime]:
    """YYYY.MM.DD 또는 YYYY-MM-DD 둘 다 허용"""
    if not isinstance(s, str):
        return None
    s = s.strip()
    for fmt in ("%Y.%m.%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    return None


_SENT_SPLIT = re.compile(r'(?<=[\.!?])(?=[\s\"\')\]])')

def _sentences(text: str) -> List[str]:
    if not isinstance(text, str) or not text.strip():
        return []
    t = re.sub(r'\s+', ' ', text.strip())
    parts = _SENT_SPLIT.split(t)
    return [p.strip() for p in parts if p.strip()]


def _smart_summary(row: Dict, limit_chars: int = 700) -> Optional[str]:
    """
    요약 우선순위:
      1) 판결요지 (앞 2~3문장)
      2) 판시사항 (앞 2~3문장)
      3) 본문 (앞 2문장)
    문장 경계로 끊고 길이 초과면 … 추가
    """
    for col, take in (("판결요지", 3), ("판시사항", 3), ("본문", 2)):
        txt = row.get(col)
        if isinstance(txt, str) and txt.strip():
            sents = _sentences(txt)
            if sents:
                cand = " ".join(sents[:take])
            else:
                cand = txt.strip()
            return cand if len(cand) <= limit_chars else cand[:limit_chars] + "…"
    return None


# =========================
# 로딩 함수들
# =========================
def load_ids_and_meta(index_dir: str):
    metas = []
    with open(f"{index_dir}/meta.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            metas.append(json.loads(line))
    ids = np.load(f"{index_dir}/ids.npy")
    return ids, metas


def load_model(index_dir: str):
    info_p = Path(f"{index_dir}/meta_info.json")
    if info_p.exists():
        info = json.loads(info_p.read_text(encoding="utf-8"))
        return SentenceTransformer(info.get("model", MODEL_NAME_FALLBACK))
    return SentenceTransformer(MODEL_NAME_FALLBACK)


def load_index(index_dir: str):
    return faiss.read_index(f"{index_dir}/faiss.index")


def load_dataframe(data_path: str):
    # 판례일련번호를 key로 빠르게 접근할 수 있게 인덱스 설정
    df = pd.read_parquet(data_path)
    if "판례일련번호" not in df.columns:
        raise ValueError("데이터에 '판례일련번호' 컬럼이 없습니다.")
    df = df.set_index("판례일련번호", drop=False)
    return df


# =========================
# 검색 본체
# =========================
def search(
    text: str,
    topk: int = 5,
    index_dir: str = INDEX_DIR_DEFAULT,
    data_path: str = DATA_PATH_DEFAULT,
    summary_len: int = 700,
    return_full: bool = False,
    court_filter: Optional[List[str]] = None,   # 예: ["대법원","서울고등법원"]
    from_date: Optional[str] = None,            # "2019-01-01"
    to_date: Optional[str] = None,              # "2025-12-31"
):
    # [1] 인덱스/메타/모델/데이터 로드
    index = load_index(index_dir)
    ids, metas = load_ids_and_meta(index_dir)
    model = load_model(index_dir)
    df = load_dataframe(data_path)

    # [2] 쿼리 임베딩
    q = model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
    q = q.reshape(1, -1).astype(np.float32)

    # [3] FAISS 검색
    scores, idxs = index.search(q, topk * 5)  # 필터링 대비 넉넉히 뽑아두기
    scores, idxs = scores[0], idxs[0]

    # [4] 필터 조건 미리 파싱
    court_set = set(court_filter) if court_filter else None
    from_dt = datetime.fromisoformat(from_date) if from_date else None
    to_dt = datetime.fromisoformat(to_date) if to_date else None

    # [5] Hit 구성(+필터링)
    hits = []
    for score, ridx in zip(scores, idxs):
        if ridx == -1:
            continue

        doc_id = int(ids[ridx])
        meta = metas[ridx]  # meta.jsonl의 동일 순서 메타

        # 상세행(본문/요지 포함)을 DF에서 가져오기
        if doc_id not in df.index:
            # 데이터 간 mismatch가 드물게 있을 수 있으니 skip
            continue
        row = df.loc[doc_id].to_dict()

        # ---- 필터: 법원
        if court_set:
            # 메타에 "법원명"이 있을 수도, row에 있을 수도 있으니 우선 row 사용
            law_court = (row.get("법원명") or meta.get("법원") or "").strip()
            if law_court not in court_set:
                continue

        # ---- 필터: 선고일자
        raw_date = (row.get("선고일자") or meta.get("선고일자"))
        dt = _parse_date(raw_date) if raw_date else None
        if from_dt and (dt is None or dt < from_dt):
            continue
        if to_dt and (dt is None or dt > to_dt):
            continue

        if return_full:
            content_key = "본문"
            content_val = row.get("본문")
        else:
            content_key = "본문요약"
            content_val = _smart_summary(row, limit_chars=summary_len)

        hits.append({
            "doc_id": doc_id,
            "score": float(score),
            "사건명": row.get("사건명") or meta.get("제목"),
            "법원명": row.get("법원명") or meta.get("법원"),
            "선고일자": row.get("선고일자") or meta.get("선고일자"),
            "사건번호": row.get("사건번호") or meta.get("사건번호"),
            content_key: content_val
        })

        if len(hits) >= topk:
            break

    return hits

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--q", required=True, help="query text")
    ap.add_argument("--k", type=int, default=5, help="top-k 반환 개수")
    ap.add_argument("--index_dir", default=INDEX_DIR_DEFAULT)
    ap.add_argument("--data", dest="data_path", default=DATA_PATH_DEFAULT)
    ap.add_argument("--summary_len", type=int, default=700, help="요약 최대 길이")
    ap.add_argument("--full", action="store_true", help="요약 대신 전체 본문 반환")
    ap.add_argument("--court", type=str, default="", help="쉼표로 구분된 법원명 필터 (예: '대법원,서울고등법원')")
    ap.add_argument("--from_date", type=str, default="", help="YYYY-MM-DD (이 날짜 이상)")
    ap.add_argument("--to_date", type=str, default="", help="YYYY-MM-DD (이 날짜 이하)")
    args = ap.parse_args()

    courts = [c.strip() for c in args.court.split(",") if c.strip()] if args.court else None
    from_d = args.from_date or None
    to_d = args.to_date or None

    res = search(
        text=args.q,
        topk=args.k,
        index_dir=args.index_dir,
        data_path=args.data_path,
        summary_len=args.summary_len,
        return_full=args.full,
        court_filter=courts,
        from_date=from_d,
        to_date=to_d,
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))
