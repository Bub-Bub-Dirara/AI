import argparse, numpy as np, pandas as pd, faiss, json
from sentence_transformers import SentenceTransformer

def load_index(path):
    index = faiss.read_index(f"{path}/faiss.index")
    meta = pd.read_parquet(f"{path}/meta.parquet")
    with open(f"{path}/model.json","r",encoding="utf-8") as f:
        model_name = json.load(f)["model"]
    model = SentenceTransformer(model_name)
    return index, meta, model

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--q", required=True)
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--index_dir", default="index")
    ap.add_argument("--court", nargs="*")
    ap.add_argument("--from_date")
    ap.add_argument("--to_date")
    args = ap.parse_args()

    index, meta, model = load_index(args.index_dir)

    # 날짜 문자열 정렬용 보정(간단)
    df = meta.copy()
    if args.court and "법원명" in df.columns:
        df = df[df["법원명"].isin(args.court)]
    if "선고일자" in df.columns:
        # 선고일자가 YYYY.MM.DD 형태면 -로 통일
        df["선고일자"] = df["선고일자"].astype(str).str.replace(".", "-", regex=False)
        if args.from_date:
            df = df[df["선고일자"] >= args.from_date.replace(".","-")]
        if args.to_date:
            df = df[df["선고일자"] <= args.to_date.replace(".","-")]

    qv = model.encode([args.q], normalize_embeddings=True)
    D,I = index.search(np.array(qv).astype("float32"), args.k*20)
    I0, S0 = I[0], D[0]

    if len(df) != len(meta):
        keep = set(df.index.tolist())
        filt = [(i,s) for i,s in zip(I0,S0) if i in keep]
        I0, S0 = zip(*filt) if filt else ([],[])

    for rank,(i,s) in enumerate(list(zip(I0,S0))[:args.k], start=1):
        row = meta.iloc[i]
        title = row.get("사건명","")
        date  = str(row.get("선고일자",""))
        court = row.get("법원명","")
        snippet = (row.get("본문","")[:200] + "…").replace("\n"," ")
        print(f"[{rank}] {title} | {court} {date} | score={s:.3f}")
        print(f"     {snippet}")

if __name__ == "__main__":
    main()
