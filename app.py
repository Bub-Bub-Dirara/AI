from fastapi import FastAPI

from be.app.api import router as be_router
from precedent.app.api import router as ai_router

import os

app = FastAPI(title="JeonSafe Unified API")

# 공통 미들웨어(CORS/로그 등) 필요시 여기에서
# from fastapi.middleware.cors import CORSMiddleware
# app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# 엔드포인트 트리
#   /api/...   -> BE (로그인/회원가입/각종 로그 등)
#   /ai/...    -> Precedent (법령/판례, GPT 에이전트)

# 서버 기동 시 DB 테이블 자동 생성
@app.on_event("startup")
def _init_db():
    from be.app.db import Base, engine
    Base.metadata.create_all(bind=engine)

@app.get("/")
def root():
    return {"services": ["/api", "/ai"]}

app.include_router(be_router, prefix="/api")
app.include_router(ai_router, prefix="/api")
