from .auth import router as auth_router
from .precheck import router as precheck_router
from .chat import router as chat_router
from .upload import router as upload_router

__all__ = ["auth_router", "precheck_router", "chat_router", "upload_router"]

from fastapi import APIRouter

router = APIRouter()

router.include_router(auth_router)
router.include_router(precheck_router)
router.include_router(chat_router)
router.include_router(upload_router)
