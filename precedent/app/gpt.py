from __future__ import annotations
import os
import re
import json
import base64
import tempfile
from pathlib import Path
from typing import List

import pdfplumber
from fastapi import APIRouter, UploadFile, File
from mimetypes import guess_type
from openai import OpenAI

GPT_MODEL = "gpt-4o-mini"
GPT_API_KEY = "sk-p내키A"
client = OpenAI(api_key=GPT_API_KEY)

IMG_MIME = {"image/png", "image/jpeg", "image/webp", "image/heic", "image/heif"}

def _guess_mime(filename: str) -> str:
    mt, _ = guess_type(filename)
    return mt or "application/octet-stream"

def _encode_image_to_data_url(file: UploadFile) -> str:
    file.file.seek(0)
    mime = file.content_type or "image/png"
    b64 = base64.b64encode(file.file.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"

def _read_pdf_text(file: UploadFile, limit_chars: int = 15000) -> str:
    """OS 독립 임시파일로 저장 후 pdfplumber로 텍스트 추출"""
    file.file.seek(0)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(file.file.read())
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

SYSTEM_PROMPT = (
    "당신은 한국 전세사기 문서 분석 전문가입니다. "
    "입력된 문서(PDF 또는 이미지)를 분석하여 전세사기 위험 요소를 평가하세요. "
    "반드시 아래 JSON 형식으로만 출력하세요. 모든 필드는 반드시 채워야 합니다(null 금지). "
    "법적 핵심 문장과 판례 검색용 핵심 쿼리도 문서 내용이 불충분해도 문맥상 생성하세요.\n\n"
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

gpt_router = APIRouter(prefix="/gpt", tags=["gpt"])

@gpt_router.post("/analyze", summary="GPT 전세사기 문서 분석")
async def analyze_with_gpt(files: list[UploadFile] = File(...)):
    results = []
    for file in files:
        mime = file.content_type or _guess_mime(file.filename)
        modality = "image" if mime in IMG_MIME else ("pdf" if "pdf" in mime else "other")

        try:
            if modality == "pdf":
                text = _read_pdf_text(file)
                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"다음 텍스트를 분석하세요:\n{text}"}
                ]
            elif modality == "image":
                data_url = _encode_image_to_data_url(file)
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

@gpt_router.get("/health")
def gpt_health():
    return {"gpt_model": GPT_MODEL, "ok": True}
