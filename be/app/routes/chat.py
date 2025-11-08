from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
# 하단 MessageOut이 필요 없다면 임포트하지 않아도 됨
from ..schemas.chat import ChatLogIn, SaveResult
# 필요 시: from ..schemas.chat import MessageOut
# DB 모델이 있다면 import (예: ChatLog)
# from ..models.chat import ChatLog

router = APIRouter(prefix="/api/chat", tags=["BE"])

@router.post("/logs", response_model=SaveResult, summary="채팅 로그 저장")
def save_chat(payload: ChatLogIn, db: Session = Depends(get_db)):
    # DB 모델이 준비되지 않았다면 임시로 no-op 저장 로직 (서버 기동 우선)
    # 나중에 실제 DB 저장 코드로 교체:
    #   for m in payload.messages:
    #       db.add(ChatLog(session_id=payload.session_id, role=m.role, content=m.content))
    #   db.commit()
    return SaveResult(ok=True, count=len(payload.messages))
