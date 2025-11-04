# src/build_index.py

import os
import json
import numpy as np
import pandas as pd
from pathlib import Path
from sentence_transformers import SentenceTransformer
import faiss

# ======== 설정 ========
DATA_PATH = "data/cases_clean.parquet"   # CSV면 .csv 로 변경
OUT_DIR = "index"
MODEL_NAME = "jhgan/ko-sroberta-multitask"  # 한글 SBERT (정확도 균형)
BATCH_SIZE = 128

# 컬럼 매핑 (너의 데이터 컬럼명에 맞게)
COL_ID = "판례일련번호"
COL_TITLE = "사건명"
COL_TEXT = "본문"    
COL_COURT = "법원명"
COL_DATE = "선고일자"
COL_CASE_NO = "사건번호"

# ======== 함수 정의 ========

def read_dataframe(path: str) -> pd.DataFrame:
    """CSV 또는 Parquet 파일 읽기"""
    if path.endswith(".parquet"):
        df = pd.read_parquet(path)
    elif path.endswith(".csv"):
        df = pd.read_csv(path)
    else:
        raise ValueError("지원하지 않는 파일 형식입니다.")
    return df


def build_embeddings(df: pd.DataFrame, model_name: str, batch: int = 128) -> np.ndarray:
    model = SentenceTransformer(model_name)
    texts = df[COL_TEXT].fillna("").astype(str).tolist()
    embs = model.encode(
        texts,
        batch_size=batch,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,   # cosine = inner product 가능하게
    )
    return embs


def save_index(embs: np.ndarray, meta_df: pd.DataFrame, model_name: str):
    """FAISS 인덱스 및 메타데이터 저장"""
    Path(OUT_DIR).mkdir(parents=True, exist_ok=True)

    dim = embs.shape[1]
    index = faiss.IndexFlatIP(dim)   # cosine 기반
    index.add(embs)
    faiss.write_index(index, f"{OUT_DIR}/faiss.index")

    np.save(f"{OUT_DIR}/ids.npy", meta_df[COL_ID].astype(np.int64).to_numpy())

    with open(f"{OUT_DIR}/meta.jsonl", "w", encoding="utf-8") as fout:
        for _, row in meta_df.iterrows():
            rec = {k: (None if pd.isna(row[k]) else str(row[k])) for k in meta_df.columns}
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")

    meta_info = {
        "model": model_name,
        "dim": dim,
        "size": int(index.ntotal),
        "text_col": COL_TEXT,
        "id_col": COL_ID,
        "excluded_fields": ["상세_JSON", "상세_XML", "상세_HTML", "판례상세링크_절대URL"],
    }
    with open(f"{OUT_DIR}/meta_info.json", "w", encoding="utf-8") as f:
        json.dump(meta_info, f, ensure_ascii=False, indent=2)

    print(f"[✅ 완료] 인덱스 저장됨: {OUT_DIR}/ (총 {index.ntotal}개, 차원 {dim})")


def main():
    # --- 데이터 로드 ---
    df = read_dataframe(DATA_PATH)
    print(f"[1/4] 데이터 로드 완료 ({len(df)}건)")

    # doc_id 준비
    if COL_ID not in df.columns:
        raise ValueError(f"'{COL_ID}' 컬럼이 없습니다. 데이터 컬럼 확인 필요.")
    df[COL_ID] = df[COL_ID].astype(np.int64)

    # --- 메타데이터 구성 ---
    meta_cols = [c for c in [COL_ID, COL_TITLE, COL_COURT, COL_DATE, COL_CASE_NO] if c in df.columns]
    meta_df = df[meta_cols].copy()
    print(f"[2/4] 메타데이터 구성 완료 ({meta_cols})")

    # --- 임베딩 생성 ---
    print(f"[3/4] SBERT 임베딩 생성 중... (모델={MODEL_NAME})")
    embs = build_embeddings(df, MODEL_NAME, BATCH_SIZE)

    # --- 인덱스 저장 ---
    print("[4/4] 인덱스 및 메타데이터 저장 중...")
    save_index(embs, meta_df, MODEL_NAME)


if __name__ == "__main__":
    main()
