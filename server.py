# app.py (프로젝트 루트)
from fastapi import FastAPI

# 각 패키지에 __init__.py가 있어야 함 (be/, precedent/ 모두)
from precedent.app.main import router as ai_router      # /precedent/app/api.py가 router를 export
from be.app.routes import router as be_router          # /be/app/routes/__init__.py 등에서 router export

app = FastAPI()

app.include_router(ai_router, prefix="/ai", tags=["AI-Precedent"])
app.include_router(be_router, prefix="/be", tags=["BE"])
