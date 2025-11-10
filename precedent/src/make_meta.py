# make_meta.py (precedent 폴더에서)
import pandas as pd
from pathlib import Path
APP_ROOT = Path(__file__).resolve().parent
df = pd.read_parquet(APP_ROOT / "data" / "cases_clean.parquet")  # 없으면 prec_full.csv로 대체
# 필요한 컬럼명은 실제 코드에 맞추세요. 예시:
# 기대 컬럼: id, title, court, date, summary 또는 body
want_cols = []
for c in ["id","title","court","date","summary","body","snippet"]:
    if c in df.columns: want_cols.append(c)
if "id" not in want_cols:
    raise SystemExit("parquet에 id 컬럼이 없습니다. 인덱스의 id와 매핑될 식별자가 필요합니다.")
out = APP_ROOT / "index" / "meta.jsonl"
out.parent.mkdir(parents=True, exist_ok=True)
with out.open("w", encoding="utf-8") as f:
    for _, row in df[want_cols].iterrows():
        rec = {k: (None if pd.isna(row[k]) else row[k]) for k in want_cols}
        # 문자열 강제 변환이 필요하면 여기서 처리
        import json
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
print("Wrote:", out)
