from __future__ import annotations
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from precedent.app.api import ai_router as _ai_router
from be.app.routes import router as be_router

app = FastAPI(title="Project Server")

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,   # 쿠키/세션 쓰면 True
    allow_methods=["*"],      # OPTIONS(프리플라이트) 포함
    allow_headers=["*"],
)

ai_prefix = getattr(_ai_router, "prefix", "") or ""
if ai_prefix.strip():
    app.include_router(_ai_router)  # 이미 prefix가 있으면 그대로
else:
    app.include_router(_ai_router, prefix="/ai", tags=["AI"])

app.include_router(be_router, prefix="/be", tags=["BE"])
