import argparse, json, numpy as np, pandas as pd, faiss, os
from sentence_transformers import SentenceTransformer

MODEL_NAME = "snunlp/KR-SBERT-V40K-klueNLI-augSTS"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/cases_clean.parquet")
    ap.add_argument("--out_dir", default="index")
    args = ap.parse_args()

    df = pd.read_parquet(args.data) if args.data.endswith(".parquet") else pd.read_csv(args.data)
    texts = df["본문"].tolist()

    model = SentenceTransformer(MODEL_NAME)
    emb = model.encode(texts, batch_size=128, normalize_embeddings=True, show_progress_bar=True)

    dim = emb.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(emb.astype("float32"))

    os.makedirs(args.out_dir, exist_ok=True)
    faiss.write_index(index, f"{args.out_dir}/faiss.index")

    meta_cols = [c for c in ["판례일련번호","사건명","사건번호","선고일자","법원명","사건종류명","판결유형","본문"] if c in df.columns]
    df[meta_cols].to_parquet(f"{args.out_dir}/meta.parquet", index=False)

    with open(f"{args.out_dir}/model.json","w",encoding="utf-8") as f:
        json.dump({"model": MODEL_NAME}, f, ensure_ascii=False, indent=2)

    print("[index] built & saved.")

if __name__ == "__main__":
    main()
