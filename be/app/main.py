from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
from be.app.core.db import Base, engine
from be.app.routes import auth, precheck, chat, upload
from be.app.models import user as user_model
from be.app.models import Base

import logging
from be.app.core.config import settings

logger = logging.getLogger("uvicorn")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(
    title="JeonSafe API",
    version="0.1.0",
    description="전세 계약 사기 위험도 분석, 증거 자료 관리, 법률 상담 지원을 위한 백엔드 REST API",
)

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,     # "*" 쓰려면 credentials는 False여야 함
    allow_credentials=True,    # 쿠키/인증 헤더 쓸 거면 True
    allow_methods=["*"],       # ← 반드시 넣기 (POST 포함 전부 허용)
    allow_headers=["*"],       # ← 반드시 넣기 (Content-Type, Authorization 등)
)

@app.get("/", summary="Health")
def health():
    return {"ok": True, "service": "JeonSafe API"}

# 라우터 등록
app.include_router(auth.router)
app.include_router(precheck.router)
app.include_router(chat.router)
app.include_router(upload.router)

@app.on_event("startup")
def on_startup():
    # models/__init__.py에서 모든 모델이 이미 import되어 메타데이터에 등록됨
    Base.metadata.create_all(bind=engine)
    logger.info(
        f"S3 enabled={settings.s3_enabled} "
        f"region={settings.aws_region} bucket={settings.s3_bucket}"
    )
