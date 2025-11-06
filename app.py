from fastapi import FastAPI

from be.app.api import router as be_router
from precedent.app.api import router as ai_router

app = FastAPI(title="JeonSafe Monorepo")

# 공통 미들웨어(CORS/로그 등) 필요시 여기에서
# from fastapi.middleware.cors import CORSMiddleware
# app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# 엔드포인트 트리
#   /api/...   -> BE (로그인/회원가입/각종 로그 등)
#   /ai/...    -> Precedent (법령/판례, GPT 에이전트)
app.include_router(be_router)
app.include_router(ai_router)

@app.get("/")
def root():
    return {"services": ["/api", "/ai"]}
