import os, sys
from fastapi import FastAPI

CUR = os.path.dirname(os.path.abspath(__file__))

# BE의 'app' 디렉토리를 최우선 탐색 경로에 추가 (from app.core... 가 동작하도록)
BE_ROOT = os.path.join(CUR, "be")
if BE_ROOT not in sys.path:
    sys.path.insert(0, BE_ROOT)

# AI 쪽 소스들도 import 되도록
PRECEDENT_ROOT = os.path.join(CUR, "precedent")
if PRECEDENT_ROOT not in sys.path:
    sys.path.insert(0, PRECEDENT_ROOT)

# 루트 앱: BE
from be.app.main import app as be_app

# 서브 앱: AI (ai의 app 폴더명을 'aiapp'으로 수정함)
from precedent.aiapp.main import app as ai_app

app: FastAPI = be_app
app.mount("/ai", ai_app)
