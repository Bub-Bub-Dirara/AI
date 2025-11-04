# precedent/app/main.py
from pathlib import Path
import json
import numpy as np
import pandas as pd
import faiss
from fastapi import FastAPI, Query
from sentence_transformers import SentenceTransformer
import re
from datetime import datetime
import base64
import pdfplumber
from fastapi import UploadFile, File
from openai import OpenAI
from mimetypes import guess_type
import os 
import tempfile
APP_ROOT = Path(__file__).resolve().parents[1]
INDEX_DIR = APP_ROOT / "index"
DATA_FILE = APP_ROOT / "data" / "cases_clean.parquet"
MODEL_FALLBACK = "jhgan/ko-sroberta-multitask"

def load_faiss_index_safe(path: Path):
    with open(path, "rb") as f:
        data = f.read()
    arr = np.frombuffer(data, dtype=np.uint8)
    return faiss.deserialize_index(arr)

def load_meta():
    metas = []
    with open(INDEX_DIR / "meta.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            metas.append(json.loads(line))
    ids = np.load(INDEX_DIR / "ids.npy")
    return ids, metas

def load_model():
    info_p = INDEX_DIR / "meta_info.json"
    model_name = MODEL_FALLBACK
    if info_p.exists():
        info = json.loads(info_p.read_text(encoding="utf-8"))
        model_name = info.get("model", model_name)
    return SentenceTransformer(model_name)

def _parse_date(s: str):
    if not isinstance(s, str):
        return None
    s = s.strip()
    for fmt in ("%Y.%m.%d", "%Y-%m-%d"):
        try: return datetime.strptime(s, fmt)
        except: pass
    return None

SENT_SPLIT = re.compile(r'(?<=[\.!?])(?=[\s\"\')\]])')
def _sentences(text: str):
    if not isinstance(text, str) or not text.strip():
        return []
    t = re.sub(r'\s+', ' ', text.strip())
    parts = SENT_SPLIT.split(t)
    return [p.strip() for p in parts if p.strip()]

def _smart_summary(row: dict, limit_chars=700):
    for col, take in (("판결요지",3), ("판시사항",3), ("본문",2)):
        txt = row.get(col)
        if isinstance(txt, str) and txt.strip():
            sents = _sentences(txt)
            cand = " ".join(sents[:take]) if sents else txt.strip()
            return cand if len(cand) <= limit_chars else cand[:limit_chars] + "…"
    return None

faiss_index = load_faiss_index_safe(INDEX_DIR / "faiss.index")
ids_arr, metas = load_meta()
model = load_model()

df = pd.read_parquet(DATA_FILE)
df["판례일련번호"] = df["판례일련번호"].astype(str)
body_map = dict(zip(df["판례일련번호"], df["본문"]))
row_map  = { str(r["판례일련번호"]) : r.to_dict() for _, r in df.iterrows() }

app = FastAPI(title="precedent API")

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/search_topk", summary="Search Topk", tags=["search"])
def search_topk(
    q: str = Query(..., description="검색 질의문"),
    k: int = Query(5, ge=1, le=50, description="반환 개수"),
    with_summary: bool = Query(True, description="본문요약 포함 여부"),
    with_body: bool = Query(False, description="전체 본문 포함 여부"),
    court: str | None = Query(None, description="쉼표구분 법원 필터 (예: 대법원,서울고등법원)"),
    from_date: str | None = Query(None, description="YYYY-MM-DD 이상"),
    to_date: str | None = Query(None, description="YYYY-MM-DD 이하"),
):

    qv = model.encode(q, convert_to_numpy=True, normalize_embeddings=True).astype(np.float32)
    qv = qv.reshape(1, -1)

    scores, idxs = faiss_index.search(qv, k * 5)
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

    return hits

@app.get("/case/{doc_id}", summary="한 건 상세 본문", tags=["search"])
def get_case(doc_id: int, with_summary: bool = True, with_body: bool = False):
    key = str(doc_id)
    meta = None
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
        body = body_map.get(key)
        if body:
            item["본문"] = body
    return item

GPT_MODEL = "gpt-4o-mini"
GPT_API_KEY = "sk-p내키A"
client = OpenAI(api_key=GPT_API_KEY)

IMG_MIME = {"image/png", "image/jpeg", "image/webp", "image/heic", "image/heif"}

def guess_mime(filename: str) -> str:
    mt, _ = guess_type(filename)
    return mt or "application/octet-stream"

def read_pdf_text(file: UploadFile, limit_chars: int = 15000) -> str:
    """OS 독립 임시파일로 저장 후 pdfplumber로 텍스트 추출"""
    file.file.seek(0)  # 업로드 스트림 포인터 초기화
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        # 업로드 스트림 → 임시파일로 복사
        tmp.write(file.file.read())
        tmp_path = tmp.name

    try:
        text_parts = []
        with pdfplumber.open(tmp_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ""
                if t.strip():
                    text_parts.append(t)
                if sum(len(x) for x in text_parts) >= limit_chars:
                    break
        text = "\n\n".join(text_parts).strip()
        if not text:
            text = "(PDF 텍스트 추출 실패 — 스캔본일 수 있습니다.)"
        return text[:limit_chars]
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

def encode_image_to_data_url(file: UploadFile) -> str:
    file.file.seek(0)
    mime = file.content_type or "image/png"
    b64 = base64.b64encode(file.file.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


SYSTEM_PROMPT = (
    "당신은 한국 전세사기 문서 분석 전문가입니다. "
    "입력된 문서(PDF 또는 이미지)를 분석하여 전세사기 위험 요소를 평가하세요. "
    "반드시 아래 JSON 형식으로만 출력하세요.모든 필드는 반드시 채워야 합니다(null 금지). 법적 핵심 문장. 없더라도 문서 내용에서 최대한 유추하세요. 판례 검색용 핵심 쿼리인 input도 문서 내용이 불충분해도 문맥상 생성하세요.\n\n"
    "{\n"
    '  "law_input": string,\n'
    '  "case_input": string,\n'
    '  "rating": {\n'
    '     "label": "좋아요"|"괜찮아요"|"별로예요",\n'
    '     "reasons": [string, string, string]\n'
    "  }\n"
    "}\n"
    "주의: null, 빈 문자열, 불명확 등의 값 없이 반드시 문장으로 출력할 것.\n"
)

@app.post("/gpt/analyze", summary="GPT 전세사기 문서 분석", tags=["gpt"])
async def analyze_with_gpt(files: list[UploadFile] = File(...)):

    results = []
    for file in files:
        mime = file.content_type or guess_mime(file.filename)
        modality = "image" if mime in IMG_MIME else ("pdf" if "pdf" in mime else "other")

        try:
            if modality == "pdf":
                text = read_pdf_text(file)
                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"다음 텍스트를 분석하세요:\n{text}"}
                ]
            elif modality == "image":
                data_url = encode_image_to_data_url(file)
                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": [
                        {"type": "text", "text": "다음 이미지를 분석하세요."},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ]}
                ]
            else:
                text = (await file.read()).decode("utf-8", errors="ignore")
                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"다음 텍스트를 분석하세요:\n{text}"}
                ]

            resp = client.chat.completions.create(
                model=GPT_MODEL,
                messages=messages,
                max_tokens=900,
            )
            content = resp.choices[0].message.content
            try:
                parsed = json.loads(re.sub(r"```json|```", "", content).strip())
            except:
                parsed = {"parse_error": True, "raw": content}

            # 정제된 결과
            rating = parsed.get("rating", {})
            reasons = rating.get("reasons", [])
            if isinstance(reasons, str):
                reasons = [reasons]
            reasons = [r for r in reasons if r][:3]

            results.append({
                "filename": file.filename,
                "mime": mime,
                "modality": modality,
                "law_input": parsed.get("law_input"),
                "case_input": parsed.get("case_input"),
                "rating": {
                    "label": rating.get("label"),
                    "reasons": reasons
                }
            })

        except Exception as e:
            results.append({
                "filename": file.filename,
                "error": str(e)
            })

    return {"items": results}