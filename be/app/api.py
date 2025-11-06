from fastapi import APIRouter

# 내부 라우터들
from .routes.auth import router as auth_router
# from .routes.precheck import router as precheck_router  # 있으면 추가

router = APIRouter(prefix="/api", tags=["BE"])

# 개별 라우터 include
router.include_router(auth_router)
# router.include_router(precheck_router)

@router.post("/auth/login")
def login():
    return {"ok": True}

@router.post("/auth/signup")
def signup():
    return {"ok": True}

@router.post("/chat/logs")
def save_chat():
    return {"saved": True}
