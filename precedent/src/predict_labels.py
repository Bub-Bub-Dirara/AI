import joblib, argparse, numpy as np

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    ap.add_argument("--model", default="../precedent/models/multilabel_tfidf_lr.joblib")
    args = ap.parse_args()

    obj = joblib.load(args.model)
    pipe, mlb = obj["pipe"], obj["mlb"]

    # OneVsRest + LR 이면 (1, C) 확률이 바로 나옴
    probs = pipe.predict_proba([args.text])[0]  # shape: (num_labels,)

    top = sorted(zip(mlb.classes_, probs), key=lambda x: x[1], reverse=True)[:5]
    for lab, p in top:
        print(f"{lab}: {p:.3f}")

if __name__ == "__main__":
    main()
