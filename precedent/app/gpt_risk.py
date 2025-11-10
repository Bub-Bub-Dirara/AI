# precedent/app/gpt_risk.py
from __future__ import annotations
import os, re, json, base64, tempfile
from typing import List, Dict, Any
from mimetypes import guess_type

import pdfplumber
from fastapi import APIRouter, UploadFile, File
from openai import OpenAI


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "sk-s내 API KEYAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA!!!!!!!!!!!!!!!!!")
if not OPENAI_API_KEY.startswith("sk-"):
    raise RuntimeError("OPENAI_API_KEY 환경변수(또는 파일 내 상수)를 설정하세요.")
_oai = OpenAI(api_key=OPENAI_API_KEY)

ANALYZE_MODEL = os.getenv("GPT_ANALYZE_MODEL", "gpt-4o")   # 필요시 gpt-4o-mini
RISK_MODEL    = os.getenv("GPT_RISK_MODEL",    "gpt-4o")

IMG_MIME = {"image/png", "image/jpeg", "image/webp", "image/heic", "image/heif"}

router = APIRouter(prefix="/gpt", tags=["gpt"])

def _guess_mime(fn: str) -> str:
    mt, _ = guess_type(fn)
    return mt or "application/octet-stream"

def _read_pdf_text(upload: UploadFile, limit_chars: int = 18000) -> str:
    upload.file.seek(0)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(upload.file.read())
        tmp_path = tmp.name
    try:
        parts: List[str] = []
        with pdfplumber.open(tmp_path) as pdf:
            for p in pdf.pages:
                t = p.extract_text() or ""
                if t.strip():
                    parts.append(t)
                if sum(len(x) for x in parts) >= limit_chars:
                    break
        txt = "\n\n".join(parts).strip()
        if not txt:
            txt = "(PDF 텍스트 추출 실패 — 스캔본일 수 있습니다.)"
        return txt[:limit_chars]
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

def _encode_image_data_url(upload: UploadFile) -> str:
    upload.file.seek(0)
    mime = upload.content_type or "image/png"
    b64 = base64.b64encode(upload.file.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"

def _json_only(s: str) -> Dict[str, Any]:
    s = s.strip()
    s = re.sub(r"^```json\s*", "", s)
    s = re.sub(r"^```\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    try:
        return json.loads(s)
    except Exception:
        return {"parse_error": True, "raw": s}

_CAT_RULES = [
    ("계약서",   [r"계약", r"contract", r"agreement", r"임대차", r"전세계약"]),
    ("문자내역", [r"문자", r"메시지", r"sms", r"kakao", r"카카오", r"톡"]),
    ("입금내역", [r"입금", r"이체", r"송금", r"거래내역", r"영수증", r"계좌"]),
]
def _infer_category(filename: str) -> str:
    lower = filename.lower()
    for label, pats in _CAT_RULES:
        for p in pats:
            if re.search(p, lower):
                return label
    return "기타"

SYSTEM_ITEM = (
    "당신은 한국 전세사기/임대차 문서(계약서·문자·입금내역·기타) 분석 전문가입니다.\n"
    "반드시 JSON만 출력하고, null/빈문자열 없이 모든 필드를 채우세요.\n"
    "{\n"
    '  "law_input": string,\n'
    '  "case_input": string,\n'
    '  "rating": {\n'
    '    "label": "좋아요"|"괜찮아요"|"별로예요",\n'
    '    "reasons": [string, string, string]\n'
    "  }\n"
    "}\n"
)
USER_FROM_TEXT = "다음 텍스트를 분석해 위 JSON 형식으로만 출력하세요.\n텍스트---\n{TEXT}\n---끝"
USER_FROM_IMAGE = "다음 이미지를 읽고 핵심 내용을 요약한 뒤, 위 JSON 형식으로만 출력하세요."

RISK_SYSTEM = (
    "당신은 한국 임대차(전세) 문서 위험 분석가입니다. "
    "입력 문서에서 전세사기 관점의 위험 문장을 찾아 설명하세요. "
    "반드시 JSON만 출력합니다:\n"
    "{\n"
    '  "summary_score": number,\n'
    '  "recommendations": [string, ...],\n'
    '  "risky_sentences": [\n'
    '     {"sentence": string, "reason": string, "risk_label": "높음"|"중간"|"낮음", "tags": [string,...]}\n'
    "  ]\n"
    "}\n"
    "null/빈값 금지, 문맥상 최대한 채워 넣으세요."
)
RISK_USER_TEXT  = "다음 텍스트에서 위험 문장을 추출하세요.\n텍스트---\n{TEXT}\n---끝"
RISK_USER_IMAGE = "다음 이미지를 읽고 동일 기준으로 위험 문장을 추출하세요."

def _analyze_from_text(text: str) -> Dict[str, Any]:
    resp = _oai.chat.completions.create(
        model=ANALYZE_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_ITEM},
            {"role": "user", "content": USER_FROM_TEXT.replace("{TEXT}", text)},
        ],
        max_tokens=900,
    )
    obj = _json_only(resp.choices[0].message.content)
    rating = obj.get("rating") or {}
    reasons = rating.get("reasons") or []
    if isinstance(reasons, str):
        reasons = [reasons]
    obj["rating"] = {
        "label": rating.get("label") or "괜찮아요",
        "reasons": [r for r in reasons if r][:3] or ["핵심 근거 보완 필요", "문서 정보 제한", "추가 증빙 권장"]
    }
    obj["law_input"]  = obj.get("law_input")  or "문서 기반 법적 핵심 진술 보완 필요"
    obj["case_input"] = obj.get("case_input") or "임대차 보증금·확정일자·근저당 관련 판례"
    return obj

def _analyze_from_image(data_url: str) -> Dict[str, Any]:
    resp = _oai.chat.completions.create(
        model=ANALYZE_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_ITEM},
            {"role": "user", "content": [
                {"type": "text", "text": USER_FROM_IMAGE},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]},
        ],
        max_tokens=900,
    )
    obj = _json_only(resp.choices[0].message.content)
    rating = obj.get("rating") or {}
    reasons = rating.get("reasons") or []
    if isinstance(reasons, str):
        reasons = [reasons]
    obj["rating"] = {
        "label": rating.get("label") or "괜찮아요",
        "reasons": [r for r in reasons if r][:3] or ["핵심 근거 보완 필요", "이미지 정보 제한", "추가 증빙 권장"]
    }
    obj["law_input"]  = obj.get("law_input")  or "이미지 기반 법적 핵심 진술 보완 필요"
    obj["case_input"] = obj.get("case_input") or "임대차 보증금·확정일자·근저당 관련 판례"
    return obj

def _risks_from_text(text: str) -> Dict[str, Any]:
    resp = _oai.chat.completions.create(
        model=RISK_MODEL,
        messages=[
            {"role": "system", "content": RISK_SYSTEM},
            {"role": "user", "content": RISK_USER_TEXT.replace("{TEXT}", text)},
        ],
        max_tokens=1200,
    )
    return _json_only(resp.choices[0].message.content)

def _risks_from_image(data_url: str) -> Dict[str, Any]:
    resp = _oai.chat.completions.create(
        model=RISK_MODEL,
        messages=[
            {"role": "system", "content": RISK_SYSTEM},
            {"role": "user", "content": [
                {"type": "text", "text": RISK_USER_IMAGE},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]},
        ],
        max_tokens=1200,
    )
    return _json_only(resp.choices[0].message.content)

@router.post("/analyze", summary="문서별 law_input/case_input/판정")
async def analyze(files: List[UploadFile] = File(...)):
    items: List[Dict[str, Any]] = []
    for f in files:
        mime = f.content_type or _guess_mime(f.filename)
        modality = "image" if mime in IMG_MIME else ("pdf" if "pdf" in mime else "other")
        try:
            if modality == "pdf":
                text = _read_pdf_text(f)
                res = _analyze_from_text(text)
            elif modality == "image":
                data_url = _encode_image_data_url(f)
                res = _analyze_from_image(data_url)
            else:
                f.file.seek(0)
                text = f.file.read().decode("utf-8", errors="ignore")
                res = _analyze_from_text(text)

            rating = res.get("rating") or {}
            reasons = rating.get("reasons") or []
            if isinstance(reasons, str):
                reasons = [reasons]
            items.append({
                "filename": f.filename,
                "mime": mime,
                "modality": modality,
                "category": _infer_category(f.filename),
                "law_input":  res.get("law_input"),
                "case_input": res.get("case_input"),
                "rating": {
                    "label": rating.get("label") or "괜찮아요",
                    "reasons": [r for r in reasons if r][:3]
                }
            })
        except Exception as e:
            items.append({"filename": f.filename, "error": str(e)})
    return {"items": items}

@router.post("/extract_risks", summary="계약서 위험 문장 추출(미니멀 응답)")
async def extract_risks(files: List[UploadFile] = File(...)):
    """
    여러 PDF/이미지 업로드 → 파일별 위험 문장(문장/이유/심각도)만 반환
    응답 스키마:
    {
      "items": [
        { "filename": str, "risky_sentences": [ {sentence, reason, risk_label}, ... ] }
      ]
    }
    """
    items_out: List[Dict[str, Any]] = []

    for f in files:
        mime = f.content_type or _guess_mime(f.filename)
        modality = "image" if mime in IMG_MIME else ("pdf" if "pdf" in mime else "other")

        try:
            if modality == "pdf":
                text = _read_pdf_text(f)
                res = _risks_from_text(text)
            elif modality == "image":
                data_url = _encode_image_data_url(f)
                res = _risks_from_image(data_url)
            else:
                f.file.seek(0)
                text = f.file.read().decode("utf-8", errors="ignore")
                res = _risks_from_text(text)

            rs = res.get("risky_sentences") or []
            if isinstance(rs, dict):
                rs = [rs]

            cleaned: List[Dict[str, str]] = []
            for r in rs[:20]:
                if not isinstance(r, dict):
                    continue
                sentence = (r.get("sentence") or "").strip() or "핵심 문장 식별 어려움"
                reason   = (r.get("reason") or "").strip()   or "문맥상 위험 사유 추정"
                label    = (r.get("risk_label") or "").strip() or "중간"
                cleaned.append({
                    "sentence": sentence,
                    "reason": reason,
                    "risk_label": label
                })

            items_out.append({
                "filename": f.filename,
                "risky_sentences": cleaned
            })

        except Exception as e:
            items_out.append({
                "filename": f.filename,
                "risky_sentences": [
                    {
                        "sentence": "처리 중 오류 발생",
                        "reason": str(e),
                        "risk_label": "낮음"
                    }
                ]
            })

    return {"items": items_out}