from fastapi import APIRouter

# 내부 라우터들
from .routes.auth import router as auth_router
# from .routes.precheck import router as precheck_router  # 있으면 추가
from .routes.chat import router as chat_router  # 있다면 유지
from .routes.admin import router as admin_router

router = APIRouter(tags=["BE"])

# 개별 라우터 include
router.include_router(auth_router)
router.include_router(chat_router)
router.include_router(admin_router)
# router.include_router(precheck_router)
