from __future__ import annotations
from fastapi import FastAPI
from precedent.app.main import ai_router as _ai_router 
from be.app.routes import router as be_router

app = FastAPI(title="Project Server")

ai_prefix = getattr(_ai_router, "prefix", "") or ""
if ai_prefix.strip():
    app.include_router(_ai_router) 
else:
    app.include_router(_ai_router, prefix="/ai", tags=["AI-Precedent"])

# BE 엔드포인트는 항상 /be 아래로
app.include_router(be_router, prefix="/be", tags=["BE"])

