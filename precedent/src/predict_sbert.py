import argparse, re
from joblib import load
from sentence_transformers import SentenceTransformer

THRESH = 0.50
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/multilabel_sbert_lr.joblib")
    ap.add_argument("--text", required=True)
    args = ap.parse_args()

    bundle = load(args.model)
    enc = SentenceTransformer(bundle["encoder"])
    clf = bundle["clf"]; mlb = bundle["mlb"]

    X = enc.encode([args.text], convert_to_numpy=True)
    probs = clf.predict_proba(X)[0]
    pairs = list(zip(mlb.classes_, probs))
    pairs.sort(key=lambda x: x[1], reverse=True)
    acc = [(l,s) for l,s in pairs if s >= THRESH]

    print("=== Accepted labels ===")
    if not acc: print("(none)")
    else:
        for l,s in acc: print(f"{l}: {s:.3f}")
    print("\n=== Top-5 raw ===")
    for l,s in pairs[:5]: print(f"{l}: {s:.3f}")

if __name__ == "__main__":
    main()
