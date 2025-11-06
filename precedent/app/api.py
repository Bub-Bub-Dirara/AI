from fastapi import APIRouter
from .gpt import gpt_router
from .case_search_topk import cases_router
from .laws_api import laws_router

router = APIRouter(prefix="/ai", tags=["AI-Precedent"])
# 각 기능 라우터를 /ai 아래로 묶기
router.include_router(laws_router)   # /ai/laws/...
router.include_router(gpt_router)    # /ai/gpt/...
router.include_router(cases_router)  # /ai/cases/...
