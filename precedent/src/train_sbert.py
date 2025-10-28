import argparse, json, re, os
import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
from sklearn.preprocessing import MultiLabelBinarizer
from joblib import dump

def weak_labels(text, kw):
    t = re.sub(r"\s+","", str(text)).lower()
    labs = []
    for k, words in kw.items():
        for w in words:
            if re.sub(r"\s+","",w).lower() in t:
                labs.append(k); break
    return labs or ["기타"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--keywords", required=True)
    ap.add_argument("--text_col", default="본문")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--model_out", default="models/multilabel_sbert_lr.joblib")
    ap.add_argument("--encoder", default="jhgan/ko-sroberta-multitask")
    args = ap.parse_args()

    print("[1/6] loading:", args.data)
    df = pd.read_parquet(args.data) if args.data.endswith(".parquet") else pd.read_csv(args.data)
    if args.limit > 0: df = df.head(args.limit).copy()
    print(f"rows = {len(df):,}")

    with open(args.keywords, "r", encoding="utf-8") as f: kw = json.load(f)
    print("[2/6] weak labeling...")
    df["labels"] = df[args.text_col].apply(lambda x: weak_labels(x, kw))
    mlb = MultiLabelBinarizer()
    Y = mlb.fit_transform(df["labels"])
    texts = df[args.text_col].fillna("").tolist()

    print("[3/6] embed with SBERT:", args.encoder)
    enc = SentenceTransformer(args.encoder)
    X = enc.encode(texts, batch_size=64, show_progress_bar=True, convert_to_numpy=True)

    print("[4/6] split...")
    X_train, X_val, Y_train, Y_val = train_test_split(X, Y, test_size=0.2, random_state=42, stratify=Y)

    print("[5/6] train LR (one-vs-rest)...")
    lr = LogisticRegression(max_iter=1000, class_weight="balanced")
    clf = OneVsRestClassifier(lr, n_jobs=-1)
    clf.fit(X_train, Y_train)

    print("[6/6] eval + save...")
    pred = clf.predict(X_val)
    print(classification_report(Y_val, pred, target_names=mlb.classes_, digits=2))

    os.makedirs(os.path.dirname(args.model_out), exist_ok=True)
    dump({"encoder": args.encoder, "clf": clf, "mlb": mlb}, args.model_out)
    print("saved →", args.model_out)

if __name__ == "__main__":
    main()
