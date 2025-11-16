from __future__ import annotations
import os
import re
import json
import base64
import tempfile
from typing import List, Dict, Any, Tuple
from mimetypes import guess_type

import pdfplumber
import httpx
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, AnyHttpUrl, Field
from openai import OpenAI
from dotenv import load_dotenv

import fitz  # PyMuPDF 

load_dotenv(override=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
if not OPENAI_API_KEY.startswith("sk-"):
    raise RuntimeError("OPENAI_API_KEY가 유효하지 않습니다. 서버에서는 sk- 형태의 키를 사용하세요.")

_oai = OpenAI(api_key=OPENAI_API_KEY)

RISK_MODEL = os.getenv("GPT_RISK_MODEL", "gpt-4o-mini")
IMG_MIME = {"image/png", "image/jpeg", "image/webp", "image/heic", "image/heif"}

router = APIRouter(prefix="/gpt")

RISK_TEXT_TO_CODE = {
    "높음": "B",
    "중간": "M",
    "낮음": "G",
    "high": "B",
    "medium": "M",
    "low": "G",
}

VALID_CODE_LABELS = {"B", "M", "G"}


def _guess_mime(fn: str) -> str:
    mt, _ = guess_type(fn)
    return mt or "application/octet-stream"


async def _fetch_url(url: str, timeout_s: int = 60) -> Tuple[bytes, str, str]:
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout_s) as client:
        r = await client.get(url)

    if r.status_code == 403 and (
        "AccessDenied" in r.text
        or "ExpiredToken" in r.text
        or "Request has expired" in r.text
    ):
        raise HTTPException(400, "S3 프리사인드 URL이 만료되었습니다. 새 링크를 요청하세요.")

    if r.status_code >= 400:
        raise HTTPException(400, f"URL 요청 실패({r.status_code})")

    cd = r.headers.get("Content-Disposition", "")
    filename = None
    if "filename=" in cd:
        filename = cd.split("filename=")[-1].strip('"; ')
    if not filename:
        from urllib.parse import urlparse, unquote
        path = urlparse(url).path
        filename = unquote(path.split("/")[-1]) or "downloaded"

    mime = r.headers.get("Content-Type") or _guess_mime(filename)
    return r.content, mime, filename


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
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _encode_image_bytes_to_data_url(content: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(content).decode('utf-8')}"


def _json_only(s: str) -> Dict[str, Any]:
    s = re.sub(r"^```json\s*|```$", "", s.strip())
    try:
        return json.loads(s)
    except Exception:
        return {"parse_error": True, "raw": s}


def _attach_pdf_positions(content: bytes, risks: List[Dict[str, Any]]) -> None:
    """
    각 risk에 대해 anchor(없으면 sentence)를 기준으로 PDF 내 위치(page, x, y, w, h) 목록을 붙인다.
    positions: [{page, x, y, w, h}] (PDF 원본 좌표 기준)
    """
    if not risks:
        return

    # anchor / sentence 가 하나도 없으면 그냥 리턴
    any_anchor = any((r.get("anchor") or r.get("sentence")) for r in risks)
    if not any_anchor:
        return

    doc = fitz.open(stream=content, filetype="pdf")
    try:
        for r in risks:
            anchor = (r.get("anchor") or r.get("sentence") or "").strip()
            if not anchor:
                continue

            positions: List[Dict[str, float]] = []

            for page_index, page in enumerate(doc):
                rects = page.search_for(anchor)
                if not rects:
                    continue

                for rect in rects:
                    positions.append(
                        {
                            "page": page_index + 1,
                            "x": float(rect.x0),
                            "y": float(rect.y0),
                            "w": float(rect.x1 - rect.x0),
                            "h": float(rect.y1 - rect.y0),
                            "page_width": float(page.rect.width),
                            "page_height": float(page.rect.height),
                        }
                    )

            if positions:
                r["positions"] = positions
            else:
                r["positions"] = []
    finally:
        doc.close()

RISK_SYSTEM = (
    "당신은 한국 임대차(전세/월세) 계약서 전문 위험 분석가입니다. "
    "입력 문서에서 전세사기 관점의 위험 문장을 가능한 한 많이 추출하고, "
    "각 문장에 대해 법적 위험 이유와 판례 검토 쟁점을 상세히 설명하세요.\n\n"
    "★★★ 아주 중요한 규칙 – 절대 어기지 마세요 ★★★\n"
    "1) 'sentence'와 'anchor'에 들어가는 문자열은 반드시 계약서 원문에 실제로 존재하는 구절을 그대로 복사해야 합니다.\n"
    "   - 요약, 의역, 설명용 문장, 새로운 표현을 만들지 마세요.\n"
    "   - 날짜, 금액, 비율, 주소, 이름 등도 문서에 적힌 그대로 사용하세요.\n"
    "   - 문서에 없는 단어, 숫자, 조항, 문장을 새로 지어내거나 추가하면 안 됩니다.\n"
    "2) 문서가 한국어인 경우 모든 필드(sentence, anchor, reason, law_input, case_input)는 한국어로 작성하세요.\n"
    "3) 위험 문장을 찾을 때는 반드시 제공된 텍스트/이미지 안에서만 선택하세요. "
    "   일반적인 상식이나 경험을 근거로 문서에 없는 내용을 상상해서 만들지 마세요.\n"
    "4) 'sentence'는 위험한 내용을 포함하는 한 문장을 원문에서 그대로 복사합니다. "
    "   너무 길다면 위험 핵심이 포함된 한 문장만 선택하세요.\n"
    "5) 'anchor'는 PDF에서 위치를 찾기 위한 짧은 구절(약 5~30자)을 원문 그대로 복사해서 넣습니다. "
    "   가능하면 sentence 안에 포함된 핵심 구절을 선택하세요.\n"
    "6) 문장이 여러 줄에 걸쳐 있어도, 실제 계약서에 보이는 순서와 표현을 그대로 따라야 합니다.\n\n"
    "risk_label 의미:\n"
    "- B: 높은 위험도(보증금 미반환, 대항력 상실, 선순위 근저당 등 치명적 위험)\n"
    "- M: 중간 위험도(분쟁 가능성이 상당하지만 치명적이지는 않은 위험)\n"
    "- G: 낮은 위험도(주의는 필요하지만 비교적 일반적인 위험)\n\n"
    "출력 형식은 반드시 아래 JSON 한 개만 사용해야 합니다:\n"
    "{\n"
    '  "risky_sentences": [\n'
    "    {\n"
    '      "sentence": string,\n'
    '      "anchor": string,\n'
    '      "reason": string,\n'
    '      "risk_label": "B" | "M" | "G",\n'
    '      "law_input": string,\n'
    '      "case_input": string\n'
    "    }\n"
    "  ]\n"
    "}\n\n"
    "추가 규칙:\n"
    "1) risk_label은 반드시 \"B\" 또는 \"M\" 또는 \"G\"만 사용하세요.\n"
    "2) law_input은 한국 임대차 관련 법률 관점에서 2~3문장 정도로 구체적으로 작성합니다.\n"
    "3) case_input은 반드시 질문형 문장으로, 판례 검색용 쿼리처럼 작성합니다. (예: \"~할 수 있는지 여부.\")\n"
    "4) null, 빈 문자열, 빈 배열은 절대 사용하지 마세요.\n"
    "5) 문서가 불완전하더라도 위험 문장은 최소 1개 이상 반드시 생성하세요.\n"
    "6) 의미가 다른 위험 포인트는 가능한 한 많이 추출하되, 동일/유사 의미는 하나로 합치세요. "
    "   (위험 문장은 최대 30개 정도까지 추출해도 괜찮습니다.)\n"
    "7) 'anchor' 필드는 반드시 계약서 원문에 그대로 등장하는 짧은 구절(약 5~30자)을 그대로 복사하여 넣으세요. "
    "   anchor는 PDF에서 해당 위험 문장을 찾는 기준이 되므로, 핵심이 잘 드러나는 부분을 선택하세요.\n"
)

RISK_USER_TEXT = (
    "아래는 임대차 계약서의 일부 텍스트입니다. "
    "반드시 이 텍스트 안에서만 전세사기 관점의 위험 문장을 찾아야 합니다. "
    "텍스트에 나오지 않는 내용(새로운 숫자, 날짜, 조항, 표현 등)은 절대 만들지 마세요.\n\n"
    "텍스트---\n{TEXT}\n---끝"
)

RISK_USER_IMAGE = (
    "다음 계약서/문서 이미지를 읽고, 전세사기 관점에서 "
    "위험해 보이는 문장을 가능한 한 많이 추출하세요.\n"
    "반드시 이미지 안에 실제로 보이는 문장/구절만 사용해야 하며, "
    "이미지에 없는 문장을 새로 만들거나 의역/요약한 문장을 'sentence'나 'anchor'에 넣으면 안 됩니다."
)



def _risks_from_text(text: str) -> Dict[str, Any]:
    resp = _oai.chat.completions.create(
        model=RISK_MODEL,
        max_tokens=2000,
        messages=[
            {"role": "system", "content": RISK_SYSTEM},
            {"role": "user", "content": RISK_USER_TEXT.replace("{TEXT}", text)},
        ],
    )
    return _json_only(resp.choices[0].message.content)


def _risks_from_image(data_url: str) -> Dict[str, Any]:
    resp = _oai.chat.completions.create(
        model=RISK_MODEL,
        max_tokens=2000,
        messages=[
            {"role": "system", "content": RISK_SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": RISK_USER_IMAGE},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
    )
    return _json_only(resp.choices[0].message.content)


# ---------------- Models ----------------

class AnalyzeUrlsIn(BaseModel):
    urls: List[AnyHttpUrl] = Field(..., description="분석할 파일 URL 목록")


# ---------------- Router ----------------

@router.post("/extract_risks", summary="계약서 위험 문장 추출 (URL 기반)")
async def extract_risks_urls(payload: AnalyzeUrlsIn = Body(...)):
    if not payload.urls:
        raise HTTPException(400, "urls must not be empty")

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
            if isinstance(rs, dict):
                rs = [rs]

            # --------------- fallback: 최소 1개 보장 ---------------
            if not rs:
                rs = [
                    {
                        "sentence": "위험 문장 식별 실패",
                        "anchor": "위험 문장 식별 실패",
                        "reason": "계약서에서 명확한 위험 조항을 인식하지 못했습니다.",
                        "risk_label": "G",
                        "law_input": (
                            "보증금 반환 시기, 대항력·우선변제권 확보, 선순위 권리관계(근저당 등)를 중심으로 "
                            "계약서를 다시 검토할 필요가 있습니다."
                        ),
                        "case_input": (
                            "임대인의 선순위 권리 또는 세금 체납 등으로 인해 임차인이 보증금을 전액 회수하지 못한 경우, "
                            "임차인의 계약 해제 및 손해배상 청구가 인정되는지 여부."
                        ),
                    }
                ]

            cleaned: List[Dict[str, Any]] = [] 
            seen: set[tuple[str, str]] = set()

            for r in rs[:50]:
                if not isinstance(r, dict):
                    continue

                sentence = (r.get("sentence") or "").strip()
                anchor = (r.get("anchor") or "").strip()
                reason = (r.get("reason") or "").strip()
                raw_label = (r.get("risk_label") or "").strip()

                if not sentence:
                    sentence = "위험 문장 내용 미상"
                if not reason:
                    reason = "문맥상 임차인에게 불리하게 작용할 수 있는 조항으로 추정됩니다."
                if not anchor:
                    anchor = sentence

                if raw_label in VALID_CODE_LABELS:
                    code_label = raw_label
                elif raw_label in RISK_TEXT_TO_CODE:
                    code_label = RISK_TEXT_TO_CODE[raw_label]
                else:
                    code_label = "M"

                law_input = (r.get("law_input") or "").strip()
                case_input = (r.get("case_input") or "").strip()

                key = (sentence, reason)
                if key in seen:
                    continue
                seen.add(key)

                # law_input 자동 보강
                if not law_input:
                    law_input = (
                        f"{reason} 이 조항은 주택임대차보호법상 보증금 보호 및 우선변제권 확보 측면에서 "
                        "임차인에게 불리하게 작용할 수 있습니다."
                    )

                # case_input 자동 보강 + 질문형 강제
                if not case_input:
                    case_input = (
                        "해당 조항이 존재할 경우 임대인이 보증금 반환을 지연하거나 거부할 때 "
                        "임차인이 계약 해제 및 손해배상을 청구할 수 있는지 여부."
                    )
                if not any(x in case_input for x in ["여부", "가능한지", "수 있는지", "인지"]):
                    case_input = case_input.rstrip(" .") + " 여부."

                cleaned.append(
                    {
                        "sentence": sentence,
                        "anchor": anchor,
                        "reason": reason,
                        "risk_label": code_label,
                        "law_input": law_input,
                        "case_input": case_input,
                        # positions는 나중에 _attach_pdf_positions에서 채움
                    }
                )

            if not cleaned:
                cleaned.append(
                    {
                        "sentence": "위험 문장 식별 실패",
                        "anchor": "위험 문장 식별 실패",
                        "reason": "후처리 과정에서 유효한 위험 문장이 남지 않았습니다.",
                        "risk_label": "G",
                        "law_input": (
                            "보증금, 대항력, 선순위 권리관계 등 기본적인 리스크 요소에 대해 "
                            "전체 계약서를 다시 검토할 필요가 있습니다."
                        ),
                        "case_input": (
                            "계약서에 명시적인 위험 조항이 드러나지 않는 경우에도, "
                            "임차인이 보증금을 온전히 보호받을 수 있는지 여부."
                        ),
                    }
                )

            # PDF인 경우 PyMuPDF로 좌표
            if modality == "pdf":
                _attach_pdf_positions(content, cleaned)

            items_out.append(
                {
                    "fileurl": u,
                    "risky_sentences": cleaned,
                }
            )

        except HTTPException as he:
            items_out.append(
                {
                    "fileurl": u,
                    "risky_sentences": [
                        {
                            "sentence": "처리 중 오류 발생",
                            "anchor": "처리 중 오류 발생",
                            "reason": str(he.detail),
                            "risk_label": "G",
                            "law_input": "URL 오류로 인해 계약서를 분석할 수 없습니다.",
                            "case_input": "입력 URL이 유효하지 않을 경우 동일 계약서에 대해 재분석이 가능한지 여부.",
                            "positions": [],
                        }
                    ],
                }
            )
        except Exception as e:
            items_out.append(
                {
                    "fileurl": u,
                    "risky_sentences": [
                        {
                            "sentence": "처리 중 예외 발생",
                            "anchor": "처리 중 예외 발생",
                            "reason": str(e),
                            "risk_label": "G",
                            "law_input": "서버 내부 오류로 인해 계약서 내용을 정상적으로 분석하지 못했습니다.",
                            "case_input": "분석 시스템 오류 발생 시 동일 계약서의 재분석이 안정적으로 가능한지 여부.",
                            "positions": [],
                        }
                    ],
                }
            )

    return {"items": items_out}
