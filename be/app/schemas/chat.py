from __future__ import annotations
from typing import List, Literal
from datetime import datetime
from pydantic import BaseModel, Field

# 요청 바디: 대화 메시지 단위
class ChatMessageIn(BaseModel):
    role: Literal["user", "assistant", "system"] = Field(..., description="역할")
    content: str = Field(..., description="메시지 내용")

# 요청 바디: 한 번에 저장할 로그 묶음
class ChatLogIn(BaseModel):
    session_id: str = Field(..., description="세션/대화 ID")
    messages: List[ChatMessageIn] = Field(..., min_items=1, description="저장할 메시지 목록")

# 응답 바디(개별 메시지 조회용이 필요하다면)
class MessageOut(BaseModel):
    id: int
    session_id: str
    role: str
    content: str
    created_at: datetime

# 응답 바디(저장 결과)
class SaveResult(BaseModel):
    ok: bool = True
    count: int = 0
