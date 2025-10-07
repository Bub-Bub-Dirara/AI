import re, argparse, json

R_DATE = r"(19|20)\d{2}[.\-년/ ]\s?\d{1,2}[.\-월/ ]\s?\d{1,2}\s?(일)?"
R_MONEY = r"(\d{1,3}(,\d{3})+|\d+)\s*(원|만원|억원)"
R_RATE  = r"(연\s*)?(\d{1,2}(\.\d+)?)\s?%|(연\s*\d+\s*퍼센트)"
R_MORTG = r"(근저당|근저당권|채권최고액)\s*(\d{1,3}(,\d{3})+|\d+)\s*(원|만원|억원)?"

def extract(text: str):
    def get(pat): return [m.group().strip() for m in re.finditer(pat, text)]
    return {"날짜": get(R_DATE), "금액": get(R_MONEY), "이자율": get(R_RATE), "근저당관련": get(R_MORTG)}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    args = ap.parse_args()
    print(json.dumps(extract(args.text), ensure_ascii=False, indent=2))
