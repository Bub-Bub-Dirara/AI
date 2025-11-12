# precedent/app/gpt_risk.py
from __future__ import annotations
import os
import re
import json
import base64
import tempfile
from typing import List, Optional, Dict, Any, Tuple

import pdfplumber
import httpx
from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field, AnyHttpUrl
from mimetypes import guess_type
from openai import OpenAI

from dotenv import load_dotenv
load_dotenv()

# --------- 설정 ----------
GPT_MODEL = "gpt-4o-mini"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
client = OpenAI(api_key=OPENAI_API_KEY)

IMG_MIME = {"image/png", "image/jpeg", "image/webp", "image/heic", "image/heif"}

LABEL_TO_CODE = {"별로예요": "B", "괜찮아요": "M", "좋아요": "G"}
CODE_TO_LABEL = {v: k for k, v in LABEL_TO_CODE.items()}

_VALID_KINDS = {"contract", "sms", "deposit", "me", "landlord", "other"}

# --------- 유틸 ----------
def _guess_mime_from_name(name: str) -> str:
    mt, _ = guess_type(name or "")
    return mt or "application/octet-stream"

def _encode_image_to_data_url_bytes(content: bytes, mime: str) -> str:
    b64 = base64.b64encode(content).decode("utf-8")
    return f"data:{mime};base64,{b64}"

def _read_pdf_text_bytes(content: bytes, limit_chars: int = 15000) -> str:
    """바이트 기반 PDF 텍스트 추출 (pdfplumber)."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        text_parts: List[str] = []
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

def _nz(s: Optional[str], fallback: str) -> str:
    s = (s or "").strip()
    return s if s else fallback

def _validate_kind(v: Optional[str]) -> str:
    v = (v or "").strip().lower()
    return v if v in _VALID_KINDS else "other"

def _normalize_rating_and_kind(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """필수 필드 보정 + 라벨 코드화(B/M/G) + kind 보정"""
    parsed["law_input"]  = _nz(parsed.get("law_input"),  "계약서의 임대인·보증금·등기부 권리관계 관련 문장을 중심으로 검토 요청.")
    parsed["case_input"] = _nz(parsed.get("case_input"), "보증금 미반환·대항력·우선변제권·확정일자 관련 판례 중심 검색.")
    kind = _validate_kind(parsed.get("kind"))

    rating = parsed.get("rating") or {}
    label_text = _nz(rating.get("label"), "괜찮아요")
    # 이미 B/M/G 코드면 유지, 아니면 변환
    code = label_text if label_text in {"B", "M", "G"} else LABEL_TO_CODE.get(label_text, "M")

    reasons = rating.get("reasons", [])
    if isinstance(reasons, str):
        reasons = [reasons]
    reasons = [r for r in reasons if r][:3] or [
        "등기부 권리분석 필요.",
        "확정일자/전입일 확인 필요.",
        "선순위 담보권 여부 확인 필요.",
    ]

    return {
        "kind": kind,
        "law_input": parsed["law_input"],
        "case_input": parsed["case_input"],
        "rating": {"label": code, "reasons": reasons},
    }

async def _fetch_url(url: str, timeout_s: int = 20) -> Tuple[bytes, str, str]:
    """
    URL에서 파일을 받아 (content, mime, filename)을 반환.
    S3 프리사인드 만료/권한 오류를 감지해 친절한 메시지로 변환.
    """
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout_s) as http:
        r = await http.get(url)

    # S3 만료/권한: 403 + XML 본문
    if r.status_code == 403 and (r.headers.get("Content-Type", "").startswith("application/xml") or r.text.strip().startswith("<Error")):
        text = r.text
        if "AccessDenied" in text and ("Request has expired" in text or "ExpiredToken" in text):
            raise HTTPException(status_code=400, detail="S3 프리사인드 URL이 만료되었습니다. 새 링크로 다시 시도하세요.")
        raise HTTPException(status_code=400, detail="S3 접근이 거부되었습니다. URL이나 권한을 확인하세요.")
    if r.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"URL 요청 실패({r.status_code}).")

    content = r.content

    # 파일명 추정
    cd = r.headers.get("Content-Disposition", "")
    filename = None
    if "filename=" in cd:
        filename = cd.split("filename=")[-1].strip('"; ')
    if not filename:
        try:
            from urllib.parse import urlparse, unquote
            path = urlparse(url).path
            filename = unquote(path.split("/")[-1]) or "downloaded"
        except Exception:
            filename = "downloaded"

    mime = r.headers.get("Content-Type") or _guess_mime_from_name(filename)
    return content, mime, filename

async def _analyze_bytes(content: bytes, mime: str) -> Dict[str, Any]:
    """바이트+MIME을 받아 모델 호출 메시지 구성/전송 및 결과 정규화 반환"""
    if "pdf" in mime:
        text = _read_pdf_text_bytes(content)
        user_msg = f"다음 텍스트를 분석하세요:\n{text}"
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]
    elif mime in IMG_MIME:
        data_url = _encode_image_to_data_url_bytes(content, mime)
        user_msg = "[이미지 1장 첨부: data_url]"
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": "다음 이미지를 분석하세요."},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]},
        ]
    else:
        try:
            text = content.decode("utf-8", errors="ignore")
        except Exception:
            text = ""
        user_msg = f"다음 텍스트를 분석하세요:\n{text}"
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]

    resp = client.chat.completions.create(
        model=GPT_MODEL,
        messages=messages,
        max_tokens=900,
        response_format={"type": "json_object"},  # JSON 강제
    )
    content_text = resp.choices[0].message.content
    try:
        parsed = json.loads(re.sub(r"```json|```", "", content_text).strip())
    except Exception:
        parsed = {"parse_error": True, "raw": content_text}

    norm = _normalize_rating_and_kind(parsed)
    # 분석에 사용된 프롬프트 메타(디버깅/투명성용)
    norm["prompt"] = {
        "model": GPT_MODEL,
        "system": SYSTEM_PROMPT,
        "user_preview": user_msg[:500],
    }
    return norm

SYSTEM_PROMPT = (
    "당신은 한국 전세사기 문서 분석 전문가입니다. "
    "입력된 문서(PDF 또는 이미지)를 분석하여 전세사기 위험 요소를 평가하세요. "
    "반드시 아래 JSON 형식으로만 출력하세요. 모든 필드는 반드시 채워야 합니다(null 금지). "
    "문서 내용·파일명·URL의 힌트를 활용해 문서 유형(kind)을 아래 6개 중 하나로 분류하세요.\n\n"
    "{\n"
    '  "kind": "contract"|"sms"|"deposit"|"me"|"landlord"|"other",\n'
    '  "law_input": string,\n'
    '  "case_input": string,\n'
    '  "rating": {\n'
    '     "label": "좋아요"|"괜찮아요"|"별로예요",\n'
    '     "reasons": [string, string, string]\n'
    "  }\n"
    "}\n"
    "주의: null, 빈 문자열, 불명확 등의 값 없이 반드시 문장으로 출력할 것.\n"
)

# --------- 입력 스키마 ----------
class AnalyzeUrlsIn(BaseModel):
    urls: List[AnyHttpUrl] = Field(..., description="분석할 파일 URL 배열")

# --------- 라우터 ----------
gpt_router = APIRouter(prefix="/gpt", tags=["gpt"])

@gpt_router.post("/analyze", summary="전세사기 문서 분석 (URL 여러 개 전용)")
async def analyze_with_gpt_urls(payload: AnalyzeUrlsIn = Body(...)):
    if not payload.urls:
        raise HTTPException(status_code=400, detail="urls must not be empty")

    results: List[Dict[str, Any]] = []
    for url in payload.urls:
        u = str(url)
        try:
            content, mime, _detected_name = await _fetch_url(u)
            normalized = await _analyze_bytes(content, mime)
            results.append({
                "fileurl": u,  # ✅ URL 그대로 반환
                "mime": mime,
                "modality": ("image" if mime in IMG_MIME else ("pdf" if "pdf" in mime else "other")),
                "kind": normalized["kind"],  # ✅ GPT 분류
                "law_input":  normalized["law_input"],
                "case_input": normalized["case_input"],
                "rating": {
                    "label":   normalized["rating"]["label"],   # G/M/B
                    "reasons": normalized["rating"]["reasons"],
                },
                "prompt": normalized.get("prompt"),
            })
        except HTTPException as he:
            results.append({"fileurl": u, "kind": "other", "error": he.detail})
        except Exception as e:
            results.append({"fileurl": u, "kind": "other", "error": str(e)})

    return {"items": results}
