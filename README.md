# AI
AI models and pipelines for analyzing precedents and providing fraud-prevention/legal guidance

'''
precedent/
 ├─ data/
 │   └─ prec_full.csv
 ├─ src/
 │   ├─ preprocess.py
 │   ├─ build_index.py
 │   ├─ search.py
 │   ├─ train_multilabel_baseline.py
 │   ├─ predict_labels.py
 │   ├─ extract_entities.py
 │   └─ labels_keywords.json
 ├─ index/
 ├─ models/
 └─ requirements.txt
'''

'''
cd precedent

# 가상환경
python -m venv .venv
# Windows
.venv\Scrirts\activate
'''

'''
pip install -
'''

'''
pip install -r requirements.txt
python src/build_index.py --data data/cases_clean.parquet --out_dir index

python src/train_multilabel_baseline.py --data data/cases_clean.parquet --keywords src/labels_keywords.json
python src/predict_labels.py --text "채무자가 시효완성 후 일부 변제한 경우 시효이익 포기 인정 여부"
python src/extract_entities.py --text "2016. 2. 6. 150만 원 변제, 이자는 연 20%, 채권최고액 2억 원 근저당권 설정"

'''
'''
cd precedent
python -m venv .venv
'''
# Windows
'''
.venv\Scripts\activate

'''
python -m uvicorn precedent.app.main:app --reload --port 8000
'''


# 2 패키지 설치
'''
pip install -r requirements.txt
'''
# 3 데이터 두기
# 자신의 CSV를 여기에 복사 (파일명은 자유, 아래 명령에서 --in으로 지정)
# 예: data/prec_full.csv

# 4 전처리 -> 인덱스 -> 검색 (산출물은 레포에 포함되지 않으므로 각자 생성)
'''
python src/preprocess.py --in data/prec_full.csv --out data/cases_clean.parquet
python src/build_index.py --data data/cases_clean.parquet --out_dir index
python src/search.py --q "배당이의 전원합의체 시효이익 포기" --k 5

python src/train_multilabel_baseline.py --data data/cases_clean.parquet --keywords src/labels_keywords.json
python src/predict_labels.py --text "시효완성 후 일부 변제의 시효이익 포기 여부"
python src/extract_entities.py --text "150만 원 변제, 연 20%, 채권최고액 2억 원 근저당"
'''


'''
pip install openai pdfplumber fastapi uvicorn python-multipart
'''