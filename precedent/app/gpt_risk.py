# precedent/app/gpt_risk.py
from __future__ import annotations
import os, re, json, base64, tempfile
from typing import List, Dict, Any, Tuple
from mimetypes import guess_type

import pdfplumber
import httpx
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, AnyHttpUrl, Field
from openai import OpenAI

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
if not OPENAI_API_KEY.startswith("sk-"):
    raise RuntimeError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
_oai = OpenAI(api_key=OPENAI_API_KEY)

RISK_MODEL = os.getenv("GPT_RISK_MODEL", "gpt-4o-mini")
IMG_MIME = {"image/png", "image/jpeg", "image/webp", "image/heic", "image/heif"}

router = APIRouter(prefix="/gpt")

def _guess_mime(fn: str) -> str:
    mt, _ = guess_type(fn)
    return mt or "application/octet-stream"

async def _fetch_url(url: str, timeout_s: int = 60) -> Tuple[bytes, str, str]:
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout_s) as client:
        r = await client.get(url)
    if r.status_code == 403 and ("AccessDenied" in r.text or "ExpiredToken" in r.text):
        raise HTTPException(status_code=400, detail="S3 프리사인드 URL이 만료되었습니다. 새 링크로 다시 시도하세요.")
    if r.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"URL 요청 실패({r.status_code}).")

    content = r.content
    cd = r.headers.get("Content-Disposition", "")
    filename = None
    if "filename=" in cd:
        filename = cd.split("filename=")[-1].strip('"; ')
    if not filename:
        from urllib.parse import urlparse, unquote
        path = urlparse(url).path
        filename = unquote(path.split("/")[-1]) or "downloaded"
    mime = r.headers.get("Content-Type") or _guess_mime(filename)
    return content, mime, filename

def _read_pdf_text_bytes(content: bytes, limit_chars: int = 18000) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(content)
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
        text = "\n\n".join(parts).strip() or "(PDF 텍스트 추출 실패 — 스캔본일 수 있습니다.)"
        return text[:limit_chars]
    finally:
        try: os.remove(tmp_path)
        except OSError: pass

def _encode_image_bytes_to_data_url(content: bytes, mime: str) -> str:
    b64 = base64.b64encode(content).decode("utf-8")
    return f"data:{mime};base64,{b64}"

def _json_only(s: str) -> Dict[str, Any]:
    s = re.sub(r"^```json\s*|```$", "", s.strip())
    try:
        return json.loads(s)
    except Exception:
        return {"parse_error": True, "raw": s}

# -------- GPT 프롬프트 --------
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

# -------- 입력 모델 --------
class AnalyzeUrlsIn(BaseModel):
    urls: List[AnyHttpUrl] = Field(..., description="분석할 파일 URL 배열")

# -------- 라우터 --------
@router.post("/extract_risks", summary="계약서 위험 문장 추출 (URL 전용 최소 응답)")
async def extract_risks_urls(payload: AnalyzeUrlsIn = Body(...)):
    if not payload.urls:
        raise HTTPException(status_code=400, detail="urls must not be empty")

    items_out: List[Dict[str, Any]] = []
    for url in payload.urls:
        u = str(url)
        try:
            content, mime, _filename = await _fetch_url(u)
            modality = "image" if mime in IMG_MIME else ("pdf" if "pdf" in mime else "other")

            if modality == "pdf":
                text = _read_pdf_text_bytes(content)
                res = _risks_from_text(text)
            elif modality == "image":
                data_url = _encode_image_bytes_to_data_url(content, mime)
                res = _risks_from_image(data_url)
            else:
                try:
                    text = content.decode("utf-8", errors="ignore")
                except Exception:
                    text = ""
                res = _risks_from_text(text)

            rs = res.get("risky_sentences") or []
            if isinstance(rs, dict): rs = [rs]

            cleaned: List[Dict[str, str]] = []
            for r in rs[:20]:
                if not isinstance(r, dict): continue
                sentence = (r.get("sentence") or "").strip() or "핵심 문장 식별 어려움"
                reason   = (r.get("reason") or "").strip()   or "문맥상 위험 사유 추정"
                label    = (r.get("risk_label") or "").strip() or "중간"
                cleaned.append({"sentence": sentence, "reason": reason, "risk_label": label})

            items_out.append({"fileurl": u, "risky_sentences": cleaned})

        except HTTPException as he:
            items_out.append({"fileurl": u, "risky_sentences": [
                {"sentence": "처리 중 오류 발생", "reason": he.detail, "risk_label": "낮음"}
            ]})
        except Exception as e:
            items_out.append({"fileurl": u, "risky_sentences": [
                {"sentence": "처리 중 오류 발생", "reason": str(e), "risk_label": "낮음"}
            ]})

    return {"items": items_out}
