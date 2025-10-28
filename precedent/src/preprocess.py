import pandas as pd, re, html, argparse, os

DROP_COLS = ["상세_JSON","상세_XML","상세_HTML","판례상세링크_절대URL"]
KEEP_COLS = ["판례일련번호","사건명","사건번호","선고일자","법원명",
             "사건종류명","판결유형","판시사항","판결요지","이유"]

def clean_html_text(s: str) -> str:
    if pd.isna(s): return ""
    s = html.unescape(str(s))
    s = re.sub(r"<\s*br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="../data/prec_full.csv")
    ap.add_argument("--out", dest="out", default="../data/cases_clean.parquet")
    args = ap.parse_args()

    if args.inp.lower().endswith((".xls",".xlsx")):
        df = pd.read_excel(args.inp)
    else:
        df = pd.read_csv(args.inp)

    cols = [c for c in df.columns if c not in DROP_COLS]
    df = df[cols]

    cols2 = [c for c in KEEP_COLS if c in df.columns]
    df = df[cols2]

    for c in ["사건명","판시사항","판결요지","이유"]:
        if c in df.columns:
            df[c] = df[c].map(clean_html_text)

    def get(col): return df[col] if col in df.columns else ""
    df["본문"] = (get("사건명") + "\n" + get("판시사항") + "\n" +
                  get("판결요지") + "\n" + get("이유")).str.replace(r"\n{2,}", "\n", regex=True).str.strip()

    df = df[df["본문"].str.len() > 0].copy()

    out = args.out
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if out.lower().endswith(".parquet"):
        df.to_parquet(out, index=False)
    else:
        df.to_csv(out, index=False, encoding="utf-8-sig")

    print(f"[preprocess] rows={len(df)} saved -> {out}")

if __name__ == "__main__":
    main()
