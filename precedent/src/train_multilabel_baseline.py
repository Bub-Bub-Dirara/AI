import argparse, json, pandas as pd, numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MultiLabelBinarizer
from sklearn.pipeline import Pipeline
from sklearn.metrics import classification_report
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier
import joblib, os

def weak_labels(text, kw):
    t = str(text).lower()
    labs = []
    for k, words in kw.items():
        if any(w.lower() in t for w in words):
            labs.append(k)
    return labs or ["기타"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="../data/cases_clean.parquet")
    ap.add_argument("--keywords", default="labels_keywords.json")
    ap.add_argument("--out", default="../models/multilabel_tfidf_lr.joblib")
    args = ap.parse_args()

    df = pd.read_parquet(args.data) if args.data.endswith(".parquet") else pd.read_csv(args.data)
    df["본문"] = df["본문"].astype(str).fillna("")

    kw = json.load(open(args.keywords, "r", encoding="utf-8"))
    df["labels"] = df["본문"].map(lambda x: weak_labels(x, kw))

    # 멀티라벨에서는 stratify가 리스트를 못 받으므로 대표 라벨(첫 라벨)로 대체
    strat = df["labels"].map(lambda labs: labs[0] if len(labs) > 0 else "기타")

    X_train, X_test, y_train, y_test = train_test_split(
        df["본문"], df["labels"], test_size=0.2, random_state=42, stratify=strat
    )

    mlb = MultiLabelBinarizer()
    Y_train = mlb.fit_transform(y_train)
    Y_test  = mlb.transform(y_test)

    pipe = Pipeline([
        ("tfidf", TfidfVectorizer(max_features=200000, ngram_range=(1,2))),
        ("clf", OneVsRestClassifier(
            LogisticRegression(max_iter=500, class_weight="balanced")
        ))
    ])

    pipe.fit(X_train, Y_train)

    Y_pred = pipe.predict(X_test)
    print(classification_report(Y_test, Y_pred, target_names=mlb.classes_))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    joblib.dump({"pipe": pipe, "mlb": mlb}, args.out)
    print(f"[classify] saved -> {args.out}")

if __name__ == "__main__":
    main()
