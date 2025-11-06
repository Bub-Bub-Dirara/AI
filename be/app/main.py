from fastapi import FastAPI
from .db import Base, engine
# 모델을 메타데이터에 등록
from .models import user as user_model  # noqa: F401
from .api import router as be_router  # << 집합 라우터

from .routes.auth import router as auth_router
# (다른 라우터도 있으면 아래에 추가)

def create_app() -> FastAPI:
    app = FastAPI(
        title="JeonSafe API",
        version="0.1.0",
        description="전세 계약 사기 위험도 분석, 증거 자료 관리, 법률 상담 지원을 위한 백엔드 REST API",
    )
    # 모델 import 이후에 테이블 생성
    Base.metadata.create_all(bind=engine)

    @app.get("/", summary="Health")
    def health():
        return {"ok": True}

    # 집합 라우터 장착 (/api/...)
    app.include_router(be_router)
    return app

# 단독 실행도 가능하게 유지
app = create_app()
