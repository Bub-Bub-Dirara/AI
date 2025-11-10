from datetime import datetime
from pydantic import BaseModel
from typing import Optional, Literal, List
from .chat_message import MessageOut

Channel = Literal["PREVENTION", "POST_CASE"]

class ThreadCreate(BaseModel):
    user_id: int
    channel: Channel
    title: Optional[str] = None


class ThreadOut(BaseModel):
    id: int
    user_id: int
    channel: Channel
    title: Optional[str]
    status: str
    created_at: datetime
    closed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ThreadDetailOut(ThreadOut):
    # 쓰레드 상세에 최근 메시지 N개를 포함해 내려주고 싶을 때 사용
    recent_messages: Optional[List[MessageOut]] = None


class ThreadListOut(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[ThreadOut]
