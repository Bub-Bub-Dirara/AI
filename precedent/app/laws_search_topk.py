# src/laws_search_topk.py
from __future__ import annotations
import json, re, textwrap
from pathlib import Path
from typing import Any, Dict, List, Tuple, Iterable

import numpy as np
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer

# ===================== 전세사기 특화 사전 =====================


RISK_KEYWORDS = [
    "전세","임대차","보증금","계약금","가계약","가계약금","선계약금","청약금",
    "중도금","잔금","분할지급","분납","부분지급","나눠서 지급","분할 송금",
    "선입금","선납","선결제","입금","송금","이체","입금 요청","입금 독촉","급하게 입금","급히 입금",
    "지급유예","지급 연기","대여","변제","반환","반환청구","지급청구",
    "위약금","위약벌","지연손해금","연체","연체료","손해배상","불이행","채무불이행",
    "기망","사기","허위","사취","횡령","배임",
    "전세권","확정일자","확정일자부여","전입","전입신고",
    "근저당","담보","담보권","말소기준","압류","가압류","가처분","경매","배당","낙찰",
    "등기부등본","권리분석","말소","설정","말소기준권리",
    "특약","계약해제","계약해지","중도해지","무효","취소","해제권","동시이행항변",
    "명의신탁","전대","재임대","용도제한","관리비","공과금","원상복구","하자","수리",
    "열쇠인도","입주지연","확약서","계약서원본",
    "피해자","구제","지원","주거안정","보증보험","보증가입","대위변제","HUG","주택도시보증공사",
]

# 위험 문구(연어/구문) — 발견 시 강한 가점
RISK_PHRASES = [
    "계약금 분할 지급","계약금 분할지급","보증금 분할 지급","보증금 분할지급",
    "선입금 요구","선납 요구","입금 독촉","급하게 입금","급히 입금",
    "가계약금 입금","가계약 먼저","계약서 나중","등기 후 지급",
    "확정일자 없이","전입 지연","근저당 설정 예정","말소기준권리 존재",
]

# 질의 동의어/표현 확장
ALIASES = {
    "계약금": ["가계약금","선계약금","청약금","계약금"],
    "입금": ["입금","송금","이체","선입금","선납","선결제"],
    "분할지급": ["분할지급","분납","부분지급","나눠서 지급","분할 송금"],
    "보증금": ["보증금","전세보증금","임대보증금"],
    "사기": ["사기","기망","사취","허위"],
}

# 메인 핵심 법률명(타이틀 부스트)
TITLE_BOOST_LAWS = [
    "주택임대차보호법",
    "주택임대차보호법 시행령",
    "전세사기피해자 지원 및 주거안정에 관한 특별법",
    "전세사기피해자 지원 및 주거안정에 관한 특별법 시행령",
    "주택도시보증공사법",
    "주택공급에 관한 규정",
    # 기반/연계 법률(전세사기 맥락상 중요)
    "민법",            # 임대차·계약·하자·해제/해지의 기본
    "민사집행법",      # 경매/배당/집행
    "형법",            # 사기·기망 처벌
]

DOWNWORDS = {
    "위원회","주택임대차위원회","조정위원회","구성","심의","조정서의 작성","벌칙 적용 시 공무원 의제"
}

FOCUS_NEEDLES = {
    "계약금","가계약금","분할지급","분납","선입금","선납","보증금","확정일자","근저당","해제","해지","사기","기망"
}

_token_pat = re.compile(r"[가-힣A-Za-z0-9]+")
def _tokenize(s: str) -> List[str]:
    return _token_pat.findall(s or "")

def _load_json(path: str | Path) -> Any:
    p = Path(path)
    if p.suffix.lower() == ".jsonl":
        out = []
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

def _expand_query_tokens(tokens: Iterable[str]) -> set[str]:
    tokens = set(tokens)
    out = set(tokens)
    for base, alts in ALIASES.items():
        if base in tokens or any(a in tokens for a in alts):
            out.update([base, *alts])
    return out

class LawRetriever:
    def __init__(
        self,
        meta_path: str | Path | None = None,
        corpus_path: str | Path = "index/laws_preprocessed.json",
        max_features: int = 140_000,
    ):
        self.base_dir = Path(".").resolve()
        self.meta_path = self._resolve(meta_path) if meta_path else None
        self.corpus_path = self._resolve(corpus_path)

        corp_list = _load_json(self.corpus_path)
        meta_list = (
            _load_json(self.meta_path)
            if self.meta_path and Path(self.meta_path).exists()
            else [{} for _ in corp_list]
        )

        N = min(len(meta_list), len(corp_list))
        meta_list = meta_list[:N]; corp_list = corp_list[:N]

        self.corpus_rows: List[Dict[str, Any]] = []
        raw_docs: List[str] = []
        bm25_docs: List[List[str]] = []

        for i in range(N):
            m = meta_list[i] if isinstance(meta_list[i], dict) else {}
            c = corp_list[i]
            if isinstance(c, dict):
                law_name  = c.get("law_name", m.get("law_name", "")) or ""
                article_no = str(c.get("article_no", m.get("article_no", "")) or "")
                text = c.get("text", "") or ""
            else:
                law_name = m.get("law_name", "") or ""
                article_no = str(m.get("article_no", "") or "")
                text = str(c or "")

            self.corpus_rows.append({
                "idx": i,
                "law_name": law_name,
                "article_no": article_no,
                "text": text,
            })
            
            title_tokens = _tokenize(f"{law_name} {article_no}")
            combined = " ".join(title_tokens) + " " + text
            raw_docs.append(combined)
            bm25_docs.append(_tokenize(combined))

        # 조회 맵
        self.body: Dict[Tuple[str, str], str] = {
            (r["law_name"], r["article_no"]): r["text"] for r in self.corpus_rows
        }

        self.vectorizer = TfidfVectorizer(
            tokenizer=_tokenize, lowercase=False, ngram_range=(1, 2),
            max_features=max_features,
        )
        self.vecs = self.vectorizer.fit_transform(raw_docs)

        self.bm25 = BM25Okapi(bm25_docs)

    def _resolve(self, p: str | Path | None) -> Path | None:
        if p is None: return None
        p = Path(p)
        if p.is_absolute(): return p
        cand = self.base_dir / p
        if cand.exists(): return cand
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {p}")

    def embed_query(self, text: str):
        return self.vectorizer.transform([text])

    # ---------- 보너스/페널티 ----------
    def _keyword_bonus(self, query: str, law_text: str) -> float:
        q = {k for k in RISK_KEYWORDS if k in (query or "")}
        t = {k for k in RISK_KEYWORDS if k in (law_text or "")}
        if not q: return 0.0
        return min(1.0, len(q & t) / max(1, len(q)))

    def _phrase_bonus(self, query: str, law_text: str) -> float:
        hits = 0
        text = (law_text or "")
        qtext = (query or "")
        for ph in RISK_PHRASES:
            if ph in text or ph in qtext:
                hits += 1
        return min(1.0, hits / 3.0)  # 최대 1.0

    def _title_bonus(self, law_name: str) -> float:
        return 1.0 if any(k in (law_name or "") for k in TITLE_BOOST_LAWS) else 0.0

    def _down_penalty(self, law_text: str) -> float:
        # 절차/위원회 중심 용어가 많으면 감점
        return 1.0 if any(w in (law_text or "") for w in DOWNWORDS) else 0.0

    # ---------- 검색 ----------
    def search(self, text: str, top_k: int = 8, min_score: float = 0.05):
        # TF-IDF (0~1)
        q = self.embed_query(text)
        sims = (self.vecs @ q.T).toarray().ravel()
        cos = (sims - sims.min()) / (sims.max() - sims.min() + 1e-9)

        # BM25 (0~1)
        bm = np.asarray(self.bm25.get_scores(_tokenize(text)), dtype=np.float32)
        bm_norm = (bm - bm.min()) / (bm.max() - bm.min() + 1e-9)

        # 확장 토큰 기반 soft boost/penalty
        q_tokens = _expand_query_tokens(_tokenize(text))
        needles = q_tokens & FOCUS_NEEDLES

        kw  = np.zeros_like(cos, dtype=np.float32)
        phr = np.zeros_like(cos, dtype=np.float32)
        ttl = np.zeros_like(cos, dtype=np.float32)
        soft = np.zeros_like(cos, dtype=np.float32)
        down = np.zeros_like(cos, dtype=np.float32)

        for i, r in enumerate(self.corpus_rows):
            txt, law = r["text"], r["law_name"]
            kw[i]   = self._keyword_bonus(text, txt)
            phr[i]  = self._phrase_bonus(text, txt)
            ttl[i]  = self._title_bonus(law)
            down[i] = self._down_penalty(txt)
            if needles and any(n in txt for n in needles):
                soft[i] = 1.0

        if soft.max() > 0:
            soft = (soft - soft.min()) / (soft.max() - soft.min() + 1e-9)
        if down.max() > 0:
            down = (down - down.min()) / (down.max() - down.min() + 1e-9)

        # 가중합(전세사기 특화)
        final = (
            0.48 * cos +        # TF-IDF
            0.27 * bm_norm +    # BM25
            0.12 * kw +         # 키워드 일치
            0.07 * phr +        # 위험 문구 일치
            0.03 * ttl +        # 법명 부스트(완화)
            0.06 * soft -       # 핵심 토큰 포함 가점
            0.03 * down         # 절차/위원회성 감점
        )
        final = np.clip(final, 0, 1) * 100.0

        n = min(top_k, len(final))
        idx = np.argpartition(-final, n - 1)[:n]
        idx = idx[np.argsort(-final[idx])]

        hits = [
            (int(i), float(final[i]), float(cos[i]), float(bm_norm[i]),
             float(kw[i]), float(phr[i]), float(ttl[i]),
             float(soft[i]), float(down[i]))
            for i in idx
        ]
        cutoff = min_score * 100.0
        return [h for h in hits if h[1] >= cutoff]

    def pretty(self, text: str, top_k: int = 5, min_score: float = 0.05) -> List[Dict[str, Any]]:
        hits = self.search(text, top_k=top_k, min_score=min_score)
        out: List[Dict[str, Any]] = []
        for rank, (i, f, c, b, k, p, t, s, d) in enumerate(hits, start=1):
            r = self.corpus_rows[i]
            law, art, raw = r["law_name"], str(r["article_no"]), r["text"]
            snippet = raw
            pretty_art = art if art.startswith("제") else (f"제{art}조" if art else "")
            out.append({
                "rank": rank,
                "score": round(f, 1),
                "law_name": law,
                "article_no": pretty_art,
                "snippet": snippet
            })
        return out

# -------------------- (옵션) CLI --------------------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="법령 검색 (전세사기 특화 튜닝)")
    parser.add_argument("--meta", default=None, help="(선택) 메타 JSON 경로")
    parser.add_argument("--corpus", default="index/laws_preprocessed.json", help="본문 JSON 경로")
    parser.add_argument("--topk", type=int, default=8, help="상위 k")
    parser.add_argument("--min", type=float, default=0.05, help="최소 점수 비율(0~1)")
    parser.add_argument("query", nargs="*", help="검색어")
    args = parser.parse_args()

    retriever = LawRetriever(meta_path=args.meta, corpus_path=args.corpus)
    q = " ".join(args.query) if args.query else input("검색어 입력: ").strip()
    results = retriever.pretty(q, top_k=args.topk, min_score=args.min)
    if not results:
        print("검색 결과가 없습니다.")
    else:
        for r in results:
            print(f"[{r['rank']}] {r['law_name']} {r['article_no']} — {r['score']}점 "
                  f"(cos={r['cosine']}, bm25={r['bm25']}, kw={r['kw_bonus']}, "
                  f"phr={r['phrase_bonus']}, ttl={r['title_bonus']}, "
                  f"soft={r['soft_boost']}, down={r['down_penalty']})")
            print(f"  {r['snippet']}\n")